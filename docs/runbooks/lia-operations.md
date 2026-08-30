# LIA operations

## Health and readiness

Call `GET /api/v1/lia/readiness` with a normal authenticated tenant context. A
healthy provider-neutral deployment reports `PRODUCT_READY_PROVIDER_GATE` and
`AI_PROVIDER_NOT_CONFIGURED` until a protected model provider is deliberately
configured. This is truthful readiness, not an outage.

Use the `/lia` workspace to verify deterministic evidence retrieval. Evidence is
permission-selected before querying. A forbidden result should be investigated
through membership, branch access and domain permission authority; never broaden
access simply to make an answer appear.

## Incorrect or incomplete answers

Record the safe request ID, classification, evidence labels and evidence digest.
Do not copy protected business text into tickets. Inspect the cited authoritative
domain result first. LIA feedback never rewrites that domain fact.

## Provider outage or disablement

Disable the provider through protected backend runtime configuration. LIA must
continue to label deterministic summaries correctly and must never fabricate a
generative answer. Rotate provider credentials only through the accepted secret
delivery mechanism. Never print or place credentials in shell arguments.

## Data-leak response

Disable LIA access at the runtime/release gate, preserve safe request and audit
identities, rotate any potentially exposed credential, and follow the security
incident process. Do not place prompts, answers, tokens or protected rows in
ordinary logs or incident chat.
