---
type: overview
category: system
system: financial-stability
tags: [map, summary, full-system]
last_updated: 2025-07-12
---

---

## 🔧 Purpose
This document provides a full overview of the **Financial Stability System** inside the Helios Core. It connects the key modules and explains how they work together to help Mike and Teresa:

- Maintain stable income from Efkaristo Ltd
- Track business and personal financial health
- Avoid Universal Credit overdraws or clawbacks
- Make strategic draw decisions using buffer and forecast data

---

## 🧩 Core Components

### 1. **Company Tracker**  
**Sheet**: `Company_Tracker`  
**Logic File**: `FS-Logic_CompanyTracker`
- Pulls income and expense data from Xero import
- Calculates available funds, VAT, CT reserves, and upcoming liabilities
- Sets recommended draw limit and buffer safety

### 2. **Director Pay Engine**  
**Sheet**: `Director_Pay_Engine`  
**Logic File**: `FS-Logic_DirectorPayEngine`
- Allocates salary and dividend based on safe funds
- Highlights if proposed draw exceeds safety buffer
- Automates status label: Green / Amber / Red for pay status

### 3. **UC Safe Drawdown Simulator**  
**Sheet**: `SafeToDrawSimulator`  
**Logic File**: `FS-Logic_UCSafeDrawdown_Tracker`
- Uses Starling personal spend logs and draw tracking
- Applies rolling spend calculations (30/60/90 days)
- Calculates MIF, earnings above WA, UC taper
- Outputs safest recommended draw that won't trigger clawback

### 4. **Dashboards**  
**Sheets**:
- `Helios Financial Dashboard` → summary of core metrics
- `Live Dashboard` → real-time rolling draw recommendations
- `SafeToDrawSimulator` → individual draw logic
**Logic Files**:
- `FS-View_FinancialDashboard`
- `FS-View_LiveDashboard`
- `FS-View_SafeToDrawSimulator`

### 5. **UC Planner (Planner_Main)**  
**Sheet**: `Planner_Main`  
**Logic File**: `FS-View_UCPlannerSnapshot`
- Combines proposed draw + MIF + UC taper deduction
- Models the **actual Universal Credit impact**
- Warns if draw is safe, unsafe, or impacts minimum benefit

### 6. **Baseline + Spend Logs**  
**Sources**:
- `Helios_Baseline_Averages_Phase_2.1.xlsx`
- `Helios_Personal_Spend_Phase_2.1_Full.csv`
- `Helios_Professional_Spend_Phase_2.1_Full.csv`
**Logic Files**:
- `FS-Data_BaselineMonthlySpend`
- `FS-Data_PersonalSpendLog`
- `FS-Data_ProfessionalSpendLog`

Used to calculate rolling essential/discretionary/wasteful spend averages across time.

---

## 🔁 Flow Summary
1. **Xero data → Company Tracker → Safe Available Funds**
2. **Safe Funds → Director Pay Engine** → Tee + Mike draw
3. **Safe Funds → SafeToDrawSimulator + UC Planner** → Traffic Light draw recommendation
4. **Outputs summarised in dashboards**

---

## 📌 Status Indicators
- ✅ Green: Full draw safe
- 🟡 Amber: Partial draw safe
- ❌ Red: Do not pay
- 🧮 UC Planner Unsafe: Below MIF or UC Taper triggers clawback

---

## ⏳ Next Step (Post-Manual Stage)
- Convert logic to automated app layer
- API integration for Starling + Xero
- Push notifications for draw timing and limits
- Include Target Buffer forecasts and custom rules per draw

---

**Created for:** Helios OS → Financial Stability System  
**Last updated:** 12 July 2025

