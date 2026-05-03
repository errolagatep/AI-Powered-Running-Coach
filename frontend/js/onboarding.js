// ── State ────────────────────────────────────────────────────
const state = {
  experience_level: null,
  years_running: 0,
  weekly_runs: null,
  weekly_km: 0,
  primary_goal: null,
  race_type: null,
  race_date: null,
  target_time_min: null,
  load_capacity: null,
  available_days: null,
  preferred_distance: null,
  injury_history: null,
  weight_kg: null,
  max_hr: null,
};

const TOTAL_STEPS = 6;
let currentStep = 1;

// ── Boot ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;

  const user = getUser();
  if (user && user.onboarding_complete) {
    window.location.href = "/dashboard.html";
    return;
  }

  updateTopbar();

  flatpickr("#body-birthdate", {
    maxDate: "today",
    dateFormat: "Y-m-d",
    disableMobile: true,
    allowInput: false,
  });

  flatpickr("#race-date", {
    minDate: "today",
    dateFormat: "Y-m-d",
    disableMobile: true,
    allowInput: false,
  });
});

// ── Progress topbar ───────────────────────────────────────────
function updateTopbar() {
  const isNumberedStep = currentStep >= 1 && currentStep <= TOTAL_STEPS;
  const pct = isNumberedStep ? ((currentStep - 1) / TOTAL_STEPS) * 100 : 100;

  document.getElementById("ob-progress-bar").style.width = `${pct}%`;
  document.getElementById("ob-step-counter").textContent =
    isNumberedStep ? `${currentStep} / ${TOTAL_STEPS}` : "";

  const backBtn = document.getElementById("ob-back-btn");
  backBtn.style.visibility = currentStep > 1 && currentStep <= TOTAL_STEPS ? "visible" : "hidden";
}

// ── Navigation ───────────────────────────────────────────────
function goStep(n) {
  // Determine outgoing element ID
  let fromId;
  if (currentStep <= TOTAL_STEPS) {
    fromId = `step-${currentStep}`;
  } else if (currentStep === 7) {
    fromId = "step-followup";
  } else {
    fromId = "step-final";
  }
  document.getElementById(fromId)?.classList.remove("active");

  currentStep = n;

  // Determine incoming element ID
  let toId;
  if (n <= TOTAL_STEPS) {
    toId = `step-${n}`;
  } else if (n === 7) {
    toId = "step-followup";
  } else {
    toId = "step-final";
  }
  document.getElementById(toId)?.classList.add("active");
  updateTopbar();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function goBack() {
  if (currentStep > 1) goStep(currentStep - 1);
}

// ── Auto-advance on card selection ───────────────────────────
function pickAndAdvance(radioName, value, fromStep) {
  document.querySelectorAll(`input[name="${radioName}"]`).forEach(r => {
    r.checked = r.value === value;
    r.closest(".option-card").classList.toggle("selected", r.value === value);
  });

  if (radioName === "experience") {
    const [level, years] = value.split(":");
    state.experience_level = level;
    state.years_running = parseFloat(years);
  } else if (radioName === "goal") {
    state.primary_goal = value;
  }

  clearError();
  setTimeout(() => goStep(fromStep + 1), 200);
}

// ── Race step ─────────────────────────────────────────────────
function pickRaceType(value) {
  state.race_type = value;
  document.querySelectorAll('input[name="race_type"]').forEach(r => {
    r.checked = r.value === value;
    r.closest(".option-card").classList.toggle("selected", r.value === value);
  });
  document.getElementById("race-details").classList.remove("hidden");
}

function skipRace() {
  state.race_type = null;
  state.race_date = null;
  state.target_time_min = null;
  clearError();
  goStep(4);
}

// ── Load / distance / day toggles ────────────────────────────
function pickLoad(value) {
  state.load_capacity = value;
  document.querySelectorAll('input[name="load"]').forEach(r => {
    r.checked = r.value === value;
    r.closest(".option-card").classList.toggle("selected", r.value === value);
  });
}

function pickDistance(value) {
  state.preferred_distance = value;
  document.querySelectorAll('input[name="distance"]').forEach(r => {
    r.checked = r.value === value;
    r.closest(".option-card").classList.toggle("selected", r.value === value);
  });
}

function selectDays(val) {
  state.available_days = val;
  document.querySelectorAll('#step-5 .day-toggle[data-val]').forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.val) === val);
  });
}

function selectWeeklyRuns(val) {
  state.weekly_runs = val;
  document.querySelectorAll('#step-4 .day-toggle[data-val]').forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.val) === val);
  });
}

// ── Explicit continue (steps with inputs) ────────────────────
function continueStep(step) {
  clearError();

  if (step === 3) {
    // Race step: race_type is required only if race-details are visible
    if (state.race_type) {
      const dateVal = document.getElementById("race-date").value;
      if (!dateVal) {
        showError("Please select your race date.");
        return;
      }
      state.race_date = dateVal;
      const h = parseInt(document.getElementById("race-target-h").value) || 0;
      const m = parseInt(document.getElementById("race-target-m").value) || 0;
      state.target_time_min = (h * 60 + m) || null;
    }
  }

  if (step === 4) {
    if (state.weekly_runs === null) {
      showError("Please select how many runs per week you currently do.");
      return;
    }
    state.weekly_km = parseFloat(document.getElementById("weekly-km").value) || 0;
  }

  if (step === 5) {
    if (!state.load_capacity) {
      showError("Please select your training load.");
      return;
    }
    if (state.available_days === null) {
      showError("Please select how many days per week you can run.");
      return;
    }
    if (!state.preferred_distance) {
      showError("Please select your preferred run distance.");
      return;
    }
  }

  goStep(step + 1);
}

// ── Generation overlay ───────────────────────────────────────
function showGenOverlay(title, sub, steps) {
  document.getElementById("gen-overlay-title").textContent = title;
  document.getElementById("gen-overlay-sub").textContent = sub;
  const container = document.getElementById("gen-steps");
  container.innerHTML = steps.map(s =>
    `<div class="gen-step">${s}</div>`
  ).join("");
  document.getElementById("gen-overlay").classList.remove("hidden");
  return container.querySelectorAll(".gen-step");
}

function hideGenOverlay() {
  document.getElementById("gen-overlay").classList.add("hidden");
}

function animateGenSteps(stepEls, intervalMs = 1800) {
  let i = 0;
  stepEls[0].classList.add("active");
  return setInterval(() => {
    if (i < stepEls.length) {
      if (i > 0) {
        stepEls[i - 1].classList.remove("active");
        stepEls[i - 1].classList.add("done");
      }
      stepEls[i].classList.add("active");
      i++;
    }
  }, intervalMs);
}

// ── Validation helpers ────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById("alert");
  el.textContent = msg;
  el.classList.remove("hidden");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function clearError() {
  document.getElementById("alert").classList.add("hidden");
}

// ── Submit assessment (step 6) ────────────────────────────────
async function submitAssessment() {
  clearError();
  state.injury_history = document.getElementById("injury-history").value.trim() || null;
  state.medications    = document.getElementById("ob-medications").value.trim() || null;
  const w  = document.getElementById("body-weight").value;
  const hr = document.getElementById("body-maxhr").value;
  const bd = document.getElementById("body-birthdate").value;
  const ht = document.getElementById("body-height").value;
  state.weight_kg  = w  ? parseFloat(w)  : null;
  state.max_hr     = hr ? parseInt(hr)   : null;
  state.birthdate  = bd || null;
  state.height_cm  = ht ? parseFloat(ht) : null;

  const btn = document.getElementById("analyze-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> Analysing…';

  const stepEls = showGenOverlay(
    "Analysing your profile…",
    "Takbo Coach is building a personalised picture of your running",
    [
      "Reading your running history",
      "Identifying your strengths",
      "Checking for training gaps",
      "Crafting your coaching approach",
    ]
  );
  const ticker = animateGenSteps(stepEls, 1600);

  try {
    const res = await api.post("/onboarding/", {
      experience_level:   state.experience_level,
      years_running:      state.years_running,
      weekly_runs:        state.weekly_runs,
      weekly_km:          state.weekly_km,
      primary_goal:       state.primary_goal,
      race_type:          state.race_type,
      race_date:          state.race_date,
      target_time_min:    state.target_time_min,
      injury_history:     state.injury_history,
      medications:        state.medications,
      available_days:     state.available_days,
      preferred_distance: state.preferred_distance,
      load_capacity:      state.load_capacity,
      weight_kg:          state.weight_kg,
      max_hr:             state.max_hr,
      birthdate:          state.birthdate,
      height_cm:          state.height_cm,
    });

    clearInterval(ticker);
    hideGenOverlay();

    if (res.ai_followup_q) {
      document.getElementById("followup-question").textContent = res.ai_followup_q;
      document.getElementById(`step-${currentStep}`).classList.remove("active");
      currentStep = 7;  // followup is step 7 (out of numbered flow)
      document.getElementById("step-followup").classList.add("active");
      document.getElementById("ob-step-counter").textContent = "Almost done!";
      document.getElementById("ob-back-btn").style.visibility = "hidden";
      document.getElementById("ob-progress-bar").style.width = "95%";
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      showFinalScreen();
    }
  } catch (err) {
    clearInterval(ticker);
    hideGenOverlay();
    showError(err.message || "Something went wrong. Please try again.");
    btn.disabled = false;
    btn.textContent = "Build My Profile";
  }
}

// ── Follow-up answer ─────────────────────────────────────────
async function submitFollowup() {
  const answer = document.getElementById("followup-answer").value.trim();
  if (answer) {
    try { await api.post("/onboarding/answer", { answer }); } catch (_) {}
  }
  showFinalScreen();
}

function showFinalScreen() {
  document.getElementById("step-followup")?.classList.remove("active");
  document.getElementById(`step-${currentStep}`)?.classList.remove("active");
  document.getElementById("step-final").classList.add("active");
  document.getElementById("ob-step-counter").textContent = "";
  document.getElementById("ob-back-btn").style.visibility = "hidden";
  document.getElementById("ob-progress-bar").style.width = "100%";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ── Generate first plan ───────────────────────────────────────
async function generatePlan() {
  const btn = document.getElementById("gen-plan-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner"></span> Generating…';

  const stepEls = showGenOverlay(
    "Generating your training plan…",
    "Takbo Coach is designing the perfect week for you",
    [
      "Reviewing your runner profile",
      "Calculating ideal weekly volume",
      "Scheduling workouts & rest days",
      "Adding race-specific sessions",
      "Finalising your plan",
    ]
  );
  const ticker = animateGenSteps(stepEls, 1400);

  try {
    await api.post("/plans/generate", {});
    clearInterval(ticker);
    window.location.href = "/training_plan.html";
  } catch (err) {
    clearInterval(ticker);
    hideGenOverlay();
    btn.disabled = false;
    btn.textContent = "Generate My Training Plan";
    showError(err.message || "Could not generate plan. You can try again from the dashboard.");
  }
}

// ── Skip ──────────────────────────────────────────────────────
function skipOnboarding() {
  // Signal dashboard to show the "complete your profile" prompt
  localStorage.setItem("show_profile_prompt", "1");
  window.location.href = "/dashboard.html";
}
