# Twelve Hats Speech Genesis Bridge v1

This bridge is the fail-closed compatibility boundary between LIA Voice Genesis
governance and the Twelve Hats speech-engine foundation.

It can issue a `TWELVE_HATS_SPEECH_DATASET.v1` training-authority record only
when the Genesis dataset manifest is reproducible and every manifest asset has
one exact rights-ledger entry with matching source/transcript digests, the same
dataset version, approved exclusive Twelve Hats rights, and passed quality.

The resulting record binds:

- the exact Genesis manifest digest;
- a deterministic digest of the complete rights evidence;
- corpus and pronunciation versions;
- the exact admitted asset identities; and
- a timezone-aware admission timestamp.

The bridge deliberately does not read audio, copy files, admit assets, train a
model, select an architecture, render speech, configure a provider, or enable
inference. Genesis remains the authority for rights and asset admission. The
speech-engine package remains the authority for training and model governance.

Any missing, extra, duplicate, mismatched, pending, rejected, quarantined, or
revoked evidence fails before training authority is created.
