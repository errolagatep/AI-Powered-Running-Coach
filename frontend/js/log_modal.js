/* ── Global Quick Log Run Modal ──────────────────────────────────────────────
 * Included on every page. Injects its own HTML on first open, wires up
 * Flatpickr, live pace preview, and submits to POST /runs/. On success it
 * shows an inline feedback panel rather than navigating away.
 *
 * Exports (globals): openLogModal(prefill), closeLogModal()
 * prefill: { distance_km?, notes? }  – optional pre-fill from Today's Workout
 */

(function () {

  let _fpicker = null;
  let _injected = false;

  // ── Build & inject HTML ──────────────────────────────────────────────────
  function _inject() {
    if (_injected) return;
    _injected = true;

    const html = `
<!-- ── Quick Log Modal ── -->
<div id="qlm-backdrop" class="modal-backdrop hidden" onclick="closeLogModal(event)">
  <div class="modal-card qlm-card" role="dialog" aria-modal="true" aria-labelledby="qlm-title">

    <!-- FORM VIEW -->
    <div id="qlm-form-view">
      <div class="modal-header">
        <h3 class="modal-title" id="qlm-title">Log a Run</h3>
        <button class="modal-close" onclick="closeLogModal()">&times;</button>
      </div>

      <div style="padding:0 24px;">
        <div id="qlm-alert" class="alert alert-error hidden" style="margin-bottom:12px;"></div>

        <div class="form-group">
          <label for="qlm-date">Date</label>
          <input class="form-control" type="text" id="qlm-date" placeholder="Select date" readonly required />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="qlm-distance">Distance (km)</label>
            <input class="form-control" type="number" id="qlm-distance" placeholder="5.0" step="0.01" min="0.1" max="200" required />
          </div>
          <div class="form-group">
            <label>Duration</label>
            <div style="display:flex;gap:8px;">
              <input class="form-control" type="number" id="qlm-dur-min" placeholder="Min" min="0" max="999" required style="flex:1;" />
              <input class="form-control" type="number" id="qlm-dur-sec" placeholder="Sec" min="0" max="59" value="0" style="width:72px;" />
            </div>
            <div class="form-hint">Minutes : Seconds</div>
          </div>
        </div>

        <div id="qlm-pace-preview" class="pace-preview hidden">
          <span id="qlm-pace-value">—</span> min/km
          <small>Calculated pace</small>
        </div>

        <div class="form-group">
          <label for="qlm-notes">Notes <span style="opacity:.5">optional</span></label>
          <textarea class="form-control" id="qlm-notes" rows="2" placeholder="How did it feel? Hills, intervals, weather…" style="resize:vertical;"></textarea>
        </div>

        <div class="form-group">
          <label for="qlm-coach-note">Note to your coach <span style="opacity:.5">optional</span></label>
          <textarea class="form-control" id="qlm-coach-note" rows="2" placeholder="Anything for the coach before feedback — e.g. "I was dehydrated", "slept 4 hrs", "ran at altitude"…" style="resize:vertical;"></textarea>
        </div>

        <div class="form-row" style="margin-top:4px;">
          <div class="form-group">
            <label for="qlm-hr">Avg Heart Rate <span style="opacity:.5">optional</span></label>
            <input class="form-control" type="number" id="qlm-hr" placeholder="145" min="60" max="250" />
          </div>
          <div class="form-group">
            <label>Effort: <span id="qlm-effort-display" style="color:var(--accent);font-weight:700;">5</span>/10</label>
            <div class="slider-container" style="margin-top:8px;">
              <span style="font-size:12px;color:var(--text-sec);">Easy</span>
              <input type="range" class="effort-range" id="qlm-effort" min="1" max="10" value="5"
                     oninput="document.getElementById('qlm-effort-display').textContent=this.value" />
              <span style="font-size:12px;color:var(--text-sec);">Max</span>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeLogModal()">Cancel</button>
        <button class="btn btn-primary" id="qlm-submit-btn" onclick="_qlmSubmit()">
          Save Run &amp; Get Feedback
        </button>
      </div>
    </div>

    <!-- LOADING VIEW -->
    <div id="qlm-loading-view" class="hidden" style="text-align:center;padding:40px 24px;">
      <div class="spinner" style="margin:0 auto 16px;width:28px;height:28px;border-width:3px;"></div>
      <h3 style="font-size:16px;font-weight:600;margin-bottom:8px;">Analyzing your run…</h3>
      <p style="color:var(--text-sec);font-size:14px;">Takbo Coach is reviewing your performance.</p>
    </div>

    <!-- FEEDBACK VIEW -->
    <div id="qlm-feedback-view" class="hidden">
      <div class="modal-header">
        <h3 class="modal-title">Takbo Coach Feedback</h3>
        <button class="modal-close" onclick="closeLogModal()">&times;</button>
      </div>
      <div style="padding:0 24px 8px;">
        <div id="qlm-plan-adjusted" class="plan-adjusted-banner hidden" style="margin-bottom:12px;">
          <div class="pab-icon">${Icons.refreshCw}</div>
          <div class="pab-body">
            <div class="pab-title">Training plan updated</div>
            <div id="qlm-pab-reason" class="pab-reason"></div>
          </div>
          <a href="/training_plan.html" class="pab-cta">View new plan →</a>
        </div>
        <div id="qlm-feedback-text" class="feedback-box" style="max-height:340px;overflow-y:auto;"></div>
      </div>
      <div class="modal-footer" style="flex-wrap:wrap;gap:8px;">
        <button class="btn btn-secondary" onclick="_qlmLogAnother()">Log Another Run</button>
        <button class="btn btn-secondary" onclick="closeLogModal()">Close</button>
        <a href="/training_plan.html" class="btn btn-primary">View Training Plan</a>
      </div>
    </div>

  </div>
</div>

<!-- Floating Log Run button -->
<button id="qlm-fab" class="qlm-fab" onclick="openLogModal()" title="Log a Run" aria-label="Log a Run">
  <span class="qlm-fab-icon">+</span>
  <span class="qlm-fab-label">Log Run</span>
</button>`;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    document.body.appendChild(wrapper.firstElementChild); // backdrop
    document.body.appendChild(wrapper.lastElementChild);  // FAB

    // Flatpickr on modal date
    _fpicker = flatpickr("#qlm-date", {
      maxDate: "today",
      defaultDate: "today",
      dateFormat: "Y-m-d",
      disableMobile: true,
      allowInput: false,
    });

    // Live pace preview
    ["qlm-distance", "qlm-dur-min", "qlm-dur-sec"].forEach(id => {
      document.getElementById(id).addEventListener("input", _qlmUpdatePace);
    });
  }

  // ── Pace preview ────────────────────────────────────────────────────────
  function _qlmUpdatePace() {
    const dist = parseFloat(document.getElementById("qlm-distance").value);
    const mins = parseFloat(document.getElementById("qlm-dur-min").value) || 0;
    const secs = parseFloat(document.getElementById("qlm-dur-sec").value) || 0;
    const total = mins + secs / 60;
    const preview = document.getElementById("qlm-pace-preview");
    if (dist > 0 && total > 0) {
      const pace = total / dist;
      document.getElementById("qlm-pace-value").textContent = _fmtPace(pace);
      preview.classList.remove("hidden");
    } else {
      preview.classList.add("hidden");
    }
  }

  function _fmtPace(pace) {
    if (typeof formatPace === "function") return formatPace(pace);
    const m = Math.floor(pace);
    const s = Math.round((pace - m) * 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  // ── Submit ───────────────────────────────────────────────────────────────
  window._qlmSubmit = async function () {
    const alertEl = document.getElementById("qlm-alert");
    alertEl.classList.add("hidden");

    const dist  = parseFloat(document.getElementById("qlm-distance").value);
    const mins  = parseFloat(document.getElementById("qlm-dur-min").value) || 0;
    const secs  = parseFloat(document.getElementById("qlm-dur-sec").value) || 0;
    const total = mins + secs / 60;

    if (!dist || dist <= 0) { _qlmAlert("Distance must be greater than 0"); return; }
    if (total <= 0)          { _qlmAlert("Duration must be greater than 0"); return; }

    const hr         = document.getElementById("qlm-hr").value;
    const date       = document.getElementById("qlm-date").value;
    const notes      = document.getElementById("qlm-notes").value.trim();
    const coachNote  = document.getElementById("qlm-coach-note").value.trim();

    const body = {
      date: date + "T12:00:00",
      distance_km: dist,
      duration_min: total,
      effort_level: parseInt(document.getElementById("qlm-effort").value),
    };
    if (hr)         body.heart_rate_avg = parseInt(hr);
    if (notes)      body.notes = notes;
    if (coachNote)  body.coach_note = coachNote;

    const submitBtn = document.getElementById("qlm-submit-btn");
    submitBtn.disabled = true;
    _qlmShowView("loading");

    try {
      const run = await api.post("/runs/", body);
      _qlmShowFeedback(run);
    } catch (err) {
      _qlmShowView("form");
      submitBtn.disabled = false;
      _qlmAlert(err.message || "Failed to save run. Please try again.");
    }
  };

  function _qlmShowFeedback(run) {
    _qlmShowView("feedback");
    const fbEl = document.getElementById("qlm-feedback-text");
    if (run.ai_feedback) {
      const renderFn = typeof renderMarkdown === "function" ? renderMarkdown : (t) => escapeHtml(t);
      fbEl.innerHTML = renderFn(run.ai_feedback);
    } else {
      fbEl.textContent = "Feedback unavailable. Please check your API key.";
    }
    if (run.plan_adjusted) {
      document.getElementById("qlm-pab-reason").textContent =
        run.plan_adjustment_reason || "Your coach adjusted the plan to better match your current fitness.";
      document.getElementById("qlm-plan-adjusted").classList.remove("hidden");
    }

    // Refresh the page's run data if the page exposes a reload hook
    if (typeof window._qlmOnRunLogged === "function") {
      window._qlmOnRunLogged(run);
    }
  }

  function _qlmShowView(view) {
    document.getElementById("qlm-form-view").classList.toggle("hidden",    view !== "form");
    document.getElementById("qlm-loading-view").classList.toggle("hidden", view !== "loading");
    document.getElementById("qlm-feedback-view").classList.toggle("hidden",view !== "feedback");
  }

  function _qlmAlert(msg) {
    const el = document.getElementById("qlm-alert");
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  // ── Log another (reset form) ─────────────────────────────────────────────
  window._qlmLogAnother = function () {
    _qlmReset();
    _qlmShowView("form");
  };

  function _qlmReset() {
    document.getElementById("qlm-distance").value = "";
    document.getElementById("qlm-dur-min").value  = "";
    document.getElementById("qlm-dur-sec").value  = "0";
    document.getElementById("qlm-hr").value       = "";
    document.getElementById("qlm-effort").value   = "5";
    document.getElementById("qlm-effort-display").textContent = "5";
    document.getElementById("qlm-notes").value           = "";
    document.getElementById("qlm-coach-note").value      = "";
    document.getElementById("qlm-submit-btn").disabled   = false;
    document.getElementById("qlm-pace-preview").classList.add("hidden");
    document.getElementById("qlm-alert").classList.add("hidden");
    document.getElementById("qlm-plan-adjusted").classList.add("hidden");
    if (_fpicker) _fpicker.setDate(new Date(), false);
  }

  // ── Public API ───────────────────────────────────────────────────────────
  window.openLogModal = function (prefill) {
    _inject();
    _qlmReset();
    _qlmShowView("form");
    if (prefill) {
      if (prefill.distance_km) document.getElementById("qlm-distance").value = prefill.distance_km;
      if (prefill.notes)       document.getElementById("qlm-notes").value    = prefill.notes;
      if (prefill.distance_km || prefill.notes) _qlmUpdatePace();
    }
    document.getElementById("qlm-backdrop").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    setTimeout(() => document.getElementById("qlm-distance").focus(), 80);
  };

  window.closeLogModal = function (e) {
    if (e && e.target !== document.getElementById("qlm-backdrop")) return;
    if (e === undefined || e.target === document.getElementById("qlm-backdrop")) {
      document.getElementById("qlm-backdrop")?.classList.add("hidden");
      document.body.style.overflow = "";
    }
  };

})();

// ── Shared Feedback Notes Modal ───────────────────────────────────────────────
// Available on every page that includes log_modal.js.
// Pages must define window.generateFeedback(runId, coachNote) to handle the call.
(function () {
  let _runId = null;

  function _inject() {
    if (document.getElementById("feedback-notes-backdrop")) return;
    document.body.insertAdjacentHTML("beforeend", `
<div id="feedback-notes-backdrop" class="modal-backdrop hidden" onclick="closeFeedbackModal(event)">
  <div class="modal-card" style="max-width:440px;">
    <div class="modal-header">
      <span class="modal-title">Get Coach Feedback</span>
      <button class="modal-close" onclick="closeFeedbackModal()">&times;</button>
    </div>
    <div style="padding:0 24px;">
      <label class="form-label">Note to your coach <span style="font-weight:400;color:var(--text-sec);">(optional)</span></label>
      <textarea id="feedback-notes-input" rows="3" class="form-control" style="resize:vertical;margin-top:6px;"
        placeholder="e.g. slept poorly, felt dehydrated, running at altitude, tight calves…"
        onkeydown="if(event.ctrlKey&&event.key==='Enter'){event.preventDefault();confirmFeedbackGenerate();}"></textarea>
      <p style="font-size:12px;color:var(--text-sec);margin-top:6px;">Your coach reads this before generating feedback.</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeFeedbackModal()">Cancel</button>
      <button class="btn btn-primary" id="feedback-confirm-btn" onclick="confirmFeedbackGenerate()">Generate Feedback</button>
    </div>
  </div>
</div>`);
  }

  window.openFeedbackModal = function (runId) {
    _inject();
    _runId = runId;
    document.getElementById("feedback-notes-input").value = "";
    document.getElementById("feedback-notes-backdrop").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => document.getElementById("feedback-notes-input").focus());
  };

  window.closeFeedbackModal = function (e) {
    if (e && e.target !== document.getElementById("feedback-notes-backdrop")) return;
    document.getElementById("feedback-notes-backdrop").classList.add("hidden");
    document.body.style.overflow = "";
    _runId = null;
  };

  window.confirmFeedbackGenerate = function () {
    const runId = _runId;
    if (!runId) return;
    const coachNote = document.getElementById("feedback-notes-input").value.trim();
    document.getElementById("feedback-notes-backdrop").classList.add("hidden");
    document.body.style.overflow = "";
    _runId = null;
    if (typeof window.generateFeedback === "function") window.generateFeedback(runId, coachNote);
  };
})();

// ── Shared Edit Run Notes Modal ───────────────────────────────────────────────
// Light-weight notes-only edit — useful for Strava imports that bypassed the log form.
// After saving, calls window._onRunNotesUpdated(runId, updatedRun) if defined.
(function () {
  let _runId = null;

  function _inject() {
    if (document.getElementById("edit-notes-backdrop")) return;
    document.body.insertAdjacentHTML("beforeend", `
<div id="edit-notes-backdrop" class="modal-backdrop hidden" onclick="closeEditNotesModal(event)">
  <div class="modal-card" style="max-width:440px;">
    <div class="modal-header">
      <span class="modal-title">Edit Run Notes</span>
      <button class="modal-close" onclick="closeEditNotesModal()">&times;</button>
    </div>
    <div style="padding:0 24px;">
      <label class="form-label">Notes</label>
      <textarea id="edit-notes-input" rows="4" class="form-control" style="resize:vertical;margin-top:6px;"
        placeholder="How did it feel? Hills, weather, intervals…"></textarea>
      <div id="edit-notes-error" class="alert alert-error hidden" style="margin-top:10px;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeEditNotesModal()">Cancel</button>
      <button class="btn btn-primary" id="edit-notes-save-btn" onclick="confirmEditNotes()">Save notes</button>
    </div>
  </div>
</div>`);
  }

  window.openEditNotesModal = function (runId, currentNotes) {
    _inject();
    _runId = runId;
    document.getElementById("edit-notes-input").value = currentNotes || "";
    document.getElementById("edit-notes-error").classList.add("hidden");
    document.getElementById("edit-notes-backdrop").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => document.getElementById("edit-notes-input").focus());
  };

  window.closeEditNotesModal = function (e) {
    if (e && e.target !== document.getElementById("edit-notes-backdrop")) return;
    document.getElementById("edit-notes-backdrop").classList.add("hidden");
    document.body.style.overflow = "";
    _runId = null;
  };

  window.confirmEditNotes = async function () {
    const runId = _runId;
    if (!runId) return;
    const notes = document.getElementById("edit-notes-input").value.trim();
    const btn   = document.getElementById("edit-notes-save-btn");
    const errEl = document.getElementById("edit-notes-error");
    errEl.classList.add("hidden");
    btn.disabled = true;
    btn.textContent = "Saving…";
    try {
      const updated = await api.patch(`/runs/${runId}`, { notes });
      document.getElementById("edit-notes-backdrop").classList.add("hidden");
      document.body.style.overflow = "";
      _runId = null;
      if (typeof window._onRunNotesUpdated === "function") window._onRunNotesUpdated(runId, updated);
    } catch (err) {
      errEl.textContent = err.message || "Failed to save notes.";
      errEl.classList.remove("hidden");
    } finally {
      btn.disabled = false;
      btn.textContent = "Save notes";
    }
  };
})();
