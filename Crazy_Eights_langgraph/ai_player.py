"""LLM move selection for AI players, built with LangChain.

The engine decides what is legal; the LLM only picks one of the legal card indices
(and a suit when it chooses an 8), plus an optional bit of banter.
"""
import os
from pathlib import Path
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

PROMPTS_DIR = Path(__file__).parent/"prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR/"system_prompt.txt").read_text(encoding="utf-8")
USER_TEMPLATE = (PROMPTS_DIR/"user_prompt.txt").read_text(encoding="utf-8")
MODEL_NAME = os.environ.get("CRAZY8_MODEL", "gpt-4o")

class AIMoveDecision(BaseModel):
    chosen_index: int = Field(description="The 0-based index of the card to play. MUST be one of the legal indices provided.")
    declared_suit: Optional[str] = Field(None, description="Must be provided ('Hearts', 'Diamonds', 'Clubs', or 'Spades') ONLY if playing an 8.")
    roleplay_comment: Optional[str] = Field(None, description="A short, fun comment in the spirit of the house rules. Leave null when the prompt says not to comment.")

_chain = None

def _get_chain():
    """Build the prompt | model chain lazily, so importing this module never needs an API key."""
    global _chain
    if _chain is None:
        prompt = ChatPromptTemplate.from_messages(
        [   ('system', SYSTEM_TEMPLATE),
            ('human', USER_TEMPLATE)
        ]) 
        llm = ChatOpenAI(model=MODEL_NAME, temperature=0.7, max_tokens=100)
        _chain = prompt | llm
    return _chain

def build_prompt_inputs(
        ai_hand: List[dict],
        legal_indices: List[int],
        top_card: dict,
        active_suit: str,
        house_rules: str):
    
    rules = (house_rules or "").strip()
    if rules:
        comment_instruction = ("Write ONE short, fun comment about your move in the spirit of the house rules "
                                "above and return it in `roleplay_comment`.")
    else:
        comment_instruction = ("There are no house rules for this game, so do NOT write any comment: "
                                   "set `roleplay_comment` to null.")

    return {
        "house_rules": rules or "None",
        "comment_instruction": comment_instruction,
        "ai_hand": ai_hand,
        "legal_indices": legal_indices,
        "top_card": top_card,
        "active_suit": active_suit,
    }

async def choose_move(
    ai_hand: List[dict],
    legal_indices: List[int],
    top_card: dict,
    active_suit: str,
    house_rules: str
):
    return await _get_chain().ainvoke(
        build_prompt_inputs(ai_hand, legal_indices, top_card, active_suit, house_rules)
    )

