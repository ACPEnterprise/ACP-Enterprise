# Provider access execution packets

These are owner actions, not authority to mutate a provider. All requested access
is read-only migration evidence.

## Intuit / QuickBooks

Current proven state: a production app has granted
`com.intuit.quickbooks.accounting`. The current partner tier is not retained in
TwelveHats and must be read directly from the Intuit Developer Portal. All County
Payroll/Workforce access is not granted.

Owner steps:

1. Sign in to the Intuit Developer Portal and open the TwelveHats production app.
2. Record the Workspace tier shown under Billing and Subscriptions. If it is
   Builder, subscribe to Silver; Silver is the minimum tier for Payroll
   Compensation.
3. Complete and submit the Intuit app assessment questionnaire and accept the
   current developer/partner terms when prompted.
4. Under Permissions request `payroll.compensation.read` for compensation/pay
   types. Its least-privilege purpose is historical compensation configuration and
   pay-type interpretation only.
5. Request approved-partner access to `qb.employee.read` for identity,
   employment status, hire date, and termination date.
6. Request approved-partner access to `qb.payroll.benefits` for employee and
   employer benefit/deduction configuration.
7. Ask Intuit support to provide the current least-privilege read scopes and
   resources for payslip history, withholding elections, and complete YTD payroll
   state. Do not request tax-identifier scope unless Intuit confirms it is required
   for the migration fields.
8. Keep the production callback exactly
   `https://preview.allcountyhomeservices.com/api/v1/integrations/qbo/production/oauth/callback`.
9. For Accounting live certification, make the existing protected runtime and
   evidence roots available to the OM2A sanctioned runner; no new Accounting
   consent is required.

After access, engineering enables only approved scopes in the deployment
allowlist, runs incremental consent, verifies the exact realm/company, performs a
GET-only snapshot, and certifies domains independently. Tokens remain in protected
secret storage and are never placed in tickets or chat.

## ServiceTitan

Owner steps:

1. Create or open the TwelveHats app in the ServiceTitan Developer Portal.
2. Add the All County tenant ID and choose self-service connection if available.
3. Request read access for CRM customers/contacts and locations; Settings
   employees/technicians; JPM jobs and appointments; dispatch; Sales estimates;
   Pricebook services/materials; Accounting invoices and payments; and inventory
   resources exposed to the tenant.
4. Do not select create, update, delete, payment, dispatch mutation, or other write
   permissions. ServiceTitan expresses permissions as portal-managed resource
   scopes; export the final scope list from the portal rather than translating
   guessed scope strings. `tn.acc.invoices:r` is the documented invoice-read
   example, but the portal is authoritative for every requested resource.
5. Have an All County administrator with **Manage API Application Access** connect
   the app under Settings → API Application Access → Connect New App.
6. Generate an integration-environment client ID/secret and provide it through the
   approved secret manager. Provide a test tenant containing representative
   customers, locations, employees, jobs, appointments, estimates, pricebook
   records, invoices, and payments.
7. After synthetic/integration qualification, repeat tenant approval for
   production and generate a production client ID/secret. No browser OAuth callback
   is required: ServiceTitan V2 uses client-credentials authentication. Configure
   the app key, tenant ID, auth base, API base, and secret references.

Engineering then runs discovery, records the exact granted scopes, qualifies each
domain, verifies pagination/rate behavior, and retains polling/backfill drift
checks unless usable webhooks are confirmed.

## Jobber

Owner steps:

1. Create the TwelveHats app in Jobber Developer Center and enable two-factor
   authentication for the owner account.
2. Configure the production OAuth callback and a Manage App URL. Engineering will
   use authorization code flow with state and PKCE S256.
3. Select only the portal read permissions needed to view clients, properties,
   users/team members, jobs, visits, quotes, invoices, payments, products/services,
   and time sheets. Jobber configures scopes in Developer Center; export the exact
   generated scope list instead of relying on guessed strings.
4. Connect a dedicated Jobber test account containing representative records for
   every selected resource and authorize the app as an account administrator.
5. Provide the client ID/secret through the approved secret manager. Do not send
   access or refresh tokens manually.
6. For commercial operation beyond five paying connected accounts, request Jobber
   App Review. Before review, engineering must demonstrate refresh-token rotation,
   connect/disconnect/reconnect, dated GraphQL version handling, and the
   `APP_DISCONNECT` webhook.

Engineering then captures the account identity, exact granted scopes and API
version, runs cursor-complete read acquisition, and certifies every domain
independently.
