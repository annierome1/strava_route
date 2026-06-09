"""
Agentic route recipe builder (4a + 4b).

Claude uses tool calls to investigate the rider's territory and IRL profile
before finalizing the recipe. This turns recipe building from a one-shot
prompt into a 2–3 step reasoning loop, producing recipes grounded in
real rider data rather than general heuristics.

Tools available during recipe building:
  check_area_novelty  — how many past rides cover a given bounding box
  get_irl_profile     — learned road preference weights from GPS history
  finalize_recipe     — structured output; Claude MUST call this to finish
"""
import anthropic
import json
import re
from typing import Optional

from src.layers.dream_generator.recipe import RouteRecipe
from src.layers.route_dna.taste_profile import TasteProfile


RECIPE_SYSTEM = """You are a cycling route architect. Craft a route recipe that matches both the
rider's explicit request and their actual riding history.

You have tools to verify choices before finalizing:
- check_area_novelty: see how familiar a bounding box is based on past ride coverage
- get_irl_profile: access their GPS-learned road preferences (traffic aversion, grade seeking, etc.)
- finalize_recipe: structured output — always end by calling this

Use 1–2 tool calls maximum, then finalize. Think concisely."""


AGENT_TOOLS = [
    {
        "name": "check_area_novelty",
        "description": (
            "Check how many of this rider's past rides have covered an area. "
            "Returns overlap_count and novelty_score (0.0=all been there, 1.0=completely new). "
            "Useful when the request implies going to a specific area or the rider wants new roads."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_lat": {"type": "number"},
                "min_lng": {"type": "number"},
                "max_lat": {"type": "number"},
                "max_lng": {"type": "number"},
            },
            "required": ["min_lat", "min_lng", "max_lat", "max_lng"],
        },
    },
    {
        "name": "get_irl_profile",
        "description": (
            "Get this rider's GPS-learned road preference profile (IRL model). "
            "Returns whether they implicitly prefer cycleways, avoid traffic, seek or avoid climbs, "
            "and prefer paved roads. Use this to validate traffic_tolerance and surface choices."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "finalize_recipe",
        "description": "Submit the completed route recipe and a personalised explanation for the rider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "distance_km":        {"type": "array", "items": {"type": "number"}, "description": "[lo_km, hi_km]"},
                "elevation_m":        {"type": "array", "items": {"type": "number"}, "description": "[lo_m, hi_m]"},
                "climb_profile":      {"type": "string", "enum": ["flat", "rolling", "one_big_climb", "punchy"]},
                "climb_position":     {"type": "string", "enum": ["early", "middle", "late", "distributed"]},
                "min_climbs":         {"type": "integer"},
                "max_climbs":         {"type": "integer"},
                "traffic_tolerance":  {"type": "string", "enum": ["low", "medium", "high"]},
                "surface":            {"type": "string", "enum": ["paved", "mixed", "any"]},
                "route_shape":        {"type": "string", "enum": ["loop", "out_and_back", "either"]},
                "novelty":            {"type": "string", "enum": ["new_roads", "familiar", "mixed"]},
                "effort_intent":      {"type": "string", "enum": ["endurance", "threshold", "recovery", "adventure"]},
                "mood":               {"type": "string", "description": "Preserve the user's exact phrase"},
                "distance_influence": {"type": "integer", "description": "50=scenic, 300=efficient"},
                "target_distance_m":  {"type": "integer", "description": "Midpoint of distance range in meters"},
                "geographic_target":  {
                    "type": ["string", "null"],
                    "enum": ["coastal", "mountain", "forest", "park", "ridge", None],
                },
                "avoid_surface":      {"type": "string", "enum": ["none", "unpaved", "gravel"]},
                "explanation":        {
                    "type": "string",
                    "description": "2–3 sentences to the rider explaining why this recipe matches their request and history",
                },
            },
            "required": [
                "distance_km", "elevation_m", "climb_profile", "climb_position",
                "min_climbs", "max_climbs", "traffic_tolerance", "surface", "route_shape",
                "novelty", "effort_intent", "mood", "distance_influence", "target_distance_m",
                "geographic_target", "avoid_surface", "explanation",
            ],
        },
    },
]


PROFILE_PROMPT = """RIDER TASTE PROFILE:
Preferred distance: {d_lo}–{d_hi} km (median {d_med} km)
Preferred elevation: {e_lo}–{e_hi} m ({vkm} m/km)
Grade mix: {pct_flat}% flat / {pct_rolling}% rolling / {pct_steep}% steep
Avg climbs per ride: {climbs} | Favors sustained: {sustained} | Favors punchy: {punchy}
Typical effort shape: {shape}
Explorer index: {novelty:.0%} new roads | Prefers loops: {loops}
Signature tags: {tags}

Recipe guidelines:
- Honor explicit numbers if the user named them; otherwise use upper end of their range for "epic"/"long".
- geographic_target: "coastal"/"beach" → "coastal"; "mountain"/"peak"/"summit" → "mountain"; "forest"/"woods" → "forest"; "park"/"greenway" → "park"; "ridge" → "ridge". Otherwise null.
- avoid_surface: "unpaved" if "paved only"/"no gravel"/"road only"; "gravel" if gravel specifically avoided; "none" otherwise.
- distance_influence: 50=scenic/willing to detour, 300=strictly shortest qualifying path.
- target_distance_m = midpoint of distance_km range × 1000.
- Use check_area_novelty if the request implies a direction or new territory.
- Use get_irl_profile to verify traffic_tolerance and surface align with actual GPS preferences.
- Call finalize_recipe with the complete recipe and a 2–3 sentence personalised explanation.

<user_request>
{prompt}
</user_request>

Think, use up to 2 tools, then finalize."""


def _bbox_overlap(b1: list, b2: list) -> float:
    i_min_lat = max(b1[0], b2[0]); i_max_lat = min(b1[2], b2[2])
    i_min_lng = max(b1[1], b2[1]); i_max_lng = min(b1[3], b2[3])
    if i_min_lat >= i_max_lat or i_min_lng >= i_max_lng:
        return 0.0
    i_area = (i_max_lat - i_min_lat) * (i_max_lng - i_min_lng)
    b1_area = (b1[2] - b1[0]) * (b1[3] - b1[1])
    return i_area / b1_area if b1_area > 0 else 0.0


def _handle_tool(name: str, tool_input: dict, ride_bboxes: list, irl_weights: Optional[list]) -> dict:
    if name == "check_area_novelty":
        bbox = [
            tool_input["min_lat"], tool_input["min_lng"],
            tool_input["max_lat"], tool_input["max_lng"],
        ]
        overlaps = sum(1 for rb in ride_bboxes if _bbox_overlap(bbox, list(rb)) > 0.2)
        novelty  = max(0.0, 1.0 - overlaps / max(len(ride_bboxes), 1))
        return {"previous_rides_in_area": overlaps, "novelty_score": round(novelty, 2)}

    if name == "get_irl_profile":
        if not irl_weights:
            return {"available": False, "message": "IRL model not trained yet for this rider."}
        from src.builds.irl_engine.engine import MaxEntropyIRL
        import numpy as np
        model = MaxEntropyIRL()
        model.weights = np.array(irl_weights)
        return {"available": True, **model.explain_weights()}

    return {"error": f"Unknown tool: {name}"}


def _extract_json(response) -> dict:
    for block in response.content:
        text = getattr(block, "text", None)
        if not text:
            continue
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    raise ValueError(
        f"No valid JSON in response: {[getattr(b, 'text', '')[:120] for b in response.content]}"
    )


async def build_route_recipe(
    user_prompt: str,
    taste: TasteProfile,
    home: Optional[tuple] = None,
    ride_bboxes: Optional[list] = None,
    irl_weights: Optional[list] = None,
) -> tuple:
    """
    Agentic recipe builder. Claude uses tools to verify area novelty and IRL preferences
    before submitting the finalized recipe via the finalize_recipe tool.

    Returns (RouteRecipe, explanation, thinking_trace).
    thinking_trace is a list of {"type": ..., ...} dicts for UI display.
    """
    client  = anthropic.AsyncAnthropic()
    bboxes  = ride_bboxes or []

    prompt_content = PROFILE_PROMPT.format(
        d_lo=taste.preferred_distance_km[0], d_hi=taste.preferred_distance_km[1],
        d_med=taste.median_distance_km,
        e_lo=taste.preferred_elevation_m[0], e_hi=taste.preferred_elevation_m[1],
        vkm=taste.vert_per_km,
        pct_flat=int(taste.grade_distribution["flat"] * 100),
        pct_rolling=int(taste.grade_distribution["rolling"] * 100),
        pct_steep=int(taste.grade_distribution["steep"] * 100),
        climbs=taste.avg_climbs_per_ride,
        sustained=taste.favors_sustained, punchy=taste.favors_punchy,
        shape=taste.effort_shape,
        novelty=taste.avg_novelty_score, loops=taste.prefers_loops,
        tags=", ".join(taste.signature_tags),
        prompt=user_prompt,
    )

    messages        = [{"role": "user", "content": prompt_content}]
    thinking_trace  = []

    for _round in range(4):  # max 3 tool rounds + 1 final
        resp = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=RECIPE_SYSTEM,
            tools=AGENT_TOOLS,
            messages=messages,
        )

        # Capture any inline reasoning text
        for block in resp.content:
            if getattr(block, "type", None) == "text" and block.text.strip():
                thinking_trace.append({"type": "thinking", "content": block.text.strip()})

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                if block.name == "finalize_recipe":
                    data        = dict(block.input)
                    explanation = data.pop("explanation", "")
                    recipe      = RouteRecipe.from_dict(data)
                    thinking_trace.append({"type": "finalized", "recipe_mood": recipe.mood})
                    return recipe, explanation, thinking_trace

                result = _handle_tool(block.name, block.input, bboxes, irl_weights)
                thinking_trace.append({
                    "type":   "tool_call",
                    "name":   block.name,
                    "input":  block.input,
                    "result": result,
                })
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(result),
                })

            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user",      "content": tool_results})

        else:
            # end_turn without finalize_recipe — parse JSON from text
            for block in resp.content:
                text = getattr(block, "text", "")
                if "{" in text:
                    m = re.search(r"\{[\s\S]*\}", text)
                    if m:
                        try:
                            data        = json.loads(m.group())
                            explanation = data.pop("explanation", "")
                            recipe      = RouteRecipe.from_dict(data)
                            thinking_trace.append({"type": "finalized", "recipe_mood": recipe.mood})
                            return recipe, explanation, thinking_trace
                        except Exception:
                            pass
            break

    # Safety fallback: one-shot call without tools
    fallback = await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system="You are a cycling route architect. Return ONLY valid JSON with all recipe fields plus an 'explanation' key. No commentary.",
        messages=[{"role": "user", "content": prompt_content}],
    )
    data        = _extract_json(fallback)
    explanation = data.pop("explanation", "")
    thinking_trace.append({"type": "fallback"})
    return RouteRecipe.from_dict(data), explanation, thinking_trace
