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
