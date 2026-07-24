from datetime import timedelta

# Connectivity display policy is deliberately centralized so operations can
# tune it later without changing projection or UI behavior.
HEARTBEAT_FRESH_FOR = timedelta(seconds=90)
LEASE_EXPIRING_WITHIN = timedelta(minutes=2)
