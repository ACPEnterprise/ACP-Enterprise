# Google Ads Beta owner connection

This runbook admits a real Google Ads connection only after the owner-facing code is released to Beta. It does not authorize an account by itself.

## Google-side configuration

1. Use a TwelveHats-controlled Google Cloud project and enable the Google Ads API.
2. Configure the OAuth consent screen for the TwelveHats Beta application and add Michael's Google identity as an authorized/test user while the application remains in testing.
3. Create a Web application OAuth client. Register exactly `https://preview.allcountyhomeservices.com/api/v1/marketing/google-ads/oauth/callback`; do not register wildcards, localhost, or Production callbacks for this Beta credential.
4. Request only `https://www.googleapis.com/auth/adwords`. Google makes this broad scope unavoidable; TwelveHats enforces read-only behavior in its adapter and routes.
5. Obtain the Google Ads developer token in the manager account used for reporting. Confirm its access level supports the intended real account.
6. Place the OAuth client configuration and developer token in the platform secret provider under separate opaque references rooted at `marketing/beta/google-ads/`. Never put either value in application configuration, a Marketing table, logs, tickets, or this runbook.

Set only these non-secret Beta application values:

- `GOOGLE_ADS_OAUTH_CLIENT_REFERENCE`
- `GOOGLE_ADS_DEVELOPER_TOKEN_REFERENCE`
- `GOOGLE_ADS_CALLBACK_URI`
- `GOOGLE_ADS_RUNTIME_ROOT` — absolute owner-restricted persistent volume outside the repository
- `GOOGLE_ADS_LIVE_ACCESS_ENABLED=true` only in Beta after the callback and secret-provider implementation are admitted

Provision or rotate the three source values from owner-readable `0600` files with `backend/scripts/provision_google_ads_secrets.py`. Supply the current generation for rotation. The command reports only status and generation numbers; values are never printed. Restart the Beta workload after configuration changes and verify all five readiness checks before selecting Connect.

Production must use different credentials and references. The application rejects live access outside Beta.

## Owner steps after release admission

1. Open **Marketing → Provider Connections → Google Ads** and verify every readiness item.
2. Select **Connect Google Ads**, authenticate with the Google identity that can see the All County account, and review Google's consent screen.
3. Review the exact discovered customer IDs and descriptive names. Select only the All County account; discovery does not bind or ingest any account.
4. Map that customer ID to the All County Company and the correct Branch.
5. Confirm read-only ingestion and choose 30, 90, or 180 days of initial history.
6. Start the bounded sync, then inspect partition status, reconciliation findings, and evidence coverage before using Marketing reporting.

Provider conversions remain provider-reported evidence. They do not become TwelveHats Jobs, revenue, or economic contribution without deterministic touch and attribution evidence through the canonical operational chain.
