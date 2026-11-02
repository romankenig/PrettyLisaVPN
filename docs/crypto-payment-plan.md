# Crypto payments — proposal only

No crypto checkout or automatic debit is enabled by this document.

1. Verify provider eligibility, assets/networks, settlement currency, fees, refunds,
   webhook authentication and idempotency. 1Plat's public API describes crypto
   orders; this shop's availability is still unverified. Reuse the replaceable
   billing port and prefer hosted checkout. Never request wallet keys/seed phrases.
2. Start with a prepaid month. Show asset, network, exact amount, exchange quote
   and expiry before checkout. Keep contract prices immutable in PostgreSQL and
   invoice conversion in a separate immutable record. Crypto selection is not
   recurring consent. No commercial price changes are proposed here.
3. Persist an account-owned operation before provider IO. Reuse its ID after
   timeout and reconcile uncertain creates; never issue a second invoice simply
   because a client retries. Store minimal settlement data, no browsing history.
4. Require authenticated callbacks and authoritative provider lookup. Validate
   merchant, operation, asset/network, amount, expiry and finality. Deduplicate
   receipts and grant the paid period exactly once in one transaction. Define
   partial/over/late/wrong-network payment handling before launch; uncertainty
   stays pending and cannot create a new charge.
5. Show pending/paid/expired, paid-until and manual renewal in both clients.
   Browser return is never payment evidence. No bind/unbind or automatic wallet
   debit controls without a separately supported and confirmed mandate.
6. Test invalid signatures, duplicate/out-of-order events, amount mismatch,
   concurrent devices, timeout recovery and one-time entitlement with mocked
   providers and integration tests. Run sandbox, then an owner-approved small
   real payment/refund before enabling the backend capability.

Recurring billing is separately postponed. A future solution needs explicit
consent, immutable monthly terms, revocation, retry limits and authoritative
cancellation. Reminders or monthly invoices alone are not recurring charges.
