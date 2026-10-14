from typing import Dict, List, Optional, Union

from pydantic import BaseModel


class CreateGameRequest(BaseModel):
    house_rules: str = ""


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
    game_over: bool = False
    pending_suit_player: Optional[str] = None
    players: Dict[str, PlayerModel]


class GameEvent(BaseModel):
    """One thing that happened while the graph ran (a move, a draw, a suit declaration...)."""
    type: str                                  # deal | play | draw | declare
    player: Optional[str] = None
    text: str
    state: GameStateSummary                    # the public game state right after this event
    card: Optional[CardModel] = None
    declared_suit: Optional[str] = None
    drawn_cards: List[CardModel] = []
    played: Optional[CardModel] = None
    awaiting_suit: bool = False
    banter: Optional[str] = None


class MoveResponse(BaseModel):
    events: List[GameEvent]
    state: GameStateSummary
