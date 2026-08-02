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
        self.books: List[List[Card]] = []  

    def check_for_books(self):
        rank_count = {}
        for card in self.hand:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        for rank, count in rank_count.items():
            if count == 4:
                book = [card for card in self.hand if card.rank == rank]
                self.books.append(book)
                self.hand = [card for card in self.hand if card.rank != rank]
                

    def add_card(self, card: Card):
        self.hand.append(card)

class GameEngine:
    def __init__(self, house_rules: str):
        self.players: Dict[str, Player] = {}
        self.inactive_players: List[Player] = []  # Track players who have been removed
        self.player_order: List[str] = []
        self.house_rules = house_rules
        self.current_turn_index = 0
        self.draw_pile: List[Card] = []
        self.winner: Optional[str] = None

    def initialize_game(self):
        # create deck of cards
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'K', 'Q', 'A']
        deck = [Card(suit, rank) for suit in suits for rank in ranks]

        random.shuffle(deck)

        # deal 7 cards to each player if number of players is 2 or 3, else deal 5 cards
        num_cards_to_deal = 7 if len(self.players) == 2 or len(self.players) == 3 else 5
        for _ in range(num_cards_to_deal):
            for player in self.players.values():
                player.add_card(deck.pop())
        
        self.draw_pile = deck  # Remaining cards become the draw pile

        for player in self.players.values():
            player.check_for_books()
    
    @property
    def current_player_name(self) -> str:
        return self.player_order[self.current_turn_index]
    
    @property
    def game_ended(self) -> bool:
        return True if len(self.players) == 0 else False
    
    def advance_turn(self):
        self.current_turn_index = (self.current_turn_index +1) % len(self.player_order)

    def add_player(self, player_name: str, player_type: str = "human"):
        self.players[player_name] = Player(player_name, player_type=player_type)
        self.player_order.append(player_name)
    
    def draw_from_player(self, player_name: str, selected_rank: str, target_player_name: str) -> {str, list[Card]}:
        if player_name != self.current_player_name:
            raise ValueError("It's not this player's turn.")
        player = self.players[player_name]
        
        if target_player_name not in self.player_order:
            raise ValueError(f"Target player {target_player_name} does not exist.")
        target_player = self.players[target_player_name]
        
        # get all card of the selected rank from the target player's hand
        transfered_cards = [card for card in target_player.hand if card.rank == selected_rank]

        if not transfered_cards:
            return {selected_rank, []}  # No cards of the selected rank in target player's hand, player must draw from the pile
        else:
            # add transfered_cards to players and call check_for_books
            for card in transfered_cards:
                player.add_card(card)
                target_player.hand.remove(card)

            player.check_for_books()

        return {selected_rank, transfered_cards}
    
    def draw_from_pile(self, player_name: str, selected_rank: str) -> Optional[Card]:
        if player_name != self.current_player_name:
            raise ValueError("It's not this player's turn.")
        player = self.players[player_name]
        
        if not self.draw_pile:
            self.advance_turn()
            if not player.hand:
                self.inactive_players.append(player)
                self.player_order.remove(player_name)
                self.players.pop(player_name)
            return None  # No card draw
        
        drawn_card = self.draw_pile.pop()
        player.add_card(drawn_card)
        
        if drawn_card.rank == selected_rank:
            player.check_for_books()
        else:
            self.advance_turn()
            drawn_card = None  # No card draw
            
        return drawn_card
    

    def calculate_winner(self) -> Optional[str]:
        max_books = -1
        for player in self.inactive_players:
            if len(player.books) > max_books:
                max_books = len(player.books)
                self.winner = player.name
        return self.winner