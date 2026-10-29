import fs from "node:fs";
import vm from "node:vm";

const context = {};
vm.createContext(context);
for (const file of ["ledger-data.js", "ledger-calc.js"]) {
  vm.runInContext(fs.readFileSync(new URL(file, import.meta.url), "utf8"), context);
}

const { LEDGER, buildMonths, sumByType, dayTotal, daySpendBySlot, monthSpend, roundMoney } = context;
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
assertClose(byKey["2026-10"].expense, 4878.25, "October spend");
assertClose(byKey["2026-10"].remainder, -19.29, "October remainder");
assertClose(byKey["2026-11"].rolled, -19.29, "November carries the deficit");
assertClose(byKey["2026-11"].pool, 4584.71, "November opening");
assertClose(dayTotal(LEDGER.transactions, "2026-10-10"), 339.97, "10 Oct spend");
const oct11 = daySpendBySlot(LEDGER.transactions, "2026-10-11");
assertClose(oct11.slots[9].amount, 293.7, "牛角 in 18:00 slot");
assertClose(oct11.slots[8].cumulative, 0, "cumulative before 18:00");
assertClose(oct11.slots[9].cumulative, 293.7, "cumulative at 18:00");
assertClose(oct11.slots[11].cumulative, 293.7, "cumulative holds after 18:00");
assertClose(oct11.untimed, 0, "11 Oct has times");
const octoberDays = monthSpend(LEDGER.transactions, "2026-10");
assertClose(octoberDays.length, 31, "October day count");
assertClose(octoberDays[0].date === "2026-10-01" ? 1 : 0, 1, "month starts on the 1st");
assertClose(octoberDays[30].cumulative, byKey["2026-10"].expense, "month cumulative equals spend");
assertClose(roundMoney(byKey["2026-10"].budget * 1.2), 5524.8, "October axis");
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
