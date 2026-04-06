// ── Strava integration helpers ────────────────────────────────────────────────

async function initStravaStatus() {
  // Check for Strava OAuth callback result in URL
  const params = new URLSearchParams(window.location.search);
  const stravaParam = params.get("strava");
  if (stravaParam) {
    // Clean the param from URL
    const clean = window.location.pathname;
    window.history.replaceState(null, "", clean);
    if (stravaParam === "connected") {
      showStravaMessage("Strava connected! Click \"Sync Runs\" to import your activities.", "success");
    } else if (stravaParam === "denied") {
      showStravaMessage("Strava connection was cancelled.", "error");
    } else if (stravaParam === "error") {
      showStravaMessage("Strava connection failed. Please try again.", "error");
    }
  }

  try {
    const data = await api.get("/integrations/strava/status");
    setStravaConnected(data.connected);
  } catch (e) {
    // Integrations not available or not configured — hide section gracefully
  }
}

function setStravaConnected(connected) {
  document.getElementById("strava-badge").classList.toggle("hidden", !connected);
  document.getElementById("strava-sync-btn").classList.toggle("hidden", !connected);
  document.getElementById("strava-connect-btn").classList.toggle("hidden", connected);
  document.getElementById("strava-disconnect-btn").classList.toggle("hidden", !connected);
  if (connected) {
    document.getElementById("strava-status-msg").textContent = "Your Strava account is connected.";
  } else {
    document.getElementById("strava-status-msg").textContent = "Connect Strava to automatically import your runs.";
  }
}

function showStravaMessage(msg, type) {
  const el = document.getElementById("strava-sync-result");
  el.textContent = msg;
  el.style.color = type === "success" ? "var(--accent)" : "#e53e3e";
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 6000);
}

async function stravaConnect() {
  const btn = document.getElementById("strava-connect-btn");
  btn.disabled = true;
  btn.textContent = "Connecting…";
  try {
    const data = await api.get("/integrations/strava/auth-url");
    window.location.href = data.url;
  } catch (e) {
    showStravaMessage(e.message || "Could not initiate Strava connection.", "error");
    btn.disabled = false;
    btn.textContent = "Connect Strava";
  }
}

async function stravaSync() {
  const btn = document.getElementById("strava-sync-btn");
  btn.disabled = true;
  btn.textContent = "Syncing…";
  try {
    const data = await api.post("/integrations/strava/sync", {});
    showStravaMessage(
      `Sync complete: ${data.imported} new run${data.imported !== 1 ? "s" : ""} imported, ${data.skipped} already existed.`,
      "success"
    );
    // Refresh the run list on the page if the function exists
    if (typeof loadRuns === "function") loadRuns();
  } catch (e) {
    showStravaMessage(e.message || "Sync failed. Please try again.", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sync Runs";
  }
}

async function stravaDisconnect() {
  if (!confirm("Disconnect Strava? Your imported runs will remain but future syncs will stop.")) return;
  try {
    await api.delete("/integrations/strava/disconnect");
    setStravaConnected(false);
    showStravaMessage("Strava disconnected.", "success");
  } catch (e) {
    showStravaMessage(e.message || "Failed to disconnect.", "error");
  }
}

// Run on page load
document.addEventListener("DOMContentLoaded", initStravaStatus);
