# OM2-B authenticated browser qualification runbook

This runbook qualifies the isolated synthetic runtime. It does not establish actual All County operational acceptance, and Owner Acceptance Finding 001 remains open until actual protected source and browser acceptance pass.

## Security and prerequisites

- Use the existing runtime at `http://127.0.0.1:18182/`; do not expose it publicly.
- Obtain the disposable owner credential JSON and acceptance receipt through the approved local custody channel. Never paste credentials into chat, terminal arguments, logs, source files, or Git.
- The credential file must be owned by the reviewer and mode `0600`. The harness refuses broader permissions.
- Confirm the exact commit served by the runtime with Laptop Master before setting `OM2B_SERVING_SHA`.
- Use a Chromium-compatible executable approved for the qualification host. The harness creates and removes its own temporary browser profile.

## Disposable owner login

Set the credential path without displaying its contents:

```bash
export OM2B_ACCEPTANCE_CREDENTIAL_FILE=/approved/local/custody/owner-credentials.json
test "$(stat -f %Lp "$OM2B_ACCEPTANCE_CREDENTIAL_FILE")" = 600
```

Open `http://127.0.0.1:18182/login` in the approved browser. Copy one field at a time without printing it:

```bash
jq -r '.email' "$OM2B_ACCEPTANCE_CREDENTIAL_FILE" | pbcopy
# Paste into Email, then overwrite the clipboard with the password:
jq -r '.password' "$OM2B_ACCEPTANCE_CREDENTIAL_FILE" | pbcopy
# Paste into Password and sign in, then clear the clipboard:
printf '' | pbcopy
```

When inspection is complete, sign out, clear the clipboard again, and run `unset OM2B_ACCEPTANCE_CREDENTIAL_FILE`. Credential disposal or rotation remains a custody-owner action; do not delete or rotate it while the owner inspection runtime is reserved.

## Reproducible browser harness

From a clean checkout of the published task branch, set only local paths and verified runtime facts:

```bash
export OM2B_ACCEPTANCE_BASE_URL=http://127.0.0.1:18182
export OM2B_ACCEPTANCE_CREDENTIAL_FILE=/approved/local/custody/owner-credentials.json
export OM2B_ACCEPTANCE_RECEIPT_FILE=/approved/local/custody/acceptance-receipt.json
export OM2B_CHROME_EXECUTABLE=/approved/path/to/chromium
export OM2B_BROWSER_LABEL='Chromium (reviewer host)'
export OM2B_SERVING_SHA=FULL_SHA_CONFIRMED_BY_LAPTOP_MASTER
export OM2B_REVIEW_OUTPUT="$(mktemp -t om2b-browser-review).json"

node frontend/tests/real-browser-workflow.mjs \
  "$OM2B_ACCEPTANCE_BASE_URL" \
  "$OM2B_ACCEPTANCE_CREDENTIAL_FILE" \
  "$OM2B_ACCEPTANCE_RECEIPT_FILE" \
  "$OM2B_REVIEW_OUTPUT" \
  independent-review

python3 -m json.tool "$OM2B_REVIEW_OUTPUT"
```

The result must report `PASS` for all authenticated routes, `fixture: SYNTHETIC_DISPOSABLE`, the independently confirmed serving SHA, screenshot hashes, and `all_county_operational_acceptance: false`. Screenshots are stored beside the result in a mode-restricted artifacts directory. Inspect them for meaningful rendered content; an HTTP response alone is not acceptance.

Coordinate any restart/persistence phase with Laptop Master so the reserved runtime is not disrupted during owner inspection. Run the same command after the coordinated restart with a different output path and phase label, then compare record identifiers and visible state with the acceptance receipt.

Clear local variables and the clipboard after review:

```bash
printf '' | pbcopy
unset OM2B_ACCEPTANCE_BASE_URL OM2B_ACCEPTANCE_CREDENTIAL_FILE \
  OM2B_ACCEPTANCE_RECEIPT_FILE OM2B_CHROME_EXECUTABLE \
  OM2B_BROWSER_LABEL OM2B_SERVING_SHA OM2B_REVIEW_OUTPUT
```
