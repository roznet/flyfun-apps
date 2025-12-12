List airports within a specified distance from a direct route between two locations, with optional airport filters.

**USE THIS TOOL when user asks about airports "between" two locations.**

**IMPORTANT - Pass location names exactly as user provides them, INCLUDING country/region context:**
- Pass ICAO codes as-is (e.g., "LFPO", "EGKB", "EDDM")
- Pass location names WITH COUNTRY if user mentions it - DO NOT strip country context
- The tool will automatically geocode location names and find the nearest airport
- Examples:
  - "between LFPO and Bromley" → from_location="LFPO", to_location="Bromley"
  - "between Paris and Vik in Iceland" → from_location="Paris", to_location="Vik, Iceland"
  - "Vik, Iceland" or "Vik in Iceland" → to_location="Vik, Iceland" (INCLUDE COUNTRY!)
  - "between LFPO and EDDM" → from_location="LFPO", to_location="EDDM"

**Filters:**
When user mentions fuel (e.g., AVGAS, Jet-A), customs/border crossing, runway type (paved/hard), IFR procedures, or country, you MUST include the corresponding filter:
- has_avgas=True for AVGAS
- has_jet_a=True for Jet-A
- point_of_entry=True for customs
- has_hard_runway=True for paved runways
- has_procedures=True for IFR
- country='XX' for specific country

Useful for finding fuel stops, alternates, or customs stops along a route.
