let currentGoalId = null;
let currentPlanId = null;    // ID of the currently loaded plan
let currentPlanData = null;  // Full plan response object
let weekRunsMap = {};        // date-string → run object for this plan's week
let weekRunsById = {};       // run.id → run object (safe onclick lookup)

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  await loadGoal();
  await loadPlan();
});

async function loadGoal() {
  try {
    const goal = await api.get("/goals/");
    if (goal) {
      renderGoal(goal);
    }
  } catch (err) {
    console.error("Failed to load goal:", err);
  }
}

function renderGoal(goal) {
  currentGoalId = goal.id;
  const raceDate = new Date(goal.race_date);
  const weeksLeft = Math.max(0, Math.round((raceDate - new Date()) / (7 * 24 * 60 * 60 * 1000)));
  const dateStr = raceDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  const targetStr = goal.target_time_min ? ` · Target: ${formatTargetTime(goal.target_time_min)}` : "";

  document.getElementById("goal-info").innerHTML =
    `<strong style="color:var(--text);font-size:15px;">${goal.race_type}</strong><br>
     ${dateStr}<br>
     <span style="color:var(--accent);">${weeksLeft} weeks to go</span>${targetStr}`;

  document.getElementById("goal-display").classList.remove("hidden");
  document.getElementById("goal-form").classList.add("hidden");
}

function formatTargetTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

async function saveGoal() {
  const raceType = document.getElementById("race-type").value;
  const raceDate = document.getElementById("race-date").value;
  const targetRaw = document.getElementById("target-time").value.trim();

  if (!raceType) { alert("Please select a race type"); return; }
  if (!raceDate) { alert("Please select a race date"); return; }

  const body = {
    race_type: raceType,
    race_date: new Date(raceDate).toISOString(),
  };

  if (targetRaw) {
    const minutes = parseTimeToMinutes(targetRaw);
    if (minutes) body.target_time_min = minutes;
  }

  try {
    const goal = await api.post("/goals/", body);
    renderGoal(goal);
  } catch (err) {
    alert(err.message || "Failed to save goal");
  }
}

function parseTimeToMinutes(str) {
  const parts = str.split(":").map(Number);
  if (parts.length === 2) return parts[0] + parts[1] / 60;         // MM:SS
  if (parts.length === 3) return parts[0] * 60 + parts[1] + parts[2] / 60; // H:MM:SS
  return null;
}

async function deleteGoal() {
  if (!currentGoalId) return;
  if (!confirm("Remove your current goal?")) return;
  try {
    await api.delete(`/goals/${currentGoalId}`);
    currentGoalId = null;
    document.getElementById("goal-display").classList.add("hidden");
    document.getElementById("goal-form").classList.remove("hidden");
    document.getElementById("goal-info").innerHTML = "";
  } catch (err) {
    alert(err.message || "Failed to remove goal");
  }
}

async function loadPlan() {
  try {
    const data = await api.get("/plans/current");
    if (data) {
      currentPlanId = data.id;
      currentPlanData = data;
      await loadWeekRuns(data.week_start);
      renderPlan(data);
    }
  } catch (err) {
    console.error("Failed to load plan:", err);
  }
}

// Parse "YYYY-MM-DD..." as a local-date number (days since epoch) to avoid UTC shift
function dateStrToLocalKey(dateStr) {
  return dateStr.slice(0, 10); // just keep "YYYY-MM-DD"
}

function addDaysToDateKey(dateKey, days) {
  const [y, m, d] = dateKey.split("-").map(Number);
  const dt = new Date(y, m - 1, d + days);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

async function loadWeekRuns(weekStart) {
  try {
    // Fetch recent runs — enough to cover this week's 7 days
    const runs = await api.get("/runs/?limit=14");
    weekRunsMap = {};
    if (!runs || !runs.length) return;

    // Use the date portion only to avoid UTC/local timezone mismatch
    const mondayKey = dateStrToLocalKey(weekStart);
    const sundayKey = addDaysToDateKey(mondayKey, 6);

    for (const run of runs) {
      const key = dateStrToLocalKey(run.date);
      if (key >= mondayKey && key <= sundayKey) {
        weekRunsMap[key] = run;
        weekRunsById[run.id] = run;
      }
    }
  } catch (err) {
    console.error("Failed to load week runs:", err);
  }
}

async function generatePlan() {
  const btn = document.getElementById("generate-btn");
  btn.disabled = true;
  btn.textContent = "Generating…";

  document.getElementById("plan-loading").classList.remove("hidden");
  document.getElementById("plan-container").classList.add("hidden");
  document.getElementById("alert").classList.add("hidden");

  try {
    const data = await api.post("/plans/generate", {});
    currentPlanId = data.id;
    currentPlanData = data;
    await loadWeekRuns(data.week_start);
    renderPlan(data);
  } catch (err) {
    const alertEl = document.getElementById("alert");
    alertEl.textContent = err.message || "Failed to generate plan";
    alertEl.classList.remove("hidden");
  } finally {
    document.getElementById("plan-loading").classList.add("hidden");
    btn.disabled = false;
    btn.textContent = "✨ Generate New Plan";
  }
}

function renderPlan(data) {
  const plan = data.plan;
  if (!plan || !plan.days) return;

  // Meta
  const generatedAt = new Date(data.generated_at);
  const weekStart   = new Date(data.week_start);
  document.getElementById("plan-meta").innerHTML =
    `<strong>Week of:</strong> ${weekStart.toLocaleDateString("en-US", { month: "long", day: "numeric" })}<br>
     <strong>Generated:</strong> ${generatedAt.toLocaleDateString("en-US", { month: "short", day: "numeric" })}<br>
     <strong>Total volume:</strong> ${plan.total_km?.toFixed(1) || 0} km`;

  // Summary
  const summaryEl = document.getElementById("plan-summary");
  summaryEl.innerHTML =
    `<h3>${plan.focus || "Training Week"}</h3>
     <p>${plan.week_summary || ""}</p>`;

  // Days grid — match each plan day to a logged run this week
  const DAY_OFFSET = { Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3, Friday: 4, Saturday: 5, Sunday: 6 };
  const mondayKey = dateStrToLocalKey(data.week_start);

  const grid = document.getElementById("plan-grid");
  grid.innerHTML = plan.days.map(day => {
    const offset = DAY_OFFSET[day.day] ?? 0;
    const dateKey = addDaysToDateKey(mondayKey, offset);
    const matchedRun = weekRunsMap[dateKey] || null;
    return workoutCard(day, matchedRun);
  }).join("");

  document.getElementById("plan-container").classList.remove("hidden");
  document.getElementById("plan-loading").classList.add("hidden");
}

function workoutCard(day, run) {
  const type = day.workout_type || "Easy Run";
  const badgeClass = badgeForType(type);
  const isRest = ["Rest", "Active Recovery"].includes(type);

  const metricsHtml = !isRest
    ? `<div class="workout-metrics">
         <div class="workout-metric"><strong>${day.distance_km?.toFixed(1) || 0} km</strong></div>
         <div class="workout-metric"><strong>${day.duration_min || 0} min</strong></div>
         <div class="workout-metric">${day.intensity}</div>
       </div>`
    : `<div class="workout-metrics"><div class="workout-metric" style="color:var(--text-sec);">Rest &amp; recover</div></div>`;

  const completedBanner = run
    ? `<div class="workout-completed-banner">
         <span class="workout-completed-msg">✅ ${day.day} session done!</span>
         <span class="workout-completed-link">View details →</span>
       </div>`
    : "";

  const rescheduledBanner = day.rescheduled_from
    ? `<div class="workout-rescheduled-banner">
         📅 Rescheduled from ${escapeHtml(day.rescheduled_from)}${day.reschedule_note ? ` — ${escapeHtml(day.reschedule_note)}` : ""}
       </div>`
    : "";

  const rescheduleBtn = !run && currentPlanId
    ? `<div class="workout-card-footer">
         <button class="btn-reschedule" onclick="event.stopPropagation();openRescheduleModal('${day.day}')">📅 Reschedule</button>
       </div>`
    : "";

  const clickAttr = run ? `onclick="openRunDetailById('${run.id}')"` : "";
  const cardClass = `workout-card${run ? " completed" : ""}${day.rescheduled_from ? " rescheduled" : ""}`;

  return `
    <div class="${cardClass}" ${clickAttr}>
      <div class="workout-header">
        <span class="workout-day">${day.day}</span>
        <span class="workout-type-badge ${badgeClass}">${type}</span>
      </div>
      <div class="workout-body">
        <div class="workout-title">${day.title}</div>
        <div class="workout-desc">${day.description}</div>
        ${metricsHtml}
        ${day.notes ? `<div class="workout-notes">${day.notes}</div>` : ""}
        ${rescheduledBanner}
        ${completedBanner}
      </div>
      ${rescheduleBtn}
    </div>
  `;
}

// ── Run detail modal ──────────────────────────────────────────
function openRunDetailById(id) {
  const run = weekRunsById[id];
  if (run) openRunDetail(run);
}

function openRunDetail(run) {

  const pace = run.pace_per_km;
  const paceMin = Math.floor(pace);
  const paceSec = Math.round((pace - paceMin) * 60).toString().padStart(2, "0");

  const duration = run.duration_min;
  const durH = Math.floor(duration / 60);
  const durM = Math.round(duration % 60);
  const durStr = durH > 0 ? `${durH}h ${durM}m` : `${durM} min`;

  const dateStr = new Date(run.date).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

  const hrStat = run.heart_rate_avg
    ? `<div class="run-detail-stat">
         <div class="run-detail-stat-label">Avg Heart Rate</div>
         <div class="run-detail-stat-value">${run.heart_rate_avg}<span class="run-detail-stat-unit">bpm</span></div>
       </div>`
    : "";

  const notesStat = run.notes
    ? `<div style="margin-bottom:16px;">
         <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-sec);margin-bottom:6px;">Your Notes</div>
         <div style="font-size:13px;color:var(--text);line-height:1.6;font-style:italic;">${escapeHtml(run.notes)}</div>
       </div>`
    : "";

  const feedbackHtml = run.ai_feedback
    ? `<div class="ai-feedback-box">
         <div class="ai-feedback-label">🤖 Coach Feedback</div>
         <div class="ai-feedback-text">${escapeHtml(run.ai_feedback)}</div>
       </div>`
    : `<div style="color:var(--text-sec);font-size:13px;">No AI feedback available for this run.</div>`;

  document.getElementById("run-detail-date").textContent = dateStr;
  document.getElementById("run-detail-body").innerHTML = `
    <div class="run-detail-grid">
      <div class="run-detail-stat">
        <div class="run-detail-stat-label">Distance</div>
        <div class="run-detail-stat-value">${run.distance_km.toFixed(2)}<span class="run-detail-stat-unit">km</span></div>
      </div>
      <div class="run-detail-stat">
        <div class="run-detail-stat-label">Duration</div>
        <div class="run-detail-stat-value">${durStr}</div>
      </div>
      <div class="run-detail-stat">
        <div class="run-detail-stat-label">Avg Pace</div>
        <div class="run-detail-stat-value">${paceMin}:${paceSec}<span class="run-detail-stat-unit">/km</span></div>
      </div>
      <div class="run-detail-stat">
        <div class="run-detail-stat-label">Effort</div>
        <div class="run-detail-stat-value">${run.effort_level}<span class="run-detail-stat-unit">/ 10</span></div>
      </div>
      ${hrStat}
    </div>
    ${notesStat}
    ${feedbackHtml}
  `;

  document.getElementById("run-detail-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeRunDetailModal(e) {
  if (e && e.target !== document.getElementById("run-detail-modal")) return;
  document.getElementById("run-detail-modal").classList.add("hidden");
  document.body.style.overflow = "";
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Recalibrate modal ─────────────────────────────────────────
function openRecalibrateModal() {
  document.getElementById("recalibrate-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeRecalibrateModal(e) {
  if (e && e.target !== document.getElementById("recalibrate-modal")) return;
  document.getElementById("recalibrate-modal").classList.add("hidden");
  document.body.style.overflow = "";
}

async function recalibratePlan() {
  const confirmBtn = document.getElementById("recalibrate-confirm-btn");
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<span class="btn-spinner"></span> Recalibrating…';

  const recalibrateBtn = document.getElementById("recalibrate-btn");
  recalibrateBtn.disabled = true;

  document.getElementById("recalibrate-modal").classList.add("hidden");
  document.body.style.overflow = "";
  document.getElementById("plan-loading").classList.remove("hidden");
  document.getElementById("plan-container").classList.add("hidden");
  document.getElementById("alert").classList.add("hidden");

  try {
    const data = await api.post("/plans/recalibrate", {});
    currentPlanId = data.id;
    currentPlanData = data;
    await loadWeekRuns(data.week_start);
    renderPlan(data);
  } catch (err) {
    const alertEl = document.getElementById("alert");
    alertEl.textContent = err.message || "Failed to recalibrate plan. Please try again.";
    alertEl.classList.remove("hidden");
  } finally {
    document.getElementById("plan-loading").classList.add("hidden");
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Recalibrate plan";
    recalibrateBtn.disabled = false;
  }
}

// ── Reschedule modal ─────────────────────────────────────────
let _rescheduleSourceDay = null;

function openRescheduleModal(sourceDay) {
  if (!currentPlanId || !currentPlanData) return;
  _rescheduleSourceDay = sourceDay;
  document.getElementById("reschedule-source-label").textContent = sourceDay;

  const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const DAY_OFFSET = { Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3, Friday: 4, Saturday: 5, Sunday: 6 };
  const mondayKey = dateStrToLocalKey(currentPlanData.week_start);

  const select = document.getElementById("reschedule-target-day");
  const options = DAY_NAMES.filter(d => {
    if (d === sourceDay) return false;
    const dateKey = addDaysToDateKey(mondayKey, DAY_OFFSET[d]);
    return !weekRunsMap[dateKey]; // exclude days with a logged run
  });
  select.innerHTML = options.map(d => `<option value="${d}">${d}</option>`).join("");

  document.getElementById("reschedule-note").value = "";
  document.getElementById("reschedule-error").classList.add("hidden");
  document.getElementById("reschedule-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeRescheduleModal(e) {
  if (e && e.target !== document.getElementById("reschedule-modal")) return;
  document.getElementById("reschedule-modal").classList.add("hidden");
  document.body.style.overflow = "";
  _rescheduleSourceDay = null;
}

async function confirmReschedule() {
  if (!currentPlanId || !_rescheduleSourceDay) return;
  const targetDay = document.getElementById("reschedule-target-day").value;
  const note = document.getElementById("reschedule-note").value.trim();
  const confirmBtn = document.getElementById("reschedule-confirm-btn");
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<span class="btn-spinner"></span> Saving…';
  document.getElementById("reschedule-error").classList.add("hidden");

  try {
    const data = await api.patch(`/plans/${currentPlanId}`, {
      source_day: _rescheduleSourceDay,
      target_day: targetDay,
      note: note || null,
    });
    currentPlanData = data;
    document.getElementById("reschedule-modal").classList.add("hidden");
    document.body.style.overflow = "";
    _rescheduleSourceDay = null;
    renderPlan(data);
  } catch (err) {
    const errorEl = document.getElementById("reschedule-error");
    errorEl.textContent = err.message || "Failed to reschedule. Please try again.";
    errorEl.classList.remove("hidden");
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Confirm swap";
  }
}

function badgeForType(type) {
  const t = type.toLowerCase();
  if (t.includes("easy"))     return "badge-easy";
  if (t.includes("tempo"))    return "badge-tempo";
  if (t.includes("interval")) return "badge-interval";
  if (t.includes("long"))     return "badge-long";
  if (t.includes("cross"))    return "badge-cross";
  if (t.includes("active"))   return "badge-recovery";
  if (t.includes("rest"))     return "badge-rest";
  return "badge-easy";
}
