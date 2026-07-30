# First-dollar runbook — the literal handoff

> The funnel is built and wired to your handles. What was missing wasn't code — it was *this*:
> the exact click+command sequence, not the category "enroll a payout rail." Each rail below is one
> account sign-up (irreducibly your identity/bank) bracketed by work already done. After you finish a
> rail, tell me and I run the listed verify + flip its status to LIVE. No re-asking after that.
>
> **Why only you can do the sign-up:** a payment processor attaches *your* bank + verifies *your*
> identity. "Full permissions" can't make me you to a KYC form. Everything *around* that one act is
> staged so your part is sign-up → connect payout → done.

---

## Already shipped (the bracket — verify any of it yourself)

- `a-organvm/a-i-chat--exporter` `.github/FUNDING.yml` (on `master`):
  `github: [4444J99]` · `ko_fi: 4444J99` · custom: `aichatexporter.com/pro`, `ko-fi.com/4444J99/tip`
- README "Supporting the Project" section (sponsor + ko-fi + Pro links) — live on `master`.
- Lemon Squeezy Pro license gate: 6-file scaffold, offline-ECDSA verification, **125 tests green**, fail-closed.
- Verify the bracket: `gh api repos/a-organvm/a-i-chat--exporter/contents/.github/FUNDING.yml --jq .content | base64 -d`

**The two destinations the buttons point at are still empty shells** (this is the only gap):
- `gh api graphql -f query='{user(login:"4444J99"){hasSponsorsListing}}'` → `false`  (Sponsors not enrolled)
- `ko-fi.com/4444J99` → not a claimed page yet

---

## RAIL 1 — Ko-fi  ·  fastest, ~5 min, donations live today, NO new LLC/Stripe

Donations land on an **existing PayPal** — no new entity, no new KYC if you already have PayPal.

1. Open **https://ko-fi.com** → **Sign up** (use `padavano.anthony@gmail.com` or Google).
2. **CRITICAL — set your page handle to exactly `4444J99`** → your page becomes `ko-fi.com/4444J99`.
   The live repo's Sponsor button + README already point here; any other handle and they 404.
3. Page name: `AI Chat Exporter`.  Short bio (paste):
   `Export your full ChatGPT / Claude history to Markdown, JSON, and PDF. Free + open source.`
4. **Payments** → **Connect PayPal** → log into your existing PayPal → done. (Stripe is optional/skip.)
5. Tell me **"ko-fi live"**.
   - I run: `curl -sI https://ko-fi.com/4444J99` (expect `200`) + confirm the repo Sponsor button resolves.
   - I flip registry item 1 → LIVE.

## RAIL 2 — GitHub Sponsors  ·  ~10 min, needs Stripe Connect (bank + SSN)

1. Open **https://github.com/sponsors** → **Join the waitlist / Set up GitHub Sponsors** for `4444J99`.
2. Country → individual → **Stripe Connect**: bank account + SSN/tax id (this is the heavier KYC).
3. Set a one-time / monthly tier (suggest `$3` and `$10`).
4. Tell me **"sponsors live"**.
   - I run: `gh api graphql -f query='{user(login:"4444J99"){hasSponsorsListing}}'` (expect `true`).
   - The repo "Sponsor" button activates automatically (FUNDING.yml already lists you).

## RAIL 3 — Lemon Squeezy Pro  ·  recurring product revenue (not donations)

The Pro license code is already integrated; this turns it on.

1. Open **https://app.lemonsqueezy.com** → create a store (tax/payout info = your identity).
2. Create a **product** "AI Chat Exporter Pro" → copy the **Store ID** and the **checkout URL**.
3. Paste two values into the Exporter's env (I land the commit once you give them):
   - `VITE_LEMON_SQUEEZY_CHECKOUT_URL=<checkout url>`
   - `LEMONSQUEEZY_STORE_ID=<store id>`
4. Tell me the two values → I wire them, redeploy, and Pro upgrades start gating real license keys.

---

## Co-drive option (I do everything except the identity click)

Say **"co-drive ko-fi"** and I open Chrome, drive to the sign-up, pre-fill the handle (`4444J99`), page
name, and bio. You do only the two things that are physically yours: approve the account and connect
PayPal. That's the smallest your hand can get.

---

## What I cannot reduce further — and why it's physics, not a missing permission

Dollar #1 needs one of the three accounts above to exist, because money moves through *your* verified
bank/identity. I built and verified the entire funnel that points at it, reduced your part to one
sign-up, and wrote out every surrounding command so nothing is vague. The trigger is one account; it's
the kind only you can pull. Pick the rail and I take it from there.
