const API_BASE = window.location.origin;
let chart, candleSeries;
let obPriceLines = [];
let fvgPriceLines = [];
let structureMarkers = [];
let currentData = null;

const el = (id) => document.getElementById(id);

function initChart() {
  const container = el("chart");
  chart = LightweightCharts.createChart(container, {
    layout: { background: { color: "#131826" }, textColor: "#e6edf7" },
    grid: {
      vertLines: { color: "#1a2035" },
      horzLines: { color: "#1a2035" },
    },
    timeScale: { borderColor: "#232b40", timeVisible: true },
    rightPriceScale: { borderColor: "#232b40" },
    crosshair: { mode: 0 },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: "#16c784",
    downColor: "#ea3943",
    borderUpColor: "#16c784",
    borderDownColor: "#ea3943",
    wickUpColor: "#16c784",
    wickDownColor: "#ea3943",
  });

  window.addEventListener("resize", () => {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  });
}

function toTime(ts) {
  // Backend returns string timestamps; convert to unix seconds
  const d = new Date(ts);
  if (isNaN(d.getTime())) return Math.floor(Date.now() / 1000);
  return Math.floor(d.getTime() / 1000);
}

function renderCandles(candles) {
  const data = candles.map((c) => ({
    time: toTime(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
  candleSeries.setData(data);
  chart.timeScale().fitContent();
}

function clearOverlays() {
  obPriceLines.forEach((l) => candleSeries.removePriceLine(l));
  fvgPriceLines.forEach((l) => candleSeries.removePriceLine(l));
  obPriceLines = [];
  fvgPriceLines = [];
  structureMarkers = [];
}

function drawOrderBlocks(obs) {
  // Only draw recent, unmitigated OBs to avoid clutter
  const recent = obs.filter((o) => !o.mitigated).slice(-8);
  recent.forEach((ob) => {
    const color = ob.kind === "bullish"
      ? "rgba(22, 199, 132, 0.6)"
      : "rgba(234, 57, 67, 0.6)";
    const line = candleSeries.createPriceLine({
      price: ob.top,
      color,
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true,
      title: `${ob.kind === "bullish" ? "Bull" : "Bear"} OB`,
    });
    obPriceLines.push(line);
  });
}

function drawFVGs(fvgs) {
  const recent = fvgs.filter((f) => !f.filled).slice(-8);
  recent.forEach((f) => {
    const color = f.kind === "bullish"
      ? "rgba(79, 140, 255, 0.5)"
      : "rgba(255, 179, 71, 0.5)";
    const line = candleSeries.createPriceLine({
      price: (f.top + f.bottom) / 2,
      color,
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: `${f.kind === "bullish" ? "Bull" : "Bear"} FVG`,
    });
    fvgPriceLines.push(line);
  });
}

function drawStructure(structure) {
  const markers = structure.slice(-15).map((s) => ({
    time: toTime(s.timestamp),
    position: s.direction === "bullish" ? "belowBar" : "aboveBar",
    color: s.kind === "CHoCH" ? "#ffb347" : "#a259ff",
    shape: s.direction === "bullish" ? "arrowUp" : "arrowDown",
    text: s.kind,
  })).sort((a, b) => a.time - b.time);

  candleSeries.setMarkers(markers);
}

function renderSignal(signal) {
  const box = el("signal-content");
  const bias = signal.bias || "neutral";
  const conf = signal.confidence || 0;

  const fmt = (v) => v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 6 });

  box.innerHTML = `
    <div class="bias ${bias}">
      ${bias === "bullish" ? "▲" : bias === "bearish" ? "▼" : "■"}
      ${bias.toUpperCase()}
    </div>
    <div class="confidence-bar">
      <div class="confidence-fill" style="width:${conf}%"></div>
    </div>
    <div style="font-size:12px;color:var(--muted)">Confidence: ${conf}%</div>
    <div class="levels">
      <div><span class="label">Entry</span><strong>${fmt(signal.entry)}</strong></div>
      <div><span class="label">Stop Loss</span><strong>${fmt(signal.stop_loss)}</strong></div>
      <div><span class="label">Take Profit 1</span><strong>${fmt(signal.take_profit_1)}</strong></div>
      <div><span class="label">Take Profit 2</span><strong>${fmt(signal.take_profit_2)}</strong></div>
      <div><span class="label">R:R</span><strong>${signal.risk_reward || "—"}</strong></div>
    </div>
    <ul class="reasons">
      ${(signal.reasons || []).map((r) => `<li>${r}</li>`).join("")}
    </ul>
  `;
}

function renderZones(tab) {
  const list = el("zones-list");
  if (!currentData) return;

  let items = [];
  if (tab === "obs") {
    items = currentData.order_blocks.slice(-10).map((o) => `
      <div class="zone-item ${o.kind === "bullish" ? "bull" : "bear"}">
        <div class="row"><strong>${o.kind.toUpperCase()} OB</strong>
          <span>${o.mitigated ? "Mitigated" : "Active"}</span></div>
        <div class="row"><span>${o.bottom.toFixed(4)} — ${o.top.toFixed(4)}</span></div>
      </div>`);
  } else if (tab === "fvgs") {
    items = currentData.fvgs.slice(-10).map((f) => `
      <div class="zone-item ${f.kind === "bullish" ? "bull" : "bear"}">
        <div class="row"><strong>${f.kind.toUpperCase()} FVG</strong>
          <span>${f.filled ? "Filled" : "Open"}</span></div>
        <div class="row"><span>${f.bottom.toFixed(4)} — ${f.top.toFixed(4)}</span></div>
      </div>`);
  } else if (tab === "struct") {
    items = currentData.structure.slice(-10).map((s) => `
      <div class="zone-item ${s.direction === "bullish" ? "bull" : "bear"}">
        <div class="row"><strong>${s.kind}</strong>
          <span>${s.direction}</span></div>
        <div class="row"><span>@ ${s.price.toFixed(4)}</span></div>
      </div>`);
  } else {
    items = currentData.liquidity.slice(-10).map((l) => `
      <div class="zone-item ${l.kind === "buy_side" ? "bear" : "bull"}">
        <div class="row"><strong>${l.kind === "buy_side" ? "Buy-side" : "Sell-side"}</strong>
          <span>${l.swept ? "Swept" : "Intact"}</span></div>
        <div class="row"><span>@ ${l.price.toFixed(4)}</span></div>
      </div>`);
  }

  list.innerHTML = items.join("") || `<div style="color:var(--muted)">No data</div>`;
}

async function analyze() {
  const symbol = el("symbol").value.trim().toUpperCase();
  const timeframe = el("timeframe").value;

  el("loader").classList.remove("hidden");
  try {
    const res = await fetch(`${API_BASE}/api/analyze?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Analysis failed");

    currentData = data;

    clearOverlays();
    renderCandles(data.candles);
    drawOrderBlocks(data.order_blocks);
    drawFVGs(data.fvgs);
    drawStructure(data.structure);
    renderSignal(data.signal);
    renderZones(document.querySelector(".tab.active").dataset.tab);
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    el("loader").classList.add("hidden");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initChart();
  el("analyze").addEventListener("click", analyze);
  el("symbol").addEventListener("keydown", (e) => {
    if (e.key === "Enter") analyze();
  });

  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      renderZones(t.dataset.tab);
    });
  });

  // Initial load
  analyze();
});
