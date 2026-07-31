from uuid import UUID

from app.economics.domain import (
    BusinessFact,
    Confidence,
    EconomicCategory,
    EvidenceKind,
    EvidenceReference,
    MeasuredCost,
    MeasurementStatus,
    ProfitMeasurement,
)

ENGINE_VERSION = "business-economics/1"


class MeasurementEngine:
    @staticmethod
    def _total(
        category: EconomicCategory, facts: tuple[BusinessFact, ...], currency: str
    ) -> MeasuredCost:
        selected = tuple(fact for fact in facts if fact.category is category)
        known = tuple(fact for fact in selected if fact.amount_minor is not None)
        unknown = tuple(fact for fact in selected if fact.amount_minor is None)
        evidence = tuple(reference for fact in selected for reference in fact.evidence)
        if not selected or unknown:
            explanation = (
                f"{category.value} is unknown because no measured fact exists."
                if not selected
                else f"{category.value} is unknown because {len(unknown)} fact(s) lack values."
            )
            return MeasuredCost(
                category=category,
                amount_minor=None,
                currency=currency,
                confidence=Confidence(MeasurementStatus.UNKNOWN, 0, explanation),
                evidence=evidence,
            )
        status = (
            MeasurementStatus.ESTIMATED
            if any(
                fact.confidence.status is MeasurementStatus.ESTIMATED for fact in known
            )
            else MeasurementStatus.MEASURED
        )
        percentage = min(fact.confidence.percentage for fact in known)
        return MeasuredCost(
            category=category,
            amount_minor=sum(fact.amount_minor or 0 for fact in known),
            currency=currency,
            confidence=Confidence(
                status,
                percentage,
                f"Summed {len(known)} evidence-backed {category.value} fact(s).",
            ),
            evidence=evidence,
        )

    @staticmethod
    def _derived(
        name: EconomicCategory,
        minuend: MeasuredCost,
        subtrahends: tuple[MeasuredCost, ...],
        currency: str,
        explanation: str,
    ) -> MeasuredCost:
        inputs = (minuend, *subtrahends)
        evidence = tuple(reference for value in inputs for reference in value.evidence)
        if any(value.amount_minor is None for value in inputs):
            return MeasuredCost(
                category=name,
                amount_minor=None,
                currency=currency,
                confidence=Confidence(
                    MeasurementStatus.UNKNOWN,
                    0,
                    f"{explanation} At least one required component is unknown.",
                ),
                evidence=evidence,
            )
        status = (
            MeasurementStatus.ESTIMATED
            if any(
                value.confidence.status is MeasurementStatus.ESTIMATED
                for value in inputs
            )
            else MeasurementStatus.MEASURED
        )
        return MeasuredCost(
            category=name,
            amount_minor=(minuend.amount_minor or 0)
            - sum(value.amount_minor or 0 for value in subtrahends),
            currency=currency,
            confidence=Confidence(
                status,
                min(value.confidence.percentage for value in inputs),
                explanation,
            ),
            evidence=evidence,
        )

    @classmethod
    def measure(
        cls, subject_type: str, subject_id: UUID, facts: tuple[BusinessFact, ...]
    ) -> ProfitMeasurement:
        if not facts:
            raise ValueError("profit measurement requires business facts")
        currencies = {fact.currency.upper() for fact in facts}
        subjects = {(fact.subject_type, fact.subject_id) for fact in facts}
        periods = {(fact.period_start, fact.period_end) for fact in facts}
        if len(currencies) != 1:
            raise ValueError("profit measurement cannot mix currencies")
        if subjects != {(subject_type, subject_id)}:
            raise ValueError("all facts must belong to the measured subject")
        if len(periods) != 1:
            raise ValueError("all facts must cover the same measurement period")
        currency = currencies.pop()
        input_categories = (
            EconomicCategory.REVENUE,
            EconomicCategory.LABOR,
            EconomicCategory.MATERIALS,
            EconomicCategory.EQUIPMENT,
            EconomicCategory.TRUCK,
            EconomicCategory.OVERHEAD,
        )
        totals = {
            category: cls._total(category, facts, currency)
            for category in input_categories
        }
        direct_costs = tuple(
            totals[category]
            for category in (
                EconomicCategory.LABOR,
                EconomicCategory.MATERIALS,
                EconomicCategory.EQUIPMENT,
                EconomicCategory.TRUCK,
            )
        )
        gross = cls._derived(
            EconomicCategory.GROSS_PROFIT,
            totals[EconomicCategory.REVENUE],
            direct_costs,
            currency,
            "Gross profit equals revenue less labor, materials, equipment, and truck costs.",
        )
        net = cls._derived(
            EconomicCategory.NET_PROFIT,
            gross,
            (totals[EconomicCategory.OVERHEAD],),
            currency,
            "Net profit equals gross profit less allocated overhead.",
        )
        evidence_by_key: dict[
            tuple[EvidenceKind, str, str, str], EvidenceReference
        ] = {}
        for fact in facts:
            for reference in fact.evidence:
                key = (
                    reference.kind,
                    reference.reference_id,
                    reference.source_system,
                    reference.source_version,
                )
                evidence_by_key[key] = reference
        reasoning = EvidenceReference(
            kind=EvidenceKind.REASONING,
            reference_id=ENGINE_VERSION,
            source_system="business_economics",
            source_version=ENGINE_VERSION,
            source_record_type="measurement_formula",
            content_digest=(
                "cb8a23a67b7d90c1bf4c21bb6e902b726c761878c104a3fe299d29fc7ba89e53"
            ),
            observed_at=max(fact.occurred_at for fact in facts),
            explanation=(
                "Gross profit is revenue less direct costs; net profit is gross "
                "profit less allocated overhead. Unknown inputs propagate."
            ),
        )
        evidence_by_key[
            (
                reasoning.kind,
                reasoning.reference_id,
                reasoning.source_system,
                reasoning.source_version,
            )
        ] = reasoning
        overall = net.confidence
        period_start, period_end = periods.pop()
        return ProfitMeasurement(
            subject_type=subject_type,
            subject_id=subject_id,
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            revenue=totals[EconomicCategory.REVENUE],
            labor=totals[EconomicCategory.LABOR],
            materials=totals[EconomicCategory.MATERIALS],
            equipment=totals[EconomicCategory.EQUIPMENT],
            truck=totals[EconomicCategory.TRUCK],
            overhead=totals[EconomicCategory.OVERHEAD],
            gross_profit=gross,
            net_profit=net,
            confidence=overall,
            evidence=tuple(evidence_by_key.values()),
            input_fact_ids=tuple(sorted((fact.id for fact in facts), key=str)),
            input_allocation_ids=(),
            engine_version=ENGINE_VERSION,
        )
