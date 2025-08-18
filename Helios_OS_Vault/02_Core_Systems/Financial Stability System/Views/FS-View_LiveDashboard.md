---
type: view
category: dashboard
system: financial-stability
tags: [live-dashboard, cashflow, traffic-light]
last_updated: 2025-07-12
---


**Role:** Operational Google Sheet dashboard used to determine UC-safe and financially stable drawdown timing. Presents a traffic light indicator and guidance for weekly or monthly decision-making based on rolling spend, income, and buffer logic.

---

## 📅 Last Updated
2025-07-12

---

## 🗂️ Core Sheet Tabs

| Tab              | Purpose                                                                 |
|------------------|-------------------------------------------------------------------------|
| `Dashboard`      | Draw decision panel: SAFE/CAUTION/UNSAFE + recommended action          |
| `Control Panel`  | Set variables (MIF, taper, UC thresholds, buffer targets, current buffer)|
| `Rolling Averages`| Pulls live 30/60/90-day essential spend data via IMPORTRANGE          |
| `Xero Intake`    | Paste area for weekly CSV exports from Xero                             |
| `Bank Intake`    | Paste area for bank transaction data (CSV)                              |

---

## 🔁 Key Logic

- **Recommended Draw** = MIF - 30-day essential rolling spend  
- **Adjusted Draw** = MIN(Recommended Draw, Buffer)  
- **Traffic Light Logic:**
  - 🟩 Green: Buffer >= Recommended Draw  
  - 🟨 Amber: Buffer < Recommended Draw but > 0  
  - 🟥 Red: Buffer = 0

---

## 🔧 Data Sources

- `Helios_Personal_Spend_Phase_2.1_Full`  
- `Helios_Professional_Spend_Phase_2.1_Full`  
- `Xero CSV` uploads  
- `Bank CSV` uploads

---

## ✅ Operational Use

- Run check weekly (or as needed after payments)  
- Use “Safe to Draw” status to confirm pay timing  
- Update `Control Panel` variables if buffer, MIF, or UC rules shift  
- Approve IMPORTRANGE permissions on first load

---

## 🛠️ Future Enhancements

- [ ] Automate Xero and Bank feeds using Coupler/Make  
- [ ] Add "Why UNSAFE?" flags to improve explainability  
- [ ] Expand to Looker Studio for visual reporting (Phase 4+)  
- [ ] Add sandbox tab for “What if I paid £X?” simulations

---

## 🧷 Related Modules

- `📐 FS-Build_DashboardStructure.md` (technical build spec)  
- `📊 FS-View_FinancialDashboard.md`  
- `💼 FS-Logic_DirectorPayEngine.md`  
- `Helios Draw Module Plan.pdf`
