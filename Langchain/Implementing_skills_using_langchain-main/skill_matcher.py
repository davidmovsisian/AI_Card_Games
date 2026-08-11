"""
Skill Matcher — mirrors how Claude decides which skill (if any) to activate.

Claude's skill-triggering logic (replicated with Gemini):
  Step 1: Build a prompt with user query + all skill name+description pairs
  Step 2: Ask the LLM: "Does this query require a skill? Which one?"
  Step 3: If a skill is selected → load its full SKILL.md into context
  Step 4: Re-invoke LLM with full skill instructions + original query
  Step 5: LLM follows the skill's workflow to produce the response

Key insight from the skill-creator docs:
  "Skills appear in Claude's available_skills list with their name + description,
   and Claude decides whether to consult a skill based on that description."
   "Claude only consults skills for tasks it can't easily handle on its own —
    complex, multi-step, or specialized queries reliably trigger skills."
"""

import json
import re
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from skill_registry import SkillMetadata, get_registry_summary


SKILL_SELECTION_SYSTEM = """You are a skill-routing assistant. You have access to a registry of skills.
Your job is to analyze the user's request and decide:
1. Does this request require a specialized skill from the registry?
2. If yes, which skill is the best match?

Skills are only triggered for complex, multi-step, or specialized tasks.
Simple one-step queries (like "what is Python?") do NOT need a skill.

You MUST respond with valid JSON only — no markdown fences, no explanation:
{{
  "needs_skill": true or false,
  "skill_name": "exact-skill-name-from-registry or null",
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation"
}}"""


def select_skill(
    user_query: str,
    registry: dict[str, SkillMetadata],
    llm: ChatGoogleGenerativeAI,
) -> tuple[Optional[str], float, str]:
    """
    Use Gemini to decide which skill (if any) to activate for a given query.
    Returns: (skill_name_or_None, confidence, reasoning)
    """
    if not registry:
        return None, 0.0, "No skills available"

    skills_block = get_registry_summary(registry)

    prompt = f"""{skills_block}

User request: {user_query}

Analyze the request and select the appropriate skill, or indicate no skill is needed."""

    messages = [
        SystemMessage(content=SKILL_SELECTION_SYSTEM),
        HumanMessage(content=prompt),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        parsed = json.loads(raw)
        needs_skill = parsed.get("needs_skill", False)
        skill_name = parsed.get("skill_name") if needs_skill else None
        confidence = float(parsed.get("confidence", 0.0))
        reasoning = parsed.get("reasoning", "")

        # Validate skill exists in registry
        if skill_name and skill_name not in registry:
            # Try fuzzy match
            for reg_name in registry:
                if skill_name.lower() in reg_name.lower() or reg_name.lower() in skill_name.lower():
                    skill_name = reg_name
                    break
            else:
                skill_name = None

        return skill_name, confidence, reasoning

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # Fallback: keyword matching
        for skill_name, meta in registry.items():
            keywords = meta.description.lower().split()
            query_lower = user_query.lower()
            matches = sum(1 for kw in keywords if len(kw) > 4 and kw in query_lower)
            if matches >= 2:
                return skill_name, 0.5, f"Keyword fallback match ({matches} keywords)"

        return None, 0.0, f"JSON parse error: {e}"
