---
type: logic
category: uc-drawdown
system: financial-stability
tags: [uc, drawdown, tracker, safety]
last_updated: 2025-07-12
---


**Role:** Acts as a structured, manual tracker for safe available funds (SAF) and UC-compliant drawdown planning. Splits logic across personal and professional tabs to assess income, spend, and buffer sufficiency before monthly decisions.

---

## 📅 Last Updated
2025-07-12

---

## 📂 File: `Helios_SAF_and_Draw_Tracker.xlsx`

---

## 🗂️ Tabs Overview

### 🟦 `Professional SAF Tracker`

| Category         | Monthly Amount |
|------------------|----------------|
| Essential Spend  | £3,200         |
| Wastable Spend   | £850           |
| Income (Efkaristo Ltd) | £7,000   |
| Buffer Target    | £2,000         |

**Logic:** Compares total income vs required spend + reserve, and outputs potential draw window from business earnings.

---

### 🟩 `Personal SAF Tracker`

| Category             | Monthly Amount |
|----------------------|----------------|
| Essential Spend      | £1,800         |
| Discretionary Spend  | £600           |
| Draw from Company    | £2,500         |
| Buffer Target        | £1,000         |

**Logic:** Ensures draw from company covers needs without breaching buffer or discretionary thresholds.

---

## 🔄 Role in System

- ✅ Manual planning and cross-check layer for the Live Dashboard  
- ✅ Models UC-compliant drawdowns against essentials + reserves  
- ✅ Helps define monthly floor limits and draw caps  
- ❌ Not dynamically linked to dashboards (used as manual checker)

---

## 🛠️ Suggested Enhancements

- [ ] Link draw output to dashboard (`Planner.Main` or `Director_Pay_Engine`)  
- [ ] Visualise draw safety over time  
- [ ] Add monthly archive for tracking draw patterns  
- [ ] Highlight “UC Breach Risk” if thresholds exceeded

---

## 🧷 Related Notes

- `📊 FS-Data_BaselineMonthlySpend.md`  
- `📊 FS-View_LiveDashboard.md`  
- `💼 FS-Logic_DirectorPayEngine.md`  
- `Helios Draw Module Plan.pdf`
