import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.platform.security.metrics import security_metrics


logger = logging.getLogger("acp.security.authorization")


@dataclass(frozen=True)
class AuthorizationDenial:
    reason: str
    actor_user_id: UUID | None = None
    company_id: UUID | None = None
    branch_id: UUID | None = None
    permission_code: str | None = None
    resource: str | None = None


class AuthorizationDecisionLogger:
    @staticmethod
    def denied(decision: AuthorizationDenial) -> None:
        security_metrics.increment(
            "authorization_denials_total", reason=decision.reason
        )
        logger.warning(
            "authorization_denied",
            extra={
                "security_decision": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_user_id": str(decision.actor_user_id)
                    if decision.actor_user_id
                    else None,
                    "company_id": str(decision.company_id)
                    if decision.company_id
                    else None,
                    "branch_id": str(decision.branch_id)
                    if decision.branch_id
                    else None,
                    "permission": decision.permission_code,
                    "resource": decision.resource,
                    "reason": decision.reason,
                }
            },
        )


authorization_decision_logger = AuthorizationDecisionLogger()
