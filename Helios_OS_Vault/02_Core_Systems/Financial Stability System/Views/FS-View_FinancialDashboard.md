---
type: view
category: dashboard
system: financial-stability
tags: [financial-dashboard, buffer, display]
last_updated: 2025-07-12
---


**Role:** Central cockpit dashboard for draw readiness, buffer safety, and short-term forecasting. This is the output layer of the Draw Decision Module — showing whether it's safe to pay yourself, and if not, why.

---

## 📅 Last Updated
2025-07-12

---

## 🔍 Key Metrics Tracked

| Metric                  | Purpose                                                  |
|-------------------------|-----------------------------------------------------------|
| Rolling Spend 30/60/90  | Shows short/medium-term business outflow trends           |
| Expected Income 30/60   | Forecast inflow based on known/pending income             |
| CT Reserve              | Corporation Tax provision (typically 19%)                 |
| Buffer Reserve Target   | Minimum cash floor before any drawdown is permitted       |
| Safe Available Funds    | True available cash after all obligations and buffers     |
| Recommended Draw        | Value safe to draw, based on live cash and buffer rules   |
| Traffic Light Status    | Visual indicator of whether it is safe to draw            |
| Next Best Payment Date  | Suggested earliest safe date for next draw (manual for now) |

---

## 🧠 Logic Summary

- Pulls **safe funds** from underlying Company Tracker / DPE sheets.
- CT Reserve and Buffer are deducted before calculating draw availability.
- Draw status is defined as:
  - ✅ **SAFE:** All obligations met and buffer protected
  - ⚠️ **CAUTION:** Risk to buffer but not catastrophic
  - ❌ **UNSAFE:** UC risk, insufficient buffer, or unpaid obligations

---

## 🛠️ Future Enhancements

- [ ] Add logic flags to explain WHY a draw is blocked.
- [ ] Auto-link “Next Best Payment Date” to Planner_Main.
- [ ] Colour bars or gauges for rolling spend vs buffer strength.
- [ ] Move to Looker Studio for Phase 4 presentation layer.

---

## 🧷 Related Modules

- `Company_Tracker.gsheet` (Safe Available Funds)
- `Director_Pay_Engine.gsheet` (Draw recommendation)
- `Planner_Main.gsheet` (UC logic + proposed timing)
- `Helios Draw Module Plan.pdf` (Core blueprint)
