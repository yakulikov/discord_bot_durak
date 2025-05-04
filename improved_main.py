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

# Card class for better representation
class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit

# Set up Discord bot
intents = discord.Intents.all()
client = commands.Bot(command_prefix='/', intents=intents)

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

    async def update_table(self):
        """Update the table display for all players."""
        for player in self.players:
            content = []
            for a, d in self.table:
                if d:
                    content.append(f"{a}<-{d}")
                else:
                    content.append(f"{a}")

            if self.trump_card:
                trump_str = f"{self.trump_card.suit}" if self.trump_taken else f"{self.trump_card}"
            else:
                trump_str = "?"

            deck_status = f"Deck: {len(self.deck)} cards | Trump: {trump_str}"
            table_str = "     ".join(content) if content else "(empty)"
            
            try:
                await self.players[player].table_message.edit(
                    content=f'Table: ```{table_str}\n{deck_status}```'
                )
            except Exception as e:
                logger.error(f"Failed to update table: {str(e)}")

    async def update_hand(self, player):
        """Update the hand display for a specific player."""
        cards = ' '.join([f' {card}' for card in self.players[player].hand])
        
        try:
            await self.players[player].cards_message.edit(
                content=f'Here are your cards: ```{cards}```'
            )
        except Exception as e:
            logger.error(f"Failed to update hand: {str(e)}")

    def cards_are_in_hand(self, player, cards):
        """Check if all specified cards are in the player's hand."""
        hand_strings = [str(card) for card in player.hand]
        return all(card in hand_strings for card in cards)

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
            
            await self.update_hand(p.author)
        
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
        if attacking_card.suit == self.trump_card.suit and defending_card.suit != self.trump_card.suit:
            return False
        elif attacking_card.suit != self.trump_card.suit and defending_card.suit == self.trump_card.suit:
            return True
        elif defending_card.suit == attacking_card.suit:
            return self.card_ranks[attacking_card.rank] < self.card_ranks[defending_card.rank]
        else:
            return False

    def initialize_deck(self):
        """Initialize and shuffle the deck of cards."""
        self.deck = []
        for number in range(6, 14):
            for suit in ['♥️', '♦️', '♣️', '♠️']:
                label = str(number)
                if number == 10: label = 'J'
                elif number == 11: label = 'Q'
                elif number == 12: label = 'K'
                elif number == 13: label = 'A'
                self.deck.append(Card(label, suit))
        
        random.shuffle(self.deck)
        self.trump_card = self.deck[-1]

class Player:
    def __init__(self, author, player_number):
        self.author = author
        self.number = player_number
        self.channel = None
        self.hand = []
        self.cards_message = None
        self.attacker_message = None
        self.defender_message = None
        self.table_message = None
        self.error_message = None
        self.tip_message = None
    
    async def send_error(self, ctx, message):
        """Send an error message to the player, replacing any previous error message."""
        try:
            if self.error_message:
                await self.error_message.delete()
            self.error_message = await ctx.send(message)
        except Exception as e:
            logger.error(f"Failed to send error message: {str(e)}")
    
    async def send_tip(self, message):
        """Send a tip message to the player, replacing any previous tip message."""
        try:
            if self.tip_message:
                await self.tip_message.delete()
            self.tip_message = await self.channel.send(message)
        except Exception as e:
            logger.error(f"Failed to send tip message: {str(e)}")
    
    async def cleanup_messages(self):
        """Clean up temporary messages."""
        for msg in [self.tip_message, self.error_message]:
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
        self.tip_message = None
        self.error_message = None

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
        await message.channel.send("Type /join to join the game.")
        server.state = GameState.SETUP
        server.players = {}

    elif server.state == GameState.SETUP and message.content.startswith('/join'):
        if message.author not in server.players:
            server.players[message.author] = Player(message.author, len(server.players) + 1)
            await message.channel.send(f'{message.author.display_name} joined the game.')
            await message.delete()
        else:
            await message.channel.send(f'{message.author.display_name} is already in the game.')

    await client.process_commands(message)

@client.command(name='start')
async def start_game(ctx):
    """Start a Durak game with the joined players."""
    server = app.get_server(ctx.guild)
    await ctx.message.delete()

    if server.state != GameState.SETUP or len(server.players) < 2:
        await ctx.send("Not enough players or game not set up. Use /durak to set up a game.")
        return

    # Initialize game state
    server.state = GameState.PLAYING
    server.initialize_deck()
    server.attacker = None
    lowest_trump = None

    # Create player channels and deal cards
    for player in server.players:
        # Create role for the player
        role_name = f'durak {server.players[player].number}'
        try:
            role = await ctx.guild.create_role(name=role_name, colour=discord.Colour.random())
            await player.add_roles(role)
        except Exception as e:
            logger.error(f"Error creating role: {str(e)}")
            await ctx.send("Failed to create roles. Check bot permissions.")
            return
        
        # Create private channel
        channel_name = f'durak-{player.display_name}-room'.lower().replace(' ', '-')
        try:
            channel = await ctx.guild.create_text_channel(channel_name)
            await channel.set_permissions(role, send_messages=True, read_messages=True)
            await channel.set_permissions(ctx.guild.default_role, read_messages=False)
        except Exception as e:
            logger.error(f"Error creating channel: {str(e)}")
            await ctx.send("Failed to create channels. Check bot permissions.")
            return
        
        # Set up player
        p = server.players[player]
        p.channel = channel
        p.hand = [server.deck.pop(0) for _ in range(6)]
        
        # Check for lowest trump
        for card in p.hand:
            if card.suit == server.trump_card.suit:
                if lowest_trump is None or server.card_ranks[card.rank] < server.card_ranks[lowest_trump]:
                    lowest_trump = card.rank
                    server.attacker = p
        
        # Send initial messages
        players_list = ", ".join([player.display_name for player in server.players])
        await channel.send(f'Players in the game: {players_list}')
        
        cards_str = ' '.join([str(card) for card in p.hand])
        p.cards_message = await channel.send(f'Here are your cards: ```{cards_str}```')

    # Set initial attacker and defender
    if server.attacker is None:
        server.attacker = list(server.players.values())[0]

    players_by_number = sorted(server.players.values(), key=lambda p: p.number)
    attacker_index = next(i for i, p in enumerate(players_by_number) if p == server.attacker)
    defender_index = (attacker_index + 1) % len(players_by_number)
    server.defender = players_by_number[defender_index]

    # Send game status to all players
    for player in server.players:
        p = server.players[player]
        p.attacker_message = await p.channel.send(
            f'Attacker: ***{server.attacker.author.display_name}***\n'
            f'Defender: ***{server.defender.author.display_name}***'
        )
        
        p.table_message = await p.channel.send('Table: ```(empty)\nDeck: loading...```')

    await server.update_table()
    
    # Send tip to attacker
    await server.attacker.send_tip(f'Your turn! Type /play <card(s)> to play, /giveup to end your attack.')
    
    await ctx.send("Game started, roles and channels created.")

@client.command(name='play')
async def play(ctx, *cards):
    """Play cards as the attacker."""
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    
    if server.state != GameState.PLAYING:
        return
    
    if ctx.author not in server.players:
        return
    
    player = server.players[ctx.author]
    
    # Validate player is attacker
    if ctx.author != server.attacker.author or ctx.channel != server.attacker.channel:
        return
    
    # Validate cards
    if not cards:
        await player.send_error(ctx, "Please specify which card(s) to play.")
        return
    
    # Check if cards are in hand
    if not server.cards_are_in_hand(player, cards):
        await player.send_error(ctx, "You do not have these cards.")
        return
    
    # Check if all cards have the same value
    card_objects = []
    try:
        for card_str in cards:
            rank = card_str[:-2]
            suit = card_str[-2:]
            card_objects.append(Card(rank, suit))
        
        first_rank = card_objects[0].rank
        
        if any(card.rank != first_rank for card in card_objects):
            await player.send_error(ctx, "You can only play cards of the same value.")
            return
        
        # Check if cards match values on the table
        if server.table:
            allowed_values = set()
            for atk, dfn in server.table:
                allowed_values.add(atk.rank)
                if dfn:
                    allowed_values.add(dfn.rank)
            
            if not all(card.rank in allowed_values for card in card_objects):
                await player.send_error(ctx, 
                    "You can only play cards that match the rank of any card on the table."
                )
                return
        
        # Play the cards
        for card_obj in card_objects:
            player.hand.remove(card_obj)
            server.table.append((card_obj, None))
        
        # Update defender's tip
        await server.defender.send_tip("Type /defend <card(s)> to defend or /take to take the cards.")
        
        # If all cards have been defended, enable /giveup tip
        if all(d is not None for _, d in server.table):
            await player.send_tip(
                f'Your turn! Type /play <card(s)> to continue the attack or /giveup to end your attack.'
            )
        
        # Update displays
        await server.update_hand(ctx.author)
        await server.update_table()
        
    except Exception as e:
        logger.error(f"Error in play command: {str(e)}")
        await player.send_error(ctx, f"An error occurred: {str(e)}")

@client.command(name='defend')
async def defend(ctx, *cards):
    """Defend against attack cards."""
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    
    if server.state != GameState.PLAYING:
        return
    
    if ctx.author not in server.players:
        return
    
    player = server.players[ctx.author]
    
    # Validate player is defender
    if ctx.author != server.defender.author or ctx.channel != server.defender.channel:
        return
    
    # Check if there are cards to defend against
    if not server.table:
        await player.send_error(ctx, "There are no cards to defend against.")
        return
    
    # Check if all cards are already defended
    if all(def_card is not None for _, def_card in server.table):
        await player.send_error(ctx, "You already defended all cards.")
        return
    
    # Validate cards
    if not cards:
        await player.send_error(ctx, "Please specify which card(s) to defend with.")
        return
    
    # Check if cards are in hand
    if not server.cards_are_in_hand(player, cards):
        await player.send_error(ctx, "You do not have these cards.")
        return
    
    # Get undefended cards
    undefended = [i for i, (_, d) in enumerate(server.table) if d is None]
    
    # Check if the right number of cards were provided
    if len(cards) != len(undefended):
        await player.send_error(ctx, f"You must defend all {len(undefended)} undefended cards.")
        return
    
    try:
        # Convert strings to Card objects
        card_objects = []
        for card_str in cards:
            rank = card_str[:-2]
            suit = card_str[-2:]
            card_objects.append(Card(rank, suit))
        
        # Check if defenses are valid
        valid_defense = True
        for j, i in enumerate(undefended):
            attack_card = server.table[i][0]
            defense_card = card_objects[j]
            
            if not server.is_defence_success(attack_card, defense_card):
                valid_defense = False
                break
        
        if not valid_defense:
            await player.send_error(ctx, "These cards are not a valid defence.")
            return
        
        # Apply the defense
        for j, i in enumerate(undefended):
            defense_card = card_objects[j]
            server.table[i] = (server.table[i][0], defense_card)
            player.hand.remove(defense_card)
        
        # Update displays
        await server.update_hand(ctx.author)
        await server.update_table()
        
        # If all cards are now defended, update attacker's tip
        if all(d is not None for _, d in server.table):
            await server.attacker.send_tip(
                f'Your turn! Type /play <card(s)> to continue the attack or /giveup to end your attack.'
            )
        
    except Exception as e:
        logger.error(f"Error in defend command: {str(e)}")
        await player.send_error(ctx, f"An error occurred: {str(e)}")

@client.command(name='take')
async def take(ctx):
    """Take all cards from the table as the defender."""
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    
    if server.state != GameState.PLAYING:
        return
    
    if ctx.author not in server.players:
        return
    
    player = server.players[ctx.author]
    
    # Validate player is defender
    if ctx.author != server.defender.author or ctx.channel != server.defender.channel:
        return
    
    # Check if there are cards to take
    if not server.table:
        await player.send_error(ctx, "There are no cards to take.")
        return
    
    # Check if all cards are already defended
    if all(def_card is not None for _, def_card in server.table):
        await player.send_error(ctx, "You already defended all cards. You cannot take now.")
        return
    
    # Take all cards
    for attack_card, defense_card in server.table:
        player.hand.append(attack_card)
        if defense_card:
            player.hand.append(defense_card)
    
    # End the turn
    await end_turn(server, turn_taken=True)

@client.command(name='giveup')
async def giveup(ctx):
    """End your attack and pass the turn."""
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    
    if server.state != GameState.PLAYING:
        return
    
    if ctx.author not in server.players:
        return
    
    player = server.players[ctx.author]
    
    # Validate player is attacker
    if ctx.author != server.attacker.author or ctx.channel != server.attacker.channel:
        return
    
    # Check if there are cards on the table
    if not server.table:
        await player.send_error(ctx, "You must play at least one card before you can give up.")
        return
    
    # Check if all cards have been defended
    if any(def_card is None for _, def_card in server.table):
        await player.send_error(ctx, "You can only give up after all your cards have been defended.")
        return
    
    # End the turn
    await end_turn(server, turn_taken=False)

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
    
    # Update player messages
    for p in server.players.values():
        try:
            await p.attacker_message.edit(content=
                f'Attacker: ***{server.attacker.author.display_name}***\n'
                f'Defender: ***{server.defender.author.display_name}***'
            )
        except Exception as e:
            logger.error(f"Error updating attacker message: {str(e)}")
    
    # Refill hands
    await server.refill_hands()
    
    # Check win condition
    if len(server.players) == 1:
        durak = list(server.players.values())[0]
        
        # Notify finished players
        for fin_author in server.finished_players:
            try:
                await fin_author.send(f"Game over! ***{durak.author.display_name}*** is the Durak!")
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
    
    # Replace trump card if it's taken
    if server.trump_card and server.trump_card not in server.deck:
        # Keep only the suit information
        server.trump_card = Card(server.trump_card.rank, server.trump_card.suit)
        server.trump_taken = True
    
    # Update all displays
    for player in server.players:
        try:
            await server.update_hand(player)
        except Exception as e:
            logger.error(f"Error updating hand: {str(e)}")
    
    await server.update_table()
    
    # Attacker gets a tip to start turn
    await server.attacker.send_tip(
        f'Your turn! Type /play <card(s)> to play or /giveup to end your attack.'
    )

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
        value="Start setting up a new Durak game", 
        inline=False
    )
    embed.add_field(
        name="/join", 
        value="Join a game that's being set up", 
        inline=False
    )
    embed.add_field(
        name="/start", 
        value="Start the game with all joined players", 
        inline=False
    )
    embed.add_field(
        name="/play <card(s)>", 
        value="Play cards as the attacker (e.g., /play 7♥️ 7♦️)", 
        inline=False
    )
    embed.add_field(
        name="/defend <card(s)>", 
        value="Defend with cards as the defender", 
        inline=False
    )
    embed.add_field(
        name="/take", 
        value="Take all cards from the table as the defender", 
        inline=False
    )
    embed.add_field(
        name="/giveup", 
        value="End your attack (only when all cards are defended)", 
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