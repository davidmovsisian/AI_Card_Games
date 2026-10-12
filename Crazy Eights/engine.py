import random
from typing import List, Dict, Optional

class Card:
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank

    def __repr__(self):
        return f"{self.rank} of {self.suit}"

    def to_dict(self):
        return {"suit": self.suit, "rank": self.rank}

class Player:
    def __init__(self, name: str, player_type: str = "human"):
        self.name = name
        self.player_type = player_type
        self.hand: List[Card] = []

    def add_card(self, card: Card):
        self.hand.append(card)

class GameEngine:
    def __init__(self, house_rules: str):
        self.players: Dict[str, Player] = {}
        self.player_order: List[str] = []
        self.house_rules = house_rules
        self.current_turn_index = 0
        self.draw_pile: List[Card] = []
        self.discard_pile: List[Card] = []
        self.declared_suit: Optional[str] = None
        self.winner: Optional[str] = None
        self.started: bool = False
        self.pending_suit_player: Optional[str] = None  # human who drew an 8 and must declare a suit

    def initialize_game(self):
        if self.started:
            raise ValueError("Game already started.")

        self.started = True
        # create deck of cards
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'K', 'Q', 'A']
        deck = [Card(suit, rank) for suit in suits for rank in ranks]

        random.shuffle(deck)

        # deal 7 cards to each player if number of players is 2, else deal 8 cards
        num_cards_to_deal = 7 if len(self.players) == 2 else 8
        for _ in range(num_cards_to_deal):
            for player in self.players.values():
                player.add_card(deck.pop())
        
        self.draw_pile = deck  # Remaining cards become the draw pile

        # Initial card of the discard pile
        initial_card = self.draw_pile.pop() 

        # Ensure the initial card is not '8'.
        while initial_card.rank == '8':  
            self.draw_pile.insert(0, initial_card)
            random.shuffle(self.draw_pile)
            initial_card = self.draw_pile.pop()

        self.discard_pile.append(initial_card)
        self.declared_suit = None
    
    @property
    def current_player_name(self) -> str:
        return self.player_order[self.current_turn_index]

    @property
    def top_card(self) -> Card:
        return self.discard_pile[-1] if self.discard_pile else None
    
    @property
    def active_suit(self) -> str:
        return self.declared_suit if self.declared_suit else self.top_card.suit

    
    def is_playable(self, card: Card) -> bool:
        if card.rank == '8':
            return True
        return card.suit == self.active_suit or card.rank == self.top_card.rank
    
    def legal_moves(self, player_name: str) -> List[int]:
        player = self.players[player_name]
        return [i for i, c in enumerate(player.hand) if self.is_playable(c)]

    @staticmethod
    def best_suit(cards: List[Card]) -> str:
        """Most common suit among non-8 cards (ties/empty -> random suit)."""
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        counts = {s:0 for s in suits}

        for c in cards:
            if c.rank != '8':
                counts[c.suit] += 1
        top = max(counts.values())
        return random.choice([s for s in suits if counts[s] == top])

    # if all cards are drawn from draw pile => need to return cards from discard pile back to the draw pile
    def _recycle_discard_pile(self) -> bool:
        """Shuffle all but the top discard back into the draw pile. Returns True if cards were added."""
        if len(self.discard_pile) <=1:
            return False
        
        top = self.discard_pile.pop()
        self.draw_pile = self.discard_pile
        random.shuffle(self.draw_pile)
        self.discard_pile = [top]
        return True

    def add_player(self, player_name: str, player_type: str = "human"):
            self.players[player_name] = Player(player_name, player_type=player_type)
            self.player_order.append(player_name)
            
    def advance_turn(self):
            self.current_turn_index = (self.current_turn_index +1) % len(self.player_order)

    def play_card(self, player_name: str, card_index: int, declared_suit: Optional[str] = None):
        if self.winner:
            raise ValueError("the game is already over")
        if self.pending_suit_player:
            raise ValueError("A suit must be declared for the drawn 8 first.")
        if player_name != self.current_player_name:
            raise ValueError("It's not this player's turn.")
        
        player = self.players[player_name]

        if card_index < 0 or card_index >= len(player.hand):
            raise IndexError("Card index out of range.")
        
        card_to_play = player.hand[card_index]

        if not self.is_playable(card_to_play):
            raise ValueError(f"Cannot play {card_to_play} on top of {self.top_card} (Active suit: {self.active_suit})")
        if card_to_play.rank == '8':
            if not declared_suit or declared_suit not in ['Hearts', 'Diamonds', 'Clubs', 'Spades']:
                raise ValueError("Must declare a valid suit (Hearts, Diamonds, Clubs, Spades) when playing an 8.")
            self.declared_suit = declared_suit

        player.hand.pop(card_index)
        self.discard_pile.append(card_to_play)

        if card_to_play.rank != '8':
            self.declared_suit = None  # Reset declared suit if not an 8
            
        # if the player has no cards left, he is the winner
        if len(player.hand) == 0:
            self.winner = player_name
            return

        self.advance_turn()

    def draw_until_playable(self, player_name: str, auto_declare: bool = False) -> List[dict]:
        """Draw until a playable card appears and play it.
        
        If that card is an 8: with auto_declare=True (AI players) the suit is chosen
        automatically; otherwise the turn is left pending until declare_suit() is called.
        """
        if self.winner:
            raise ValueError("The game is already over.")
        if self.pending_suit_player:
            raise ValueError("A suit must be declared for the drawn 8 first.")
        if player_name != self.current_player_name:
            raise ValueError("It's not this player's turn.")
        
        player = self.players[player_name]
        if self.legal_moves(player_name):
            raise ValueError("You have a playable card; you may only draw when you have none.")
        
        drawn_cards_log = []

        while True:
            if not self.draw_pile and not self._recycle_discard_pile():
                self.advance_turn()
                return drawn_cards_log

            drawn_card = self.draw_pile.pop()
            drawn_cards_log.append(drawn_card.to_dict())

            if self.is_playable(drawn_card):
                self.discard_pile.append(drawn_card)
                if drawn_card.rank == '8':
                    if auto_declare:
                        self.declared_suit = self.best_suit(player.hand)
                    # Human draw '8' => need to declare the suit. turn is not advanced
                    else:
                        self.declared_suit = None
                        self.pending_suit_player = player_name
                        break
                else:
                    self.declared_suit = None  # Reset declared suit if not an 8
                    
                self.advance_turn()
                break
            else:
                player.add_card(drawn_card)
        
        return drawn_cards_log

    def declare_suit(self, player_name: str, suit: str):
        """Finish a human's turn after they drew a playable 8."""
        if player_name != self.pending_suit_player:
            raise ValueError("No suit declaration is pending for this player.")
        if suit not in ['Hearts', 'Diamonds', 'Clubs', 'Spades']:
            raise ValueError("Must declare a valid suit (Hearts, Diamonds, Clubs, Spades).")

        self.declared_suit = suit
        self.pending_suit_player = None
        self.advance_turn()