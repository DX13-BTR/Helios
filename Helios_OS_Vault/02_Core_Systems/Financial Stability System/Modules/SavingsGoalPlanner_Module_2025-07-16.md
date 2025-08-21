---
title: SavingsGoalPlanner() – Automated Savings Suggestion Module
tags: [fss, savings, goals, apps-script, helios]
created: 2025-07-16
---

# 💰 SavingsGoalPlanner() – Automated Goal-Based Saving Engine

This module creates and manages a dynamic savings planner inside your Financial Stability System. It tracks individual savings goals and recommends weekly contributions based on live surplus data and goal deadlines.

---

## 📄 Sheet: `SavingsGoals`

Set up a new Google Sheet tab with the following structure:

| Column | Description |
|--------|-------------|
| A: Goal Name | Name of the goal (e.g. Emergency Fund, Property Deposit) |
| B: Target (£) | Total amount you're trying to save |
| C: Deadline | When you'd like to hit the target (e.g. `2025-11-01`) |
| D: Priority | Optional label (`High`, `Med`, `Low`) |
| E: Saved So Far (£) | Amount already saved |
| F: Suggested Save (£) | Auto-calculated amount to save this week |
| G: Weeks Left | Auto-calculated from deadline |
| H: Weekly Needed (£) | Target - SavedSoFar ÷ WeeksLeft |
| I: Status | `On Track`, `Behind`, `Ahead` (optional future feature) |

---

## 🧠 Script: `generateSavingsGoalSuggestion()`

Paste the following into your Apps Script project:

```javascript
function generateSavingsGoalSuggestion() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("SavingsGoals");
  const plannerSheet = ss.getSheetByName("SavingsPlanner") || ss.insertSheet("SavingsPlanner");

  // Clear old results
  plannerSheet.clear();
  plannerSheet.appendRow(["Goal Name", "Target", "Deadline", "Weeks Left", "Weekly Needed", "Suggested Save", "Saved So Far", "Status"]);

  const data = sheet.getDataRange().getValues();
  const header = data[0];
  const rows = data.slice(1);

  const today = new Date();
  const surplus = 100; // Replace this with a dynamic calculation from your forecast system
  let remainingSurplus = surplus;

  rows.forEach(row => {
    const [name, target, deadlineStr, priority, savedSoFar] = row;
    if (!name || !target || !deadlineStr) return;

    const deadline = new Date(deadlineStr);
    const diffMs = deadline - today;
    const weeksLeft = Math.max(1, Math.floor(diffMs / (1000 * 60 * 60 * 24 * 7)));
    const neededPerWeek = Math.max(0, (target - savedSoFar) / weeksLeft);
    const suggested = Math.min(neededPerWeek, remainingSurplus);

    remainingSurplus -= suggested;

    plannerSheet.appendRow([
      name,
      target,
      deadlineStr,
      weeksLeft,
      neededPerWeek.toFixed(2),
      suggested.toFixed(2),
      savedSoFar,
      suggested >= neededPerWeek ? "On Track" : "Behind"
    ]);
  });
}
```

---

## 🔁 Optional: Add to `runDailyPlanner()`

Append this to the bottom of your `runDailyPlanner()` function:

```javascript
generateSavingsGoalSuggestion();
```

---

## 📊 Dashboard Integration (Phase 2)

You can pull total suggested savings from `SavingsPlanner!F2` or generate a visual progress bar later.

---

## ✅ Outcome

- Named goals
- Weekly suggestions that evolve as buffer/surplus changes
- Actionable savings plan for property, emergencies, or seasonal costs

---
