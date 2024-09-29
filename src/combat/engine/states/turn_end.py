import datetime

from combat.encounter import EncounterContext
from combat.engine.states.state import State
from combat.engine.types import StateType
from combat.skills.types import StatusEffectTrigger
from control.controller import Controller
from events.bot_event import BotEvent
from events.combat_event import CombatEvent
from events.encounter_event import EncounterEvent
from events.types import CombatEventType, EncounterEventType, EventType


class TurnEndState(State):
    def __init__(self, controller: Controller, context: EncounterContext):
        super().__init__(controller, context)
        self.state_type: StateType = StateType.TURN_END
        self.next_state: StateType = None

    async def startup(self):
        actor = self.context.current_actor

        outcome = await self.status_effect_manager.handle_turn_status_effects(
            self.context, actor, StatusEffectTrigger.END_OF_TURN
        )
        if outcome.embed_data is not None:
            status_effect_embed = self.embed_manager.get_status_effect_embed(
                actor, outcome.embed_data
            )
            await self.discord.append_embed_to_round(self.context, status_effect_embed)

        outcomes = (
            await self.status_effect_manager.handle_applicant_turn_status_effects(
                self.context, actor
            )
        )
        for actor_id, outcome in outcomes.items():
            if outcome.embed_data is not None:
                status_effect_embed = self.embed_manager.get_status_effect_embed(
                    self.context.get_actor_by_id(actor_id), outcome.embed_data
                )
                await self.discord.append_embed_to_round(
                    self.context, status_effect_embed
                )

        if actor.is_enemy:
            combat_event_type = CombatEventType.ENEMY_END_TURN
        else:
            combat_event_type = CombatEventType.MEMBER_END_TURN

        event = CombatEvent(
            datetime.datetime.now(),
            self.context.encounter.guild_id,
            self.context.encounter.id,
            actor.id,
            actor.id,
            None,
            None,
            None,
            None,
            combat_event_type,
        )
        await self.controller.dispatch_event(event)

        await self.common.check_actor_defeat(self.context)

        self.next_state = StateType.TURN_START
        if self.context.initiative[-1] == actor or self.context.reset_initiative:
            self.next_state = StateType.ROUND_END
            self.context.reset_initiative = False

        self.context._last_actor = self.context._current_actor
        self.context._current_initiative.rotate(-1)
        self.context._current_actor = self.context._current_initiative[0]

        self.done = True

    async def handle(self, event: BotEvent) -> bool:
        update = False
        if not event.synchronized:
            return update
        match event.type:
            case EventType.ENCOUNTER:
                encounter_event: EncounterEvent = event
                if encounter_event.encounter_id != self.context.encounter.id:
                    return update

                match encounter_event.encounter_event_type:
                    case EncounterEventType.MEMBER_ENGAGE:
                        await self.common.add_member_to_encounter(
                            encounter_event.member_id, self.context
                        )
                    case EncounterEventType.MEMBER_REQUEST_JOIN:
                        await self.common.add_member_join_request(
                            encounter_event.member_id, self.context
                        )
                    case EncounterEventType.END:
                        self.next_state = StateType.POST_ENCOUNTER
                        self.done = True
                        await self.common.force_end(self.context)
                        update = True

        return update

    async def update(self):
        await self.discord.refresh_round_overview(self.context)
        enemy_embed = await self.embed_manager.get_combat_embed(self.context)
        message = await self.discord.get_previous_enemy_info(self.context.thread)
        if message is not None:
            await self.discord.edit_message(message, embed=enemy_embed)
