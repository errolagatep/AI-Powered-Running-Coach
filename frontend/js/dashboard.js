document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;

  const user = getUser();
  if (user) {
    document.getElementById("welcome-msg").textContent = `Welcome back, ${user.name.split(" ")[0]}!`;
  }

  try {
    const [runs, progress, goal, gam, achievements] = await Promise.all([
      api.get("/runs/?limit=5"),
      api.get("/progress/"),
      api.get("/goals/"),
      api.get("/gamification/").catch(() => null),
      api.get("/gamification/achievements").catch(() => []),
    ]);

    renderStats(progress, runs);
    renderGoalBanner(goal);
    renderRuns(runs);
    if (gam) renderGamification(gam);
    if (achievements) checkNewAchievements(achievements);
  } catch (err) {
    console.error(err);
  }
});

function renderStats(progress, runs) {
  // Total runs
  document.getElementById("stat-total-runs").textContent = progress.stats.total_runs;

  // This week
  const weekKm = progress.weekly.km[progress.weekly.km.length - 1] || 0;
  document.getElementById("stat-week-km").textContent = weekKm.toFixed(1);

  // Runs this week (count from weekly data index)
  const today = new Date();
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - today.getDay());
  const weekRuns = runs.filter(r => new Date(r.date) >= weekStart).length;
  document.getElementById("stat-week-runs").textContent = weekRuns;

  // Avg pace last 7 runs
  const last7 = runs.slice(0, 7);
  if (last7.length) {
    const avg = last7.reduce((s, r) => s + r.pace_per_km, 0) / last7.length;
    document.getElementById("stat-avg-pace").textContent = formatPace(avg);
  } else {
    document.getElementById("stat-avg-pace").textContent = "—";
  }
}

function renderGoalBanner(goal) {
  if (!goal) return;
  const banner = document.getElementById("goal-banner");
  banner.classList.remove("hidden");

  const raceDate = new Date(goal.race_date);
  const weeksLeft = Math.max(0, Math.round((raceDate - new Date()) / (7 * 24 * 60 * 60 * 1000)));

  document.getElementById("goal-title").textContent = `${goal.race_type} Goal`;
  const detail = goal.target_time_min
    ? `${weeksLeft} weeks away · Target: ${formatTargetTime(goal.target_time_min)}`
    : `${weeksLeft} weeks away · ${raceDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`;
  document.getElementById("goal-detail").textContent = detail;
}

function formatTargetTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

function renderRuns(runs) {
  document.getElementById("runs-loading").classList.add("hidden");

  if (!runs || runs.length === 0) {
    document.getElementById("no-runs").classList.remove("hidden");
    return;
  }

  const list = document.getElementById("run-list");
  list.classList.remove("hidden");
  list.innerHTML = runs.map(run => runCard(run)).join("");
}

function runCard(run) {
  const effort = run.effort_level;
  const cls = effortClass(effort);
  const hrs = Math.floor(run.duration_min / 60);
  const mins = Math.round(run.duration_min % 60);
  const durStr = hrs > 0 ? `${hrs}h ${mins}m` : `${mins} min`;
  const hrStr = run.heart_rate_avg ? `${run.heart_rate_avg} bpm` : "—";

  const feedbackSection = run.ai_feedback
    ? `<button class="feedback-toggle" onclick="toggleFeedback(this)">▶ Show AI feedback</button>
       <div class="feedback-content">${renderMarkdown(run.ai_feedback)}</div>`
    : "";

  return `
    <div class="run-item">
      <div class="run-item-header">
        <span class="run-date">${formatDate(run.date)}</span>
        <div class="run-stats">
          <div class="run-stat">
            <span class="run-stat-value">${formatDistance(run.distance_km)} km</span>
            <span class="run-stat-label">Distance</span>
          </div>
          <div class="run-stat">
            <span class="run-stat-value">${formatPace(run.pace_per_km)}</span>
            <span class="run-stat-label">Pace /km</span>
          </div>
          <div class="run-stat">
            <span class="run-stat-value">${durStr}</span>
            <span class="run-stat-label">Duration</span>
          </div>
          <div class="run-stat">
            <span class="run-stat-value">${hrStr}</span>
            <span class="run-stat-label">Heart Rate</span>
          </div>
        </div>
        <span class="effort-badge ${cls}">${effort}</span>
      </div>
      ${run.notes ? `<p style="font-size:13px;color:var(--text-sec);margin-top:8px;">${run.notes}</p>` : ""}
      ${feedbackSection}
    </div>
  `;
}

function renderGamification(gam) {
  // Streak card
  const streakCard = document.getElementById("streak-stat-card");
  streakCard.style.display = "";
  document.getElementById("stat-streak").textContent = gam.current_streak;

  // Level + XP card
  const levelCard = document.getElementById("level-stat-card");
  levelCard.style.display = "";
  document.getElementById("stat-level").textContent = gam.level;

  const xpInLevel = gam.total_xp - gam.xp_for_current_level;
  const xpRange   = gam.xp_for_next_level - gam.xp_for_current_level;
  const pct = xpRange > 0 ? Math.min(100, (xpInLevel / xpRange) * 100) : 100;
  document.getElementById("stat-xp-bar").style.width = `${pct}%`;
  document.getElementById("stat-xp-text").textContent = `${gam.total_xp} XP`;
}

function checkNewAchievements(achievements) {
  const seen = JSON.parse(localStorage.getItem("seen_achievements") || "[]");
  const newOnes = achievements.filter(a => !seen.includes(a.achievement_key));
  if (newOnes.length === 0) return;

  // Mark all as seen
  const allKeys = achievements.map(a => a.achievement_key);
  localStorage.setItem("seen_achievements", JSON.stringify(allKeys));

  // Show toasts
  newOnes.forEach((a, i) => {
    setTimeout(() => showAchievementToast(a), i * 800);
  });
}

function showAchievementToast(a) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast-achievement";
  toast.innerHTML = `
    <div class="toast-icon">${a.icon}</div>
    <div class="toast-body">
      <div class="toast-title">Achievement Unlocked!</div>
      <div class="toast-name">${a.title}</div>
      <div class="toast-desc">${a.description}</div>
    </div>
    <button class="toast-close" onclick="this.parentElement.remove()">×</button>
  `;
  container.appendChild(toast);
  // Auto-remove after 6 seconds
  setTimeout(() => toast.remove(), 6000);
}

function toggleFeedback(btn) {
  const content = btn.nextElementSibling;
  const isOpen = content.classList.toggle("open");
  btn.textContent = (isOpen ? "▼ Hide" : "▶ Show") + " AI feedback";
}

function renderMarkdown(text) {
  // Simple markdown renderer for headings and paragraphs
  return text
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 style="font-size:13px;color:var(--text);margin:8px 0 4px;">$3</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[h])(.+)$/gm, (m) => m.startsWith('<') ? m : `<p>${m}</p>`)
    .replace(/<p><\/p>/g, '');
}
