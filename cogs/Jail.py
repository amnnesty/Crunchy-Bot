import datetime
import random
import discord
import TenGiphPy

from discord.ext import tasks, commands
from discord import app_commands
from typing import Dict, Literal
from BotLogger import BotLogger
from BotSettings import BotSettings
from BotUtil import BotUtil
from MaraBot import MaraBot
from datalayer.Database import Database
from datalayer.JailList import JailList
from datalayer.UserInteraction import UserInteraction
from events.BotEventManager import BotEventManager
from events.EventType import EventType
from events.JailEventType import JailEventType

class Jail(commands.Cog):
    
    def __init__(self, bot: MaraBot):
        self.bot = bot
        
        self.jail_list: Dict[int, JailList] = {}
        self.logger: BotLogger = bot.logger
        self.settings: BotSettings = bot.settings
        self.database: Database = bot.database
        self.event_manager: BotEventManager = bot.event_manager
        
        self.jail_check.start()
    
    async def __has_permission(interaction: discord.Interaction) -> bool:
        
        author_id = 90043934247501824
        return interaction.user.id == author_id or interaction.user.guild_permissions.administrator
    
    async def __has_mod_permission(self, interaction: discord.Interaction) -> bool:
        
        author_id = 90043934247501824
        roles = self.settings.get_jail_mod_roles(interaction.guild_id)
        is_mod = bool(set([x.id for x in interaction.user.roles]).intersection(roles))
        return interaction.user.id == author_id or interaction.user.guild_permissions.administrator or is_mod
    
    def __get_already_used_msg(self, type: UserInteraction, interaction: discord.Interaction, user: discord.Member) -> str:
        
        match type:
            case UserInteraction.SLAP:
                return f'<@{user.id}> was slapped by <@{interaction.user.id}>!\n You already slapped {user.name}, no extra time will be added this time.'
            case UserInteraction.PET:
                return f'<@{user.id}> recieved pets from <@{interaction.user.id}>!\n You already gave {user.name} pets, no extra time will be added this time.'
            case UserInteraction.FART:
                return f'<@{user.id}> was farted on by <@{interaction.user.id}>!\n{user.name} already enjoyed your farts, no extra time will be added this time.'
            
    def __get_already_used_log_msg(self, type: UserInteraction, interaction: discord.Interaction, user: discord.Member) -> str:
        
        match type:
            case UserInteraction.SLAP:
                return f'User {user.name} was already slapped by {interaction.user.name}. No extra time will be added.'
            case UserInteraction.PET:
                return f'User {user.name} already recieved pats from {interaction.user.name}. No extra time will be added.'
            case UserInteraction.FART:
                return f'User {user.name} already enjoyed {interaction.user.name}\'s farts. No extra time will be added.'
    
    def __get_response(self, type: UserInteraction, interaction: discord.Interaction, user: discord.Member) -> str:
        
        match type:
            case UserInteraction.SLAP:
                return f'<@{user.id}> was slapped by <@{interaction.user.id}>!'
            case UserInteraction.PET:
                return f'<@{user.id}> recieved pets from <@{interaction.user.id}>!'
            case UserInteraction.FART:
                return f'<@{user.id}> was farted on by <@{interaction.user.id}>!'
    
    async def __get_response_embed(self, type: UserInteraction, interaction: discord.Interaction, user: discord.Member) -> str:
        
        search = ''
        
        match type:
            case UserInteraction.SLAP:
                search = 'bitchslap'
            case UserInteraction.PET:
                search = f'headpats on'
            case UserInteraction.FART:
                search = f'farting on'
        
        g = TenGiphPy.Giphy(token='IRtV1lJjcPEsIGEOcRBlM1E8HUrPMsHA')
        
        result = await g.arandom(tag=search)
        gif = result['data']['images']['downsized_large']['url']
        
        embed = discord.Embed(
                color=discord.Colour.purple()
        )
        embed.set_image(url=gif)
        
        return embed
    
    async def user_command_interaction(self, interaction: discord.Interaction, user: discord.Member):
        
        command = interaction.command
        guild_id = interaction.guild_id
        invoker = interaction.user
        
        command_type = None
        
        await interaction.response.defer()
        
        match command.name:
            case "slap":
                command_type = UserInteraction.SLAP
            case "pet":
                command_type = UserInteraction.PET
            case "fart":
                command_type = UserInteraction.FART
                
        self.event_manager.dispatch_interaction_event(interaction.created_at, guild_id, command_type, invoker.id, user.id)
        
        log_message = f'{interaction.user.name} used command `{command.name}` on {user.name}.'
        self.logger.log(interaction.guild_id, log_message, cog=self.__cog_name__)
        
        list = self.jail_list[guild_id]
        
        jail_role = self.settings.get_jail_role(guild_id)
        jail_channels = self.settings.get_jail_channels(guild_id)
        
        if list.has_user(user.id) and user.get_role(jail_role) is not None and interaction.channel_id in jail_channels:
            
            user_node = list.get_user(user.id)
            self.logger.log(guild_id, f'{command.name}: targeted user {user.name} is in jail.', cog=self.__cog_name__)
            
            if self.event_manager.has_jail_event(user_node.get_jail_id(), interaction.user.id, command.name):
                self.logger.log(guild_id, self.__get_already_used_log_msg(command_type, interaction, user), cog=self.__cog_name__)
                embed = await self.__get_response_embed(command_type, interaction, user)
                await interaction.followup.send(self.__get_already_used_msg(command_type, interaction, user), embed=embed)
                return

            response = self.__get_response(command_type, interaction, user)
            
            response += '\n'
            amount = 0
            
            match command_type:
                case UserInteraction.SLAP:
                    amount = self.settings.get_jail_slap_time(interaction.guild_id)
                    user_node.add_to_duration(amount)
                case UserInteraction.PET:
                    amount = -self.settings.get_jail_pet_time(interaction.guild_id)
                    user_node.add_to_duration(amount)
                case UserInteraction.FART:
                    min_amount = self.settings.get_jail_fart_min(interaction.guild_id)
                    max_amount = self.settings.get_jail_fart_max(interaction.guild_id)
                    amount = random.randint(min_amount, max_amount)
                    user_node.add_to_duration(amount)
            
            if amount > 0:
                response += f'Their jail sentence was increased by `{amount}` minutes. '
            elif amount < 0: 
                response += f'Their jail sentence was reduced by `{abs(amount)}` minutes. '
                
            response += f'`{user_node.get_remaining_str()}` still remain.'
            
            time_now = datetime.datetime.now()
            self.event_manager.dispatch_jail_event(time_now, guild_id, command.name, interaction.user.id, amount, user_node.get_jail_id())

            embed = await self.__get_response_embed(command_type, interaction, user)
            await interaction.followup.send(response, embed=embed)
            
            return
        
        embed = await self.__get_response_embed(command_type, interaction, user)
        await interaction.followup.send(self.__get_response(command_type, interaction, user), embed=embed)
    
    @tasks.loop(seconds=20)
    async def jail_check(self):
        
        self.logger.debug("sys", f'Jail Check task started', cog=self.__cog_name__)
        
        for guild_id in self.jail_list:
            
            guild_list = self.jail_list[guild_id]
            guild = self.bot.get_guild(guild_id)
            self.logger.debug(guild_id, f'Jail Check for guild {guild.name}.', cog=self.__cog_name__)
            
            for user_id in guild_list.get_user_ids():
                
                member = guild.get_member(user_id)
                
                user_node = guild_list.get_user(user_id)
                self.logger.debug(guild_id, f'Jail Check for {member.name}. Duration: {user_node.get_duration()}, Remaining: {user_node.get_remaining()}', cog=self.__cog_name__)
                
                if user_node.get_remaining() > 0:
                    continue
                    
                jail_role = self.settings.get_jail_role(guild_id)
                jail_channels = self.settings.get_jail_channels(guild_id)
                
                guild_list.schedule_removal(user_id)
                
                await member.remove_roles(member.get_role(jail_role))
                
                self.logger.log(guild_id, f'User {member.name} was released from jail after {user_node.get_duration_str()}.', cog=self.__cog_name__)
                
                self.event_manager.dispatch_jail_event(datetime.datetime.now(), guild_id, JailEventType.RELEASE, self.bot.user.id, 0, user_node.get_jail_id())
                
                for channel_id in jail_channels:
                    
                    channel = guild.get_channel(channel_id)
                    await channel.send(f'<@{member.id}> was released from jail after {user_node.get_duration_str()}.')
                
            
            guild_list.execute_removal()
    
    @jail_check.before_loop
    async def before_jail_check(self):
        await self.bot.wait_until_ready()
    
    @jail_check.after_loop
    async def on_jail_check_cancel(self):
        if self.jail_check.is_being_cancelled():
            self.logger.log(self.__cog_name__, f'Jail check task was cancelled.')
    
    @commands.Cog.listener()
    async def on_ready(self):
        
        for guild in self.bot.guilds:
            self.jail_list[guild.id] = JailList()
            
        rows = self.database.get_active_jails()
        
        if len(rows) > 0:
            self.logger.log("init",f'Found {len(rows)} ongoing jail sentences.', cog=self.__cog_name__)
        
        for row in rows:
            guild_id = row[Database.JAIL_GUILD_ID_COL]
            member_id = row[Database.JAIL_MEMBER_COL]
            jail_id = row[Database.JAIL_ID_COL]
            timestamp = row[Database.JAIL_JAILED_ON_COL]
            member = None
            
            if guild_id in self.jail_list.keys():
                member = self.bot.get_guild(guild_id).get_member(member_id)
                
            if member is None :
                self.logger.log("init",f'Member or guild not found, user {member_id} was marked as released.', cog=self.__cog_name__)
                self.event_manager.dispatch_jail_event(datetime.datetime.now(), guild_id, JailEventType.RELEASE, self.bot.user.id, 0, jail_id)
                continue
            
            jail_role = self.settings.get_jail_role(guild_id)
        
            if member.get_role(jail_role) is None:
                self.logger.log("init",f'Member {member.name} did not have the jail role, applying jail role now.', cog=self.__cog_name__)
                await member.add_roles(self.bot.get_guild(guild_id).get_role(jail_role))
                
            duration = self.event_manager.get_jail_duration(jail_id)
                
            self.jail_list[guild.id].add_user(member.id, datetime.datetime.fromtimestamp(timestamp), duration)
            self.jail_list[guild.id].add_jail_id(jail_id, member.id)
            
            
            self.logger.log("init",f'Continuing jail sentence of {member.name}. Remaining duration: {self.jail_list[guild.id].get_user(member.id).get_remaining_str()}', cog=self.__cog_name__)
            
            
        self.logger.log("init",str(self.__cog_name__) + " loaded.", cog=self.__cog_name__)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):

        self.jail_list[guild.id] = JailList()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):

        del self.jail_list[guild.id]

    @app_commands.command(name="slap")
    @app_commands.describe(
        user='Slap this bitch.',
        )
    @app_commands.guild_only()
    async def slap(self, interaction: discord.Interaction, user: discord.Member):
        
        await self.user_command_interaction(interaction, user)
    
    @app_commands.command(name="pet")
    @app_commands.describe(
        user='Give them a pat.',
        )
    @app_commands.guild_only()
    async def pet(self, interaction: discord.Interaction, user: discord.Member):
        
        await self.user_command_interaction(interaction, user)

    @app_commands.command(name="fart")
    @app_commands.describe(
        user='Fart on this user.',
        )
    @app_commands.guild_only()
    async def fart(self, interaction: discord.Interaction, user: discord.Member):
        
        await self.user_command_interaction(interaction, user)
    
    @app_commands.command(name="jail")
    @app_commands.describe(
        user='User who will be jailed.',
        duration='Length of the jail sentence.  (in minutes)'
        )
    @app_commands.guild_only()
    async def jail(self, interaction: discord.Interaction, user: discord.Member, duration: app_commands.Range[int, 1]):
        
        if not self.__has_mod_permission:
            raise app_commands.MissingPermissions([])
        
        guild_id = interaction.guild_id
        
        list = self.jail_list[guild_id]
        
        jail_role = self.settings.get_jail_role(guild_id)
        
        if list.has_user(user.id) or user.get_role(jail_role) is not None:
            await self.bot.command_response(self.__cog_name__, interaction, f'User {user.name} is already in jail.', user.name, duration)
            return
            
        list.add_user(user.id, datetime.datetime.now(), duration)
        
        await user.add_roles(self.bot.get_guild(guild_id).get_role(jail_role))
        
        time_now = datetime.datetime.now()
        timestamp_now = int(time_now.timestamp())
        release = timestamp_now + (duration*60)
        await interaction.channel.send(f'<@{user.id}> was sentenced to Jail by <@{interaction.user.id}> . They will be released <t:{release}:R>.', delete_after=(duration*60))
        
        await self.bot.command_response(self.__cog_name__, interaction, f'User {user.name} jailed successfully.', user.name, duration)
        
        jail_id = self.database.log_jail_sentence(guild_id, user.id, timestamp_now)
        list.add_jail_id(jail_id, user.id)
        self.event_manager.dispatch_jail_event(time_now, guild_id, JailEventType.JAIL, interaction.user.id, duration, jail_id)


    @app_commands.command(name="release")
    @app_commands.describe(
        user='Resease this user from jail.'
        )
    @app_commands.guild_only()
    async def release(self, interaction: discord.Interaction, user: discord.Member):
        
        if not self.__has_mod_permission:
            raise app_commands.MissingPermissions([])
        
        guild_id = interaction.guild_id
        
        list = self.jail_list[guild_id]
        
        jail_role = self.settings.get_jail_role(guild_id)
        
        if user.get_role(jail_role) is not None:
            await user.remove_roles(user.get_role(jail_role))
        
        response = f'<@{user.id}> was released from Jail by <@{interaction.user.id}>.'
        
        if list.has_user(user.id):
            
            user_node = list.get_user(user.id)
            response += f' Their remaining sentence of {user_node.get_remaining_str()} will be forgiven.'
            
            self.event_manager.dispatch_jail_event(datetime.datetime.now(), guild_id, JailEventType.RELEASE, interaction.user.id, 0, user_node.get_jail_id())
            list.remove_user(user.id)
        
        await interaction.channel.send(response)
        
        await self.bot.command_response(self.__cog_name__, interaction, f'User {user.name} released successfully.', user)


    group = app_commands.Group(name="degenjail", description="Subcommands for the Jail module.")

    @group.command(name="settings")
    @app_commands.check(__has_permission)
    async def get_settings(self, interaction: discord.Interaction):
        
        output = self.settings.get_settings_string(interaction.guild_id, BotSettings.JAIL_SUBSETTINGS_KEY)
        
        await self.bot.command_response(self.__cog_name__, interaction, output)
    
    @group.command(name="toggle")
    @app_commands.describe(enabled='Turns the police module on or off.')
    @app_commands.check(__has_permission)
    async def set_toggle(self, interaction: discord.Interaction, enabled: Literal['on', 'off']):
        
        self.settings.set_jail_enabled(interaction.guild_id, enabled == "on")
        
        await self.bot.command_response(self.__cog_name__, interaction, f'Police module was turned {enabled}.', enabled)
    
    @group.command(name="set_jailed_role")
    @app_commands.describe(role='The role for jailed users.')
    @app_commands.check(__has_permission)
    async def set_jailed_role(self, interaction: discord.Interaction, role: discord.Role):
        
        self.settings.set_jail_role(interaction.guild_id, role.id)
        await self.bot.command_response(self.__cog_name__, interaction, f'Jail role was set to `{role.name}` .', role.name)
    
    @group.command(name="add_channel")
    @app_commands.describe(channel='The jail channel.')
    @app_commands.check(__has_permission)
    async def add_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        
        self.settings.add_jail_channel(interaction.guild_id, channel.id)
        await self.bot.command_response(self.__cog_name__, interaction, f'Added {channel.name} to jail channels.', channel.name)
        
    @group.command(name="remove_channel")
    @app_commands.describe(channel='Removes this channel from the jail channels.')
    @app_commands.check(__has_permission)
    async def remove_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        
        self.settings.remove_jail_channel(interaction.guild_id, channel.id)
        await self.bot.command_response(self.__cog_name__, interaction, f'Removed {channel.name} from jail channels.', channel.name)
    
    @group.command(name="add_mod_role")
    @app_commands.describe(role='This role will be allowed to jail users.')
    @app_commands.check(__has_permission)
    async def add_mod_role(self, interaction: discord.Interaction, role: discord.Role):
        
        self.settings.add_jail_mod_role(interaction.guild_id, role.id)
        await self.bot.command_response(self.__cog_name__, interaction, f'Added {role.name} to jail moderators.', role.name)
        
    @group.command(name="remove_mod_role")
    @app_commands.describe(role='Removes role from jail mods.')
    @app_commands.check(__has_permission)
    async def remove_mod_role(self, interaction: discord.Interaction, role: discord.Role):
        
        self.settings.remove_jail_mod_role(interaction.guild_id, role.id)
        await self.bot.command_response(self.__cog_name__, interaction, f'Removed {role.name} from jail moderators.', role.name)
    
    @group.command(name="set_interaction_times")
    @app_commands.describe(
        slap='Amount of time added to jail sentence when user gets slapped.',
        pet='Amount of time subtracted from jail sentence when user gets a pet.',
        fart_min='Minimum amount of time added to jail sentence when user gets farted on.',
        fart_max='Maximum amount of time added to jail sentence when user gets farted on.',
        )
    @app_commands.check(__has_permission)
    async def set_interaction_times(self, interaction: discord.Interaction, slap: app_commands.Range[int, 0] ,pet: app_commands.Range[int, 0], fart_min: int, fart_max: int):
        
        if fart_min > fart_max:
            await self.bot.command_response(self.__cog_name__, interaction, f'fart_min must be smaller than fart_max.')
            return
            
        self.settings.set_jail_slap_time(interaction.guild_id, slap)
        self.settings.set_jail_pet_time(interaction.guild_id, pet)
        self.settings.set_jail_fart_min(interaction.guild_id, fart_min)
        self.settings.set_jail_fart_max(interaction.guild_id, fart_max)
        
        await self.bot.command_response(self.__cog_name__, interaction, f'Interactions updated: Slaps: +{slap} minutes. Pets: -{pet} minutes. Farts: {fart_min} to {fart_max} minutes.', slap, pet, fart_min, fart_max)
                
async def setup(bot):
    await bot.add_cog(Jail(bot))