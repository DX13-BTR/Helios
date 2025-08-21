---
type: view
category: dashboard
tags: [helios, fss, metrics, uc-buffer, snapshot-view]
title: Daily Financial Metrics View
status: active
---

# 📊 Daily Financial Metrics – UC Buffer Tracker

This view renders a rolling summary of UC-safe surplus status using daily snapshots stored in the vault.

---

## ✅ Requirements

- Starling snapshot `.md` files must exist in:  
  `Helios_Snapshots/Markdown_Snapshots/`
- Each must include a valid JSON code block in the format:
  ```json
  {
    "efkaristo": { "main": ..., "spaces": { ... } },
    "personal": { "main": ..., "spaces": { ... } }
  }
  ```

---

## 📅 14-Day UC Buffer Trend

```dataviewjs
dv.header(2, "📂 Snapshot Debug Log");

const pages = dv.pages()
  .where(p => p.tags && p.tags.includes("starling") && p.tags.includes("snapshot"))
  .sort(p => p.file.name);

for (let p of pages) {
  dv.header(3, p.file.name);
  dv.paragraph("🧾 Has content: " + (p.file.content ? "✅ Yes" : "❌ No"));
  dv.paragraph("🏷️ Tags: " + (p.tags || []).join(", "));
  dv.paragraph("🗓️ Date field: " + (p.date || "❌ Missing"));
  dv.paragraph("---");
}
```

```dataviewjs
const pages = dv.pages()
  .where(p => p.tags && p.tags.includes("starling") && p.tags.includes("snapshot") && p.date)
  .sort(p => p.date, 'desc')
  .limit(14);

dv.paragraph(`✅ Found ${pages.length} snapshot pages`);

const results = [];

for (const p of pages) {
  if (!p.file || !p.file.content) {
    dv.paragraph(`❌ Skipped file: ${p.file?.name ?? "unknown"} (no content)`);
    continue;
  }

  const match = p.file.content.match(/```json\s*\n([\s\S]*?)```/i);
  if (!match) {
    dv.paragraph(`❌ No JSON match in file: ${p.file.name}`);
    continue;
  }

  const cleaned = match[1]
    .replace(/,\s*}/g, '}')
    .replace(/,\s*]/g, ']');

  let data;
  try {
    data = JSON.parse(cleaned);
  } catch (e) {
    dv.paragraph(`❌ Still failed to parse after cleanup in file: ${p.file.name}`);
    dv.codeBlock(cleaned.trim(), 'json');
    continue;
  }

  const efkMain = data.efkaristo?.main || 0;
  const personalMain = data.personal?.main || 0;
  const efkSpaces = Object.values(data.efkaristo?.spaces || {}).reduce((a, b) => a + b, 0);
  const personalSpaces = Object.values(data.personal?.spaces || {}).reduce((a, b) => a + b, 0);

  const efkaristo = efkMain + efkSpaces;
  const personal = personalMain + personalSpaces;
  const combined = efkaristo + personal;

  const ucThreshold = 2450;
  const surplus = Math.round((combined - ucThreshold) * 100) / 100;

  let status = "✅ UC-Safe";
  if (surplus < 0) status = "⚠️ Below UC Buffer";
  if (surplus < -250) status = "🔻 Critically Low";

  results.push([
    p.date,
    `£${efkaristo.toFixed(2)}`,
    `£${personal.toFixed(2)}`,
    `£${combined.toFixed(2)}`,
    `£${surplus.toFixed(2)}`,
    status
  ]);
}

if (results.length) {
  dv.table(["Date", "Efkaristo (£)", "Personal (£)", "Combined (£)", "UC Surplus (£)", "Status"], results);
} else {
  dv.paragraph("⚠️ No valid data to display.");
}
```

---

## 🔎 Notes

- UC threshold set to **£2450.00** for initial tracking.
- Surplus calculated as `Combined - Threshold`
- Status:
  - ✅ Safe if surplus ≥ 0
  - ⚠️ Below if < 0
  - 🔻 Critical if < -250

---

_Last updated: 2025-07-14  
