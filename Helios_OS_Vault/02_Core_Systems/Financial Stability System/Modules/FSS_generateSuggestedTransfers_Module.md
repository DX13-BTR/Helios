```javascript
/**
 * generateSuggestedTransfers()
 * Proposes fund movements (e.g. top-ups to savings) based on buffer %, Tee coverage, and forecast.
 * Outputs to 'AdviceOutput' column G or separate 'SuggestedTransfers' sheet.
 */
function generateSuggestedTransfers() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const adviceSheet = ss.getSheetByName('AdviceOutput');
  const bufferSheet = ss.getSheetByName('BufferMonitor');
  const forecastSheet = ss.getSheetByName('Forecast_90DayDaily');
  const weekStart = Utilities.formatDate(new Date(), ss.getSpreadsheetTimeZone(), "yyyy-MM-dd");

  const bufferPercent = bufferSheet.getRange('D2').getValue(); // Assume this holds % Achieved
  const teePaid = checkTeePaidThisMonth(); // Custom logic to determine if Tee payment is already covered
  const shortfallFlagged = checkShortfallFlag(); // Optional: Check if forecast shows flagged shortfall

  let suggestion = '';

  if (!teePaid) {
    suggestion = "Hold transfers – Tee payment not yet covered.";
  } else if (shortfallFlagged) {
    suggestion = "Hold transfers – shortfall projected in next 14 days.";
  } else if (bufferPercent > 130) {
    suggestion = "Buffer healthy (130%+). Recommend transferring £25–£50 to a savings goal.";
  } else if (bufferPercent > 100) {
    suggestion = "Buffer met. Consider a £15–£30 top-up to emergency fund or specific space.";
  } else {
    suggestion = "No transfer suggested – buffer not yet at target.";
  }

  // Output to AdviceOutput column G (Assuming A = Week Start)
  const adviceData = adviceSheet.getDataRange().getValues();
  const rowIndex = adviceData.findIndex(row => {
    const cellDate = Utilities.formatDate(new Date(row[0]), ss.getSpreadsheetTimeZone(), "yyyy-MM-dd");
    return cellDate === weekStart;
  });

  if (rowIndex >= 0) {
    adviceSheet.getRange(rowIndex + 1, 7).setValue(suggestion); // Column G
  } else {
    // Append new row if not found
    adviceSheet.appendRow([weekStart, '', '', '', '', '', suggestion]);
  }
}

/**
 * checkTeePaidThisMonth()
 * Simple placeholder to check if the fixed £650 Tee payment has been accounted for this month.
 * Adjust to match your own logic.
 */
function checkTeePaidThisMonth() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const forecastSheet = ss.getSheetByName('Forecast_90DayDaily');
  const data = forecastSheet.getDataRange().getValues();
  const currentMonth = new Date().getMonth();

  return data.some(row => {
    const date = new Date(row[0]);
    return (
      date.getMonth() === currentMonth &&
      row[1] === "Tee Payment" &&
      parseFloat(row[2]) === -650
    );
  });
}

/**
 * checkShortfallFlag()
 * Placeholder logic — returns true if any "Shortfall" risk flag exists in the next 14 days.
 */
function checkShortfallFlag() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const forecastSheet = ss.getSheetByName('Forecast_90DayDaily');
  const today = new Date();
  const cutoff = new Date(today);
  cutoff.setDate(today.getDate() + 14);

  const data = forecastSheet.getDataRange().getValues();
  const dateColIndex = 0;
  const flagColIndex = 5; // Example: adjust if your sheet has risk flags in another column

  return data.some(row => {
    const date = new Date(row[dateColIndex]);
    return date >= today && date <= cutoff && row[flagColIndex] === "Shortfall";
  });
}
```