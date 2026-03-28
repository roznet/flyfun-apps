def _call_tool_fn(tool, **kwargs):
    return tool.fn(**kwargs)


def test_server_search_airports(server_module):
    result = _call_tool_fn(
        server_module.search_airports,
        query="LFPG",
        max_results=5,
        filters={"country": "FR"},
        include_large_airports=True,
    )

    assert result["count"] >= 1
    assert any(airport["ident"] == "LFPG" for airport in result["airports"])


def test_server_search_airports_ga(server_module):
    """Default search excludes large commercial airports."""
    result = _call_tool_fn(
        server_module.search_airports,
        query="LFPT",
        max_results=5,
    )
    assert result["count"] >= 1


def test_server_find_airports_near_route(server_module):
    result = _call_tool_fn(
        server_module.find_airports_near_route,
        from_location="EGTF",
        to_location="LFPT",
        max_distance_nm=40,
    )

    assert result["count"] >= 1
    assert result["airports"]


def test_server_get_data_coverage(server_module):
    result = _call_tool_fn(server_module.get_data_coverage)
    assert result["available"] is True
    assert len(result["countries_with_aip_data"]) > 0
    country = result["countries_with_aip_data"][0]
    assert "country_iso" in country
    assert "airac_date" in country
    assert "airports_with_aip_data" in country


def test_server_calculate_flight_distance(server_module):
    result = _call_tool_fn(
        server_module.calculate_flight_distance,
        from_location="EGTF",
        to_location="LFPT",
    )
    assert result["found"] is True
    assert result["distance_nm"] > 0

