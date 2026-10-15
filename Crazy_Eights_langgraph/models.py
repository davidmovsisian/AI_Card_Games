"""API schemas: request bodies and the responses returned to the frontend.

`engine.summarize()` and the graph's events are plain dicts (they live in the LangGraph
checkpoint); these models validate and document them at the HTTP boundary, so the
OpenAPI schema (/docs) and the frontend's JSDoc types in api.js describe the same shapes.
"""
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── requests ──────────────────────────────────────────────────────────────────

class CreateGameRequest(BaseModel):
    house_rules: str = ""


class JoinGameRequest(BaseModel):
    player_name: str
    player_type: Literal["human", "ai"] = "human"


class PlayCardRequest(BaseModel):
    player_name: str
    card_index: int
    declared_suit: Optional[str] = None


# ── responses ─────────────────────────────────────────────────────────────────

class CardModel(BaseModel):
    suit: str
    rank: str


class PlayerModel(BaseModel):
    type: Literal["human", "ai"]
    hand_count: int
    hand: Union[List[CardModel], Literal["HIDDEN"]]      # AI hands are hidden


class GameStateSummary(BaseModel):
    current_player: str
    top_card: CardModel
    active_suit: str
    winner: Optional[str] = None
    game_over: bool = False
    pending_suit_player: Optional[str] = None            # human who must declare a suit after drawing an 8
    players: Dict[str, PlayerModel]


class GameEvent(BaseModel):
    """One thing that happened while the graph ran (a move, a draw, a suit declaration...)."""
    type: Literal["deal", "play", "draw", "declare"]
    player: Optional[str] = None
    text: str
    state: GameStateSummary                              # the public game state right after this event
    card: Optional[CardModel] = None                     # play: the card played
    declared_suit: Optional[str] = None
    drawn_cards: List[CardModel] = Field(default_factory=list)
    played: Optional[CardModel] = None                   # draw: the drawn card that was played
    awaiting_suit: bool = False
    banter: Optional[str] = None


class MoveResponse(BaseModel):
    events: List[GameEvent]
    state: GameStateSummary


class StartGameResponse(MoveResponse):
    status: str


class CreateGameResponse(BaseModel):
    status: str
    game_id: str


class StatusResponse(BaseModel):
    status: str
