# Owner Review Checklist

Designed for a quick phone review:

- [ ] The implementation stayed within the approved scope.
- [ ] The changed-file list contains no unrelated work.
- [ ] Architecture findings passed or have an understood rationale.
- [ ] Security and tenant-isolation findings passed or were explicitly reviewed.
- [ ] Required tests passed.
- [ ] No required check is unavailable or silently skipped.
- [ ] Migrations, if present, were tested only on disposable PostgreSQL.
- [ ] The proposed commit boundary is exact.
- [ ] The proposed commit subject is appropriate.
- [ ] No commit, push, merge, deployment, infrastructure, permission, or shared-data action occurred.
- [ ] The milestone is ready for architectural approval.

This checklist records review; it grants no permission and performs no action.
