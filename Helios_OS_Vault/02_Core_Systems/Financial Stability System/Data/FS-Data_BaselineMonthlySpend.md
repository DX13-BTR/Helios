---
type: data
category: baseline
system: financial-stability
tags: [spend, average, essential, buffer]
last_updated: 2025-07-12
---


**Role:** Stores the baseline monthly spend data used across the Draw Decision Module and Buffer Logic. Divides spending into personal and professional, split by essential vs discretionary/wastable. Forms the foundation for determining safe drawdowns, buffer thresholds, and risk-aware planning.

---

## 📅 Last Updated
2025-07-12

---

## 🧮 Data Snapshot

| Layer        | Type           | Monthly Avg (£) |
|--------------|----------------|------------------|
| Personal     | Essential      | -1,859.26        |
| Personal     | Discretionary  | -204.02          |
| Professional | Essential      | -1,289.43        |
| Professional | Wastable       | -2,175.09        |
| TOTAL        | Essential      | -3,148.69        |
| TOTAL        | Wastable       | -2,919.11        |

---

## 🔍 Usage Summary

- Used to calculate **true Safe Available Funds** before recommending a draw.
- Deducted in full or in part depending on system mode (essential-only or full load).
- Incorporated into **cash runway** or **burn rate tracking**.
- Defines what the **Buffer Reserve Target** should aim to cover.

---

## 🛠️ Future Actions

- [ ] Integrate into automated rolling average engine (Phase 3+).
- [ ] Tag transactions dynamically as Essential/Discretionary.
- [ ] Adjust monthly averages automatically from live feed.
- [ ] Use for personalised UC-safe spend limits and forecast logic.

---

## 🧷 Related Modules

- `Company_Tracker.gsheet`
- `Helios Draw Module Plan.pdf`
- `Planner_Main.gsheet`
- `Helios_Financial_Dashboard.gsheet`
