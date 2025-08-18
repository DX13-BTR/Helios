---
title: generateAIAdvice() – GPT-Powered Financial Nudging
tags: [fss, apps-script, gpt, openai, advice-layer]
created: 2025-07-16
---

# 🤖 generateAIAdvice() – Smart Spending Suggestions with GPT

This module adds **context-aware financial advice** to your FSS system by using the OpenAI API to turn your live sheet data into clear, natural-language nudges.

---

## ✅ What It Does

1. Pulls key data from:
   - `HeliosDashboard` (UC status, buffer %, drawdown)
   - `SpendingOptimiser` (top merchants)
   - `SavingsPlanner` (suggested savings)
2. Creates a prompt summarising your current week
3. Sends it to OpenAI via `UrlFetchApp`
4. Logs the returned advice to `AdviceOutput` for dashboard display

---

## 🧰 SETUP INSTRUCTIONS

### 1. 🔑 Get your OpenAI API key

If you don’t already have one:
- Go to https://platform.openai.com/account/api-keys
- Click **Create new secret key**
- Copy it. You’ll paste it in Step 3.

---

### 2. 📄 Add `AdviceOutput` sheet if not already present

Columns:
```
| Week Start | AI Advice |
```

---

### 3. 🧠 Paste this into your Apps Script editor

```javascript
function generateAIAdvice() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dashboard = ss.getSheetByName('HeliosDashboard');
  const optimiser = ss.getSheetByName('SpendingOptimiser');
  const savings = ss.getSheetByName('SavingsPlanner');
  const adviceSheetName = 'AdviceOutput';
  const apiKey = 'PASTE_YOUR_OPENAI_KEY_HERE';

  // Ensure advice sheet exists
  let adviceSheet = ss.getSheetByName(adviceSheetName);
  if (!adviceSheet) {
    adviceSheet = ss.insertSheet(adviceSheetName);
    adviceSheet.appendRow(['Week Start', 'AI Advice']);
  }

  const buffer = dashboard.getRange('B6').getValue(); // e.g. "194.0%"
  const drawdown = dashboard.getRange('B8').getValue();
  const ucStatus = dashboard.getRange('B4').getValue();
  const teeCovered = dashboard.getRange('B9').getValue();
  const savingsSuggested = savings.getRange('D2').getValue();

  const spendData = optimiser.getDataRange().getValues().slice(1);
  const topMerchants = spendData
    .sort((a, b) => b[1] - a[1]) // Sort by spend
    .slice(0, 3)
    .map(row => `${row[0]}: £${row[1]} (${row[2]} txs)`).join(', ');

  const prompt = `
This week’s financial state:
- UC Status: ${ucStatus}
- Buffer Achieved: ${buffer}
- Suggested Drawdown: £${drawdown}
- Tee Payment Covered: ${teeCovered}
- Suggested Savings: £${savingsSuggested}
- Top Merchants: ${topMerchants}

What should I do this week to optimise my finances, maintain my buffer, and reach my savings goals?
Return up to 3 pieces of practical, human-readable advice.
`;

  const response = UrlFetchApp.fetch("https://api.openai.com/v1/chat/completions", {
    method: "post",
    headers: {
      "Authorization": "Bearer " + apiKey,
      "Content-Type": "application/json"
    },
    payload: JSON.stringify({
      model: "gpt-4o",
      messages: [{ role: "user", content: prompt }],
      temperature: 0.7
    }),
    muteHttpExceptions: true
  });

  const content = JSON.parse(response.getContentText());
  const advice = content.choices?.[0]?.message?.content ?? "No advice returned.";

  adviceSheet.appendRow([new Date(), advice]);
}
```

---

## ✅ Final Steps

1. Replace `'PASTE_YOUR_OPENAI_KEY_HERE'` with your actual API key
2. Run `generateAIAdvice()` from Apps Script
3. Advice will appear in `AdviceOutput` and can be pulled into your dashboard

---

## 🛠 Optional (Next Steps)

- Add `generateAIAdvice()` to `runDailyPlanner()`
- Display advice on your HTML dashboard
- Add fallback to `generateSpendingAdvice()` if GPT fails

---
