import asyncio
import json
import logging
import typing
from collections import namedtuple
from logging import getLogger

import discord
from discord.ext import commands


logger = getLogger(__name__)


class MessageListenerCog(commands.Cog):
    def __init__(self, main_bot: commands.Bot, bots_list: typing.List[commands.Bot], config_contents: typing.Dict) -> None:
        self._main_bot: commands.Bot = main_bot
        self._bots_list: typing.List[commands.Bot] = bots_list
        self._survivors_voice_channel_id: int = config_contents.get("survivors_voice_channel_id")
        self._corpses_voice_channel_id: int = config_contents.get("corpses_voice_channel_id")
        self._command_enable_text_channel_id: int = config_contents.get("command_enable_text_channel_id")
        self._corpses_list: typing.List[discord.Member] = list()
        self._mute_control_mes: discord.Message = None
        self._is_muted: bool = False
        self._mute_lock: asyncio.Lock = asyncio.Lock()


    # bot起動時のイベント
    @commands.Cog.listener(name="on_ready")
    async def on_ready(self) -> None:
        activity = discord.Activity(name=".help", type=discord.ActivityType.playing)
        await self._main_bot.change_presence(status=discord.Status.online, activity=activity)
        logger.info("Ready!")
        logger.debug("生存者部屋:" + self._main_bot.get_channel(self._survivors_voice_channel_id).name)
        logger.debug("死亡者部屋:" + self._main_bot.get_channel(self._corpses_voice_channel_id).name)
        logger.info(f"Active bot:{len(self._bots_list)}")
        for bot in self._bots_list:
            logger.debug(f"using: {bot.user}")


    @commands.Cog.listener(name="on_reaction_add")
    async def response_reaction(self, reaction: discord.Reaction, user: typing.Union[discord.Member, discord.User]) -> None:
        try:
            if self._mute_control_mes is not None and user != self._main_bot.user and reaction.message.author == self._main_bot.user:
                if self._mute_control_mes.id == reaction.message.id:
                    if reaction.emoji == "🇲":
                        await self._mute(reaction.message.channel)
                        await reaction.remove(user)

                    elif reaction.emoji == "🇺":
                        await self._unmute(reaction.message.channel)
                        await reaction.remove(user)

                    elif reaction.emoji == "🇷":
                        await self.reset_mute(reaction.message.channel)
                        await reaction.remove(user)

                    elif reaction.emoji == "🇪":
                        self._mute_control_mes = None
                        await reaction.message.delete()

        except discord.errors.Forbidden as e:
            logger.warning(f"caused other: {e}")
            await reaction.message.channel.send("ボット稼働に必要な権限が足りません: ボットに『管理者』が有効なロールを付与するか以下の権限を持つロールを付与して下さい\n"
                           "『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』")


    @commands.Cog.listener(name="on_voice_state_update")
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        # Mute前に死亡者部屋へ移動出来なかった人のミュートを解除
        if after.channel == self._main_bot.get_channel(self._corpses_voice_channel_id) and member.voice.mute == True:
            await member.edit(mute=False)
            logger.debug(f"unmute {member.name}.")


    # リアクションによるミュート制御用メッセージ作成コマンド
    @commands.command(aliases=["s"])
    async def start(self, ctx, *, member: discord.Member=None) -> None:
        if not self.is_enable_channel(ctx):
            return

        try:
            embed = discord.Embed()
            embed_text =  f":regional_indicator_m: ミュート（実行時、ミュートのユーザは {self._main_bot.get_channel(self._corpses_voice_channel_id).name} へ移動します）\n"
            embed_text +=  ":regional_indicator_u: ミュート解除\n"
            embed_text +=  ":regional_indicator_r: リセット（1試合終了ごとに実行して下さい）\n"
            embed_text +=  ":regional_indicator_e: 終了（メッセージの削除）"
            embed.add_field(name="リアクションで操作が出来ます",
                            value=embed_text,
                                  inline=False)
            message = await ctx.send(content="準備OK!", embed=embed)
            self._mute_control_mes = message

            await message.add_reaction("🇲")
            await message.add_reaction("🇺")
            await message.add_reaction("🇷")
            await message.add_reaction("🇪")

        except discord.errors.Forbidden as e:
            logger.warning(f"[start] caused other: {e}")
            await ctx.send("ボット稼働に必要な権限が足りません: ボットに『管理者』が有効なロールを付与するか以下の権限を持つロールを付与して下さい\n"
                           "『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』")

        except discord.errors.NotFound as e:
            logger.warning(f"[start] caused other: {e}")
            await ctx.channel.send("スタートに失敗しました\n"
                                   "ボット稼働に必要な権限が付与されているか確認して下さい（以下のいずれかの条件を満たして下さい）\n"
                                   "・『管理者』が有効なロール\n"
                                   "・『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』が有効なロール")

        except discord.errors.HTTPException as e:
            logger.warning(f"[start] caused other: {e}")
            await ctx.channel.send("スタートに失敗しました\n"
                                   "ボット稼働に必要な権限が付与されているか確認して下さい（以下のいずれかの条件を満たして下さい）\n"
                                   "・『管理者』が有効なロール\n"
                                   "・『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』が有効なロール")

        except Exception as e:
            logger.warning(f"[start] caused other: {e}")
            await ctx.channel.send("スタートに失敗しました\n"
                                   "ボット稼働に必要な権限が付与されているか確認して下さい（以下のいずれかの条件を満たして下さい）\n"
                                   "・『管理者』が有効なロール\n"
                                   "・『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』が有効なロール")


    @commands.command(aliases=["h", "Help", "H"])
    async def help(self, ctx, *, member: discord.Member=None) -> None:
        if not self.is_enable_channel(ctx):
            return

        embed = discord.Embed(color=discord.Color.lighter_grey())

        embed.set_author(name="Available Commands")

        embed.add_field(name="`.start` / `.s`",
                        value="リアクションでミュート制御できるメッセージを作成．\n"
                              "制御方法は生成されたメッセージを確認して下さい．\n"
                              "ボットを再起動すると再起動前に生成したメッセージで制御できなくなります．",
                        inline=False)

        await ctx.send(embed=embed)


    async def _mute(self, channel) -> None:
        async with self._mute_lock:
            logger.debug(f"lock.")
            if self._is_muted == True:
                logger.debug(f"unlock.")
                return

            await self._disp_state(content="ミュート処理中")
            try:
                # 生存者部屋メンバのミュート処理
                survivors_vc: discord.abc.GuildChannel = self._main_bot.get_channel(self._survivors_voice_channel_id)
                no_of_members: int = 0
                mute_params_list: typing.List[typing.List[MuteMemberParam]] = [list() for i in range(len(self._bots_list))]
                for member in survivors_vc.members:
                    if not member.bot and not member.voice.self_mute:  # ボットでなく、ミュートにしていないメンバのみミュート
                        mute_params, _index = self.get_less_elements_list(mute_params_list)
                        mute_params.append(MuteMemberParam(member.id, True, None))
                        #await member.edit(mute=True)
                        logger.debug(f"mute {member.name}.")
                        no_of_members += 1
                    elif not member.bot and member.voice.self_mute: # ミュートにしているので死亡者部屋のメンバに追加
                        self._corpses_list.append(member)
                        logger.debug(f"add corpses_list {member.name}.")
                    else:
                        mute_params, _index = self.get_less_elements_list(mute_params_list)
                        mute_params.append(MuteMemberParam(member.id, False, None))
                        #await member.edit(mute=False)
                        logger.debug(f"Un-muted {member.name}")
                await self.process_mute(survivors_vc.members, mute_params_list[0])
                survivors_vc_list: typing.List[discord.abc.GuildChannel] = [survivors_vc]
                for i in range(1, len(self._bots_list)):
                    sub_survivors_vc = self._bots_list[i].get_channel(self._survivors_voice_channel_id)
                    survivors_vc_list.append(sub_survivors_vc)
                    await self.process_mute(sub_survivors_vc.members, mute_params_list[i])
                if no_of_members == 0:
                    logger.info(f"Everyone, please disconnect and reconnect to the Voice Channel again.")
                elif no_of_members < 2:
                    logger.info(f"Muted {no_of_members} user in {survivors_vc}.")
                else:
                    logger.info(f"Muted {no_of_members} users in {survivors_vc}.")

                # 死亡者部屋メンバのミュート解除、部屋移動処理
                mute_params_list: typing.List[typing.List[MuteMemberParam]] = [list() for i in range(len(self._bots_list))]
                corpses_vc_list = [bot.get_channel(self._corpses_voice_channel_id) for bot in self._bots_list]
                for member in self._corpses_list:
                    mute_params, mute_params_index = self.get_less_elements_list(mute_params_list)
                    mute_params.append(MuteMemberParam(member.id, False, corpses_vc_list[mute_params_index]))
                    #await member.edit(mute=False, voice_channel=corpses_vc_list[0])
                    logger.debug(f"   corpses_member {member.name}.")
                await self.process_mute(self._corpses_list, mute_params_list[0])
                logger.debug(f"main:{len(mute_params_list[0])}")
                for i in range(1, len(self._bots_list)):
                    await self.process_mute(survivors_vc_list[i].members, mute_params_list[i]) # corpses_list は self._main_bot から取得しているので他botは生存者部屋リストで代用
                    logger.debug(f"sub[{i}]:{len(mute_params_list[i])}")
                
                self._corpses_list.clear()
                self._is_muted = True

            except discord.Forbidden as e:
                logger.warning(f"caused other: {e}")
                await channel.send("ボット稼働に必要な権限が足りません: ボットに『管理者』が有効なロールを付与するか以下の権限を持つロールを付与して下さい\n"
                                       "『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』")

            except discord.HTTPException as e:
                logger.warning(f"caused HTTPException: {e}")
                await channel.send("処理が途中で失敗しました (HTTPException) \n"
                                       "・試合中なら全員セルフミュートで対応して下さい\n"
                                       "・次の会議で🇷でリセットして死亡者は改めてセルフミュートして下さい\n")
            except Exception as e:
                logger.warning(f"caused other: {e}")
                await channel.send("処理が途中で失敗しました\n"
                                       "・試合中なら全員セルフミュートで対応して下さい\n"
                                       "・次の会議で🇷でリセットして死亡者は改めてセルフミュートして下さい\n")

            await self._disp_state(content="ミュート!")
            logger.debug(f"unlock.")


    async def _unmute(self, channel) -> None:
        async with self._mute_lock:
            logger.debug(f"lock.")
            if self._is_muted == False:
                logger.debug(f"unlock.")
                return

            await self._disp_state(content="ミュート解除処理中")
            try:
                # 生存者部屋メンバのミュート解除処理
                survivors_vc = self._main_bot.get_channel(self._survivors_voice_channel_id)
                no_of_members = 0
                mute_params_list: typing.List[typing.List[MuteMemberParam]] = [list() for i in range(len(self._bots_list))]
                for member in survivors_vc.members:
                    if not member.bot: # ボットでない生存者部屋のユーザの場合ミュート解除 
                        mute_params, _index = self.get_less_elements_list(mute_params_list)
                        mute_params.append(MuteMemberParam(member.id, False, None))
                        #await member.edit(mute=False)
                        logger.debug(f"unmute {member.name}.")
                        no_of_members += 1
                    else:
                        mute_params, _index = self.get_less_elements_list(mute_params_list)
                        mute_params.append(MuteMemberParam(member.id, True, None))
                        #await member.edit(mute=True)  # mute the bot member
                        await channel.send(f"Muted {member.name}")
                await self.process_mute(survivors_vc.members, mute_params_list[0])
                survivors_vc_list: typing.List[typing.Any] = [survivors_vc]
                for i in range(1, len(self._bots_list)):
                    sub_survivors_vc = self._bots_list[i].get_channel(self._survivors_voice_channel_id)
                    survivors_vc_list.append(sub_survivors_vc)
                    await self.process_mute(sub_survivors_vc.members, mute_params_list[i])
                if no_of_members == 0:
                    logger.info(f"Everyone, please disconnect and reconnect to the Voice Channel again.")
                elif no_of_members < 2:
                    logger.info(f"Un-muted {no_of_members} user in {survivors_vc}.")
                else:
                    logger.info(f"Un-muted {no_of_members} users in {survivors_vc}.")

                # 死亡者部屋メンバのミュート、部屋移動処理
                mute_params_list: typing.List[typing.List[MuteMemberParam]] = [list() for i in range(len(self._bots_list))]
                self._corpses_list = self._main_bot.get_channel(self._corpses_voice_channel_id).members
                for member in self._corpses_list: # 死亡者部屋のユーザをミュート状態で生存者部屋へ移動
                    mute_params, mute_params_index = self.get_less_elements_list(mute_params_list)
                    mute_params.append(MuteMemberParam(member.id, True, survivors_vc_list[mute_params_index]))
                    #await member.edit(mute=True, voice_channel=survivors_vc)
                    logger.debug(f"   corpses_member {member.name}.")
                await self.process_mute(self._corpses_list, mute_params_list[0])
                logger.debug(f"main:{len(mute_params_list[0])}")
                for i in range(1, len(self._bots_list)):
                    await self.process_mute(self._bots_list[i].get_channel(self._corpses_voice_channel_id).members, mute_params_list[i])
                    logger.debug(f"sub{i}:{len(mute_params_list[i])}")
                self._is_muted = False

            except discord.Forbidden as e:
                logger.warning(f"caused other: {e}")
                await channel.send("ボット稼働に必要な権限が足りません: ボットに『管理者』が有効なロールを付与するか以下の権限を持つロールを付与して下さい\n"
                                       "『メッセージを送信』『メッセージの管理』『メッセージ履歴を読む』『リアクションの追加』『メンバーをミュート』『メンバーのスピーカーをミュート』『メンバーを移動』")

            except discord.HTTPException as e:
                logger.warning(f"caused HTTPException: {e}")
                await channel.send("処理が途中で失敗しました (HTTPException) \n"
                                       "・試合中なら全員セルフミュートで対応して下さい\n"
                                       "・次の会議で🇷でリセットして死亡者は改めてセルフミュートして下さい\n")

            except Exception as e:
                logger.warning(f"caused other: {e}")
                await channel.send("処理が途中で失敗しました\n"
                                       "・試合中なら全員セルフミュートで対応して下さい\n"
                                       "・次の会議で🇷でリセットして死亡者は改めてセルフミュートして下さい\n")

            await self._disp_state(content="ミュート解除!")
            logger.debug(f"unlock.")


    async def reset_mute(self, channel) -> None:
        async with self._mute_lock:
            await self._disp_state(content="初期化中")
            logger.debug(f"lock.")

            survivors_vc_list: typing.List[discord.abc.GuildChannel] = [bot.get_channel(self._survivors_voice_channel_id) for bot in self._bots_list]
            mute_params_list: typing.List[typing.List[MuteMemberParam]] = [list() for i in range(len(self._bots_list))]
            # 全メンバのミュート解除
            for member in survivors_vc_list[0].members:
                mute_params, _index = self.get_less_elements_list(mute_params_list)
                mute_params.append(MuteMemberParam(member.id, False, None))
                #await member.edit(mute=False)
            for i in range(len(self._bots_list)):
                await self.process_mute(survivors_vc_list[i].members, mute_params_list[i])

            corpses_vc = self._main_bot.get_channel(self._corpses_voice_channel_id)
            mute_params_list: typing.List[typing.List[MuteMemberParam]] = [list() for i in range(len(self._bots_list))]
            for member in corpses_vc.members:
                mute_params, mute_params_index = self.get_less_elements_list(mute_params_list)
                mute_params.append(MuteMemberParam(member.id, False, survivors_vc_list[mute_params_index]))
                #await member.edit(mute=False, voice_channel=survivors_vc_list[0])
            await self.process_mute(corpses_vc.members, mute_params_list[0])
            for i in range(1, len(self._bots_list)):
                await self.process_mute(self._bots_list[i].get_channel(self._corpses_voice_channel_id).members, mute_params_list[i])

            self._corpses_list.clear()
            self._is_muted = False

            await self._disp_state(content="準備OK!")
            logger.debug(f"unlock.")


    async def process_mute(self, members: discord.Member, mute_member_params: typing.List[typing.List[typing.Any]]) -> None:
        if members is None or mute_member_params is None:
            return

        logger.info("members:"+", ".join(["("+m.name+":"+str(m.id)+")" for m in members]))
        logger.info("mute_member_params:"+", ".join(["("+str(m.id)+")" for m in mute_member_params]))
        for member in members:
            for mute_member_param in mute_member_params:
                if member.id == mute_member_param.id:
                    if mute_member_param.voice_channel is None:
                        await member.edit(mute=mute_member_param.is_mute)
                    else:
                        await member.edit(mute=mute_member_param.is_mute, voice_channel=mute_member_param.voice_channel)


    async def _disp_state(self, content):
        if self._mute_control_mes is not None:
            await self._mute_control_mes.edit(content=content)


    def is_enable_channel(self, ctx) -> bool:
        if self._command_enable_text_channel_id is None:
            return True
        return ctx.message.channel.id == self._command_enable_text_channel_id


    def get_less_elements_list(self, target_list_list: typing.List[typing.List[typing.Any]]) -> typing.Tuple[typing.List[typing.Any], int]:
        less_elements_index = len(target_list_list)-1
        for i in range(less_elements_index-1, -1, -1):
            if len(target_list_list[i]) < len(target_list_list[less_elements_index]):
                less_elements_index = i
        return target_list_list[less_elements_index], less_elements_index


class MuteMemberParam:
    def __init__(self, id: int=None, is_mute: bool= None, voice_channel: discord.abc.GuildChannel=None):
        self.id = id
        self.is_mute = is_mute
        self.voice_channel = voice_channel


class MuteBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.tree.sync()
        return await super().setup_hook()


def main() -> None:
    log_format = "[%(asctime)s %(levelname)s %(name)s(%(lineno)s)][%(funcName)s] %(message)s"
    logging.basicConfig(filename=f"MuteAll_ex.log", encoding="utf-8", filemode="w", format=log_format)
    #logging.basicConfig(filename=f"MuteAll_ex.log", encoding="utf-8", filemode="w")
    logging.getLogger().setLevel(level=logging.DEBUG)

    with open("config.json", "r") as token_file:
        config_contents = json.load(token_file)

        BotEntry = namedtuple("BotEntry", "bot token")
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        bot_entries: typing.List[BotEntry] = [BotEntry(bot=MuteBot(command_prefix="." if i==0 else f"._{i}", intents=intents), token=config_contents.get("token")[i]) for i in range(len(config_contents.get("token")))]
        bot_list: typing.List[commands.Bot] = [bot_entry.bot for bot_entry in bot_entries]
        for bot in bot_list:
            bot.remove_command("help")
        main_bot: commands.Bot = bot_entries[0].bot

        try:
            loop = asyncio.get_event_loop()
            message_listener_cog = MessageListenerCog(main_bot, bot_list, config_contents)
            loop.run_until_complete(main_bot.add_cog(message_listener_cog))
            cors = [entry.bot.start(entry.token) for entry in bot_entries]
            loop.run_until_complete(asyncio.gather(*cors))
        except Exception as e:
            logger.warning(f"Exception:{e}")


if __name__ == "__main__":
        main()
