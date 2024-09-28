import contextlib
import datetime

import discord

from combat.encounter import EncounterContext
from control.controller import Controller
from control.types import ControllerType
from events.types import UIEventType
from events.ui_event import UIEvent
from view.view_menu import ViewMenu


class EnemyEngageView(ViewMenu):

    DEFAULT_TIMEOUT = 60 * 60

    def __init__(self, controller: Controller, context: EncounterContext):
        timeout = self.DEFAULT_TIMEOUT
        self.enemy = context.opponent.enemy
        if self.enemy.is_boss:
            timeout = None
        super().__init__(timeout=timeout)
        self.controller = controller

        self.context = context
        self.controller_type = ControllerType.COMBAT
        self.controller.register_view(self)
        self.done = False
        self.active = False
        self.timeout_timestamp = None
        self.loaded = False

        if timeout is not None:
            now = datetime.datetime.now().timestamp()
            self.timeout_timestamp = int(now + timeout)

        self.refresh_elements(disabled=(not self.loaded))

    async def listen_for_ui_event(self, event: UIEvent):
        match event.type:
            case UIEventType.COMBAT_ENGAGE_UPDATE:
                encounter_id = event.payload[0]
                if encounter_id != self.context.encounter.id:
                    return
                embed = event.payload[1]
                started = event.payload[2]
                if started:
                    self.active = True
                done = event.payload[3]
                await self.refresh_ui(embed=embed, done=done)
            case UIEventType.COMBAT_LOADED:
                encounter_id = event.payload
                if encounter_id != self.context.encounter.id:
                    return
                self.loaded = True
                await self.refresh_ui()

    async def engage(self, interaction: discord.Interaction):
        event = UIEvent(
            UIEventType.COMBAT_ENGAGE,
            interaction,
            self.id,
        )
        await self.controller.dispatch_ui_event(event)

    async def leave(self, interaction: discord.Interaction):
        event = UIEvent(
            UIEventType.COMBAT_LEAVE,
            interaction,
            self.id,
        )
        await self.controller.dispatch_ui_event(event)

    def refresh_elements(self, disabled: bool = False):
        self.clear_items()
        if not self.done:
            self.add_item(EngageButton(disabled))

    async def refresh_ui(
        self,
        embed: discord.Embed = None,
        done: bool = None,
    ):
        if self.message is None:
            return

        if done is not None and done:
            self.done = done

        self.refresh_elements(disabled=(not self.loaded))

        if embed is None:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                self.controller.detach_view(self)
            return

        if self.active and self.timeout is not None:
            self.timeout = None

        if self.done and self.timeout is None:
            self.timeout = self.DEFAULT_TIMEOUT / 5
            now = datetime.datetime.now().timestamp()
            self.timeout_timestamp = int(now + self.timeout)

        if (not self.active or self.done) and self.timeout_timestamp is not None:
            embed.add_field(
                name=f"Will disappear <t:{self.timeout_timestamp}:R>", value=""
            )

        try:
            await self.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.HTTPException):
            self.controller.detach_view(self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.active and not self.done and self.timeout is not None:
            now = datetime.datetime.now().timestamp()
            self.timeout = max(1, int(self.timeout_timestamp - now))
        return True

    async def on_timeout(self):
        if not self.done:
            event = UIEvent(
                UIEventType.COMBAT_DISAPPEAR,
                self.context,
                self.id,
            )
            await self.controller.dispatch_ui_event(event)
        with contextlib.suppress(discord.NotFound):
            await self.message.delete()
        self.controller.detach_view(self)


class LeaveButton(discord.ui.Button):

    def __init__(self):
        super().__init__(label="Leave", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: EnemyEngageView = self.view

        await view.leave(interaction)


class EngageButton(discord.ui.Button):

    def __init__(self, disabled: bool = False):
        super().__init__(
            label="Engage!", style=discord.ButtonStyle.green, disabled=disabled
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: EnemyEngageView = self.view

        await view.engage(interaction)
