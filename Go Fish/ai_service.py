import os
from pydantic import BaseModel, Field
from openai import OpenAI
from pathlib import Path
from typing import Optional

SYSTEM_TEMPLATE = Path("prompts/system_prompt.txt").read_text(encoding="utf-8")
USER_TEMPLATE = Path("prompts/user_prompt.txt").read_text(encoding="utf-8")

class AIMoveDecision(BaseModel):
    use_draw_pile: bool = Field(description="True if the AI has no playable cards and must draw from the pile. False if playing from hand.")
    chosen_index: int = Field(description="The 0-based index of the card to play from the hand. Ignored if use_draw_pile is True.")
    declared_suit: Optional[str] = Field(None, description="Must be provided ('Hearts', 'Diamonds', 'Clubs', or 'Spades') ONLY if playing an 8.")
    roleplay_comment: Optional[str] = Field(None, description="A witty, slightly competitive banter comment regarding the move.")

class AIService:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    async def get_ai_move(self, ai_hand: list, top_card: dict, active_suit: str, house_rules: str = ""):
        system_prompt = SYSTEM_TEMPLATE.format(house_rules=house_rules)
        user_prompt = USER_TEMPLATE.format(
            ai_hand=ai_hand, 
            top_card=top_card,
            active_suit=active_suit)

        response = self.client.responses.parse(
            model="gpt-4o",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            text_format=AIMoveDecision,
            max_output_tokens=300,
            temperature=0.7,)
        
        return response.output_parsed