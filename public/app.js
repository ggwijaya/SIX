const state = {
  stocks: [],
  filtered: [],
  sortKey: "score",
  sortDirection: "desc",
};

const $ = (selector) => document.querySelector(selector);
const stockRows = $("#stockRows");
const statusAlert = $("#statusAlert");

const formatNumber = (value, decimals = 1) =>
  value == null ? "—" : new Intl.NumberFormat("en-US", { maximumFractionDigits: decimals }).format(value);

const formatIDR = (value) => {
  if (value == null) return "—";
  if (value >= 1e12) return `IDR ${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `IDR ${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `IDR ${(value / 1e6).toFixed(0)}M`;
  return `IDR ${formatNumber(value, 0)}`;
};

const median = (values) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

function setAlert(message, kind = "warning") {
  statusAlert.textContent = message;
  statusAlert.classList.toggle("hidden", !message);
  statusAlert.dataset.kind = kind;
}

function updateSummary(data) {
  $("#universeMetric").textContent = formatNumber(data.universeCount, 0);
  $("#eligibleMetric").textContent = formatNumber(data.qualifyingCount, 0);
  $("#medianMetric").textContent = formatNumber(median(data.stocks.map((stock) => stock.score)), 1);
  $("#updatedMetric").textContent = new Date(data.asOf).toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
  $("#sourceMetric").textContent = data.source;
  $("#modelLabel").textContent = data.model?.label || "Conservative v2";
  const market = data.marketContext || {};
  $("#regimeLabel").textContent = !market.available
    ? "Unavailable"
    : market.bullish
      ? "Bullish regime"
      : "Defensive regime";
  $("#regimeLabel").classList.toggle("positive", Boolean(market.available && market.bullish));
  $("#regimeLabel").classList.toggle("negative", Boolean(market.available && !market.bullish));
  $("#freshnessLabel").textContent = data.stale ? "Showing cached market data" : "Market data is current";
  $(".status-dot").classList.toggle("stale", data.stale);
  document.querySelectorAll(".skeleton-card").forEach((card) => card.classList.remove("skeleton-card"));
  const warnings = Array.isArray(data.warnings) ? data.warnings.filter(Boolean) : [];
  if (data.error) setAlert(data.error.message);
  else if (warnings.length) setAlert(warnings.join(" "));
  else if (data.reducedCountReason) setAlert(data.reducedCountReason);
  else setAlert("");
}

function populateSectors() {
  const select = $("#sectorFilter");
  const current = select.value;
  const sectors = [...new Set(state.stocks.map((stock) => stock.sector).filter(Boolean))].sort();
  select.innerHTML = '<option value="">All sectors</option>' +
    sectors.map((sector) => `<option value="${escapeHtml(sector)}">${escapeHtml(sector)}</option>`).join("");
  select.value = current;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

function applyFilters() {
  const query = $("#searchInput").value.trim().toLowerCase();
  const sector = $("#sectorFilter").value;
  const signal = $("#signalFilter").value;
  const setup = $("#setupFilter").value;
  const minimumScore = Number($("#scoreFilter").value);
  const rsiRange = $("#rsiFilter").value;
  const minimumLiquidity = Number($("#liquidityFilter").value);
  $("#scoreValue").textContent = minimumScore;

  state.filtered = state.stocks.filter((stock) => {
    const identity = `${stock.symbol} ${stock.company}`.toLowerCase();
    if (query && !identity.includes(query)) return false;
    if (sector && stock.sector !== sector) return false;
    if (signal && stock.signal !== signal) return false;
    if (setup && stock.reversalSetup?.status !== setup) return false;
    if (stock.score < minimumScore) return false;
    if ((stock.averageTradedValue || 0) < minimumLiquidity) return false;
    if (rsiRange) {
      const [low, high] = rsiRange.split("-").map(Number);
      if (stock.rsi == null || stock.rsi < low || stock.rsi > high) return false;
    }
    return true;
  });

  const key = state.sortKey;
  const direction = state.sortDirection === "asc" ? 1 : -1;
  state.filtered.sort((left, right) => {
    const a = left[key];
    const b = right[key];
    if (typeof a === "string") return a.localeCompare(b) * direction;
    return ((a ?? -Infinity) - (b ?? -Infinity)) * direction;
  });
  renderRows();
}

function renderRows() {
  $("#resultCount").textContent = state.filtered.length;
  if (!state.filtered.length) {
    stockRows.innerHTML = '<tr><td colspan="11" class="empty-state">No stocks match these filters. Try widening the screen.</td></tr>';
    return;
  }
  stockRows.innerHTML = state.filtered.map((stock) => {
    const changeClass = stock.change >= 0 ? "positive" : "negative";
    const changePrefix = stock.change > 0 ? "+" : "";
    const setupStatus = stock.reversalSetup?.status || "Unavailable";
    return `<tr class="stock-row" tabindex="0" data-symbol="${escapeHtml(stock.symbol)}">
      <td class="rank">${stock.rank}</td>
      <td><span class="ticker">${escapeHtml(stock.symbol)}</span><span class="company">${escapeHtml(stock.company)}</span></td>
      <td class="sector">${escapeHtml(stock.sector)}</td>
      <td class="numeric">${formatNumber(stock.price, 0)}</td>
      <td class="numeric ${changeClass}">${changePrefix}${formatNumber(stock.change, 2)}%</td>
      <td class="numeric score-cell"><strong>${formatNumber(stock.score, 1)}</strong><span class="score-track"><i style="width:${stock.score}%"></i></span></td>
      <td><span class="signal ${stock.signal.toLowerCase()}">${stock.signal}</span></td>
      <td><span class="setup-badge ${setupStatusClass(setupStatus)}">${escapeHtml(compactSetupStatus(setupStatus))}</span></td>
      <td class="numeric">${formatNumber(stock.rsi, 1)}</td>
      <td class="numeric">${formatNumber(stock.relativeVolume, 2)}×</td>
      <td class="numeric">${formatIDR(stock.averageTradedValue)}</td>
    </tr>`;
  }).join("");

  document.querySelectorAll(".stock-row").forEach((row) => {
    row.addEventListener("click", () => openDetail(row.dataset.symbol));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") openDetail(row.dataset.symbol);
    });
  });
}

async function loadScreener() {
  try {
    const response = await fetch("/api/screener?limit=200");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Unable to load market data.");
    state.stocks = data.stocks;
    updateSummary(data);
    populateSectors();
    applyFilters();
  } catch (error) {
    stockRows.innerHTML = `<tr><td colspan="11" class="empty-state">${escapeHtml(error.message)}</td></tr>`;
    $("#freshnessLabel").textContent = "Market data unavailable";
    $(".status-dot").classList.add("stale");
    setAlert(error.message);
  }
}

async function refreshScreener() {
  const button = $("#refreshButton");
  button.disabled = true;
  button.querySelector(".refresh-icon").textContent = "…";
  try {
    const response = await fetch("/api/refresh", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Refresh failed.");
    state.stocks = data.stocks.slice(0, 200);
    updateSummary({ ...data, stocks: state.stocks });
    populateSectors();
    applyFilters();
  } catch (error) {
    setAlert(error.message);
  } finally {
    button.disabled = false;
    button.querySelector(".refresh-icon").textContent = "↻";
  }
}

function openDrawer() {
  $("#detailDrawer").classList.add("open");
  $("#detailDrawer").setAttribute("aria-hidden", "false");
  $("#drawerBackdrop").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeDrawer() {
  $("#detailDrawer").classList.remove("open");
  $("#detailDrawer").setAttribute("aria-hidden", "true");
  $("#drawerBackdrop").classList.add("hidden");
  document.body.style.overflow = "";
}

async function openDetail(symbol) {
  const stock = state.stocks.find((item) => item.symbol === symbol);
  const content = $("#drawerContent");
  content.innerHTML = `<p class="detail-symbol">IDX:${escapeHtml(symbol)}</p><h2 class="detail-title">${escapeHtml(stock?.company || symbol)}</h2><div class="loading-line"></div>`;
  openDrawer();
  try {
    const response = await fetch(`/api/stocks/${encodeURIComponent(symbol)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "Unable to load stock history.");
    renderDetail(data.stock, data.history, data.stale);
  } catch (error) {
    content.innerHTML += `<p class="alert">${escapeHtml(error.message)}</p>`;
  }
}

function renderDetail(stock, history, stale) {
  const latest = history[history.length - 1];
  const relativeStrength = stock.relativeStrength || {};
  const strongGate = stock.strongGate || {};
  const gateChecks = strongGate.checks || {};
  const deductions = stock.deductions || [];
  const reversalSetup = stock.reversalSetup || {};
  const setupChecks = reversalSetup.checks || {};
  const setupLookback = reversalSetup.lookback || {};
  const setupIndicators = reversalSetup.indicators || {};
  const setupStatus = reversalSetup.status || "Unavailable";
  $("#drawerContent").innerHTML = `
    <p class="detail-symbol">IDX:${escapeHtml(stock.symbol)} ${stale ? "· CACHED" : ""}</p>
    <h2 class="detail-title">${escapeHtml(stock.company || stock.symbol)}</h2>
    <p class="sector">${escapeHtml(stock.sector || "IDX Equity")}</p>
    <div class="detail-price">IDR ${formatNumber(latest?.close || stock.price, 0)}
      <span class="${stock.change >= 0 ? "positive" : "negative"}" style="font-size:12px">${stock.change > 0 ? "+" : ""}${formatNumber(stock.change, 2)}%</span>
    </div>
    <div class="chart-shell"><span class="chart-caption">1 YEAR · DAILY CLOSE</span><canvas id="priceChart"></canvas></div>
    <section class="detail-section">
      <h3>Score composition · ${formatNumber(stock.score, 1)}/100</h3>
      <div class="breakdown">
        ${Object.entries(stock.scoreBreakdown || {}).map(([key, value]) => `<div class="${value < 0 ? "penalty-score" : ""}"><span>${key.replace(/([A-Z])/g, " $1").toUpperCase()}</span><strong>${formatNumber(value, 1)}</strong></div>`).join("")}
      </div>
    </section>
    <section class="detail-section">
      <h3>Technical snapshot</h3>
      <div class="indicator-grid">
        <div><span>RSI 14</span><strong>${formatNumber(stock.rsi, 1)}</strong></div>
        <div><span>REL. VOLUME</span><strong>${formatNumber(stock.relativeVolume, 2)}×</strong></div>
        <div><span>ATR / PRICE</span><strong>${formatNumber(stock.atrPercent, 2)}%</strong></div>
        <div><span>CHAIKIN MF</span><strong>${formatNumber(stock.cmf, 3)}</strong></div>
        <div><span>TREND PERSISTENCE</span><strong>${formatNumber(stock.trendPersistence, 0)}/3</strong></div>
        <div><span>VOLUME CONFIRMED</span><strong>${stock.volumeConfirmed ? "YES" : "NO"}</strong></div>
        <div><span>1 MONTH</span><strong>${formatNumber(stock.return1m, 1)}%</strong></div>
        <div><span>3 MONTH</span><strong>${formatNumber(stock.return3m, 1)}%</strong></div>
        <div><span>AVG. VALUE</span><strong>${formatIDR(stock.averageTradedValue)}</strong></div>
      </div>
    </section>
    <section class="detail-section">
      <h3>Relative strength</h3>
      <div class="indicator-grid">
        <div><span>VS IHSG 1M</span><strong>${formatSignedPercent(relativeStrength.market1m)}</strong></div>
        <div><span>VS IHSG 3M</span><strong>${formatSignedPercent(relativeStrength.market3m)}</strong></div>
        <div><span>VS SECTOR 1M</span><strong>${formatSignedPercent(relativeStrength.sector1m)}</strong></div>
        <div><span>VS SECTOR 3M</span><strong>${formatSignedPercent(relativeStrength.sector3m)}</strong></div>
        <div><span>SECTOR SAMPLE</span><strong>${formatNumber(relativeStrength.sectorSize, 0)}</strong></div>
        <div><span>BENCHMARK VALID</span><strong>${relativeStrength.sectorEligible ? "YES" : "NO"}</strong></div>
      </div>
    </section>
    <section class="detail-section">
      <h3>Oversold recovery · <span class="setup-badge ${setupStatusClass(setupStatus)}">${escapeHtml(setupStatus)}</span></h3>
      <p class="setup-note">Timing diagnostic only. It does not change the score, rank, or signal.</p>
      <div class="indicator-grid">
        <div><span>RSI 14</span><strong>${formatNumber(setupIndicators.rsi, 1)}</strong></div>
        <div><span>STOCHASTIC %K</span><strong>${formatNumber(setupIndicators.stochasticK, 1)}</strong></div>
        <div><span>STOCHASTIC %D</span><strong>${formatNumber(setupIndicators.stochasticD, 1)}</strong></div>
        <div><span>LOOKBACK</span><strong>${formatNumber(setupLookback.sessions, 0)} sessions</strong></div>
        <div><span>PRIOR OVERSOLD</span><strong>${setupLookback.oversoldDetected ? "YES" : "NO"}</strong></div>
        <div><span>MOST RECENT</span><strong>${setupLookback.mostRecentOversoldSessionsAgo == null ? "—" : `${setupLookback.mostRecentOversoldSessionsAgo} session(s) ago`}</strong></div>
      </div>
      <div class="tag-list setup-checks">${Object.entries(setupChecks).map(([key, passed]) => `<span class="tag ${passed ? "" : "risk"}">${passed ? "PASS" : "FAIL"} · ${escapeHtml(humanizeKey(key))}</span>`).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>Strong gate · ${strongGate.passed ? "PASSED" : "NOT PASSED"}</h3>
      <div class="tag-list">${Object.entries(gateChecks).map(([key, passed]) => `<span class="tag ${passed ? "" : "risk"}">${passed ? "PASS" : "FAIL"} · ${escapeHtml(humanizeKey(key))}</span>`).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>Positive signals</h3>
      <div class="tag-list">${(stock.positiveSignals?.length ? stock.positiveSignals : ["No strong positive signals"]).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>Risk flags</h3>
      <div class="tag-list">${(stock.riskFlags?.length ? stock.riskFlags : ["No major technical risk flags"]).map((tag) => `<span class="tag risk">${escapeHtml(tag)}</span>`).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>Deductions</h3>
      <div class="deduction-list">${deductions.length
        ? deductions.map((item) => `<div><span>${escapeHtml(item.label)}</span><strong>-${formatNumber(item.points, 1)}</strong></div>`).join("")
        : "<p class=\"sector\">No score deductions.</p>"}
      </div>
    </section>`;
  drawChart(history);
}

function humanizeKey(value) {
  return String(value).replace(/([A-Z])/g, " $1").replace(/^./, (character) => character.toUpperCase());
}

function setupStatusClass(status) {
  return String(status || "Unavailable").toLowerCase().replace(/\s+/g, "-");
}

function compactSetupStatus(status) {
  if (status === "Recovery Confirmed") return "Recovery";
  if (status === "Oversold Watch") return "Oversold";
  return status;
}

function formatSignedPercent(value) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${formatNumber(value, 1)}%`;
}

function drawChart(history) {
  const canvas = $("#priceChart");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const width = rect.width;
  const height = rect.height;
  const padding = 22;
  const closes = history.map((point) => point.close).filter(Number.isFinite);
  if (closes.length < 2) return;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const points = closes.map((value, index) => ({
    x: padding + (index / (closes.length - 1)) * (width - padding * 2),
    y: height - padding - ((value - min) / range) * (height - padding * 2),
  }));
  context.strokeStyle = "rgba(130,151,160,.12)";
  context.lineWidth = 1;
  for (let line = 1; line <= 3; line++) {
    const y = padding + line * ((height - padding * 2) / 4);
    context.beginPath(); context.moveTo(padding, y); context.lineTo(width - padding, y); context.stroke();
  }
  const gradient = context.createLinearGradient(0, padding, 0, height);
  gradient.addColorStop(0, "rgba(54,224,189,.24)");
  gradient.addColorStop(1, "rgba(54,224,189,0)");
  context.beginPath();
  points.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
  context.lineTo(points[points.length - 1].x, height - padding);
  context.lineTo(points[0].x, height - padding);
  context.closePath(); context.fillStyle = gradient; context.fill();
  context.beginPath();
  points.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
  context.strokeStyle = "#36e0bd"; context.lineWidth = 2; context.stroke();
}

document.querySelectorAll(".filters input, .filters select").forEach((control) => {
  const eventName = ["search", "range"].includes(control.type) ? "input" : "change";
  control.addEventListener(eventName, applyFilters);
});
document.querySelectorAll("th[data-sort]").forEach((header) => {
  header.addEventListener("click", () => {
    const key = header.dataset.sort;
    state.sortDirection = state.sortKey === key && state.sortDirection === "desc" ? "asc" : "desc";
    state.sortKey = key;
    document.querySelectorAll("th").forEach((cell) => cell.classList.remove("active-sort"));
    header.classList.add("active-sort");
    header.textContent = header.textContent.replace(/[ ↑↓]/g, "") + (state.sortDirection === "asc" ? " ↑" : " ↓");
    applyFilters();
  });
});
$("#refreshButton").addEventListener("click", refreshScreener);
$("#drawerClose").addEventListener("click", closeDrawer);
$("#drawerBackdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });

loadScreener();
