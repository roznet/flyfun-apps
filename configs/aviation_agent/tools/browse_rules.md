Browse/list aviation rules for a country with pagination.

**Parameters:**
- country_code: ISO-2 country code (e.g., FR, GB, DE)
- tags: Optional array of topic tags to filter (e.g., ["flight_plan", "transponder"])
- offset: Starting index for pagination (default: 0)
- limit: Maximum rules to return (default: 10, max: 50)

**Use this tool when:**
- User wants to see ALL rules in a category
- "List all flight plan rules for France"
- "Show me transponder regulations in Germany"
- "What rules do you have about airspace in the UK?"
- User asks to "show more" after seeing initial results

**Do NOT use for:**
- Answering a specific question → use answer_rules_question
- Comparing rules between countries → use compare_rules_between_countries
