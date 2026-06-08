import asyncio
from typing import Optional

import anthropic
import structlog

from src.layers.dream_generator.recipe_builder import build_route_recipe
from src.layers.route_builder.routing_client import generate_candidates
from src.layers.route_builder.scorer import score_candidate
from src.layers.route_dna.taste_profile import TasteProfile
from src.platform.logger import GenerationLogger

log = structlog.get_logger()


async def generate_dream_ride(
    user_prompt: str,
    taste: TasteProfile,
    home: tuple,
    historical_bboxes: list,
    graphhopper_key: str,
    generation_logger: GenerationLogger,
    end: tuple = None,
    is_loop: bool = True,
    irl_weights: Optional[list] = None,
) -> dict:
    """
    Full pipeline: prompt → agentic recipe → 3 candidate routes → scored → explained.
    Pass end=(lat,lng) + is_loop=False for point-to-point routes.
    irl_weights are used to tune ORS steepness and are passed to the recipe builder
    so Claude can call get_irl_profile during reasoning.
    """
    # 1. Build recipe — agentic loop with tool use (returns thinking trace)
    recipe, recipe_explanation, thinking_trace = await build_route_recipe(
        user_prompt, taste,
        home=home,
        ride_bboxes=historical_bboxes,
        irl_weights=irl_weights,
    )
    log.info("recipe_built", mood=recipe.mood, distance=recipe.distance_km, elevation=recipe.elevation_m)

    # 2. Generate 3 candidates (GraphHopper/ORS, parallel)
    candidates = await generate_candidates(
        recipe, home, graphhopper_key,
        end=end, is_loop=is_loop,
        library_bboxes=historical_bboxes,
        irl_weights=irl_weights,
    )
    if not candidates:
        raise RuntimeError("GraphHopper returned no valid routes")

    # 3. Score each candidate
    scores = {c.variant: score_candidate(c, recipe, taste, historical_bboxes)
              for c in candidates}

    # 4. Per-route one-line explanation (Claude Haiku, parallel)
    async def explain_one(c) -> str:
        score = scores[c.variant]
        prompt = (
            f'The rider asked for: "{user_prompt}". '
            f'This is the "{c.variant}" option: {c.distance_km}km, {c.elevation_m}m elevation. '
            f'Score notes: {"; ".join(score.notes) or "fits well"}. '
            f'Write ONE sentence (max 20 words) explaining why this option suits the mood. '
            f'Be specific. No stats verbatim.'
        )
        client = anthropic.AsyncAnthropic()
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=60,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()

    explanations = await asyncio.gather(*[explain_one(c) for c in candidates])

    # 5. Sort by score
    ranked = sorted(
        zip(candidates, explanations),
        key=lambda x: scores[x[0].variant].total,
        reverse=True
    )

    result = {
        "user_prompt": user_prompt,
        "recipe_explanation": recipe_explanation,
        "recipe": recipe.to_dict(),
        "thinking_trace": thinking_trace,
        "routes": [
            {
                "variant":     c.variant,
                "rank":        i + 1,
                "distance_km": c.distance_km,
                "elevation_m": c.elevation_m,
                "score":       score.__dict__,
                "explanation": explanation,
                "geojson":     c.geojson,
            }
            for i, (c, explanation) in enumerate(ranked)
            for score in [scores[c.variant]]
        ]
    }

    generation_logger.log("dream_ride", user_prompt, recipe, list(scores.values()))
    return result
