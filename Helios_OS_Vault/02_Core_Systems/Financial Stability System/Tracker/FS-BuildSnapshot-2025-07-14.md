## ✅ Build Decision Log – 2025-07-14 (Updated)

**Component:** `FS-View_DailyMetrics.md` (Obsidian DataviewJS)  
**Status:** ❌ Deprecated (logic migrated)

---

### 🔍 Summary:

The Obsidian DataviewJS-based UC buffer trend tracker (`file.content` dependent) was fully implemented with valid `.md` snapshots. However, Obsidian + DataviewJS consistently failed to parse `.file.content` from externally created markdown files — even after:

- Manual edits in source mode
    
- Offline sync enforcement
    
- JSON block and YAML frontmatter validation
    
- Plugin re-indexing and config verification
    

Despite valid rendering in Obsidian, DataviewJS continued to return `file.content: ❌ No`, making automated parsing unreliable for daily metrics.

---

### 🔁 Decision:

**Deprecate `.md`-based metrics tracker.**  
Shift all daily financial outputs to **Google Sheets**, where:

- File content is fully controllable
    
- Snapshots are structured and appendable
    
- Visualisation and automation are easier
    

---

### ✅ Final Output State:

- `DailyMetrics` tab logs all snapshot summaries (Efkaristo, Personal, Combined, Surplus, UC tagging)
    
- `DailyMetrics_14DayTracker` tab auto-refreshes with the 14 most recent records
    
- Conditional formatting applied for buffer status:
    
    - ✅ UC-Safe → green
        
    - ⚠️ Below UC Buffer → yellow
        
    - 🔻 Critically Low → red
        

---

### 🧭 Next Actions (for future session):

**🔄 Optional Next Visuals (Sheet-native):**

-  Add line graph of UC Surplus over 14 days
    
-  Highlight today's row using conditional formatting
    
-  Add "days until recovery" estimate if buffer is below target
    

**📊 Core Build: Xero Integration Phase**

-  Start `xero_module.gs` to ingest Xero bank balances (Efkaristo Ltd)
    
-  Normalize and combine with Starling snapshot to support:
    
    -  Unified cash position
        
    -  Real surplus vs booked accruals
        
    -  Drawdown planning logic
        

**📦 Optional System Enhancements**

-  Add PDF export of 14-day tracker for report archive
    
-  Add email notification trigger if surplus < -£250
    
-  Add chart view to Sheets (optional sparkline / chart tab)