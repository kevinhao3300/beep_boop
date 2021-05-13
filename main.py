import discord
import os
import random
from replit import db
from keep_alive import keep_alive
import trueskill as ts
import logging

# set up logging
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

def db_string():
  ret = ''
  for k in db.keys():
    ret += f'db[{k}] = {db[k]}\n'
    print(type(db[k][0]))
  return ret

def clear_db():
  for k in db.keys():
    del db[k]

# global userid lists
ADMINS = [335828416412778496, 263745246821744640]

# discord py client
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

# dicts for guild-local variables
guild_to_start_msg = {}
guild_to_teams = {}

# VALORANT maps
MAPS = ['Bind', 'Split', 'Haven', 'Iceb <:OMEGALUL:821118232614273105> x', 'Ascent', 'Breeze']

# TrueSkill Rating Settings
env = ts.TrueSkill(draw_probability=0.05)
env.make_as_global()

# TrueSkill DB cache
ratings_cache = {}

# TrueSkill DB helper functions
def get_skill(userid):
    '''
    Returns the TrueSkill rating of a discord user.
    Will initialize skill if none is found.
    :param userid: Discord userid to find
    :return: stored TrueSkill rating object of userid
    '''
    userid = int(userid)
    # check cache first
    if userid in ratings_cache:
        return ratings_cache[userid]
    print('Cache Miss: userid =', userid)
    if userid in db.keys():
        mu, sigma = db[userid]
        return ts.Rating(float(mu), float(sigma))
    new_rating = ts.Rating()
    db[userid] = new_rating.mu, new_rating.sigma
    ratings_cache[userid] = new_rating
    return new_rating

def record_result(winning_team, losing_team):
    '''
    Updates the TrueSkill ratings given a result.
    :param winning_team: list of userids of players on the winning team
    :param losing_team: list of userids of players on the losing team
    :return: old winning team ratings, old losing team ratings, new winning team ratings, new losing team ratings
    '''
    winning_team_ratings = {id : get_skill(id) for id in winning_team}
    losing_team_ratings = {id : get_skill(id) for id in losing_team}
    winning_team_ratings_new, losing_team_ratings_new = ts.rate([winning_team_ratings, losing_team_ratings], [0,1])
    for id in winning_team_ratings:
        ratings_cache[id] = winning_team_ratings_new[id]
        db[id] = winning_team_ratings_new[id].mu, winning_team_ratings_new[id].sigma
    for id in losing_team_ratings:
        ratings_cache[id] = losing_team_ratings_new[id]
        db[id] = losing_team_ratings_new[id].mu, losing_team_ratings_new[id].sigma
    return winning_team_ratings, losing_team_ratings, winning_team_ratings_new, losing_team_ratings_new

def make_teams(players, pool=10):
    '''
    Make teams based on rating.
    :param players: list of userid of participating players
    :param pool: number of matches to generate from which the best is chosen
    :return: attackers (list of userids), defenders (list of userids), predicted quality of match
    '''
    player_ratings = {id : get_skill(id) for id in players}
    attackers = defenders = []
    best_quality = 0.0
    for i in range(pool):
        random.shuffle(players)
        team_size = len(players) // 2
        t1 = {id : player_ratings[id] for id in players[:team_size]}
        t2 = {id : player_ratings[id] for id in players[team_size:]}
        quality = ts.quality([t1, t2])
        if quality > best_quality:
            attackers = list(t1.keys())
            defenders = list(t2.keys())
            best_quality = quality
    return attackers, defenders, best_quality

def get_leaderboard():
    '''
    Gets list of userids and TrueSkill ratings, sorted by current rating
    :return: list of (userid, TrueSkill.Rating) tuples, sorted by rating
    '''
    ratings = {id : get_skill(id) for id in db.keys()}
    return sorted(ratings.items(), key=lambda x: (x[1].mu, -x[1].sigma), reverse=True)


@client.event
async def on_ready():
    global ratings_cache
    ratings_cache = {id : get_skill(id) for id in db.keys()}
    print('Logged in as {0.user}'.format(client))

@client.event
async def on_raw_reaction_add(payload):
    # update start message with reactors
    if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
        channel = client.get_channel(payload.channel_id)
        start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players] )
        await start_msg.edit(content=output_message)

@client.event
async def on_raw_reaction_remove(payload):
    # update start message with reactors
    if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
        channel = client.get_channel(payload.channel_id)
        start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players])
        await start_msg.edit(content=output_message)

@client.event
async def on_voice_state_update(member, before, after):
    '''
    Clean up created voice channels if they're empty.
    (could be less janky if we kept track of the created voice channels explicitly)
    '''
    if before.channel == None or before.channel.category == None or before.channel.category.name.lower() != 'valorant':
        return
    guild = before.channel.guild
    attackers_vc = defenders_vc = None
    # find channels
    for vc in guild.voice_channels:
        if vc.category == None or vc.category.name.lower() != 'valorant':
            continue
        if vc.name.lower() == 'attackers':
            attackers_vc = vc
        elif vc.name.lower() == 'defenders':
            defenders_vc = vc
    # delete VALORANT channels if they're empty
    if attackers_vc is not None and defenders_vc is not None:
        if len(attackers_vc.members) == len(defenders_vc.members) == 0:
            await attackers_vc.delete()
            await defenders_vc.delete()
            for category in guild.categories:
                if category.name.lower() == 'valorant':
                    await category.delete()

@client.event
async def on_message(message):
    
    # ignore your own messages
    if message.author == client:
        return

    if message.content.startswith('$help'):
        output_string = "**Available Commands:**\n"
        output_string += "\t**$start** - start matchmaking process, bot sends message for players to react to\n"
        output_string += "\t\t**$make** - create random teams from reactions to $start message\n"
        output_string += "\t\t**$rated** - create teams based on MMR\n"
        output_string += "\t\t\t**$attackers** - record a win for the attackers\n"
        output_string += "\t\t\t**$defenders** - record a win for the defenders\n"
        output_string += "\t\t**$move** - move players to generated teams' voice channels\n"
        output_string += "\t\t**$back** - move all players into attacker voice channel\n"
        output_string += "\t**$rating** - get your current rating\n"
        output_string += "\t**$leaderboard** - get players sorted by rating\n"
        output_string += "\t**$clean** - reset players and remove created voice channels\n"
        output_string += "\t**$help** - list available commands"
        await message.channel.send(output_string)

    if message.content.startswith('$start'):
        start_msg = await message.channel.send("React to this message if you're playing :)")
        guild_to_start_msg[message.guild.id] = start_msg
        # guild_to_teams[message.guild.id] = {'attackers':[], 'defenders':[]}

    if message.content.startswith('$make'):
        # read reacts and make teams accordingly
        if message.guild.id not in guild_to_start_msg or guild_to_start_msg[message.guild.id] is None:
            await message.channel.send('use $start before $make')
        else:
            # read reacts
            guild_to_teams[message.guild.id] = {'attackers':[], 'defenders':[]}
            start_msg = await message.channel.fetch_message(guild_to_start_msg[message.guild.id].id)
            players = set()
            for reaction in start_msg.reactions:
                users = await reaction.users().flatten()
                players.update((user.id for user in users))
            # create teams
            players = list(players)
            random.shuffle(players)
            team_size = len(players) // 2
            attackers = players[:team_size]
            defenders = players[team_size:]
            # create output
            output_string = f"Map: {random.choice(MAPS)}\n" 
            output_string += "\nAttackers:\n"
            for member in attackers:
                output_string += f'\t<@!{member}>'
            output_string += "\n\nDefenders:\n"
            for member in defenders:
                output_string += f'\t<@!{member}>'
            # store teams
            guild_to_teams[message.guild.id]['attackers'] = attackers
            guild_to_teams[message.guild.id]['defenders'] = defenders
            # send output
            await message.channel.send(output_string)
    
    if message.content.startswith('$rated'):
        if message.guild.id not in guild_to_start_msg or guild_to_start_msg[message.guild.id] is None:
            await message.channel.send('use *$start* before *$rated*')
        else:
            # read reacts
            guild_to_teams[message.guild.id] = {'attackers':[], 'defenders':[]}
            start_msg = await message.channel.fetch_message(guild_to_start_msg[message.guild.id].id)
            players = set()
            for reaction in start_msg.reactions:
                users = await reaction.users().flatten()
                players.update((user.id for user in users))
            # must have at least one member on each team
            if len(players) < 2:
                await message.channel.send('must have **at least 2 players** for rated game')
                return
            # create teams
            attackers, defenders, quality = make_teams(list(players))
            # create output
            output_string = f'Map: {random.choice(MAPS)}    Predicted Quality: {round(quality*200, 2)}\n'
            output_string += "\nAttackers:\n"
            for member in attackers:
                output_string += f'\t<@!{member}>({round(get_skill(member).mu, 2)}) '
            output_string += "\n\nDefenders:\n"
            for member in defenders:
                output_string += f'\t<@!{member}>({round(get_skill(member).mu, 2)}) '
            # store teams
            guild_to_teams[message.guild.id]['attackers'] = attackers
            guild_to_teams[message.guild.id]['defenders'] = defenders
            # send output
            await message.channel.send(output_string)
    
    if message.content.startswith('$attackers'):
        if not guild_to_teams[message.guild.id]['attackers']:
            await message.channel.send('use *$make* or *$rated* before recording a result')
        else:
            attackers, defenders, attackers_new, defenders_new = record_result(guild_to_teams[message.guild.id]['attackers'], guild_to_teams[message.guild.id]['defenders'])
            output_string = '**Win for** ***Attackers*** **recorded.**\n'
            output_string += "\n**Attackers:**\n"
            for member in attackers:
                output_string += f'\t<@!{member}> ({round(attackers[member].mu, 2)} -> {round(attackers_new[member].mu, 2)})\n'
            output_string += "\n\n**Defenders:**\n"
            for member in defenders:
                output_string += f'\t<@!{member}> ({round(defenders[member].mu, 2)} -> {round(defenders_new[member].mu, 2)})\n'
            # send output
            await message.channel.send(output_string)
    
    if message.content.startswith('$defenders'):
        if not guild_to_teams[message.guild.id]['defenders']:
            await message.channel.send('use *$make* or *$rated* before recording a result')
        else:
            defenders, attackers, defenders_new, attackers_new = record_result(guild_to_teams[message.guild.id]['defenders'], guild_to_teams[message.guild.id]['attackers'])
            output_string = '**Win for** ***Defenders*** **recorded.**\n'
            output_string += "\n**Attackers:**\n"
            for member in attackers:
                output_string += f'\t<@!{member}> ({round(attackers[member].mu, 2)} -> {round(attackers_new[member].mu, 2)})\n'
            output_string += "\n\n**Defenders:**\n"
            for member in defenders:
                output_string += f'\t<@!{member}> ({round(defenders[member].mu, 2)} -> {round(defenders_new[member].mu, 2)})\n'
            # send output
            await message.channel.send(output_string)

    if message.content.startswith('$leaderboard'):
        leaderboard = get_leaderboard()
        output_string = ''
        rank = 0
        last = 0, 0, 0    # mu, sigma, rank
        for item in leaderboard:
            member = message.guild.get_member(int(item[0]))
            if member:
                rank += 1
                if (item[1].mu, item[1].sigma) == last[:2]:
                    output_string += f'**{last[2]}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)}\n'
                else:
                    output_string += f'**{rank}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)}\n'
                last = item[1].mu, item[1].sigma, rank
        await message.channel.send(output_string)
    
    if message.content.startswith('$move'):
        if message.guild.id not in guild_to_teams:
            await message.channel.send("Use $start to begin matchmaking.")
            return
        guild = message.guild
        # find attacker and defender voice channels
        attacker_channel, defender_channel = None, None
        # check if Valorant channel category exists
        valorant_category = None
        for category in guild.categories:
            if category.name.lower() == 'valorant':
                valorant_category = category
        if valorant_category is None:
            # make it
            valorant_category = await guild.create_category_channel('VALORANT')
            # await message.channel.send("VALORANT category created.")
        for vc in guild.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category != valorant_category:
                continue
            if vc.name.lower() == 'attackers':
                attacker_channel = vc
            elif vc.name.lower() == 'defenders':
                defender_channel = vc
        # create vc if necessary
        if attacker_channel is None:
            attacker_channel = await guild.create_voice_channel('attackers', category=valorant_category)
            # await message.channel.send("Attacker voice channel created.")
        if defender_channel is None:
            defender_channel = await guild.create_voice_channel('defenders', category=valorant_category)
            # await message.channel.send("Defender voice channel created.")
        # move members to right channel
        attackers = guild_to_teams[guild.id]['attackers']
        defenders = guild_to_teams[guild.id]['defenders']
        count = 0
        for attacker in attackers:
            member = guild.get_member(attacker)
            if member.voice is not None:
                count += 1
                await member.move_to(attacker_channel)
        for defender in defenders:
            member = guild.get_member(defender)
            if member.voice is not None:
                count += 1
                await member.move_to(defender_channel)
        await message.channel.send(f"{count} player{'s' if count > 1 else ''} moved.")
    
    if message.content.startswith('$back'):
        # find VALORANT voice channels
        guild = message.guild
        for vc in guild.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category is not None and vc.category.name.lower() != 'valorant':
                continue
            elif vc.name.lower() == 'defenders':
                for vc2 in guild.voice_channels:
                    if vc2.name.lower() == 'attackers':
                        for defender in vc.members:
                            await defender.move_to(vc2)
                        await message.channel.send('✅')

    if message.content.startswith('$rating'):
        if message.raw_mentions:
            for id in message.raw_mentions:
                skill = get_skill(id)
                await message.channel.send(f'\t<@!{id}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}\n')
        else:
            authorid = message.author.id
            skill = get_skill(authorid)
            await message.channel.send(f'\t<@!{authorid}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}')

    # remove valorant category and voice channels
    if message.content.startswith('$clean'):
        # find VALORANT voice channels
        guild = message.guild
        for vc in guild.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category is not None and vc.category.name.lower() != 'valorant':
                continue
            if vc.name.lower() == 'attackers':
                await vc.delete()
                await message.channel.send('Attacker voice channel deleted.')
            elif vc.name.lower() == 'defenders':
                await vc.delete()
                await message.channel.send('Defender voice channel deleted.')
        # delete VALORANT category
        for category in guild.categories:
            if category.name.lower() == 'valorant':
                await category.delete()
                await message.channel.send('VALORANT category deleted.')
        guild_to_teams[message.guild.id] = {'attackers':[], 'defenders':[]}
        await message.channel.send('Players emptied.')
    
    # admin-only clearing of repl db
    if message.content.startswith('$cleardb'):
        if message.author.id in ADMINS:
            clear_db()
            await message.channel.send('Database cleared.')
        else:
            await message.channel.send('Permission denied.')

keep_alive()
client.run(os.getenv('TOKEN'))