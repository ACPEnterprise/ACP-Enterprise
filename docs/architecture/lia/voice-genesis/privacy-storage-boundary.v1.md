# LIA voice Genesis privacy and storage boundary

Training assets remain in Twelve Hats-controlled storage. Nothing is uploaded
automatically, and commercial speech services receive no source audio,
normalized audio, transcript, embedding, speaker representation, or model
artifact.

Storage separates source audio, normalized audio, transcripts, rights metadata,
training manifests, and model artifacts. Access to one class does not imply
access to another. Rights metadata contains references and digests, never actual
contracts, credentials, secrets, or contributor financial information.

Source retention follows the explicit asset ledger rule. Normalized derivatives
inherit the source asset's rights and revocation constraints. Dataset manifests
are retained as immutable lineage evidence even when an asset becomes revoked;
revoked bytes are excluded from future datasets and handled only under a future
approved deletion workflow. This mission defines no destructive deletion.

`New Recording.m4a` remains `REFERENCE_MEASUREMENT_PENDING`. Its presence or
future measurement never grants training rights or admission.
