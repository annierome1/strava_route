import anthropic
import json
import re
import asyncio

from src.layers.dream_generator.recipe import RouteRecipe
from src.layers.route_dna.taste_profile import TasteProfile


RECIPE_SYSTEM = """You are a cycling route architect. You translate a rider's request into
a precise route recipe, grounded entirely in their actual riding history.
Return ONLY valid JSON. No commentary."""

RECIPE_PROMPT = """RIDER TASTE PROFILE:
Preferred distance: {d_lo}–{d_hi} km (median {d_med} km)
Preferred elevation: {e_lo}–{e_hi} m ({vkm} m/km)
Grade mix: {pct_flat}% flat / {pct_rolling}% rolling / {pct_steep}% steep
Avg climbs per ride: {climbs}
Favors sustained climbs: {sustained} | Favors punchy: {punchy}
Typical effort shape: {shape}
Explorer index: {novelty:.0%} new roads
Prefers loops: {loops}
Tags: {tags}

USER REQUEST: "{prompt}"

Instructions:
- Honor explicit distance/elevation if the user named numbers.
- If vague ("something long", "epic"), use the upper end of their preferred range.
- Anchor climb_profile and novelty to this rider's actual history — not to the mood alone.
- distance_influence: 50 = scenic/willing to detour, 300 = strictly shortest qualifying path.
- target_distance_m = midpoint of distance range in meters.
- geographic_target: extract from user language. "coastal"/"beach"/"ocean" → "coastal";
  "mountain"/"peak"/"summit" → "mountain"; "forest"/"woods" → "forest";
  "park"/"greenway" → "park"; "ridge"/"ridgeline" → "ridge". Otherwise null.
- avoid_surface: "unpaved" if user says "paved only", "no gravel", "road only", etc.
  "gravel" if user explicitly wants gravel avoided but dirt/unpaved OK. "none" otherwise.

Return JSON:
{{
  "distance_km":        [float, float],
  "elevation_m":        [int, int],
  "climb_profile":      "flat|rolling|one_big_climb|punchy",
  "climb_position":     "early|middle|late|distributed",
  "min_climbs":         0,
  "max_climbs":         0,
  "traffic_tolerance":  "low|medium|high",
  "surface":            "paved|mixed|any",
  "route_shape":        "loop|out_and_back|either",
  "novelty":            "new_roads|familiar|mixed",
  "effort_intent":      "endurance|threshold|recovery|adventure",
  "mood":               "<preserve exact user phrase>",
  "distance_influence": 100,
  "target_distance_m":  0,
  "geographic_target":  null,
  "avoid_surface":      "none"
}}"""

EXPLAIN_PROMPT = """A cyclist asked for: "{prompt}"

You built this recipe for them:
- Distance: {d_lo}–{d_hi} km
- Elevation: {e_lo}–{e_hi} m
- Climb profile: {climb_profile}, positioned {climb_position}
- Roads: {traffic} traffic, {surface} surface, {shape}
- Novelty: {novelty}

Their signature: {tags}

Write 2–3 sentences to the rider in second person explaining why THIS recipe matches both
their request and their actual riding style. Cite 1–2 data points from their profile. Be
specific. Do not start with "I". Do not restate every stat."""


def _extract_json(response) -> dict:
    """Pull JSON out of an Anthropic response regardless of block type or markdown fencing."""
    for block in response.content:
        text = getattr(block, "text", None)
        if not text:
            continue
        text = text.strip()
        # Strip markdown fences: ```json ... ``` or ``` ... ```
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
        if not text:
            continue
        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try extracting first JSON object from prose
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    raise ValueError(f"No valid JSON found in model response. Content: {[getattr(b, 'text', '')[:120] for b in response.content]}")


async def build_route_recipe(
    user_prompt: str,
    taste: TasteProfile,
) -> tuple:
    """Returns (RouteRecipe, rider_narrative_explanation)."""
    client = anthropic.AsyncAnthropic()

    recipe_content = RECIPE_PROMPT.format(
        d_lo=taste.preferred_distance_km[0],
        d_hi=taste.preferred_distance_km[1],
        d_med=taste.median_distance_km,
        e_lo=taste.preferred_elevation_m[0],
        e_hi=taste.preferred_elevation_m[1],
        vkm=taste.vert_per_km,
        pct_flat=int(taste.grade_distribution["flat"] * 100),
        pct_rolling=int(taste.grade_distribution["rolling"] * 100),
        pct_steep=int(taste.grade_distribution["steep"] * 100),
        climbs=taste.avg_climbs_per_ride,
        sustained=taste.favors_sustained,
        punchy=taste.favors_punchy,
        shape=taste.effort_shape,
        novelty=taste.avg_novelty_score,
        loops=taste.prefers_loops,
        tags=", ".join(taste.signature_tags),
        prompt=user_prompt
    )

    recipe_resp = await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=RECIPE_SYSTEM,
        messages=[{"role": "user", "content": recipe_content}]
    )

    data = _extract_json(recipe_resp)
    recipe = RouteRecipe.from_dict(data)

    explain_content = EXPLAIN_PROMPT.format(
        prompt=user_prompt,
        d_lo=recipe.distance_km[0], d_hi=recipe.distance_km[1],
        e_lo=recipe.elevation_m[0], e_hi=recipe.elevation_m[1],
        climb_profile=recipe.climb_profile,
        climb_position=recipe.climb_position,
        traffic=recipe.traffic_tolerance,
        surface=recipe.surface,
        shape=recipe.route_shape,
        novelty=recipe.novelty,
        tags=", ".join(taste.signature_tags)
    )

    explain_resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": explain_content}]
    )

    explanation = explain_resp.content[0].text.strip()
    return recipe, explanation
