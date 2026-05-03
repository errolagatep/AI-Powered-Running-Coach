// Init Flatpickr for the edit-run modal date field (no future dates on a logged run)
const _editDatePicker = flatpickr("#edit-date", {
  maxDate: "today",
  dateFormat: "Y-m-d",
  disableMobile: true,
  allowInput: false,
});

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;

  const user = getUser();
  if (user) {
    document.getElementById("welcome-msg").textContent = `Welcome back, ${user.name.split(" ")[0]}!`;
  }

  // Auto-sync Strava silently on first load after login/relogin
  const shouldSync = localStorage.getItem("strava_sync_on_load") === "1";
  if (shouldSync) {
    localStorage.removeItem("strava_sync_on_load");
    _silentStravaSync();
  }

  try {
    const [runs, progress, goal, gam, achievements, plan] = await Promise.all([
      api.get("/runs/?limit=10"),
      api.get("/progress/"),
      api.get("/goals/"),
      api.get("/gamification/").catch(() => null),
      api.get("/gamification/achievements").catch(() => []),
      api.get("/plans/current").catch(() => null),
    ]);

    renderStats(progress, runs);
    renderGoalBanner(goal, plan);
    renderProfileIncompleteBanner();
    renderSetupChecklist(goal, plan, runs);
    renderWeeklyRecap(runs, plan, gam);
    renderTodayWorkout(plan);
    renderRuns(runs);
    if (gam) renderGamification(gam);
    if (achievements) checkNewAchievements(achievements);
  } catch (err) {
    console.error(err);
  }
});

async function _silentStravaSync() {
  try {
    const status = await api.get("/integrations/strava/status");
    if (!status.connected) return;
    const result = await api.post("/integrations/strava/sync", {});
    if (result.imported > 0) {
      // Refresh run list to show newly synced runs
      const runs = await api.get("/runs/?limit=10");
      renderRuns(runs);
      if (result.new_achievements?.length && typeof showAchievementToast === "function") {
        result.new_achievements.forEach((a, i) => {
          setTimeout(() => showAchievementToast(a), 800 + i * 800);
        });
      }
    }
  } catch (_) {
    // Silent — never surface Strava sync errors on login
  }
}

// Standalone loadRuns — called by integrations.js after Strava sync
async function loadRuns() {
  document.getElementById("runs-loading").classList.remove("hidden");
  document.getElementById("run-list").classList.add("hidden");
  document.getElementById("no-runs").classList.add("hidden");
  try {
    const runs = await api.get("/runs/?limit=10");
    renderRuns(runs);
  } catch (err) {
    console.error(err);
    document.getElementById("runs-loading").classList.add("hidden");
  }
}

// ── Profile incomplete prompt ──────────────────────────────────
function renderProfileIncompleteBanner() {
  const user = getUser();
  const wasSkipped = localStorage.getItem("show_profile_prompt") === "1";
  if (wasSkipped) localStorage.removeItem("show_profile_prompt");
  if (!user || (user.onboarding_complete && !wasSkipped)) return;
  const el = document.getElementById("profile-incomplete-banner");
  el.innerHTML = `
    <div class="coach-prompt-card">
      <div class="coach-prompt-avatar">🏃</div>
      <div class="coach-prompt-body">
        <div class="coach-prompt-title">Complete your runner profile</div>
        <div class="coach-prompt-msg">Your coaching feedback and training plans will be much more accurate once I know more about you. It only takes 2 minutes!</div>
        <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap;">
          <a href="/onboarding.html" class="btn btn-primary" style="font-size:13px;padding:7px 16px;">Complete Onboarding</a>
          <a href="/profile.html" class="btn btn-secondary" style="font-size:13px;padding:7px 16px;">Edit Profile</a>
        </div>
      </div>
    </div>`;
  el.classList.remove("hidden");
}

// ── Setup Checklist ────────────────────────────────────────────
function renderSetupChecklist(goal, plan, runs) {
  const STORAGE_KEY = "setup_checklist_dismissed";
  if (localStorage.getItem(STORAGE_KEY) === "1") return;

  const user = getUser();
  const hasAssessment  = user?.onboarding_complete;
  const hasGoal        = !!goal;
  const hasProgram     = !!(plan?.program_id);
  const hasFirstRun    = runs && runs.length > 0;

  // Hide once all steps are complete
  if (hasAssessment && hasGoal && hasProgram && hasFirstRun) {
    localStorage.setItem(STORAGE_KEY, "1");
    return;
  }

  const step = (done, label, href, cta) => `
    <li class="setup-checklist-item${done ? " done" : ""}">
      <span class="setup-check-icon${done ? " done" : ""}">${done ? "✓" : "·"}</span>
      <span style="flex:1;">${label}</span>
      ${!done && href ? `<a href="${href}" class="btn btn-secondary" style="font-size:12px;padding:4px 12px;">${cta}</a>` : ""}
    </li>`;

  const el = document.getElementById("setup-checklist");
  el.innerHTML = `
    <div class="setup-checklist-card">
      <div class="setup-checklist-title">
        <span>🚀 Get started with Takbo</span>
        <button class="setup-checklist-dismiss" onclick="dismissSetupChecklist()" title="Dismiss">&times;</button>
      </div>
      <ul class="setup-checklist-items">
        ${step(hasAssessment, "Complete your runner assessment",  "/onboarding.html", "Start")}
        ${step(hasGoal,       "Set a training goal",             "/training_plan.html", "Set goal")}
        ${step(hasProgram,    "Build your training program",     "/training_plan.html", "Build")}
        ${step(hasFirstRun,   "Log your first run",              null, "")}
      </ul>
    </div>`;
  el.classList.remove("hidden");
}

function dismissSetupChecklist() {
  localStorage.setItem("setup_checklist_dismissed", "1");
  document.getElementById("setup-checklist").classList.add("hidden");
}

// ── Weekly Recap ───────────────────────────────────────────────
function renderWeeklyRecap(runs, planData, gam) {
  const el = document.getElementById("weekly-recap");

  // Determine current week bounds (Mon–Sun)
  const now = new Date();
  const dayOfWeek = now.getDay(); // 0=Sun
  const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const monday = new Date(now);
  monday.setDate(now.getDate() + mondayOffset);
  monday.setHours(0, 0, 0, 0);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  sunday.setHours(23, 59, 59, 999);

  const weekRuns = runs.filter(r => {
    const d = new Date(r.date);
    return d >= monday && d <= sunday;
  });

  const weekKm    = weekRuns.reduce((s, r) => s + r.distance_km, 0);
  const weekCount = weekRuns.length;
  const streak    = gam ? gam.current_streak : 0;

  // Plan context: how many non-rest days are scheduled this week?
  let plannedDays = 0, plannedKm = 0, plannedWorkouts = [];
  const DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  if (planData?.plan?.days) {
    planData.plan.days.forEach(d => {
      if (!["Rest","Active Recovery"].includes(d.workout_type)) {
        plannedDays++;
        plannedKm += (d.distance_km || 0);
        plannedWorkouts.push(d.workout_type);
      }
    });
  }

  // Days remaining in the week (including today)
  const daysLeft = 7 - (dayOfWeek === 0 ? 6 : dayOfWeek - 1);

  // Progress ratio (capped at 1)
  const progress = plannedDays > 0 ? Math.min(weekCount / plannedDays, 1) : null;
  const kmProgress = plannedKm > 0 ? Math.min(weekKm / plannedKm, 1) : null;

  // Motivational message
  let emoji, headline, subline;
  if (weekCount === 0) {
    emoji = "💪"; headline = "Week is just getting started!";
    subline = daysLeft <= 2
      ? "Still time to get a run in — every kilometre counts."
      : "Your first run of the week sets the tone. Lace up!";
  } else if (progress !== null && progress >= 1) {
    emoji = "🔥"; headline = "You've hit your planned workouts — incredible!";
    subline = "Every session done. Rest up and come back stronger next week.";
  } else if (progress !== null && progress >= 0.6) {
    emoji = "⭐"; headline = "Strong week — keep the momentum going!";
    subline = `${weekCount} of ${plannedDays} planned runs done. ${daysLeft > 0 ? `${daysLeft} day${daysLeft !== 1 ? "s" : ""} left to finish strong.` : ""}`;
  } else if (streak >= 3) {
    emoji = "🔥"; headline = `${streak}-day streak — you're on fire!`;
    subline = "Consistency is your superpower. Keep showing up.";
  } else if (weekCount >= 2) {
    emoji = "📈"; headline = "Good momentum this week!";
    subline = `${weekKm.toFixed(1)} km logged so far. ${plannedKm > 0 ? `Target: ${plannedKm.toFixed(1)} km.` : "Keep building."}`;
  } else {
    emoji = "🌅"; headline = `${weekCount} run down this week — nice start!`;
    subline = "Every run builds the habit. One more this week would be great.";
  }

  // Progress bar percentage for km
  const barPct = kmProgress !== null ? Math.round(kmProgress * 100) : null;

  el.innerHTML = `
    <div class="weekly-recap-card">
      <div class="weekly-recap-header">
        <div>
          <div class="weekly-recap-eyebrow">This Week</div>
          <div class="weekly-recap-headline">${emoji} ${headline}</div>
          <div class="weekly-recap-sub">${subline}</div>
        </div>
      </div>
      <div class="weekly-recap-metrics">
        <div class="recap-metric">
          <div class="recap-metric-val">${weekCount}</div>
          <div class="recap-metric-lbl">Runs${plannedDays > 0 ? ` / ${plannedDays} planned` : ""}</div>
        </div>
        <div class="recap-metric">
          <div class="recap-metric-val">${weekKm.toFixed(1)}</div>
          <div class="recap-metric-lbl">km${plannedKm > 0 ? ` / ${plannedKm.toFixed(1)} target` : " this week"}</div>
        </div>
        ${streak > 0 ? `<div class="recap-metric">
          <div class="recap-metric-val">${streak}</div>
          <div class="recap-metric-lbl">day streak 🔥</div>
        </div>` : ""}
      </div>
      ${barPct !== null ? `
      <div class="recap-progress-wrap">
        <div class="recap-progress-bar" style="width:${barPct}%"></div>
      </div>
      <div style="font-size:11px;color:var(--text-sec);margin-top:4px;">${barPct}% of weekly km target</div>` : ""}
    </div>`;
  el.classList.remove("hidden");
}

function renderStats(progress, runs) {
  // Total runs
  document.getElementById("stat-total-runs").textContent = progress.stats.total_runs;

  // This week
  const weekKm = progress.weekly.km[progress.weekly.km.length - 1] || 0;
  document.getElementById("stat-week-km").textContent = weekKm.toFixed(1);

  // Runs this week — Monday-based to match the rest of the app
  const today = new Date();
  const dayOfWeek = today.getDay(); // 0=Sun
  const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const weekStart = new Date(today.getFullYear(), today.getMonth(), today.getDate() + mondayOffset);
  const weekRuns = runs.filter(r => new Date(r.date) >= weekStart).length;
  document.getElementById("stat-week-runs").textContent = weekRuns;

  // Avg pace last 7 runs
  const last7 = runs.slice(0, 7);
  if (last7.length) {
    const avg = last7.reduce((s, r) => s + r.pace_per_km, 0) / last7.length;
    document.getElementById("stat-avg-pace").textContent = formatPace(avg);
  } else {
    document.getElementById("stat-avg-pace").textContent = "—";
  }
}

function renderGoalBanner(goal, plan) {
  if (!goal) return;
  const banner = document.getElementById("goal-banner");
  banner.classList.remove("hidden");

  const raceDate = new Date(goal.race_date);
  const weeksLeft = Math.max(0, Math.round((raceDate - new Date()) / (7 * 24 * 60 * 60 * 1000)));

  document.getElementById("goal-title").textContent = `${goal.race_type} Goal`;
  let detail = goal.target_time_min
    ? `${weeksLeft} weeks away · Target: ${formatTargetTime(goal.target_time_min)}`
    : `${weeksLeft} weeks away · ${raceDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`;

  if (plan?.week_number && plan?.total_weeks) {
    detail += ` · Week ${plan.week_number} of ${plan.total_weeks}`;
  }
  document.getElementById("goal-detail").textContent = detail;
}

function badgeForType(type) {
  const t = (type || "").toLowerCase();
  if (t.includes("easy"))      return "badge-easy";
  if (t.includes("tempo"))     return "badge-tempo";
  if (t.includes("interval"))  return "badge-interval";
  if (t.includes("long"))      return "badge-long";
  if (t.includes("rest"))      return "badge-rest";
  if (t.includes("recovery"))  return "badge-rest";
  return "badge-easy";
}

function renderTodayWorkout(planData) {
  const el = document.getElementById("today-workout");
  if (!planData?.plan?.days) return;

  const DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  const todayName = DAY_NAMES[new Date().getDay()];
  const workout = planData.plan.days.find(d => d.day === todayName);
  if (!workout) return;

  const isRest = ["Rest","Active Recovery"].includes(workout.workout_type);
  const badgeClass = badgeForType(workout.workout_type || "Easy Run");

  const metrics = !isRest
    ? `<div class="today-workout-metrics">
         <div class="today-metric"><span class="today-metric-val">${workout.distance_km?.toFixed(1) || 0} km</span><span class="today-metric-lbl">Distance</span></div>
         <div class="today-metric"><span class="today-metric-val">${workout.duration_min || 0} min</span><span class="today-metric-lbl">Duration</span></div>
         <div class="today-metric"><span class="today-metric-val">${workout.intensity || "—"}</span><span class="today-metric-lbl">Intensity</span></div>
       </div>`
    : "";

  el.innerHTML = `
    <div class="today-workout-card">
      <div class="today-workout-top">
        <div>
          <div class="today-workout-eyebrow">Today · ${todayName}</div>
          <div class="today-workout-title">${workout.title}</div>
        </div>
        <span class="workout-type-badge ${badgeClass}">${workout.workout_type}</span>
      </div>
      <p class="today-workout-desc">${workout.description}</p>
      ${metrics}
      ${workout.notes ? `<p class="today-workout-notes">${workout.notes}</p>` : ""}
      ${!isRest
        ? `<div style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
             <button class="btn btn-primary" style="font-size:13px;padding:7px 16px;"
               onclick="openLogModal({distance_km:${workout.distance_km || ''}})">
               + Log this run
             </button>
             <a href="/training_plan.html" class="today-workout-link" style="margin:0;">View full week →</a>
           </div>`
        : `<a href="/training_plan.html" class="today-workout-link">View full week →</a>`
      }
    </div>`;
  el.classList.remove("hidden");
}

// Refresh dashboard run list after a run is logged via the quick modal
window._qlmOnRunLogged = async function () {
  try {
    const [runs, progress, gam] = await Promise.all([
      api.get("/runs/?limit=10"),
      api.get("/progress/"),
      api.get("/gamification/").catch(() => null),
    ]);
    renderStats(progress, runs);
    renderRuns(runs);
    if (gam) renderGamification(gam);
  } catch (_) {}
};

function isWithin7Days(dateStr) {
  const runDay    = dateStr.slice(0, 10); // "YYYY-MM-DD"
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
    _runsCache[updated.id] = updated;
    const card = document.getElementById(`run-card-${runId}`);
    if (card) {
      card.outerHTML = runCard(updated);
      document.getElementById(`run-card-${runId}`)?.classList.add("run-expanded");
      initRouteMaps([updated]);
    }
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "✨ Get Takbo Coach Feedback";
    alert(err.message || "Failed to generate feedback.");
  }
}

function formatTargetTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

// Cache of runs by id — avoids embedding large JSON in inline event attrs
const _runsCache = {};

function renderRuns(runs) {
  document.getElementById("runs-loading").classList.add("hidden");

  if (!runs || runs.length === 0) {
    document.getElementById("no-runs").classList.remove("hidden");
    return;
  }

  runs.forEach(r => { _runsCache[r.id] = r; });

  const list = document.getElementById("run-list");
  list.classList.remove("hidden");
  list.innerHTML = runs.map(run => runCard(run)).join("");
  initRouteMaps(runs);
}

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
    ? `<div class="run-item-map" id="map-${run.id}"></div>`
    : "";

  const withMap = run.route_polyline ? "run-item-with-route" : "";

  const actions = run.strava_activity_id ? "" : `
    <div class="run-actions">
      <button class="run-action-btn" onclick="event.stopPropagation();openEditModal('${run.id}')">Edit</button>
      <button class="run-action-btn run-action-danger" onclick="event.stopPropagation();confirmDelete('${run.id}')">Delete</button>
    </div>`;

  return `
    <div class="run-item ${withMap}" id="run-card-${run.id}" onclick="toggleRunExpand(this)" style="cursor:pointer;">
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
          ${actions}
        </div>
        ${run.notes ? `<p class="run-notes">${escapeHtml(run.notes)}</p>` : ""}
        <div class="run-expandable"><div>${expandContent}</div></div>
      </div>
      ${mapPanel}
    </div>
  `;
}

// ── Route maps ────────────────────────────────────────────────
const _routeMaps = {};

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
      const container = document.getElementById(`map-${run.id}`);
      if (!container || _routeMaps[run.id]) return;

      const coords = decodePolyline(run.route_polyline);
      if (coords.length < 2) return;

      const map = L.map(container, {
        zoomControl: false, attributionControl: false,
        dragging: false, scrollWheelZoom: false,
        touchZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(map);

      const line = L.polyline(coords, { color: "#F97316", weight: 3.5, opacity: 0.95 }).addTo(map);
      L.circleMarker(coords[0],               { radius: 6, color: "#fff", weight: 2, fillColor: "#22C55E", fillOpacity: 1 }).addTo(map);
      L.circleMarker(coords[coords.length-1], { radius: 6, color: "#fff", weight: 2, fillColor: "#EF4444", fillOpacity: 1 }).addTo(map);

      map.fitBounds(line.getBounds(), { padding: [14, 14] });
      _routeMaps[run.id] = map;
    });
  });
}


// ── Delete ────────────────────────────────────────────────────
async function confirmDelete(runId) {
  if (!confirm("Delete this run? This cannot be undone.")) return;
  try {
    await api.delete(`/runs/${runId}`);
    document.getElementById(`run-card-${runId}`)?.remove();
    // Show empty state if no runs left
    if (!document.querySelector(".run-item")) {
      document.getElementById("run-list").classList.add("hidden");
      document.getElementById("no-runs").classList.remove("hidden");
    }
  } catch (err) {
    alert(err.message || "Failed to delete run.");
  }
}

// ── Edit modal ────────────────────────────────────────────────
let _editingRunId = null;

function openEditModal(runId) {
  _editingRunId = runId;
  const run = _runsCache[runId];
  if (!run) return;

  // Populate fields
  _editDatePicker.setDate(run.date.split("T")[0], false);
  document.getElementById("edit-distance").value = run.distance_km;
  const totalMin = run.duration_min;
  document.getElementById("edit-dur-min").value  = Math.floor(totalMin);
  document.getElementById("edit-dur-sec").value  = Math.round((totalMin % 1) * 60);
  document.getElementById("edit-hr").value       = run.heart_rate_avg || "";
  document.getElementById("edit-effort").value   = run.effort_level;
  document.getElementById("edit-effort-display").textContent = run.effort_level;
  document.getElementById("edit-notes").value    = run.notes || "";

  document.getElementById("modal-alert").classList.add("hidden");
  document.getElementById("edit-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeEditModal(e) {
  if (e && e.target !== document.getElementById("edit-modal")) return;
  document.getElementById("edit-modal").classList.add("hidden");
  document.body.style.overflow = "";
  _editingRunId = null;
}

async function saveEdit() {
  const alertEl = document.getElementById("modal-alert");
  alertEl.classList.add("hidden");

  const dist    = parseFloat(document.getElementById("edit-distance").value);
  const durMin  = parseInt(document.getElementById("edit-dur-min").value) || 0;
  const durSec  = parseInt(document.getElementById("edit-dur-sec").value) || 0;
  const totalMin = durMin + durSec / 60;

  if (!dist || dist <= 0) { showModalAlert("Distance must be greater than 0."); return; }
  if (totalMin <= 0)      { showModalAlert("Duration must be greater than 0."); return; }

  const body = {
    date:         document.getElementById("edit-date").value + "T12:00:00",
    distance_km:  dist,
    duration_min: totalMin,
    effort_level: parseInt(document.getElementById("edit-effort").value),
    heart_rate_avg: parseInt(document.getElementById("edit-hr").value) || null,
    notes:        document.getElementById("edit-notes").value.trim() || null,
  };

  const btn = document.getElementById("edit-save-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";

  try {
    const updated = await api.put(`/runs/${_editingRunId}`, body);
    // Update cache and replace card in the DOM
    _runsCache[updated.id] = updated;
    const card = document.getElementById(`run-card-${_editingRunId}`);
    if (card) card.outerHTML = runCard(updated);
    closeEditModal();
  } catch (err) {
    showModalAlert(err.message || "Failed to save changes.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save changes";
  }
}

function showModalAlert(msg) {
  const el = document.getElementById("modal-alert");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function renderGamification(gam) {
  // Streak card
  const streakCard = document.getElementById("streak-stat-card");
  streakCard.style.display = "";
  document.getElementById("stat-streak").textContent = gam.current_streak;

  // Level + XP card
  const levelCard = document.getElementById("level-stat-card");
  levelCard.style.display = "";
  document.getElementById("stat-level").textContent = gam.level;

  const xpInLevel = gam.total_xp - gam.xp_for_current_level;
  const xpRange   = gam.xp_for_next_level - gam.xp_for_current_level;
  const pct = xpRange > 0 ? Math.min(100, (xpInLevel / xpRange) * 100) : 100;
  document.getElementById("stat-xp-bar").style.width = `${pct}%`;
  document.getElementById("stat-xp-text").textContent = `${gam.total_xp} XP`;
}

function checkNewAchievements(achievements) {
  const seen = JSON.parse(localStorage.getItem("seen_achievements") || "[]");
  const newOnes = achievements.filter(a => !seen.includes(a.achievement_key));
  if (newOnes.length === 0) return;

  // Mark all as seen
  const allKeys = achievements.map(a => a.achievement_key);
  localStorage.setItem("seen_achievements", JSON.stringify(allKeys));

  // Show toasts
  newOnes.forEach((a, i) => {
    setTimeout(() => showAchievementToast(a), i * 800);
  });
}

function showAchievementToast(a) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast-achievement";
  toast.innerHTML = `
    <div class="toast-icon">${a.icon}</div>
    <div class="toast-body">
      <div class="toast-title">Achievement Unlocked!</div>
      <div class="toast-name">${a.title}</div>
      <div class="toast-desc">${a.description}</div>
    </div>
    <button class="toast-close" onclick="this.parentElement.remove()">×</button>
  `;
  container.appendChild(toast);
  // Auto-remove after 6 seconds
  setTimeout(() => toast.remove(), 6000);
}

function toggleRunExpand(card) {
  card.classList.toggle("run-expanded");
}

function toggleFeedback(btn) {
  const content = btn.nextElementSibling;
  const isOpen = content.classList.toggle("open");
  btn.textContent = (isOpen ? "▼ Hide" : "▶ Show") + " coach feedback";
}

function renderMarkdown(text) {
  // Simple markdown renderer for headings and paragraphs
  return text
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 style="font-size:13px;color:var(--text);margin:8px 0 4px;">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[h])(.+)$/gm, (m) => m.startsWith('<') ? m : `<p>${m}</p>`)
    .replace(/<p><\/p>/g, '');
}
