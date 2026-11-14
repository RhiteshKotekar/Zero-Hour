"""``VulnerableLinUCB`` (S1) — intentionally unsafe, Experiment C only.

It learns from any authenticated claim's reward, with no evidence gate. It must
never be selected by default wiring; ``make_policy`` only builds it for kind ``"S1"``.
"""

from __future__ import annotations

from samg.domain.enums import ReasonCode
from samg.domain.events import IneligibleLearningEvent, LearningEvent
from samg.learning.linucb import LinUCBPolicy


class VulnerableLinUCB(LinUCBPolicy):
    kind = "S1-VulnerableLinUCB"

    def observe(self, event: LearningEvent) -> None:
        """Update from the event's reward whatever its status or source (the flaw under test)."""
        if event.reward is None:
            raise IneligibleLearningEvent(ReasonCode.INELIGIBLE_STATUS, "no reward to learn from")
        if event.episode_id in self.gate.applied_episodes:
            raise IneligibleLearningEvent(ReasonCode.DUPLICATE_EPISODE, event.episode_id)
        self._apply(event, event.reward)
        self.gate.mark_applied(event)
