function getToken()   { return localStorage.getItem("token"); }
function getUser()    { return JSON.parse(localStorage.getItem("user") || "null"); }
function isLoggedIn() { return !!getToken(); }

function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = "/index.html";
    return false;
  }
  return true;
}

function setAuth(token, user) {
  localStorage.setItem("token", token);
  localStorage.setItem("user", JSON.stringify(user));
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = "/index.html";
}

function formatPace(paceDecimal) {
  const min = Math.floor(paceDecimal);
  const sec = Math.round((paceDecimal - min) * 60);
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function formatDistance(km) {
  return km % 1 === 0 ? `${km}` : km.toFixed(2);
}

function formatDuration(durationMin) {
  const totalSec = Math.round(durationMin * 60);
  const h   = Math.floor(totalSec / 3600);
  const m   = Math.floor((totalSec % 3600) / 60);
  const s   = totalSec % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function effortClass(effort) {
  if (effort <= 4) return "effort-easy";
  if (effort <= 7) return "effort-mod";
  return "effort-hard";
}

function renderNavbarUser(user) {
  const userEl = document.getElementById("navbar-user");
  if (!userEl || !user) return;
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

  // Inject Profile into the hamburger nav (for mobile)
  const navList = document.querySelector(".navbar-nav");
  if (navList && !navList.querySelector(".nav-profile-link")) {
    const li = document.createElement("li");
    const isActive = window.location.pathname === "/profile.html";
    li.innerHTML = `<a href="/profile.html" class="nav-profile-link${isActive ? " active" : ""}">Profile</a>`;
    navList.appendChild(li);
  }
}

// Render navbar user info if element exists; fetch from API if user object missing after OAuth
document.addEventListener("DOMContentLoaded", async () => {
  if (getToken() && !getUser()) {
    try {
      const res = await fetch("/api/auth/me", {
        headers: { "Authorization": `Bearer ${getToken()}` },
      });
      if (res.ok) {
        const user = await res.json();
        localStorage.setItem("user", JSON.stringify(user));
        renderNavbarUser(user);
      }
    } catch (_) {}
  } else {
    renderNavbarUser(getUser());
  }
  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", logout);
});
