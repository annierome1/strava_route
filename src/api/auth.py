"""FastAPI dependency: validates a Supabase JWT.

Supports both EC (P-256 / ES256) keys — current Supabase default — and
legacy HS256 shared secrets.

Key resolution order for ES256:
  1. SUPABASE_JWT_JWK env var (single JWK as JSON string) — no network call
  2. JWKS fetch from Supabase auth endpoint — fallback, cached in-process
"""
import os
import jwt
import httpx
import structlog
from fastapi import Header, HTTPException

log = structlog.get_logger()

_jwks_cache: dict | None = None   # {kid: public_key}


def _key_from_env() -> object | None:
    """Load EC public key from env vars. Three formats tried in order:
    1. SUPABASE_JWT_JWK  — full JWK as a JSON string
    2. SUPABASE_JWT_X + SUPABASE_JWT_Y  — raw base64url coordinates (no JSON)
    """
    jwk_str = os.environ.get("SUPABASE_JWT_JWK", "").strip()
    if jwk_str:
        try:
            return jwt.algorithms.ECAlgorithm.from_jwk(jwk_str)
        except Exception as e:
            log.error("jwt_jwk_env_invalid", raw=repr(jwk_str[:120]), error=str(e))

    x = os.environ.get("SUPABASE_JWT_X", "").strip()
    y = os.environ.get("SUPABASE_JWT_Y", "").strip()
    if x and y:
        try:
            return jwt.algorithms.ECAlgorithm.from_jwk({"kty": "EC", "crv": "P-256", "x": x, "y": y})
        except Exception as e:
            log.error("jwt_coords_invalid", x_len=len(x), y_len=len(y), error=str(e))

    return None


async def _get_public_key(kid: str | None) -> object | None:
    """Return the ES256 public key. Env var takes priority over JWKS fetch."""
    env_key = _key_from_env()
    if env_key is not None:
        return env_key

    global _jwks_cache
    if _jwks_cache is None:
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{supabase_url}/auth/v1/.well-known/jwks.json")
                resp.raise_for_status()
                _jwks_cache = {}
                for key_data in resp.json().get("keys", []):
                    key_id = key_data.get("kid")
                    public_key = jwt.algorithms.ECAlgorithm.from_jwk(key_data)
                    _jwks_cache[key_id] = public_key
                log.info("jwks_loaded", key_count=len(_jwks_cache))
        except Exception as e:
            log.error("jwks_fetch_failed", error=str(e))
            return None
    return _jwks_cache.get(kid) if kid else (next(iter(_jwks_cache.values()), None) if _jwks_cache else None)


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.removeprefix("Bearer ")

    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")
        kid = header.get("kid")

        if alg == "HS256":
            # Legacy shared-secret path
            secret = os.environ.get("SUPABASE_JWT_SECRET", "")
            if not secret:
                raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
            payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})

        elif alg in ("ES256", "RS256"):
            # JWKS public-key path
            public_key = await _get_public_key(kid)
            if not public_key:
                raise HTTPException(status_code=500, detail="Could not load JWT signing key")
            payload = jwt.decode(token, public_key, algorithms=[alg], options={"verify_aud": False})

        else:
            log.warning("auth_unknown_alg", alg=alg)
            raise HTTPException(status_code=401, detail="Unsupported token algorithm")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except HTTPException:
        raise
    except Exception as e:
        log.warning("auth_failed", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid token")
