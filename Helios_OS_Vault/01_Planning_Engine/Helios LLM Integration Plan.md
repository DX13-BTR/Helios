# 🧠 **Helios LLM Integration Plan**

_Finalised AI Integration Scope for FSS + Weekly Planning Logic (GPT-4.1)_

---

## ✅ **Modules Fully Owned by GPT-4.1**

> GPT generates the _entire_ output: summary, advice, language, tone.

|Module/File|Key Functions|
|---|---|
|`AI Advice.gs`|`generateAIAdvice()` – GPT generates all weekly advice blocks|
|`generateWeeklyDigest.gs`|GPT writes a full week wrap-up (plain English)|
|`generateWeeklyFeedback.gs`|GPT narrates performance vs expectations|
|`WeeklySavingsAdvice.gs`|GPT suggests savings goals per surplus & risk|
|`WeeklyOutcomeTracker.gs`|GPT compares “plan vs outcome” and reflects|
|`spendingadvice.gs`|GPT personalises spending guidance|
|`generateMemoryInsights.gs`|GPT creates high-level memory-style learning summaries|
|`FeedbackInsights.gs`|GPT highlights what was learned from previous actions|
|`summaryViews.gs` _(partially)_|GPT generates freeform summary panels for dashboard|

**Integration Style:**

- These scripts will pass structured data (forecast, snapshot logs, buffers, UC thresholds) into GPT
    
- GPT returns formatted markdown or HTML summaries
    
- Results logged to Sheets and/or embedded into the dashboard
    

---

## 🧠 **Modules Supported by GPT-4.1 (Reflect, Explain, Summarise Only)**

> Logic stays in Apps Script or Sheets. GPT observes outcome and **comments, advises, or explains.**

|Module/File|GPT Role|
|---|---|
|`RiskRadar.gs`|GPT explains why risk flags were triggered, and mitigation options|
|`plannedExpensesIntegration.gs`|GPT suggests which expenses to defer if surplus is tight|
|`savingsPlanner.gs`|GPT reflects on how savings were allocated|
|`savingsgoals.gs`|GPT offers commentary on progress towards goals|
|`spendingOptimiser.gs`|GPT comments on pacing and UC timing, not logic|
|`runweeklyplanner.gs`|Primary trigger to call GPT functions on a schedule|
|`injectTeeAndDrawdown.txt`|GPT summarises Tee impact + drawdown strategy from results|
|`ucMonitor.gs`|GPT can explain UC threshold impact, not enforce it|
|`heliosApi.gs`|Passes GPT-generated summaries as part of API responses|
|`logHeliosSnapshot.gs`|GPT reads logs and finds patterns or shifts|
|`dailyForecastBundler.gs`|GPT interprets output — "this week will be surplus-light due to X"|
|`Responses.gs`|GPT can replace static blocks with real-time adaptive responses|
|`weeklytrendsheet.gs`|GPT can narrate chart trends from weekly snapshot|

**Integration Style:**

- These modules send **existing results** to GPT
    
- GPT returns **rationale, summaries, or suggestions**
    
- No core logic is modified
    

---

## ❌ **Modules with No GPT Involvement**

> Logic is deterministic, backend, formatting-only, or system-bound.

|Module/File|Reason|
|---|---|
|`forecast.gs`|Core projection logic (UC caps, surplus calc)|
|`bufferMonitor.gs`|Threshold checking (pure logic)|
|`Dashboard.gs`|Layout/visual cell writer|
|`heliosCharts.gs`|Sheet-embedded chart building|
|`fetchRecentStarlingTransactions.gs`|Transaction pull logic|
|`fetchallbalances.gs`|Balance fetch logic|
|`CalculateDailyFinancialMetrics.gs`|Raw balance calculations|
|`recurring.gs`|Recurring expense logic|
|`summaryViews.gs` (chart layout)|Basic formatting only|
|`untitled.gs` (archived)|Placeholder, now deprecated|
|`untitled 3/4.gs`|No useful logic for LLM|
|`weeklytrendsheet.gs`|Feeds GPT, not owned by GPT|

---

## 🧭 Where to Add GPT Calls

**Trigger Points:**

- `runweeklyplanner.gs` – calls:
    
    - `generateAIAdvice()`
        
    - `generateWeeklyFeedback()`
        
    - `generateWeeklyDigest()`
        
    - `generateDrawdownSuggestion()` + pass result to GPT for summary
        
- `heliosApi.gs` – serve GPT-generated summaries via `getAdvice`, `getPlannerDigest`
    

---

## 🔧 GPT Output Targets

|Output|Destinations|
|---|---|
|Advice block|Sheet cell (`AI Advice`), dashboard, API|
|Weekly digest|`Dashboard`, `WeeklyDigest`|
|Feedback|Log sheet + markdown or HTML block|
|Outcome summary|Sheet + `summaryViews`|
|Drawdown comments|`DrawdownPlanner` notes column|
|Risk feedback|Comment cell or alert tag|

---

## 🧠 Prompt Strategy

|Type|GPT Prompt Style|
|---|---|
|Advice|“Based on the forecast below, suggest practical financial advice…”|
|Digest|“Write a weekly financial digest summarising buffer trends, surplus, savings activity…”|
|Feedback|“Compare plan vs actual. Highlight risks, successes, and recommend 1 thing to change.”|
|Drawdown summary|“Summarise the suggested drawdown plan and flag concerns”|
|UC commentary|“Explain UC threshold situation in plain language”|