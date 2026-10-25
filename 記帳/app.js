const EXTRA_KEY = "ledger-extra-v1";
const HIDE_KEY = "ledger-hide-v1";
const FIXED_KEY = "ledger-fixed-v1";
const CATEGORIES = ["飲食", "超市", "日用品", "交通", "購物", "醫療", "娛樂", "家居", "其他", "退款", "其他收入"];

const $ = (id) => document.getElementById(id);
const money = (n) => {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString("en-HK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};
const monthLabel = (key) => {
  const [year, month] = key.split("-");
  return `${year}年${Number(month)}月`;
};
const dayLabel = (date) => {
  const [, month, day] = date.split("-");
  return `${Number(month)}月${Number(day)}日`;
};

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

const state = {
  tab: "overview",
  day: "",
  extra: loadJson(EXTRA_KEY, []),
  hidden: new Set(loadJson(HIDE_KEY, [])),
  fixedOverride: loadJson(FIXED_KEY, null),
  month: "2026-10",
  category: "全部",
  search: "",
};

function fixedRows() {
  if (state.fixedOverride) return state.fixedOverride;
  return { salary: LEDGER.salary, items: LEDGER.fixed.map((row) => ({ ...row })) };
}

function transactions() {
  return LEDGER.transactions
    .filter((row) => !state.hidden.has(row.id))
    .concat(state.extra)
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date) || (a.time || "").localeCompare(b.time || "") || a.id.localeCompare(b.id));
}

function currentNet() {
  const fixed = fixedRows();
  const total = roundMoney(fixed.items.reduce((sum, row) => sum + Number(row.amount), 0));
  return { salary: Number(fixed.salary), fixedTotal: total, net: roundMoney(Number(fixed.salary) - total) };
}

function saveExtra() {
  localStorage.setItem(EXTRA_KEY, JSON.stringify(state.extra));
  localStorage.setItem(HIDE_KEY, JSON.stringify([...state.hidden]));
}

function renderStats(rows, months) {
  const current = months.find((month) => month.key === monthKey(state.day)) || months[months.length - 1];
  const todaySpend = dayTotal(rows, state.day);
  const used = current.pool > 0 ? (current.expense / current.pool) * 100 : 0;
  const today = hkNow().date;
  const [year, month] = current.key.split("-").map(Number);
  const monthDays = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const todayKey = today.slice(0, 7);
  const daysLeft = current.key < todayKey
    ? 0
    : current.key > todayKey
      ? monthDays
      : monthDays - Number(today.slice(8)) + 1;
  const daily = daysLeft > 0 ? roundMoney(current.remainder / daysLeft) : null;
  $("stats").innerHTML = `
    <article class="card">
      <div class="label">已用可支配</div>
      <div class="value spend">${used.toFixed(1)}%</div>
      <div class="hint">${money(current.expense)} / ${money(current.pool)}</div>
    </article>
    <article class="card">
      <div class="label">${monthLabel(current.key)}總支出</div>
      <div class="value spend">${money(current.expense)}</div>
      <div class="hint">月初可動用 ${money(current.pool)}</div>
    </article>
    <article class="card">
      <div class="label">${dayLabel(state.day)}總支出</div>
      <div class="value spend">${money(todaySpend)}</div>
      <div class="hint"><input id="day-picker" type="date" value="${state.day}" /></div>
    </article>
    <article class="card">
      <div class="label">${monthLabel(current.key)}剩餘</div>
      <div class="value ${current.remainder < 0 ? "spend" : "good"}">${money(current.remainder)}</div>
      <div class="hint">現行固定後淨可支配 ${money(currentNet().net)}</div>
    </article>
    <article class="card">
      <div class="label">剩餘每日可花</div>
      <div class="value ${daily != null && daily < 0 ? "spend" : "good"}">${daily == null ? "—" : money(daily)}</div>
      <div class="hint">${daysLeft ? `剩餘 ${money(current.remainder)} ÷ ${daysLeft} 日，含今日` : "呢個月已經過咗"}</div>
    </article>`;
  $("day-picker").addEventListener("change", (event) => {
    state.day = event.target.value;
    render();
  });
}

function hkNow() {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Hong_Kong",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date()).map((part) => [part.type, part.value])
  );
  const hour = parts.hour === "24" ? "00" : parts.hour;
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${hour}:${parts.minute}` };
}

function renderDayChart(target, rows) {
  const { slots, untimed } = daySpendBySlot(rows, state.day);
  const width = 680;
  const height = 220;
  const pad = { l: 52, r: 16, t: 16, b: 32 };
  const max = Math.max(1, ...slots.map((slot) => slot.cumulative));
  const x = (index) => pad.l + (index * (width - pad.l - pad.r)) / (slots.length - 1);
  const y = (value) => pad.t + ((max - value) * (height - pad.t - pad.b)) / max;
  const line = slots.map((slot, index) => `${x(index)},${y(slot.cumulative)}`).join(" ");
  const dots = slots.map((slot, index) => `
    <circle cx="${x(index)}" cy="${y(slot.cumulative)}" r="3.5" fill="#9a3d2f">
      <title>${slot.label} 累積 ${money(slot.cumulative)}</title>
    </circle>
    <text x="${x(index)}" y="${height - 10}" text-anchor="middle" font-size="11" fill="#6d655c">${slot.hour}</text>`).join("");
  const grid = [0, max / 2, max].map((value) => `
    <line x1="${pad.l}" x2="${width - pad.r}" y1="${y(value)}" y2="${y(value)}" stroke="#eadfce" />
    <text x="4" y="${y(value) + 4}" font-size="11" fill="#6d655c">${Math.round(value)}</text>`).join("");
  const missing = untimed
    ? `<p class="hint">呢日有 ${money(untimed)} 冇記錄時間，所以冇畫入線圖。</p>`
    : "";
  target.innerHTML = `
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${dayLabel(state.day)}每兩小時支出">
      ${grid}
      <polyline fill="none" stroke="#9a3d2f" stroke-width="2.5" points="${line}"></polyline>
      ${dots}
    </svg>
    <div class="legend"><span><i class="swatch" style="background:#9a3d2f"></i>${dayLabel(state.day)}累積支出</span></div>
    ${missing}`;
}

function renderMonthSpendChart(target, rows, months) {
  const key = monthKey(state.day);
  const month = months.find((item) => item.key === key) || months[months.length - 1];
  const days = monthSpend(rows, month.key);
  const width = 680;
  const height = 240;
  const pad = { l: 58, r: 12, t: 16, b: 28 };
  const max = roundMoney(month.budget * 1.2);
  const x = (index) => pad.l + (index * (width - pad.l - pad.r)) / Math.max(days.length - 1, 1);
  const y = (value) => pad.t + ((max - value) * (height - pad.t - pad.b)) / (max || 1);
  const today = hkNow().date;
  const shown = days.filter((day) => day.date <= today);
  const line = shown.map((day) => `${x(days.indexOf(day))},${y(day.cumulative)}`).join(" ");
  const dots = shown.map((day) => `
    <circle cx="${x(days.indexOf(day))}" cy="${y(Math.min(day.cumulative, max))}" r="2.4" fill="#1e4d86">
      <title>${dayLabel(day.date)} 當日 ${money(day.amount)}，累積 ${money(day.cumulative)}</title>
    </circle>`).join("");
  const labels = days.map((day, index) => `
    <text x="${x(index)}" y="${height - 8}" text-anchor="middle" font-size="9" fill="#6d655c">${index + 1}</text>`).join("");
  const grid = [0, max / 2, max].map((value) => `
    <line x1="${pad.l}" x2="${width - pad.r}" y1="${y(value)}" y2="${y(value)}" stroke="#eadfce" />
    <text x="4" y="${y(value) + 4}" font-size="11" fill="#6d655c">${Math.round(value)}</text>`).join("");
  const half = roundMoney(month.budget / 2);
  const halfLine = `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(half)}" y2="${y(half)}" stroke="#9a3d2f" stroke-dasharray="6 4" stroke-width="1.5" />`;
  const last = shown[shown.length - 1];
  const total = last ? `累積 ${money(last.cumulative)}，` : "";
  const lastIndex = last ? days.indexOf(last) : 0;
  const labelX = last ? Math.min(x(lastIndex) + 8, width - pad.r - 72) : 0;
  const amountLabel = last
    ? `<text x="${labelX}" y="${y(Math.min(last.cumulative, max)) - 8}" font-size="13" font-weight="650" fill="#1e4d86">${money(last.cumulative)}</text>`
    : "";
  target.innerHTML = `
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${monthLabel(month.key)}累積支出">
      ${grid}
      ${halfLine}
      <polyline fill="none" stroke="#1e4d86" stroke-width="2.5" points="${line}"></polyline>
      ${dots}
      ${amountLabel}
      ${labels}
    </svg>
    <div class="legend">
      <span><i class="swatch" style="background:#1e4d86"></i>${monthLabel(month.key)}${total}縱軸 ${money(max)}（淨可支配 ${money(month.budget)} × 1.2）</span>
      <span><i class="swatch" style="background:#9a3d2f"></i>淨可支配一半 ${money(half)}</span>
    </div>`;
}

function renderChart(months) {
  const history = LEDGER.budgetHistory;
  const width = 680;
  const height = 280;
  const pad = { l: 52, r: 16, t: 16, b: 32 };
  const values = [
    ...history.map((row) => row.amount),
    ...months.map((month) => month.remainder),
  ];
  const min = Math.min(0, ...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (index) => pad.l + (index * (width - pad.l - pad.r)) / Math.max(history.length - 1, 1);
  const y = (value) => pad.t + ((max - value) * (height - pad.t - pad.b)) / span;
  const budgetLine = history.map((row, index) => `${x(index)},${y(row.amount)}`).join(" ");
  const remainPoints = history.map((row, index) => {
    const found = months.find((month) => month.key === row.month);
    return found ? `${x(index)},${y(found.remainder)}` : null;
  });
  const remainLine = remainPoints.filter(Boolean).join(" ");
  const dots = history.map((row, index) => {
    const found = months.find((month) => month.key === row.month);
    const remain = found
      ? `<circle cx="${x(index)}" cy="${y(found.remainder)}" r="4" fill="#0d6b52"></circle>`
      : "";
    return `<circle cx="${x(index)}" cy="${y(row.amount)}" r="3.5" fill="#1e4d86"></circle>${remain}
      <text x="${x(index)}" y="${height - 10}" text-anchor="middle" font-size="12" fill="#6d655c">${Number(row.month.slice(5))}月</text>`;
  }).join("");
  const grid = [0, 2000, 4000, 6000]
    .filter((value) => value >= min - 200 && value <= max + 200)
    .map((value) => `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(value)}" y2="${y(value)}" stroke="#eadfce" />
      <text x="4" y="${y(value) + 4}" font-size="11" fill="#6d655c">${value / 1000}k</text>`)
    .join("");
  $("chart").innerHTML = `
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="每月淨可支配線圖">
      ${grid}
      <polyline fill="none" stroke="#1e4d86" stroke-width="2.5" points="${budgetLine}"></polyline>
      <polyline fill="none" stroke="#0d6b52" stroke-width="2.5" points="${remainLine}"></polyline>
      ${dots}
    </svg>
    <div class="legend">
      <span><i class="swatch" style="background:#1e4d86"></i>預算淨可支配</span>
      <span><i class="swatch" style="background:#0d6b52"></i>月底剩餘</span>
    </div>`;
}

function renderTable(months) {
  $("month-table").innerHTML = `
    <thead><tr>
      <th>月份</th><th class="num">月初可支配</th><th class="num">滾入</th>
      <th class="num">額外收入</th><th class="num">總支出</th><th class="num">月底剩餘</th>
    </tr></thead>
    <tbody>
      ${months.map((month) => `<tr>
        <td>${monthLabel(month.key)}</td>
        <td class="num">${money(month.budget)}</td>
        <td class="num">${month.rolled || month.adjust ? money(roundMoney(month.rolled + (month.adjust || 0))) : "—"}</td>
        <td class="num">${month.income ? money(month.income) : "—"}</td>
        <td class="num">${money(month.expense)}</td>
        <td class="num ${month.remainder < 0 ? "neg" : "pos"}">${money(month.remainder)}</td>
      </tr>`).join("")}
    </tbody>`;
}

function renderReconcile() {
  $("reconcile").innerHTML = `
    <div>6 月最後餘額 -$1,091.19，同舊帳最底嗰個大字一樣。</div>
    <ul>
      <li>7 月逐筆係 $6,029.56，舊總數 $5,879.56 少計 $150。之後補返嘅單再加 $957.25。</li>
      <li>8 月蛋糕喺舊餘額計多一次 $543。呢度只計一次，剩餘 $641.40。</li>
      <li>9 月舊總數無端少咗 $76.50。已補記 $42.50，9 月剩餘 $254.96 滾入 10 月。</li>
      <li>10 月 10 日餘額 $2,553.80。25 日魚蛋燒賣同雞翼之後，餘額 $325.20。</li>
    </ul>`;
}

function renderLedger(rows) {
  const monthRows = rows.filter((row) => {
    if (monthKey(row.date) !== state.month) return false;
    if (state.category !== "全部" && row.category !== state.category) return false;
    if (state.search && !`${row.name} ${row.category}`.includes(state.search.trim())) return false;
    return true;
  });
  const days = [...new Set(monthRows.map((row) => row.date))].reverse();
  $("ledger-list").innerHTML = days.map((date) => {
    const items = monthRows.filter((row) => row.date === date);
    const total = dayTotal(items, date);
    return `<section class="day">
      <div class="day-head">
        <strong>${dayLabel(date)}</strong>
        <span>當日總支出 ${money(total)}　${items.length} 筆</span>
      </div>
      ${items.map((row) => `<div class="row">
        <div>${row.name}</div>
        <span class="cat">${row.category}</span>
        <span class="amt ${row.type === "income" ? "in" : "out"}">${row.type === "income" ? "+" : "−"}${money(row.amount)}</span>
        <button class="icon-btn" type="button" data-remove="${row.id}" aria-label="刪除">刪</button>
      </div>`).join("")}
    </section>`;
  }).join("") || `<p class="sub">呢個月未有符合條件嘅數。</p>`;
  const expense = sumByType(monthRows, "expense");
  $("month-foot").innerHTML = `<span>${monthLabel(state.month)}總支出 <strong>${money(expense)}</strong></span>`;
  $("ledger-list").querySelectorAll("[data-remove]").forEach((button) => {
    button.addEventListener("click", () => removeRow(button.dataset.remove));
  });
}

function renderFixed() {
  const fixed = fixedRows();
  const net = currentNet();
  $("fixed-form").innerHTML = `
    <div class="form">
      <label>每月薪酬 <input name="salary" type="number" step="0.1" value="${fixed.salary}" /></label>
    </div>
    ${fixed.items.map((row, index) => `<div class="row">
      <div>${row.name}<div class="hint" style="color:#6d655c;font-size:12px">${row.note || ""}</div></div>
      <span></span>
      <input data-fixed="${index}" type="number" step="0.1" value="${row.amount}" />
      <span></span>
    </div>`).join("")}
    <div class="month-foot">
      <span>其他固定開支 ${money(net.fixedTotal)}</span>
      <span>卡數（淨支票餘額）${money(net.net)}</span>
      <span>下個月潛在固定支出 <strong>${money(roundMoney(net.fixedTotal + net.net))}</strong></span>
      <button class="primary" type="button" id="save-fixed">儲存</button>
    </div>`;
  $("save-fixed").addEventListener("click", () => {
    const salary = Number($("fixed-form").querySelector("[name=salary]").value);
    const items = fixed.items.map((row, index) => ({
      ...row,
      amount: Number($("fixed-form").querySelector(`[data-fixed="${index}"]`).value),
    }));
    state.fixedOverride = { salary, items };
    localStorage.setItem(FIXED_KEY, JSON.stringify(state.fixedOverride));
    render();
  });
}

function fillFilters(rows) {
  const months = [...new Set(rows.map((row) => monthKey(row.date)))].sort();
  $("month-filter").innerHTML = months.map((key) => `<option value="${key}" ${key === state.month ? "selected" : ""}>${monthLabel(key)}</option>`).join("");
  $("category-filter").innerHTML = ["全部", ...CATEGORIES]
    .map((name) => `<option ${name === state.category ? "selected" : ""}>${name}</option>`)
    .join("");
  $("category").innerHTML = CATEGORIES.map((name) => `<option>${name}</option>`).join("");
}

function removeRow(id) {
  if (id.startsWith("imp-")) state.hidden.add(id);
  else state.extra = state.extra.filter((row) => row.id !== id);
  saveExtra();
  render();
}

function render() {
  const rows = transactions();
  if (!state.day) state.day = latestDate(rows);
  const months = buildMonths(rows, LEDGER.months, currentNet().net || LEDGER.defaultBudget);
  document.querySelectorAll(".tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.tab);
  });
  for (const name of ["overview", "ledger", "fixed"]) {
    $(name).classList.toggle("hidden", state.tab !== name);
  }
  if (state.tab === "overview") {
    renderStats(rows, months);
    renderDayChart($("day-chart-overview"), rows);
    renderMonthSpendChart($("month-chart-overview"), rows, months);
    renderChart(months);
    renderTable(months);
    renderReconcile();
  } else if (state.tab === "ledger") {
    fillFilters(rows);
    renderDayChart($("day-chart"), rows);
    renderMonthSpendChart($("month-chart"), rows, months);
    renderLedger(rows);
  } else {
    renderFixed();
  }
}

$("tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  state.tab = button.dataset.tab;
  render();
});

$("entry-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  state.extra.push({
    id: `new-${Date.now()}`,
    date: data.get("date"),
    time: data.get("time"),
    type: data.get("type"),
    name: String(data.get("name")).trim(),
    amount: roundMoney(data.get("amount")),
    category: data.get("category"),
    source: "manual",
  });
  state.month = monthKey(data.get("date"));
  state.day = data.get("date");
  saveExtra();
  form.reset();
  const now = hkNow();
  form.date.value = state.day;
  form.time.value = now.time;
  render();
});

$("month-filter").addEventListener("change", (event) => {
  state.month = event.target.value;
  render();
});
$("category-filter").addEventListener("change", (event) => {
  state.category = event.target.value;
  render();
});
$("search").addEventListener("input", (event) => {
  state.search = event.target.value;
  render();
});

const opening = hkNow();
document.querySelector("#entry-form [name=date]").value = opening.date;
document.querySelector("#entry-form [name=time]").value = opening.time;
render();
