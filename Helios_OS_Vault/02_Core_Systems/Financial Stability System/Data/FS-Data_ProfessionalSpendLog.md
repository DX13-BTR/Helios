---
type: data
category: professional
system: financial-stability
tags: [spend, log, business, operations]
last_updated: 2025-07-12
---


**Role:** Tracks all professional (business) expenses, categorised by essential and wastable spending. Used for live rolling spend calculations, buffer threshold validation, and planning sustainable drawdowns without compromising operational stability.

---

## 📅 Last Updated
2025-07-12

---

## 📂 File: `Helios_Professional_Spend_Phase_2.1_Full.csv`

### 📊 Columns

| Column        | Description                                              |
|---------------|----------------------------------------------------------|
| `Date`        | Date of transaction                                      |
| `Description` | Vendor or expense type                                   |
| `Amount`      | Negative = spend; Positive = refund/income               |
| `Category`    | Expense category (e.g. SaaS, Rent, Utilities)            |
| `Type`        | Essential / Wastable                                     |
| `Source`      | Source of transaction (Tide, Starling, Credit Card)      |

---

## 🔄 Uses in System

- ✅ Feeds 30/60/90-day rolling spend totals  
- ✅ Contributes to `FS-Data_BaselineMonthlySpend.md`  
- ✅ Integrated into buffer threshold and safe drawdown logic  
- ✅ Future categorisation engine (Phase 3) will learn from this file

---

## 🛠️ Suggested Enhancements

- [ ] Automate source import (Coupler/Make from Tide/Starling)  
- [ ] Add recurring vs ad-hoc tag  
- [ ] Validate category consistency with Personal Spend log  
- [ ] Track flagged “excess” wastable spend during cost reviews

---

## 🧷 Related Notes

- `📊 FS-Data_BaselineMonthlySpend.md`  
- `📊 FS-View_FinancialDashboard.md`  
- `📊 FS-View_LiveDashboard.md`  
- `📐 FS-Build_DashboardStructure.md`  
- `Helios Draw Module Plan.pdf`
