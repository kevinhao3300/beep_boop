import discord
import os
import random
# from replit import db
from keep_alive import keep_alive

# def update_db(k,v):
#   if k in db.keys():
#     db[k].append(v)
#   else:
#     db[k] = [v]

# def db_string():
#   ret = ''
#   for k in db.keys():
#     ret += f'{k}: {db[k]}\n'
#   return ret

# def clear_db():
#   for k in db.keys():
#     del db[k]
    
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

start_msg_id = None
guild_to_teams = {}

MAPS = ['Bind', 'Split', 'Haven', 'Icebox', 'Ascent']


@client.event
async def on_ready():
    print('Logged in as {0.user}'.format(client))
    

@client.event
async def on_message(message):
    global start_msg_id
    
    # ignore your own messages
    if message.author == client:
        return

    if message.content.startswith('$help'):
        output_string = "Available Commands:\n"
        output_string += "\t$start - start matchmaking process\n"
        output_string += "\t$make - create teams from people who reacted to the $start message\n"
        output_string += "\t$move - move players to generated teams' voice channels\n"
        output_string += "\t$help - list available commands"
        await message.channel.send(output_string)

    if message.content.startswith('$start'):
        start_msg = await message.channel.send("React to this message if you're playing :)")
        start_msg_id = start_msg.id
        guild_to_teams[message.guild.id] = {'attackers':[], 'defenders':[]}

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
            await message.channel.send("VALORANT category created.")
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
            await message.channel.send("Attacker voice channel created.")
        if defender_channel is None:
            defender_channel = await guild.create_voice_channel('defenders', category=valorant_category)
            await message.channel.send("Defender voice channel created.")
        # move members to right channel
        attackers = guild_to_teams[guild.id]['attackers']
        defenders = guild_to_teams[guild.id]['defenders']
        for attacker in attackers:
            member = guild.get_member(attacker)
            if member.voice is not None:
                await member.move_to(attacker_channel)
        for defender in defenders:
            member = guild.get_member(defender)
            if member.voice is not None:
                await member.move_to(defender_channel)
        await message.channel.send("Available players moved.")

    
    if message.content.startswith('$make'):
        # read reacts and make teams accordingly
        if start_msg_id is None:
            await message.channel.send('use $start before $make')
        else:
            # read reacts
            start_msg = await message.channel.fetch_message(start_msg_id)
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


keep_alive()
client.run(os.getenv('TOKEN'))