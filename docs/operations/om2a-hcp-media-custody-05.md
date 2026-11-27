# OM2-A HCP media custody recovery tooling

This assignment adds deterministic attachment reconciliation and a resumable,
GET-only recovery command for Laptop Master to run inside approved protected
custody. It preserves attachment, Job, Customer, timestamp, filename, content
type, content digest, and artifact relationships. Missing bodies and orphaned
media remain explicit; neither is treated as confirmed source absence.

The command accepts a protected reference manifest and checkpoint, restricts
retrieval to the approved HTTPS attachment host and paths, writes artifacts and
atomic checkpoints with private modes, and emits a secret-free summary receipt.
It never invokes an HCP mutation method. Signed URLs remain only in protected
inputs and are represented by hashes in reconciliation evidence.

Example inside protected custody:

```bash
umask 077
PYTHONPATH=backend python scripts/hcp_media_recovery.py \
  --references /protected/hcp/attachment-references.json \
  --checkpoint /protected/hcp/media-recovery-checkpoint.json \
  --output /protected/hcp/media-recovery \
  --recover
```

Implementation qualification uses synthetic metadata only. No protected HCP
packet, signed URL, credential, or media body was available or recovered on
OM2-A, and this work is not actual All County source acceptance.
