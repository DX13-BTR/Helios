---
type: build-log
title: Starling vs Xero Data Roles – Drawdown System Foundation
date: 2025-07-14
status: active
tags: [financial-stability, ingestion, roadmap, drawdown]
---

# 🧭 Starling vs Xero – Ingestion and Decision Layer Roles

## ✅ Summary

The core of the Financial Stability System will be built on **Starling transaction-level data**, not just balances.

While Xero was originally considered for ingestion, it's now confirmed that:

- Starling will act as the **real-time financial source of truth**
- Xero will act as a **contextual cross-reference** (e.g. category labels, reconciled view)

---

## 🧠 Why Starling Takes Priority

- Direct live access to personal + business bank accounts
- API gives:
  - 🔁 Transaction feed (`/feed-items`)
  - 💰 Account + space balances
  - 🏦 Transfers between accounts/spaces
- Enables:
  - 🔎 Detection of recurring bills from real historical spend
  - 🧮 Real-time UC-safe drawdown limits
  - ⚠️ Future spend simulation based on past behaviour

---

## 🧾 Why Xero Is Still Useful (But Not Primary)

Xero’s role is *not* for live balance or spending data, but to:

- Provide **meaning/context** to spend (via nominal accounts)
- Enable **reconciliation insights**
- Act as a **bookkeeping sanity-check layer** (e.g. is Starling tagged correctly?)
- Possibly inform tax planning, PAYE cycles, or forecasted obligations

> Xero = “What the transaction means”  
> Starling = “What’s actually happening”

---

## 🔒 Locked-in Principle

> **We will not build manual bills trackers, budgets, or static operating buffers.**  
> Instead, we will analyse real historical Starling transaction behaviour to:

- Detect recurring bills
- Project expected spend
- Define actual safe drawdown recommendations

---

## ✅ Immediate Next Step: Starling Transaction Feed Build

### Build: `fetchStarlingTransactions()`  
Pull raw transaction history via Starling `/feed-items` or `/transactions` endpoint for:

- Efkaristo Ltd account
- Personal account

---

## 🧩 Then:

1. **Normalise transactions**
   - Identify payees
   - Match patterns (amount + day of month)
   - Group into categories (e.g. rent, utilities, food, subscriptions)

2. **Detect expected upcoming outgoings**
   - Predict bills due in next 14 days based on history
   - Use this to calculate realistic drawdown ceiling

3. **Replace balance-only planner**
   - Use transactional forecast in drawdown logic
   - `safeToDraw = available cash − forecasted spend − UC buffer`

---

## ⏭️ Future (Optional Later):

- Add Xero reconciled transaction feed for accuracy checking
- Add “explain this transaction” layer using Xero’s nominals
- Sync back drawdowns into Xero (optional advisory feature)

---

_Last updated: 2025-07-14 @ 22:38 by Mike_

