import json
from datetime import date
from pathlib import Path


VARIANT_COLORS = {
    "match":  "#22c55e",   # --route-match
    "harder": "#f59e0b",   # --route-harder
    "scenic": "#6366f1",   # --route-scenic
}

VARIANT_LABELS = {
    "match":  "BEST MATCH",
    "harder": "HARDER",
    "scenic": "SCENIC",
}


def render_dream_route_html(result: dict, mapbox_token: str, output_dir: str = "outputs") -> str:
    """
    Renders a self-contained HTML file with three-panel Mapbox route map.
    Returns the output file path.
    """
    today = date.today().isoformat()
    filename = f"dream-route-{today}.html"
    filepath = Path(output_dir) / filename

    routes = result["routes"]
    user_prompt = result["user_prompt"]
    recipe_explanation = result["recipe_explanation"]

    # Build per-route map layers JS
    layers_js = []
    for r in routes:
        variant = r["variant"]
        color = VARIANT_COLORS.get(variant, "#fc4c02")
        geojson_str = json.dumps(r["geojson"])
        layers_js.append(f"""
            map.addSource('route-{variant}', {{
                type: 'geojson',
                data: {{
                    type: 'Feature',
                    geometry: {geojson_str}
                }}
            }});
            map.addLayer({{
                id: 'route-{variant}-line',
                type: 'line',
                source: 'route-{variant}',
                layout: {{ 'line-join': 'round', 'line-cap': 'round' }},
                paint: {{ 'line-color': '{color}', 'line-width': 4 }}
            }});
        """)

    # Build route panels HTML
    panels_html = []
    for r in routes:
        variant = r["variant"]
        color = VARIANT_COLORS.get(variant, "#fc4c02")
        label = VARIANT_LABELS.get(variant, variant.upper())
        star = "★ " if r["rank"] == 1 else ""
        score_pct = int(r["score"]["total"] * 100)
        panels_html.append(f"""
            <div class="route-panel" onclick="focusRoute('{variant}')" data-variant="{variant}">
                <div class="panel-header" style="border-top: 3px solid {color}">
                    <span class="panel-label">{star}{label}</span>
                    <span class="panel-score" style="color:{color}">Score: {r['score']['total']:.2f}</span>
                </div>
                <div class="panel-stats">
                    <span>{r['distance_km']}km</span>
                    <span>·</span>
                    <span>{r['elevation_m']:,}m</span>
                </div>
                <div class="panel-explanation">{r['explanation']}</div>
            </div>
        """)

    # Compute map center from first route
    center = [0, 0]
    if routes and routes[0].get("geojson", {}).get("coordinates"):
        coords = routes[0]["geojson"]["coordinates"]
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        center = [sum(lngs) / len(lngs), sum(lats) / len(lats)]

    all_coords = []
    for r in routes:
        coords = r.get("geojson", {}).get("coordinates", [])
        all_coords.extend(coords)

    bounds_js = ""
    if all_coords:
        min_lng = min(c[0] for c in all_coords)
        max_lng = max(c[0] for c in all_coords)
        min_lat = min(c[1] for c in all_coords)
        max_lat = max(c[1] for c in all_coords)
        bounds_js = f"map.fitBounds([[{min_lng},{min_lat}],[{max_lng},{max_lat}]], {{padding: 40}});"

    layers_js_str = "\n".join(layers_js)
    panels_html_str = "\n".join(panels_html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strava AI Route Planner</title>
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.css" rel="stylesheet">
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.js"></script>
    <style>
        :root {{
            --bg:             #0f1117;
            --surface:        #1a1d27;
            --surface-alt:    #22263a;
            --border:         #2a2d3a;
            --strava:         #fc4c02;
            --route-match:    #22c55e;
            --route-harder:   #f59e0b;
            --route-scenic:   #6366f1;
            --text-primary:   #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted:     #64748b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        .header {{
            padding: 16px 24px;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
        }}
        .header h1 {{
            font-size: 13px;
            font-weight: 500;
            color: var(--strava);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 4px;
        }}
        .header .prompt {{
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
        }}
        .header .explanation {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 6px;
        }}
        .main {{
            display: flex;
            flex: 1;
            overflow: hidden;
        }}
        #map {{
            flex: 1;
        }}
        .sidebar {{
            width: 340px;
            background: var(--surface);
            border-left: 1px solid var(--border);
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 1px;
        }}
        .route-panel {{
            background: var(--surface-alt);
            padding: 16px;
            cursor: pointer;
            border-left: 3px solid transparent;
            transition: border-color 0.15s, background 0.15s;
        }}
        .route-panel:hover, .route-panel.active {{
            background: var(--surface);
            border-left-color: var(--strava);
        }}
        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 8px;
            margin-bottom: 8px;
        }}
        .panel-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--text-primary);
        }}
        .panel-score {{
            font-size: 12px;
            font-weight: 600;
        }}
        .panel-stats {{
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 8px;
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .panel-stats span:nth-child(2) {{
            color: var(--text-muted);
            font-size: 14px;
        }}
        .panel-explanation {{
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Strava AI Route Planner</h1>
        <div class="prompt">"{user_prompt}"</div>
        <div class="explanation">{recipe_explanation}</div>
    </div>
    <div class="main">
        <div id="map"></div>
        <div class="sidebar">
            {panels_html_str}
        </div>
    </div>

    <script>
        mapboxgl.accessToken = '{mapbox_token}';
        const map = new mapboxgl.Map({{
            container: 'map',
            style: 'mapbox://styles/mapbox/dark-v11',
            center: {json.dumps(center)},
            zoom: 10
        }});

        map.on('load', () => {{
            {layers_js_str}
            {bounds_js}
        }});

        function focusRoute(variant) {{
            document.querySelectorAll('.route-panel').forEach(p => p.classList.remove('active'));
            const panel = document.querySelector(`[data-variant="${{variant}}"]`);
            if (panel) panel.classList.add('active');
        }}
    </script>
</body>
</html>"""

    filepath.parent.mkdir(exist_ok=True)
    filepath.write_text(html)
    return str(filepath)


def render_training_route_html(result: dict, adaptation: str, mapbox_token: str, output_dir: str = "outputs") -> str:
    """Renders a training route HTML file."""
    today = date.today().isoformat()
    filename = f"training-{adaptation}-{today}.html"
    result["user_prompt"] = result.get("user_prompt", f"Training: {adaptation}")
    filepath_str = render_dream_route_html(result, mapbox_token, output_dir)
    # Rename to training filename
    old = Path(filepath_str)
    new = old.parent / filename
    old.rename(new)
    return str(new)
