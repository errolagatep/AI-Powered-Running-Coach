let currentGoalId = null;
let currentGoalData = null;  // Full goal object (needed for program modal)
let currentPlanId = null;    // ID of the currently loaded plan
let currentPlanData = null;  // Full plan response object
let currentProgram = null;   // Active training program object
let weekRunsMap = {};        // date-string → run object for this plan's week
let weekRunsById = {};       // run.id → run object (safe onclick lookup)
let viewingWeekNumber = null; // Week number the user is currently viewing (null = current week)
let _isPastWeekView = false;  // True when viewing a past week (disables action buttons)

// ── Header button state ───────────────────────────────────────
// Single primary CTA changes meaning based on state:
//   Nothing         → "Generate This Week's Plan"  (calls generatePlan)
//   Program active  → "Generate Week N"            (calls generateNextWeek / generatePlan)
//   Standalone plan → "Start a Training Program"   (calls openProgramModal)
// Overflow menu appears whenever a plan or program exists.
function updateHeaderButtons() {
  const primaryBtn  = document.getElementById("plan-primary-btn");
  const overflowWrap = document.getElementById("plan-overflow-wrap");
  const overflowProg = document.getElementById("overflow-program");

  if (currentProgram) {
    // In a program — primary action is generating the next week
    primaryBtn.innerHTML = `${Icons.calendar} Build Full Program`;
    primaryBtn.classList.remove("btn-primary");
    primaryBtn.classList.add("btn-secondary");
    overflowWrap.classList.remove("hidden");
    overflowProg.innerHTML = `${Icons.calendar} New Program`;
    // Disable overflow rebuild if viewing a past week
    document.getElementById("overflow-recalibrate").disabled = _isPastWeekView;
  } else if (currentPlanData) {
    // Standalone plan — nudge toward building a full program
    primaryBtn.innerHTML = `${Icons.calendar} Start a Training Program`;
    primaryBtn.classList.remove("btn-secondary");
    primaryBtn.classList.add("btn-primary");
    overflowWrap.classList.remove("hidden");
    overflowProg.innerHTML = `${Icons.calendar} Build Full Program`;
    document.getElementById("overflow-recalibrate").disabled = false;
  } else {
    // Nothing yet — primary action: generate a quick plan for this week
    primaryBtn.innerHTML = `${Icons.sparkles} Generate This Week's Plan`;
    primaryBtn.classList.remove("btn-secondary");
    primaryBtn.classList.add("btn-primary");
    overflowWrap.classList.add("hidden");
  }
}

function handlePrimaryAction() {
  if (currentProgram) {
    openProgramModal();
  } else if (currentPlanData) {
    openProgramModal();
  } else {
    generatePlan();
  }
}

function togglePlanOverflow(e) {
  e.stopPropagation();
  document.getElementById("plan-overflow-dropdown").classList.toggle("open");
}
function closePlanOverflow() {
  document.getElementById("plan-overflow-dropdown").classList.remove("open");
}
// Close dropdown when clicking elsewhere
document.addEventListener("click", () => closePlanOverflow());

function dismissGoalChangedBanner() {
  document.getElementById("goal-changed-banner").classList.add("hidden");
}

// Returns the local Monday date as "YYYY-MM-DD" (avoids UTC off-by-one for UTC+ users)
function getLocalMondayISO() {
  const now = new Date();
  const day = now.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
  const diffToMonday = (day === 0) ? -6 : 1 - day;
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diffToMonday);
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
}

let _activeGoalCategory = "race"; // "race" | "fitness" | "weight_loss" | "endurance"

function setGoalCategory(cat) {
  _activeGoalCategory = cat;
  document.querySelectorAll(".goal-type-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.category === cat);
  });
  const isRace = cat === "race";
  document.getElementById("goal-race-fields").classList.toggle("hidden", !isRace);
  document.getElementById("goal-nonrace-fields").classList.toggle("hidden", isRace);
  document.getElementById("goal-weight-group").classList.toggle("hidden", cat !== "weight_loss");
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  lucide.createIcons();

  flatpickr("#race-date", {
    minDate: "today",
    dateFormat: "Y-m-d",
    disableMobile: true,
    allowInput: false,
  });

  flatpickr("#goal-target-date", {
    minDate: "today",
    dateFormat: "Y-m-d",
    disableMobile: true,
    allowInput: false,
  });

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
  currentGoalData = goal;
  const raceDate = new Date(goal.race_date);
  const weeksLeft = Math.max(0, Math.round((raceDate - new Date()) / (7 * 24 * 60 * 60 * 1000)));
  const dateStr = raceDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  const targetStr = goal.target_time_min ? ` · Target: ${formatTargetTime(goal.target_time_min)}` : "";
  const isRace = !goal.goal_type || goal.goal_type === "race";
  const dateLabel = isRace ? "Race date" : "Target date";

  const goalInfo = document.getElementById("goal-info");
  goalInfo.innerHTML =
    `<strong style="color:var(--text);font-size:15px;">${goal.race_type}</strong><br>
     ${dateLabel}: ${dateStr}<br>
     <span style="color:var(--accent);">${weeksLeft} weeks to go</span>${targetStr}
     ${goal.goal_description ? `<br><span style="font-size:12px;color:var(--text-sec);">${escapeHtml(goal.goal_description)}</span>` : ""}`;
  goalInfo.dataset.raceDate = goal.race_date;

  document.getElementById("goal-display").classList.remove("hidden");
  document.getElementById("goal-form").classList.add("hidden");
}

function formatTargetTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

async function saveGoal() {
  const cat = _activeGoalCategory;

  if (cat === "race") {
    const raceType = document.getElementById("race-type").value;
    const raceDate = document.getElementById("race-date").value;
    if (!raceType) { alert("Please select a race distance"); return; }
    if (!raceDate) { alert("Please select a race date"); return; }

    const body = {
      race_type: raceType,
      race_date: raceDate + "T12:00:00",
      goal_type: "race",
    };
    const targetRaw = document.getElementById("target-time").value.trim();
    if (targetRaw) {
      const minutes = parseTimeToMinutes(targetRaw);
      if (minutes) body.target_time_min = minutes;
    }
    return _submitGoal(body);
  }

  // Non-race goals
  const targetDate = document.getElementById("goal-target-date").value;
  if (!targetDate) { alert("Please select a target date"); return; }

  const goalTypeMap = {
    fitness:     { race_type: "General Fitness",   goal_type: "fitness"     },
    weight_loss: { race_type: "Weight Loss",        goal_type: "weight_loss" },
    endurance:   { race_type: "Endurance Building", goal_type: "endurance"   },
  };
  const meta = goalTypeMap[cat];

  const body = {
    race_type: meta.race_type,
    race_date: targetDate + "T12:00:00",
    goal_type: meta.goal_type,
  };

  const desc = document.getElementById("goal-description").value.trim();
  if (desc) body.goal_description = desc;

  if (cat === "weight_loss") {
    const tw = parseFloat(document.getElementById("goal-target-weight").value);
    if (tw > 0) body.target_weight_kg = tw;
  }

  return _submitGoal(body);
}

async function _submitGoal(body) {
  try {
    const goal = await api.post("/goals/", body);
    renderGoal(goal);
    if (currentProgram) {
      document.getElementById("goal-changed-banner").classList.remove("hidden");
    }
  } catch (err) {
    alert(err.message || "Failed to save goal");
  }
}

// isPace=true → always treat 2-part as MM:SS (e.g. "5:30" = 5.5 min/km)
// isPace=false (default, race target time) → 2-part treated as H:MM when first
//   part is 1–9 (e.g. "3:30" → 210 min), else MM:SS (e.g. "45:00" → 45 min)
function parseTimeToMinutes(str, isPace = false) {
  const parts = str.split(":").map(Number);
  if (parts.some(isNaN)) return null;
  if (parts.length === 3) return parts[0] * 60 + parts[1] + parts[2] / 60; // H:MM:SS
  if (parts.length === 2) {
    if (isPace) return parts[0] + parts[1] / 60; // always MM:SS for pace
    if (parts[0] >= 1 && parts[0] <= 9) return parts[0] * 60 + parts[1]; // H:MM for race time
    return parts[0] + parts[1] / 60; // MM:SS for short race times (e.g. "45:00")
  }
  return null;
}

async function deleteGoal() {
  if (!currentGoalId) return;
  if (!confirm("Remove your current goal?")) return;
  try {
    await api.delete(`/goals/${currentGoalId}`);

    // Clear all goal state
    currentGoalId = null;
    currentGoalData = null;
    document.getElementById("goal-display").classList.add("hidden");
    document.getElementById("goal-form").classList.remove("hidden");
    document.getElementById("goal-info").innerHTML = "";

    // Clear all plan and program state
    currentPlanId = null;
    currentPlanData = null;
    currentProgram = null;
    viewingWeekNumber = null;
    _isPastWeekView = false;
    weekRunsMap = {};
    weekRunsById = {};

    // Hide all plan UI sections
    document.getElementById("plan-container").classList.add("hidden");
    document.getElementById("program-banner").classList.add("hidden");
    document.getElementById("next-week-banner").classList.add("hidden");
    document.getElementById("week-navigator").classList.add("hidden");
    document.getElementById("goal-changed-banner").classList.add("hidden");
    document.getElementById("alert").classList.add("hidden");

    // Reset plan info card
    document.getElementById("plan-meta").innerHTML =
      "No plan yet. Build a full program for a structured training block, or generate a quick plan for this week.";

    updateHeaderButtons();
  } catch (err) {
    alert(err.message || "Failed to remove goal");
  }
}

async function loadPlan() {
  try {
    const [data, program] = await Promise.all([
      api.get("/plans/current"),
      api.get("/plans/program/active").catch(() => null),
    ]);
    currentProgram = program;

    // Only show a plan if it's a standalone plan (no program_id)
    // or if its program is still active. A plan linked to an abandoned
    // program (e.g. after goal deletion) should not be shown.
    const planBelongsToActiveProgram = data?.program_id && program;
    const planIsStandalone = data && !data.program_id;

    if (planBelongsToActiveProgram || planIsStandalone) {
      currentPlanId = data.id;
      currentPlanData = data;
      await loadWeekRuns(data.week_start);
      renderPlan(data);
    }
    if (program) {
      renderProgramBanner(program, data);
      checkNextWeekPrompt(program, data);
      updateWeekNavigator();
    } else {
      document.getElementById("program-banner").classList.add("hidden");
      document.getElementById("next-week-banner").classList.add("hidden");
      document.getElementById("week-navigator").classList.add("hidden");
    }
    updateHeaderButtons();
  } catch (err) {
    console.error("Failed to load plan:", err);
  }
}

// Refresh plan day status markers after a run is logged via the quick modal
window._qlmOnRunLogged = async function (run) {
  if (currentPlanData?.week_start) {
    await loadWeekRuns(currentPlanData.week_start);
    renderPlan(currentPlanData);
  }
};

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
    const runs = await api.get("/runs/?limit=50");
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
  const btn = document.getElementById("plan-primary-btn");
  btn.disabled = true;
  btn.textContent = "Generating…";

  document.getElementById("plan-loading").classList.remove("hidden");
  document.getElementById("plan-container").classList.add("hidden");
  document.getElementById("alert").classList.add("hidden");

  try {
    const localMonday = getLocalMondayISO();
    const data = await api.post(`/plans/generate?local_monday=${localMonday}`, {});
    currentPlanId = data.id;
    currentPlanData = data;
    viewingWeekNumber = null;
    _isPastWeekView = false;
    await loadWeekRuns(data.week_start);
    renderPlan(data);
    updateHeaderButtons();
  } catch (err) {
    const alertEl = document.getElementById("alert");
    alertEl.textContent = err.message || "Failed to generate plan";
    alertEl.classList.remove("hidden");
  } finally {
    document.getElementById("plan-loading").classList.add("hidden");
    btn.disabled = false;
    updateHeaderButtons(); // restore correct label after any state
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
  lucide.createIcons();
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
         <span class="workout-completed-msg">${Icons.checkCircle} ${day.day} session done!</span>
         <span class="workout-completed-link">View details →</span>
       </div>`
    : "";

  const rescheduledBanner = day.rescheduled_from
    ? `<div class="workout-rescheduled-banner">
         ${Icons.calendar} Rescheduled from ${escapeHtml(day.rescheduled_from)}${day.reschedule_note ? ` — ${escapeHtml(day.reschedule_note)}` : ""}
       </div>`
    : "";

  const variationBadge = day.is_variation
    ? `<span class="workout-variation-badge">${Icons.shuffle} Varied</span>`
    : "";

  // Footer buttons: reschedule always shown for incomplete days in current week; hidden for past weeks
  let footerHtml = "";
  if (!run && currentPlanId && !_isPastWeekView) {
    const rescheduleBtn = `<button class="btn-reschedule" onclick="event.stopPropagation();openRescheduleModal('${day.day}')">${Icons.calendar} Reschedule</button>`;
    const varyBtn = !isRest
      ? `<button class="btn-vary" onclick="event.stopPropagation();varyWorkout('${day.day}')">${Icons.shuffle} Vary workout</button>`
      : "";
    footerHtml = `<div class="workout-card-footer">${rescheduleBtn}${varyBtn}</div>`;
  }

  const clickAttr = run ? `onclick="openRunDetailById('${run.id}')"` : "";
  const cardClass = [
    "workout-card",
    run ? "completed" : "",
    day.rescheduled_from ? "rescheduled" : "",
    day.is_variation && !run ? "varied" : "",
  ].filter(Boolean).join(" ");

  return `
    <div class="${cardClass}" ${clickAttr}>
      <div class="workout-header">
        <span class="workout-day">${day.day}</span>
        <div style="display:flex;align-items:center;gap:6px;">
          ${variationBadge}
          <span class="workout-type-badge ${badgeClass}">${type}</span>
        </div>
      </div>
      <div class="workout-body">
        <div class="workout-title">${day.title}</div>
        <div class="workout-desc">${day.description}</div>
        ${metricsHtml}
        ${day.notes ? `<div class="workout-notes">${day.notes}</div>` : ""}
        ${rescheduledBanner}
        ${completedBanner}
      </div>
      ${footerHtml}
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
         <div class="ai-feedback-label">${Icons.runner} Takbo Coach Feedback</div>
         <div class="ai-feedback-text">${renderMarkdown(run.ai_feedback)}</div>
       </div>`
    : `<div style="color:var(--text-sec);font-size:13px;">No coaching feedback available for this run.</div>`;

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

function renderMarkdown(text) {
  return text
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 style="font-size:13px;color:var(--text);margin:8px 0 4px;">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(?!<)(.+)/gm, (m) => `<p>${m}</p>`)
    .replace(/<p><\/p>/g, '');
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

  const recalibrateBtn = document.getElementById("overflow-recalibrate");
  if (recalibrateBtn) recalibrateBtn.disabled = true;

  document.getElementById("recalibrate-modal").classList.add("hidden");
  document.body.style.overflow = "";
  document.getElementById("plan-loading").classList.remove("hidden");
  document.getElementById("plan-container").classList.add("hidden");
  document.getElementById("alert").classList.add("hidden");

  try {
    const localMonday = getLocalMondayISO();
    const data = await api.post(`/plans/recalibrate?local_monday=${localMonday}`, {});
    currentPlanId = data.id;
    currentPlanData = data;
    viewingWeekNumber = null;
    _isPastWeekView = false;
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
    if (recalibrateBtn) recalibrateBtn.disabled = false;
    updateHeaderButtons();
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

// ── Vary workout ──────────────────────────────────────────────
async function varyWorkout(dayName) {
  if (!currentPlanId) return;

  // Find the card and put it into a loading state
  let targetCard = null;
  for (const card of document.querySelectorAll(".workout-card")) {
    if (card.querySelector(".workout-day")?.textContent === dayName) {
      targetCard = card;
      break;
    }
  }
  if (targetCard) {
    targetCard.classList.add("varying");
    const footer = targetCard.querySelector(".workout-card-footer");
    if (footer) {
      footer.innerHTML = `<span class="vary-loading-text"><span class="btn-spinner"></span> Generating variation…</span>`;
    }
  }

  try {
    const data = await api.post(`/plans/${currentPlanId}/vary/${dayName}`, {});
    currentPlanData = data;
    renderPlan(data);
  } catch (err) {
    alert(err.message || "Failed to generate variation. Please try again.");
    renderPlan(currentPlanData);
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

// ── Training Program ──────────────────────────────────────────

function renderProgramBanner(program, planData) {
  if (!program) return;
  const weekNum = planData?.week_number ?? null;
  const totalWeeks = program.total_weeks;

  const endDate = new Date(program.end_date + "T00:00:00");
  const now = new Date();
  const daysLeft = Math.max(0, Math.round((endDate - now) / (1000 * 60 * 60 * 24)));
  const weeksLeft = Math.ceil(daysLeft / 7);

  const skeletonWeek = weekNum ? program.skeleton.find(w => w.week_number === weekNum) : null;
  const phase = skeletonWeek?.phase ?? "";

  const pct = weekNum ? Math.round((weekNum / totalWeeks) * 100) : 0;

  document.getElementById("program-week-label").textContent =
    weekNum ? `Week ${weekNum} of ${totalWeeks}` : `${totalWeeks}-Week Program`;
  document.getElementById("program-phase-label").textContent = phase ? `Phase: ${phase}` : "";
  document.getElementById("program-countdown").textContent =
    weeksLeft > 1 ? `${weeksLeft} weeks (${daysLeft} days)` : `${daysLeft} day${daysLeft !== 1 ? "s" : ""}`;
  document.getElementById("program-progress-bar").style.width = `${pct}%`;
  document.getElementById("program-progress-label").textContent =
    weekNum ? `${pct}% of program complete` : "Program active — generate Week 1 to begin";

  document.getElementById("program-banner").classList.remove("hidden");
}

function checkNextWeekPrompt(program, planData) {
  if (!planData?.week_start || !planData?.week_number) return;
  const mondayKey = planData.week_start.slice(0, 10);
  const [y, m, d] = mondayKey.split("-").map(Number);
  const sunday = new Date(y, m - 1, d + 6);
  sunday.setHours(23, 59, 59, 999);

  const nextWeekNum = planData.week_number + 1;
  if (new Date() > sunday && nextWeekNum <= program.total_weeks) {
    const skeletonWeek = program.skeleton.find(w => w.week_number === nextWeekNum);
    const nextPhase = skeletonWeek?.phase ?? "";
    const nextFocus = skeletonWeek?.focus ?? "";
    document.getElementById("next-week-number").textContent = nextWeekNum;
    document.getElementById("next-week-info").textContent =
      nextPhase ? `${nextPhase}: ${nextFocus}` : nextFocus;
    document.getElementById("next-week-banner").classList.remove("hidden");
  }
}

async function generateNextWeek() {
  if (!currentProgram || !currentPlanData?.week_number) return;
  const nextWeekNum = currentPlanData.week_number + 1;
  const btn = document.getElementById("next-week-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> Generating…';

  document.getElementById("plan-loading").classList.remove("hidden");
  document.getElementById("plan-container").classList.add("hidden");
  document.getElementById("next-week-banner").classList.add("hidden");

  try {
    const data = await api.post("/plans/next-week", {
      program_id: currentProgram.id,
      week_number: nextWeekNum,
    });
    currentPlanId = data.id;
    currentPlanData = data;
    viewingWeekNumber = null;
    _isPastWeekView = false;
    await loadWeekRuns(data.week_start);
    renderPlan(data);
    renderProgramBanner(currentProgram, data);
    updateWeekNavigator();
    updateHeaderButtons();
  } catch (err) {
    const alertEl = document.getElementById("alert");
    alertEl.textContent = err.message || "Failed to generate next week.";
    alertEl.classList.remove("hidden");
    document.getElementById("next-week-banner").classList.remove("hidden");
  } finally {
    document.getElementById("plan-loading").classList.add("hidden");
    btn.disabled = false;
    btn.textContent = `Generate Week ${nextWeekNum}`;
  }
}

async function openProgramModal() {
  const body = document.getElementById("program-modal-body");
  const goalType = currentGoalData?.goal_type || "race";

  if ((goalType === "race" || goalType === "pb_attempt") && (!currentGoalId || !currentGoalData)) {
    alert("Please set a goal before building a program."); return;
  }

  // Fetch existing assessment for prefilling intensity questions
  let assessment = null;
  try { assessment = await api.get("/onboarding/"); } catch (_) {}

  // ── Intensity section (always shown) ──────────────────────────
  const intensityHtml = buildProgramIntensityHtml(assessment);

  // ── Goal-type-specific section ────────────────────────────────
  let goalHtml = "";

  if (goalType === "race" || goalType === "pb_attempt") {
    const raceDate = new Date(currentGoalData.race_date);
    const weeks = Math.min(26, Math.max(2,
      Math.floor((raceDate - new Date()) / (7 * 24 * 60 * 60 * 1000))));
    goalHtml = `
      <p style="font-size:14px;line-height:1.7;margin-bottom:4px;">
        Takbo Coach will create a <strong>${weeks}-week</strong> periodized program for your
        <strong>${escapeHtml(currentGoalData.race_type)}</strong> goal,
        covering Base Building → Build → Peak → Taper.
      </p>
      <p style="font-size:13px;color:var(--text-sec);line-height:1.5;">
        Each week is generated on demand using your actual run history. This replaces any existing program.
      </p>`;

  } else if (goalType === "fitness") {
    goalHtml = `
      <div class="form-group">
        <label>Program Duration</label>
        <select class="form-control" id="pm-duration">
          <option value="6">6 weeks</option>
          <option value="8" selected>8 weeks</option>
          <option value="12">12 weeks</option>
        </select>
      </div>
      <div class="form-group">
        <label>Weekly km target <span style="opacity:.5">optional</span></label>
        <input class="form-control" type="number" id="pm-target-km" placeholder="e.g. 35" min="5" max="200" />
        <div class="form-hint">How many km/week do you want to be running by the end?</div>
      </div>`;

  } else if (goalType === "speed") {
    goalHtml = `
      <div class="form-group">
        <label>Program Duration</label>
        <select class="form-control" id="pm-duration">
          <option value="6">6 weeks</option>
          <option value="8" selected>8 weeks</option>
          <option value="10">10 weeks</option>
        </select>
      </div>
      <div class="form-group">
        <label>Target 5K pace <span style="opacity:.5">optional</span></label>
        <input class="form-control" type="text" id="pm-target-pace" placeholder="e.g. 5:30" />
        <div class="form-hint">Format: MM:SS per km</div>
      </div>`;

  } else if (goalType === "endurance") {
    goalHtml = `
      <div class="form-group">
        <label>Program Duration</label>
        <select class="form-control" id="pm-duration">
          <option value="8">8 weeks</option>
          <option value="12" selected>12 weeks</option>
          <option value="16">16 weeks</option>
        </select>
      </div>
      <div class="form-group">
        <label>Target long run <span style="opacity:.5">km, optional</span></label>
        <input class="form-control" type="number" id="pm-target-long-run" placeholder="e.g. 20" min="5" max="60" />
        <div class="form-hint">Longest single run you want to complete by the end of the program</div>
      </div>`;

  } else if (goalType === "weight_loss") {
    const currentWeight = getUser()?.weight_kg;
    const weightNote = currentWeight
      ? `Your current weight: <strong>${currentWeight} kg</strong>`
      : `<a href="/profile.html">Set your weight in Profile</a> for better calorie estimates`;
    goalHtml = `
      <div class="form-group">
        <label>Program Duration</label>
        <select class="form-control" id="pm-duration">
          <option value="8">8 weeks</option>
          <option value="12" selected>12 weeks</option>
          <option value="16">16 weeks</option>
        </select>
      </div>
      <div class="form-group">
        <label>Target weight <span style="opacity:.5">kg, optional</span></label>
        <input class="form-control" type="number" id="pm-target-weight" placeholder="e.g. 72" step="0.5" min="30" max="300" />
        <div class="form-hint">${weightNote}</div>
      </div>`;

  } else {
    goalHtml = `
      <div class="form-group">
        <label>Program Duration</label>
        <select class="form-control" id="pm-duration">
          <option value="6">6 weeks</option>
          <option value="8" selected>8 weeks</option>
          <option value="12">12 weeks</option>
        </select>
      </div>`;
  }

  body.innerHTML = intensityHtml + goalHtml;

  document.getElementById("program-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  lucide.createIcons();
}

function buildProgramIntensityHtml(assessment) {
  const load = assessment?.load_capacity ?? "moderate";
  const days = assessment?.available_days ?? 4;
  const dist = assessment?.preferred_distance ?? "mixed";

  const loadOpts = [
    { val: "low",      icon: Icons.smile,     label: "Easy",     sub: "Light & consistent" },
    { val: "moderate", icon: Icons.briefcase, label: "Moderate", sub: "Balanced effort" },
    { val: "high",     icon: Icons.flame,     label: "High",     sub: "Push the limits" },
  ];
  const distOpts = [
    { val: "short",  icon: Icons.building2, label: "Short",  sub: "3–5 km" },
    { val: "medium", icon: Icons.route,     label: "Medium", sub: "5–10 km" },
    { val: "long",   icon: Icons.trees,     label: "Long",   sub: "10 km+" },
    { val: "mixed",  icon: Icons.shuffle,   label: "Mixed",  sub: "Variety" },
  ];

  const loadBtns = loadOpts.map(o =>
    `<button type="button" class="pm-opt-btn${o.val === load ? " active" : ""}"
       data-group="load" data-val="${o.val}" onclick="pmSelectOption(this)">
       <span class="pm-opt-icon">${o.icon}</span>
       <span class="pm-opt-label">${o.label}</span>
       <span class="pm-opt-sub">${o.sub}</span>
     </button>`).join("");

  const dayBtns = [1,2,3,4,5,6,7].map(n =>
    `<button type="button" class="day-toggle${n === days ? " active" : ""}"
       data-val="${n}" onclick="pmSelectDay(this)">${n}</button>`).join("");

  const distBtns = distOpts.map(o =>
    `<button type="button" class="pm-opt-btn${o.val === dist ? " active" : ""}"
       data-group="distance" data-val="${o.val}" onclick="pmSelectOption(this)">
       <span class="pm-opt-icon">${o.icon}</span>
       <span class="pm-opt-label">${o.label}</span>
       <span class="pm-opt-sub">${o.sub}</span>
     </button>`).join("");

  return `
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-sec);margin-bottom:12px;">
      Training Preferences
    </div>
    <div class="form-group">
      <label>How hard do you want to train?</label>
      <div class="pm-opt-grid">${loadBtns}</div>
    </div>
    <div class="form-group" style="margin-top:14px;">
      <label>Days available per week</label>
      <div class="day-toggles" id="pm-days-group">${dayBtns}</div>
    </div>
    <div class="form-group" style="margin-top:14px;">
      <label>Preferred run distance</label>
      <div class="pm-opt-grid pm-opt-grid-4">${distBtns}</div>
    </div>
    <div style="border-top:1px solid var(--border);margin:18px 0 16px;"></div>
  `;
}

function pmSelectOption(btn) {
  const group = btn.dataset.group;
  document.querySelectorAll(`.pm-opt-btn[data-group="${group}"]`)
    .forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
}

function pmSelectDay(btn) {
  document.getElementById("pm-days-group")
    ?.querySelectorAll(".day-toggle")
    .forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
}

function closeProgramModal(e) {
  if (e && e.target !== document.getElementById("program-modal")) return;
  document.getElementById("program-modal").classList.add("hidden");
  document.body.style.overflow = "";
}

// ── Week navigator ────────────────────────────────────────────

function updateWeekNavigator() {
  if (!currentProgram) {
    document.getElementById("week-navigator").classList.add("hidden");
    return;
  }

  const totalWeeks = currentProgram.total_weeks;
  // Current live week number from the generated plan (null if no plan yet)
  const liveWeekNum = currentPlanData?.week_number ?? null;
  const viewing = viewingWeekNumber ?? liveWeekNum;

  if (!viewing) {
    document.getElementById("week-navigator").classList.add("hidden");
    return;
  }

  // Compute week date range from program start
  const progStart = new Date(currentProgram.start_date + "T00:00:00");
  const weekStart = new Date(progStart);
  weekStart.setDate(weekStart.getDate() + (viewing - 1) * 7);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 6);

  const fmt = { month: "short", day: "numeric" };
  const rangeStr = `${weekStart.toLocaleDateString("en-US", fmt)} – ${weekEnd.toLocaleDateString("en-US", fmt)}`;

  const isCurrentWeek = viewing === liveWeekNum;
  const label = isCurrentWeek
    ? `Week ${viewing} of ${totalWeeks} (Current)`
    : `Week ${viewing} of ${totalWeeks}`;

  document.getElementById("week-nav-label").textContent = label;
  document.getElementById("week-nav-dates").textContent = rangeStr;

  document.getElementById("week-nav-prev").disabled = viewing <= 1;
  document.getElementById("week-nav-next").disabled = viewing >= (liveWeekNum ?? totalWeeks);

  const todayBtn = document.getElementById("week-nav-today");
  if (_isPastWeekView) {
    todayBtn.classList.remove("hidden");
  } else {
    todayBtn.classList.add("hidden");
  }

  document.getElementById("week-navigator").classList.remove("hidden");
}

async function navigateWeek(dir) {
  if (!currentProgram) return;
  const liveWeekNum = currentPlanData?.week_number ?? null;
  const currentViewing = viewingWeekNumber ?? liveWeekNum;
  if (currentViewing === null) return;

  const newWeek = currentViewing + dir;
  if (newWeek < 1 || newWeek > (liveWeekNum ?? currentProgram.total_weeks)) return;

  if (newWeek === liveWeekNum) {
    // Going back to current week — restore from loaded plan data
    viewingWeekNumber = null;
    _isPastWeekView = false;
    updateWeekNavigator();
    if (currentPlanData) {
      await loadWeekRuns(currentPlanData.week_start);
      renderPlan(currentPlanData);
    }
    return;
  }

  await loadWeekByNumber(newWeek);
}

async function goToCurrentWeek() {
  if (!currentProgram || !currentPlanData) return;
  viewingWeekNumber = null;
  _isPastWeekView = false;
  updateWeekNavigator();
  await loadWeekRuns(currentPlanData.week_start);
  renderPlan(currentPlanData);
  renderProgramBanner(currentProgram, currentPlanData);
  checkNextWeekPrompt(currentProgram, currentPlanData);
}

async function loadWeekByNumber(weekNum) {
  if (!currentProgram) return;
  document.getElementById("plan-loading").classList.remove("hidden");
  document.getElementById("plan-container").classList.add("hidden");

  try {
    const data = await api.get(
      `/plans/by-week?program_id=${currentProgram.id}&week_number=${weekNum}`
    );

    viewingWeekNumber = weekNum;
    _isPastWeekView = true;

    // Populate weekRunsMap and weekRunsById from the returned runs
    weekRunsMap = {};
    weekRunsById = {};
    if (data.runs?.length) {
      for (const run of data.runs) {
        const key = dateStrToLocalKey(run.date);
        weekRunsMap[key] = run;
        weekRunsById[run.id] = run;
      }
    }

    if (data.plan) {
      // Build a minimal plan response shape renderPlan expects
      const pseudoPlanData = {
        id: null,
        week_start: data.week_start,
        generated_at: null,
        week_number: weekNum,
        total_weeks: data.total_weeks,
        plan: data.plan,
      };
      renderPlan(pseudoPlanData);
      renderProgramBanner(currentProgram, pseudoPlanData);
    } else {
      // Week exists in program but plan not generated yet
      document.getElementById("plan-container").classList.add("hidden");
      document.getElementById("plan-summary").innerHTML = "";
      document.getElementById("plan-grid").innerHTML =
        `<div style="grid-column:1/-1;text-align:center;padding:32px;color:var(--text-sec);">
           Week ${weekNum} plan hasn't been generated yet.
         </div>`;
      document.getElementById("plan-container").classList.remove("hidden");
      renderProgramBanner(currentProgram, { week_number: weekNum, total_weeks: data.total_weeks });
    }

    updateWeekNavigator();
  } catch (err) {
    const alertEl = document.getElementById("alert");
    alertEl.textContent = err.message || "Failed to load week.";
    alertEl.classList.remove("hidden");
  } finally {
    document.getElementById("plan-loading").classList.add("hidden");
  }
}

async function createProgram() {
  const btn = document.getElementById("program-confirm-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> Building skeleton…';

  // Build payload — collect goal-type-specific fields from modal
  const payload = {};
  if (currentGoalId) payload.goal_id = currentGoalId;

  const durationEl = document.getElementById("pm-duration");
  if (durationEl) payload.duration_weeks = parseInt(durationEl.value);

  const kmEl = document.getElementById("pm-target-km");
  if (kmEl?.value) { payload.target_value = parseFloat(kmEl.value); payload.target_unit = "km_per_week"; }

  const paceEl = document.getElementById("pm-target-pace");
  if (paceEl?.value) {
    const mins = parseTimeToMinutes(paceEl.value, true); // pace: always MM:SS
    if (mins) { payload.target_value = mins; payload.target_unit = "pace_per_km"; }
  }

  const longRunEl = document.getElementById("pm-target-long-run");
  if (longRunEl?.value) { payload.target_value = parseFloat(longRunEl.value); payload.target_unit = "long_run_km"; }

  const weightEl = document.getElementById("pm-target-weight");
  if (weightEl?.value) payload.target_weight_kg = parseFloat(weightEl.value);

  // Intensity preferences
  const loadVal = document.querySelector('.pm-opt-btn[data-group="load"].active')?.dataset.val;
  if (loadVal) payload.load_capacity = loadVal;

  const daysVal = document.querySelector('#pm-days-group .day-toggle.active')?.dataset.val;
  if (daysVal) payload.available_days = parseInt(daysVal);

  const distVal = document.querySelector('.pm-opt-btn[data-group="distance"].active')?.dataset.val;
  if (distVal) payload.preferred_distance = distVal;

  try {
    payload.local_monday = getLocalMondayISO();
    const program = await api.post("/plans/program", payload);
    currentProgram = program;
    closeProgramModal();

    // Auto-generate Week 1
    document.getElementById("plan-loading").classList.remove("hidden");
    document.getElementById("plan-container").classList.add("hidden");
    document.getElementById("plan-loading").querySelector("p").textContent =
      "Takbo Coach is building your full program skeleton and generating Week 1…";

    const data = await api.post("/plans/next-week", {
      program_id: program.id,
      week_number: 1,
    });
    currentPlanId = data.id;
    currentPlanData = data;
    viewingWeekNumber = null;
    _isPastWeekView = false;
    await loadWeekRuns(data.week_start);
    renderPlan(data);
    renderProgramBanner(program, data);
    updateWeekNavigator();
    updateHeaderButtons();
    document.getElementById("goal-changed-banner").classList.add("hidden");
    document.getElementById("next-week-banner").classList.add("hidden");
  } catch (err) {
    const alertEl = document.getElementById("alert");
    alertEl.textContent = err.message || "Failed to build program. Please try again.";
    alertEl.classList.remove("hidden");
  } finally {
    document.getElementById("plan-loading").classList.add("hidden");
    btn.disabled = false;
    btn.textContent = "Build Program";
  }
}
