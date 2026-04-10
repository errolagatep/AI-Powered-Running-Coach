const PAGE_SIZE = 20;
let _skip       = 0;
let _allLoaded  = [];        // all fetched runs, before filter
let _hasMore    = true;
let _currentFilter = "all";
const _maps     = {};        // runId → Leaflet map instance

// ── Boot ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  await fetchRuns();
});

// ── Data fetching ─────────────────────────────────────────────
async function fetchRuns() {
  document.getElementById("runs-loading").classList.remove("hidden");
  try {
    const batch = await api.get(`/runs/?skip=${_skip}&limit=${PAGE_SIZE}`);
    _allLoaded = _allLoaded.concat(batch);
    _skip += batch.length;
    _hasMore = batch.length === PAGE_SIZE;

    if (_allLoaded.length === 0) {
      document.getElementById("runs-loading").classList.add("hidden");
      document.getElementById("no-runs").classList.remove("hidden");
      return;
    }

    renderStats();
    applyFilter();
    document.getElementById("runs-loading").classList.add("hidden");
    document.getElementById("load-more-wrap").classList.toggle("hidden", !_hasMore);
  } catch (err) {
    document.getElementById("runs-loading").textContent = "Failed to load runs.";
    console.error(err);
  }
}

async function loadMore() {
  const btn = document.getElementById("load-more-btn");
  btn.disabled = true;
  btn.textContent = "Loading…";
  await fetchRuns();
  btn.disabled = false;
  btn.textContent = "Load more runs";
}

// ── Filter ────────────────────────────────────────────────────
function setFilter(filter) {
  _currentFilter = filter;
  document.querySelectorAll(".runs-filter-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.filter === filter);
  });
  applyFilter();
}

function applyFilter() {
  let filtered = _allLoaded;
  if (_currentFilter === "strava") filtered = _allLoaded.filter(r => r.strava_activity_id);
  if (_currentFilter === "manual") filtered = _allLoaded.filter(r => !r.strava_activity_id);

  const list  = document.getElementById("run-list");
  const noRes = document.getElementById("no-filter-results");
  const noRuns = document.getElementById("no-runs");

  noRuns.classList.add("hidden");

  if (filtered.length === 0) {
    list.classList.add("hidden");
    noRes.classList.remove("hidden");
    document.getElementById("no-filter-msg").textContent =
      _currentFilter === "strava"
        ? "No Strava runs imported yet. Connect Strava on the Dashboard."
        : "No manually logged runs yet.";
    return;
  }

  noRes.classList.add("hidden");
  list.classList.remove("hidden");
  list.innerHTML = filtered.map(runCard).join("");
  initRouteMaps(filtered);
}

// ── Stats ─────────────────────────────────────────────────────
function renderStats() {
  const total    = _allLoaded.length;
  const totalKm  = _allLoaded.reduce((s, r) => s + r.distance_km, 0);
  const avgPace  = _allLoaded.reduce((s, r) => s + r.pace_per_km, 0) / total;
  const stravaCount = _allLoaded.filter(r => r.strava_activity_id).length;

  document.getElementById("run-stats").innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Total Runs</div>
      <div class="stat-value">${total}${_hasMore ? "+" : ""}</div>
      <div class="stat-unit">loaded</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Distance</div>
      <div class="stat-value">${totalKm.toFixed(1)}</div>
      <div class="stat-unit">kilometers</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Pace</div>
      <div class="stat-value">${formatPace(avgPace)}</div>
      <div class="stat-unit">min/km</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Strava Runs</div>
      <div class="stat-value">${stravaCount}</div>
      <div class="stat-unit">imported</div>
    </div>
  `;
}

// ── Run card ──────────────────────────────────────────────────
function runCard(run) {
  const effort  = run.effort_level;
  const cls     = effortClass(effort);
  const durStr  = formatDuration(run.duration_min);
  const hrStr   = run.heart_rate_avg ? `${run.heart_rate_avg} bpm` : "—";
  const stravaTag = run.strava_activity_id ? `<span class="strava-tag">Strava</span>` : "";

  let expandContent;
  if (run.ai_feedback) {
    expandContent = `<div class="feedback-content">${renderMarkdown(run.ai_feedback)}</div>`;
  } else if (isWithin7Days(run.date)) {
    expandContent = `<div style="padding:10px 0 4px;">
      <button class="btn btn-secondary" style="font-size:13px;"
        onclick="event.stopPropagation();generateFeedback('${run.id}',this)">
        ✨ Get Takbo Coach Feedback
      </button>
    </div>`;
  } else {
    expandContent = `<p style="font-size:13px;color:var(--text-sec);padding:8px 0 2px;">No coaching feedback for this run.</p>`;
  }

  const mapPanel = run.route_polyline
    ? `<div class="run-item-map" id="rmap-${run.id}"></div>`
    : "";

  const withMap = run.route_polyline ? "run-item-with-route" : "";

  return `
    <div class="run-item ${withMap}" id="rcard-${run.id}" onclick="toggleRunExpand(this)" style="cursor:pointer;">
      <div class="run-item-body">
        <div class="run-item-header">
          <span class="run-date">${formatDate(run.date)}${stravaTag}</span>
          <div class="run-stats">
            <div class="run-stat">
              <span class="run-stat-value">${formatDistance(run.distance_km)} km</span>
              <span class="run-stat-label">Distance</span>
            </div>
            <div class="run-stat">
              <span class="run-stat-value">${formatPace(run.pace_per_km)}</span>
              <span class="run-stat-label">Pace /km</span>
            </div>
            <div class="run-stat">
              <span class="run-stat-value">${durStr}</span>
              <span class="run-stat-label">Duration</span>
            </div>
            <div class="run-stat">
              <span class="run-stat-value">${hrStr}</span>
              <span class="run-stat-label">Heart Rate</span>
            </div>
          </div>
          <span class="effort-badge ${cls}">${effort}</span>
        </div>
        ${run.notes ? `<p class="run-notes">${run.notes}</p>` : ""}
        <div class="run-expandable"><div>${expandContent}</div></div>
      </div>
      ${mapPanel}
    </div>
  `;
}

function toggleRunExpand(card) {
  card.classList.toggle("run-expanded");
}

function isWithin7Days(dateStr) {
  const runDay    = dateStr.slice(0, 10);
  const cutoff    = new Date();
  cutoff.setDate(cutoff.getDate() - 7);
  const cutoffDay = cutoff.toISOString().slice(0, 10);
  return runDay >= cutoffDay;
}

async function generateFeedback(runId, btn) {
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    const updated = await api.post(`/runs/${runId}/regenerate`, {});
    const idx = _allLoaded.findIndex(r => r.id === runId);
    if (idx !== -1) _allLoaded[idx] = updated;
    const card = document.getElementById(`rcard-${runId}`);
    if (card) {
      if (_maps[runId]) { _maps[runId].remove(); delete _maps[runId]; }
      card.outerHTML = runCard(updated);
      document.getElementById(`rcard-${runId}`)?.classList.add("run-expanded");
      initRouteMaps([updated]);
    }
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "✨ Get Takbo Coach Feedback";
    alert(err.message || "Failed to generate feedback.");
  }
}

// ── Route maps ────────────────────────────────────────────────
function decodePolyline(encoded) {
  let index = 0, lat = 0, lng = 0, coords = [];
  while (index < encoded.length) {
    let shift = 0, result = 0, byte;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : result >> 1;
    shift = 0; result = 0;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : result >> 1;
    coords.push([lat / 1e5, lng / 1e5]);
  }
  return coords;
}

function initRouteMaps(runs) {
  requestAnimationFrame(() => {
    runs.filter(r => r.route_polyline).forEach(run => {
      const container = document.getElementById(`rmap-${run.id}`);
      if (!container || _maps[run.id]) return;

      const coords = decodePolyline(run.route_polyline);
      if (coords.length < 2) return;

      const map = L.map(container, {
        zoomControl: false, attributionControl: false,
        dragging: false, scrollWheelZoom: false,
        touchZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(map);

      const line = L.polyline(coords, { color: "#F97316", weight: 4, opacity: 0.95 }).addTo(map);
      L.circleMarker(coords[0],               { radius: 7, color: "#fff", weight: 2, fillColor: "#22C55E", fillOpacity: 1 }).bindTooltip("Start").addTo(map);
      L.circleMarker(coords[coords.length-1], { radius: 7, color: "#fff", weight: 2, fillColor: "#EF4444", fillOpacity: 1 }).bindTooltip("Finish").addTo(map);

      map.fitBounds(line.getBounds(), { padding: [16, 16] });
      _maps[run.id] = map;
    });
  });
}

// ── Helpers ───────────────────────────────────────────────────
function toggleFeedback(btn) {
  const content = btn.nextElementSibling;
  const isOpen  = content.classList.toggle("open");
  btn.textContent = (isOpen ? "▼ Hide" : "▶ Show") + " coach feedback";
}

function renderMarkdown(text) {
  return text
    .replace(/^## (.+)$/gm,  "<h2>$1</h2>")
    .replace(/^### (.+)$/gm, "<h3 style='font-size:13px;color:var(--text);margin:8px 0 4px;'>$1</h3>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[h])(.+)$/gm, m => m.startsWith("<") ? m : `<p>${m}</p>`)
    .replace(/<p><\/p>/g, "");
}
