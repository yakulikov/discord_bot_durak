import discord
from discord.ext import commands
import random
import os
import asyncio
import logging
from enum import Enum
from typing import Dict, List, Set, Tuple, Optional
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("durak_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('durak_bot')

# Load environment variables
load_dotenv()
token = os.getenv('DISCORD_TOKEN1')

# Validate token
if not token:
    logger.error("No Discord token found. Please set the DISCORD_TOKEN1 environment variable.")
    raise ValueError("No Discord token found. Please set the DISCORD_TOKEN1 environment variable.")

# Game state enum
class GameState(Enum):
    SETUP = 0
    PLAYING = 1
    FINISHED = 2

# Action state enum
class ActionState(Enum):
    IDLE = 0
    SELECTING_CARDS = 1
    CONFIRMING_ACTION = 2

# Card class for better representation
class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.original_suit = suit
        # Map emoji suits to alternative symbols with better contrast
        suit_map = {
            '♠️': '♤',  # Spades
            '♥️': '♡',  # Hearts
            '♦️': '♢',  # Diamonds
            '♣️': '♧'   # Clubs
        }
        self.suit = suit_map.get(suit, suit)
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.original_suit == other.original_suit

# Set up Discord bot
intents = discord.Intents.all()
client = commands.Bot(command_prefix='/', intents=intents)

# Emoji numbers for card selection
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
CONFIRM_EMOJI = "✅"
CANCEL_EMOJI = "❌"
PLAY_EMOJI = "🃏"
DEFEND_EMOJI = "🛡️"
TAKE_EMOJI = "🤲"
GIVEUP_EMOJI = "🏳️"
NEXT_PAGE_EMOJI = "⏩"
PREV_PAGE_EMOJI = "⏪"
JOIN_EMOJI = "👤"
START_EMOJI = "🎮"

class Application:
    def __init__(self):
        self.servers = {}

    def get_server(self, guild):
        if guild.id not in self.servers:
            self.servers[guild.id] = Server(guild.id, guild.name)
        return self.servers[guild.id]

class Server:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.trump_taken = False
        self.state = GameState.SETUP
        self.players = {}
        self.deck = []
        self.trump_card = None
        self.table = []
        self.attacker = None
        self.defender = None
        self.finished_players = set()  # authors who completed the game
        self.card_ranks = {'6': 0, '7': 1, '8': 2, '9': 3, '10': 4, 'J': 5, 'Q': 6, 'K': 7, 'A': 8}
        self.active_selection_messages = {}  # Track active selection messages
        self.setup_message = None  # Message for game setup with reactions
        self.setup_channel = None  # Channel where setup is happening

    async def update_table(self):
        """Update the table display for all players."""
        for player in self.players.values():
            embed = discord.Embed(title="Game Table", color=discord.Color.gold())
            
            # Add table cards
            table_str = ""
            for a, d in self.table:
                if d:
                    table_str += f"{a} ← {d}  "
                else:
                    table_str += f"{a} ❓  "
            
            embed.add_field(
                name="Cards on Table", 
                value=table_str if table_str else "(empty)", 
                inline=False
            )
            
            # Add deck and trump info
            if self.trump_card:
                trump_str = f"{self.trump_card.suit}" if self.trump_taken else f"{self.trump_card}"
            else:
                trump_str = "?"
                
            embed.add_field(
                name="Game Info", 
                value=f"Deck: {len(self.deck)} cards | Trump: {trump_str}", 
                inline=False
            )
            
            # Add turn info
            embed.add_field(
                name="Turn", 
                value=f"Attacker: {self.attacker.author.display_name}\nDefender: {self.defender.author.display_name}", 
                inline=False
            )
            
            try:
                if player.table_message:
                    await player.table_message.edit(embed=embed)
                else:
                    player.table_message = await player.channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to update table: {str(e)}")

    async def update_hand(self, player):
        """Update the hand display for a specific player."""
        embed = discord.Embed(title="Your Cards", color=discord.Color.blue())
        
        if player.hand:
            # Group cards by suit for better organization
            suits = {"♥️": [], "♦️": [], "♣️": [], "♠️": []}
            for card in player.hand:
                suits[card.original_suit].append(card)
            
            # Create a compact display of all cards
            all_cards = []
            # Use the alternative suit symbols for display
            suit_display = {"♥️": "♡", "♦️": "♢", "♣️": "♧", "♠️": "♤"}
            
            for suit in ["♥️", "♦️", "♣️", "♠️"]:
                cards = suits[suit]
                if cards:
                    sorted_cards = sorted(cards, key=lambda c: self.card_ranks[c.rank])
                    cards_str = " ".join([str(card) for card in sorted_cards])
                    all_cards.append(f"{suit_display[suit]}: {cards_str}")
            
            embed.description = "\n".join(all_cards)
            
            # Add total count
            embed.set_footer(text=f"Total: {len(player.hand)} cards")
        else:
            embed.description = "You have no cards left!"
        
        try:
            if player.cards_message:
                await player.cards_message.edit(embed=embed)
            else:
                player.cards_message = await player.channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update hand: {str(e)}")

    def cards_are_in_hand(self, player, cards):
        """Check if all specified cards are in the player's hand."""
        return all(card in player.hand for card in cards)

    async def refill_hands(self):
        """Refill all players' hands to 6 cards if possible."""
        players_by_number = sorted(self.players.values(), key=lambda p: p.number)
        start_index = next((i for i, p in enumerate(players_by_number) if p == self.attacker), 0)
        
        for i in range(len(players_by_number)):
            p = players_by_number[(start_index + i) % len(players_by_number)]
            
            if len(p.hand) == 0:
                continue  # already empty, skip draw
            
            while len(p.hand) < 6 and self.deck:
                drawn = self.deck.pop(0)
                if drawn == self.trump_card:
                    self.trump_taken = True
                p.hand.append(drawn)
            
            await self.update_hand(p)
        
        # Eliminate players with 0 cards after refill
        eliminated = []
        for p in list(self.players.values()):
            if len(p.hand) == 0:
                try:
                    durak_role = discord.utils.get(p.channel.guild.roles, name="Ultimate Durak")
                    if durak_role in p.author.roles:
                        await p.author.remove_roles(durak_role)
                except Exception as e:
                    logger.error(f"Error removing role: {str(e)}")
                
                eliminated.append(p)
        
        for p in eliminated:
            self.finished_players.add(p.author)
            try:
                await p.channel.send("🎉 You have finished all your cards!")
                await p.channel.delete()
            except Exception as e:
                logger.error(f"Error with channel operations: {str(e)}")
            
            try:
                role = discord.utils.get(p.channel.guild.roles, name=f"durak {p.number}")
                if role:
                    await role.delete()
            except Exception as e:
                logger.error(f"Error deleting role: {str(e)}")
            
            del self.players[p.author]

    def is_defence_success(self, attacking_card, defending_card):
        """Determine if a defense is successful according to Durak rules."""
        if attacking_card.original_suit == self.trump_card.original_suit and defending_card.original_suit != self.trump_card.original_suit:
            return False
        elif attacking_card.original_suit != self.trump_card.original_suit and defending_card.original_suit == self.trump_card.original_suit:
            return True
        elif defending_card.original_suit == attacking_card.original_suit:
            return self.card_ranks[attacking_card.rank] < self.card_ranks[defending_card.rank]
        else:
            return False

    def initialize_deck(self):
        """Initialize and shuffle the deck of cards."""
        self.deck = []
        for number in range(6, 14):
            for suit in ['♥️', '♦️', '♣️', '♠️']:
                if number == 6: label = '6'
                elif number == 7: label = '7'
                elif number == 8: label = '8'
                elif number == 9: label = '9'
                elif number == 10: label = '10'
                elif number == 11: label = 'J'
                elif number == 12: label = 'Q'
                elif number == 13: label = 'K'
                elif number == 14: label = 'A'
                else: label = str(number)  # Fallback
                self.deck.append(Card(label, suit))
        
        random.shuffle(self.deck)
        self.trump_card = self.deck[-1]

    async def display_action_menu(self, player, is_attacker=True):
        """Display action menu with reaction buttons."""
        # Clear any existing action menu
        if player.action_menu:
            try:
                await player.action_menu.delete()
            except:
                pass
        
        embed = discord.Embed(
            title="Your Turn", 
            description="Choose an action by clicking a reaction below:",
            color=discord.Color.green() if is_attacker else discord.Color.red()
        )
        
        if is_attacker:
            embed.add_field(name=f"{PLAY_EMOJI} Play Card(s)", value="Select cards to attack", inline=True)
            
            # Only show give up if there are cards on the table and all are defended
            if self.table and all(d is not None for _, d in self.table):
                embed.add_field(name=f"{GIVEUP_EMOJI} End Attack", value="Pass turn to next player", inline=True)
        else:
            embed.add_field(name=f"{DEFEND_EMOJI} Defend", value="Select cards to defend with", inline=True)
            embed.add_field(name=f"{TAKE_EMOJI} Take Cards", value="Take all cards from the table", inline=True)
        
        player.action_menu = await player.channel.send(embed=embed)
        
        # Add reactions
        if is_attacker:
            await player.action_menu.add_reaction(PLAY_EMOJI)
            if self.table and all(d is not None for _, d in self.table):
                await player.action_menu.add_reaction(GIVEUP_EMOJI)
        else:
            await player.action_menu.add_reaction(DEFEND_EMOJI)
            await player.action_menu.add_reaction(TAKE_EMOJI)

    async def display_card_selection(self, player, action_type, undefended_indices=None):
        """Display cards with number reactions for selection."""
        # Clear any existing selection message
        if player.author in self.active_selection_messages:
            try:
                await self.active_selection_messages[player.author].delete()
            except:
                pass
        
        # Reset pagination
        player.selection_page = 0
        
        # Create and display the selection message
        await self.update_card_selection_display(player, action_type, undefended_indices)
        
        # Set player state
        player.action_state = ActionState.SELECTING_CARDS
        player.selected_cards = []
        player.selection_action = action_type
        
        if action_type == "defend":
            player.undefended_indices = undefended_indices
            
    async def update_card_selection_display(self, player, action_type=None, undefended_indices=None, update_reactions=False):
        """Update the card selection display with pagination."""
        # Sort the hand by suit and rank
        sorted_hand = sorted(player.hand, key=lambda card: (card.original_suit, self.card_ranks[card.rank]))
        
        # Store the mapping between sorted indices and original hand
        player.sorted_to_hand_map = {i: sorted_hand[i] for i in range(len(sorted_hand))}
        
        # Calculate pagination
        cards_per_page = 10
        total_pages = (len(sorted_hand) + cards_per_page - 1) // cards_per_page
        start_idx = player.selection_page * cards_per_page
        end_idx = min(start_idx + cards_per_page, len(sorted_hand))
        
        embed = discord.Embed(
            title="Select Card(s)", 
            description=f"Click the number reactions to select cards, then click ✅ to confirm (Page {player.selection_page + 1}/{max(1, total_pages)}):",
            color=discord.Color.blue()
        )
        
        # Display cards with numbers in a compact format
        cards_display = []
        for i in range(start_idx, end_idx):
            # The display number is relative to the current page (1-10)
            display_num = i - start_idx + 1
            
            # Get the corresponding emoji for this number
            emoji_num = NUMBER_EMOJIS[display_num - 1]
            
            card = sorted_hand[i]
            selected = "✓ " if card in player.selected_cards else ""
            cards_display.append(f"**{emoji_num}** {selected}{card}")
        
        # Group cards in rows of 5 for better display
        rows = []
        for i in range(0, len(cards_display), 5):
            rows.append("  ".join(cards_display[i:i+5]))
        
        # Show selected cards from all pages
        if player.selected_cards:
            selected_str = ", ".join([str(card) for card in player.selected_cards])
            embed.add_field(
                name="Selected Cards",
                value=selected_str,
                inline=False
            )
        
        embed.add_field(
            name="Select Card(s)",
            value="\n".join(rows) if rows else "(No cards on this page)",
            inline=False
        )
        
        # For defense, show which cards need defending
        if action_type == "defend" and undefended_indices:
            undefended_cards = [self.table[i][0] for i in undefended_indices]
            undefended_str = ", ".join([str(card) for card in undefended_cards])
            embed.add_field(
                name="Cards to Defend Against:",
                value=undefended_str,
                inline=False
            )
        
        # Add instructions with pagination info if needed
        instructions = [
            f"Select cards by clicking number reactions",
            f"Click {CONFIRM_EMOJI} to confirm your selection",
            f"Click {CANCEL_EMOJI} to cancel"
        ]
        
        if total_pages > 1:
            instructions.append(f"Use {PREV_PAGE_EMOJI} and {NEXT_PAGE_EMOJI} to navigate pages")
        
        embed.add_field(
            name="Instructions",
            value="\n".join(instructions),
            inline=False
        )
        
        # Create a new message or update existing one
        if not player.selection_message:
            # First time creating the message - create it and add all reactions
            player.selection_message = await player.channel.send(embed=embed)
            self.active_selection_messages[player.author] = player.selection_message
            
            # Add all necessary reactions
            await self.add_selection_reactions(player, total_pages, end_idx - start_idx)
        else:
            # Just update the embed content without touching reactions
            try:
                await player.selection_message.edit(embed=embed)
            except Exception as e:
                logger.error(f"Failed to update selection message: {str(e)}")
                # If editing fails, create a new message with reactions
                player.selection_message = await player.channel.send(embed=embed)
                self.active_selection_messages[player.author] = player.selection_message
                await self.add_selection_reactions(player, total_pages, end_idx - start_idx)
        
        # Only update reactions if explicitly requested (page change)
        if update_reactions:
            try:
                await player.selection_message.clear_reactions()
                await self.add_selection_reactions(player, total_pages, end_idx - start_idx)
            except Exception as e:
                logger.error(f"Failed to update reactions: {str(e)}")
    
    async def add_selection_reactions(self, player, total_pages, visible_cards):
        """Add all necessary reactions to a selection message."""
        # Add number reactions for visible cards
        for i in range(min(visible_cards, 10)):
            await player.selection_message.add_reaction(NUMBER_EMOJIS[i])
        
        # Add pagination reactions if needed
        if total_pages > 1:
            if player.selection_page > 0:
                await player.selection_message.add_reaction(PREV_PAGE_EMOJI)
            if player.selection_page < total_pages - 1:
                await player.selection_message.add_reaction(NEXT_PAGE_EMOJI)
        
        # Add confirm/cancel reactions
        await player.selection_message.add_reaction(CONFIRM_EMOJI)
        await player.selection_message.add_reaction(CANCEL_EMOJI)
        
    async def update_setup_message(self):
        """Update the game setup message with current players and status."""
        embed = discord.Embed(
            title="Durak Game Setup", 
            description="React to join or start the game:",
            color=discord.Color.gold()
        )
        
        # Add player list
        if self.players:
            players_list = "\n".join([f"{i+1}. {player.display_name}" for i, player in enumerate(self.players)])
            embed.add_field(
                name=f"Players ({len(self.players)})",
                value=players_list,
                inline=False
            )
        else:
            embed.add_field(
                name="Players (0)",
                value="No players yet. Click 👤 to join!",
                inline=False
            )
        
        # Add instructions
        embed.add_field(
            name="How to Join",
            value=f"Click {JOIN_EMOJI} to join the game\nClick {START_EMOJI} to start the game (need at least 2 players)",
            inline=False
        )
        
        # Update or create the setup message
        if self.setup_message:
            try:
                await self.setup_message.edit(embed=embed)
            except Exception as e:
                logger.error(f"Failed to update setup message: {str(e)}")
                self.setup_message = await self.setup_channel.send(embed=embed)
                await self.setup_message.add_reaction(JOIN_EMOJI)
                await self.setup_message.add_reaction(START_EMOJI)
        else:
            self.setup_message = await self.setup_channel.send(embed=embed)
            await self.setup_message.add_reaction(JOIN_EMOJI)
            await self.setup_message.add_reaction(START_EMOJI)

class Player:
    def __init__(self, author, player_number):
        self.author = author
        self.number = player_number
        self.channel = None
        self.hand = []
        self.cards_message = None
        self.action_menu = None
        self.table_message = None
        self.error_message = None
        self.tip_message = None
        self.notification_message = None  # For turn notifications
        self.action_state = ActionState.IDLE
        self.selected_cards = []
        self.selection_message = None
        self.selection_action = None
        self.undefended_indices = None
        self.selection_page = 0  # For pagination of card selection
        self.sorted_to_hand_map = {}  # Maps sorted indices to hand cards
    
    async def send_error(self, message):
        """Send an error message to the player, replacing any previous error message."""
        try:
            if self.error_message:
                await self.error_message.delete()
            
            embed = discord.Embed(
                title="Error", 
                description=message,
                color=discord.Color.red()
            )
            self.error_message = await self.channel.send(embed=embed)
            
            # Auto-delete after 5 seconds
            await asyncio.sleep(5)
            await self.error_message.delete()
            self.error_message = None
        except Exception as e:
            logger.error(f"Failed to send error message: {str(e)}")
    
    async def send_tip(self, message):
        """Send a tip message to the player, replacing any previous tip message."""
        try:
            if self.tip_message:
                await self.tip_message.delete()
            
            embed = discord.Embed(
                title="Tip", 
                description=message,
                color=discord.Color.purple()
            )
            self.tip_message = await self.channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send tip message: {str(e)}")
            
    async def send_notification(self, title, message, color=discord.Color.blue()):
        """Send a notification message, replacing any previous notification."""
        try:
            if self.notification_message:
                await self.notification_message.delete()
            
            embed = discord.Embed(
                title=title, 
                description=message,
                color=color
            )
            self.notification_message = await self.channel.send(embed=embed)
            
            # Auto-delete after 5 seconds
            await asyncio.sleep(5)
            if self.notification_message:
                await self.notification_message.delete()
                self.notification_message = None
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
    
    async def cleanup_messages(self):
        """Clean up temporary messages."""
        for msg in [self.tip_message, self.error_message, self.action_menu, self.notification_message]:
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
        self.tip_message = None
        self.error_message = None
        self.action_menu = None
        self.notification_message = None

app = Application()

@client.event
async def on_ready():
    logger.info(f'Bot is up and running as {client.user}')
    print('Bot is up and running')

@client.event
async def on_message(message):
    if message.author == client.user or not message.guild:
        return

    server = app.get_server(message.guild)

    if message.content.startswith('/durak'):
        await message.delete()
        # Reset game state
        server.state = GameState.SETUP
        server.players = {}
        server.setup_channel = message.channel
        
        # Create reaction-based setup message
        await server.update_setup_message()
        
        # No need for additional messages - everything is in the setup message now

    # Keep the command processing for backward compatibility
    elif server.state == GameState.SETUP and message.content.startswith('/join'):
        if message.author not in server.players:
            server.players[message.author] = Player(message.author, len(server.players) + 1)
            await message.delete()
            # Update the setup message with the new player
            if server.setup_message:
                await server.update_setup_message()
            else:
                await message.channel.send(f'{message.author.display_name} joined the game.')
        else:
            await message.channel.send(f'{message.author.display_name} is already in the game.')
            await asyncio.sleep(3)
            await message.delete()

    await client.process_commands(message)

@client.event
async def on_reaction_add(reaction, user):
    """Handle reaction additions for card selection and actions."""
    if user.bot or not reaction.message.guild:
        return
    
    server = app.get_server(reaction.message.guild)
    
    # Check if this is a reaction to the setup message
    if server.setup_message and reaction.message.id == server.setup_message.id:
        # Remove the reaction
        try:
            await reaction.remove(user)
        except:
            pass
        
        # Handle setup reactions
        if str(reaction.emoji) == JOIN_EMOJI and server.state == GameState.SETUP:
            # Join the game
            if user not in server.players:
                server.players[user] = Player(user, len(server.players) + 1)
                await server.update_setup_message()
            else:
                # User already joined
                temp_msg = await server.setup_channel.send(f'{user.display_name} is already in the game.')
                await asyncio.sleep(3)
                await temp_msg.delete()
        
        elif str(reaction.emoji) == START_EMOJI and server.state == GameState.SETUP:
            # Start the game if enough players
            if len(server.players) < 2:
                temp_msg = await server.setup_channel.send("Need at least 2 players to start the game.")
                await asyncio.sleep(3)
                await temp_msg.delete()
            else:
                # Start the game
                await start_game_internal(server, reaction.message.channel)
        
        return  # Don't process other reactions for setup message
    
    # Check if user is in a game
    if user not in server.players:
        return
    
    player = server.players[user]
    
    # Check if this is a reaction to the action menu
    if player.action_menu and reaction.message.id == player.action_menu.id:
        # Remove the reaction
        try:
            await reaction.remove(user)
        except:
            pass
        
        # Handle action menu reactions
        if str(reaction.emoji) == PLAY_EMOJI and server.attacker == player:
            # Start card selection for attack
            await server.display_card_selection(player, "play")
            
        elif str(reaction.emoji) == DEFEND_EMOJI and server.defender == player:
            # Get undefended cards
            undefended = [i for i, (_, d) in enumerate(server.table) if d is None]
            if not undefended:
                await player.send_error("There are no cards to defend against.")
                return
            
            # Start card selection for defense
            await server.display_card_selection(player, "defend", undefended)
            
        elif str(reaction.emoji) == TAKE_EMOJI and server.defender == player:
            # Take all cards
            await take_cards(server)
            
        elif str(reaction.emoji) == GIVEUP_EMOJI and server.attacker == player:
            # Check if all cards are defended
            if not server.table:
                await player.send_error("You must play at least one card before you can end your attack.")
                return
                
            if any(d is None for _, d in server.table):
                await player.send_error("You can only end your attack after all your cards have been defended.")
                return
                
            # End the turn
            await end_turn(server, turn_taken=False)
    
    # Check if this is a reaction to a card selection message
    elif player.selection_message and reaction.message.id == player.selection_message.id:
        # Handle card selection reactions
        if player.action_state == ActionState.SELECTING_CARDS:
            # Remove the reaction
            try:
                await reaction.remove(user)
            except:
                pass
            
            if str(reaction.emoji) in NUMBER_EMOJIS:
                # Get the card index relative to the current page
                relative_index = NUMBER_EMOJIS.index(str(reaction.emoji))
                cards_per_page = 10
                absolute_index = player.selection_page * cards_per_page + relative_index
                
                # Check if the index is valid
                if absolute_index in player.sorted_to_hand_map:
                    # Toggle card selection
                    card = player.sorted_to_hand_map[absolute_index]
                    
                    if card in player.selected_cards:
                        player.selected_cards.remove(card)
                    else:
                        player.selected_cards.append(card)
                    
                    # Update the selection message
                    await server.update_card_selection_display(player, player.selection_action, player.undefended_indices)
            
            elif str(reaction.emoji) == NEXT_PAGE_EMOJI:
                # Calculate total pages
                cards_per_page = 10
                total_pages = (len(player.hand) + cards_per_page - 1) // cards_per_page
                
                # Move to next page if possible
                if player.selection_page < total_pages - 1:
                    player.selection_page += 1
                    # Update reactions when changing pages
                    await server.update_card_selection_display(player, player.selection_action, player.undefended_indices, update_reactions=True)
            
            elif str(reaction.emoji) == PREV_PAGE_EMOJI:
                # Move to previous page if possible
                if player.selection_page > 0:
                    player.selection_page -= 1
                    # Update reactions when changing pages
                    await server.update_card_selection_display(player, player.selection_action, player.undefended_indices, update_reactions=True)
            
            elif str(reaction.emoji) == CONFIRM_EMOJI:
                # Process the selected cards
                if not player.selected_cards:
                    await player.send_error("You must select at least one card.")
                    return
                
                if player.selection_action == "play":
                    await process_play_cards(server, player)
                elif player.selection_action == "defend":
                    await process_defend_cards(server, player)
                
                # Clean up
                try:
                    await player.selection_message.delete()
                except:
                    pass
                player.selection_message = None
                player.action_state = ActionState.IDLE
                
                if player.author in server.active_selection_messages:
                    del server.active_selection_messages[player.author]
            
            elif str(reaction.emoji) == CANCEL_EMOJI:
                # Cancel selection
                try:
                    await player.selection_message.delete()
                except:
                    pass
                player.selection_message = None
                player.selected_cards = []
                player.action_state = ActionState.IDLE
                
                if player.author in server.active_selection_messages:
                    del server.active_selection_messages[player.author]
                
                # Show action menu again
                await server.display_action_menu(player, server.attacker == player)

# This function has been replaced by Server.update_card_selection_display

async def process_play_cards(server, player):
    """Process the selected cards for playing."""
    # Check if all cards have the same rank
    if len(set(card.rank for card in player.selected_cards)) > 1:
        await player.send_error("You can only play cards of the same rank.")
        return
    
    # Check if cards match values on the table
    if server.table:
        allowed_values = set()
        for atk, dfn in server.table:
            allowed_values.add(atk.rank)
            if dfn:
                allowed_values.add(dfn.rank)
        
        if not all(card.rank in allowed_values for card in player.selected_cards):
            await player.send_error(
                "You can only play cards that match the rank of any card on the table."
            )
            return
    
    # Play the cards
    for card in player.selected_cards:
        player.hand.remove(card)
        server.table.append((card, None))
    
    # Update displays
    await server.update_hand(player)
    await server.update_table()
    
    # Update defender's action menu
    await server.display_action_menu(server.defender, is_attacker=False)
    
    # If all cards have been defended, enable give up option for attacker
    if all(d is not None for _, d in server.table):
        await server.display_action_menu(server.attacker, is_attacker=True)
    
    # Clear selected cards
    player.selected_cards = []

async def process_defend_cards(server, player):
    """Process the selected cards for defending."""
    # Check if the right number of cards were provided
    undefended = player.undefended_indices
    
    if len(player.selected_cards) != len(undefended):
        await player.send_error(f"You must select exactly {len(undefended)} cards to defend.")
        return
    
    # Check if defenses are valid
    valid_defense = True
    for i, card_index in enumerate(undefended):
        attack_card = server.table[card_index][0]
        defense_card = player.selected_cards[i]
        
        if not server.is_defence_success(attack_card, defense_card):
            valid_defense = False
            break
    
    if not valid_defense:
        await player.send_error("These cards are not a valid defence.")
        return
    
    # Apply the defense
    for i, card_index in enumerate(undefended):
        defense_card = player.selected_cards[i]
        server.table[card_index] = (server.table[card_index][0], defense_card)
        player.hand.remove(defense_card)
    
    # Update displays
    await server.update_hand(player)
    await server.update_table()
    
    # If all cards are now defended, update attacker's action menu
    if all(d is not None for _, d in server.table):
        await server.display_action_menu(server.attacker, is_attacker=True)
    
    # Clear selected cards
    player.selected_cards = []
    player.undefended_indices = None

async def take_cards(server):
    """Take all cards from the table as the defender."""
    player = server.defender
    
    # Check if there are cards to take
    if not server.table:
        await player.send_error("There are no cards to take.")
        return
    
    # Check if all cards are already defended
    if all(def_card is not None for _, def_card in server.table):
        await player.send_error("You already defended all cards. You cannot take now.")
        return
    
    # Take all cards
    for attack_card, defense_card in server.table:
        player.hand.append(attack_card)
        if defense_card:
            player.hand.append(defense_card)
    
    # End the turn
    await end_turn(server, turn_taken=True)

async def end_turn(server, turn_taken):
    """End the current turn and set up the next one."""
    players_by_number = sorted(server.players.values(), key=lambda p: p.number)
    old_attacker = server.attacker
    old_defender = server.defender
    
    # Clean up messages
    for p in server.players.values():
        await p.cleanup_messages()
    
    # Determine next attacker and defender
    if turn_taken:
        # Defender took cards: attacker = player after defender
        def_index = next(i for i, p in enumerate(players_by_number) if p == old_defender)
        start_index = (def_index + 1) % len(players_by_number)
    else:
        # Attackers gave up: defender becomes attacker
        start_index = next(i for i, p in enumerate(players_by_number) if p == old_defender)
    
    server.attacker = players_by_number[start_index]
    server.defender = players_by_number[(start_index + 1) % len(players_by_number)]
    server.table = []
    
    # Refill hands
    await server.refill_hands()
    
    # Check win condition
    if len(server.players) == 1:
        durak = list(server.players.values())[0]
        
        # Notify finished players with a compact message
        for fin_author in server.finished_players:
            try:
                await fin_author.send(f"🎮 Game over! ***{durak.author.display_name}*** is the Durak!")
            except Exception as e:
                logger.error(f"Error sending game over message: {str(e)}")
        
        # Grant "Ultimate Durak" role
        try:
            guild = durak.channel.guild
            durak_role = discord.utils.get(guild.roles, name="Ultimate Durak")
            if not durak_role:
                durak_role = await guild.create_role(name="Ultimate Durak", colour=discord.Colour.dark_red())
            
            await durak.author.add_roles(durak_role)
        except Exception as e:
            logger.error(f"Error assigning Durak role: {str(e)}")
        
        server.state = GameState.FINISHED
        return
    
    # Make sure trump card is preserved even when deck is empty
    if not server.trump_card or (server.trump_card not in server.deck and not server.trump_taken):
        # Keep the trump card information even when it's taken from the deck
        if server.trump_card:
            server.trump_card = Card(server.trump_card.rank, server.trump_card.original_suit)
            server.trump_taken = True
    
    # Update all displays
    for player in server.players:
        try:
            await server.update_hand(server.players[player])
        except Exception as e:
            logger.error(f"Error updating hand: {str(e)}")
    
    await server.update_table()
    
    # Show action menu to attacker
    await server.display_action_menu(server.attacker, is_attacker=True)
    
    # No turn notification - removed as requested

async def start_game_internal(server, channel):
    """Internal function to start a Durak game with the joined players."""
    if server.state != GameState.SETUP or len(server.players) < 2:
        await channel.send("Not enough players or game not set up.")
        return

    # Initialize game state
    server.state = GameState.PLAYING
    server.initialize_deck()
    server.attacker = None
    lowest_trump = None
    
    # Clean up setup message
    if server.setup_message:
        try:
            await server.setup_message.delete()
        except:
            pass
        server.setup_message = None

    # Create player channels and deal cards
    for player in server.players:
        # Create role for the player
        role_name = f'durak {server.players[player].number}'
        try:
            role = await channel.guild.create_role(name=role_name, colour=discord.Colour.random())
            await player.add_roles(role)
        except Exception as e:
            logger.error(f"Error creating role: {str(e)}")
            await channel.send("Failed to create roles. Check bot permissions.")
            return
        
        # Create private channel
        channel_name = f'durak-{player.display_name}-room'.lower().replace(' ', '-')
        try:
            player_channel = await channel.guild.create_text_channel(channel_name)
            await player_channel.set_permissions(role, send_messages=True, read_messages=True)
            await player_channel.set_permissions(channel.guild.default_role, read_messages=False)
        except Exception as e:
            logger.error(f"Error creating channel: {str(e)}")
            await channel.send("Failed to create channels. Check bot permissions.")
            return
        
        # Set up player
        p = server.players[player]
        p.channel = player_channel
        p.hand = [server.deck.pop(0) for _ in range(6)]
        
        # Check for lowest trump
        for card in p.hand:
            if card.suit == server.trump_card.suit:
                if lowest_trump is None or server.card_ranks[card.rank] < server.card_ranks[lowest_trump]:
                    lowest_trump = card.rank
                    server.attacker = p
    
    # Send welcome message to each player
    for player in server.players:
        p = server.players[player]
        
        # Send compact welcome message
        players_list = ", ".join([player.display_name for player in server.players])
        welcome_text = (
            f"**Welcome to Durak!** Players: {players_list}\n"
            f"• Click action buttons: {PLAY_EMOJI} {DEFEND_EMOJI} {TAKE_EMOJI} {GIVEUP_EMOJI}\n"
            f"• Select cards with number reactions, confirm with {CONFIRM_EMOJI}, cancel with {CANCEL_EMOJI}"
        )
        await p.channel.send(welcome_text)
        
        # Send initial hand
        await server.update_hand(p)

    # Set initial attacker and defender
    if server.attacker is None:
        server.attacker = list(server.players.values())[0]

    players_by_number = sorted(server.players.values(), key=lambda p: p.number)
    attacker_index = next(i for i, p in enumerate(players_by_number) if p == server.attacker)
    defender_index = (attacker_index + 1) % len(players_by_number)
    server.defender = players_by_number[defender_index]

    # Update table for all players
    await server.update_table()
    
    # Show action menu to attacker
    await server.display_action_menu(server.attacker, is_attacker=True)
    
    # No game start notification - removed as requested
    
    await channel.send("Game started, roles and channels created.")

@client.command(name='start')
async def start_game(ctx):
    """Start a Durak game with the joined players."""
    server = app.get_server(ctx.guild)
    await ctx.message.delete()
    
    # Use the internal start game function
    await start_game_internal(server, ctx.channel)

@client.command(name='deleteall')
@commands.has_permissions(administrator=True)
async def delete_all(ctx):
    """Delete all Durak game channels and roles (admin only)."""
    guild = ctx.guild
    
    # Delete roles
    roles_to_delete = [role for role in guild.roles if role.name.startswith("durak")]
    for role in roles_to_delete:
        try:
            await role.delete()
            await ctx.send(f'Deleted role: {role.name}')
        except Exception as e:
            logger.error(f"Error deleting role: {str(e)}")
            await ctx.send(f'Failed to delete role: {role.name}')
    
    # Delete channels
    channels_to_delete = [channel for channel in guild.text_channels if channel.name.startswith("durak")]
    for channel in channels_to_delete:
        try:
            await channel.delete()
            await ctx.send(f'Deleted channel: {channel.name}')
        except Exception as e:
            logger.error(f"Error deleting channel: {str(e)}")
            await ctx.send(f'Failed to delete channel: {channel.name}')

@client.command(name='help_durak')
async def help_durak(ctx):
    """Show help information for Durak game commands."""
    embed = discord.Embed(
        title="Durak Game Commands",
        description="Here are the commands for playing the Durak card game:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="/durak", 
        value=f"Start setting up a new Durak game. Creates a setup message with reactions:\n"
              f"{JOIN_EMOJI} - Join the game\n"
              f"{START_EMOJI} - Start the game", 
        inline=False
    )
    embed.add_field(
        name="/join", 
        value="(Alternative) Join a game that's being set up", 
        inline=False
    )
    embed.add_field(
        name="/start", 
        value="(Alternative) Start the game with all joined players", 
        inline=False
    )
    embed.add_field(
        name="Playing with Reactions", 
        value="The entire game is played using reactions. No typing needed!\n"
              f"• Action buttons: {PLAY_EMOJI} {DEFEND_EMOJI} {TAKE_EMOJI} {GIVEUP_EMOJI}\n"
              f"• Card selection: 1️⃣-🔟 + {CONFIRM_EMOJI}/{CANCEL_EMOJI}\n"
              f"• Pagination: {PREV_PAGE_EMOJI}/{NEXT_PAGE_EMOJI} (for 10+ cards)", 
        inline=False
    )
    embed.add_field(
        name="/deleteall", 
        value="(Admin only) Delete all Durak game channels and roles", 
        inline=False
    )
    
    await ctx.send(embed=embed)

@delete_all.error
async def delete_all_error(ctx, error):
    """Handle errors from the delete_all command."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need administrator permissions to use this command.")
    else:
        logger.error(f"Command error: {str(error)}")
        await ctx.send("An error occurred while processing your command.")

# Run the bot
client.run(token)