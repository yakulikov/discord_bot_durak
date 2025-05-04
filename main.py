import discord
from discord.ext import commands
import random
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN1')

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
        self.game_setup = False
        self.game = False
        self.players = {}
        self.deck = []
        self.trump_card = None
        self.table = []
        self.attacker = None
        self.defender = None
        self.finished_players = set()  # authors who completed the game
        self.card_ranks = {'6': 0, '7': 1, '8': 2, '9': 3, '10': 4, 'J': 5, 'Q': 6, 'K': 7, 'A': 8}

    async def update_table(self):
        for player in self.players:
            content = []
            for a, d in self.table:
                if d:
                    content.append(f"{a[0]}{a[1]}<-{d[0]}{d[1]}")
                else:
                    content.append(f"{a[0]}{a[1]}")

            if self.trump_card:
                trump_str = f"{self.trump_card[1]}" if self.trump_taken else f"{self.trump_card[0]}{self.trump_card[1]}"
            else:
                trump_str = "?"

            deck_status = f"Deck: {len(self.deck)} cards | Trump: {trump_str}"
            table_str = "     ".join(content) if content else "(empty)"
            await self.players[player].table_message.edit(
                content=f'Table: ```{table_str}\n{deck_status}```'
            )

    async def update_hand(self, player):
        cards = ' '.join([f' {card[0]}{card[1]}' for card in self.players[player].hand])

        await self.players[player].cards_message.edit(content=f'Here are your cards: ```{cards}```')

    def cards_are_in_hand(self, player, cards):
        hand_strings = [f"{card[0]}{card[1]}" for card in player.hand]
        return all(card in hand_strings for card in cards)

    async def refill_hands(self):
        players_by_number = sorted(self.players.values(), key=lambda p: p.number)
        start_index = next(i for i, p in enumerate(players_by_number) if p == self.attacker)

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
                durak_role = discord.utils.get(p.channel.guild.roles, name="Ultimate Durak")
                if durak_role in p.author.roles:
                    await p.author.remove_roles(durak_role)

                eliminated.append(p)

        for p in eliminated:
            self.finished_players.add(p.author)
            await p.channel.send("🎉 You have finished all your cards!")
            try:
                await p.channel.delete()
            except:
                pass
            role = discord.utils.get(p.channel.guild.roles, name=f"durak {p.number}")
            if role:
                await role.delete()
            del self.players[p.author]

    def is_defence_success(self, attacking_card, defending_card):
        if attacking_card[1] == self.trump_card[1] and defending_card[1] != self.trump_card[1]:
            return False
        elif attacking_card[1] != self.trump_card[1] and defending_card[1] == self.trump_card[1]:
            return True
        elif defending_card[1] == attacking_card[1]:
            return self.card_ranks[attacking_card[0]] < self.card_ranks[defending_card[0]]
        else:
            return False


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

app = Application()

@client.event
async def on_ready():
    print('Bot is up and running')

@client.event
async def on_message(message):
    if message.author == client.user or not message.guild:
        return

    server = app.get_server(message.guild)

    if message.content.startswith('/durak'):
        await message.delete()
        await message.channel.send("Type /join to join the game.")
        server.game_setup = True
        server.game = False
        server.players = {}

    elif server.game_setup and message.content.startswith('/join'):
        if message.author not in server.players:
            server.players[message.author] = Player(message.author, len(server.players) + 1)
            await message.channel.send(f'{message.author.display_name} joined the game.')
            await message.delete()
        else:
            await message.channel.send(f'{message.author.display_name} is already in the game.')

    await client.process_commands(message)

@client.command(name='start')
async def start_game(ctx):
    server = app.get_server(ctx.guild)
    await ctx.message.delete()

    if not server.game_setup or len(server.players) < 2:
        await ctx.send("Not enough players or game not set up.")
        return

    server.game_setup = False
    server.deck = []
    server.attacker = None
    lowest_trump = None

    for number in range(6, 14):
        for suit in ['♥️', '♦️', '♣️', '♠️']:
            label = str(number)
            if number == 10: label = 'J'
            elif number == 11: label = 'Q'
            elif number == 12: label = 'K'
            elif number == 13: label = 'A'
            server.deck.append((label, suit))

    random.shuffle(server.deck)
    server.trump_card = server.deck[-1]

    for player in server.players:
        role_name = f'durak {server.players[player].number}'
        role = await ctx.guild.create_role(name=role_name, colour=discord.Colour.random())
        await player.add_roles(role)

        channel_name = f'durak-{player.display_name}-room'.lower().replace(' ', '-')
        channel = await ctx.guild.create_text_channel(channel_name)
        await channel.set_permissions(role, send_messages=True, read_messages=True)
        await channel.set_permissions(ctx.guild.default_role, read_messages=False)

        p = server.players[player]
        p.channel = channel
        p.hand = [server.deck.pop(0) for _ in range(6)]

        cards = ' '.join([f'{card[0]}{card[1]}' for card in p.hand])
        await channel.send(f'players in the game: {", ".join([player.display_name for player in server.players])}.')
        p.cards_message = await channel.send(f'Here are your cards: ```{cards}```')

        for card in p.hand:
            if card[1] == server.trump_card[1]:
                if lowest_trump is None or server.card_ranks[card[0]] < server.card_ranks[lowest_trump]:
                    lowest_trump = card[0]
                    server.attacker = p

    if server.attacker is None:
        server.attacker = list(server.players.values())[0]

    players_by_number = sorted(server.players.values(), key=lambda p: p.number)
    attacker_index = next(i for i, p in enumerate(players_by_number) if p == server.attacker)
    defender_index = (attacker_index + 1) % len(players_by_number)
    server.defender = players_by_number[defender_index]

    for player in server.players:
        p = server.players[player]
        msg = await p.channel.send(
            f'Attacker: ***{server.attacker.author.display_name}***\n'
            f'Defender: ***{server.defender.author.display_name}***'
        )
        p.attacker_message = msg  # this will be edited later

        p.table_message = await p.channel.send('Table: ```(empty)\nDeck: loading...```')

    await server.update_table()

    server.attacker.tip_message = await server.attacker.channel.send(f'Your turn! Type /play <card(s)> to play, /giveup to end your attack.')

    await ctx.send("Game started, roles and channels created.")
    server.game = True

@client.command(name='play')
async def play(ctx, *cards):
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    if not server.game:
        return

    if ctx.author != server.attacker.author or ctx.channel != server.attacker.channel:
        return

    if not server.cards_are_in_hand(server.attacker, cards):
        if server.attacker.error_message:
            await server.attacker.error_message.delete()
        server.attacker.error_message = await ctx.send("You do not have these cards.")
        return

    card_value = cards[0][:-2]
    if any(card[:-2] != card_value for card in cards):
        if server.attacker.error_message:
            await server.attacker.error_message.delete()
        server.attacker.error_message = await ctx.send("You can only play cards of the same value.")
        return

    if server.table:
        allowed_values = {atk[0] for atk, dfn in server.table}
        allowed_values.update(dfn[0] for atk, dfn in server.table if dfn is not None)
        if not all(card[:-2] in allowed_values for card in cards):
            if server.attacker.error_message:
                await server.attacker.error_message.delete()
            server.attacker.error_message = await ctx.send(
                "You can only play cards that match the rank of any card on the table."
            )
            return

    for card in cards:
        card_tuple = (card[:-2], card[-2:])
        server.attacker.hand.remove(card_tuple)
        server.table.append((card_tuple, None))

    if server.defender.tip_message is not None:
        await server.defender.tip_message.delete()

    server.defender.tip_message = await server.defender.channel.send(
        "Type /defend <card(s)> to defend or /take to take the cards.")

    # If all cards have been defended, enable /giveup tip
    if all(d is not None for _, d in server.table):
        if server.attacker.tip_message:
            await server.attacker.tip_message.delete()
        server.attacker.tip_message = await server.attacker.channel.send(
            f'Your turn! Type /play <card(s)> to continue the attack or /giveup to end your attack.'
        )

    await server.update_hand(ctx.author)
    await server.update_table()

@client.command(name='defend')
async def defend(ctx, *cards):
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    if not server.game:
        return

    if ctx.author != server.defender.author or ctx.channel != server.defender.channel or not server.table:
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You cannot take at this time.")
        return

    if all(def_card is not None for _, def_card in server.table):
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You already defended all cards. You cannot take now.")
        return

    if all(def_card is not None for _, def_card in server.table):
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You already defended all cards. You cannot take now.")
        return

        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You cannot defend at this time.")
        return

    if not server.cards_are_in_hand(server.defender, cards):
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You do not have these cards.")
        return

    undefended = [i for i, (_, d) in enumerate(server.table) if d is None]

    if len(cards) != len(undefended):
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You must defend all cards on the table.")
        return

    if not all(server.is_defence_success(server.table[i][0], (cards[j][:-2], cards[j][-2:])) for j, i in enumerate(undefended)):
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("These cards are not a valid defence.")
        return

    for j, i in enumerate(undefended):
        defense_tuple = (cards[j][:-2], cards[j][-2:])
        server.table[i] = (server.table[i][0], defense_tuple)
        server.defender.hand.remove(defense_tuple)

    await server.update_hand(ctx.author)
    await server.update_table()

async def end_turn(server: Server, turn_taken: bool):
    players_by_number = sorted(server.players.values(), key=lambda p: p.number)
    old_attacker = server.attacker
    old_defender = server.defender

    # Clean tip and error messages
    for p in server.players.values():
        # Delete previous tip/error messages
        for msg in [p.tip_message, p.error_message]:
            if msg:
                await msg.delete()
        p.tip_message = None
        p.error_message = None

        # Edit attacker message in-place
        new_attacker = None
        new_defender = None

        if turn_taken:
            # Defender took: attacker is next after defender
            def_index = next(i for i, p in enumerate(players_by_number) if p == server.defender)
            new_attacker = players_by_number[(def_index + 1) % len(players_by_number)]
        else:
            # Attackers gave up: defender becomes attacker
            new_attacker = server.defender

        new_defender_index = (players_by_number.index(new_attacker) + 1) % len(players_by_number)
        new_defender = players_by_number[new_defender_index]

        server.attacker = new_attacker
        server.defender = new_defender

        for p in server.players.values():
            await p.attacker_message.edit(content=
                                          f'Attacker: ***{server.attacker.author.display_name}***\n'
                                          f'Defender: ***{server.defender.author.display_name}***'
                                          )

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

    # Refill hands in correct order
    await server.refill_hands()

    # Win condition
    if len(server.players) == 1:
        durak = list(server.players.values())[0]
        for fin_author in server.finished_players:
            try:
                await fin_author.send(f"Game over! ***{durak.author.display_name}*** is the Durak!")
            except:
                pass
        # Grant "Ultimate Durak" role
        guild = durak.channel.guild
        durak_role = discord.utils.get(guild.roles, name="Ultimate Durak")
        if not durak_role:
            durak_role = await guild.create_role(name="Ultimate Durak", colour=discord.Colour.dark_red())

        await durak.author.add_roles(durak_role)
        return

    # Replace trump card if it’s taken
    if server.trump_card and server.trump_card not in server.deck:
        server.trump_card = (server.trump_card[1], '')  # symbol only, no value

    # Update all displays
    for player in server.players:
        await server.update_hand(player)
        await server.update_table()

    # Attacker gets a tip to start turn
    server.attacker.tip_message = await server.attacker.channel.send(
        f'Your turn! Type /play <card(s)> to play or /giveup to end your attack.'
    )


@client.command(name='take')
async def take(ctx):
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    if not server.game:
        return

    if ctx.author != server.defender.author or ctx.channel != server.defender.channel or not server.table:
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You cannot take at this time.")
        return

    if all(def_card is not None for _, def_card in server.table):
        if server.defender.error_message:
            await server.defender.error_message.delete()
        server.defender.error_message = await ctx.send("You already defended all cards. You cannot take now.")
        return

    for attack_card, defense_card in server.table:
        server.defender.hand.append(attack_card)
        if defense_card:
            server.defender.hand.append(defense_card)

    await end_turn(server, turn_taken=True)


@client.command(name='giveup')
async def giveup(ctx):
    await ctx.message.delete()
    server = app.get_server(ctx.guild)
    if not server.game:
        return
    if ctx.author != server.attacker.author or ctx.channel != server.attacker.channel:
        return

    if not server.table:
        if server.attacker.error_message:
            await server.attacker.error_message.delete()
        server.attacker.error_message = await ctx.send("You must play at least one card before you can give up.")
        return

    # Check if all cards have been defended
    if any(def_card is None for _, def_card in server.table):
        if server.attacker.error_message:
            await server.attacker.error_message.delete()
        server.attacker.error_message = await ctx.send("You can only give up after all your cards have been defended.")
        return

    await end_turn(server, turn_taken=False)


@client.command(name='deleteall')
async def delete_all(ctx):
    guild = ctx.guild
    roles_to_delete = [role for role in guild.roles if role.name.startswith("durak")]
    for role in roles_to_delete:
        await role.delete()
        await ctx.send(f'Deleted role: {role.name}')

    channels_to_delete = [channel for channel in guild.text_channels if channel.name.startswith("durak")]
    for channel in channels_to_delete:
        await channel.delete()
        await ctx.send(f'Deleted channel: {channel.name}')

client.run(token)
