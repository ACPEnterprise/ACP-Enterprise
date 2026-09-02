# Transactional provider decision packet

Facts retrieved 2026-09-01 from provider-owned public documentation. Pricing changes; re-check at admission.

## Recommendation for owner decision

Use separate providers: Postmark for transactional Email and Twilio for US operational SMS. This is a proposed admission choice, not an activated decision.

Postmark is narrowly transactional, exposes REST/SMTP, event webhooks, bounce evidence, DKIM/SPF/DMARC support, sandbox mode, and separate transactional streams. Its published 10,000-message plans begin at $15/month with overage beginning at $1.80/1,000. Amazon SES is materially cheaper at published à-la-carte rates ($0.10/1,000 outbound plus data/add-ons), but requires more AWS configuration and operational deliverability ownership. Mailgun and SendGrid remain viable alternatives with API/webhook/suppression capabilities; re-evaluate if ACP needs combined marketing operations or already standardizes vendor operations there.

Twilio has mature US messaging services, delivery callbacks, Advanced Opt-Out/STOP/START/HELP evidence, and broad operational tooling. Published US outbound long-code SMS begins at $0.0083 per segment plus carrier fees; number and A2P registration costs are additional. Telnyx is the cost-focused alternative, publishing $0.004 per message part plus carrier fees and explicit 10DLC APIs/fees. Re-evaluate Telnyx if measured ACP volume makes unit economics outweigh Twilio operational familiarity and support.

A combined Twilio + SendGrid purchase reduces vendor count but does not eliminate distinct Email/SMS products, credentials, sender admission, webhooks, or failure modes. The provider-neutral ACP adapters make best-of-breed replacement safer, so vendor count alone is not a sufficient reason to combine them.

## Cost model

Inputs: monthly Email recipients `E`; SMS segments `S`; inbound SMS segments `I`; phone numbers `N`; provider base `B`; number cost `P`; registration/campaign fees `R`; carrier pass-through `C`; data/add-ons `A`.

`monthly cost = B + email unit(E) + sms unit(S + I) + N×P + R + C + A`

ACP must measure SMS segments, not messages. No All County volume is assumed. Dedicated IPs are not justified until volume/reputation evidence supports them.

## Required owner decisions

- Email provider and plan; transactional sender display, From identity, Reply-To, and domain.
- SMS provider; long-code/toll-free strategy; registered use case; approved opt-out/help language.
- Transactional Email/SMS defaults and authorized fallback.
- Reminder offsets; On My Way/arrival/work-complete enablement; Estimate follow-up cadence/limit; Invoice resend and Agreement notice policy.
- Retention period for provider message-body/activity data. ACP retains minimum immutable delivery evidence, not bodies by default.

No provider account, contract, number, campaign, DNS record, credential, webhook, real send, Preview deployment, or Production operation is authorized by this packet.
