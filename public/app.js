const gradeOrder = { "A+": 0, A: 1, B: 2 };
const state = {
  current: null,
  history: [],
  metrics: null,
  grade: "ALL",
  query: "",
  candidateStatus: "ALL",
  candidateQuery: "",
};

const statusMeta = {
  waiting: ["Esperando sesiones", "status-waiting"],
  waiting_expansion: ["Esperando expansión", "status-waiting"],
  expanded_waiting_retest: ["Esperando retest", "status-ready"],
  signal: ["Señal", "status-signal"],
  rejected_first_contact: ["Rechazado", "status-rejected"],
  rejected_weekly_grade: ["B semanal descartada", "status-rejected"],
  expired: ["Expirado", "status-expired"],
  missing_prices: ["Sin precios", "status-error"],
  missing_formation: ["Sin formación", "status-error"],
  invalid_formation: ["Formación inválida", "status-error"],
};

const phaseMeta = {
  before_retest_window: "Ventana de retest todavía no abierta",
  retest_window_open: "Ventana de retest abierta",
  retest_window_closed: "Ventana de retest cerrada",
};

const checkLabels = {
  contact: "Contacto con la banda",
  hold: "Cierre sobre el nivel L",
  strong_close: "Cierre en el 70% superior",
  not_extended: "Extensión máxima de 0,75 ATR",
  volume_contraction: "Volumen inferior al 80%",
};

const byQualityDate = (a, b) =>
  (gradeOrder[a.grade] ?? 9) - (gradeOrder[b.grade] ?? 9) ||
  String(a.event_date || "").localeCompare(String(b.event_date || "")) ||
  String(a.ticker || "").localeCompare(String(b.ticker || ""));

const gradeClass = (grade) => grade === "A+" ? "grade-aplus" : grade === "A" ? "grade-a" : "grade-b";
const fmtPct = (value, digits = 2) => value == null ? "N/D" : `${value >= 0 ? "+" : ""}${(100 * value).toFixed(digits)}%`;
const fmtNum = (value, digits = 2) => value == null ? "N/D" : Number(value).toFixed(digits);
const fmtPrice = (value) => value == null ? "N/D" : `$${Number(value).toFixed(Math.abs(value) < 10 ? 3 : 2)}`;
const fmtDate = (value) => value ? new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${value}T12:00:00`)) : "Pendiente";
const signClass = (value) => value == null ? "" : value >= 0 ? "positive" : "negative";
const sourceLabel = (row) => row?.is_confluence || row?.source === "monthly+weekly"
  ? "Mensual + semanal"
  : row?.source === "weekly" ? "Semanal" : "Mensual";
const sourceClass = (row) => row?.is_confluence || row?.source === "monthly+weekly"
  ? "source-confluence"
  : row?.source === "weekly" ? "source-weekly" : "source-monthly";
const sourceBadge = (row) => `<span class="source-badge ${sourceClass(row)}">${sourceLabel(row)}</span>`;

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

function cyclePhaseLabel() {
  return phaseMeta[state.current?.cycle_phase] || "Estado de ventana no disponible";
}

function renderSummary() {
  const signals = state.current?.signals || [];
  const counts = state.current?.source_counts || {};
  const weeklyDates = state.current?.weekly_formation_dates || [];
  const actionable = signals.filter(signal => signal.event_date === state.current?.cutoff);
  const cards = [
    ["Formaciones activas", 1 + weeklyDates.length, `Mensual ${state.current?.monthly_formation_date || "N/D"}${weeklyDates.length ? ` · semanal ${weeklyDates.join(", ")}` : ""}`],
    ["Candidatos swing", (counts.monthly_candidates ?? 0) + (counts.weekly_crossing_candidates ?? 0), `${counts.monthly_candidates ?? 0} mensuales · ${counts.weekly_crossing_candidates ?? 0} cruces semanales`],
    ["Señales confirmadas hoy", actionable.length, actionable.length ? "Entrada en la próxima apertura" : "Ninguna entrada nueva"],
    ["Histórico operativo", state.history.length, `${state.metrics?.signals ?? 232} señales de referencia + posteriores`],
  ];
  document.querySelector("#summary").innerHTML = cards.map(([label, value, note]) => `
    <article class="summary-card"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>
  `).join("");
}

function statusPill(candidate) {
  const [label, cls] = statusMeta[candidate.status] || [candidate.status || "N/D", "status-error"];
  const suffix = candidate.status === "signal" && candidate.grade ? ` ${candidate.grade}` : "";
  return `<span class="status-pill ${cls}">${label}${suffix}</span>`;
}

function candidateGroup(candidate) {
  if (["waiting", "waiting_expansion", "expanded_waiting_retest"].includes(candidate.status)) return "POSSIBLE";
  if (candidate.status === "signal") return "SIGNAL";
  if (["rejected_first_contact", "rejected_weekly_grade"].includes(candidate.status)) return "REJECTED";
  if (candidate.status === "expired") return "EXPIRED";
  return "OTHER";
}

function candidateRow(candidate) {
  const latest = candidate.latest_session;
  const lastSession = latest ? `D${latest.day} · ${fmtDate(latest.date)}` : "Sin sesión";
  const volume = latest ? fmtPct(latest.volume_ratio - 1) : "N/D";
  return `<tr data-candidate="${candidate.candidate_id}">
    <td>${candidate.candidate_rank ?? "—"}</td>
    <td><strong>${candidate.ticker}</strong></td>
    <td>${sourceBadge(candidate)}</td>
    <td>${statusPill(candidate)}</td>
    <td>${fmtNum(candidate.swing_score, 3)}</td>
    <td>${fmtPrice(candidate.formation_close)}</td>
    <td>≥ ${fmtPrice(candidate.expansion_threshold)}</td>
    <td>${fmtPrice(candidate.contact_band_low)}–${fmtPrice(candidate.contact_band_high)}</td>
    <td>${lastSession}</td>
    <td class="${latest && latest.volume_ratio < 0.8 ? "positive" : ""}">${volume}</td>
    <td class="next-step">${candidate.next_step || "N/D"}</td>
    <td><button class="detail-button">Ver →</button></td>
  </tr>`;
}

function renderCandidates() {
  const candidates = state.current?.candidates || [];
  const query = state.candidateQuery.trim().toUpperCase();
  const filtered = candidates
    .filter(candidate => state.candidateStatus === "ALL" || candidateGroup(candidate) === state.candidateStatus)
    .filter(candidate => !query || String(candidate.ticker).toUpperCase().includes(query))
    .sort((a, b) => String(a.source).localeCompare(String(b.source)) ||
      String(b.formation_date).localeCompare(String(a.formation_date)) ||
      (a.candidate_rank ?? 9999) - (b.candidate_rank ?? 9999));
  const weeklyDates = state.current?.weekly_formation_dates || [];
  document.querySelector("#candidate-subtitle").textContent = state.current
    ? `Mensual ${state.current.monthly_formation_date} · semanal ${weeklyDates.join(", ") || "sin ventana activa"} · corte ${state.current.cutoff}`
    : "Datos no disponibles";
  document.querySelector("#candidate-body").innerHTML = filtered.length
    ? filtered.map(candidateRow).join("")
    : `<tr><td colspan="12" class="empty-table">No hay candidatos en este filtro.</td></tr>`;
  document.querySelector("#candidate-count").textContent = `${filtered.length} de ${candidates.length} candidatos`;
}

function signalCard(signal) {
  const actionable = signal.event_date === state.current?.cutoff;
  const timing = actionable
    ? "Confirmada hoy · entrada en próxima apertura"
    : `Señal ${fmtDate(signal.event_date)} · entrada ${fmtDate(signal.entry_date)}`;
  return `<article class="signal-card ${actionable ? "actionable" : ""}" data-signal="${signal.signal_id}">
    <div class="signal-top"><span class="signal-ticker">${signal.ticker}</span><span>${sourceBadge(signal)} <span class="grade ${gradeClass(signal.grade)}">${signal.grade}</span></span></div>
    <p class="muted">${timing}</p>
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
  subtitle.textContent = state.current
    ? `Unión de la formación mensual y los cruces semanales A/A+ · corte ${state.current.cutoff}`
    : "Datos no disponibles";
  const empty = document.querySelector("#current-empty");
  const grid = document.querySelector("#current-signals");
  if (!signals.length) {
    empty.hidden = false;
    empty.textContent = "No hubo señales confirmadas en este ciclo. La selectividad es una característica del método.";
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
    <td>${sourceBadge(signal)}</td>
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

function openSignalDrawer(signalId) {
  const signal = [...(state.current?.signals || []), ...state.history].find(row => row.signal_id === signalId);
  if (!signal) return;
  const content = document.querySelector("#drawer-content");
  content.innerHTML = `
    <p class="eyebrow">${signal.method_version || "MTR‑Multitemporal‑v1.1"}</p>
    <div class="drawer-title"><h2>${signal.ticker}</h2><span class="grade ${gradeClass(signal.grade)}">${signal.grade}</span></div>
    <p>${sourceBadge(signal)}</p>
    <p class="muted">Formación ${Object.entries(signal.formation_dates || { principal: signal.formation_date }).map(([source, date]) => `${source === "monthly" ? "mensual" : source === "weekly" ? "semanal" : source} ${fmtDate(date)}`).join(" · ")} · señal ${fmtDate(signal.event_date)} · entrada ${fmtDate(signal.entry_date)}</p>
    ${signal.is_confluence ? `<section class="detail-section"><h3>Confluencia</h3><p>El mismo retest fue detectado por ambos marcos. Grado mensual ${signal.monthly_grade}; grado semanal ${signal.weekly_grade}. El grado maestro es el mejor grado observado, sin mejora automática por coincidencia.</p></section>` : ""}
    <section class="detail-section"><h3>Selección</h3><div class="detail-grid">
      ${detailItem("MOM universo", fmtNum(signal.universe_momentum_percentile, 3))}
      ${detailItem("SwingScore", fmtNum(signal.swing_score, 3))}
      ${detailItem("Pendiente SMA200 pct", fmtNum(signal.sma200_slope_percentile_d10, 3))}
      ${detailItem("ADV20", signal.adv20 == null ? "N/D" : `$${(signal.adv20 / 1e6).toFixed(1)} M`)}
    </div></section>
    ${signal.weekly_grade ? `<section class="detail-section"><h3>Calidad semanal</h3><div class="detail-grid">
      ${detailItem("Grado semanal", signal.weekly_grade)}
      ${detailItem("Puntos de calidad", signal.weekly_quality_points ?? signal.source_details?.weekly?.weekly_quality_points ?? "N/D")}
      ${detailItem("Volumen formación 5/20", fmtPct(signal.formation_relative_volume5_20 ?? signal.source_details?.weekly?.formation_relative_volume5_20))}
      ${detailItem("Confirmación volumen", (signal.weekly_formation_volume_confirmation ?? signal.source_details?.weekly?.weekly_formation_volume_confirmation) ? "Sí" : "No")}
    </div></section>` : ""}
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
    <section class="detail-section"><h3>Entrada</h3><p>${signal.entry_rule || "Apertura ajustada de la sesión posterior al retest."}</p><p class="muted">Precio de referencia: ${signal.entry_open == null ? "pendiente" : fmtPrice(signal.entry_open)}. R5/R10 son métricas de estudio, no reglas automáticas de salida.</p></section>`;
  showDrawer();
}

function checksBlock(candidate) {
  if (!candidate.checks) return "";
  return `<section class="detail-section"><h3>Comprobación del primer contacto</h3><div class="check-list">
    ${Object.entries(checkLabels).map(([key, label]) => {
      const passed = Boolean(candidate.checks[key]);
      return `<div class="check-row"><span>${label}</span><strong class="${passed ? "check-pass" : "check-fail"}">${passed ? "Cumple" : "Falla"}</strong></div>`;
    }).join("")}
  </div></section>`;
}

function openCandidateDrawer(candidateId) {
  const candidate = (state.current?.candidates || []).find(row => row.candidate_id === candidateId);
  if (!candidate) return;
  const latest = candidate.latest_session;
  const content = document.querySelector("#drawer-content");
  content.innerHTML = `
    <p class="eyebrow">Candidato #${candidate.candidate_rank ?? "—"} · ${sourceLabel(candidate)}</p>
    <div class="drawer-title"><h2>${candidate.ticker}</h2>${statusPill(candidate)}</div>
    <p class="muted">Formación ${fmtDate(candidate.formation_date)} · ${candidate.next_step}</p>
    <section class="detail-section"><h3>Selección</h3><div class="detail-grid">
      ${detailItem("SwingScore", fmtNum(candidate.swing_score, 3))}
      ${detailItem("Percentil swing", fmtNum(candidate.swing_rank_percentile, 3))}
      ${detailItem("Percentil MOM universo", fmtNum(candidate.universe_momentum_percentile, 3))}
      ${detailItem("Pendiente SMA200 pct", fmtNum(candidate.sma200_slope_percentile_d10, 3))}
    </div></section>
    <section class="detail-section"><h3>Niveles congelados</h3><div class="detail-grid">
      ${detailItem("Nivel L", fmtPrice(candidate.formation_close))}
      ${detailItem("ATR20", fmtPrice(candidate.atr_abs20))}
      ${detailItem("Expansión mínima", fmtPrice(candidate.expansion_threshold))}
      ${detailItem("Cierre máximo", fmtPrice(candidate.max_valid_close))}
      ${detailItem("Banda inferior", fmtPrice(candidate.contact_band_low))}
      ${detailItem("Banda superior", fmtPrice(candidate.contact_band_high))}
      ${detailItem("Volumen medio20", fmtNum(candidate.prior_adj_volume20, 0))}
      ${detailItem("Volumen máximo", fmtNum(candidate.max_event_volume, 0))}
    </div></section>
    <section class="detail-section"><h3>Secuencia</h3><div class="detail-grid">
      ${detailItem("Expansión", candidate.expansion_seen ? fmtDate(candidate.expansion_date) : "No confirmada")}
      ${detailItem("Pico expansión", fmtPrice(candidate.expansion_peak))}
      ${detailItem("Primer contacto", fmtDate(candidate.first_contact_date))}
      ${detailItem("Sesiones restantes", candidate.sessions_remaining ?? "N/D")}
    </div></section>
    ${latest ? `<section class="detail-section"><h3>Última sesión evaluada</h3><div class="detail-grid">
      ${detailItem("Fecha / día", `${fmtDate(latest.date)} · D${latest.day}`)}
      ${detailItem("Cierre", fmtPrice(latest.close))}
      ${detailItem("Máximo / mínimo", `${fmtPrice(latest.high)} / ${fmtPrice(latest.low)}`)}
      ${detailItem("Cierre en rango", fmtNum(latest.close_location, 3))}
      ${detailItem("Cierre vs L", `${fmtNum(latest.close_vs_level_atr)} ATR`)}
      ${detailItem("Volumen vs media", fmtPct(latest.volume_ratio - 1))}
    </div></section>` : ""}
    ${checksBlock(candidate)}
    ${candidate.status === "signal" ? `<section class="detail-section"><h3>Entrada</h3><p>Grado ${candidate.grade}. Entrada en la apertura posterior al retest.</p><p class="muted">${candidate.entry_date ? `${fmtDate(candidate.entry_date)} a ${fmtPrice(candidate.entry_open)}` : "Precio pendiente hasta la próxima sesión."}</p></section>` : ""}`;
  showDrawer();
}

function showDrawer() {
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
  document.querySelectorAll(".candidate-filter").forEach(button => button.addEventListener("click", () => {
    state.candidateStatus = button.dataset.candidateStatus;
    document.querySelectorAll(".candidate-filter").forEach(x => x.classList.toggle("active", x === button));
    renderCandidates();
  }));
  document.querySelector("#ticker-search").addEventListener("input", event => {
    state.query = event.target.value;
    renderHistory();
  });
  document.querySelector("#candidate-search").addEventListener("input", event => {
    state.candidateQuery = event.target.value;
    renderCandidates();
  });
  document.body.addEventListener("click", event => {
    const candidate = event.target.closest("[data-candidate]");
    if (candidate) {
      openCandidateDrawer(candidate.dataset.candidate);
      return;
    }
    const signal = event.target.closest("[data-signal]");
    if (signal) openSignalDrawer(signal.dataset.signal);
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
  renderSummary();
  renderCandidates();
  renderCurrent();
  renderHistory();
  renderProfile();
  bindEvents();
}

init();
