```javascript
/**
 * generateSpendingAdvice()
 * Parses flagged merchants in `SpendingOptimiser` and produces up to 4 context-rich suggestions.
 * Output is written to `AdviceOutput` sheet with Week Start and up to 4 advice columns.
 */
function generateSpendingAdvice() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const optimiserSheet = ss.getSheetByName('SpendingOptimiser');
  const outputSheetName = 'AdviceOutput';
  let outputSheet = ss.getSheetByName(outputSheetName);
  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    outputSheet.appendRow(['Week Start', 'Advice 1', 'Advice 2', 'Advice 3', 'Advice 4']);
  }

  const data = optimiserSheet.getDataRange().getValues();
  const headers = data[0];
  const rows = data.slice(1);

  const thisWeekStart = Utilities.formatDate(new Date(), ss.getSpreadsheetTimeZone(), "yyyy-MM-dd");
  let advice = [];

  rows.forEach(row => {
    const [merchant, totalSpend, txCount, category] = [
      row[headers.indexOf('Merchant')],
      row[headers.indexOf('TotalSpend')],
      row[headers.indexOf('TransactionCount')],
      row[headers.indexOf('Category')]
    ];

    if (txCount >= 3 && advice.length < 4) {
      advice.push(`You've used ${merchant} ${txCount}× this week (£${totalSpend}). Try capping usage to once/week to free up £${Math.round(totalSpend * 0.6)}.`);
    } else if (totalSpend > 100 && advice.length < 4) {
      advice.push(`${merchant} spend is high (£${totalSpend}). Consider delaying purchases or reviewing subscriptions.`);
    } else if (merchant.toLowerCase().includes('spotify') && advice.length < 4) {
      advice.push(`You have Spotify. Check for overlap with YouTube/Apple subs and cut redundant services.`);
    }
  });

  // Buffer logic: if above buffer goal and no savings
  const bufferSheet = ss.getSheetByName('BufferMonitor');
  const bufferVal = bufferSheet.getRange('D2').getValue(); // % Achieved
  const suggestedSave = ss.getSheetByName('SavingsPlanner').getRange('D2').getValue(); // Suggested Save £

  if (bufferVal > 100 && suggestedSave === 0 && advice.length < 4) {
    advice.push("You've exceeded your buffer goal but haven't saved anything. Consider moving £20–£50 to a savings goal.");
  }

  // Write to AdviceOutput
  outputSheet.appendRow([thisWeekStart, ...advice]);
}
```