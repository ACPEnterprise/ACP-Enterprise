# Dispatch, Scheduling, and My Day real operability 1

## Current-authority reconciliation

This candidate starts from Operations `b30d43d5b98cad47610f5a3973a8419b9cff98b1`
with protected authority `cb207f0aad1902df52ff461ab2e9dc25757e073e`.
It does not merge a historical branch.

- `work/scheduling-dispatch-operational-product-1` is patch-equivalent to current
  authority and was not replayed.
- The current-valid Day/Week/Work Week/Month, crowded-month, booking, recovery,
  and CSR operator behavior from the two later historical candidates is already
  represented by protected successors. No divergent historical commit was
  cherry-picked.

## Bounded corrections

- Day Scheduling and live-day Dispatch timelines now show a current-time marker
  for today within the visible operating window.
- My Day uses the active Branch timezone for its service-day boundary, falling
  back to Company timezone only when no active Branch exists.
- My Day now carries and displays the authoritative Job service type alongside
  Job state, Customer, service Location, arrival window, assignment state, and
  normal Job navigation.
- My Day errors use the existing safe operator-error projection rather than
  presenting every authorization, identity, or dependency condition as a
  network outage.

## Chain proof

A PostgreSQL-backed integration creates a real-shaped Customer, Location, Job,
Appointment, canonical Employee, and active Dispatch assignment through existing
models. The normal My Day service resolves the authenticated Membership to that
Employee and returns the same Appointment and Job, including Customer, Location,
service type, and arrival window. No synthetic fallback is added to product code.

Current Scheduling consumes canonical Appointment reads and Job/Dispatch
projections. Dispatch uses the same Appointment assignment authority. My Day
accepts active primary and crew assignments only and preserves Company,
authorized-Branch, and own-Employee scope.

## Remaining gates

- Available-but-unbooked technician lanes cannot be asserted without bounded
  Workforce availability evidence. The calendar truthfully labels open visual
  space as unbooked rather than claiming availability.
- Drag/drop is not enabled because the existing optimistic-concurrency
  reschedule form is the sanctioned safe mutation path.
- Real closure requires a deployed candidate, an owner-sanctioned real
  Appointment, and a real field Employee session. No real record was mutated by
  this qualification.

## Qualification

- Fresh PostgreSQL zero-to-head: passed.
- Field Service, My Day, Dispatch, Scheduling, Jobs, Workforce: 353 passed.
- Focused frontend Scheduling, Dispatch, My Day: 37 passed.
- Full frontend: 602 passed; 3 unrelated current-authority assertions failed
  because they expect superseded Engineering/Payroll labels.
- Ruff, MyPy, Python compilation, ESLint, TypeScript, Vite production build,
  and diff check: passed.
- No schema migration.
