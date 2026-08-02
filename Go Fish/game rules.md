Go Fish is a simple card game where players collect complete sets (usually four cards of the same rank). The core algorithm is a repeated cycle of asking → receiving or fishing → checking for completed sets → next turn.

Setup
Use a standard 52-card deck (no Jokers).
Shuffle the deck.
Deal:
7 cards each for 2–3 players.
5 cards each for 4–5 players.
Place the remaining cards face down as the draw pile ("the pond").
Each player checks their hand:
If they already have four cards of the same rank (e.g., four Kings), they immediately place that set face up.
Randomly choose the first player.

Main Game Loop

Repeat until the game ends.

Step 1: Current player chooses a rank

The current player selects one rank they already hold.

Example:
Hand:
3♠ 3♥ 7♦ K♣ A♠

Can ask for:
3
7
K
A

Cannot ask for:
5 (because they don't own one)

Step 2: Choose another player

The current player asks one opponent.

Example:

"Do you have any Queens?"

Step 3: Opponent checks their hand
Case A — Opponent has the requested rank

The opponent must give all cards of that rank.

Example:

Current player asks for 8s.

Opponent has:
8♠
8♥
J♣
K♦

Opponent gives both 8s.

Current player adds them to their hand.

Case B — Opponent has none

Opponent says:

"Go Fish!"

The current player draws one card from the draw pile.

Step 4: Check what was drawn

If the drawn card matches the requested rank:

Example:

Asked for Queens.

Draws:
Q♥

The player shows it (in many versions) and continues taking another turn.

Otherwise:

The turn ends.

Step 5: Check for completed books

After receiving cards (either from another player or from the deck), the player checks whether they now have four of a rank.

Example:
9♠
9♥
9♦
9♣

These four cards are removed from the hand and placed face up as one completed book (or set).

Step 6: Determine who plays next

The current player continues their turn if:

the opponent gave them one or more requested cards, or
they drew the requested rank from the deck.

Otherwise, play passes to the next player clockwise.

Empty Hand Rule
If a player has no cards:
    If the draw pile still has cards:
        draw one card.
    Otherwise:
        wait until the game ends.

Game End
The game finishes when:
    every book has been completed (13 total in a standard deck), or
    no cards remain in any player's hand and the draw pile is empty.

Winner
Count the number of books each player has collected.
Example:
| Player | Books |
| ------ | ----: |
| Alice  |     5 |
| Bob    |     3 |
| Carol  |     5 |

Alice and Carol tie for first place.

initialize deck
shuffle deck

Pseudocode:
deal cards

for each player
    remove any completed books

choose starting player

while game not over

    player chooses a rank they hold

    choose an opponent

    if opponent has requested rank

        transfer all matching cards

        remove completed books

        player continues turn

    else

        draw one card

        if drawn card matches requested rank

            remove completed books

            player continues turn

        else

            remove completed books

            next player's turn

determine winner by counting books

State machine:
Start Turn
     |
     v
Choose Rank
     |
     v
Ask Opponent
     |
     +----------------------+
     |                      |
Opponent Has Cards?         No
     |                      |
    Yes                     |
     |                      |
Receive All Cards           Draw One Card
     |                      |
     v                      v
Check for Books      Draw Requested Rank?
     |                      |
     |                 +----+----+
     |                 |         |
     |                Yes       No
     |                 |         |
     +-----------------+         |
               |                 |
        Continue Turn      Next Player

Key Rules Summary
You may only ask for a rank that is already in your hand.
When asked, an opponent must give all cards of the requested rank.
Completing a book requires all four suits of a rank.
A successful request earns another turn.
Drawing the requested rank after hearing "Go Fish!" also earns another turn in the standard rules.
The player with the most completed books wins.