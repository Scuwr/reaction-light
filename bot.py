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
import datetime
import configparser
from shutil import copy
from sys import platform, exit as shutdown

import discord
from discord.ext import commands, tasks

from core import database, migration, activity, github, schema

import bot_util as util
import bot_tasks
import bot_commands

bot = util.get_bot()

activities = util.activities
db = database.Database(util.db_file)

@bot.event
async def on_ready():
    print("Reaction Light ready!")
    if util.migrated:
        await util.system_notification(
            None,
            "Your CSV files have been deleted and migrated to an SQLite"
            " `reactionlight.db` file.",
        )

    if util.config_migrated:
        await util.system_notification(
            None,
            "Your `config.ini` has been edited and your admin IDs are now stored in"
            f" the database.\nYou can add or remove them with `{prefix}admin` and"
            f" `{prefix}rm-admin`.",
        )

    await util.database_updates()
    db.migrate_admins(bot)
    bot_tasks.maintain_presence.start()
    bot_tasks.cleandb.start()
    bot_tasks.check_cleanup_queued_guilds.start()
    bot_tasks.updates.start()


@bot.event
async def on_guild_remove(guild):
    db.remove_guild(guild.id)

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if util.isadmin(message.author, message.guild.id):
        user = str(message.author.id)
        channel = str(message.channel.id)
        step = db.step(user, channel)
        msg = message.content.split()

        # Checks if the setup process was started before.
        # If it was not, it ignores the message.
        if step is not None:
            if step == 0:
                db.step0(user, channel)

            elif step == 1:
                # The channel the message needs to be sent to is stored
                # Advances to step two
                if message.channel_mentions:
                    target_channel = message.channel_mentions[0].id

                else:
                    await message.channel.send("The channel you mentioned is invalid.")
                    return

                server = await util.getguild(message.guild.id)
                bot_user = server.get_member(bot.user.id)
                bot_permissions = await util.getchannel(target_channel).permissions_for(
                    bot_user
                )
                writable = bot_permissions.read_messages
                readable = bot_permissions.view_channel
                if not writable or not readable:
                    await message.channel.send(
                        "I cannot read or send messages in that channel."
                    )
                    return

                db.step1(user, channel, target_channel)

                await message.channel.send(
                    "Attach roles and emojis separated by one space (one combination"
                    " per message). When you are done type `done`. Example:\n:smile:"
                    " `@Role`"
                )
            elif step == 2:
                if msg[0].lower() != "done":
                    # Stores reaction-role combinations until "done" is received
                    try:
                        reaction = msg[0]
                        role = message.role_mentions[0].id
                        exists = db.step2(user, channel, role, reaction)
                        if exists:
                            await message.channel.send(
                                "You have already used that reaction for another role."
                            )
                            return

                        await message.add_reaction(reaction)

                    except IndexError:
                        await message.channel.send(
                            "Mention a role after the reaction. Example:\n:smile:"
                            " `@Role`"
                        )

                    except discord.HTTPException:
                        await message.channel.send(
                            "You can only use reactions uploaded to servers the bot has"
                            " access to or standard emojis."
                        )

                else:
                    # Advances to step three
                    db.step2(user, channel, done=True)

                    selector_embed = discord.Embed(
                        title="Embed_title",
                        description="Embed_content",
                        colour=botcolour,
                    )
                    selector_embed.set_footer(text=f"{botname}", icon_url=util.logo)

                    await message.channel.send(
                        "What would you like the message to say?\nFormatting is:"
                        " `Message // Embed_title // Embed_content`.\n\n`Embed_title`"
                        " and `Embed_content` are optional. You can type `none` in any"
                        " of the argument fields above (e.g. `Embed_title`) to make the"
                        " bot ignore it.\n\n\nMessage",
                        embed=selector_embed,
                    )

            elif step == 3:
                # Receives the title and description of the reaction-role message
                # If the formatting is not correct it reminds the user of it
                msg_values = message.content.split(" // ")
                selector_msg_body = (
                    msg_values[0] if msg_values[0].lower() != "none" else None
                )
                selector_embed = discord.Embed(colour=botcolour)
                selector_embed.set_footer(text=f"{botname}", icon_url=util.logo)

                if len(msg_values) > 1:
                    if msg_values[1].lower() != "none":
                        selector_embed.title = msg_values[1]
                    if len(msg_values) > 2 and msg_values[2].lower() != "none":
                        selector_embed.description = msg_values[2]

                # Prevent sending an empty embed instead of removing it
                selector_embed = (
                    selector_embed
                    if selector_embed.title or selector_embed.description
                    else None
                )

                if selector_msg_body or selector_embed:
                    target_channel = await util.getchannel(
                        db.get_targetchannel(user, channel)
                    )
                    selector_msg = None
                    try:
                        selector_msg = await target_channel.send(
                            content=selector_msg_body, embed=selector_embed
                        )

                    except discord.Forbidden:
                        await message.channel.send(
                            "I don't have permission to send selector_msg messages to"
                            f" the channel {target_channel.mention}."
                        )

                    if isinstance(selector_msg, discord.Message):
                        combos = db.get_combos(user, channel)

                        end = db.end_creation(user, channel, selector_msg.id)
                        if isinstance(end, Exception):
                            await message.channel.send(
                                "I could not commit the changes to the database."
                            )
                            await util.system_notification(
                                message.channel.id, f"Database error:\n```\n{end}\n```",
                            )

                        for reaction in combos:
                            try:
                                await selector_msg.add_reaction(reaction)

                            except discord.Forbidden:
                                await message.channel.send(
                                    "I don't have permission to react to messages from"
                                    f" the channel {target_channel.mention}."
                                )

                else:
                    await message.channel.send(
                        "You can't use an empty message as a role-reaction message."
                    )


@bot.event
async def on_raw_reaction_add(payload):
    reaction = str(payload.emoji)
    msg_id = payload.message_id
    ch_id = payload.channel_id
    user_id = payload.user_id
    guild_id = payload.guild_id
    exists = db.exists(msg_id)

    if isinstance(exists, Exception):
        await util.system_notification(
            guild_id,
            f"Database error after a user added a reaction:\n```\n{exists}\n```",
        )

    elif exists:
        # Checks that the message that was reacted to is a reaction-role message managed by the bot
        reactions = db.get_reactions(msg_id)

        if isinstance(reactions, Exception):
            await util.system_notification(
                guild_id,
                f"Database error when getting reactions:\n```\n{reactions}\n```",
            )
            return

        ch = await util.getchannel(ch_id)
        msg = await ch.fetch_message(msg_id)
        user = await util.getuser(user_id)
        if reaction not in reactions:
            # Removes reactions added to the reaction-role message that are not connected to any role
            await msg.remove_reaction(reaction, user)

        else:
            # Gives role if it has permissions, else 403 error is raised
            role_id = reactions[reaction]
            server = await util.getguild(guild_id)
            member = server.get_member(user_id)
            role = discord.utils.get(server.roles, id=role_id)
            if user_id != bot.user.id:
                try:
                    await member.add_roles(role)

                except discord.Forbidden:
                    await util.system_notification(
                        guild_id,
                        "Someone tried to add a role to themselves but I do not have"
                        " permissions to add it. Ensure that I have a role that is"
                        " hierarchically higher than the role I have to assign, and"
                        " that I have the `Manage Roles` permission.",
                    )


@bot.event
async def on_raw_reaction_remove(payload):
    reaction = str(payload.emoji)
    msg_id = payload.message_id
    user_id = payload.user_id
    guild_id = payload.guild_id
    exists = db.exists(msg_id)

    if isinstance(exists, Exception):
        await util.system_notification(
            guild_id,
            f"Database error after a user removed a reaction:\n```\n{exists}\n```",
        )

    elif exists:
        # Checks that the message that was unreacted to is a reaction-role message managed by the bot
        reactions = db.get_reactions(msg_id)

        if isinstance(reactions, Exception):
            await util.system_notification(
                guild_id,
                f"Database error when getting reactions:\n```\n{reactions}\n```",
            )

        elif reaction in reactions:
            role_id = reactions[reaction]
            # Removes role if it has permissions, else 403 error is raised
            server = await util.getguild(guild_id)
            member = server.get_member(user_id)

            if not member:
                member = await server.fetch_member(user_id)

            role = discord.utils.get(server.roles, id=role_id)
            try:
                await member.remove_roles(role)

            except discord.Forbidden:
                await util.system_notification(
                    guild_id,
                    "Someone tried to remove a role from themselves but I do not have"
                    " permissions to remove it. Ensure that I have a role that is"
                    " hierarchically higher than the role I have to remove, and that I"
                    " have the `Manage Roles` permission.",
                )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("Only the bot owner may execute this command.")

try:
    bot.run(util.TOKEN)

except discord.PrivilegedIntentsRequired:
    print("[Login Failure] You need to enable the server members intent on the Discord Developers Portal.")

except discord.errors.LoginFailure:
    print("[Login Failure] The token inserted in config.ini is invalid.")
