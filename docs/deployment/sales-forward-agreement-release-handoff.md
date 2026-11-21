# Sales Forward Agreement Release Handoff

## Candidate

- Base candidate: `b534cf1689c00b1021aee0f4181f63bb34c0eda1`
- This handoff adds the verified agreement source and publication command.
- Production deployment: prohibited.

## Agreement source

- Legal entity: LHERNANDEZ HOLDINGS, LLC, a Florida limited liability company
- Agreement code: `TWELVEHATS_SALES_DEMO_ACCESS`
- Version: `1`
- Source: `docs/legal/TwelveHats_NDA_v1.0_Approved_Source.md`
- SHA-256: `aaf90aafe6aa6e10ef1ae7bc9d002634cad7fd36018a9279d77153fd5d804fd6`
- Source bytes: `17,130`
- Sections: `20`

## Governed release sequence

1. Apply Alembic head `s1a3g5k7m9q2`.
2. Verify the source file digest before database mutation.
3. Run `backend/scripts/publish_sales_demo_agreement.py` with the authorized actor user ID and `--publish`.
4. Verify the returned agreement ID, version, status `published`, and exact SHA-256.
5. Deploy the candidate through OM1E/Enterprise Beta governance.
6. Authenticate Keith through the supported onboarding workflow; do not print invitation secrets.
7. Require first-login electronic acceptance and verify the durable receipt.
8. Run Demo-only and direct All County denial tests before activating sales access.

The publication command refuses a digest mismatch and refuses to overwrite an existing immutable version.
