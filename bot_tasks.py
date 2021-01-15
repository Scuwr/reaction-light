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


import datetime

import discord
from discord.ext import tasks

from core import database, github

import bot_util as util

bot = util.get_bot()

activities = util.activities
db = database.Database(util.db_file)


@tasks.loop(seconds=30)
async def maintain_presence():
    # Loops through the activities specified in activities.csv
    activity = activities.get()
    await bot.change_presence(activity=discord.Game(name=activity))


@tasks.loop(hours=24)
async def updates():
    # Sends a reminder once a day if there are updates available
    new_version = github.check_for_updates(util.__version__)
    if new_version:
        await util.system_notification(
            None,
            f"An update is available. Download Reaction Light v{new_version} at"
            f" https://github.com/Scuwr/reaction-light or simply use `{prefix}update`"
            " (only works with git installations).\n\nYou can view what has changed"
            " here: <https://github.com/Scuwr/reaction-light/blob/master/CHANGELOG.md>",
        )


@tasks.loop(hours=24)
async def cleandb():
    # Cleans the database by deleting rows of reaction role messages that don't exist anymore
    messages = db.fetch_all_messages()
    guilds = db.fetch_all_guilds()
    # Get the cleanup queued guilds
    cleanup_guild_ids = db.fetch_cleanup_guilds(guild_ids_only=True)

    if isinstance(messages, Exception):
        await util.system_notification(
            None,
            "Database error when fetching messages during database"
            f" cleaning:\n```\n{messages}\n```",
        )
        return

    for message in messages:
        try:
            channel_id = message[1]
            channel = await bot.fetch_channel(channel_id)

            await channel.fetch_message(message[0])

        except discord.NotFound as e:
            # If unknown channel or unknown message
            if e.code == 10003 or e.code == 10008:
                delete = db.delete(message[0], message[3])

                if isinstance(delete, Exception):
                    await util.system_notification(
                        channel.guild.id,
                        "Database error when deleting messages during database"
                        f" cleaning:\n```\n{delete}\n```",
                    )
                    return

                await util.system_notification(
                    channel.guild.id,
                    "I deleted the database entries of a message that was removed."
                    f"\n\nID: {message} in {channel.mention}",
                )

        except discord.Forbidden:
            # If we can't fetch the channel due to the bot not being in the guild or permissions we usually cant mention it or get the guilds id using the channels object
            await util.system_notification(
                message[3],
                "I do not have access to a message I have created anymore. "
                "I cannot manage the roles of users reacting to it."
                f"\n\nID: {message[0]} in channel {message[1]}",
            )

    if isinstance(guilds, Exception):
        await util.system_notification(
            None,
            "Database error when fetching guilds during database"
            f" cleaning:\n```\n{guilds}\n```",
        )
        return

    for guild_id in guilds:
        try:
            await bot.fetch_guild(guild_id)
            if guild_id in cleanup_guild_ids:
                db.remove_cleanup_guild(guild_id)

        except discord.Forbidden:
            # If unknown guild
            if guild_id in cleanup_guild_ids:
                continue
            else:
                db.add_cleanup_guild(guild_id, round(datetime.datetime.utcnow().timestamp()))

    cleanup_guilds = db.fetch_cleanup_guilds()

    if isinstance(cleanup_guilds, Exception):
        await util.system_notification(
            None,
            "Database error when fetching cleanup guilds during"
            f" cleaning:\n```\n{cleanup_guilds}\n```",
        )
        return

    current_timestamp = round(datetime.datetime.utcnow().timestamp())
    for guild in cleanup_guilds:
        if int(guild[1]) - current_timestamp <= -86400:
            # The guild has been invalid / unreachable for more than 24 hrs, try one more fetch then give up and purge the guilds database entries
            try:
                await bot.fetch_guild(guild[0])
                db.remove_cleanup_guild(guild[0])
                continue

            except discord.Forbidden:
                delete = db.remove_guild(guild[0])
                delete2 = db.remove_cleanup_guild(guild[0])
                if isinstance(delete, Exception):
                    await util.system_notification(
                        None,
                        "Database error when deleting a guilds datebase entries during"
                        f" database cleaning:\n```\n{delete}\n```",
                    )
                    return

                elif isinstance(delete2, Exception):
                    await util.system_notification(
                        None,
                        "Database error when deleting a guilds datebase entries during"
                        f" database cleaning:\n```\n{delete2}\n```",
                    )
                    return


@tasks.loop(hours=6)
async def check_cleanup_queued_guilds():
    cleanup_guild_ids = db.fetch_cleanup_guilds(guild_ids_only=True)
    for guild_id in cleanup_guild_ids:
        try:
            await bot.fetch_guild(guild_id)
            db.remove_cleanup_guild(guild_id)

        except discord.Forbidden:
            continue