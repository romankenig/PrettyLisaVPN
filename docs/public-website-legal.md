# PrettyLisaVPN legal documents — 2026-11-08

## Request and scope

The owner supplied a moderation request to replace technical summaries with legal
documents and then explicitly asked to preserve the supplied templates as closely
as possible. Both complete texts were supplied in chat. The privacy policy retains
seven sections; the agreement retains ten sections and its concluding acceptance
sentence. Section order, clause numbering and applicable wording are preserved.

The owner explicitly requested **no seller identifiers** and designated only
`help@prettylisavpn.com` for correspondence. No personal name, INN, postal street
address or substitute legal entity was invented or restored. This editorial
instruction does not establish legal sufficiency of the operator/provider identity.

Website **0.5.0 → 0.5.1** (PATCH: existing legal content and its presentation).
All client and backend versions remain unchanged. No new endpoint, database
migration, contract-acceptance mechanism, payment operation or deployment setting.
Existing legal URLs and all six language routes remain compatible.

## Necessary adaptations to the templates

- Replace website/bot placeholders, bot commands and informational digital goods
  with PrettyLisaVPN, the actual website, applications and VPN/browser-proxy service.
- At the owner's follow-up request, use generic terms throughout all four legal
  documents: selected plan, payment method and payment provider. Do not name plans,
  SBP or Platega in legal content. Plan periods, limits, features, device counts,
  price and payment options are disclosed by the Service before confirmation.
  Preserve separate consent to renewal amount/frequency, the immutable agreed
  amount, cancellation and retained paid access. Unavailable payments do not sell.
- Preserve data disclosures from the previous policy: account/device data, guest
  identifiers, service analytics, support, portal cookie/local operation recovery
  and payment-provider matching. Include measured traffic volume/speed, not browsing.
  Retention evidence: product analytics 180 days, support working database 30 days,
  fleet traffic intervals eight days; temporary guest IP hash up to one hour.
- Qualify the liability exclusions by mandatory law. Preserve permitted software
  and open-source licence use. Replace blanket non-refund/24-hour/chargeback bars
  with claims and statutory rights; add the same clarification to the refund page.
- Distinguish notice of the privacy policy from consent. Changes cannot silently
  replace required consent or worsen an already paid period/agreed renewal amount.
- Keep operational detail necessary for honest disclosure inside the original
  section structure, rather than add a new technical-reference document.

These edits do not constitute a legal opinion or guarantee of moderation approval.
`legalApproved`, `refundPolicyApproved`, `receiptProcessApproved` and provider
approval remain false; their release guard is retained. A wording change does not
prove that notice delivery, deletion of all storage/backup/mailbox copies, recording
accepted document revisions or receipt issuance is implemented. Before sales,
confirm operator identity requirements, processors/regions and retention inventory,
claims/receipt procedures and the actual consent/notice process with the operator.

## Implementation and verification

The existing locale JSON files own the content. Terms/privacy now contain typed
section-shaped data (`title`, `paragraphs`); newline-separated enumerations render
as semantic lists. The static renderer escapes all titles, paragraphs and list
items before adding fixed mailto links. Contents links point to section headings.
Other legal pages keep their existing plain-paragraph format. No dependency added.

Validation covers six-language schema parity, 10/7 numbered sections, internal
links and anchors, escaped untrusted content, safe email links, generic legal
terminology, the release guard, clean static output and all 96 routes. Run
`npm run check`, `npm test`, `npm run build`, formatting and diff checks; browser
review covers the expanded documents at desktop/mobile widths. Existing CI runs
the real Caddy integration tests in a disposable container.

Base: develop `f217f549db8f55e5bedcc12cebf8804ae3302e50`. The exact verified final
source HEAD, push build SHA, PR merge-build SHA, run/attempt, artifact and browser
evidence are recorded in the task PR after the last push, avoiding a documentation
commit that would invalidate the reported CI results. Earlier website artifacts
do not verify this revision. No client/native build is required for this task.

Publication is separate from commit/push: this work does not merge the PR, enable
payments or deploy to production. Rollback is the previous verified static website
artifact; there are no schema or API changes to undo.

## References

Owner-supplied templates (full text subsequently provided directly):
[privacy policy](https://telegra.ph/Politika-konfidencialnosti-08-01-83) and
[user agreement](https://telegra.ph/Polzovatelskoe-soglashenie-08-01-39).

For the narrow statutory-rights adjustments, consulted
[Rospotrebnadzor on termination of services and invalid time restrictions](https://44.rospotrebnadzor.ru/zacshita_prav_potreb/1440/).
For processing purposes, grounds and rights, consulted the
[Roskomnadzor recommendations hosted by the Smolensk administration](https://it-security.admin-smolensk.ru/files/303/rec-polit.pdf).
The recommendations inform structure, not evidence of this service's compliance.

Operational sources: [DEMO](android-demo-access.md),
[billing](platega-billing.md), [traffic metrics](active-user-speed.md),
[support](support-ui.md), and the historical
[website data inventory](public-website-preview.md).
