---
type: tracker
category: vault_structure
tags: [helios, fss, structure, standard]
last_updated: 2025-07-12
title: Vault Structure Standard – Financial Stability System
status: active
---

# 📁 Vault Structure – Helios Financial Stability System (Standard)

> Canonical folder structure for the Financial Stability System engine inside `Helios System Core`.

This structure ensures clarity, maintainability, and smooth automation across logic, data, dashboards, and trackers.

---

## 🔹 Folder Overview

### 📁 Index/
- Contains: `FS-Index_FinancialStabilitySystem.md`
- Purpose: Master Dataview index for browsing all components

### 📁 Logic/
- Files: `FS-Logic_*.md`
- Purpose: Core system logic and calculation files (e.g., SafeToDraw, DirectorPayEngine)

### 📁 Data/
- Files: `FS-Data_*.md`
- Purpose: All data sources — manual logs, Starling feeds, spending exports, etc.

### 📁 Views/
- Files: `FS-View_*.md`
- Purpose: Dashboards and decision interfaces (e.g., Modular Output Generator, Draw Readiness)

### 📁 Tracker/
- Files: `Tracker_*.md`
- Purpose: Phase tracking, build logs, manifest generator, decision logs

### 📁 CSV_Structures/
- Purpose: Schema definitions and sample CSVs for ingestion or testing

### 📁 XLSX_Builds/
- Purpose: Archived spreadsheet-based logic (historical/pre-Obsidian)

### 📁 Archive/
- Purpose: Retired or deprecated files no longer in active use

### 📁 Modules/
- Purpose: External modules (e.g. Python Streamlit app, MOG scripts) used to augment or connect the vault

### 📁 References/
- Purpose: High-level documentation, system overviews, logic maps

---

## 🔐 Notes
- Every file should include frontmatter with `type:`, `category:`, `last_updated:`, and `title:`
- This structure is designed to support future API wrapping, Obsidian → Web syncing, and modular export
- If folder contents expand, create `README.md` in each folder with internal indexing

