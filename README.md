# Discord Durak Bot

A Discord bot for playing the Russian card game Durak.

## Features

- Play the Durak card game with friends in Discord
- Private channels for each player
- Automatic card dealing and turn management
- Visual representation of the game state
- Role-based permissions

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your Discord bot token:
   ```
   DISCORD_TOKEN1=your_discord_token_here
   ```
4. Run the bot:
   ```
   python bot.py
   ```

## Game Commands

- `/durak` - Start setting up a new game
- `/join` - Join a game that's being set up
- `/start` - Start the game with all joined players
- `/play <card(s)>` - Play cards as the attacker
- `/defend <card(s)>` - Defend with cards as the defender
- `/take` - Take all cards from the table as the defender
- `/giveup` - End your attack (only when all cards are defended)
- `/deleteall` - (Admin only) Delete all game channels and roles
- `/help_durak` - Show help information for game commands

## Game Rules

Durak is a Russian card game where the objective is to get rid of all your cards. The last player with cards is the "durak" (fool).

### Basic Rules:
1. Each player starts with 6 cards
2. The bottom card of the deck determines the trump suit
3. The player with the lowest trump card attacks first
4. The attacker plays cards, and the defender must beat them with higher cards of the same suit or trumps
5. If the defender successfully defends all cards, they become the next attacker
6. If the defender takes the cards, the next player becomes the attacker
7. After each turn, players draw cards to maintain 6 cards in hand (if possible)
8. The game continues until only one player has cards left - they are the "durak"

## Project Structure

- `bot.py` - Main bot initialization and event handling
- `commands.py` - Game command implementations
- `models.py` - Data models for the game (Card, Player, Server, Application)
- `config.py` - Configuration settings and constants
- `utils/helpers.py` - Utility functions for Discord operations

## License

MIT License