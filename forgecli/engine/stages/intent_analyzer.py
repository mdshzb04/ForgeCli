"""Stage 1 — Intent Analyzer.

Classifies the user's prompt into an :class:`Intent` using the
:class:`HeuristicIntentClassifier`. The result is stored in
``context.engine.intent_analysis``.
"""

from __future__ import annotations

from forgecli.engine.context import IntentAnalysis
from forgecli.engine.execution import StageContext, StageResult, StageStatus
from forgecli.orchestrator import HeuristicIntentClassifier
from forgecli.plugins import IntentClassifier


class IntentAnalyzerStage:
    """Classify the user prompt into an :class:`Intent`."""

    name = "intent-analyzer"

    def __init__(self, classifier: IntentClassifier | None = None) -> None:
        self._classifier = classifier or HeuristicIntentClassifier()

    async def __call__(self, context: StageContext) -> StageResult:
        prediction = self._classifier.classify(context.engine.prompt)
        context.engine.intent_analysis = IntentAnalysis(
            intent=prediction.intent,
            confidence=prediction.confidence,
            rationale=prediction.rationale,
        )
        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "intent": prediction.intent.value,
                "confidence": prediction.confidence,
            },
            notes=prediction.rationale,
        )
