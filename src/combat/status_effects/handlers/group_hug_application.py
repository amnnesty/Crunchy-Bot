from combat.effects.effect import (
    EffectOutcome,
)
from combat.effects.effect_handler import HandlerContext
from combat.status_effects.status_effect import ActiveStatusEffect
from combat.status_effects.status_effects import GroupHugApplication
from combat.status_effects.status_handler import StatusEffectHandler
from combat.status_effects.types import StatusEffectType
from control.combat.effect_manager import CombatEffectManager
from control.controller import Controller


class GroupHugApplicationHandler(StatusEffectHandler):

    def __init__(self, controller: Controller):
        StatusEffectHandler.__init__(
            self, controller=controller, status_effect=GroupHugApplication()
        )
        self.effect_manager: CombatEffectManager = self.controller.get_service(
            CombatEffectManager
        )

    async def handle(
        self, active_status_effect: ActiveStatusEffect, handler_context: HandlerContext
    ) -> EffectOutcome:
        outcome = EffectOutcome.EMPTY()

        effect_type = active_status_effect.status_effect.effect_type
        if effect_type != self.effect_type:
            return outcome

        if handler_context.target.defeated:
            return outcome

        final_damage = await self.actor_manager.get_damage_after_defense(
            handler_context.target,
            handler_context.skill.base_skill.skill_effect,
            handler_context.damage_instance.value,
        )
        inital_source_actor = handler_context.context.get_actor_by_id(
            active_status_effect.event.source_id
        )
        context = handler_context.context
        target = handler_context.target
        application_outcome = await self.effect_manager.apply_status(
            context,
            inital_source_actor,
            target,
            StatusEffectType.GROUP_HUG_DAMAGE,
            1,
            final_damage,
        )
        return application_outcome
