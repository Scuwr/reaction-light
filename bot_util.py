"""
MIT License

Copyright (c) 2019-2021 Scuwr

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import os
import configparser
from sys import platform

import discord
from discord.ext import commands

from core import database, migration, activity, schema

directory = os.path.dirname(os.path.realpath(__file__))

migrated = migration.migrate()
config_migrated = migration.migrateconfig()

with open(f"{directory}/.version") as f:
    __version__ = f.read().rstrip("\n").rstrip("\r")

folder = f"{directory}/files"
config = configparser.ConfigParser()
config.read(f"{directory}/config.ini")
logo = str(config.get("server", "logo"))
TOKEN = str(config.get("server", "token"))
botname = str(config.get("server", "name"))
prefix = str(config.get("server", "prefix"))
botcolour = discord.Colour(int(config.get("server", "colour"), 16))
system_channel = (
    int(config.get("server", "system_channel"))
    if config.get("server", "system_channel")
    else None
)

activities_file = f"{directory}/files/activities.csv"
activities = activity.Activities(activities_file)
db_file = f"{directory}/files/reactionlight.db"
db = database.Database(db_file)

intents = discord.Intents.default()
intents.members = True
intents.reactions = True
intents.messages = True
intents.emojis = True

class BotSingleton:
    __instance = None
    __botInfo = None

    @staticmethod
    def get_instance():
        if BotSingleton.__instance is None:
            BotSingleton()
        return BotSingleton.__instance

    def __init__(self):
        if BotSingleton.__instance is not None:
            raise Exception("This class is a singleton! Only one refernce can exist.")
        else:
            BotSingleton.__instance = self
            BotSingleton.__botInfo = commands.Bot(command_prefix=prefix, intents=intents)

    def get_bot_info(self):
        return BotSingleton.__botInfo


def get_bot():
    return BotSingleton.get_instance().get_bot_info()


bot = get_bot()


def isadmin(member, guild_id):
    # Checks if command author has an admin role that was added with rl!admin
    admins = db.get_admins(guild_id)

    if isinstance(admins, Exception):
        print(f"Error when checking if the member is an admin:\n{admins}")
        return False

    try:
        member_roles = [role.id for role in member.roles]
        return [admin_role for admin_role in admins if admin_role in member_roles]

    except AttributeError:
        # Error raised from 'fake' users, such as webhooks
        return False


async def getchannel(id):
    channel = bot.get_channel(id)

    if not channel:
        channel = await bot.fetch_channel(id)

    return channel


async def getguild(id):
    guild = bot.get_guild(id)

    if not guild:
        guild = await bot.fetch_guild(id)

    return guild


async def getuser(id):
    user = bot.get_user(id)

    if not user:
        user = await bot.fetch_user(id)

    return user


def restart():
    # Create a new python process of bot.py and stops the current one
    os.chdir(directory)
    python = "python" if platform == "win32" else "python3"
    cmd = os.popen(f"nohup {python} bot.py &")
    cmd.close()


async def database_updates():
    handler = schema.SchemaHandler(db_file)
    if handler.version == 0:
        handler.update()
        messages = db.fetch_all_messages()
        for message in messages:
            channel_id = message[1]
            channel = await getchannel(channel_id)
            db.add_guild(channel.id, channel.guild.id)


async def system_notification(guild_id, text):
    # Send a message to the system channel (if set)
    if guild_id:
        server_channel = db.fetch_systemchannel(guild_id)

        if isinstance(server_channel, Exception):
            await system_notification(
                None,
                "Database error when fetching guild system"
                f" channels:\n```\n{server_channel}\n```\n\n{text}",
            )
            return

        if server_channel:
            try:
                target_channel = await getchannel(server_channel[0][0])
                await target_channel.send(text)

            except discord.Forbidden:
                await system_notification(None, text)

        else:
            await system_notification(None, text)

    elif system_channel:
        try:
            target_channel = await getchannel(system_channel)
            await target_channel.send(text)

        except discord.NotFound:
            print("I cannot find the system channel.")

        except discord.Forbidden:
            print("I cannot send messages to the system channel.")

    else:
        print(text)


async def formatted_channel_list(channel):
    all_messages = db.fetch_messages(channel.id)
    if isinstance(all_messages, Exception):
        await system_notification(
            channel.guild.id,
            f"Database error when fetching messages:\n```\n{all_messages}\n```",
        )
        return

    formatted_list = []
    counter = 1
    for msg_id in all_messages:
        try:
            old_msg = await channel.fetch_message(int(msg_id))

        except discord.NotFound:
            # Skipping reaction-role messages that might have been deleted without updating CSVs
            continue

        except discord.Forbidden:
            await system_notification(
                channel.guild.id,
                "I do not have permissions to edit a reaction-role message"
                f" that I previously created.\n\nID: {msg_id} in"
                f" {channel.mention}",
            )
            continue

        entry = (
            f"`{counter}`"
            f" {old_msg.embeds[0].title if old_msg.embeds else old_msg.content}"
        )
        formatted_list.append(entry)
        counter += 1

    return formatted_list
