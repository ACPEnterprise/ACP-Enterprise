from datetime import date

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.posting.contracts import PostingFact, PostingRule


class PostingRuleRegistry:
    """Immutable runtime view of Finance-approved posting rules."""

    def __init__(self, rules: tuple[PostingRule, ...]) -> None:
        self._rules = rules
        self._validate()

    def _validate(self) -> None:
        for rule in self._rules:
            if not rule.version.strip() or not rule.event_type.strip():
                raise AccountingValidation("Posting rule identity is required")
            if rule.effective_to is not None and rule.effective_to < rule.effective_from:
                raise AccountingValidation("Posting rule effective range is invalid")
            if len(rule.legs) < 2:
                raise AccountingValidation("Posting rules require at least two legs")
            if len({(leg.component, leg.side) for leg in rule.legs}) != len(rule.legs):
                raise AccountingValidation("Posting rule legs must be unique")
        enabled = tuple(rule for rule in self._rules if rule.enabled)
        for index, left in enumerate(enabled):
            for right in enabled[index + 1 :]:
                if (
                    left.company_id == right.company_id
                    and left.event_type == right.event_type
                    and self._overlap(left, right)
                ):
                    raise AccountingConflict(
                        "Approved posting rules overlap for Company and event type"
                    )

    @staticmethod
    def _overlap(left: PostingRule, right: PostingRule) -> bool:
        maximum = date.max
        return left.effective_from <= (right.effective_to or maximum) and (
            right.effective_from <= (left.effective_to or maximum)
        )

    def resolve(self, fact: PostingFact) -> PostingRule:
        matches = tuple(
            rule
            for rule in self._rules
            if rule.enabled
            and rule.company_id == fact.company_id
            and rule.event_type == fact.event_type
            and rule.effective_from <= fact.effective_date
            and (rule.effective_to is None or fact.effective_date <= rule.effective_to)
        )
        if len(matches) != 1:
            raise AccountingValidation(
                "Exactly one approved effective posting rule is required"
            )
        return matches[0]
