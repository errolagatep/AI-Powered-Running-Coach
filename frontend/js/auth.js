// Pick up JWT token injected via URL query param (Google OAuth redirect)
(function () {
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get("token");
  if (urlToken) {
    localStorage.setItem("token", urlToken);
    // Clean the token from the URL without a page reload
    const clean = window.location.pathname + window.location.search.replace(/[?&]token=[^&]+/, "").replace(/^&/, "?");
    window.history.replaceState(null, "", clean || window.location.pathname);
  }
})();

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

// Render navbar user info if element exists
document.addEventListener("DOMContentLoaded", () => {
  const userEl = document.getElementById("navbar-user");
  if (userEl) {
    const user = getUser();
    if (user) userEl.textContent = user.name;
  }
  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", logout);
});
