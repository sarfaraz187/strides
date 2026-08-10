from mcp_servers.fit_server.helpers.formatter import parse_run


def test_parse_run_with_distance_computes_distance_and_pace():
    data_point = {
        "dataPoints": [
            {
                "exercise": {
                    "interval": {"startTime": "2026-08-10T13:29:55.865Z"},
                    "metricsSummary": {"distanceMillimeters": 5_000_000, "caloriesKcal": 300},
                    "activeDuration": "1800s",
                }
            }
        ]
    }

    result = parse_run(data_point)

    assert result == [
        {
            "date": "2026-08-10T13:29:55.865Z",
            "distance_km": 5.0,
            "duration_min": 30.0,
            "pace_min_per_km": 6.0,
            "calories": 300,
        }
    ]


def test_parse_run_without_distance_millimeters_omits_distance_and_pace():
    data_point = {
        "dataPoints": [
            {
                "exercise": {
                    "interval": {"startTime": "2026-08-10T11:01:00Z"},
                    "metricsSummary": {},
                    "activeDuration": "1440s",
                }
            }
        ]
    }

    result = parse_run(data_point)

    assert result == [
        {
            "date": "2026-08-10T11:01:00Z",
            "distance_km": None,
            "duration_min": 24.0,
            "pace_min_per_km": None,
            "calories": None,
        }
    ]
