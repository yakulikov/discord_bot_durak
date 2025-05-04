import discord
from discord.ext import commands
import asyncio
from typing import List, Callable, Any
from config import logger

async def batch_discord_operations(operations: List[Callable[[], Any]], chunk_size: int = 5) -> None:
    """
    Execute Discord API operations in batches to avoid rate limits.
    
    Args:
        operations: List of async callables to execute
        chunk_size: Number of operations to execute in parallel
    """
    for i in range(0, len(operations), chunk_size):
        chunk = operations[i:i+chunk_size]
        await asyncio.gather(*[op() for op in chunk], return_exceptions=True)

async def safe_delete_message(message) -> bool:
    """Safely delete a Discord message, handling exceptions."""
    if not message:
        return False
    
    try:
        await message.delete()
        return True
    except discord.errors.NotFound:
        # Message already deleted
        return True
    except discord.errors.Forbidden:
        logger.warning(f"No permission to delete message in {message.channel}")
        return False
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        return False

async def safe_send_message(channel, content=None, **kwargs) -> discord.Message:
    """Safely send a Discord message, handling exceptions."""
    try:
        return await channel.send(content, **kwargs)
    except discord.errors.Forbidden:
        logger.warning(f"No permission to send message to {channel}")
        return None
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return None

def is_game_active():
    """Check decorator to ensure a game is active."""
    async def predicate(ctx):
        from models import Application
        app = ctx.bot.get_cog('DurakGame').app
        server = app.get_server(ctx.guild)
        
        if server.state != GameState.PLAYING:
            raise commands.CheckFailure("No active game in this server")
        return True
    return commands.check(predicate)

def is_player_turn(attacker=False, defender=False):
    """Check decorator to ensure it's the player's turn."""
    async def predicate(ctx):
        from models import Application
        app = ctx.bot.get_cog('DurakGame').app
        server = app.get_server(ctx.guild)
        
        if server.state != GameState.PLAYING:
            raise commands.CheckFailure("No active game in this server")
        
        if attacker and ctx.author != server.attacker.author:
            raise commands.CheckFailure("It's not your turn to attack")
        
        if defender and ctx.author != server.defender.author:
            raise commands.CheckFailure("It's not your turn to defend")
        
        return True
    return commands.check(predicate)

def create_card_embed(title, player=None, cards=None, trump=None, deck_size=None):
    """Create a Discord embed for displaying card information."""
    embed = discord.Embed(title=title, color=discord.Color.blue())
    
    if player:
        embed.set_author(name=player.author.display_name, icon_url=player.author.avatar.url if player.author.avatar else None)
    
    if cards:
        card_str = ' '.join([str(card) for card in cards])
        embed.add_field(name="Cards", value=f"```{card_str}```", inline=False)
    
    if trump:
        embed.add_field(name="Trump", value=str(trump), inline=True)
    
    if deck_size is not None:
        embed.add_field(name="Deck", value=f"{deck_size} cards remaining", inline=True)
    
    return embed