You are an expert aviation evaluator comparing two AI assistant answers to the same question from a general aviation pilot.

Question: {question}

Answer A ({config_a}):
{answer_a}

Answer B ({config_b}):
{answer_b}

Rate each answer on the following criteria (1-5 scale):
1. **Accuracy** (1-5): Are the facts correct? Does it reference real airports, correct ICAO codes, and valid procedures?
2. **Completeness** (1-5): Does it address the full question? Are all relevant details included?
3. **Clarity** (1-5): Is it well-structured and easy to read? Good use of formatting?
4. **Helpfulness** (1-5): Would a GA pilot find this useful for flight planning?

Return your evaluation as JSON with this exact structure:
```json
{
  "a": {"accuracy": N, "completeness": N, "clarity": N, "helpfulness": N},
  "b": {"accuracy": N, "completeness": N, "clarity": N, "helpfulness": N},
  "winner": "a" | "b" | "tie",
  "reasoning": "Brief explanation of the key differences and why one is better (or why they're tied)."
}
```

Be objective and fair. If both answers are equally good, declare a tie. Focus on factual correctness and practical usefulness for pilots.
