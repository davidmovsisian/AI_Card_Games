import random
from typing import List, Tuple, Dict

class Card:
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.color = "Red" if suit in ["Hearts", "Diamonds"] else "Black"

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

    def remove_pairs(self) -> List[str]:
        from collections import defaultdict
        rank_groups = defaultdict(list)
        for card in self.hand:
            rank_groups[card.rank].append(card)

        new_hand = []
        removed_pairs = []

        for rank, cards in rank_groups.items():
            count = len(cards)
            pairs_count = count // 2
            
            # Track removed pairs for house rules / logs
            for _ in range(pairs_count):
                removed_pairs.append(f"Pair of {rank}s")
                
            # IF there's a remainder (1 or 3 cards originally), ONE card survives
            if count % 2 == 1:
                new_hand.append(cards[-1])

        # Update the engine's state with the clean hand
        self.hand = new_hand

        return removed_pairs
    
class GameEngine:
    def __init__(self, house_rules: str):
        self.players: Dict[str, Player] = {}
        self.house_rules = house_rules
        self.current_turn_index = 0
        self.discarded_pairs: List[str] = []

    def _remove_empty_players_after_turn(self, current_player: str, original_order: List[str]):
        eliminated_players = [name for name, player in self.players.items() if len(player.hand) == 0]
        for player_name in eliminated_players:
            self.players.pop(player_name)

        if not self.players:
            self.current_turn_index = 0
            return

        current_index = original_order.index(current_player)
        next_player = None
        for offset in range(1, len(original_order) + 1):
            candidate = original_order[(current_index + offset) % len(original_order)]
            if candidate in self.players:
                next_player = candidate
                break

        if next_player is None:
            next_player = next(iter(self.players))

        self.current_turn_index = list(self.players.keys()).index(next_player)

    def initialize_game(self):
        # create deck of cards
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'K', 'A']
        deck = [Card(suit, rank) for suit in suits for rank in ranks]

        deck.append(Card('Hearts', 'Q'))  # Adding the Queen of Hearts as a special card
        deck.append(Card('Diamonds', 'Q'))  # Adding the Queen of Diamonds as a special card
        deck.append(Card('Clubs', 'Q'))  # Adding the Queen of Clubs as a special card

        random.shuffle(deck)

        # deal cards to players
        for i, card in enumerate(deck):
            player = list(self.players.values())[i % len(self.players)]
            player.add_card(card)
        
        # remove pairs from hands
        for player in self.players.values():
            removed_pairs = player.remove_pairs()
            self.discarded_pairs.extend(removed_pairs)

    def add_player(self, player_name: str, player_type: str = "human"):
        self.players[player_name] = Player(player_name, player_type=player_type)

    def get_next_player(self, current_player: str) -> str:
        idx = list(self.players.keys()).index(current_player)
        next_idx = (idx + 1) % len(self.players)
        return list(self.players.keys())[next_idx]
    
    def execute_draw(self, current_player: str, target_player: str, card_index: int):
        print(f"Executing draw: {current_player} draws from {target_player} at index {card_index}")
        if card_index < 0 or card_index >= len(self.players[target_player].hand):
            raise IndexError("Card index out of range.")

        original_order = list(self.players.keys())
        
        drawn_card = self.players[target_player].hand.pop(card_index)
        self.players[current_player].hand.append(drawn_card)
        
        # Remove pairs after drawing
        removed_pairs = self.players[current_player].remove_pairs()

        self._remove_empty_players_after_turn(current_player, original_order)

        return {
            "drawn_card_visible_to_drawer": drawn_card.to_dict(),
            "new_pairs_formed": removed_pairs
        }
