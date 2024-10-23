from combat.effects.effect import (
    EffectOutcome,
)
from combat.effects.effect_handler import HandlerContext
from combat.status_effects.status_effect import ActiveStatusEffect
from combat.status_effects.status_effects import GroupHugEffect
from combat.status_effects.status_handler import StatusEffectHandler
from combat.status_effects.types import StatusEffectType
from control.combat.effect_manager import CombatEffectManager
from control.controller import Controller


class GroupHugEffectHandler(StatusEffectHandler):

    def __init__(self, controller: Controller):
        StatusEffectHandler.__init__(
            self, controller=controller, status_effect=GroupHugEffect()
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

        source_actor = handler_context.source
        context = handler_context.context
        effect_outcomes = []
        for combatant in context.active_combatants:
            application_outcome = await self.effect_manager.apply_status(
                context,
                source_actor,
                combatant,
                StatusEffectType.GROUP_HUG_APPLICATION,
                1,
            )
            effect_outcomes.append(application_outcome)
        outcome = await self.combine(effect_outcomes, handler_context)
        return outcome
