import random
from typing import List, Tuple, Dict, Optional

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

    def initialize_game(self):
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

        initial_card = self.draw_pile.top() # Initial card of the discard pile
        while initial_card == '8':  # Ensure the top card is not an '8'
            self.draw_pile.insert(0, initial_card)
            random.shuffle(self.draw_pile)
            initial_card = self.draw_pile.top()

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
    
    def advance_turn(self):
        self.current_turn_index = (self.current_turn_index +1) % len(self.player_order)

    def add_player(self, player_name: str, player_type: str = "human"):
        self.players[player_name] = Player(player_name, player_type=player_type)
        self.player_order.append(player_name)
    
    # def get_next_player(self, current_player: str) -> str:
    #     idx = list(self.players.keys()).index(current_player)
    #     next_idx = (idx + 1) % len(self.players)
    #     return list(self.players.keys())[next_idx]

    def play_card(self, player_name: str, card_index: int, declared_suit: Optional[str] = None):
        if player_name != self.current_player_name:
            raise ValueError("It's not this player's turn.")
        player = self.players[player_name]

        if card_index < 0 or card_index >= len(player.hand):
            raise IndexError("Card index out of range.")
        
        card_to_play = player.hand[card_index]

        if not self.is_playable(card_to_play):
            raise ValueError(f"Cannot play {card_to_play} on top of {self.top_card} (Active suit: {self.active_suit})")
        player.hand.pop(card_index)
        self.discard_pile.append(card_to_play)

        if card_to_play.rank == '8':
            if not declared_suit or declared_suit not in ['Hearts', 'Diamonds', 'Clubs', 'Spades']:
                raise ValueError("Must declare a valid suit (Hearts, Diamonds, Clubs, Spades) when playing an 8.")
            self.declared_suit = declared_suit
            
        # if the player has no cards left, he is the winner
        if len(player.hand) == 0:
            self.winner = player_name
            return

        self.advance_turn()

    def draw_until_playable(self, player_name: str) -> List[dict]:
        if player_name != self.current_player_name:
            raise ValueError("It's not this player's turn.")
        if not self.draw_pile:
            raise ValueError("Draw pile is empty. Cannot draw a card.")
        
        player = self.players[player_name]
        drawn_cards_log = []

        while True:
            if not self.draw_pile:
            # If draw pile is empty, recycle discard pile except top card
                if len(self.discard_pile) > 1:
                    top = self.discard_pile.pop()
                    self.draw_pile = self.discard_pile
                    random.shuffle(self.draw_pile)
                    self.discard_pile = [top]
                else:
                # Absolutely no cards left to draw, skip turn
                    self.advance_turn()
                    return drawn_cards_log

            drawn_card = self.draw_pile.pop()
            drawn_cards_log.append(drawn_card.to_dict())

            if self.is_playable(drawn_card):
                self.discard_pile.append(drawn_card)
                if drawn_card.rank == '8':
                    # If the drawn card is an '8', randomly declare a suit
                    self.declared_suit = random.choice(['Hearts', 'Diamonds', 'Clubs', 'Spades'])
                self.advance_turn()
                break
            else:
                player.add_card(drawn_card)
        
        return drawn_cards_log