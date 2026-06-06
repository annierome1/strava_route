"""
CLI entry point for the Dream Ride Generator.

Usage:
    python -m src.builds.dream_ride.cli "quiet European training day, 60 miles"
    python -m src.builds.dream_ride.cli "something long with a big climb in the middle"
    python -m src.builds.dream_ride.cli "fast flat loop, 2 hours max"
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


async def main(user_prompt: str):
    import sqlite3
    from src.layers.route_dna.taste_profile import taste_profile_from_dict
    from src.builds.dream_ride.generator import generate_dream_ride
    from src.builds.dream_ride.renderer import render_dream_route_html
    from src.platform.logger import GenerationLogger

    db_path = os.environ.get("DB_PATH", ".route_planner.db")
    graphhopper_key = os.environ.get("GRAPHHOPPER_API_KEY", "")
    mapbox_token = os.environ.get("MAPBOX_TOKEN", "")

    # Load taste profile
    db = sqlite3.connect(db_path)
    row = db.execute("SELECT profile_json FROM taste_profiles ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row:
        print("No taste profile found. Run: curl -X POST http://localhost:8000/dna/build", file=sys.stderr)
        sys.exit(1)

    taste = taste_profile_from_dict(json.loads(row[0]))

    # Load historical bboxes
    bboxes = []
    for (bbox_json,) in db.execute("SELECT bbox_json FROM ride_bboxes"):
        try:
            bboxes.append(tuple(json.loads(bbox_json)))
        except Exception:
            pass

    home = taste.home_coords or (0.0, 0.0)

    gen_logger = GenerationLogger(db_path)
    result = await generate_dream_ride(
        user_prompt=user_prompt,
        taste=taste,
        home=home,
        historical_bboxes=bboxes,
        graphhopper_key=graphhopper_key,
        generation_logger=gen_logger
    )

    # Print summary
    print(f"\n🚴 {user_prompt}")
    print(f"📋 {result['recipe_explanation']}\n")
    for r in result["routes"]:
        rank_star = "★" if r["rank"] == 1 else " "
        print(f"  {rank_star} [{r['variant'].upper():10}] {r['distance_km']}km · {r['elevation_m']}m"
              f"  score={r['score']['total']:.2f}  —  {r['explanation']}")

    if mapbox_token:
        html_path = render_dream_route_html(result, mapbox_token)
        print(f"\n📍 HTML route map: {html_path}")
    else:
        print("\n⚠  Set MAPBOX_TOKEN in .env to generate interactive map.")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.builds.dream_ride.cli '<prompt>'")
        sys.exit(1)
    prompt = " ".join(sys.argv[1:])
    asyncio.run(main(prompt))
