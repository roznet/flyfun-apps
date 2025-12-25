Answer a specific question about aviation rules for a country using semantic search.

**Parameters:**
- country_code: ISO-2 country code (e.g., FR, GB, DE)
- question: The user's actual question about aviation rules
- tags: Optional array of topic tags to help filter (e.g., ["flight_plan", "transponder"])

**Use this tool when:**
- User asks a specific question about rules in ONE country
- "How do I file a flight plan in France?"
- "What are the transponder requirements in Germany?"
- "Do I need PPR for airfields in the UK?"

**Do NOT use for:**
- Comparing rules between countries → use compare_rules_between_countries
- Browsing/listing all rules in a category → use browse_rules
