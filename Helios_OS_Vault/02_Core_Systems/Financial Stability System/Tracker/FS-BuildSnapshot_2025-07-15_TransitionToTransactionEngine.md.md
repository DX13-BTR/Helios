---
type: tracker
title: FS-BuildSnapshot – 2025-07-15 (Phase 3 Transition: Starling Txn Logic)
status: active
category: build_snapshot
tags: [helios, fss, decision-layer, starling, transactions]
---

# 📍 Build Snapshot – 2025-07-15 (Phase 3 Transition: Starling Transaction Logic)

---

## ✅ Phase 2 Completion (Locked)

- ✅ Live Starling balance feed (Efkaristo + Personal)
- ✅ Structured `.json` + `.md` snapshot export
- ✅ Obsidian archival system live
- ✅ DailyMetrics logic populating to Sheets
- ✅ 14-day UC Buffer Tracker (Sheet-based)
- ❌ Obsidian DataviewJS logic deprecated for decision making

---

## 🎯 Phase 3 Goal: Transaction-Powered Drawdown Engine

You are now shifting from balance-based logic to **transaction-based forecasting and safe drawdown decisions**.

---

## 🔁 What Changes Now

| From                              | To                                             |
|-----------------------------------|------------------------------------------------|
| Balance snapshots                 | Live transaction ingestion via Starling API    |
| Manual/assumed bills              | Pattern-matched expected outgoings             |
| Static drawdown math              | UC-safe + forecast-aware drawdown recommendations |
| Obsidian file inspection          | Real-time cash + transaction analysis engine   |

---

## 🧠 Phase 3 Modules

### 1. `fetchStarlingTransactions()`
- Pull live transactions using Starling API
- From both:
  - Efkaristo Ltd account
  - Personal account
- Store in `StarlingTransactions` tab

### 2. `identifyRecurringOutgoings()`
- Group transactions by payee + amount + day-of-month pattern
- Predict next 14-day outgoings
- Output estimated obligation total

### 3. `calculateSafeDrawdown()`
- Compute:  
  `available cash − UC buffer − expected outgoings`
- Output: recommended drawdown amount + status

---

## ⏭️ Future Layers (Post Phase 3)

- Xero reconciliation logic  
- Surplus timeline projection  
- Drawdown automation using Starling's `/transfer-between-accounts` endpoint  
- Optional: build web GUI, chart visualisation, client-facing version

---

_Last updated: 2025-07-15 @ 11:58 BST_

