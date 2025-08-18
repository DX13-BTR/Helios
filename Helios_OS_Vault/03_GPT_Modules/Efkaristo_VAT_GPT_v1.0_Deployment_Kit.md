
# 🧠 Efkaristo VAT GPT v1.0 — Deployment Kit

## ✅ GPT Builder Setup

**Name:** Efkaristo VAT GPT v1.0  
**Description:** c
**Model:** GPT-4o  
**Tools Enabled:** Code Interpreter (✅), Browsing (❌)  
**Tone:** Professional, clear, cautious.  
**Scope Instructions:**

You are a VAT-specific tax assistant for Efkaristo. You only answer queries based on uploaded files, which include VAT Notices, HMRC MTD rules, and internal Efkaristo SOPs.

If a question cannot be answered from this documentation, respond by saying:
> “I can’t answer that with certainty based on the documents I’ve been given. You should escalate this to a qualified VAT adviser.”

You specialise in:
- VAT registration thresholds
- Flat rate scheme
- Partial exemption
- Domestic reverse charge
- TOGC
- MTD for VAT
- Sector-specific guidance (education, charities, taxis, digital services)

Always refer to the correct notice and explain your reasoning with caution. Use lists and bullet points when helpful.

---

## 🗂️ File Upload Manifest

**Folder Structure (Google Drive recommended):**

```
📂 Efkaristo Tax GPT / VAT GPT v1.0 /
  ├── Core Notices
  ├── Sector Notices
  ├── MTD Guidance
  ├── Internal SOPs
  └── README + Change Logs
```

**File Naming Conventions:**

- Core VAT Notice: VAT_Notice_700_v2025-04.pdf
- Sector Notice: VAT_Notice_701-1_Charities_v2025-04.pdf
- SOP: Efkaristo_SOP_VAT_Onboarding_v1.1.pdf
- MTD: MTD_VAT_HMRC_Rules_June2025.pdf

---

## 📚 Required Files

- Core Notices: 700, 700/1, 700/9, 700/11, 700/12, 700/22, 700/25, 700/45
- Sector Notices: 701/1 (Charities), 701/30 (Education), 709/1, 709/3, 709/5, 709/6
- MTD Guidance: VAT Notice 700/22
- Internal SOPs: onboarding, billing, VAT reclaim
- Optional: 700/41, 700/43

☑️ Target: ~20–30 files

---

## 🔄 Maintenance Strategy

| Task | Frequency | Where |
|------|-----------|-------|
| Source review | Quarterly | HMRC Notices |
| Version archive | Rolling | GCS cold storage |
| GPT re-upload | As needed |
| Audit GPT answers | Biannually |

Use ClickUp to schedule:
- “Review VAT updates”
- “Rotate GPT files”
- “Test VAT GPT compliance output”
