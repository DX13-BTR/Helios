---
type: tracker
category: build_plan
tags: [helios, fss, planning, sequence]
last_updated: 2025-07-12
status: in_progress
title: Helios FSS - Phase-by-Phase Build Plan
---

# 🚀 Helios Financial Stability System — Build Plan Tracker

This file outlines the step-by-step build sequence to align **Obsidian**, **Google Sheets**, **Python**, **Starling**, and **Xero** into a unified, interactive product.

---

## 🔹 PHASE 1: Finalise the Obsidian Core (Spec + Audit Layer)

**🎯 Goal:** Lock the brain of the system — logic, structure, and audit trail.

- [x] Finalise `FS-Index_FinancialStabilitySystem.md` with correct frontmatter and filters.
- [ ] Create **Modular Output Generator (MOG)** using DataviewJS.
- [ ] Create **File Manifest Generator** to track logic file metadata.
- [ ] (Optional) Prepare `Data_DrawLog.md` to receive Python-generated logs.

📌 **Outcome:**  
Obsidian vault is audit-ready, browsable, and acts as the system spec and fallback.

---

## 🔹 PHASE 2: Consolidate Inputs — Starling + Xero Ingestion

**🎯 Goal:** Replace manual entry with live financial data.

- [x] Starling → Google Sheets working.
- [ ] (Optional) Build direct Starling API pull (remove Sheets dependency).
- [ ] Create Xero API App + auth setup.
- [ ] Build `xero_module.py` to pull:
  - [ ] Outstanding bills
  - [ ] PAYE/NI liabilities
  - [ ] VAT owed
  - [ ] CT buffer (manual or rule-based)
- [ ] Merge Starling + Xero into a unified ingestion payload.

📌 **Outcome:**  
Live daily data from both cash and accounting system → logic engine-ready.

---

## 🔹 PHASE 3: Build the Python DPM App MVP (Live Logic Engine)

**🎯 Goal:** Translate Obsidian logic into an actionable, real-time tool.

- [ ] Set up Python + Streamlit environment (`venv`, `requirements.txt`).
- [ ] Build modular app:
  - [ ] `input_module.py` → load Starling/Xero or manual input
  - [ ] `calc_engine.py` → draw logic, UC taper, buffers
  - [ ] `output_module.py` → CSV, PDF, traffic light decision
  - [ ] `dividend_generator.py` → branded PDF vouchers
- [ ] Build `main.py` Streamlit UI.

📌 **Outcome:**  
You can click a button, see your safe draw, and generate outputs.

---

## 🔹 PHASE 4: Connect Obsidian + Python + Google Sheets

**🎯 Goal:** Traceability and optional sync between systems.

- [ ] Export draw results to `Data_DrawLog.md`
- [ ] (Optional) Push results to Google Sheets for archiving.
- [ ] Create `config.yaml` or `.json` pulled from Obsidian or synced settings.

📌 **Outcome:**  
System feels unified. History preserved. Config versioned in vault.

---

## 🔹 PHASE 5: Package and Productise

**🎯 Goal:** Make the tool usable by Teresa, then other accountants.

- [ ] Package Python app via `auto-py-to-exe`.
- [ ] Finalise `config_template.yaml` for safe reuse.
- [ ] Package Obsidian vault with:
  - [ ] Sample data files
  - [ ] README
  - [ ] MOG and Manifest
- [ ] Add usage instructions + screen walkthrough.

📌 **Outcome:**  
Ready for internal team, early clients, or external rollout.

---

## 🧠 Notes

- Starling and Xero together create the **real-time data foundation**.
- Obsidian remains the **logic and audit layer**.
- Python is the **interactive decision engine**.
- All three are modular and separable if needed, but designed to be unified.

---
---
type: build_snapshot
source: helios
date: 2025-07-12
status: complete
tags: [financial-stability, snapshot, build-log]
---
