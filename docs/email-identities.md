# Email identity policy — backend 0.41.0

All clients and the website use the same backend account lookup. Email casing
continues to be normalized; only the finite groups below share a domain identity.
We never remove arbitrary domain suffixes, dots, plus tags or custom-domain labels.
The first saved normalized email remains the account's displayed/stored address.
OTP delivery uses the address actually submitted by the user, not a rewritten
canonical destination. Receiving and verifying the OTP still proves mailbox access.

## Provider review (2026-11-14)

Scope: Yandex plus ten widely used providers requested by the owner. This is an
explicit review set, not a claimed statistical worldwide ranking. Only documented
shared same-username namespaces are mapped; having an alias feature is insufficient.

| Provider | Backend decision | Official evidence / limitation |
| --- | --- | --- |
| Yandex | `yandex.ru`, `yandex.com`, `yandex.by`, `yandex.kz`, `ya.ru` | [Additional addresses](https://yandex.com/support/yandex-360/customers/mail/en/web/preferences/about-sender/additional-addresses): same mailbox name on the listed main/country/short domains. No unlisted historical domains are guessed. |
| Gmail | `gmail.com`, `googlemail.com` | [Google's domain transition announcement](https://gmail.googleblog.com/2012/06/willkommen-bei-gmail-deutschland-its.html): same mailbox retains both addresses. Dot/plus normalization is outside this task. |
| Proton | `proton.me`, `protonmail.com`, `protonmail.ch`, `pm.me` | [Addresses and aliases](https://proton.me/support/addresses-and-aliases), [free addresses](https://proton.me/support/manage-your-free-email-addresses), [pm.me](https://proton.me/support/pm-me-addresses), [username reservation](https://proton.me/support/inactive-accounts). Some addresses require activation or a plan; OTP is sent only to the submitted address. |
| Microsoft Outlook/Hotmail/Live | No automatic domain mapping | [Managing Microsoft account aliases](https://support.microsoft.com/en-us/accounts-billing/manage/how-to-add-an-email-address-or-phone-number-to-your-microsoft-account): aliases are attached to an account individually. The same local part alone does not establish that association. |
| Yahoo/Ymail/Rocketmail | No automatic domain mapping | [Sign-in instructions](https://in.help.yahoo.com/kb/new-mail-for-desktop/sign-yahoo-sln3407.html) require the complete address for non-Yahoo domains; no universal same-local-part equivalence was established. |
| Apple iCloud/Me/Mac | No automatic domain mapping | [iCloud email aliases](https://support.apple.com/en-us/118230): legacy equivalence depends on account history/dates. Do not generalize to every same-name address. |
| Mail.ru | No automatic domain mapping | [Creating a mailbox](https://help.mail.ru/mail/account/signup/): domain choice does not prove shared ownership with an existing address on another domain. |
| AOL | No automatic domain mapping | Reviewed [AOL Help](https://help.aol.com/); no official universal same-username guarantee for aol.com/aim.com was verified. Leave unchanged pending evidence. |
| GMX | No automatic domain mapping | [Alias addresses](https://support.gmx.com/email/settings/aliasaddresses.html) are explicitly created/managed by the owner; same-name domains are not automatically equivalent. |
| Zoho | No automatic domain mapping | [Multiple addresses for a user](https://help.zoho.com/portal/en/kb/mail/adminconsole/articles/can-i-configure-more-than-one-email-address-for-a-single-user): administrator-configured aliases cannot be inferred from suffixes. |
| QQ/Foxmail | No automatic domain mapping | The [official help resource](https://service.mail.qq.com/detail/0/161) could not be retrieved during this review. No primary-source universal namespace guarantee was verified; do not infer ownership from third-party descriptions. |

## Persistence and concurrency

`users/email_identity.py` supplies the exact lookup candidates and shared lock
key. Native OTP and web billing authentication already delegate account creation
to UserService; both now find the existing account across these candidates.
PostgreSQL advisory locks serialize simultaneous first logins through different
aliases, preserving one account/subscription. Queries still use the existing
unique email index; schema 0048 is unchanged.

OTP challenge, cooldown, attempts, digest and discard keys share the same identity.
Requesting codes via aliases cannot obtain separate challenge/rate-limit buckets.
Never log OTP values or mailbox credentials. Existing sessions remain valid;
an outstanding pre-deployment OTP for a noncanonical domain may require a new code
after deployment because its Redis key changes.

## Existing duplicate accounts

If multiple independently created legacy accounts already occupy a group, this
change **does not merge or delete their billing, devices, quotas or support data**.
Exact existing addresses retain access to their existing accounts. An additional
unoccupied alias returns stable HTTP 409 `EMAIL_ALIAS_CONFLICT`, rather than
creating a third account or silently choosing one. The website issues no auth cookie
on that conflict.

A separate reconciliation task must inventory such conflicts, decide how to
preserve paid contracts, device limits and consumed daily allowance, and then
migrate references transactionally with rollback evidence. Automatic unification
applies when zero or one account exists in the documented group; do not report
legacy duplicate reconciliation as implemented.

Tests cover every included/excluded provider, unchanged dot/plus/custom domains,
shared OTP keys, concurrent initial/existing logins across domains, retained first
address and subscription, and legacy-conflict responses on native and web routes.
