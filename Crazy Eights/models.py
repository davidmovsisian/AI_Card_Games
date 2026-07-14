from pydantic import BaseModel
from typing import List, Dict, Optional, Union

class CreateGameRequest(BaseModel):
    house_rules: str

class JoinGameRequest(BaseModel):
    player_name: str
    player_type: str = "human"  # or "ai"

class PlayCardRequest(BaseModel):
    player_name: str
    card_index: int
    declared_suit: Optional[str] = None

class CardModel(BaseModel):
    suit: str
    rank: str

class PlayerModel(BaseModel):
    type: str
    hand_count: int
    hand: Union[str, List[CardModel]]

class GameStateSummary(BaseModel):
    current_player: str
    top_card: CardModel
    active_suit: str
    winner: Optional[str] = None
    players: Dict[str, PlayerModel]