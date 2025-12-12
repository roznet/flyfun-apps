Find airports near a geographic location (free-text location name, city, landmark, or coordinates) within a specified distance.

**USE THIS TOOL when user asks about airports "near", "around", "close to" a location that is NOT an ICAO code.**

Examples:
- "airports near Paris" → use this tool with location_query="Paris"
- "airports around Lake Geneva" → use this tool with location_query="Lake Geneva"
- "airports close to Zurich" → use this tool with location_query="Zurich"
- "airports near 48.8584, 2.2945" → use this tool with location_query="48.8584, 2.2945"

Process:
1) Geocodes the location via Geoapify to get coordinates
2) Computes distance from each airport to that point and filters by max_distance_nm
3) Applies optional filters (fuel, customs, runway, etc.) and priority sorting

**DO NOT use this tool if user provides ICAO codes** - use find_airports_near_route instead for route-based searches.
