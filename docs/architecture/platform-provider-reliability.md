# Provider reliability and failure injection

Provider integrations must preserve what ACP actually knows. A transport failure
proven to occur before acceptance is different from an accepted request whose
response was lost. The shared contract records provider/version, operation
identity, request digest, attempt sequence, knowledge state, and a safe provider
reference digest when one exists.

Only a versioned policy may permit retry before acceptance. `UNCERTAIN` always
requires reconciliation before retry. `ACCEPTED`, `ACKNOWLEDGED`, and `REJECTED`
are never blindly retried. Maximum attempts are optional policy authority; the
Platform does not invent global intervals, attempt limits, or financial-provider
behavior.

Deterministic fault injection covers lost responses, provider timeout or
uncertainty, Redis loss, and storage loss. The API raises before injection in any
environment other than `test`, mechanically excluding Preview and Production.
Tests use synthetic provider evidence only and make no external calls.
