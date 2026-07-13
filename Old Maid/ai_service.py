import os
from pydantic import BaseModel, Field
from openai import OpenAI
from pathlib import Path

SYSTEM_TEMPLATE = Path("prompts/system_prompt.txt").read_text(encoding="utf-8")
USER_TEMPLATE = Path("prompts/user_prompt.txt").read_text(encoding="utf-8")

class AIMoveDecision(BaseModel):
    chosen_index: int = Field(description="The 0-based index of the card to draw from the target player's hand.")
    roleplay_comment: str = Field(description="A witty banter comment reacting to the house rules or the current state of the game.")

class AIService:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    async def get_ai_move(self, ai_hand: list, target_card_count: int, house_rules: str = ""):
        system_prompt = SYSTEM_TEMPLATE.format(house_rules=house_rules)
        user_prompt = USER_TEMPLATE.format(
            ai_hand=ai_hand, 
            target_card_count=target_card_count,
            max_index=target_card_count - 1)

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