Compare aviation rules and regulations between countries (iso-2 codes eg FR,GB,DE) and highlight semantic differences in answers.

This tool uses embedding-based comparison to detect REAL regulatory differences (not just wording differences). It filters out questions where countries say the same thing differently, focusing on actual practical differences for pilots.

**Parameters:**
- countries: Array of ISO-2 country codes to compare (e.g., ["FR", "DE", "GB"])
- tags: Optional array of topic tags to filter (e.g., ["flight_plan", "transponder"])

**Use this tool when:**
- Pilot asks "What's different about flying in France vs Germany?"
- User wants to compare specific topics: "Compare flight plan rules between FR and DE"
- Planning a cross-border flight and need to know key differences
- Comparing multiple countries: "Differences between DE, GB and BE"

**Returns:**
- LLM-synthesized summary of key differences prioritized by importance
- Individual rule differences with semantic difference scores
- Indication of how many questions were analyzed vs filtered
