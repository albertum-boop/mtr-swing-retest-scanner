const gradeOrder = { "A+": 0, A: 1, B: 2 };
const state = { current: null, history: [], metrics: null, grade: "ALL", query: "" };

const byQualityDate = (a, b) =>
  (gradeOrder[a.grade] ?? 9) - (gradeOrder[b.grade] ?? 9) ||
  String(a.event_date || "").localeCompare(String(b.event_date || "")) ||
  String(a.ticker || "").localeCompare(String(b.ticker || ""));

const gradeClass = (grade) => grade === "A+" ? "grade-aplus" : grade === "A" ? "grade-a" : "grade-b";
const fmtPct = (value, digits = 2) => value == null ? "N/D" : `${value >= 0 ? "+" : ""}${(100 * value).toFixed(digits)}%`;
const fmtNum = (value, digits = 2) => value == null ? "N/D" : Number(value).toFixed(digits);
const fmtDate = (value) => value ? new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${value}T12:00:00`)) : "Pendiente";
const signClass = (value) => value == null ? "" : value >= 0 ? "positive" : "negative";

async function fetchJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } catch (error) {
    console.error(path, error);
    return fallback;
  }
}

function renderSummary() {
  const signals = state.current?.signals || [];
  const stats = state.current?.formation_stats || {};
  const cards = [
    ["Formación activa", state.current?.formation_date || "N/D", `Corte ${state.current?.cutoff || "N/D"}`],
    ["Candidatos swing", stats.swing_top20 ?? "N/D", `${stats.d10 ?? "N/D"} acciones en D10`],
    ["Señales del ciclo", signals.length, `${signals.filter(x => x.grade === "A+").length} de grado A+`],
    ["Referencia histórica", state.history.length, "A+, A y B auditadas"],
  ];
  document.querySelector("#summary").innerHTML = cards.map(([label, value, note]) => `
    <article class="summary-card"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>
  `).join("");
}

function signalCard(signal) {
  return `<article class="signal-card" data-signal="${signal.signal_id}">
    <div class="signal-top"><span class="signal-ticker">${signal.ticker}</span><span class="grade ${gradeClass(signal.grade)}">${signal.grade}</span></div>
    <p class="muted">Señal ${fmtDate(signal.event_date)}</p>
    <div class="signal-metrics">
      <div class="metric"><span>SwingScore</span><strong>${fmtNum(signal.swing_score, 3)}</strong></div>
      <div class="metric"><span>Volumen</span><strong>${fmtPct(signal.event_volume_change)}</strong></div>
      <div class="metric"><span>Pullback</span><strong>${fmtNum(signal.pullback_from_peak_atr)} ATR</strong></div>
    </div>
  </article>`;
}

function renderCurrent() {
  const signals = [...(state.current?.signals || [])].sort(byQualityDate);
  const subtitle = document.querySelector("#current-subtitle");
  subtitle.textContent = state.current ? `Formación ${state.current.formation_date} · sesión ${state.current.session_after_formation} posterior · corte ${state.current.cutoff}` : "Datos no disponibles";
  const empty = document.querySelector("#current-empty");
  const grid = document.querySelector("#current-signals");
  if (!signals.length) {
    empty.hidden = false;
    empty.textContent = "No hay señales confirmadas en el ciclo activo. La selectividad es una característica del método, no un error de actualización.";
    grid.innerHTML = "";
  } else {
    empty.hidden = true;
    grid.innerHTML = signals.map(signalCard).join("");
  }
}

function historyRow(signal) {
  return `<tr data-signal="${signal.signal_id}">
    <td><span class="grade ${gradeClass(signal.grade)}">${signal.grade}</span></td>
    <td><strong>${signal.ticker}</strong></td>
    <td>${signal.event_date || "N/D"}</td>
    <td>${signal.entry_date || "N/D"}</td>
    <td class="${signClass(signal.r5)}">${fmtPct(signal.r5)}</td>
    <td class="${signClass(signal.mfe5)}">${fmtPct(signal.mfe5)}</td>
    <td class="${signClass(signal.mae5)}">${fmtPct(signal.mae5)}</td>
    <td class="${signClass(signal.r10)}">${fmtPct(signal.r10)}</td>
    <td class="${signClass(signal.mfe10)}">${fmtPct(signal.mfe10)}</td>
    <td class="${signClass(signal.mae10)}">${fmtPct(signal.mae10)}</td>
    <td><button class="detail-button">Ver →</button></td>
  </tr>`;
}

function renderHistory() {
  const query = state.query.trim().toUpperCase();
  const filtered = state.history
    .filter(row => state.grade === "ALL" || row.grade === state.grade)
    .filter(row => !query || String(row.ticker).toUpperCase().includes(query))
    .sort(byQualityDate);
  document.querySelector("#history-body").innerHTML = filtered.map(historyRow).join("");
  document.querySelector("#history-count").textContent = `${filtered.length} de ${state.history.length} señales`;
}

function renderProfile() {
  const profiles = state.metrics?.grade_profiles || [];
  document.querySelector("#grade-profile").innerHTML = profiles.map(row => `
    <div class="profile-row">
      <span class="grade ${gradeClass(row.grade)}">${row.grade}</span>
      <div class="profile-metric"><span>R5 medio</span><strong>${fmtPct(row.r5)}</strong></div>
      <div class="profile-metric"><span>MFE5</span><strong>${fmtPct(row.mfe5)}</strong></div>
      <div class="profile-metric"><span>MAE5</span><strong>${fmtPct(row.mae5)}</strong></div>
    </div>`).join("");
}

function detailItem(label, value, cls = "") {
  return `<div class="detail-item"><span>${label}</span><strong class="${cls}">${value}</strong></div>`;
}

function openDrawer(signalId) {
  const signal = [...(state.current?.signals || []), ...state.history].find(row => row.signal_id === signalId);
  if (!signal) return;
  const content = document.querySelector("#drawer-content");
  content.innerHTML = `
    <p class="eyebrow">${signal.method_version || "MTR‑Swing‑Retest‑v1.0"}</p>
    <div class="drawer-title"><h2>${signal.ticker}</h2><span class="grade ${gradeClass(signal.grade)}">${signal.grade}</span></div>
    <p class="muted">Formación ${fmtDate(signal.formation_date)} · señal ${fmtDate(signal.event_date)} · entrada ${fmtDate(signal.entry_date)}</p>
    <section class="detail-section"><h3>Selección</h3><div class="detail-grid">
      ${detailItem("MOM universo", fmtNum(signal.universe_momentum_percentile, 3))}
      ${detailItem("SwingScore", fmtNum(signal.swing_score, 3))}
      ${detailItem("Pendiente SMA200 pct", fmtNum(signal.sma200_slope_percentile_d10, 3))}
      ${detailItem("ADV20", signal.adv20 == null ? "N/D" : `$${(signal.adv20 / 1e6).toFixed(1)} M`)}
    </div></section>
    <section class="detail-section"><h3>Retest</h3><div class="detail-grid">
      ${detailItem("Día del evento", signal.event_day ?? "N/D")}
      ${detailItem("Cierre en rango", fmtNum(signal.close_location, 3))}
      ${detailItem("Pullback desde pico", `${fmtNum(signal.pullback_from_peak_atr)} ATR`)}
      ${detailItem("Volumen vs media20", fmtPct(signal.event_volume_change))}
      ${detailItem("Cuerpo", `${fmtNum(signal.event_body_atr)} ATR`)}
      ${detailItem("Cierre vs nivel", `${fmtNum(signal.close_vs_level_atr)} ATR`)}
    </div></section>
    <section class="detail-section"><h3>Recorrido ejecutable</h3><div class="detail-grid">
      ${detailItem("R5", fmtPct(signal.r5), signClass(signal.r5))}
      ${detailItem("MFE5", fmtPct(signal.mfe5), signClass(signal.mfe5))}
      ${detailItem("MAE5", fmtPct(signal.mae5), signClass(signal.mae5))}
      ${detailItem("R10", fmtPct(signal.r10), signClass(signal.r10))}
      ${detailItem("MFE10", fmtPct(signal.mfe10), signClass(signal.mfe10))}
      ${detailItem("MAE10", fmtPct(signal.mae10), signClass(signal.mae10))}
    </div></section>
    <section class="detail-section"><h3>Entrada</h3><p>${signal.entry_rule || "Apertura ajustada de la sesión posterior al retest."}</p><p class="muted">Precio de referencia: ${signal.entry_open == null ? "pendiente" : `$${fmtNum(signal.entry_open, 4)}`}. R5/R10 son métricas de estudio, no reglas automáticas de salida.</p></section>`;
  document.querySelector("#drawer").classList.add("open");
  document.querySelector("#drawer").setAttribute("aria-hidden", "false");
  document.querySelector("#backdrop").hidden = false;
}

function closeDrawer() {
  document.querySelector("#drawer").classList.remove("open");
  document.querySelector("#drawer").setAttribute("aria-hidden", "true");
  document.querySelector("#backdrop").hidden = true;
}

function bindEvents() {
  document.querySelectorAll(".filter").forEach(button => button.addEventListener("click", () => {
    state.grade = button.dataset.grade;
    document.querySelectorAll(".filter").forEach(x => x.classList.toggle("active", x === button));
    renderHistory();
  }));
  document.querySelector("#ticker-search").addEventListener("input", event => {
    state.query = event.target.value;
    renderHistory();
  });
  document.body.addEventListener("click", event => {
    const row = event.target.closest("[data-signal]");
    if (row) openDrawer(row.dataset.signal);
  });
  document.querySelector("#drawer-close").addEventListener("click", closeDrawer);
  document.querySelector("#backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
}

async function init() {
  const [current, history, metrics] = await Promise.all([
    fetchJson("/data/current.json", null),
    fetchJson("/data/history.json", { signals: [] }),
    fetchJson("/data/metrics.json", { grade_profiles: [] }),
  ]);
  state.current = current;
  state.history = history.signals || [];
  state.metrics = metrics;
  const badge = document.querySelector("#run-badge");
  if (current) badge.textContent = `Datos hasta ${current.cutoff}`;
  else { badge.textContent = "Datos no disponibles"; badge.classList.add("error"); }
  renderSummary(); renderCurrent(); renderHistory(); renderProfile(); bindEvents();
}

init();
