---
title: Weekly Digest Planner Module
tags: [fss, digest, nudges, planning, google-apps-script]
created: 2025-07-16
---

# 📬 Weekly Digest Generator – Helios Financial Stability System

This module generates a **weekly summary digest** that includes insights from the live system:

---

## 🔍 Included in the Weekly Digest:

- ✅ **Week range** (auto from dashboard)
- ✅ **UC Status** + **Buffer Status**
- ✅ **Tee Covered?**
- ✅ **Safe Drawdown**
- ✅ **AI Advice** (from `HeliosDashboard`)
- ✅ **Savings Goal Progress** (from `SavingsPlanner`)
- ✅ **Suggested Savings (if surplus)**
- ✅ **Shortfall notice (if applicable)**

---

## 🧠 Script: `generateWeeklyDigest()`

```javascript
function generateWeeklyDigest() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dashboard = ss.getSheetByName("HeliosDashboard");
  const planner = ss.getSheetByName("SavingsPlanner");

  const weekStart = dashboard.getRange("B2").getDisplayValue();
  const weekRange = dashboard.getRange("B1").getDisplayValue();
  const ucStatus = dashboard.getRange("B6").getDisplayValue();
  const bufferStatus = dashboard.getRange("B7").getDisplayValue();
  const teeCovered = dashboard.getRange("D2").getDisplayValue();
  const drawdown = dashboard.getRange("F2").getDisplayValue();
  const aiAdvice = dashboard.getRange("B15").getValue(); // AI Advice content

  let savingsSummary = "";
  if (planner) {
    const data = planner.getDataRange().getValues().slice(1);
    if (data.length === 0) {
      savingsSummary = "_No savings goals found._";
    } else {
      savingsSummary = data.map(row => {
        const [name, target, deadline, weeksLeft, needed, suggested, saved, status] = row;
        return `• **${name}** – Saved £${saved} of £${target}. This week: £${suggested} ➜ _${status}_`;
      }).join("\n");
    }
  }

  const doc = DocumentApp.create(`Helios Weekly Digest – ${weekStart}`);
  const body = doc.getBody();
  body.appendParagraph(`📅 **Weekly Financial Digest** – ${weekRange}`).setHeading(DocumentApp.ParagraphHeading.HEADING1);
  body.appendParagraph(`🟩 UC Status: ${ucStatus}`);
  body.appendParagraph(`🟦 Buffer Status: ${bufferStatus}`);
  body.appendParagraph(`👩‍👦 Tee Covered: ${teeCovered}`);
  body.appendParagraph(`💷 Safe Drawdown: £${drawdown}`).setSpacingAfter(10);

  body.appendParagraph("🧠 AI Advice:").setHeading(DocumentApp.ParagraphHeading.HEADING2);
  body.appendParagraph(aiAdvice || "_No advice available._").setSpacingAfter(15);

  body.appendParagraph("🎯 Savings Goals Status:").setHeading(DocumentApp.ParagraphHeading.HEADING2);
  body.appendParagraph(savingsSummary);

  doc.saveAndClose();

  Logger.log(`Digest generated: ${doc.getUrl()}`);
}
```

---

## 🗓️ Trigger

Add to `runWeeklyPlanner()` if you want this to run automatically every Sunday/Monday:

```javascript
generateWeeklyDigest();
```

---

## 📍Output

- Google Doc titled `Helios Weekly Digest – YYYY-MM-DD`
- Link is logged to execution history
- Can be extended to auto-email or export to PDF
