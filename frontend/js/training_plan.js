let currentGoalId = null;

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
    if (data) renderPlan(data);
  } catch (err) {
    console.error("Failed to load plan:", err);
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

  // Days grid
  const grid = document.getElementById("plan-grid");
  grid.innerHTML = plan.days.map(day => workoutCard(day)).join("");

  document.getElementById("plan-container").classList.remove("hidden");
  document.getElementById("plan-loading").classList.add("hidden");
}

function workoutCard(day) {
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

  return `
    <div class="workout-card">
      <div class="workout-header">
        <span class="workout-day">${day.day}</span>
        <span class="workout-type-badge ${badgeClass}">${type}</span>
      </div>
      <div class="workout-body">
        <div class="workout-title">${day.title}</div>
        <div class="workout-desc">${day.description}</div>
        ${metricsHtml}
        ${day.notes ? `<div class="workout-notes">${day.notes}</div>` : ""}
      </div>
    </div>
  `;
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
