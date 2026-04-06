document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  await loadProfile();
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

function populateForm(user) {
  document.getElementById("p-name").value    = user.name    || "";
  document.getElementById("p-age").value     = user.age     ?? "";
  document.getElementById("p-height").value  = user.height_cm ?? "";
  document.getElementById("p-weight").value  = user.weight_kg ?? "";
  document.getElementById("p-maxhr").value   = user.max_hr  ?? "";

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
  const name   = document.getElementById("p-name").value.trim();
  const age    = document.getElementById("p-age").value;
  const height = document.getElementById("p-height").value;
  const weight = document.getElementById("p-weight").value;
  const maxhr  = document.getElementById("p-maxhr").value;

  if (name)   payload.name       = name;
  if (age)    payload.age        = parseInt(age);
  if (height) payload.height_cm  = parseFloat(height);
  if (weight) payload.weight_kg  = parseFloat(weight);
  if (maxhr)  payload.max_hr     = parseInt(maxhr);

  try {
    const updated = await api.put("/profile/", payload);
    localStorage.setItem("user", JSON.stringify({ ...updated, onboarding_complete: updated.onboarding_complete }));

    // Update navbar name
    const userEl = document.getElementById("navbar-user");
    if (userEl) userEl.querySelector("a") ? userEl.querySelector("a").textContent = updated.name : (userEl.textContent = updated.name);

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
  if (user.avatar_url) {
    userEl.innerHTML = `<a href="/profile.html" class="navbar-user-link">
      <img src="${user.avatar_url}" class="navbar-avatar" alt="${user.name}" />
      <span>${user.name}</span>
    </a>`;
  } else {
    userEl.innerHTML = `<a href="/profile.html" class="navbar-user-link"><span>${user.name}</span></a>`;
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

// ── Helpers ───────────────────────────────────────────────────
function showAlert(id, msg)   { const el = document.getElementById(id); el.textContent = msg; el.classList.remove("hidden"); }
function hideAlert(id)        { document.getElementById(id).classList.add("hidden"); }
function showSuccess(id, msg) { const el = document.getElementById(id); el.textContent = msg; el.classList.remove("hidden"); setTimeout(() => el.classList.add("hidden"), 3000); }
