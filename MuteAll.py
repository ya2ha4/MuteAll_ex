import asyncio
import discord
from discord.ext import commands
import json
import logging
import random


# logging 設定 ================================
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging_file_handler = logging.FileHandler(filename="MuteAll_ex.log", encoding="utf-8", mode="w")
logger.addHandler(logging_file_handler)


# discord_py 設定 ================================
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix=".", intents=intents)

# removes the default ".help" command
client.remove_command("help")

survivors_voice_channel_id = int(0)
corpses_voice_channel_id = int(0)


# グローバル変数設定 ================================
# mute時の死亡者部屋のユーザリスト（unmute時に状態復帰させる為の情報格納用）
# list[discord.Member]
corpses_list = list()

# startコマンドで生成するミュート操作用のメッセージ
# discord.Message
mute_control_mes = None

is_muted = False
mute_lock = asyncio.Lock()


# sets status when the bot is ready
@client.event
async def on_ready():
    activity = discord.Activity(name=".help", type=discord.ActivityType.playing)
    await client.change_presence(status=discord.Status.online, activity=activity)
    logger.info("Ready!")
    logger.debug("生存者部屋:" + client.get_channel(survivors_voice_channel_id).name)
    logger.debug("死亡者部屋:" + client.get_channel(corpses_voice_channel_id).name)


@client.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send("Hey, thanks for adding me! If you are already in a voice channel, please make "
                               "everyone disconnect and reconnect so I can work properly. Type `.help` to view all "
                               "the commands.")
            break


# shows latency of the bot
#@client.command(aliases=["latency"])
#async def ping(ctx):
#    await ctx.send(f"{round(client.latency * 1000)} ms")


# shows help text
@client.command(aliases=["commands", "Help", "h", "H"])
async def help(ctx):
    embed = discord.Embed(color=discord.Color.lighter_grey())

    embed.set_author(name="Available Commands")

    embed.add_field(name="`.mute` / `.m`", value="Mute humans and un-mute bots in your current voice channel.",
                    inline=False)

    embed.add_field(name="`.unmute` / `.u`", value="Un-mute humans and mute bots in your current voice channel.",
                    inline=False)

    embed.add_field(name="`.start` / `.s`", value="[BETA] React with emojies to mute or unmute, no need to type "
                                                  "anymore! ", inline=False)

    embed.add_field(name="`.end` / `.e`", value="End the game, un-mute everyone (including bots)", inline=False)

    await ctx.send(embed=embed)


# ミュートのリセット
@client.command(aliases=["rm"])
async def reset_mute(ctx):
    global mute_lock
    async with mute_lock:
        await disp_state(content="初期化中")
        logger.debug(f"[reset_mute] lock.")

        # 全メンバのミュート解除
        for member in client.get_channel(survivors_voice_channel_id).members:
            await member.edit(mute=False)
        for member in client.get_channel(corpses_voice_channel_id).members:
            await member.edit(mute=False)

        # グローバル変数の初期化
        global corpses_list, is_muted
        corpses_list.clear()
        is_muted = False

        await disp_state(content="準備OK!")
        logger.debug(f"[reset_mute] unlock.")


async def _mute(ctx):
    global is_muted, mute_lock
    async with mute_lock:
        logger.debug(f"[_mute] lock.")
        if is_muted == True:
            logger.debug(f"[_mute] unlock.")
            return

        await disp_state(content="ミュート処理中")
        try:
            survivors_vc = client.get_channel(survivors_voice_channel_id)
            no_of_members = 0
            for member in survivors_vc.members:  # traverse through the members list in survivor vc
                if not member.bot and not member.voice.self_mute:  # ボットでなく、ミュートにしていないメンバのみミュート
                    await member.edit(mute=True)
                    logger.debug(f"[_mute] mute {member.name}.")
                    no_of_members += 1
                else:
                    await member.edit(mute=False)
                    logger.debug(f"Un-muted {member.name}")
            if no_of_members == 0:
                logger.info(f"Everyone, please disconnect and reconnect to the Voice Channel again.")
            elif no_of_members < 2:
                logger.info(f"Muted {no_of_members} user in {survivors_vc}.")
            else:
                logger.info(f"Muted {no_of_members} users in {survivors_vc}.")
            corpses_vc = client.get_channel(corpses_voice_channel_id)
            global corpses_list
            for member in corpses_list:
                await member.edit(mute=False, voice_channel=corpses_vc)
                logger.debug(f"[_mute]   corpses_member {member.name}.")
            corpses_list.clear()
            is_muted = True
        except discord.Forbidden:
            await ctx.channel.send(  # the bot doesn't have the permission to mute
                f"Please make sure I have the `Mute Members` permission in my role **and** in your current "
                f"voice channel `{author.voice.channel}`.")
        except discord.HTTPException as e:
            # # me = client.get_user(187568903084441600)
            # await me.send(f"{command_name} caused HTTPException: {e}")
            await ctx.channel.send("Something went wrong. (HTTPException) You can try the following things:\n"
                                   "1. Make everyone disconnect and reconnect to the Voice Channel again.\n"
                                   "2. Give me the 'Administrator' permission.\n"
                                   "3. DM `SCARECOW#0456` on discord.\n")
        except Exception as e:
            # me = client.get_user(187568903084441600)
            # await me.send(f"{command_name} caused other: {e}")
            await ctx.channel.send("Something went wrong. You can try the following things:\n"
                                   "1. Make everyone disconnect and reconnect to the Voice Channel again.\n"
                                   "2. Give me the 'Administrator' permission.\n"
                                   "3. DM `SCARECOW#0456` on discord.\n")

        await disp_state(content="ミュート!")
        logger.debug(f"[_mute] unlock.")


# mutes everyone in the current voice channel and un-mutes the bots
@client.command(aliases=["m", "M", "Mute"])
async def mute(ctx):
    command_name = "mute"
    author = ctx.author

    if ctx.guild:  # check if the msg was in a server's text channel
        if author.voice:  # check if the user is in a voice channel
            if author.guild_permissions.mute_members:  # check if the user has mute members permission
                await _mute(ctx)
            else:
                await ctx.channel.send("You don't have the `Mute Members` permission.")
        else:
            await ctx.send("You must join a voice channel first.")
    else:
        await ctx.send("This does not work in DMs.")


async def _unmute(ctx):
    global is_muted, mute_lock
    async with mute_lock:
        logger.debug(f"[_unmute] lock.")
        if is_muted == False:
            logger.debug(f"[_unmute] unlock.")
            return

        await disp_state(content="ミュート解除処理中")
        try:
            survivors_vc = client.get_channel(survivors_voice_channel_id)
            no_of_members = 0
            for member in survivors_vc.members:  # traverse through the members list in survivor vc
                if not member.bot:  # check if member is not a bot
                    await member.edit(mute=False)  # un-mute the non-bot member
                    logger.debug(f"[_unmute] unmute {member.name}.")
                    no_of_members += 1
                else:
                    await member.edit(mute=True)  # mute the bot member
                    await ctx.send(f"Muted {member.name}")
            if no_of_members == 0:
                logger.info(f"Everyone, please disconnect and reconnect to the Voice Channel again.")
            elif no_of_members < 2:
                logger.info(f"Un-muted {no_of_members} user in {survivors_vc}.")
            else:
                logger.info(f"Un-muted {no_of_members} users in {survivors_vc}.")
            global corpses_list
            corpses_list = client.get_channel(corpses_voice_channel_id).members
            for member in corpses_list:
                await member.edit(mute=True, voice_channel=survivors_vc)
                logger.debug(f"[_unmute]   corpses_member {member.name}.")
            is_muted = False
        except discord.Forbidden:
            await ctx.channel.send(  # the bot doesn't have the permission to mute
                f"Please make sure I have the `Mute Members` permission in my role **and** in your current "
                f"voice channel `{author.voice.channel}`.")
        except discord.HTTPException as e:
            # me = client.get_user(187568903084441600)
            # await me.send(f"{command_name} caused HTTPException: {e}")
            await ctx.channel.send("Something went wrong. You can try the following things:\n"
                                   "1. Make everyone disconnect and reconnect to the Voice Channel again.\n"
                                   "2. Give me the 'Administrator' permission.\n"
                                   "3. DM `SCARECOW#0456` on discord.\n")
        except Exception as e:
            # me = client.get_user(187568903084441600)
            # await me.send(f"{command_name} caused other: {e}")
            await ctx.channel.send("Something went wrong. You can try the following things:\n"
                                   "1. Make everyone disconnect and reconnect to the Voice Channel again.\n"
                                   "2. Give me the 'Administrator' permission.\n"
                                   "3. DM `SCARECOW#0456` on discord.\n")

        await disp_state(content="ミュート解除!")
        logger.debug(f"[_unmute] unlock.")


# un-mutes everyone in the current voice channel and mutes the bots
@client.command(aliases=["um", "un", "un-mute", "u", "U", "Un", "Um", "Unmute"])
async def unmute(ctx):
    command_name = "unmute"
    author = ctx.author

    if ctx.guild:  # check if the msg was in a server's text channel
        if author.voice:  # check if the user is in a voice channel
            await _unmute(ctx)
        else:
            await ctx.send("You must join a voice channel first.")
    else:
        await ctx.send("This does not work in DMs.")


# end the game and un-mute everyone including bots
@client.command(aliases=["e", "E", "End"])
async def end(ctx):
    command_name = "end"
    author = ctx.author

    if ctx.guild:  # check if the msg was in a server's text channel
        if author.voice:  # check if the user is in a voice channel
            try:
                no_of_members = 0
                for member in author.voice.channel.members:  # traverse through the members list in current vc
                    await member.edit(mute=False)  # un-mute the member
                    no_of_members += 1
                if no_of_members == 0:
                    logger.info(f"Everyone, please disconnect and reconnect to the Voice Channel again.")
                elif no_of_members < 2:
                    logger.info(f"Un-muted {no_of_members} user in {author.voice.channel}.")
                else:
                    logger.info(f"Un-muted {no_of_members} users in {author.voice.channel}.")

            except discord.Forbidden:
                await ctx.channel.send(  # the bot doesn't have the permission to mute
                    f"Please make sure I have the `Mute Members` permission in my role **and** in your current "
                    f"voice channel `{author.voice.channel}`.")
            except discord.HTTPException as e:
                # me = client.get_user(187568903084441600)
                # await me.send(f"{command_name} caused HTTPException: {e}")
                await ctx.channel.send("Something went wrong. You can try the following things:\n"
                                       "1. Make everyone disconnect and reconnect to the Voice Channel again.\n"
                                       "2. Give me the 'Administrator' permission.\n"
                                       "3. DM `SCARECOW#0456` on discord.\n")
            except Exception as e:
                # me = client.get_user(187568903084441600)
                # await me.send(f"{command_name} caused other: {e}")
                await ctx.channel.send("Something went wrong. You can try the following things:\n"
                                       "1. Make everyone disconnect and reconnect to the Voice Channel again.\n"
                                       "2. Give me the 'Administrator' permission.\n"
                                       "3. DM `SCARECOW#0456` on discord.\n")
        else:
            await ctx.send("You must join a voice channel first.")
    else:
        await ctx.send("This does not work in DMs.")


async def mute_with_reaction(user):
    command_name = "mute_with_reaction"
    try:
        if user.voice:  # check if the user is in a voice channel
            if user.guild_permissions.mute_members:  # check if the user has mute members permission
                for member in user.voice.channel.members:  # traverse through the members list in current vc
                    if not member.bot:  # check if member is not a bot
                        await member.edit(mute=True)  # mute the non-bot member
                    else:
                        await member.edit(mute=False)  # un-mute the bot member
    except Exception as e:
        pass
        # me = client.get_user(187568903084441600)
        # await me.send(f"{command_name}: {e}")


async def unmute_with_reaction(user):
    command_name = "unmute_with_reaction"
    try:
        if user.voice:  # check if the user is in a voice channel
            for member in user.voice.channel.members:  # traverse through the members list in current vc
                if not member.bot:  # check if member is not a bot
                    await member.edit(mute=False)  # mute the non-bot member
                else:
                    await member.edit(mute=True)  # un-mute the bot member
    except Exception as e:
        pass
        # me = client.get_user(187568903084441600)
        # await me.send(f"{command_name}: {e}")


# async def end_with_reaction(user):
#     command_name = "end_with_reaction"
#     try:
#         if user.voice:  # check if the user is in a voice channel
#             for member in user.voice.channel.members:  # traverse through the members list in current vc
#                 await member.edit(mute=False)  # mute the non-bot member
#     except Exception as e:
#         # me = client.get_user(187568903084441600)
#         # await me.send(f"{command_name}: {e}")


# TODO: Move to on_raw_reaction_add(), get user obj using user_id, find a way to get reaction obj
# use reactions instead of typing
@client.command(aliases=["play", "s", "p"])
async def start(ctx):
    try:
        embed = discord.Embed()
        embed.add_field(name="リアクションで操作が出来ます",
                        value=":regional_indicator_m: ミュート\n"
                              ":regional_indicator_u: ミュート解除\n"
                              ":regional_indicator_r: リセット（1試合終了ごとに実行して下さい）\n"
                              ":regional_indicator_e: 終了（メッセージの削除）",
                              inline=False)
        global mute_control_mes
        message = await ctx.send(content="準備OK!", embed=embed)
        mute_control_mes = message

        await message.add_reaction("🇲")
        await message.add_reaction("🇺")
        await message.add_reaction("🇷")
        await message.add_reaction("🇪")

        @client.event
        async def on_reaction_add(reaction, user):
            try:
                if user != client.user:  # this user is the user who reacted, ignore the initial reactions from the bot
                    if reaction.message.author == client.user:  # this user is the author of the embed, should be the
                        # bot itself, this check is needed so the bot doesn't mute/unmute on reactions to any other
                        # messages
                        if reaction.emoji == "🇲":
                            #await mute_with_reaction(user)
                            await _mute(ctx)
                            await reaction.remove(user)

                        elif reaction.emoji == "🇺":
                            #await unmute_with_reaction(user)
                            await _unmute(ctx)
                            await reaction.remove(user)

                        elif reaction.emoji == "🇷":
                            await reset_mute(ctx)
                            await reaction.remove(user)

                        elif reaction.emoji == "🇪":
                            mute_control_mes = None
                            await message.delete()

            except discord.errors.Forbidden:
                await ctx.send("Make sure I have the following permissions: `Manage Messages`, `Read Message History`, "
                               "`Add Reactions`, `Mute Members`")

    except discord.errors.Forbidden:
        await ctx.send("Make sure I have the following permissions: `Manage Messages`, `Read Message History`, "
                       "`Add Reactions`, `Mute Members`")

    except discord.errors.NotFound:
        await ctx.channel.send(f"Something went wrong. Try rejoining the VC. Also make sure the bot has the following "
                               f"permissions: `Manage Messages`, `Read Message History`, `Add Reactions`, "
                               f"`Mute Members`, `Deafen Members`. Please contact `SCARECOW#0456` if this keeps "
                               f"happening. OR use the normal `.mute` and `.unmute`")

    except discord.errors.HTTPException:
        await ctx.channel.send(f"Something went wrong. Try rejoining the VC. Also make sure the bot has the following "
                               f"permissions: `Manage Messages`, `Read Message History`, `Add Reactions`, "
                               f"`Mute Members`, `Deafen Members`. Please contact `SCARECOW#0456` if this keeps "
                               f"happening. OR use the normal `.mute` and `.unmute`")

    except Exception as e:
        # me = client.get_user(187568903084441600)
        # await me.send(e)
        await ctx.channel.send(f"Something went wrong. Try rejoining the VC. Also make sure the bot has the following "
                               f"permissions: `Manage Messages`, `Read Message History`, `Add Reactions`, "
                               f"`Mute Members`, `Deafen Members`. Please contact `SCARECOW#0456` if this keeps "
                               f"happening. OR use the normal `.mute` and `.unmute`")


@client.event
async def on_voice_state_update(member, before, after):
    # Mute前に死亡者部屋へ移動出来なかった人のミュートを解除
    if after.channel == client.get_channel(corpses_voice_channel_id) and member.voice.mute == True:
        await member.edit(mute=False)
        logger.debug(f"[on_voice_state_update] unmute {member.name}.")


async def disp_state(content):
    if mute_control_mes is not None:
        await mute_control_mes.edit(content=content)


# run the bot
discord_token = str()
with open("token_test.json", "r") as token_file:
    json_contents = json.load(token_file)
    discord_token               = json_contents["token"]
    survivors_voice_channel_id  = json_contents["survivors_voice_channel_id"]
    corpses_voice_channel_id    = json_contents["corpses_voice_channel_id"]
client.run(discord_token)
