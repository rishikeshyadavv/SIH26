// ── FloatChat SPA ──
// Talks to the same-origin proxy at /api/query — the browser never sees FLOAT_API_KEY.

const PROXY_URL = "/api/query";
let msgCount = 0;
let busy = false;

// ── Theme & Colors ──
const root = document.documentElement;
const savedTheme = localStorage.getItem("floatchat-theme");
if (savedTheme === "light") root.classList.add("light");

const colors = [
  '#22d3ee', // Cyan
  '#14b8a6', // Teal
  '#f5a524', // Amber
  '#f16565', // Coral
  '#a855f7', // Purple
  '#3b82f6'  // Blue
];
function getColorForIndex(idx, opacity = 1) {
  const c = colors[idx % colors.length];
  if (opacity === 1) return c;
  const r = parseInt(c.slice(1, 3), 16);
  const g = parseInt(c.slice(3, 5), 16);
  const b = parseInt(c.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

document.getElementById("themeToggle").addEventListener("click", () => {
  root.classList.toggle("light");
  const isLight = root.classList.contains("light");
  localStorage.setItem("floatchat-theme", isLight ? "light" : "dark");
  
  // Update Chart.js themes
  document.querySelectorAll(".chart-canvas").forEach(canvas => {
    if (canvas._chartInstance) {
      const chart = canvas._chartInstance;
      const textColor = isLight ? '#0d1b2e' : '#e7edf5';
      const gridColor = isLight ? 'rgba(10,22,40,0.08)' : 'rgba(255,255,255,0.08)';
      chart.options.scales.x.title.color = textColor;
      chart.options.scales.x.ticks.color = textColor;
      chart.options.scales.x.grid.color = gridColor;
      chart.options.scales.y.title.color = textColor;
      chart.options.scales.y.ticks.color = textColor;
      chart.options.scales.y.grid.color = gridColor;
      chart.options.plugins.legend.labels.color = textColor;
      chart.update();
    }
  });
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
const clearChatBtn = document.getElementById("clearChatBtn");

queryInput.addEventListener("keydown", e => { if (e.key === "Enter") submitQuery(); });
sendBtn.addEventListener("click", submitQuery);

if (clearChatBtn) {
  clearChatBtn.parentElement.style.display = "none";
  clearChatBtn.addEventListener("click", () => {
    document.getElementById("thread").innerHTML = "";
    document.getElementById("hero").style.display = "block";
    clearChatBtn.parentElement.style.display = "none";
    msgCount = 0;
  });
}

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
  if (clearChatBtn) clearChatBtn.parentElement.style.display = "flex";
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
      
      if (name === "map") {
        scope.querySelectorAll(".map-view").forEach(mapEl => {
          if (mapEl._leafletMap) {
            setTimeout(() => {
              mapEl._leafletMap.invalidateSize();
            }, 100);
          }
        });
      }
      
      if (name === "chart") {
        scope.querySelectorAll(".chart-canvas").forEach(canvas => {
          if (canvas._chartInstance) {
            setTimeout(() => {
              canvas._chartInstance.resize();
              canvas._chartInstance.update();
            }, 100);
          } else {
            initChartJS(canvas);
          }
        });
      }
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
  const canvasId = "chart_" + Math.random().toString(36).substr(2, 9);

  setTimeout(() => {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
      canvas._chartData = rows;
      canvas._chartMetric = metric;
      if (canvas.closest('.tab-panel').classList.contains('active')) {
        initChartJS(canvas);
      }
    }
  }, 50);

  return `
    <div style="position: relative; height: 320px; width: 100%; margin: 10px 0;">
      <canvas id="${canvasId}" class="chart-canvas"></canvas>
    </div>
  `;
}

function initChartJS(canvas) {
  if (!canvas || !canvas._chartData || canvas._chartInstance) return;

  const rows = canvas._chartData;
  const metric = canvas._chartMetric;
  const isLight = document.documentElement.classList.contains("light");
  const label = metric === "temperature" ? "Temperature (°C)" : "Salinity (PSU)";
  
  const datasets = {};
  rows.forEach(r => {
    if (r.depth == null || r[metric] == null) return;
    const floatId = r.float_id || "Float Data";
    if (!datasets[floatId]) datasets[floatId] = [];
    datasets[floatId].push({ x: +r[metric], y: +r.depth });
  });

  const chartDatasets = Object.keys(datasets).map((floatId, idx) => {
    const data = datasets[floatId].sort((a, b) => a.y - b.y);
    const color = getColorForIndex(idx);
    return {
      label: `Float ${floatId}`,
      data: data,
      borderColor: color,
      backgroundColor: getColorForIndex(idx, 0.15),
      borderWidth: 2,
      pointRadius: 3,
      pointHoverRadius: 6,
      tension: 0.2,
      showLine: true
    };
  });

  const textColor = isLight ? '#0d1b2e' : '#e7edf5';
  const gridColor = isLight ? 'rgba(10,22,40,0.08)' : 'rgba(255,255,255,0.08)';

  canvas._chartInstance = new Chart(canvas, {
    type: 'scatter',
    data: { datasets: chartDatasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      scales: {
        x: {
          type: 'linear',
          position: 'top',
          title: {
            display: true,
            text: label,
            color: textColor,
            font: { family: 'Inter', size: 12, weight: 'bold' }
          },
          ticks: { color: textColor },
          grid: { color: gridColor }
        },
        y: {
          type: 'linear',
          reverse: true,
          title: {
            display: true,
            text: 'Depth (m)',
            color: textColor,
            font: { family: 'Inter', size: 12, weight: 'bold' }
          },
          ticks: { color: textColor },
          grid: { color: gridColor }
        }
      },
      plugins: {
        legend: {
          labels: {
            color: textColor,
            font: { family: 'IBM Plex Mono', size: 11 }
          }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return `${context.dataset.label}: ${context.raw.x} (${label}) at ${context.raw.y}m depth`;
            }
          }
        }
      }
    }
  });
}

function mapHtml(rows) {
  const pts = rows.filter(r => r.lat != null && r.lon != null);
  if (!pts.length) return '<p class="empty-note">No coordinate data in this result.</p>';

  const mapId = "map_" + Math.random().toString(36).substr(2, 9);
  
  // Save points to a temporary DOM attribute for initialization
  setTimeout(() => {
    initLeafletMap(mapId, pts);
  }, 100);

  return `
    <div id="${mapId}" class="map-view" style="height: 320px; width: 100%; border-radius: var(--radius-md); overflow: hidden; background: var(--abyss); border: 1px solid var(--line);"></div>
    <div class="chart-legend" style="margin-top: 10px;"><span><span class="legend-dot" style="background:#14b8a6"></span>${pts.length} coordinates plotted on Leaflet map</span></div>
  `;
}

function initLeafletMap(mapId, pts) {
  const mapEl = document.getElementById(mapId);
  if (!mapEl) return;

  const validPts = pts.filter(p => !isNaN(p.lat) && !isNaN(p.lon));
  if (!validPts.length) return;

  // Calculate center
  const lats = validPts.map(p => +p.lat), lons = validPts.map(p => +p.lon);
  const avgLat = lats.reduce((a, b) => a + b, 0) / lats.length;
  const avgLon = lons.reduce((a, b) => a + b, 0) / lons.length;

  const map = L.map(mapId).setView([avgLat, avgLon], 4);
  
  // Custom dark theme tile layer
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO'
  }).addTo(map);

  validPts.forEach(p => {
    let popup = `<b>Float ID:</b> ${escapeHtml(p.float_id || 'Unknown')}<br><b>Coords:</b> ${p.lat}, ${p.lon}`;
    if (p.temperature !== undefined) popup += `<br><b>Temp:</b> ${p.temperature} °C`;
    if (p.salinity !== undefined) popup += `<br><b>Salinity:</b> ${p.salinity} PSU`;
    if (p.date) popup += `<br><b>Date:</b> ${p.date}`;

    L.marker([p.lat, p.lon]).addTo(map).bindPopup(popup);
  });

  // Track map instance on element to invalidateSize on tab switch
  mapEl._leafletMap = map;
}


