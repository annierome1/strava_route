"""FastAPI dependency: validates a Supabase JWT, returns the user_id."""
import structlog
from fastapi import Header, HTTPException
from .db import get_supabase

log = structlog.get_logger()


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        log.warning("auth_failed", reason="missing_header", has_header=bool(authorization))
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ")
    try:
        response = get_supabase().auth.get_user(token)
        if not response.user:
            log.warning("auth_failed", reason="no_user_returned")
            raise HTTPException(status_code=401, detail="Invalid token")
        return response.user.id
    except HTTPException:
        raise
    except Exception as e:
        log.warning("auth_failed", reason="exception", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid token")
