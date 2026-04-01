"""Tests for AIP field query tools (list_aip_fields, query_aip_fields)."""

from shared.airport_tools import (
    list_aip_fields,
    query_aip_fields,
    _aip_collect_std_fields,
    _aip_resolve_field,
)


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

def test_collect_std_fields(tool_context):
    """_aip_collect_std_fields returns a non-empty dict of fields."""
    fields = _aip_collect_std_fields(tool_context.model)
    assert len(fields) > 0
    # Each entry should have required keys
    for fid, info in fields.items():
        assert isinstance(fid, int)
        assert "std_field" in info
        assert "std_field_id" in info
        assert "airport_count" in info
        assert info["airport_count"] > 0


def test_resolve_field_by_id(tool_context):
    """Resolve field by numeric ID string."""
    fields = _aip_collect_std_fields(tool_context.model)
    if not fields:
        return  # No AIP data in test DB

    first_id = next(iter(fields))
    result = _aip_resolve_field(str(first_id), fields)
    assert result is not None
    assert result["std_field_id"] == first_id


def test_resolve_field_by_name(tool_context):
    """Resolve field by name (case-insensitive substring)."""
    fields = _aip_collect_std_fields(tool_context.model)
    if not fields:
        return

    first_info = next(iter(fields.values()))
    name = first_info["std_field"]

    # Exact name
    result = _aip_resolve_field(name, fields)
    assert result is not None

    # Lowercase partial
    partial = name[:5].lower()
    result = _aip_resolve_field(partial, fields)
    assert result is not None


def test_resolve_field_unknown():
    """Unknown field returns None."""
    result = _aip_resolve_field("nonexistent_field_xyz", {})
    assert result is None


# ---------------------------------------------------------------------------
# list_aip_fields tool
# ---------------------------------------------------------------------------

def test_list_aip_fields(tool_context):
    """list_aip_fields returns field list with counts."""
    result = list_aip_fields(tool_context)
    assert "fields" in result
    assert "total_fields" in result
    assert "total_airports_with_aip_data" in result
    assert result["total_fields"] == len(result["fields"])
    assert result["total_fields"] > 0

    # Fields should be sorted by std_field_id
    ids = [f["std_field_id"] for f in result["fields"]]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# query_aip_fields tool
# ---------------------------------------------------------------------------

def test_query_aip_fields_unknown_field(tool_context):
    """Querying an unknown field returns found=False with helpful hint."""
    result = query_aip_fields(tool_context, field="nonexistent_xyz")
    assert result["found"] is False
    assert "error" in result
    assert "hint" in result


def test_query_aip_fields_by_country(tool_context):
    """Query a known field filtered by country."""
    # First discover a field that has data
    fields = list_aip_fields(tool_context)
    if not fields["fields"]:
        return

    field_name = fields["fields"][0]["std_field"]
    # Find a country that has airports
    airports = tool_context.model.airports.with_aip_data()
    if airports.count() == 0:
        return

    first_airport = airports.first()
    country = first_airport.iso_country

    result = query_aip_fields(tool_context, field=field_name, country=country)
    assert result["found"] is True
    assert "airports" in result
    assert "staleness" in result
    # All results should be from the requested country
    for airport in result["airports"]:
        assert airport["country"] == country


def test_query_aip_fields_by_icao_codes(tool_context):
    """Query by explicit ICAO codes."""
    fields = list_aip_fields(tool_context)
    if not fields["fields"]:
        return

    field_name = fields["fields"][0]["std_field"]
    airports = tool_context.model.airports.with_aip_data()
    if airports.count() < 2:
        return

    # Pick two airports
    icaos = [a.ident for a in airports.take(2)]
    result = query_aip_fields(tool_context, field=field_name, icao_codes=icaos)
    assert result["found"] is True
    assert len(result["airports"]) <= 2
    for airport in result["airports"]:
        assert airport["icao"] in icaos


def test_query_aip_fields_by_numeric_id(tool_context):
    """Query using numeric field ID."""
    fields = list_aip_fields(tool_context)
    if not fields["fields"]:
        return

    field_id = str(fields["fields"][0]["std_field_id"])
    result = query_aip_fields(tool_context, field=field_id)
    assert result["found"] is True
    assert result["field"]["std_field_id"] == int(field_id)


def test_query_aip_fields_max_results(tool_context):
    """max_results limits the response."""
    fields = list_aip_fields(tool_context)
    if not fields["fields"]:
        return

    field_name = fields["fields"][0]["std_field"]
    result = query_aip_fields(tool_context, field=field_name, max_results=3)
    assert result["found"] is True
    assert result["returned"] <= 3


def test_query_aip_fields_staleness_info(tool_context):
    """Staleness info includes AIRAC dates for result countries."""
    fields = list_aip_fields(tool_context)
    if not fields["fields"]:
        return

    field_name = fields["fields"][0]["std_field"]
    result = query_aip_fields(tool_context, field=field_name, max_results=5)
    assert "staleness" in result
    if result["airports"]:
        # Should have AIRAC dates if storage is available
        assert "country_airac_dates" in result["staleness"]


def test_query_aip_fields_changed_since(tool_context):
    """changed_since parameter filters by change date."""
    fields = list_aip_fields(tool_context)
    if not fields["fields"]:
        return

    field_name = fields["fields"][0]["std_field"]
    # Use a very old date to potentially get changes
    result = query_aip_fields(
        tool_context, field=field_name, changed_since="2020-01-01"
    )
    assert result["found"] is True
    assert "staleness" in result
    assert result["staleness"].get("changes_queried_since") == "2020-01-01"
    # Changes may or may not exist depending on test data
    if result["airports"]:
        for airport in result["airports"]:
            assert "changed_at" in airport


# ---------------------------------------------------------------------------
# MCP server wrappers
# ---------------------------------------------------------------------------

def _call_tool_fn(tool, **kwargs):
    return tool.fn(**kwargs)


def test_server_list_aip_fields(server_module):
    """MCP list_aip_fields wrapper works."""
    result = _call_tool_fn(server_module.list_aip_fields)
    assert "fields" in result
    assert result["total_fields"] > 0


def test_server_query_aip_fields(server_module):
    """MCP query_aip_fields wrapper works."""
    # First get a valid field name
    fields_result = _call_tool_fn(server_module.list_aip_fields)
    if not fields_result["fields"]:
        return

    field_name = fields_result["fields"][0]["std_field"]
    result = _call_tool_fn(
        server_module.query_aip_fields,
        field=field_name,
        max_results=5,
    )
    assert result["found"] is True
    assert "airports" in result
