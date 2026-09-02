"""Provider-neutral seam for future Employee push delivery, not inbox authority."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class SafeEmployeeNotification:
    notification_id: UUID
    employee_id: UUID
    notification_class: Literal[
        "assignment_changed",
        "schedule_changed",
        "operational_notice",
        "security_notice",
        "attention_reference",
    ]
    title: str
    safe_summary: str
    deep_link_reference: str | None

    def validate_lock_screen(self) -> None:
        combined = f"{self.title} {self.safe_summary}".lower()
        prohibited = (
            "payment",
            "balance",
            "payroll",
            "access code",
            "gate code",
            "customer phone",
            "customer email",
        )
        if any(value in combined for value in prohibited):
            raise ValueError("Employee notification is not lock-screen safe.")


@dataclass(frozen=True)
class PushDeliveryResult:
    outcome: Literal["accepted", "rejected", "uncertain", "provider_required"]
    provider_reference: str | None = None
    safe_error_code: str | None = None


class EmployeePushProvider(Protocol):
    async def deliver(
        self, notification: SafeEmployeeNotification
    ) -> PushDeliveryResult: ...


class UnconfiguredPushProvider:
    async def deliver(
        self, notification: SafeEmployeeNotification
    ) -> PushDeliveryResult:
        notification.validate_lock_screen()
        return PushDeliveryResult(outcome="provider_required")
