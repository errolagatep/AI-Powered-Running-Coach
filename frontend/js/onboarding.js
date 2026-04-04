// ── State ────────────────────────────────────────────────────
const state = {
  experience_level: null,
  years_running: 0,
  weekly_runs: null,
  weekly_km: 0,
  primary_goal: null,
  load_capacity: null,
  available_days: null,
  preferred_distance: null,
  injury_history: null,
  ai_followup_a: null,
};

let currentStep = 1;

// ── Boot ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;

  // Redirect to dashboard if already onboarded
  const user = getUser();
  if (user && user.onboarding_complete) {
    window.location.href = "/dashboard.html";
    return;
  }

  // Wire option-card radio inputs to highlight selected card
  document.querySelectorAll(".option-card input[type=radio]").forEach(radio => {
    radio.addEventListener("change", () => {
      const name = radio.name;
      document.querySelectorAll(`input[name="${name}"]`).forEach(r => {
        r.closest(".option-card").classList.remove("selected");
      });
      radio.closest(".option-card").classList.add("selected");
    });
  });
});

// ── Navigation ───────────────────────────────────────────────
function goStep(n) {
  document.getElementById(`step-${currentStep}`).classList.remove("active");
  currentStep = n;
  document.getElementById(`step-${currentStep}`).classList.add("active");
  updateProgress(n);
}

function goNext(from) {
  if (!validateStep(from)) return;
  collectStep(from);
  goStep(from + 1);
}

function updateProgress(n) {
  if (n > 5) return;
  document.getElementById("step-label").textContent = `Step ${n} of 5`;
  document.querySelectorAll(".step-dot").forEach((dot, i) => {
    dot.classList.toggle("active", i < n);
    dot.classList.toggle("done", i < n - 1);
  });
}

// ── Validation ───────────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById("alert");
  el.textContent = msg;
  el.classList.remove("hidden");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function clearError() {
  document.getElementById("alert").classList.add("hidden");
}

function validateStep(step) {
  clearError();
  if (step === 1) {
    if (!document.querySelector('input[name="experience"]:checked')) {
      showError("Please select how long you've been running.");
      return false;
    }
  }
  if (step === 2) {
    if (state.weekly_runs === null) {
      showError("Please select how many runs per week.");
      return false;
    }
  }
  if (step === 3) {
    if (!document.querySelector('input[name="goal"]:checked')) {
      showError("Please select your primary goal.");
      return false;
    }
    if (!document.querySelector('input[name="load"]:checked')) {
      showError("Please select your load capacity.");
      return false;
    }
  }
  if (step === 4) {
    if (state.available_days === null) {
      showError("Please select how many days per week you can run.");
      return false;
    }
    if (!document.querySelector('input[name="distance"]:checked')) {
      showError("Please select your preferred run distance.");
      return false;
    }
  }
  return true;
}

// ── Collect step data ────────────────────────────────────────
function collectStep(step) {
  if (step === 1) {
    const val = document.querySelector('input[name="experience"]:checked').value;
    const [level, years] = val.split(":");
    state.experience_level = level;
    state.years_running = parseFloat(years);
  }
  if (step === 2) {
    state.weekly_km = parseFloat(document.getElementById("weekly-km").value) || 0;
  }
  if (step === 3) {
    state.primary_goal = document.querySelector('input[name="goal"]:checked').value;
    state.load_capacity = document.querySelector('input[name="load"]:checked').value;
  }
  if (step === 4) {
    state.preferred_distance = document.querySelector('input[name="distance"]:checked').value;
  }
}

// ── Day / weekly-run toggles ─────────────────────────────────
function selectDays(val) {
  state.available_days = val;
  document.querySelectorAll('#step-4 .day-toggle').forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.val) === val);
  });
}

function selectWeeklyRuns(val) {
  state.weekly_runs = val;
  document.querySelectorAll('#step-2 .day-toggle').forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.val) === val);
  });
}

// ── Submit assessment ────────────────────────────────────────
async function submitAssessment() {
  if (!validateStep(5)) return;
  state.injury_history = document.getElementById("injury-history").value.trim() || null;

  const btn = document.getElementById("analyze-btn");
  btn.disabled = true;
  btn.textContent = "Analyzing your profile… 🤖";
  clearError();

  try {
    const res = await api.post("/onboarding/", {
      experience_level:   state.experience_level,
      years_running:      state.years_running,
      weekly_runs:        state.weekly_runs,
      weekly_km:          state.weekly_km,
      primary_goal:       state.primary_goal,
      injury_history:     state.injury_history,
      available_days:     state.available_days,
      preferred_distance: state.preferred_distance,
      load_capacity:      state.load_capacity,
    });

    if (res.ai_followup_q) {
      document.getElementById("followup-question").textContent = res.ai_followup_q;
      goStep(6);
      document.getElementById("step-label").textContent = "Almost done!";
    } else {
      showFinalScreen();
    }
  } catch (err) {
    showError(err.message || "Something went wrong. Please try again.");
    btn.disabled = false;
    btn.textContent = "Analyze My Profile 🤖";
  }
}

// ── Follow-up answer ─────────────────────────────────────────
async function submitFollowup() {
  const answer = document.getElementById("followup-answer").value.trim();
  if (answer) {
    try {
      await api.post("/onboarding/answer", { answer });
    } catch (_) {}
  }
  showFinalScreen();
}

function showFinalScreen() {
  document.getElementById(`step-${currentStep}`).classList.remove("active");
  document.getElementById("step-final").classList.add("active");
  document.getElementById("step-label").textContent = "Complete!";
}

// ── Generate first plan ───────────────────────────────────────
async function generatePlan() {
  const btn = document.getElementById("gen-plan-btn");
  btn.disabled = true;
  btn.textContent = "Generating your plan… 🤖";
  try {
    await api.post("/plans/generate", {});
    window.location.href = "/training_plan.html";
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Generate My First Training Plan";
    showError(err.message || "Could not generate plan. You can do this from the dashboard.");
  }
}

// ── Skip ──────────────────────────────────────────────────────
function skipOnboarding() {
  window.location.href = "/dashboard.html";
}
