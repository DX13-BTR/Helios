---
type: logic
category: drawdown
system: financial-stability
tags: [pay-engine, director, logic, buffer]
last_updated: 2025-07-12
---


**Role:** Calculates safe drawdown amounts for both Mike and Teresa, using buffer logic and Corporation Tax reserve thresholds. Helps balance UC compliance, company cashflow, and internal safety.

## Inputs
- Safe Available Funds (from Company Tracker or calculated)
- CT Reserve (19% rule)
- Buffer Reserve Target (e.g. £500)
- Manual input of proposed salary/dividend

## Outputs
- Traffic Light Indicator (Pay Safe or Hold)
- Total proposed drawdown
- Mike vs Teresa breakdown
- Reserve protection logic

## Columns
| Field                  | Description                                  |
|------------------------|----------------------------------------------|
| Tee Base Salary        | Agreed fixed minimum for Teresa              |
| Proposed Draw Columns  | Optional add-ons (salary/dividend)           |
| CT Reserve             | Auto-calc from income @ 19%                  |
| Pay Safety Indicator   | Green = full draw safe, Red = hold warning   |
| Tee Total              | Consolidated Teresa pay                      |

## Recommendations
- [ ] Add pay notes field for logic explanations
- [ ] Forecast column for planning 1–3 months ahead
- [ ] Link Safe Funds to Company Tracker directly
- [ ] Add historical trend graph over time

