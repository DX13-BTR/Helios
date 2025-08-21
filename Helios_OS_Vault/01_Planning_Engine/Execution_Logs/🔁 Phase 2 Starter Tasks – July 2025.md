This document tracks progress and systemisation steps for the first three Phase 2 improvements in the Efkaristo Apps & Tools Review Build.

---

## ✅ Task 1: ClickUp Automation Layer – Subtask Completion → Auto-Assign Next Step

**System:** ClickUp  
**Priority:** High

### Goal:

Ensure when Teresa completes a subtask, the next linked task auto-assigns to Mike.

### Steps:- 
- [ ]  Create a recurring automation inside ClickUp for relevant Lists (e.g., Client folders)
- [ ] Set trigger: “When subtask status changes to ‘Complete’.”
- [ ] Add condition: “Subtask assigned to Teresa.”
- [ ] Use dependency: Check for ‘next task’ or linked task in a chain
- [ ] Action: Assign next task to Mike
- [ ] Optional: Add comment to the new task, e.g., “Picked up automatically after Teresa’s step complete.”
- [ ] Test using test client record with 3 subtasks in sequence
- [ ] Confirm assignment fires only once and to correct person
- [ ] Document this inside ClickUp Automation Reference doc (Internal SOPs)


---

## ✅ Task 2: Financial Stability Feed – Starling & Tide Balance Sync

**System:** Starling / Tide  
**Priority:** High

### Goal:

Build a feed that pulls account balances automatically into a daily dashboard (Obsidian, Google Sheet, or ClickUp).

Account UID: 3b2f74a9-a00f-49ad-bce4-0081a4282c99
PAT for business -
eyJhbGciOiJQUzI1NiIsInppcCI6IkdaSVAifQ.H4sIAAAAAAAA_42QS27DMAxEr1JoHQb6W_Yuu16gB6BEJjDiSoalFAWK3r0KXPSzKbobcOYNSL6JuVYxCVznY224LXO-RMzXYyrP4iDqLXbTexcGQgVKxTNY21UkrwGHEJwiHZXyPcyvq5jsKINU4-iHg5ixiUkNThvrzX2AKZVbbo9lId6eZvp_dytXzjuBTiZrrQFyksCyloBMDqRlZ2kMxivTiX7RKSWu9ZvqVQ6iok7pYYRgYi-JTEFjsD7eqZrKyvf4vum0MdJDxZf-lgqXggu0DXM98_aXlbrX-Je5xyMumBN_sit-yZ_JnRbvHwYs-lucAQAA.cgAfTPOcDDJLZJnin2_lKvNL1R2VBw-fIl0xrAEOedu9dhc7lhvK-oKTEsTzK8EFMYVWypspM12RmbhQjwhpzsZ97mquJo3Iwko0B8AsMFDF9XhMrVOSN6s2p7UZHgRIB1ISNtd0Lx-RAiBjUYA59oFb4idw1kE50-D0fxHvXKgycdbS1rV6Kip4FUnP6btiZKxQdltr17ZM_qqTIwc7ALlpgww3zLzv9RGqEGwhoQz3pr_1Rb1GX19sRxxRU_lwr3E7BEqYCxAII_lXONEzRfSLCSWRdfZg4oeNu-4aMpRrUsMhkWjbkKdu3spmCeFWF1Mo7zz_faUy5d1NiJqLJ-23wmmsrs67gNUzN6v9vTZg0gCzIqovNEwpPvSg5xm-46qo0pKOwhb0a0ukJE3rAZCifCR6zfLs2fU7VjoJEnN_lp7GjPJzwASgbK9pF2LubnNf3sf5PVoFyw9S--FBGuIEEpmVgjPLiN-kHsQV__Uob9seJiOedqJSm6mdcBG8TQI0IpA89DKyQsmjGfeTc3skVbwoi3mCoOGpseHcdDv1E6dUZ0LLzMvAPW_eaGTT6qC80RTk5tE-foP8NjqMp0Wca6UxTcklLlBJ2-xcdbscKTQZEuunk2kDoN21wqzsQlSMHFkw8F49EpWgL1504TIe-kW6JtL8Q4Zy5nJrHXQ

✅ Account UID: 347e4a4a-569e-448d-b44c-75697ab1fe77
Personal:
eyJhbGciOiJQUzI1NiIsInppcCI6IkdaSVAifQ.H4sIAAAAAAAA_32QTWrEMAyFrzJ4PR5sR3Hs7GbXC_QAkiUPYdIkxJlSKL17HZrSQqE7Se99-ntXQymqV7gMl7LhOg7TjXC6X9L8os6qPKiK3rehY7TaWsoaoEbE3mnsQmgtO7LWV7O8LaqHaIJxxpjmrAbcVG-71jXgYS9gSvNj2p7mkWV9Hngf3PgAIlkHSU6DYaODAdLsAFqJwuJj7b3Nd5kOojVMCTsdIOzbdE6TFatzzOI4B5ddqkS96JqSlPJDxUy1u2PQ0FBbo1AnCkVj2EaCZj84zYtUe8HX-omibzOO_SrIp2P3r-S3rLcVp5Jl7VPVNjkRjjgl-c_5R_pmy4IHqT4-AQPBmSicAQAA.SU58XwIZJaqEy_ML7dUwAJpp8TMKjWs2O_wjBrwnZ-fNOH_gyVhEWhPCb3rovpJHBIzBcgsUpBGgv2lMoh-LAArUVBWOeXQes1o4DEsKrdXTxF6GWu2CCTqWPBu2dEPvpAOcHmUArPXJMbjxOfDowBbdQNKkfVtpelZcd68xyJOShCgn7Xb_FM_yrdFvQuslRp5kKRjVPi3ahiMVV-QTy0c64tSnW-QVAdAGAJV0sxGSGp4hGrsiOrK-mjtkT6aybk6PtEZHubE5p0Uz6sNSEpBTvWhv7ElySfrVLk25lWg6mcebPrcHsb8wo6-YT8eNi6BbjdcBAi05a0VmQ6mBTuTp5WIxUfGE8q1Nrq2ieFeLL0Ev-1lhmydk5QX6vK6mslZCof1--oLEv-Ctv1JYQZaq8DXgW4_K3rsyWHaNHEOG9rxi1dYmWIgiNbJEn7Ui91944xZ-0Z-ppS_NVnVSYX0NElvsrVlAUZrC-7US1I7KvSh2qFfrWDir8o1DjkklGcMx8xP307O-3UwQwcQ7Yv5oT2h8tn0fohZub596BSzgsaKHjfbdVmHSQYLa0luPtyFp5CTQ23E-_YwUSrYf2sXWP9JNTN0-NlzvFMG0Xz3miIGgPky0AtGsWEUfQvUbQYw1oW5oqXvu6xuh9G7bgOcDlSMyXdsQqjyqXuxSp78

### Steps:
- [ ] Confirm both Starling and Tide API access is available
- [ ] Register/refresh developer credentials for each bank
- [ ] Create Make.com scenario (or Zapier) to call each bank’s `/accounts/balance` endpoint daily
- [ ] Format output: Account name, Balance, Date
- [ ] Push to destination:
  - [ ] Google Sheet (tab = Daily Feed)
  - [ ] Optional: Obsidian CSV import folder
  - [ ] Optional: ClickUp task comment or custom field update
- [ ] Create fallback alert (e.g., email or ClickUp task) if feed fails
- [ ] Build an Obsidian view (if used):
  - [ ] Table with bank name, daily balance, 7-day trend line
- [ ] Add workflow to Financial Feed SOP

---

## ✅ Task 3: Obsidian Dataview – CPD Total & Compliance Tracker

**System:** Obsidian  
**Priority:** Medium

### Goal:

Track total CPD hours for the year and surface compliance gaps.

### Steps:
- [ ] Standardise all CPD notes with the following frontmatter:
  ---
  cpd: true
  hours: 1.5
  date: 2025-07-10
  type: webinar
  topic: VAT reverse charge
  ---
- [ ] Create Dataview table query:
  table topic, type, hours, date
  from "CPD"
  where cpd = true
  sort date desc
- [ ] Add Dataview aggregation block:
  sum hours
- [ ] Add conditional flag for compliance check:
  if sum(hours) < 40, show warning: “CPD hours below annual threshold.”
- [ ] Add view to CPD dashboard note in Obsidian
- [ ] Create reminder in ClickUp/Obsidian to check CPD total quarterly
- [ ] Archive CPD Tracker logic in Internal SOPs (Systems & Knowledge Base)
