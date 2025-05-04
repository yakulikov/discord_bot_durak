import os
import logging
from enum import Enum
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN1')  # Using original name for compatibility
COMMAND_PREFIX = '/'

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

# Validate configuration
if not DISCORD_TOKEN:
    logger.error("No Discord token found. Please set the DISCORD_TOKEN1 environment variable.")
    raise ValueError("No Discord token found. Please set the DISCORD_TOKEN1 environment variable.")

# Game constants
class GameState(Enum):
    SETUP = 0
    PLAYING = 1
    FINISHED = 2

# Card constants
CARD_RANKS = {'6': 0, '7': 1, '8': 2, '9': 3, '10': 4, 'J': 5, 'Q': 6, 'K': 7, 'A': 8}
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']