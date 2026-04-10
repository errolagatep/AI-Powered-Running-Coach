document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;

  // Init Flatpickr on all PB date inputs
  const pbDateOpts = { maxDate: "today", dateFormat: "Y-m-d", disableMobile: true, allowInput: false };
  ["pb-5k-date", "pb-10k-date", "pb-hm-date", "pb-mar-date"].forEach(id =>
    flatpickr(`#${id}`, pbDateOpts)
  );

  await Promise.all([loadProfile(), loadHealthInfo(), loadManualBests(), loadPredictions()]);

  flatpickr("#p-birthdate", {
    maxDate: "today",
    dateFormat: "Y-m-d",
    disableMobile: true,
    allowInput: false,
    onChange: (selectedDates, dateStr) => {
      showAgeFromBirthdate(dateStr);
    },
  });
});

async function loadProfile() {
  try {
    const user = await api.get("/profile/");
    // Update localStorage so navbar is current
    const stored = JSON.parse(localStorage.getItem("user") || "{}");
    localStorage.setItem("user", JSON.stringify({ ...stored, ...user }));
    populateForm(user);
  } catch (err) {
    showAlert("profile-alert", err.message || "Failed to load profile.");
  }
}

function showAgeFromBirthdate(bdStr) {
  const el = document.getElementById("p-age-display");
  if (!bdStr) { el.textContent = ""; return; }
  const bd = new Date(bdStr);
  const now = new Date();
  let age = now.getFullYear() - bd.getFullYear();
  const m = now.getMonth() - bd.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < bd.getDate())) age--;
  el.textContent = age >= 0 ? `Age: ${age}` : "";
}

function populateForm(user) {
  document.getElementById("p-name").value      = user.name       || "";
  // Set birthdate via Flatpickr instance so the calendar reflects the saved value
  const bdPicker = document.getElementById("p-birthdate")._flatpickr;
  if (bdPicker && user.birthdate) {
    bdPicker.setDate(user.birthdate, false);
  } else if (!bdPicker) {
    document.getElementById("p-birthdate").value = user.birthdate || "";
  }
  document.getElementById("p-height").value    = user.height_cm  ?? "";
  document.getElementById("p-weight").value    = user.weight_kg  ?? "";
  document.getElementById("p-maxhr").value     = user.max_hr     ?? "";
  if (user.birthdate) showAgeFromBirthdate(user.birthdate);

  document.getElementById("profile-name-display").textContent  = user.name || "";
  document.getElementById("profile-email-display").textContent = user.email || "";

  const initials = (user.name || "?").trim().split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
  const placeholder = document.getElementById("avatar-placeholder");
  placeholder.textContent = initials;

  if (user.avatar_url) {
    const img = document.getElementById("avatar-img");
    img.src = user.avatar_url;
    img.style.display = "block";
    placeholder.style.display = "none";
  }
}

async function saveProfile() {
  const btn = document.getElementById("save-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";
  hideAlert("profile-alert");
  hideAlert("profile-success");

  const payload = {};
  const name      = document.getElementById("p-name").value.trim();
  const birthdate = document.getElementById("p-birthdate").value;
  const height    = document.getElementById("p-height").value;
  const weight    = document.getElementById("p-weight").value;
  const maxhr     = document.getElementById("p-maxhr").value;

  if (name)      payload.name       = name;
  if (birthdate) payload.birthdate  = birthdate;
  if (height)    payload.height_cm  = parseFloat(height);
  if (weight)    payload.weight_kg  = parseFloat(weight);
  if (maxhr)     payload.max_hr     = parseInt(maxhr);

  try {
    const updated = await api.put("/profile/", payload);
    localStorage.setItem("user", JSON.stringify({ ...updated, onboarding_complete: updated.onboarding_complete }));

    // Update navbar
    renderNavbarAvatar(updated);

    document.getElementById("profile-name-display").textContent = updated.name;
    showSuccess("profile-success", "Profile saved!");
  } catch (err) {
    showAlert("profile-alert", err.message || "Failed to save profile.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save changes";
  }
}

async function uploadAvatar(input) {
  const file = input.files[0];
  if (!file) return;

  const loading = document.getElementById("avatar-loading");
  loading.classList.remove("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/profile/avatar", {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Upload failed");
    }
    const updated = await res.json();
    localStorage.setItem("user", JSON.stringify({ ...updated, onboarding_complete: updated.onboarding_complete }));

    const img = document.getElementById("avatar-img");
    img.src = updated.avatar_url + "?t=" + Date.now(); // cache-bust
    img.style.display = "block";
    document.getElementById("avatar-placeholder").style.display = "none";

    // Update navbar avatar
    renderNavbarAvatar(updated);
  } catch (err) {
    alert(err.message || "Failed to upload image.");
  } finally {
    loading.classList.add("hidden");
    input.value = "";
  }
}

function renderNavbarAvatar(user) {
  const userEl = document.getElementById("navbar-user");
  if (!userEl) return;
  const initials = (user.name || "?").trim().split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
  if (user.avatar_url) {
    userEl.innerHTML = `<a href="/profile.html" class="navbar-user-link">
      <img src="${user.avatar_url}" class="navbar-avatar" alt="${user.name}" />
      <span class="navbar-user-name">${user.name}</span>
    </a>`;
  } else {
    userEl.innerHTML = `<a href="/profile.html" class="navbar-user-link">
      <div class="navbar-initials">${initials}</div>
      <span class="navbar-user-name">${user.name}</span>
    </a>`;
  }
}

function confirmDeleteAccount() {
  document.getElementById("delete-modal").classList.remove("hidden");
  document.getElementById("delete-confirm-input").value = "";
  hideAlert("delete-alert");
}

function closeDeleteModal(event) {
  if (event && event.target !== document.getElementById("delete-modal")) return;
  document.getElementById("delete-modal").classList.add("hidden");
}

async function deleteAccount() {
  const input = document.getElementById("delete-confirm-input").value.trim();
  if (input !== "DELETE") {
    showAlert("delete-alert", 'Please type DELETE (all caps) to confirm.');
    return;
  }

  const btn = document.getElementById("delete-confirm-btn");
  btn.disabled = true;
  btn.textContent = "Deleting…";

  try {
    await api.delete("/profile/");
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/index.html";
  } catch (err) {
    showAlert("delete-alert", err.message || "Failed to delete account.");
    btn.disabled = false;
    btn.textContent = "Delete permanently";
  }
}

// ── Health Info ───────────────────────────────────────────────
async function loadHealthInfo() {
  try {
    const data = await api.get("/profile/health");
    document.getElementById("p-injuries").value    = data.injury_history || "";
    document.getElementById("p-medications").value = data.medications    || "";
  } catch (_) {}
}

async function saveHealth() {
  const btn = document.getElementById("health-save-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";
  hideAlert("health-alert");
  hideAlert("health-success");

  const payload = {
    injury_history: document.getElementById("p-injuries").value.trim() || null,
    medications:    document.getElementById("p-medications").value.trim() || null,
  };

  try {
    await api.put("/profile/health", payload);
    showSuccess("health-success", "Health info saved!");
  } catch (err) {
    showAlert("health-alert", err.message || "Failed to save health info.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save health info";
  }
}

// ── Personal Bests — Manual Input ─────────────────────────────

const PB_RACES = [
  { key: "5K",            h: "pb-5k-h",  m: "pb-5k-m",  s: "pb-5k-s",  d: "pb-5k-date"  },
  { key: "10K",           h: "pb-10k-h", m: "pb-10k-m", s: "pb-10k-s", d: "pb-10k-date" },
  { key: "Half Marathon", h: "pb-hm-h",  m: "pb-hm-m",  s: "pb-hm-s",  d: "pb-hm-date"  },
  { key: "Marathon",      h: "pb-mar-h", m: "pb-mar-m", s: "pb-mar-s", d: "pb-mar-date" },
];

function _timeMinToHMS(time_min) {
  const totalSec = Math.round(time_min * 60);
  return {
    h: Math.floor(totalSec / 3600),
    m: Math.floor((totalSec % 3600) / 60),
    s: totalSec % 60,
  };
}

function _hmsToTimeMin(h, m, s) {
  return h * 60 + m + s / 60;
}

function _fmtTimeMin(time_min) {
  const { h, m, s } = _timeMinToHMS(time_min);
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
  return `${m}:${String(s).padStart(2,"0")}`;
}

async function loadManualBests() {
  try {
    const bests = await api.get("/profile/manual-bests");
    for (const { key, h, m, s, d } of PB_RACES) {
      if (bests[key]) {
        const hms = _timeMinToHMS(bests[key].time_min);
        document.getElementById(h).value = hms.h;
        document.getElementById(m).value = String(hms.m).padStart(2, "0");
        document.getElementById(s).value = String(hms.s).padStart(2, "0");
        if (bests[key].race_date) {
          const picker = document.getElementById(d)._flatpickr;
          if (picker) picker.setDate(bests[key].race_date, false);
          else document.getElementById(d).value = bests[key].race_date;
        }
      }
    }
  } catch (_) {}
}

async function saveManualBests() {
  const btn = document.getElementById("pb-save-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";
  hideAlert("pb-alert");

  const payload = {};
  for (const { key, h, m, s, d } of PB_RACES) {
    const hv = parseInt(document.getElementById(h).value) || 0;
    const mv = parseInt(document.getElementById(m).value) || 0;
    const sv = parseInt(document.getElementById(s).value) || 0;
    const picker = document.getElementById(d)._flatpickr;
    const dateVal = picker ? (picker.selectedDates[0] ? picker.formatDate(picker.selectedDates[0], "Y-m-d") : null) : (document.getElementById(d).value || null);
    if (hv > 0 || mv > 0 || sv > 0) {
      payload[key] = { time_min: _hmsToTimeMin(hv, mv, sv), race_date: dateVal };
    } else {
      payload[key] = null; // signal to delete
    }
  }

  try {
    await api.put("/profile/manual-bests", payload);
    const el = document.getElementById("pb-success");
    el.textContent = "Personal bests saved!";
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
  } catch (err) {
    showAlert("pb-alert", err.message || "Failed to save personal bests.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save PBs";
  }
}

// ── AI Race Predictions ───────────────────────────────────────

async function loadPredictions() {
  try {
    const data = await api.get("/profile/predictions");
    if (data.predictions) {
      renderPredictions(data.predictions, data.generated_at);
    }
  } catch (_) {}
}

async function generatePredictions() {
  const btn = document.getElementById("predict-btn");
  btn.disabled = true;
  btn.textContent = "Generating…";
  document.getElementById("predictions-loading").classList.remove("hidden");
  document.getElementById("predictions-content").classList.add("hidden");
  document.getElementById("predictions-empty").classList.add("hidden");
  document.getElementById("predictions-error").classList.add("hidden");

  try {
    const data = await api.post("/profile/predictions", {});
    renderPredictions(data.predictions, data.generated_at);
  } catch (err) {
    const el = document.getElementById("predictions-error");
    el.textContent = err.message || "Failed to generate predictions. Please try again.";
    el.classList.remove("hidden");
    document.getElementById("predictions-empty").classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Regenerate";
    document.getElementById("predictions-loading").classList.add("hidden");
  }
}

function renderPredictions(data, generatedAt) {
  document.getElementById("predictions-empty").classList.add("hidden");
  document.getElementById("predictions-content").classList.remove("hidden");
  document.getElementById("predict-btn").textContent = "Regenerate";

  if (data.summary) {
    document.getElementById("predictions-summary").textContent = data.summary;
  }

  const preds = data.predictions || {};
  const RACE_ORDER = ["5K", "10K", "Half Marathon", "Marathon"];
  const CONFIDENCE_COLOR = { high: "#22c55e", moderate: "var(--accent)", low: "#94a3b8" };

  const grid = document.getElementById("predictions-grid");
  grid.innerHTML = RACE_ORDER.filter(r => preds[r]).map(race => {
    const p = preds[race];
    const timeStr = _fmtTimeMin(p.time_min);
    const color = CONFIDENCE_COLOR[p.confidence] || "var(--text-sec)";
    return `
      <div class="best-card">
        <div class="best-card-race">${race}</div>
        <div class="best-card-time">${timeStr}</div>
        <div class="best-card-confidence" style="color:${color};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">${p.confidence} confidence</div>
        <div class="best-card-note" style="font-size:11px;color:var(--text-sec);line-height:1.4;">${p.note || ""}</div>
      </div>`;
  }).join("");

  if (generatedAt) {
    const d = new Date(generatedAt);
    document.getElementById("predictions-generated-at").textContent =
      `Generated ${d.toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric", hour:"2-digit", minute:"2-digit" })}`;
  }
}

// ── Helpers ───────────────────────────────────────────────────
function showAlert(id, msg)   { const el = document.getElementById(id); el.textContent = msg; el.classList.remove("hidden"); }
function hideAlert(id)        { document.getElementById(id).classList.add("hidden"); }
function showSuccess(id, msg) { const el = document.getElementById(id); el.textContent = msg; el.classList.remove("hidden"); setTimeout(() => el.classList.add("hidden"), 3000); }
