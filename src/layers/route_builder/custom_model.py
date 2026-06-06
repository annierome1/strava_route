from src.layers.dream_generator.recipe import RouteRecipe


def recipe_to_custom_model(recipe: RouteRecipe, variant: str = "match") -> dict:
    """
    Translates a RouteRecipe into a GraphHopper custom model.

    Variant tuning:
      match  — recipe defaults, balanced
      harder — higher distance_influence (efficient path to waypoints → more climbing)
      scenic — lower distance_influence + quiet road boost (more meandering)

    Reference: https://docs.graphhopper.com/openapi/custom-model
    multiply_by > 1.0 = preferred, < 1.0 = penalized.
    """
    priority = []

    # Hard-block motorways universally
    priority.append({"if": "road_class == MOTORWAY", "multiply_by": "0.01"})

    if recipe.traffic_tolerance == "low":
        priority += [
            {"if": "road_class == TRUNK",         "multiply_by": "0.1"},
            {"if": "road_class == PRIMARY",       "multiply_by": "0.2"},
            {"if": "road_class == SECONDARY",     "multiply_by": "0.4"},
            {"if": "road_class == CYCLEWAY",      "multiply_by": "2.0"},
            {"if": "road_class == LIVING_STREET", "multiply_by": "1.8"},
            {"if": "road_class == RESIDENTIAL",   "multiply_by": "1.5"},
        ]
    elif recipe.traffic_tolerance == "medium":
        priority += [
            {"if": "road_class == TRUNK",    "multiply_by": "0.3"},
            {"if": "road_class == PRIMARY",  "multiply_by": "0.6"},
            {"if": "road_class == CYCLEWAY", "multiply_by": "1.5"},
        ]
    # high: only motorway block above

    if recipe.surface == "paved":
        priority += [
            {"if": "road_environment == FORD", "multiply_by": "0.05"},
            {"if": "road_class == TRACK",      "multiply_by": "0.2"},
        ]
    elif recipe.surface == "mixed":
        priority.append({"if": "road_class == TRACK", "multiply_by": "0.7"})

    # Variant-specific road character tuning
    if variant == "scenic":
        priority += [
            {"if": "road_class == RESIDENTIAL",  "multiply_by": "1.3"},
            {"if": "road_class == UNCLASSIFIED",  "multiply_by": "1.3"},
            {"if": "road_class == TERTIARY",     "multiply_by": "1.1"},
        ]
        distance_influence = max(30, recipe.distance_influence - 60)
    elif variant == "harder":
        # More direct path to waypoints → naturally finds climbs en route
        distance_influence = min(300, recipe.distance_influence + 60)
    else:
        distance_influence = recipe.distance_influence

    return {
        "priority": priority,
        "distance_influence": distance_influence,
    }
