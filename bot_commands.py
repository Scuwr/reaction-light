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
from shutil import copy
from sys import platform, exit as shutdown

import discord
from discord.ext import commands

from core import database, github

import bot_util as util

bot = util.get_bot()

activities = util.activities
db = database.Database(util.db_file)

bot.remove_command("help")


@bot.command(name="new")
async def new(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        # Starts setup process and the bot starts to listen to the user in that channel
        # For future prompts (see: "async def on_message(message)")
        started = db.start_creation(
            ctx.message.author.id, ctx.message.channel.id, ctx.message.guild.id
        )
        if started:
            await ctx.send("Mention the #channel where to send the auto-role message.")

        else:
            await ctx.send(
                "You are already creating a reaction-role message in this channel. "
                f"Use another channel or run `{prefix}abort` first."
            )

    else:
        await ctx.send(
            f"You do not have an admin role. You might want to use `{prefix}admin`"
            " first."
        )


@bot.command(name="abort")
async def abort(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        # Aborts setup process
        aborted = db.abort(ctx.message.author.id, ctx.message.channel.id)
        if aborted:
            await ctx.send("Reaction-role message creation aborted.")

        else:
            await ctx.send(
                "There are no reaction-role message creation processes started by you"
                " in this channel."
            )

    else:
        await ctx.send(f"You do not have an admin role.")


@bot.command(name="edit")
async def edit_selector(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        # Reminds user of formatting if it is wrong
        msg_values = ctx.message.content.split()
        if len(msg_values) < 2:
            await ctx.send(
                f"**Type** `{prefix}edit #channelname` to get started. Replace"
                " `#channelname` with the channel where the reaction-role message you"
                " wish to edit is located."
            )
            return

        elif len(msg_values) == 2:
            try:
                channel_id = ctx.message.channel_mentions[0].id

            except IndexError:
                await ctx.send("You need to mention a channel.")
                return

            channel = await util.getchannel(channel_id)
            all_messages = await util.formatted_channel_list(channel)
            if len(all_messages) == 1:
                await ctx.send(
                    "There is only one reaction-role message in this channel."
                    f" **Type**:\n```\n{prefix}edit #{channel.name} // 1 // New Message"
                    " // New Embed Title (Optional) // New Embed Description"
                    " (Optional)\n```\nto edit the reaction-role message. You can type"
                    " `none` in any of the argument fields above (e.g. `New Message`)"
                    " to make the bot ignore it."
                )

            elif len(all_messages) > 1:
                await ctx.send(
                    f"There are **{len(all_messages)}** reaction-role messages in this"
                    f" channel. **Type**:\n```\n{prefix}edit #{channel.name} //"
                    " MESSAGE_NUMBER // New Message // New Embed Title (Optional) //"
                    " New Embed Description (Optional)\n```\nto edit the desired one."
                    " You can type `none` in any of the argument fields above (e.g."
                    " `New Message`) to make the bot ignore it. The list of the"
                    " current reaction-role messages is:\n\n"
                    + "\n".join(all_messages)
                )

            else:
                await ctx.send("There are no reaction-role messages in that channel.")

        elif len(msg_values) > 2:
            try:
                # Tries to edit the reaction-role message
                # Raises errors if the channel sent was invalid or if the bot cannot edit the message
                channel_id = ctx.message.channel_mentions[0].id
                channel = await util.getchannel(channel_id)
                msg_values = ctx.message.content.split(" // ")
                selector_msg_number = msg_values[1]
                all_messages = db.fetch_messages(channel_id)

                if isinstance(all_messages, Exception):
                    await util.system_notification(
                        ctx.message.guild.id,
                        "Database error when fetching"
                        f" messages:\n```\n{all_messages}\n```",
                    )
                    return

                counter = 1
                if all_messages:
                    message_to_edit_id = None
                    for msg_id in all_messages:
                        # Loop through all msg_ids and stops when the counter matches the user input
                        if str(counter) == selector_msg_number:
                            message_to_edit_id = msg_id
                            break

                        counter += 1

                else:
                    await ctx.send(
                        "You selected a reaction-role message that does not exist."
                    )
                    return

                if message_to_edit_id:
                    old_msg = await channel.fetch_message(int(message_to_edit_id))

                else:
                    await ctx.send(
                        "Select a valid reaction-role message number (i.e. the number"
                        " to the left of the reaction-role message content in the list"
                        " above)."
                    )
                    return

                await old_msg.edit(suppress=False)
                selector_msg_new_body = (
                    msg_values[2] if msg_values[2].lower() != "none" else None
                )
                selector_embed = discord.Embed()

                if len(msg_values) > 3 and msg_values[3].lower() != "none":
                    selector_embed.title = msg_values[3]
                    selector_embed.colour = botcolour
                    selector_embed.set_footer(text=f"{botname}", icon_url=util.logo)

                if len(msg_values) > 4 and msg_values[4].lower() != "none":
                    selector_embed.description = msg_values[4]
                    selector_embed.colour = botcolour
                    selector_embed.set_footer(text=f"{botname}", icon_url=util.logo)

                try:
                    if selector_embed.title or selector_embed.description:
                        await old_msg.edit(
                            content=selector_msg_new_body, embed=selector_embed
                        )

                    else:
                        await old_msg.edit(content=selector_msg_new_body, embed=None)

                    await ctx.send("Message edited.")

                except discord.HTTPException as e:
                    if e.code == 50006:
                        await ctx.send(
                            "You can't use an empty message as role-reaction message."
                        )

                    else:
                        guild_id = ctx.message.guild.id
                        await util.system_notification(guild_id, str(e))

            except IndexError:
                await ctx.send("The channel you mentioned is invalid.")

            except discord.Forbidden:
                await ctx.send("I do not have permissions to edit the message.")

    else:
        await ctx.send("You do not have an admin role.")


@bot.command(name="reaction")
async def edit_reaction(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        msg_values = ctx.message.content.split()
        mentioned_roles = ctx.message.role_mentions
        mentioned_channels = ctx.message.channel_mentions
        if len(msg_values) < 4:
            if not mentioned_channels:
                await ctx.send(
                    f" To get started, type:\n```\n{prefix}reaction add"
                    f" #channelname\n```or\n```\n{prefix}reaction remove"
                    " #channelname\n```"
                )
                return

            channel = ctx.message.channel_mentions[0]
            all_messages = await util.formatted_channel_list(channel)
            if len(all_messages) == 1:
                await ctx.send(
                    "There is only one reaction-role messages in this channel."
                    f" **Type**:\n```\n{prefix}reaction add #{channel.name} 1"
                    f" :reaction: @rolename\n```or\n```\n{prefix}reaction remove"
                    f" #{channel.name} 1 :reaction:\n```"
                )
                return

            elif len(all_messages) > 1:
                await ctx.send(
                    f"There are **{len(all_messages)}** reaction-role messages in this"
                    f" channel. **Type**:\n```\n{prefix}reaction add #{channel.name}"
                    " MESSAGE_NUMBER :reaction:"
                    f" @rolename\n```or\n```\n{prefix}reaction remove"
                    f" #{channel.name} MESSAGE_NUMBER :reaction:\n```\nThe list of the"
                    " current reaction-role messages is:\n\n"
                    + "\n".join(all_messages)
                )
                return

            else:
                await ctx.send("There are no reaction-role messages in that channel.")
                return

        action = msg_values[1].lower()
        channel = ctx.message.channel_mentions[0]
        message_number = msg_values[3]
        reaction = msg_values[4]
        if action == "add":
            if mentioned_roles:
                role = mentioned_roles[0]
            else:
                await ctx.send("You need to mention a role to attach to the reaction.")
                return

        all_messages = db.fetch_messages(channel.id)
        if isinstance(all_messages, Exception):
            await util.system_notification(
                ctx.message.guild.id,
                f"Database error when fetching messages:\n```\n{all_messages}\n```",
            )
            return

        counter = 1
        if all_messages:
            message_to_edit_id = None
            for msg_id in all_messages:
                # Loop through all msg_ids and stops when the counter matches the user input
                if str(counter) == message_number:
                    message_to_edit_id = msg_id
                    break

                counter += 1

        else:
            await ctx.send("You selected a reaction-role message that does not exist.")
            return

        if message_to_edit_id:
            message_to_edit = await channel.fetch_message(int(message_to_edit_id))

        else:
            await ctx.send(
                "Select a valid reaction-role message number (i.e. the number"
                " to the left of the reaction-role message content in the list"
                " above)."
            )
            return

        if action == "add":
            try:
                # Check that the bot can actually use the emoji
                await message_to_edit.add_reaction(reaction)

            except discord.HTTPException:
                await ctx.send(
                    "You can only use reactions uploaded to servers the bot has access"
                    " to or standard emojis."
                )
                return

            react = db.add_reaction(message_to_edit.id, role.id, reaction)
            if isinstance(react, Exception):
                await util.system_notification(
                    ctx.message.guild.id,
                    "Database error when adding a reaction to a message in"
                    f" {message_to_edit.channel.mention}:\n```\n{react}\n```",
                )
                return

            if not react:
                await ctx.send("That message already has a reaction-role combination with"
                               " that reaction.")
                return

            await ctx.send("Reaction added.")

        elif action == "remove":
            try:
                await message_to_edit.clear_reaction(reaction)

            except discord.HTTPException:
                await ctx.send("Invalid reaction.")
                return

            react = db.remove_reaction(message_to_edit.id, reaction)
            if isinstance(react, Exception):
                await util.system_notification(
                    ctx.message.guild.id,
                    "Database error when adding a reaction to a message in"
                    f" {message_to_edit.channel.mention}:\n```\n{react}\n```",
                )
                return

            await ctx.send("Reaction removed.")

    else:
        await ctx.send("You do not have an admin role.")


@bot.command(name="systemchannel")
async def set_systemchannel(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        global system_channel
        msg = ctx.message.content.split()
        mentioned_channels = ctx.message.channel_mentions
        channel_type = None if len(msg) < 2 else msg[1].lower()
        if (
                len(msg) < 3
                or not mentioned_channels
                or channel_type not in ["main", "server"]
        ):
            await ctx.send(
                "Define if you are setting up a server or main system channel and"
                f" mention the target channel.\n```\n{prefix}systemchannel"
                " <main/server> #channelname\n```"
            )
            return

        target_channel = mentioned_channels[0].id
        guild_id = ctx.message.guild.id

        server = await util.getguild(guild_id)
        bot_user = server.get_member(bot.user.id)
        bot_permissions = await util.getchannel(system_channel).permissions_for(bot_user)
        writable = bot_permissions.read_messages
        readable = bot_permissions.view_channel
        if not writable or not readable:
            await ctx.send("I cannot read or send messages in that channel.")
            return

        if channel_type == "main":
            system_channel = target_channel
            util.config["server"]["system_channel"] = str(system_channel)
            with open(f"{directory}/config.ini", "w") as configfile:
                util.config.write(configfile)

        elif channel_type == "server":
            add_channel = db.add_systemchannel(guild_id, target_channel)

            if isinstance(add_channel, Exception):
                await util.system_notification(
                    guild_id,
                    "Database error when adding a new system"
                    f" channel:\n```\n{add_channel}\n```",
                )
                return

        await ctx.send(f"System channel updated.")

    else:
        await ctx.send("You do not have an admin role.")


@commands.is_owner()
@bot.command(name="colour")
async def set_colour(ctx):
    msg = ctx.message.content.split()
    args = len(msg) - 1
    if args:
        global botcolour
        colour = msg[1]
        try:
            botcolour = discord.Colour(int(colour, 16))

            util.config["server"]["colour"] = colour
            with open(f"{directory}/config.ini", "w") as configfile:
                util.config.write(configfile)

            example = discord.Embed(
                title="Example embed",
                description="This embed has a new colour!",
                colour=botcolour,
            )
            await ctx.send("Colour changed.", embed=example)

        except ValueError:
            await ctx.send(
                "Please provide a valid hexadecimal value. Example:"
                f" `{prefix}colour 0xffff00`"
            )

    else:
        await ctx.send(
            f"Please provide a hexadecimal value. Example: `{prefix}colour"
            " 0xffff00`"
        )


@commands.is_owner()
@bot.command(name="activity")
async def add_activity(ctx):
    activity = ctx.message.content[(len(util.prefix) + len("activity")):].strip()
    if not activity:
        await ctx.send(
            "Please provide the activity you would like to"
            f" add.\n```\n{prefix}activity your activity text here\n```"
        )

    elif "," in activity:
        await ctx.send("Please do not use commas `,` in your activity.")

    else:
        activities.add(activity)
        await ctx.send(f"The activity `{activity}` was added succesfully.")


@commands.is_owner()
@bot.command(name="activitylist")
async def list_activities(ctx):
    if activities.activity_list:
        formatted_list = []
        for activity in activities.activity_list:
            formatted_list.append(f"`{activity}`")

        await ctx.send(
            "The current activities are:\n- " + "\n- ".join(formatted_list)
        )

    else:
        await ctx.send("There are no activities to show.")


@commands.is_owner()
@bot.command(name="rm-activity")
async def remove_activity(ctx):
    activity = ctx.message.content[(len(util.prefix) + len("rm-activity")):].strip()
    if not activity:
        await ctx.send(
            "Please paste the activity you would like to"
            f" remove.\n```\n{prefix}rm-activity your activity text here\n```"
        )
        return

    removed = activities.remove(activity)
    if removed:
        await ctx.send(f"The activity `{activity}` was removed.")

    else:
        await ctx.send("The activity you mentioned does not exist.")


@bot.command(name="help")
async def hlp(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        await ctx.send(
            "**Reaction Role Messages**\n"
            f"- `{prefix}new` starts the creation process for a new"
            " reaction role message.\n"
            f"- `{prefix}abort` aborts the creation process"
            " for a new reaction role message started by the command user in that"
            " channel.\n"
            f"- `{prefix}edit` edits the text and embed of an existing reaction"
            " role message.\n"
            f"- `{prefix}reaction` adds or removes a reaction from an existing"
            " reaction role message.\n"
            f"- `{prefix}colour` changes the colour of the embeds of new and newly"
            " edited reaction role messages.\n"
            "**Activities**\n"
            f"- `{prefix}activity` adds an activity for the bot to loop through and"
            " show as status.\n"
            f"- `{prefix}rm-activity` removes an activity from the bot's list.\n"
            f"- `{prefix}activitylist` lists the current activities used by the"
            " bot as statuses.\n"
        )
        await ctx.send(
            "**Admins**\n"
            f"- `{prefix}admin` adds the mentioned role to the list of {botname}"
            " admins, allowing them to create and edit reaction-role messages."
            " You need to be a server administrator to use this command.\n"
            f"- `{prefix}rm-admin` removes the mentioned role from the list of"
            f" {botname} admins, preventing them from creating and editing"
            " reaction-role messages. You need to be a server administrator to"
            " use this command.\n"
            f"- `{prefix}adminlist` lists the current admins on the server the"
            " command was run in by mentioning them and the current admins from"
            " other servers by printing out the role IDs. You need to be a server"
            " administrator to use this command.\n"
            "**System**\n"
            f"- `{prefix}systemchannel` updates the main or server system channel"
            " where the bot sends errors and update notifications.\n"
            "**Bot Control**\n"
            f"- `{prefix}kill` shuts down the bot.\n"
            f"- `{prefix}restart` restarts the bot. Only works on installations"
            " running on GNU/Linux.\n"
            f"- `{prefix}update` updates the bot and restarts it. Only works on"
            " `git clone` installations running on GNU/Linux.\n"
            f"- `{prefix}version` reports the bot's current version and the latest"
            " available one from GitHub.\n\n"
            f"{botname} is running version {util.__version__} of Reaction Light. You can"
            " find more resources, submit feedback, and report bugs at: "
            "<https://github.com/Scuwr/reaction-light>"
        )

    else:
        await ctx.send("You do not have an admin role.")


@bot.command(pass_context=True, name="admin")
@commands.has_permissions(administrator=True)
async def add_admin(ctx, role: discord.Role):
    # Adds an admin role ID to the database
    add = db.add_admin(role.id, ctx.guild.id)

    if isinstance(add, Exception):
        await util.system_notification(
            ctx.message.guild.id,
            f"Database error when adding a new admin:\n```\n{add}\n```",
        )
        return

    await ctx.send("Added the role to my admin list.")


@add_admin.error
async def add_admin_error(ctx, error):
    if isinstance(error, commands.RoleNotFound):
        await ctx.send("Please mention a valid @Role or role ID.")


@bot.command(name="rm-admin")
@commands.has_permissions(administrator=True)
async def remove_admin(ctx, role: discord.Role):
    # Removes an admin role ID from the database
    remove = db.remove_admin(role.id, ctx.guild.id)

    if isinstance(remove, Exception):
        await util.system_notification(
            ctx.message.guild.id,
            f"Database error when removing an admin:\n```\n{remove}\n```",
        )
        return

    await ctx.send("Removed the role from my admin list.")


@remove_admin.error
async def remove_admin_error(ctx, error):
    if isinstance(error, commands.RoleNotFound):
        await ctx.send("Please mention a valid @Role or role ID.")


@bot.command(name="adminlist")
@commands.has_permissions(administrator=True)
async def list_admin(ctx):
    # Lists all admin IDs in the database, mentioning them if possible
    admin_ids = db.get_admins(ctx.guild.id)

    if isinstance(admin_ids, Exception):
        await util.system_notification(
            ctx.message.guild.id,
            f"Database error when fetching admins:\n```\n{admin_ids}\n```",
        )
        return

    adminrole_objects = []
    for admin_id in admin_ids:
        adminrole_objects.append(discord.utils.get(ctx.guild.roles, id=admin_id).mention)

    if adminrole_objects:
        await ctx.send(
            "The bot admins on this server are:\n- "
            + "\n- ".join(adminrole_objects)
        )
    else:
        await ctx.send("There are no bot admins registered in this server.")


@bot.command(name="version")
async def print_version(ctx):
    if util.isadmin(ctx.message.author, ctx.guild.id):
        latest = github.get_latest()
        await ctx.send(
            f"I am currently running Reaction Light v{util.__version__}. The latest"
            f" available version is v{latest}."
        )

    else:
        await ctx.send("You do not have an admin role.")


@commands.is_owner()
@bot.command(name="kill")
async def kill(ctx):
    await ctx.send("Shutting down...")
    shutdown()  # sys.exit()


@commands.is_owner()
@bot.command(name="restart")
async def restart_cmd(ctx):
    if platform != "win32":
        util.restart()
        await ctx.send("Restarting...")
        shutdown()  # sys.exit()

    else:
        await ctx.send("I cannot do this on Windows.")


@commands.is_owner()
@bot.command(name="update")
async def update(ctx):
    if platform != "win32":
        await ctx.send("Attempting update...")
        os.chdir(util.directory)
        cmd = os.popen("git fetch")
        cmd.close()
        cmd = os.popen("git pull")
        cmd.close()
        await ctx.send("Creating database backup...")
        copy(util.db_file, f"{db_file}.bak")
        util.restart()
        await ctx.send("Restarting...")
        shutdown()  # sys.exit()

    else:
        await ctx.send("I cannot do this on Windows.")