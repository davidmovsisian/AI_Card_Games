import os
import asyncio
from pydantic import BaseModel, Field
from openai import OpenAI
from pathlib import Path
from typing import Optional

PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8")
USER_TEMPLATE = (PROMPTS_DIR / "user_prompt.txt").read_text(encoding="utf-8")
MODEL_NAME = os.environ.get("CRAZY8_MODEL", "gpt-4o")

class AIMoveDecision(BaseModel):
    chosen_index: int = Field(description="The 0-based index of the card to play from the hand. MUST be one of the legal indices provided.")
    declared_suit: Optional[str] = Field(None, description="Must be provided ('Hearts', 'Diamonds', 'Clubs', or 'Spades') ONLY if playing an 8.")
    roleplay_comment: Optional[str] = Field(None, description="A witty, slightly competitive banter comment regarding the move.")

class AIService:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    async def choose_move(self, 
        ai_hand: list, 
        legal_indices: list, 
        top_card: dict, 
        active_suit: str, 
        house_rules: str = "") -> AIMoveDecision | None:

        system_prompt = SYSTEM_TEMPLATE
        user_prompt = USER_TEMPLATE.format(
            ai_hand=ai_hand, 
            top_card=top_card,
            active_suit=active_suit,
            legal_indices=legal_indices,
            house_rules = house_rules)

        # run AI call in separate thread 
        response = await asyncio.to_thread(
            self.client.responses.parse,
                model=MODEL_NAME,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                text_format=AIMoveDecision,
                max_output_tokens=100,
                temperature=0.7,
        )
        
        return response.output_parsed
    
# """LLM move selection for AI players, built with LangChain.

# The engine decides what is legal; the LLM only picks one of the legal card indices
# (and a suit when it chooses an 8), plus an optional bit of banter.
# """
# import os
# from pathlib import Path
# from typing import List, Optional

# from langchain_core.prompts import ChatPromptTemplate
# from langchain_openai import ChatOpenAI
# from langchain_ollama import ChatOllama
# from pydantic import BaseModel, Field

# PROMPTS_DIR = Path(__file__).parent / "prompts"
# SYSTEM_TEMPLATE = (PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8")
# USER_TEMPLATE = (PROMPTS_DIR / "user_prompt.txt").read_text(encoding="utf-8")

# MODEL_NAME = os.environ.get("CRAZY8_MODEL", "gpt-4o")


# class AIMoveDecision(BaseModel):
#     chosen_index: int = Field(description="The 0-based index of the card to play. MUST be one of the legal indices provided.")
#     declared_suit: Optional[str] = Field(None, description="Must be provided ('Hearts', 'Diamonds', 'Clubs', or 'Spades') ONLY if playing an 8.")
#     roleplay_comment: Optional[str] = Field(None, description="A witty, slightly competitive banter comment regarding the move.")


# _chain = None


# def _get_chain():
#     """Build the prompt | model chain lazily, so importing this module never needs an API key."""
#     global _chain
#     if _chain is None:
#         prompt = ChatPromptTemplate.from_messages([
#             ("system", SYSTEM_TEMPLATE),
#             ("human", USER_TEMPLATE),
#         ])
#         llm = ChatOpenAI(model=MODEL_NAME, temperature=0.7, max_tokens=100)
#         _chain = prompt | llm.with_structured_output(AIMoveDecision)
#     return _chain


# async def choose_move(
#     ai_hand: List[dict],
#     legal_indices: List[int],
#     top_card: dict,
#     active_suit: str,
#     house_rules: str = "",
# ) -> Optional[AIMoveDecision]:
#     """Ask the LLM for a move. Callers must validate the result against `legal_indices`."""
#     return await _get_chain().ainvoke({
#         "house_rules": house_rules,
#         "ai_hand": ai_hand,
#         "legal_indices": legal_indices,
#         "top_card": top_card,
#         "active_suit": active_suit,
#     })

