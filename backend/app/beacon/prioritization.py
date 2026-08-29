from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.beacon.contracts import (
    BeaconPriorityBand,
    BeaconRankingFactorAvailability,
    BeaconSeverity,
    BeaconSignalSource,
)
from app.beacon.records import (
    BeaconPriority,
    BeaconRankingFactor,
    BeaconSignal,
    BeaconSupportingFact,
)

SEVERITY_POINTS = {
    BeaconSeverity.CRITICAL: 400,
    BeaconSeverity.IMPORTANT: 300,
    BeaconSeverity.ATTENTION: 200,
    BeaconSeverity.INFORMATION: 100,
}
TIE_BREAK_SEMANTICS = (
    "Higher score first; ties resolve by severity, source, rule code, then stable "
    "signal identifier."
)


class BeaconPrioritizer:
    """Assigns explainable owner-attention priority using bounded fact rules."""

    @classmethod
    def prioritize(cls, signals: tuple[BeaconSignal, ...]) -> tuple[BeaconSignal, ...]:
        evaluated = tuple(cls._evaluate(signal) for signal in signals)
        ordered = sorted(
            evaluated,
            key=lambda signal: (
                -signal.priority.score,
                -SEVERITY_POINTS[signal.severity],
                signal.source.value,
                signal.rule_code,
                str(signal.id),
            ),
        )
        return tuple(
            replace(signal, priority=replace(signal.priority, rank=index))
            for index, signal in enumerate(ordered, start=1)
        )

    @classmethod
    def _evaluate(cls, signal: BeaconSignal) -> BeaconSignal:
        factors = (
            cls._severity_factor(signal),
            cls._affected_records_factor(signal),
            cls._condition_age_factor(signal),
            cls._financial_exposure_factor(signal),
        )
        score = sum(factor.contribution for factor in factors)
        priority = BeaconPriority(
            band=cls._band(score),
            score=score,
            rank=0,
            ranking_factors=factors,
            explanation=(
                f"{signal.severity.value.title()} severity contributes "
                f"{factors[0].contribution} points; measured ranking factors "
                f"contribute {score - factors[0].contribution} points. "
                "Unavailable factors are explicitly excluded."
            ),
            evaluated_at=signal.created_at,
            tie_break_semantics=TIE_BREAK_SEMANTICS,
        )
        return replace(signal, priority=priority)

    @staticmethod
    def _severity_factor(signal: BeaconSignal) -> BeaconRankingFactor:
        contribution = SEVERITY_POINTS[signal.severity]
        return BeaconRankingFactor(
            name="severity",
            value=signal.severity.value,
            unit=None,
            availability=BeaconRankingFactorAvailability.MEASURED,
            contribution=contribution,
            explanation=(
                f"Explicit {signal.severity.value} severity contributes "
                f"{contribution} points."
            ),
        )

    @classmethod
    def _affected_records_factor(cls, signal: BeaconSignal) -> BeaconRankingFactor:
        fact_name = {
            BeaconSignalSource.SCHEDULING: "overdue_appointment_count",
            BeaconSignalSource.JOBS: "paused_job_count",
            BeaconSignalSource.INVOICES: "past_due_invoice_count",
        }.get(signal.source)
        if fact_name is None:
            return cls._not_applicable(
                "affected_records",
                "No approved affected-record ranking exists for this signal.",
            )
        fact = cls._fact(signal, fact_name)
        if fact is None:
            return cls._not_applicable(
                "affected_records",
                "No authoritative affected-record count is available; it contributes "
                "no points.",
            )
        value = int(fact.value)
        contribution = min(value, 20)
        return BeaconRankingFactor(
            name="affected_records",
            value=value,
            unit="records",
            availability=BeaconRankingFactorAvailability.MEASURED,
            contribution=contribution,
            explanation=(
                f"{value} affected records contribute one point each, capped at 20."
            ),
        )

    @classmethod
    def _condition_age_factor(cls, signal: BeaconSignal) -> BeaconRankingFactor:
        policy = {
            BeaconSignalSource.SCHEDULING: ("oldest_overdue_hours", 4, "hours"),
            BeaconSignalSource.JOBS: ("oldest_pause_hours", 4, "hours"),
            BeaconSignalSource.INVOICES: ("oldest_days_past_due", 1, "days"),
        }.get(signal.source)
        if policy is None:
            return cls._not_applicable(
                "condition_age",
                "No approved age or urgency ranking exists for this signal.",
            )
        fact_name, divisor, unit = policy
        fact = cls._fact(signal, fact_name)
        if fact is None:
            return cls._not_applicable(
                "condition_age",
                "No authoritative condition age is available; it contributes no points.",
            )
        value = int(fact.value)
        contribution = min(value // divisor, 30)
        interval = "day" if divisor == 1 else f"{divisor}-hour interval"
        return BeaconRankingFactor(
            name="condition_age",
            value=value,
            unit=unit,
            availability=BeaconRankingFactorAvailability.MEASURED,
            contribution=contribution,
            explanation=(
                f"The oldest condition is {value} {unit}; one point per {interval}, "
                "capped at 30."
            ),
        )

    @classmethod
    def _financial_exposure_factor(cls, signal: BeaconSignal) -> BeaconRankingFactor:
        fact = cls._fact(signal, "past_due_invoice_face_value")
        if fact is None:
            return cls._not_applicable(
                "financial_exposure",
                "Financial exposure is not applicable to this signal and contributes "
                "no points.",
            )
        value = Decimal(str(fact.value))
        contribution = min(int(value // Decimal(1000)), 20)
        return BeaconRankingFactor(
            name="financial_exposure",
            value=str(value.quantize(Decimal("0.01"))),
            unit="currency_amount",
            availability=BeaconRankingFactorAvailability.MEASURED,
            contribution=contribution,
            explanation=(
                "The authoritative invoice face value contributes one point per "
                "$1,000, capped at 20."
            ),
        )

    @staticmethod
    def _fact(signal: BeaconSignal, name: str) -> BeaconSupportingFact | None:
        return next(
            (fact for fact in signal.supporting_facts if fact.name == name), None
        )

    @staticmethod
    def _not_applicable(name: str, explanation: str) -> BeaconRankingFactor:
        return BeaconRankingFactor(
            name=name,
            value=None,
            unit=None,
            availability=BeaconRankingFactorAvailability.NOT_APPLICABLE,
            contribution=0,
            explanation=explanation,
        )

    @staticmethod
    def _band(score: int) -> BeaconPriorityBand:
        if score >= 400:
            return BeaconPriorityBand.CRITICAL
        if score >= 330:
            return BeaconPriorityBand.IMMEDIATE
        if score >= 200:
            return BeaconPriorityBand.IMPORTANT
        return BeaconPriorityBand.MONITOR


beacon_prioritizer = BeaconPrioritizer()
