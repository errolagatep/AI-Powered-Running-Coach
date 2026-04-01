const CHART_DEFAULTS = {
  color: "#e6edf3",
  gridColor: "rgba(48,54,61,0.8)",
  accentGreen:  "#3fb950",
  accentBlue:   "#58a6ff",
  accentOrange: "#d29922",
  accentRed:    "#f85149",
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

function chartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#1c2230",
        titleColor: "#e6edf3",
        bodyColor: "#8b949e",
        borderColor: "#30363d",
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        ticks: { color: CHART_DEFAULTS.color, font: { size: 11 }, maxTicksLimit: 10 },
        grid:  { color: CHART_DEFAULTS.gridColor },
      },
      y: {
        ticks: { color: CHART_DEFAULTS.color, font: { size: 11 } },
        grid:  { color: CHART_DEFAULTS.gridColor },
        title: { display: true, text: yLabel, color: "#8b949e", font: { size: 12 } },
      },
    },
  };
}

function renderWeeklyChart(weekly) {
  const ctx = document.getElementById("weekly-chart").getContext("2d");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: weekly.labels,
      datasets: [{
        label: "km",
        data: weekly.km,
        backgroundColor: "rgba(63,185,80,0.6)",
        borderColor: CHART_DEFAULTS.accentGreen,
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: chartOptions("km"),
  });
}

function renderPaceChart(runs) {
  if (!runs.labels.length) return;

  // Invert pace for display (lower pace = faster = better, show as descending)
  const ctx = document.getElementById("pace-chart").getContext("2d");
  new Chart(ctx, {
    type: "line",
    data: {
      labels: runs.labels,
      datasets: [{
        label: "Pace (min/km)",
        data: runs.pace,
        borderColor: CHART_DEFAULTS.accentBlue,
        backgroundColor: "rgba(88,166,255,0.1)",
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: CHART_DEFAULTS.accentBlue,
        tension: 0.3,
        fill: true,
      }],
    },
    options: {
      ...chartOptions("min/km"),
      scales: {
        ...chartOptions("min/km").scales,
        y: {
          ...chartOptions("min/km").scales.y,
          reverse: true,
          ticks: {
            color: CHART_DEFAULTS.color,
            font: { size: 11 },
            callback: (val) => formatPace(val),
          },
        },
      },
    },
  });
}

function renderHRChart(runs) {
  const hrData = runs.heart_rate.filter(v => v !== null);
  if (!hrData.length) {
    document.getElementById("hr-card").classList.add("hidden");
    return;
  }

  // Filter labels to only those with HR data
  const hrPairs = runs.labels
    .map((l, i) => ({ label: l, hr: runs.heart_rate[i] }))
    .filter(p => p.hr !== null);

  const ctx = document.getElementById("hr-chart").getContext("2d");
  new Chart(ctx, {
    type: "line",
    data: {
      labels: hrPairs.map(p => p.label),
      datasets: [{
        label: "Avg HR (bpm)",
        data: hrPairs.map(p => p.hr),
        borderColor: CHART_DEFAULTS.accentRed,
        backgroundColor: "rgba(248,81,73,0.1)",
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: CHART_DEFAULTS.accentRed,
        tension: 0.3,
        fill: true,
      }],
    },
    options: chartOptions("bpm"),
  });
}
