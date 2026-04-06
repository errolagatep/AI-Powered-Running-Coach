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

function formatDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function effortClass(effort) {
  if (effort <= 4) return "effort-easy";
  if (effort <= 7) return "effort-mod";
  return "effort-hard";
}

function renderNavbarUser(user) {
  const userEl = document.getElementById("navbar-user");
  if (!userEl || !user) return;
  if (user.avatar_url) {
    userEl.innerHTML = `<a href="/profile.html" class="navbar-user-link">
      <img src="${user.avatar_url}" class="navbar-avatar" alt="${user.name}" />
      <span>${user.name}</span>
    </a>`;
  } else {
    userEl.innerHTML = `<a href="/profile.html" class="navbar-user-link">${user.name}</a>`;
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
