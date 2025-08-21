---
type: view
category: simulator
system: financial-stability
tags: [simulator, drawdown, manual-check]
last_updated: 2025-07-12
---


**Role:** Standalone drawdown simulation dashboard for evaluating UC-safe and buffer-safe payments manually. Offers traffic-light guidance and draw recommendations based on rolling essential spend and available buffer.

---

## 📅 Last Updated
2025-07-12

---

## 📂 File: `Helios_Safe_to_Draw_Dashboard.xlsx`

---

## 🔢 Key Metrics Tracked

| Metric                          | Description                                                  |
|---------------------------------|--------------------------------------------------------------|
| 30-Day Rolling Essential Spend  | Baseline spend over 30 days (input for draw logic)           |
| 60-Day Rolling Essential Spend  | Medium-term view of trend                                    |
| 90-Day Rolling Essential Spend  | Long-term stability view                                     |
| MIF Target                      | Minimum Income Floor for UC purposes                         |
| Recommended Draw                | MIF – 30-day essentials                                      |
| Current Buffer Available        | Real cash buffer available                                   |
| Adjusted Safe Draw Amount       | Capped draw recommendation (MIN of Buffer vs Draw)           |
| Traffic Light Status            | Status: Safe / Partial / Hold                                |
| Next Best Payment Date          | Payment suggestion aligned to UC timeline                    |

---

## 🧠 System Context

- ✅ Used to validate draw decisions if dashboard is down or under revision  
- ✅ Quick reference version for manual override or testing alternate values  
- 🟡 Partially duplicated by live Google Sheet dashboard  
- 🛑 Not automatically fed by other sheets — manual input required

---

## 🔧 Suggested Improvements

- [ ] Migrate logic to main dashboard and unify formulas  
- [ ] Add risk notes based on taper rules or buffer thresholds  
- [ ] Offer dropdowns for UC mode, aggressive/safe draw intent  
- [ ] Auto-calculate safe draw dates with toggles for calendar sync

---

## 🧷 Related Notes

- `📊 FS-View_LiveDashboard.md`  
- `📐 FS-Build_DashboardStructure.md`  
- `💼 FS-Logic_UCSafeDrawdown_Tracker.md`  
- `Helios Draw Module Plan.pdf`
