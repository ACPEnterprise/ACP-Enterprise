# LIA threat model v1

| Threat | Boundary | Mechanical mitigation |
| --- | --- | --- |
| Cross-Company access | Principal/retrieval/tool input | Company predicate before retrieval; foreign Company input denied |
| Unauthorized Branch access | Principal/retrieval/conversation | active-or-authorized Branch predicates; principal digest invalidates removed grants |
| Persona privilege escalation | Source/tool registry | permissions, never titles or persona labels, select capability |
| Prompt injection | Untrusted content | business text remains labeled data and cannot alter policy/tool/principal objects |
| Secret exfiltration | Evidence admission | credential/secret source class is ineligible; deterministic secret-marker rejection |
| Payroll privacy | Source registry | adapter blocked until server-resolved Employee own-data contract exists |
| Customer overexposure | Domain adapter | permission and minimum-necessary projection required before admission |
| Stale authorization | Conversation/session | every request reauthorizes; authorization/credential/Branch digest mismatch invalidates context |
| Stale proposed action | Action contract | target version, evidence digest, principal digest, expiry, and idempotency identity bound |
| Action replay | Domain execution boundary | proposal identity differs from conversation; owning domain enforces idempotency |
| Unsafe tool call | Tool registry | no generic API; typed extra-forbid input plus server-side scope/version validation |
| Provider direct mutation | Provider boundary | candidates cannot execute; executable tool registry is empty |
| Hallucinated fact | Answer validation | unknown evidence ID is unsupported; structured numeric/temporal claims require exact evidence |
| Contradictory evidence | Evidence envelope | conflict is preserved and blocks supported answer classification |
| Malicious attachment/URL | Untrusted/network boundary | no filesystem execution, unrestricted URL, browser, or network tool exists |
| Conversation-history leakage | Conversation authority | no durable transcript policy; old context does not preserve permissions |
| Hidden reasoning exposure | Persistence/audit | chain-of-thought persistence prohibited; audit excludes prompt/evidence payloads |
| Provider outage/uncertainty | Provider state | explicit non-authoritative failure states; no business state mutation or blind retry |
| Production crossover | Environment/action risk | non-Production principal context; Production autonomous mutation disabled |

Residual gates are explicit: transcript retention policy, provider admission, Economics
adapter acceptance, Payroll own-data adapter, customer minimum-necessary projection,
and integrated PostgreSQL/Preview qualification. None is replaced by a hidden default.
