"""
Baseline test cases for Issue #8: Behavior to Ensure Work

This module defines test cases covering the requirements from issue #8:
- Airport discovery (midpoints, distance-based, border proximity)
- Smart filtering (GA-friendly, amenities, IFR approaches)
- Regulatory intelligence (country-specific rules, cross-country comparison)
"""

# Geographic Search Test Cases
GEOGRAPHIC_SEARCH_CASES = [
    {
        "id": "geo_01",
        "category": "geographic_search",
        "inputs": {"query": "Find airports within 50nm of LFPB"},
        "expected": {
            "tool": "airport_search",
            "filters": {"max_distance_nm": 50, "reference_icao": "LFPB"},
            "should_include_icaos": ["LFPB", "LFPO"],  # Paris airports
        },
        "description": "Basic distance search from ICAO code"
    },
    {
        "id": "geo_02",
        "category": "geographic_search",
        "inputs": {"query": "Show me airports near the midpoint between EGLL and LFPB"},
        "expected": {
            "tool": "route_search",
            "filters": {"midpoint": True},
            "should_mention": ["midpoint", "between", "EGLL", "LFPB"],
        },
        "description": "Midpoint calculation between two airports"
    },
    {
        "id": "geo_03",
        "category": "geographic_search",
        "inputs": {"query": "Find airports near the France-Switzerland border"},
        "expected": {
            "tool": "border_crossing_search",
            "filters": {"countries": ["FR", "CH"]},
            "should_mention": ["border", "France", "Switzerland"],
        },
        "description": "Border proximity search"
    },
    {
        "id": "geo_04",
        "category": "geographic_search",
        "inputs": {"query": "What airports are between EGLL and LFPB with IFR approaches"},
        "expected": {
            "tool": "route_search",
            "filters": {"has_ifr": True, "origin": "EGLL", "destination": "LFPB"},
            "should_mention": ["IFR", "instrument"],
        },
        "description": "Route search with approach type filter"
    },
]

# Smart Filtering Test Cases
SMART_FILTERING_CASES = [
    {
        "id": "filter_01",
        "category": "smart_filtering",
        "inputs": {"query": "Find small GA-friendly airports near Paris"},
        "expected": {
            "tool": "airport_search",
            "filters": {"general_aviation": True, "reference_city": "Paris"},
            "should_not_include": ["LFPG", "LFPO"],  # Major commercial airports
        },
        "description": "General aviation filtering to exclude major hubs"
    },
    {
        "id": "filter_02",
        "category": "smart_filtering",
        "inputs": {"query": "Airports with restaurants near LFPB"},
        "expected": {
            "tool": "airport_search",
            "filters": {"amenities": ["restaurant"], "reference_icao": "LFPB"},
            "should_mention": ["restaurant", "dining"],
        },
        "description": "Amenity filtering for restaurants"
    },
    {
        "id": "filter_03",
        "category": "smart_filtering",
        "inputs": {"query": "Find airports between EGLL and LFMD with hotels and maintenance"},
        "expected": {
            "tool": "route_search",
            "filters": {
                "amenities": ["hotel", "maintenance"],
                "origin": "EGLL",
                "destination": "LFMD"
            },
            "should_mention": ["hotel", "accommodation", "maintenance"],
        },
        "description": "Multiple amenity filters on route search"
    },
    {
        "id": "filter_04",
        "category": "smart_filtering",
        "inputs": {"query": "Show airports with low landing fees and grass runways"},
        "expected": {
            "tool": "airport_search",
            "filters": {"runway_surface": "grass", "low_fees": True},
            "should_mention": ["landing fees", "grass", "runway"],
        },
        "description": "Landing fee and runway surface filtering"
    },
]

# Regulatory Intelligence Test Cases
REGULATORY_CASES = [
    {
        "id": "reg_01",
        "category": "regulatory",
        "inputs": {"query": "What are the rules for uncontrolled airfields in France?"},
        "expected": {
            "tool": "regulatory_search",  # May need new tool
            "filters": {"country": "FR", "topic": "uncontrolled_airfield"},
            "should_mention": ["France", "uncontrolled", "VFR", "regulation"],
        },
        "description": "Country-specific regulatory question"
    },
    {
        "id": "reg_02",
        "category": "regulatory",
        "inputs": {"query": "What are airspace penetration rules in the UK vs Germany?"},
        "expected": {
            "tool": "regulatory_search",
            "filters": {"countries": ["GB", "DE"], "topic": "airspace_penetration", "compare": True},
            "should_mention": ["UK", "Germany", "airspace", "compare", "differences"],
        },
        "description": "Cross-country regulatory comparison"
    },
    {
        "id": "reg_03",
        "category": "regulatory",
        "inputs": {"query": "Tell me about GAR submission requirements in the UK"},
        "expected": {
            "tool": "regulatory_search",
            "filters": {"country": "GB", "topic": "gar"},
            "should_mention": ["GAR", "General Aviation Report", "2 hours", "notice"],
        },
        "description": "Specific regulatory requirement (GAR)"
    },
    {
        "id": "reg_04",
        "category": "regulatory",
        "inputs": {"query": "What customs procedures apply at LFMD?"},
        "expected": {
            "tool": "airport_search",
            "filters": {"icao": "LFMD", "customs_info": True},
            "should_mention": ["customs", "LFMD", "Schengen"],
        },
        "description": "Airport-specific customs information"
    },
    {
        "id": "reg_05",
        "category": "regulatory",
        "inputs": {"query": "Compare PPR requirements across France, UK, and Spain"},
        "expected": {
            "tool": "regulatory_search",
            "filters": {"countries": ["FR", "GB", "ES"], "topic": "ppr", "compare": True},
            "should_mention": ["PPR", "prior permission", "France", "UK", "Spain"],
        },
        "description": "Multi-country PPR comparison"
    },
]

# Combined/Complex Test Cases
COMPLEX_CASES = [
    {
        "id": "complex_01",
        "category": "complex",
        "inputs": {
            "query": "Find GA airports between EGLL and LFMD with IFR, restaurants, and explain customs requirements"
        },
        "expected": {
            "tool": "route_search",
            "filters": {
                "general_aviation": True,
                "has_ifr": True,
                "amenities": ["restaurant"],
                "customs_info": True,
                "origin": "EGLL",
                "destination": "LFMD"
            },
            "should_mention": ["GA", "IFR", "restaurant", "customs"],
        },
        "description": "Complex multi-filter query with regulatory info"
    },
    {
        "id": "complex_02",
        "category": "complex",
        "inputs": {
            "query": "What are the best fuel stops between EGLC and LSZH, avoiding major airports?"
        },
        "expected": {
            "tool": "route_search",
            "filters": {
                "general_aviation": True,
                "has_fuel": True,
                "origin": "EGLC",
                "destination": "LSZH"
            },
            "should_mention": ["fuel", "avoid", "major"],
        },
        "description": "Route optimization with exclusions"
    },
]

# Aggregate all test cases
ALL_TEST_CASES = (
    GEOGRAPHIC_SEARCH_CASES +
    SMART_FILTERING_CASES +
    REGULATORY_CASES +
    COMPLEX_CASES
)


def get_test_cases_by_category(category: str):
    """Get test cases filtered by category"""
    return [tc for tc in ALL_TEST_CASES if tc["category"] == category]


def get_test_case_by_id(test_id: str):
    """Get a specific test case by ID"""
    for tc in ALL_TEST_CASES:
        if tc["id"] == test_id:
            return tc
    return None
