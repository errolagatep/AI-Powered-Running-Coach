const CHART_DEFAULTS = {
  labelColor:   "#64748B",
  gridColor:    "rgba(226, 232, 240, 0.7)",
  accentGreen:  "#22C55E",
  accentBlue:   "#3B82F6",
  accentOrange: "#F97316",
  accentRed:    "#EF4444",
};

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;

  try {
    const data = await api.get("/progress/");

    if (data.stats.total_runs === 0) {
      document.getElementById("progress-loading").classList.add("hidden");
      document.getElementById("no-data").classList.remove("hidden");
      return;
    }

    document.getElementById("progress-loading").classList.add("hidden");
    document.getElementById("progress-content").classList.remove("hidden");

    renderStats(data.stats);
    renderWeeklyChart(data.weekly);
    renderPaceChart(data.runs);
    renderHRChart(data.runs);
  } catch (err) {
    document.getElementById("progress-loading").textContent = "Failed to load data.";
    console.error(err);
  }
});

function renderStats(stats) {
  document.getElementById("stats-grid").innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Total Runs</div>
      <div class="stat-value">${stats.total_runs}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Distance</div>
      <div class="stat-value">${stats.total_km.toFixed(1)}</div>
      <div class="stat-unit">kilometers</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Pace</div>
      <div class="stat-value">${formatPace(stats.avg_pace)}</div>
      <div class="stat-unit">min/km</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Best Pace</div>
      <div class="stat-value">${formatPace(stats.best_pace)}</div>
      <div class="stat-unit">min/km</div>
    </div>
  `;
}

function chartOptions(yLabel, yTickCallback) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.92)",
        titleColor: "#f8fafc",
        bodyColor: "#94a3b8",
        borderColor: "rgba(255,255,255,0.08)",
        borderWidth: 1,
        padding: { x: 12, y: 10 },
        cornerRadius: 8,
        displayColors: false,
        callbacks: yTickCallback ? { label: (ctx) => `${yTickCallback(ctx.parsed.y)}` } : {},
      },
    },
    scales: {
      x: {
        ticks: {
          color: CHART_DEFAULTS.labelColor,
          font: { size: 11 },
          maxTicksLimit: 8,
          maxRotation: 0,
        },
        grid: { display: false },
        border: { display: false },
      },
      y: {
        ticks: {
          color: CHART_DEFAULTS.labelColor,
          font: { size: 11 },
          padding: 8,
          ...(yTickCallback ? { callback: yTickCallback } : {}),
        },
        grid: {
          color: CHART_DEFAULTS.gridColor,
          drawTicks: false,
        },
        border: { display: false },
      },
    },
  };
}

function renderWeeklyChart(weekly) {
  const ctx = document.getElementById("weekly-chart").getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, "rgba(249, 115, 22, 0.85)");
  gradient.addColorStop(1, "rgba(249, 115, 22, 0.35)");

  new Chart(ctx, {
    type: "bar",
    data: {
      labels: weekly.labels,
      datasets: [{
        label: "km",
        data: weekly.km,
        backgroundColor: gradient,
        borderColor: "transparent",
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: chartOptions("km"),
  });
}

function renderPaceChart(runs) {
  if (!runs.labels.length) return;

  const ctx = document.getElementById("pace-chart").getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, "rgba(59, 130, 246, 0.2)");
  gradient.addColorStop(1, "rgba(59, 130, 246, 0)");

  const opts = chartOptions("min/km", formatPace);
  opts.scales.y.reverse = true;

  new Chart(ctx, {
    type: "line",
    data: {
      labels: runs.labels,
      datasets: [{
        label: "Pace (min/km)",
        data: runs.pace,
        borderColor: CHART_DEFAULTS.accentBlue,
        backgroundColor: gradient,
        borderWidth: 2.5,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBackgroundColor: "#fff",
        pointBorderColor: CHART_DEFAULTS.accentBlue,
        pointBorderWidth: 2,
        tension: 0.4,
        fill: true,
      }],
    },
    options: opts,
  });
}

function renderHRChart(runs) {
  const hrData = runs.heart_rate.filter(v => v !== null);
  if (!hrData.length) {
    document.getElementById("hr-card").classList.add("hidden");
    return;
  }

  const hrPairs = runs.labels
    .map((l, i) => ({ label: l, hr: runs.heart_rate[i] }))
    .filter(p => p.hr !== null);

  const ctx = document.getElementById("hr-chart").getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, "rgba(239, 68, 68, 0.18)");
  gradient.addColorStop(1, "rgba(239, 68, 68, 0)");

  new Chart(ctx, {
    type: "line",
    data: {
      labels: hrPairs.map(p => p.label),
      datasets: [{
        label: "Avg HR (bpm)",
        data: hrPairs.map(p => p.hr),
        borderColor: CHART_DEFAULTS.accentRed,
        backgroundColor: gradient,
        borderWidth: 2.5,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBackgroundColor: "#fff",
        pointBorderColor: CHART_DEFAULTS.accentRed,
        pointBorderWidth: 2,
        tension: 0.4,
        fill: true,
      }],
    },
    options: chartOptions("bpm"),
  });
}
