function roundMoney(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

function monthKey(date) {
  return String(date).slice(0, 7);
}

function buildMonths(transactions, settings, defaultBudget) {
  const keys = new Set(Object.keys(settings));
  for (const row of transactions) keys.add(monthKey(row.date));
  const sorted = [...keys].sort();
  const months = [];
  let prevRemainder = 0;
  for (const key of sorted) {
    const cfg = settings[key] || { budget: defaultBudget, roll: true, note: "" };
    const rows = transactions.filter((row) => monthKey(row.date) === key);
    const expense = roundMoney(
      rows.filter((row) => row.type === "expense").reduce((sum, row) => sum + row.amount, 0)
    );
    const income = roundMoney(
      rows.filter((row) => row.type === "income").reduce((sum, row) => sum + row.amount, 0)
    );
    const rolled = cfg.roll && prevRemainder > 0 ? roundMoney(prevRemainder) : 0;
    const pool = roundMoney(Number(cfg.budget) + rolled);
    const remainder = roundMoney(pool + income - expense);
    months.push({
      key,
      budget: roundMoney(Number(cfg.budget)),
      rolled,
      pool,
      income,
      expense,
      remainder,
      note: cfg.note || "",
    });
    prevRemainder = remainder;
  }
  return months;
}

function sumByType(transactions, type) {
  return roundMoney(
    transactions.filter((row) => row.type === type).reduce((sum, row) => sum + row.amount, 0)
  );
}

function dayTotal(transactions, date) {
  return roundMoney(
    transactions
      .filter((row) => row.date === date && row.type === "expense")
      .reduce((sum, row) => sum + row.amount, 0)
  );
}

function latestDate(transactions) {
  return transactions.reduce((latest, row) => (row.date > latest ? row.date : latest), "");
}
