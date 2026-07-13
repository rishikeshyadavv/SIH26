// ── FloatChat SPA ──
// Talks to the same-origin proxy at /api/query — the browser never sees FLOAT_API_KEY.

const PROXY_URL = "/api/query";
let msgCount = 0;
let busy = false;

// ── Theme ──
const root = document.documentElement;
const savedTheme = localStorage.getItem("floatchat-theme");
if (savedTheme === "light") root.classList.add("light");

document.getElementById("themeToggle").addEventListener("click", () => {
  root.classList.toggle("light");
  localStorage.setItem("floatchat-theme", root.classList.contains("light") ? "light" : "dark");
});

// ── Connection status ──
async function checkStatus() {
  const dot = document.querySelector("#statStatus .dot");
  const text = document.getElementById("statText");
  try {
    const res = await fetch("/api/health", { method: "GET" });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      text.textContent = data.floats && data.rows
        ? `${data.floats} floats · ${data.rows.toLocaleString()} readings`
        : "backend online";
      dot.classList.remove("err");
    } else {
      throw new Error("unhealthy");
    }
  } catch {
    text.textContent = "backend unreachable";
    dot.classList.add("err");
  }
}
checkStatus();

// ── Chips ──
document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.getElementById("queryInput").value = chip.dataset.q;
    submitQuery();
  });
});

// ── Input ──
const queryInput = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
queryInput.addEventListener("keydown", e => { if (e.key === "Enter") submitQuery(); });
sendBtn.addEventListener("click", submitQuery);

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

async function submitQuery() {
  if (busy) return;
  const question = queryInput.value.trim();
  if (!question) return;
  queryInput.value = "";
  busy = true;
  sendBtn.disabled = true;

  document.getElementById("hero").style.display = "none";
  const thread = document.getElementById("thread");

  const userMsg = el("div", "msg user");
  userMsg.innerHTML = `<div class="avatar">YOU</div><div class="bubble">${escapeHtml(question)}</div>`;
  thread.appendChild(userMsg);

  const asstMsg = el("div", "msg assistant");
  const targetId = "sk_" + msgCount++;
  asstMsg.innerHTML = `<div class="avatar">FC</div><div class="bubble" id="${targetId}">
    <div class="skeleton"><div class="bar" style="width:38%"></div><div class="bar" style="width:88%"></div><div class="bar" style="width:64%"></div></div>
  </div>`;
  thread.appendChild(asstMsg);
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });

  try {
    const res = await fetch(PROXY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    renderResult(targetId, data, res.status);
  } catch (err) {
    renderResult(targetId, { success: false, error: "Could not reach the backend. " + err.message, sql: "" }, 0);
  } finally {
    busy = false;
    sendBtn.disabled = false;
  }
}

function renderResult(targetId, res, httpStatus) {
  const target = document.getElementById(targetId);
  if (!res.success) {
    const blocked = httpStatus === 429 || /rate limit/i.test(res.error || "");
    target.innerHTML = `
      <span class="status-tag ${blocked ? "blocked" : "err"}">${blocked ? "Rate limited" : "Query failed"}</span>
      <div class="card" style="color:${blocked ? "var(--amber)" : "var(--coral)"}; font-size:13.5px;">${escapeHtml(res.error || "Unknown error")}</div>
      ${res.sql ? sqlToggleHtml(res.sql) : ""}
    `;
    wireSqlToggle(target);
    return;
  }

  const rows = res.data || [];
  target.innerHTML = `
    <span class="status-tag ok">Query executed</span>
    ${sqlToggleHtml(res.sql || "")}
    <div class="card">
      <div class="tabs">
        <div class="tab active" data-tab="data">Data</div>
        <div class="tab" data-tab="chart">Chart</div>
        <div class="tab" data-tab="map">Map</div>
      </div>
      <div class="tab-panel active" data-panel="data">${dataTableHtml(rows)}</div>
      <div class="tab-panel" data-panel="chart">${chartHtml(rows)}</div>
      <div class="tab-panel" data-panel="map">${mapHtml(rows)}</div>
    </div>
  `;
  wireSqlToggle(target);
  wireTabs(target);
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function sqlToggleHtml(sql) {
  if (!sql) return "";
  return `<div class="card">
    <div class="sql-toggle" onclick="this.classList.toggle('open'); this.nextElementSibling.classList.toggle('open');">
      <span class="arrow">▶</span> View generated SQL
    </div>
    <div class="sql-block">${escapeHtml(sql)}</div>
  </div>`;
}
function wireSqlToggle() {}

function wireTabs(scope) {
  scope.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      scope.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t === tab));
      scope.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.dataset.panel === name));
    });
  });
}

function dataTableHtml(rows) {
  if (!rows.length) return '<p class="empty-note">No records matched this query.</p>';
  const cols = Object.keys(rows[0]);
  const shown = rows.slice(0, 50);
  return `
    <p style="font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--text-faint); margin-bottom:10px;">Showing ${shown.length} of ${rows.length} rows</p>
    <div class="table-scroll">
    <table class="data-table">
      <thead><tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>
      <tbody>${shown.map(r => `<tr>${cols.map(c => `<td>${escapeHtml(r[c])}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>
    </div>
  `;
}

function chartHtml(rows) {
  const hasDepth = rows.length && "depth" in rows[0];
  const hasTemp = rows.length && "temperature" in rows[0];
  const hasSal = rows.length && "salinity" in rows[0];
  if (!hasDepth || (!hasTemp && !hasSal)) {
    return '<p class="empty-note">No depth/temperature/salinity data to chart for this query.</p>';
  }

  const metric = hasTemp ? "temperature" : "salinity";
  const label = hasTemp ? "Temperature (°C)" : "Salinity (PSU)";
  const color = hasTemp ? "#22d3ee" : "#14b8a6";

  const pts = rows
    .filter(r => r.depth != null && r[metric] != null)
    .map(r => ({ depth: +r.depth, val: +r[metric] }))
    .sort((a, b) => a.depth - b.depth);
  if (!pts.length) return '<p class="empty-note">No plottable points.</p>';

  const W = 640, H = 240, padL = 46, padR = 20, padT = 16, padB = 30;
  const minV = Math.min(...pts.map(p => p.val)), maxV = Math.max(...pts.map(p => p.val));
  const minD = Math.min(...pts.map(p => p.depth)), maxD = Math.max(...pts.map(p => p.depth));
  const x = v => padL + (v - minV) / ((maxV - minV) || 1) * (W - padL - padR);
  const y = d => padT + (d - minD) / ((maxD - minD) || 1) * (H - padT - padB);

  const pathD = pts.map((p, i) => (i === 0 ? "M" : "L") + x(p.val).toFixed(1) + "," + y(p.depth).toFixed(1)).join(" ");

  return `
    <svg class="depth-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="var(--line)" stroke-width="1"/>
      <line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="var(--line)" stroke-width="1"/>
      <text x="8" y="${padT + 8}" fill="#4d617e" font-size="9" font-family="IBM Plex Mono">${minD.toFixed(0)}m</text>
      <text x="8" y="${H - padB}" fill="#4d617e" font-size="9" font-family="IBM Plex Mono">${maxD.toFixed(0)}m</text>
      <path d="${pathD}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      ${pts.map(p => `<circle cx="${x(p.val).toFixed(1)}" cy="${y(p.depth).toFixed(1)}" r="2.5" fill="var(--deep)" stroke="${color}" stroke-width="1.5"/>`).join("")}
    </svg>
    <div class="chart-legend"><span><span class="legend-dot" style="background:${color}"></span>${label} vs depth (depth increases downward)</span></div>
  `;
}

function mapHtml(rows) {
  const pts = rows.filter(r => r.lat != null && r.lon != null);
  if (!pts.length) return '<p class="empty-note">No coordinate data in this result.</p>';

  const lats = pts.map(p => +p.lat), lons = pts.map(p => +p.lon);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats), minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const W = 640, H = 260, pad = 24;
  const x = lon => pad + ((lon - minLon) / ((maxLon - minLon) || 1)) * (W - 2 * pad);
  const y = lat => pad + (1 - (lat - minLat) / ((maxLat - minLat) || 1)) * (H - 2 * pad);

  const uniq = {};
  pts.forEach(p => { uniq[p.lat + "," + p.lon] = p; });
  const uniquePts = Object.values(uniq).slice(0, 100);

  return `
    <svg class="depth-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="background:var(--surface); border-radius:10px;">
      ${uniquePts.map(p => `<circle cx="${x(+p.lon).toFixed(1)}" cy="${y(+p.lat).toFixed(1)}" r="4" fill="#14b8a6" fill-opacity="0.85" stroke="#22d3ee" stroke-width="1"><title>${escapeHtml(p.float_id || "")} ${p.lat},${p.lon}</title></circle>`).join("")}
    </svg>
    <div class="chart-legend"><span><span class="legend-dot" style="background:#14b8a6"></span>${uniquePts.length} unique float location(s) · simplified projection</span></div>
  `;
}
