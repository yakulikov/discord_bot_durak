import discord
import random
from typing import Dict, List, Set, Tuple, Optional, Union
from config import GameState, CARD_RANKS, CARD_SUITS, logger

class Card:
    """Represents a playing card with rank and suit."""
    
    def __init__(self, rank: str, suit: str):
        self.rank = rank
        self.suit = suit
    
    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit
    
    @classmethod
    def from_string(cls, card_str: str) -> 'Card':
        """Create a Card object from a string representation."""
        if len(card_str) < 3:
            raise ValueError(f"Invalid card string: {card_str}")
        rank = card_str[:-2]
        suit = card_str[-2:]
        return cls(rank, suit)
    
    @classmethod
    def create_deck(cls) -> List['Card']:
        """Create a standard deck of cards for Durak."""
        deck = []
        for number in range(6, 14):
            for suit in CARD_SUITS:
                label = str(number)
                if number == 10: label = 'J'
                elif number == 11: label = 'Q'
                elif number == 12: label = 'K'
                elif number == 13: label = 'A'
                deck.append(cls(label, suit))
        return deck


class Player:
    """Represents a player in the Durak game."""
    
    def __init__(self, author: discord.Member, player_number: int):
        self.author = author
        self.number = player_number
        self.channel = None
        self.hand: List[Card] = []
        self.cards_message = None
        self.attacker_message = None
        self.defender_message = None
        self.table_message = None
        self.error_message = None
        self.tip_message = None
    
    async def send_error(self, ctx, message: str) -> None:
        """Send an error message to the player, replacing any previous error message."""
        try:
            if self.error_message:
                await self.error_message.delete()
            self.error_message = await ctx.send(message)
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to send error message: {str(e)}")
    
    async def send_tip(self, message: str) -> None:
        """Send a tip message to the player, replacing any previous tip message."""
        try:
            if self.tip_message:
                await self.tip_message.delete()
            self.tip_message = await self.channel.send(message)
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to send tip message: {str(e)}")
    
    async def cleanup_messages(self) -> None:
        """Clean up temporary messages."""
        for msg in [self.tip_message, self.error_message]:
            if msg:
                try:
                    await msg.delete()
                except discord.errors.HTTPException:
                    pass
        self.tip_message = None
        self.error_message = None


class Server:
    """Represents a server (guild) with an active Durak game."""
    
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self.trump_taken = False
        self.state = GameState.SETUP
        self.players: Dict[discord.Member, Player] = {}
        self.deck: List[Card] = []
        self.trump_card: Optional[Card] = None
        self.table: List[Tuple[Card, Optional[Card]]] = []
        self.attacker: Optional[Player] = None
        self.defender: Optional[Player] = None
        self.finished_players: Set[discord.Member] = set()  # authors who completed the game
    
    def get_player(self, author: discord.Member) -> Optional[Player]:
        """Get a player by their Discord member object."""
        return self.players.get(author)
    
    def add_player(self, author: discord.Member) -> Player:
        """Add a new player to the game."""
        if author in self.players:
            return self.players[author]
        
        player = Player(author, len(self.players) + 1)
        self.players[author] = player
        return player
    
    def cards_are_in_hand(self, player: Player, card_strings: List[str]) -> bool:
        """Check if all specified cards are in the player's hand."""
        hand_strings = [str(card) for card in player.hand]
        return all(card in hand_strings for card in card_strings)
    
    def is_defence_success(self, attacking_card: Card, defending_card: Card) -> bool:
        """Determine if a defense is successful according to Durak rules."""
        if attacking_card.suit == self.trump_card.suit and defending_card.suit != self.trump_card.suit:
            return False
        elif attacking_card.suit != self.trump_card.suit and defending_card.suit == self.trump_card.suit:
            return True
        elif defending_card.suit == attacking_card.suit:
            return CARD_RANKS[attacking_card.rank] < CARD_RANKS[defending_card.rank]
        else:
            return False
    
    async def update_table(self) -> None:
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
            except discord.errors.HTTPException as e:
                logger.error(f"Failed to update table: {str(e)}")
    
    async def update_hand(self, player: discord.Member) -> None:
        """Update the hand display for a specific player."""
        cards = ' '.join([f' {card}' for card in self.players[player].hand])
        
        try:
            await self.players[player].cards_message.edit(
                content=f'Here are your cards: ```{cards}```'
            )
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to update hand: {str(e)}")
    
    async def refill_hands(self) -> None:
        """Refill all players' hands to 6 cards if possible."""
        players_by_number = sorted(self.players.values(), key=lambda p: p.number)
        start_index = next((i for i, p in enumerate(players_by_number) if p == self.attacker), 0)
        
        # Refill hands
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
                except discord.errors.Forbidden:
                    logger.warning(f"No permission to remove role from {p.author.display_name}")
                except Exception as e:
                    logger.error(f"Error removing role: {str(e)}")
                
                eliminated.append(p)
        
        for p in eliminated:
            self.finished_players.add(p.author)
            try:
                await p.channel.send("🎉 You have finished all your cards!")
                await p.channel.delete()
            except discord.errors.Forbidden:
                logger.warning(f"No permission to delete channel for {p.author.display_name}")
            except Exception as e:
                logger.error(f"Error deleting channel: {str(e)}")
            
            try:
                role = discord.utils.get(p.channel.guild.roles, name=f"durak {p.number}")
                if role:
                    await role.delete()
            except discord.errors.Forbidden:
                logger.warning(f"No permission to delete role for {p.author.display_name}")
            except Exception as e:
                logger.error(f"Error deleting role: {str(e)}")
            
            del self.players[p.author]
    
    def initialize_deck(self) -> None:
        """Initialize and shuffle the deck of cards."""
        self.deck = Card.create_deck()
        random.shuffle(self.deck)
        self.trump_card = self.deck[-1]


class Application:
    """Main application class that manages all server instances."""
    
    def __init__(self):
        self.servers: Dict[int, Server] = {}
    
    def get_server(self, guild: discord.Guild) -> Server:
        """Get or create a Server instance for a Discord guild."""
        if guild.id not in self.servers:
            self.servers[guild.id] = Server(guild.id, guild.name)
        return self.servers[guild.id]