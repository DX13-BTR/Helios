---
type: data
category: personal
system: financial-stability
tags: [spend, log, personal, essentials]
last_updated: 2025-07-12
---


**Role:** Central log of personal transactions, used to calculate rolling essential/discretionary spending. Feeds into the Financial Dashboard, Buffer Logic, and Draw Decision Module to determine UC-safe draw amounts and cashflow trends.

---

## 📅 Last Updated
2025-07-12

---

## 📂 File: `Helios_Personal_Spend_Phase_2.1_Full.csv`

### 📊 Columns

| Column        | Description                                      |
|---------------|--------------------------------------------------|
| `Date`        | Date of transaction                              |
| `Description` | Optional label or vendor                         |
| `Amount`      | Value (negative = spend, positive = income)      |
| `Category`    | Spending category (e.g. Groceries, Rent)         |
| `Type`        | Essential / Discretionary                        |
| `Source`      | Origin of spend (e.g. Bank, Cash, Direct Debit)  |

---

## 🔄 Uses in System

- ✅ Inputs rolling 30/60/90-day spend averages via `IMPORTRANGE`
- ✅ Feeds `FS-Data_BaselineMonthlySpend.md` for buffer planning
- ✅ Informs drawdown safety thresholds (via Live Dashboard)
- ✅ Can be filtered by Type to isolate UC-safe minimum spend

---

## 🛠️ Suggested Enhancements

- [ ] Automate import via bank feed (e.g. Coupler or Make)
- [ ] Add running monthly average column
- [ ] Apply stricter category mapping to reduce noise
- [ ] Split recurring vs one-off flags for trend detection

---

## 🧷 Related Notes

- `📊 FS-Data_BaselineMonthlySpend.md`
- `📊 FS-View_LiveDashboard.md`
- `📐 FS-Build_DashboardStructure.md`
- `Helios Draw Module Plan.pdf`
