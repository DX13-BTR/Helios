---
type: logic
category: company
system: financial-stability
tags: [company-tracker, logic, cashflow]
last_updated: 2025-07-12
---


**Role:** Monthly financial safety dashboard to determine whether drawdowns are advisable. Central logic layer connecting income, expenses, reserve thresholds, and safe-to-pay analysis.

## Tabs + Purpose

- **Company_Tracker**: Master logic table with drawdown flags
- **Summary_Totals**: Auto-pulls totals from categorised imports
- **Xero_Upload**: Clean, categorised import from Xero
- **Raw_Xero_Import**: Original, unfiltered Xero extract

## Key Fields

| Field                  | Description                                          |
|------------------------|------------------------------------------------------|
| Income Received        | From Summary_Totals                                  |
| Expenses Paid          | From Summary_Totals                                  |
| Corporation Tax Reserve | 8.33% of Income                                      |
| Safe Available Funds   | Closing - Reserve - Bills - Tax                      |
| Recommended Draw Funds | Only populated if buffer threshold is met            |
| Traffic Light Status   | Red if buffer < target, else Green                   |

## Risk Logic

- ✅ **Green**: Buffer met → OK to draw
- 🟡 **Amber**: Optional idea — near buffer edge
- ❌ **Red**: Hold all payments

## Improvements To Add
- [ ] Automation from Starling/Xero
- [ ] Add 30/60 day rolling burn rates
- [ ] Notes field for flag justification
- [ ] Consolidate with personal tracker later

