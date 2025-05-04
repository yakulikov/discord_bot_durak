import discord
from discord.ext import commands
import asyncio
from typing import List, Optional
import random

from models import Application, Server, Player, Card
from config import GameState, logger
from utils.helpers import (
    batch_discord_operations, 
    safe_delete_message, 
    safe_send_message,
    is_game_active,
    is_player_turn
)

class DurakGame(commands.Cog):
    """Cog for the Durak card game commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.app = Application()
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Event handler when the bot is ready."""
        logger.info(f'Bot is up and running as {self.bot.user}')
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Event handler for messages to handle game setup commands."""
        if message.author == self.bot.user or not message.guild:
            return
        
        server = self.app.get_server(message.guild)
        
        if message.content.startswith('/durak'):
            await safe_delete_message(message)
            await safe_send_message(message.channel, "Type /join to join the game.")
            server.state = GameState.SETUP
            server.players = {}
        
        elif server.state == GameState.SETUP and message.content.startswith('/join'):
            if message.author not in server.players:
                server.add_player(message.author)
                await safe_send_message(message.channel, f'{message.author.display_name} joined the game.')
                await safe_delete_message(message)
            else:
                await safe_send_message(message.channel, f'{message.author.display_name} is already in the game.')
    
    @commands.command(name='start')
    async def start_game(self, ctx):
        """Start a Durak game with the joined players."""
        await safe_delete_message(ctx.message)
        server = self.app.get_server(ctx.guild)
        
        if server.state != GameState.SETUP or len(server.players) < 2:
            await safe_send_message(ctx.channel, "Not enough players or game not set up. Use /durak to set up a game.")
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
            except discord.errors.Forbidden:
                logger.error(f"No permission to create/assign roles in {ctx.guild.name}")
                await safe_send_message(ctx.channel, "Failed to create roles. Check bot permissions.")
                return
            
            # Create private channel
            channel_name = f'durak-{player.display_name}-room'.lower().replace(' ', '-')
            try:
                channel = await ctx.guild.create_text_channel(channel_name)
                await channel.set_permissions(role, send_messages=True, read_messages=True)
                await channel.set_permissions(ctx.guild.default_role, read_messages=False)
            except discord.errors.Forbidden:
                logger.error(f"No permission to create channels in {ctx.guild.name}")
                await safe_send_message(ctx.channel, "Failed to create channels. Check bot permissions.")
                return
            
            # Set up player
            p = server.players[player]
            p.channel = channel
            p.hand = [server.deck.pop(0) for _ in range(6)]
            
            # Check for lowest trump
            for card in p.hand:
                if card.suit == server.trump_card.suit:
                    if lowest_trump is None or card.rank < lowest_trump:
                        lowest_trump = card.rank
                        server.attacker = p
            
            # Send initial messages
            players_list = ", ".join([player.display_name for player in server.players])
            await safe_send_message(channel, f'Players in the game: {players_list}')
            
            cards_str = ' '.join([str(card) for card in p.hand])
            p.cards_message = await safe_send_message(channel, f'Here are your cards: ```{cards_str}```')
        
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
            p.attacker_message = await safe_send_message(
                p.channel,
                f'Attacker: ***{server.attacker.author.display_name}***\n'
                f'Defender: ***{server.defender.author.display_name}***'
            )
            
            p.table_message = await safe_send_message(p.channel, 'Table: ```(empty)\nDeck: loading...```')
        
        await server.update_table()
        
        # Send tip to attacker
        await server.attacker.send_tip(f'Your turn! Type /play <card(s)> to play, /giveup to end your attack.')
        
        await safe_send_message(ctx.channel, "Game started, roles and channels created.")
    
    @commands.command(name='play')
    @is_game_active()
    @is_player_turn(attacker=True)
    async def play(self, ctx, *cards):
        """Play cards as the attacker."""
        await safe_delete_message(ctx.message)
        server = self.app.get_server(ctx.guild)
        player = server.get_player(ctx.author)
        
        # Validate channel
        if ctx.channel != player.channel:
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
        try:
            card_objects = [Card.from_string(card) for card in cards]
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
            
        except ValueError as e:
            await player.send_error(ctx, f"Invalid card format: {str(e)}")
    
    @commands.command(name='defend')
    @is_game_active()
    @is_player_turn(defender=True)
    async def defend(self, ctx, *cards):
        """Defend against attack cards."""
        await safe_delete_message(ctx.message)
        server = self.app.get_server(ctx.guild)
        player = server.get_player(ctx.author)
        
        # Validate channel
        if ctx.channel != player.channel:
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
            card_objects = [Card.from_string(card) for card in cards]
            
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
            
        except ValueError as e:
            await player.send_error(ctx, f"Invalid card format: {str(e)}")
    
    @commands.command(name='take')
    @is_game_active()
    @is_player_turn(defender=True)
    async def take(self, ctx):
        """Take all cards from the table as the defender."""
        await safe_delete_message(ctx.message)
        server = self.app.get_server(ctx.guild)
        player = server.get_player(ctx.author)
        
        # Validate channel
        if ctx.channel != player.channel:
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
        await self.end_turn(server, turn_taken=True)
    
    @commands.command(name='giveup')
    @is_game_active()
    @is_player_turn(attacker=True)
    async def giveup(self, ctx):
        """End your attack and pass the turn."""
        await safe_delete_message(ctx.message)
        server = self.app.get_server(ctx.guild)
        player = server.get_player(ctx.author)
        
        # Validate channel
        if ctx.channel != player.channel:
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
        await self.end_turn(server, turn_taken=False)
    
    async def end_turn(self, server: Server, turn_taken: bool):
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
        update_tasks = []
        for p in server.players.values():
            update_tasks.append(lambda p=p: p.attacker_message.edit(content=
                f'Attacker: ***{server.attacker.author.display_name}***\n'
                f'Defender: ***{server.defender.author.display_name}***'
            ))
        
        await batch_discord_operations(update_tasks)
        
        # Refill hands
        await server.refill_hands()
        
        # Check win condition
        if len(server.players) == 1:
            durak = list(server.players.values())[0]
            
            # Notify finished players
            notification_tasks = []
            for fin_author in server.finished_players:
                notification_tasks.append(
                    lambda author=fin_author: safe_send_message(
                        author, f"Game over! ***{durak.author.display_name}*** is the Durak!"
                    )
                )
            
            await batch_discord_operations(notification_tasks)
            
            # Grant "Ultimate Durak" role
            try:
                guild = durak.channel.guild
                durak_role = discord.utils.get(guild.roles, name="Ultimate Durak")
                if not durak_role:
                    durak_role = await guild.create_role(name="Ultimate Durak", colour=discord.Colour.dark_red())
                
                await durak.author.add_roles(durak_role)
            except discord.errors.Forbidden:
                logger.error(f"No permission to create/assign 'Ultimate Durak' role")
            
            server.state = GameState.FINISHED
            return
        
        # Replace trump card if it's taken
        if server.trump_card and server.trump_card not in server.deck:
            # Keep only the suit information
            server.trump_card = Card(server.trump_card.rank, server.trump_card.suit)
            server.trump_taken = True
        
        # Update all displays
        update_tasks = []
        for player in server.players:
            update_tasks.append(lambda p=player: server.update_hand(p))
        
        update_tasks.append(lambda: server.update_table())
        await batch_discord_operations(update_tasks)
        
        # Attacker gets a tip to start turn
        await server.attacker.send_tip(
            f'Your turn! Type /play <card(s)> to play or /giveup to end your attack.'
        )
    
    @commands.command(name='deleteall')
    @commands.has_permissions(administrator=True)
    async def delete_all(self, ctx):
        """Delete all Durak game channels and roles (admin only)."""
        guild = ctx.guild
        
        # Delete roles
        roles_to_delete = [role for role in guild.roles if role.name.startswith("durak")]
        for role in roles_to_delete:
            try:
                await role.delete()
                await safe_send_message(ctx.channel, f'Deleted role: {role.name}')
            except discord.errors.Forbidden:
                await safe_send_message(ctx.channel, f'No permission to delete role: {role.name}')
        
        # Delete channels
        channels_to_delete = [channel for channel in guild.text_channels if channel.name.startswith("durak")]
        for channel in channels_to_delete:
            try:
                await channel.delete()
                await safe_send_message(ctx.channel, f'Deleted channel: {channel.name}')
            except discord.errors.Forbidden:
                await safe_send_message(ctx.channel, f'No permission to delete channel: {channel.name}')
    
    @commands.command(name='help_durak')
    async def help_durak(self, ctx):
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
    
    # Error handlers
    @play.error
    @defend.error
    @take.error
    @giveup.error
    async def game_command_error(self, ctx, error):
        """Handle errors from game commands."""
        if isinstance(error, commands.CheckFailure):
            await safe_send_message(ctx.channel, str(error))
        else:
            logger.error(f"Command error: {str(error)}")
            await safe_send_message(ctx.channel, "An error occurred while processing your command.")
    
    @delete_all.error
    async def delete_all_error(self, ctx, error):
        """Handle errors from the delete_all command."""
        if isinstance(error, commands.MissingPermissions):
            await safe_send_message(ctx.channel, "You need administrator permissions to use this command.")
        else:
            logger.error(f"Command error: {str(error)}")
            await safe_send_message(ctx.channel, "An error occurred while processing your command.")


def setup(bot):
    """Add the DurakGame cog to the bot."""
    bot.add_cog(DurakGame(bot))