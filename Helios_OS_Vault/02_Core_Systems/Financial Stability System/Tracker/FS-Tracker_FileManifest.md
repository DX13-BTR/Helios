---
type: tracker
category: manifest
tags: [file_manifest, audit, integrity]
title: File Manifest – Helios FSS
last_updated: 2025-07-12
status: live
---

# 🗂️ Helios Financial Stability System – File Manifest

> This file provides a live, auto-generated listing of all core files in this system, including type, last updated date, and tags. It supports audits, packaging, and future system automation.

---

## 📁 Logic Files

```dataview
TABLE file.name as "File", type, last_updated, tags
FROM "Helios System Core/Financial Stability System/Logic"
SORT file.name ASC
```

---

## 📁 Data Files

```dataview
TABLE file.name as "File", type, last_updated, tags
FROM "Helios System Core/Financial Stability System/Data"
SORT file.name ASC
```

---

## 📁 View Dashboards

```dataview
TABLE file.name as "File", type, last_updated, tags
FROM "Helios System Core/Financial Stability System/Views"
SORT file.name ASC
```

---

## 📁 Tracker & Planning Files

```dataview
TABLE file.name as "File", type, last_updated, tags
FROM "Helios System Core/Financial Stability System/Tracker"
SORT file.name ASC
```

---

## ✅ Manifest Use Cases

- 📦 Packaging for distribution or client-ready builds  
- 🔍 Integrity checks for out-of-date logic  
- 📑 Dashboard into vault activity  
- 🧠 Feeding a future CLI/script engine for automation


```dataview
LIST
WHERE file.name = "FS-Logic_UCSafeDrawdown_Tracker"
```

