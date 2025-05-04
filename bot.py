import discord
from discord.ext import commands
import sys
import traceback

from config import DISCORD_TOKEN, COMMAND_PREFIX, logger

def main():
    """Initialize and run the Discord bot."""
    # Set up intents
    intents = discord.Intents.all()
    
    # Initialize bot
    bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
    
    # Load cogs
    try:
        bot.load_extension('commands')
        logger.info("Successfully loaded commands extension")
    except Exception as e:
        logger.error(f"Failed to load extension: {e}")
        traceback.print_exc()
    
    # Error handling for command errors
    @bot.event
    async def on_command_error(ctx, error):
        """Global error handler for command errors."""
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to use this command.")
        else:
            logger.error(f"Unhandled command error: {error}")
            await ctx.send("An error occurred while processing your command.")
    
    # Run the bot
    try:
        logger.info("Starting bot...")
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        logger.critical("Invalid Discord token. Please check your .env file.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()