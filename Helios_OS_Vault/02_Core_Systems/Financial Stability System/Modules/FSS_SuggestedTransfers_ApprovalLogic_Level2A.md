```javascript
/**
 * processTransferApprovals()
 * Reads the SuggestedTransfers sheet and logs the status of approved, rejected, or pending suggestions.
 * This is Level 2A: no execution — just tracking approvals.
 */
function processTransferApprovals() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("SuggestedTransfers");
  const data = sheet.getDataRange().getValues();

  // Header: [Week Start, Suggestion, Approved?, Action Taken, Notes]
  const approvedCol = 2;
  const actionCol = 3;

  for (let i = 1; i < data.length; i++) {
    const approval = (data[i][approvedCol] || "").toString().toLowerCase();
    const actionTaken = (data[i][actionCol] || "").toString().toLowerCase();

    if (approval === "yes" && !actionTaken) {
      sheet.getRange(i + 1, actionCol + 1).setValue("✅ Approved – logged");
    } else if (approval === "no" && !actionTaken) {
      sheet.getRange(i + 1, actionCol + 1).setValue("❌ Rejected – no action taken");
    } else if (approval === "later" && !actionTaken) {
      sheet.getRange(i + 1, actionCol + 1).setValue("⏳ Deferred – review later");
    }
  }
}

/**
 * setupSuggestedTransfersSheet()
 * Creates or resets the SuggestedTransfers sheet with headers if it doesn't exist.
 */
function setupSuggestedTransfersSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("SuggestedTransfers");
  if (!sheet) {
    sheet = ss.insertSheet("SuggestedTransfers");
  } else {
    sheet.clearContents();
  }

  const headers = ["Week Start", "Suggestion", "Approved?", "Action Taken", "Notes"];
  sheet.appendRow(headers);
}
```