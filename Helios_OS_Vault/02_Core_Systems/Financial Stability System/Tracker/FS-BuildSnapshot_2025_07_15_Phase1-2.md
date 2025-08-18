---
title: FS-BuildSnapshot – Phase 1 & 2
date: 2025-07-15
status: complete
tags: [financial-stability, snapshot, system-build, helios]
---

# ✅ Financial Stability System – Phase 1 & 2 Snapshot

## 🧠 Core Goal  
Fully automated, UC-aware personal & business cash flow planning engine built for product pivot and Helios dashboard integration.

---

## 🔁 Daily Automation Chain (via `runDailyPlanner()`)

| Step | Function | Description |
|------|----------|-------------|
| 1 | `generate90DayForecastSheet()` | Projects recurring income/expenses forward 90 days |
| 2 | `injectTeePaymentIntoForecast()` | Adds fixed £650 Tee payment on the 15th |
| 3 | `generateDrawdownSuggestion()` | Calculates safe weekly drawdown window |
| 4 | `generateSummaryViews()` | Adds weekly/monthly income/expense summaries |
| 5 | `evaluateUCThreshold()` | Flags monthly UC safety limit breaches |
| 6 | `calculateTaperedBuffer()` | Tracks rolling 2-week buffer with taper |
| 7 | `generateSavingsGoalSuggestion()` | Calculates how much can be saved this week |
| 8 | `generateSpendingOptimiser()` | Flags high or frequent spending by merchant |
| 9 | `generateDirectorPaySuggestion()` | Determines if/when Mike can safely pay himself |

---

## ✅ Phase 1 Modules (Stability Layer)

- `WeeklySummary` and `MonthlySummary` views
- `UCMonitor` tab with fixed £2450 threshold + safety flags
- `BufferMonitor` with taper logic (starts at 25%, grows 5%/week)

---

## ✅ Phase 2 Modules (Growth & Control)

- `SavingsPlanner` suggests weekly savings after Tee/bills/buffer
- `SpendingOptimiser` flags wasteful or repetitive merchant spend
- `DirectorPayPlanner` ensures safe drawdown + UC-aware pay trigger

---

## 📁 Active System Tabs

- `DailyMetrics`
- `Forecast_90DayDaily`
- `DrawdownPlanner`
- `StarlingSnapshot`
- `Starling_*Transactions`
- `RecurringTransactions`
- `WeeklySummary`, `MonthlySummary`
- `UCMonitor`, `BufferMonitor`
- `SavingsPlanner`, `SpendingOptimiser`, `DirectorPayPlanner`

---

## 🔧 System Traits

- All modules triggered via `runDailyPlanner()`
- Fully automated via 07:00–07:08 time-based triggers
- Designed for productisation and dashboard surfacing
- Tee’s payment logic is top-priority and immutable
- Live balance → not assumption-based → zero manual updates

---

✅ *Next Phase: Dashboard planning + visual overlays for product-ready UI*

