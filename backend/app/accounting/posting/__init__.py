"""Deterministic domain-fact to Accounting Core journal posting."""

from app.accounting.posting.contracts import (
    PostingFact,
    PostingLeg,
    PostingOutcome,
    PostingReceipt,
    PostingRule,
)
from app.accounting.posting.receipts import DomainPostingReceiptSink
from app.accounting.posting.rules import PostingRuleRegistry
from app.accounting.posting.service import AutomatedPostingService

__all__ = [
    "AutomatedPostingService",
    "DomainPostingReceiptSink",
    "PostingFact",
    "PostingLeg",
    "PostingOutcome",
    "PostingReceipt",
    "PostingRule",
    "PostingRuleRegistry",
]
