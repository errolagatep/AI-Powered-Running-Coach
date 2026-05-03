document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;

  // Flatpickr date picker — default to today, no future dates allowed
  flatpickr("#run-date", {
    maxDate: "today",
    defaultDate: "today",
    dateFormat: "Y-m-d",
    disableMobile: true,
    allowInput: false,
  });

  // Pace preview updates
  ["run-distance", "run-dur-min", "run-dur-sec"].forEach(id => {
    document.getElementById(id).addEventListener("input", updatePacePreview);
  });
});

function updateEffort(val) {
  document.getElementById("effort-display").textContent = val;
}

function updatePacePreview() {
  const distEl = document.getElementById("run-distance");
  const minEl  = document.getElementById("run-dur-min");
  const secEl  = document.getElementById("run-dur-sec");
  const preview = document.getElementById("pace-preview");
  const paceEl  = document.getElementById("pace-value");

  const dist = parseFloat(distEl.value);
  const mins = parseFloat(minEl.value) || 0;
  const secs = parseFloat(secEl.value) || 0;
  const totalMin = mins + secs / 60;

  if (dist > 0 && totalMin > 0) {
    const pace = totalMin / dist;
    paceEl.textContent = formatPace(pace);
    preview.classList.remove("hidden");
  } else {
    preview.classList.add("hidden");
  }
}

async function handleSubmit(e) {
  e.preventDefault();

  const alertEl = document.getElementById("alert");
  alertEl.classList.add("hidden");

  const dist  = parseFloat(document.getElementById("run-distance").value);
  const mins  = parseFloat(document.getElementById("run-dur-min").value) || 0;
  const secs  = parseFloat(document.getElementById("run-dur-sec").value) || 0;
  const totalMin = mins + secs / 60;

  if (dist <= 0) { showAlert("Distance must be greater than 0"); return; }
  if (totalMin <= 0) { showAlert("Duration must be greater than 0"); return; }

  const hr     = document.getElementById("run-hr").value;
  const effort = parseInt(document.getElementById("run-effort").value);
  const notes  = document.getElementById("run-notes").value.trim();
  const date   = document.getElementById("run-date").value;

  const body = {
    date: date + "T12:00:00",
    distance_km: dist,
    duration_min: totalMin,
    effort_level: effort,
  };
  if (hr) body.heart_rate_avg = parseInt(hr);
  if (notes) body.notes = notes;

  // Show loading
  document.getElementById("form-card").classList.add("hidden");
  document.getElementById("loading-feedback").classList.remove("hidden");

  try {
    const run = await api.post("/runs/", body);
    showFeedback(run);
  } catch (err) {
    document.getElementById("form-card").classList.remove("hidden");
    document.getElementById("loading-feedback").classList.add("hidden");
    showAlert(err.message || "Failed to save run. Please try again.");
  }
}

function showAlert(msg) {
  const el = document.getElementById("alert");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function showFeedback(run) {
  document.getElementById("loading-feedback").classList.add("hidden");
  document.getElementById("feedback-result").classList.remove("hidden");

  const feedbackEl = document.getElementById("feedback-text");
  if (run.ai_feedback) {
    feedbackEl.innerHTML = renderMarkdown(run.ai_feedback);
  } else {
    feedbackEl.innerHTML = "<p>Feedback unavailable. Please check your API key.</p>";
  }

  if (run.plan_adjusted) {
    const banner = document.getElementById("plan-adjusted-banner");
    document.getElementById("pab-reason").textContent = run.plan_adjustment_reason || "Your coach adjusted the plan to better match your current fitness.";
    banner.classList.remove("hidden");
    banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // Contextual back button based on ?from= query param
  const from = new URLSearchParams(window.location.search).get("from");
  const backBtn = document.getElementById("back-btn");
  if (from === "training_plan") {
    backBtn.href = "/training_plan.html";
    backBtn.textContent = "← Back to Training Plan";
  } else if (from === "runs") {
    backBtn.href = "/runs.html";
    backBtn.textContent = "← Back to Runs";
  } else {
    backBtn.href = "/dashboard.html";
    backBtn.textContent = "← Back to Dashboard";
  }
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
