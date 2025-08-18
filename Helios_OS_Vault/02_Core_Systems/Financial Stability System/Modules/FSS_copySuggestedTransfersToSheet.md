```javascript
/**
 * copySuggestedTransfersToSheet()
 * Copies the latest Suggested Transfer from AdviceOutput column G to SuggestedTransfers sheet.
 * Ensures no duplicates and preserves Week Start alignment.
 */
function copySuggestedTransfersToSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const adviceSheet = ss.getSheetByName("AdviceOutput");
  const transferSheet = ss.getSheetByName("SuggestedTransfers");
  const dashboardSheet = ss.getSheetByName("HeliosDashboard");

  // Get active Week Start from dashboard (B3)
  const weekStartRaw = dashboardSheet.getRange("B3").getValue();
  if (!weekStartRaw || isNaN(new Date(weekStartRaw))) {
    throw new Error("HeliosDashboard!B3 is missing or invalid.");
  }
  const weekStart = new Date(weekStartRaw);

  // Format for comparison
  const formattedWeekStart = Utilities.formatDate(weekStart, ss.getSpreadsheetTimeZone(), "yyyy-MM-dd");

  // Look up matching row in AdviceOutput
  const adviceData = adviceSheet.getDataRange().getValues();
  const matchedRow = adviceData.find(row => {
    const rowDate = new Date(row[0]);
    return rowDate.getFullYear() === weekStart.getFullYear() &&
           rowDate.getMonth() === weekStart.getMonth() &&
           rowDate.getDate() === weekStart.getDate();
  });

  if (!matchedRow || !matchedRow[6]) {
    Logger.log("⚠️ No transfer suggestion found in AdviceOutput for current week.");
    return;
  }

  const suggestion = matchedRow[6];

  // Check for duplicates in SuggestedTransfers
  const transferData = transferSheet.getDataRange().getValues();
  const alreadyExists = transferData.some(row => {
    const rowDate = new Date(row[0]);
    return rowDate.getFullYear() === weekStart.getFullYear() &&
           rowDate.getMonth() === weekStart.getMonth() &&
           rowDate.getDate() === weekStart.getDate();
  });

  if (alreadyExists) {
    Logger.log("✅ Suggested transfer for this week already exists. Skipping.");
    return;
  }

  // Append to SuggestedTransfers
  transferSheet.appendRow([weekStart, suggestion, '', '', '']);
  Logger.log("✅ Suggested transfer copied to sheet.");
}
```