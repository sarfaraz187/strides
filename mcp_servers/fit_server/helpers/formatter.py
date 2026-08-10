def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
            Event: {props.get("event", "Unknown")}
            Area: {props.get("areaDesc", "Unknown")}
            Severity: {props.get("severity", "Unknown")}
            Description: {props.get("description", "No description available")}
            Instructions: {props.get("instruction", "No specific instructions provided")}
            """


def parse_run(data_point: dict) -> list[dict]:
    parsed_runs = []

    for run_entry in data_point.get("dataPoints", []):
        exercise_data = run_entry["exercise"]
        interval_data = exercise_data["interval"]
        metrics_summary = exercise_data["metricsSummary"]

        start_time = interval_data["startTime"]
        distance_mm = metrics_summary.get("distanceMillimeters")
        duration_str = exercise_data["activeDuration"]
        calories = metrics_summary.get("caloriesKcal")

        distance_km = distance_mm / 1_000_000 if distance_mm is not None else None
        duration_seconds = float(duration_str.rstrip("s"))
        duration_min = duration_seconds / 60
        pace_min_per_km = duration_min / distance_km if distance_km else None

        parsed_runs.append(
            {
                "date": start_time,
                "distance_km": round(distance_km, 2) if distance_km is not None else None,
                "duration_min": round(duration_min, 1),
                "pace_min_per_km": round(pace_min_per_km, 2)
                if pace_min_per_km is not None
                else None,
                "calories": calories,
            }
        )

    return parsed_runs
