---
type: view
category: dashboard-overview
system: financial-stability
tags: [layout, overview, dashboard]
last_updated: 2025-07-12
---


This file defines the **construction logic** and data relationships that drive all dashboard outputs in the Financial Stability System (FSS).

---

## Master Source Layers

### 1. Company_Tracker.gsheet
- Provides: Income, Expenses, CT Reserve, Opening/Closing Balances
- Pushes: Safe Available Funds, Net Cash Movement
- Used in: FS-Logic_CompanyTracker, FS-View_LiveDashboard

### 2. Director_Pay_Engine.gsheet
- Provides: Pay safety, base and proposed salaries, buffer thresholds
- Pushes: Pay Safety Indicator
- Used in: FS-View_FinancialDashboard

### 3. Planner_Main.gsheet
- Purpose: Universal Credit integration planner
- Contains: MIF logic, taper deductions, earnings above WA, UC calculations
- Used to confirm drawdown timing and UC impact status

---

## Logic Layer Mapping

- `FS-Logic_CompanyTracker` feeds:
  - Financial Dashboard (net movement, reserves)
  - Live Dashboard (invoice pipeline, safe funds)

- `FS-Logic_DirectorPayEngine` calculates:
  - Draw proposals
  - Buffer threshold comparisons

- `FS-Logic_UCSafeDrawdown_Tracker` confirms:
  - MIF-based draw tolerances
  - Adjusted safe draw and UC-safe status

---

## Dependencies

- CSV data: Imported into XUP (hidden helper sheet in Planner)
- Manual tagging: Required in Summary_Totals + Personal Spend logs
- Colour logic: Derived from conditional formatting scripts, not baked into logic layer (flag for app version)

**File references**: FS-Data_*, FS-Logic_*, FS-View_* files
