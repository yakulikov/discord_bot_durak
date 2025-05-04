# Discord Durak Bot

A Discord bot for playing the Russian card game Durak.

## Invite the Bot

Add the bot to your server using this link:
[Invite Durak Bot](https://discord.com/oauth2/authorize?client_id=1368277750439219300&permissions=8&integration_type=0&scope=bot)

## Features

- Play the Durak card game with friends in Discord
- Fully reaction-based gameplay - no typing needed!
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
4. Run the reaction-based version (recommended):
   ```
   python run_reaction_based.py
   ```
   
   Or run the command-based version:
   ```
   python bot.py
   ```

## Game Commands

### Setup Commands
- `/durak` - Start setting up a new game (creates a reaction-based setup message)
- `/join` - (Alternative) Join a game that's being set up
- `/start` - (Alternative) Start the game with all joined players
- `/deleteall` - (Admin only) Delete all game channels and roles
- `/help_durak` - Show help information for game commands

### Reaction Controls
- **Game Setup**:
  - 👤 - Join the game
  - 🎮 - Start the game (requires at least 2 players)
  
- **In-Game Actions**:
  - 🃏 - Play cards as the attacker
  - 🛡️ - Defend with cards as the defender
  - 🤲 - Take all cards from the table as the defender
  - 🏳️ - End your attack (only when all cards are defended)
  
- **Card Selection**:
  - 1️⃣-🔟 - Select cards
  - ✅ - Confirm selection
  - ❌ - Cancel selection
  - ⏪/⏩ - Navigate pages (for 10+ cards)

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

### Main Files
- `run_reaction_based.py` - Run the reaction-based version of the bot (recommended)
- `reaction_based_main.py` - Main implementation of the reaction-based Durak game
- `bot.py` - Original command-based bot implementation
- `improved_main.py` - Improved version of the command-based implementation
- `run_improved.py` - Run the improved command-based version

### Support Files
- `models.py` - Data models for the game (Card, Player, Server, Application)
- `config.py` - Configuration settings and constants
- `commands.py` - Game command implementations for the original version
- `utils/helpers.py` - Utility functions for Discord operations

## License

MIT License