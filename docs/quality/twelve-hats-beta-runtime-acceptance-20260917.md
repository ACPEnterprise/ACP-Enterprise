# Twelve Hats Beta runtime acceptance — 2026-09-17

- Protected and deployed SHA: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`
- DNS: `beta.twelve-hats.com A 162.243.234.193`
- Preview preserved: yes
- Production/app hostname touched: no

## Accepted

- Preview/Beta connectivity verifier passed.
- Both hostnames report the same healthy backend SHA, PostgreSQL and Redis state.
- Beta TLS is valid through 2026-12-15; automatic renewal information is active.
- All core tenant and Mission Control containers are healthy with zero restarts.
- `/assets` and `/assets/` return the application shell on both hostnames.
- Preview Mission Control and Engineering pages return 200; unauthenticated API returns
  401. Beta internal surfaces return 404.
- Activation and reset pages return `no-referrer`; a non-secret canary was absent from
  Caddy and frontend logs.
- Scheduled database backup checksum and archive catalog validation passed.
- Host admission passed at 82% disk utilization.
- The five-minute local connectivity monitor was installed from protected authority,
  enabled, executed successfully, and has no failed systemd unit.

## Open gates

- `/support` and `/privacy` remain the generic application shell. Approved legal and
  support content is a human/legal prerequisite for enabling
  `REQUIRE_PUBLIC_METADATA=1` or publishing those URLs to App Store Connect.
- Disk utilization is below the 85% warning threshold but trending upward. The host
  contains 295 release directories, 1.633 GiB of stopped-container data and 8.603 GiB
  of build cache. Release must establish retention classification before targeted
  cleanup; global prune remains prohibited.
- There is no explicit previous-release pointer. The current pointer resolves to
  `/opt/acp-enterprise/releases/enterprise-beta-b527d75e`. Previous directories and
  image digests exist, but rollback selection still requires a recorded compatible
  SHA/schema decision.
- Off-host encrypted backup replication, isolated restore cadence, RPO/RTO, external
  alert transport and named responder remain owner/provider decisions.
- A cross-domain Workforce timeline request returns 500 because
  `employee_timeline.py` reads nonexistent `Role.display_name` instead of the canonical
  role name. Workforce owns that bounded repair.

## New candidate

PR #410 minimizes general query-bearing container access logs. It remains pending
Enterprise integration and deployed canary acceptance.
