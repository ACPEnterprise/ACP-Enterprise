from collections import Counter
from threading import Lock


class SecurityMetrics:
    """Adapter boundary for security counters and future metrics exporters."""

    def __init__(self) -> None:
        self._counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._lock = Lock()

    def increment(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] += 1

    def value(self, name: str, **labels: str) -> int:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            return self._counters[key]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                f"{name}{dict(labels)}": count
                for (name, labels), count in self._counters.items()
            }

    def reset_for_testing(self) -> None:
        with self._lock:
            self._counters.clear()

    def record_audit_action(self, action: str, outcome: str) -> None:
        mapping = {
            "authentication.login": "authentication",
            "authentication.logout": "logout",
            "authentication.password_reset": "password_reset",
            "authentication.password_change": "password_change",
            "authentication.refresh": "refresh_token_rotation",
            "authentication.refresh_replay": "refresh_token_replay",
            "authentication.email_verification": "email_verification",
        }
        category = mapping.get(
            action, "company_administration" if action.startswith("company.") else None
        )
        if category is not None:
            self.increment(
                "security_operations_total", category=category, outcome=outcome
            )


security_metrics = SecurityMetrics()
