---
type: view
category: dashboard-overview
system: financial-stability
tags: [layout, overview, dashboard]
last_updated: 2025-07-12
---

---


This file defines the **visual structure** and intent of each view-based dashboard in the Financial Stability System (FSS), for reference in UI layer planning and system integration.

---

## 1. Financial Dashboard (FS-View_FinancialDashboard)
- **Source**: Company_Tracker + Director_Pay_Engine
- **Metrics**: Rolling Spend, Income Projections, CT Reserve, Draw Recommendations, Buffer Target
- **Traffic Light System**: Shows live safety status of draw recommendations
- **Notes**: This view is referenced by the Planner.Main sheet as a key decision layer

## 2. Live Dashboard (FS-View_LiveDashboard)
- **Source**: Company_Tracker
- **Purpose**: Mirrors live cash position, invoice pipeline, upcoming bills, and safe funds
- **Notes**: Replaced the original Helios_Live_Dashboard.txt; superseded by integrated logic

## 3. Safe to Draw Dashboard (FS-View_SafeToDrawSimulator)
- **Source**: Helios_Safe_to_Draw_Dashboard.xlsx
- **Calculations**:
  - Rolling 30/60/90-day Essential Spend
  - MIF Target
  - Draw Recommendation
  - Adjusted Safe Draw
  - Partial/Unsafe/Green indicator
- **Use**: Helps determine drawdown timing based on rolling trends

---

**Reference Location**: `Financial Stability System > Logic_Txt` in Obsidian vault
