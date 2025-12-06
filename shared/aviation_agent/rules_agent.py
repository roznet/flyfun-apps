#!/usr/bin/env python3
"""
Rules synthesis agent for aviation regulations.

This module synthesizes natural language answers from retrieved rules,
with support for multi-country comparisons and proper citations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


class RulesAgent:
    """
    Synthesizes natural language answers from retrieved rules.
    
    Takes RAG-retrieved rules and generates user-friendly explanations
    with proper citations, multi-country comparisons, and source links.
    """
    
    def __init__(self, llm: Runnable):
        """
        Initialize rules agent.
        
        Args:
            llm: LLM instance for answer synthesis
        """
        self.llm = llm
        self.prompt_template = self._build_prompt_template()
    
    def _build_prompt_template(self) -> ChatPromptTemplate:
        """Build the synthesis prompt template."""
        return ChatPromptTemplate.from_messages([
            ("system", """You are an aviation regulations expert assistant. Your role is to answer the pilot's question using ONLY the provided rules and regulations.

Guidelines:
1. **Answer the specific question** - Focus on what the pilot asked
2. **Cite countries** - Clearly indicate which rule applies to which country
3. **Compare when multiple countries** - If rules differ, highlight the differences
4. **Be concise** - Pilots need clear, actionable information
5. **Don't make up information** - Only use the provided rules
6. **Format clearly** - Use markdown with headers, bullets, and bold text

If the retrieved rules don't answer the question, say: "I don't have specific information about that in the regulations I have access to."

Format your answer in markdown:
- Use **bold** for country names and key terms
- Use bullet points for lists
- Use `code` for airport codes (ICAO)

CRITICAL: Do NOT add any "References", "Sources", or links section. Do NOT include any markdown links like [text](url) or [text](#). The system will automatically add references after your answer. Your answer should end immediately after answering the question."""),
            
            ("human", """Question: {query}

Countries in scope: {countries}

Retrieved Rules:
{rules_context}

Please provide a clear, well-formatted answer to the pilot's question.""")
        ])
    
    def synthesize(
        self,
        query: str,
        retrieved_rules: List[Dict[str, Any]],
        countries: List[str],
        conversation: Optional[List[BaseMessage]] = None
    ) -> Dict[str, Any]:
        """
        Synthesize an answer from retrieved rules.
        
        Args:
            query: User's original question
            retrieved_rules: List of rules from RAG retrieval
            countries: List of countries in scope
            conversation: Optional conversation history for context
            
        Returns:
            Dict with:
                - answer: Synthesized natural language answer
                - sources: List of source links
                - countries: Countries covered
                - rules_used: Rules that were referenced
        """
        if not retrieved_rules:
            return {
                "answer": self._no_rules_response(query, countries),
                "sources": [],
                "countries": countries,
                "rules_used": []
            }
        
        # Format rules context
        rules_context = self._format_rules_context(retrieved_rules)
        
        # Generate answer
        try:
            chain = self.prompt_template | self.llm
            response = chain.invoke({
                "query": query,
                "countries": ", ".join(countries) if countries else "Not specified",
                "rules_context": rules_context
            })
            
            answer = response.content if hasattr(response, 'content') else str(response)

            # Strip any markdown links the LLM added despite instructions
            # Remove [text](url) and [text](#) patterns
            import re
            answer = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', answer)

            # Extract sources from RAG chunks
            sources = self._extract_sources(retrieved_rules)
            logger.info(f"Extracted {len(sources)} sources from RAG: {sources}")

            # Append simple references section from RAG outputs
            if sources:
                answer = answer.strip()
                answer += "\n\n---\n\n### References\n\n"
                answer += "Based on regulations retrieved from knowledge base:\n\n"
                # Group by country - sources is now a dict: {country: [categories]}
                for country in sorted(sources.keys()):
                    categories = sources[country]
                    categories_str = ", ".join(categories)
                    answer += f"- **{country}**: {categories_str}\n"
                logger.info(f"Appended references section to answer. Answer length: {len(answer)}")
            else:
                logger.warning("No sources extracted from RAG, skipping references section")

            # Identify rules used
            rules_used = [
                {
                    "question_id": rule["question_id"],
                    "country": rule["country_code"],
                    "similarity": rule["similarity"]
                }
                for rule in retrieved_rules
            ]

            logger.info(f"Synthesized answer using {len(retrieved_rules)} rules for countries: {countries}")
            logger.info(f"Final answer preview (first 200 chars): {answer[:200]}...")
            logger.info(f"Final answer preview (last 200 chars): ...{answer[-200:]}")

            return {
                "answer": answer,
                "sources": sources,
                "countries": countries,
                "rules_used": rules_used
            }
            
        except Exception as e:
            logger.error(f"Failed to synthesize answer: {e}", exc_info=True)
            return {
                "answer": f"I encountered an error processing the regulations: {str(e)}",
                "sources": [],
                "countries": countries,
                "rules_used": []
            }
    
    def _format_rules_context(self, rules: List[Dict[str, Any]]) -> str:
        """Format rules into context string for the LLM."""
        if not rules:
            return "No rules found."
        
        # Group by country for better organization
        by_country: Dict[str, List[Dict]] = {}
        for rule in rules:
            country = rule.get("country_code", "Unknown")
            if country not in by_country:
                by_country[country] = []
            by_country[country].append(rule)
        
        # Build formatted context
        lines = []
        for country in sorted(by_country.keys()):
            country_rules = by_country[country]
            lines.append(f"\n**{country}:**")
            
            for i, rule in enumerate(country_rules, 1):
                question = rule.get("question_text", "Unknown question")
                answer = rule.get("answer_html", "No answer available")
                similarity = rule.get("similarity", 0)
                
                lines.append(f"\n{i}. **Q:** {question}")
                lines.append(f"   **A:** {answer}")
                lines.append(f"   (Relevance: {similarity:.2f})")
                
                # Add links if available
                links = rule.get("links", [])
                if links:
                    links_str = ", ".join(links[:2])  # Max 2 links per rule
                    lines.append(f"   **Sources:** {links_str}")
        
        return "\n".join(lines)
    
    def _extract_sources(self, rules: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Extract sources grouped by country from RAG-retrieved rules."""
        sources_by_country = {}

        for rule in rules:
            country = rule.get("country_code", "Unknown")
            category = rule.get("category", "Regulation")

            # Group categories by country
            if country not in sources_by_country:
                sources_by_country[country] = []

            # Add category if not already present for this country
            if category not in sources_by_country[country]:
                sources_by_country[country].append(category)

        return sources_by_country
    
    def _no_rules_response(self, query: str, countries: List[str]) -> str:
        """Generate response when no rules are found."""
        if countries:
            countries_str = ", ".join(countries)
            return f"""I don't have specific regulations about "{query}" for {countries_str} in my current database.

This could mean:
- The question might be phrased differently in official regulations
- This specific topic might not be covered in the rules I have
- The country regulations might not be fully indexed yet

**Suggestions:**
- Try rephrasing your question
- Check official aviation authority websites for {countries_str}
- Contact local flight information services"""
        else:
            return f"""I don't have specific regulations about "{query}" in my current database.

**Suggestions:**
- Could you specify which country you're asking about?
- Try rephrasing your question
- Contact local flight information services"""


def create_rules_agent(llm: Runnable) -> RulesAgent:
    """
    Factory function to create a RulesAgent.
    
    Args:
        llm: LLM instance for synthesis
        
    Returns:
        Configured RulesAgent instance
    """
    return RulesAgent(llm)


if __name__ == "__main__":
    # Simple test
    import os
    from langchain_openai import ChatOpenAI
    
    logging.basicConfig(level=logging.INFO)
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    agent = RulesAgent(llm)
    
    # Test with sample retrieved rules
    sample_rules = [
        {
            "question_id": "test-1",
            "question_text": "Is a flight plan required for VFR flights?",
            "country_code": "FR",
            "category": "VFR",
            "answer_html": "No, a flight plan is not required for VFR flights within France, except when crossing international boundaries.",
            "links": ["https://www.sia.aviation-civile.gouv.fr"],
            "similarity": 0.92
        },
        {
            "question_id": "test-1",
            "question_text": "Is a flight plan required for VFR flights?",
            "country_code": "GB",
            "category": "VFR",
            "answer_html": "No flight plan is required for VFR flights within the UK unless departing to another country.",
            "links": ["https://www.caa.co.uk"],
            "similarity": 0.90
        }
    ]
    
    result = agent.synthesize(
        query="Do I need to file a flight plan for VFR?",
        retrieved_rules=sample_rules,
        countries=["FR", "GB"]
    )
    
    print("\n" + "=" * 70)
    print("RULES AGENT TEST")
    print("=" * 70)
    print(f"\nAnswer:\n{result['answer']}")
    print(f"\nSources: {len(result['sources'])}")
    print(f"Rules used: {len(result['rules_used'])}")

