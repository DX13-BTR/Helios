---
type: tracker
category: uc
system: financial-stability
tags: [uc, planner, snapshot, impact]
last_updated: 2025-07-12
---

> Snapshot generated on 12 July 2025

This file captures the current Universal Credit (UC) drawdown safety logic layer and its dependencies within the Financial Stability System.

---

## Source File
- `Planner_Main.gsheet` (with XUP → "Not so hidden helper sheet")

---

## Key Fields
| Metric | Explanation |
|--------|-------------|
| Period | Assessment window (e.g. 16/6/25) |
| Mike/Tee MIF | Monthly income floor, calculated from essential+buffer needs |
| Combined MIF | Total safe household target |
| Total Proposed Draw | Combined proposed salary/dividend values from DPE |
| Shortfall/Surplus | Net result: Total Draw - MIF |
| UC Work Allowance | Threshold before tapering |
| Earnings Above WA | Income exceeding the threshold |
| UC Taper Deduction | % deduction from UC based on taper rate |
| UC Taper Rate | Set to 55% as of July 2025 |
| Expected UC Payment | Net UC after taper deduction |
| Base Entitlement | Standard allowance + child/disability elements |
| Draw Safety | Whether the draw is UC-safe and system-safe |
| Traffic Light Status | UC-safe recommendation (✔, ⚠, ❌) |
| Recommended Safe Draw | Value after adjusting to keep within UC safe bounds |

---

## Notes
- This sheet **bridges personal cash flow** and **UC survival strategy**
- All logic respects safe drawdowns vs UC taper impact
- Future automation may pull this data live from DWP APIs (in app version)

Reference Location: `Financial Stability System > Logic_Txt`
