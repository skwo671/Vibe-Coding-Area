import fs from "node:fs";
import vm from "node:vm";

const context = {};
vm.createContext(context);
for (const file of ["ledger-data.js", "ledger-calc.js"]) {
  vm.runInContext(fs.readFileSync(new URL(file, import.meta.url), "utf8"), context);
}

const { LEDGER, buildMonths, sumByType, dayTotal } = context;
const months = buildMonths(LEDGER.transactions, LEDGER.months, LEDGER.defaultBudget);
const byKey = Object.fromEntries(months.map((month) => [month.key, month]));

function assertClose(actual, expected, label) {
  if (Math.abs(actual - expected) > 0.001) {
    throw new Error(`${label}: ${actual} !== ${expected}`);
  }
}

assertClose(byKey["2026-06"].expense, 4201.19, "June spend");
assertClose(byKey["2026-06"].remainder, -1091.19, "June remainder");
assertClose(byKey["2026-07"].income, 1500, "July income");
assertClose(byKey["2026-08"].expense, 3773.8, "August spend");
assertClose(byKey["2026-08"].remainder, 641.4, "August remainder");
assertClose(byKey["2026-09"].remainder, 254.96, "September remainder");
assertClose(byKey["2026-10"].pool, 4858.96, "October opening");
assertClose(byKey["2026-10"].expense, 2598.86, "October spend");
assertClose(byKey["2026-10"].remainder, 2260.1, "October remainder");
assertClose(dayTotal(LEDGER.transactions, "2026-10-10"), 339.97, "10 Oct spend");
assertClose(sumByType(LEDGER.transactions, "expense") > 15000 ? 1 : 0, 1, "has history");

const fixed = LEDGER.fixed.reduce((sum, row) => sum + row.amount, 0);
if (Math.abs(LEDGER.salary - fixed - 4603.6) > 0.05) {
  throw new Error(`fixed net ${LEDGER.salary - fixed}`);
}

console.log("ledger checks ok");
console.log(
  months
    .map((month) => `${month.key} pool ${month.pool} spend ${month.expense} left ${month.remainder}`)
    .join("\n")
);
