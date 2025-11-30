def _call_tool_fn(tool, **kwargs):
    return tool.fn(**kwargs)


def test_server_search_airports(server_module):
    result = _call_tool_fn(
        server_module.search_airports,
        query="LFPG",
        max_results=5,
        filters={"country": "FR"},
    )

    assert result["count"] >= 1
    assert any(airport["ident"] == "LFPG" for airport in result["airports"])


def test_server_find_airports_near_route(server_module):
    result = _call_tool_fn(
        server_module.find_airports_near_route,
        from_location="EGLL",
        to_location="LFPG",
        max_distance_nm=40,
    )

    assert result["count"] >= 1
    assert result["airports"]

