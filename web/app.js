/* LEASH Control Room: every interaction calls the local broker demo API. */
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
const events = [];
let failures = 0;
let lastTier = null;

function tierNumber(value) {
  return Number(String(value || "T0").replace("T", ""));
}

function relativeTime(date) {
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return date.toLocaleTimeString();
}

function addEvent(action, verdict, reason, traceId = null) {
  events.unshift({ action, verdict, reason, traceId, time: new Date() });
  if (events.length > 40) events.pop();
  renderEvents();
}

function renderEvents() {
  const list = $("#feed-list");
  list.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("li");
    empty.className = "feed-empty";
    empty.textContent = "No broker decisions recorded yet. Press 1 to execute healthy release.";
    list.append(empty);
    return;
  }

  for (const event of events) {
    const state = event.verdict === "ALLOWED" ? "allowed" : event.verdict === "FAILED" ? "failed" : "denied";
    const item = document.createElement("li");
    item.className = `feed-item ${state}`;

    const status = document.createElement("span");
    status.className = "col-status";
    const pill = document.createElement("span");
    pill.className = `verdict-pill ${state}`;
    pill.textContent = event.verdict;
    status.append(pill);

    const action = document.createElement("span");
    action.className = "col-action";
    action.textContent = event.action;

    const reason = document.createElement("span");
    reason.className = "col-reason";
    reason.append(document.createTextNode(event.reason));
    if (event.traceId) {
      reason.append(document.createTextNode(" "));
      const trace = document.createElement("a");
      trace.className = "trace-code";
      trace.href = "#";
      trace.title = "Copy trace ID";
      trace.dataset.trace = event.traceId;
      trace.textContent = `${event.traceId.slice(0, 10)}…`;
      reason.append(trace);
    }

    const time = document.createElement("span");
    time.className = "col-time";
    time.textContent = relativeTime(event.time);
    time.title = event.time.toLocaleString();
    item.append(status, action, reason, time);
    list.append(item);
  }
}

document.addEventListener("click", (event) => {
  const trace = event.target.closest(".trace-code");
  if (!trace) return;
  event.preventDefault();
  const id = trace.dataset.trace;
  if (!id || !navigator.clipboard) return;
  navigator.clipboard.writeText(id).then(() => {
    const previous = trace.textContent;
    trace.textContent = "COPIED";
    window.setTimeout(() => { trace.textContent = previous; }, 1200);
  }).catch(() => {});
});

function updateBudget() {
  const used = Math.min(failures * 34, 100);
  const remaining = Math.max(0, 100 - used);
  const arc = $("#gauge-arc");
  arc.style.strokeDashoffset = `${235.6 * (used / 100)}`;
  arc.className.baseVal = `gauge-fill ${used >= 100 ? "revoked" : used > 0 ? "watch" : "granted"}`;
  $("#gauge-value").textContent = remaining;
  $("#tel-failures").textContent = failures;
}

function showRevokedBanner(reason, traceId) {
  const banner = $("#revoked-banner");
  const text = $("#banner-text");
  text.replaceChildren(document.createTextNode(`${reason} — evidence: trace `));
  const trace = document.createElement("a");
  trace.className = "trace-link trace-code";
  trace.href = "#";
  trace.dataset.trace = traceId;
  trace.textContent = `${traceId.slice(0, 10)}…`;
  text.append(trace);
  banner.hidden = false;
}

$("#banner-dismiss").addEventListener("click", () => { $("#revoked-banner").hidden = true; });

async function refreshPolicy() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("Policy service unavailable");
    const policy = await response.json();
    const tier = tierNumber(policy.current_tier);
    $("#status-dot").className = "status-dot active";
    $("#status-label").textContent = "Broker Connected";

    const labels = { 3: "T3 · AUTONOMOUS", 2: "T2 · WRITE AUTHORIZED", 1: "T1 · READ ONLY", 0: "T0 · QUARANTINED" };
    const states = { 3: "granted", 2: "watch", 1: "revoked", 0: "revoked" };
    $("#tier-badge-text").textContent = labels[tier] || `T${tier}`;
    $("#tier-badge").className = `tier-badge ${states[tier] || "granted"}`;
    $("#tier-reason").textContent = policy.last_demote_reason
      ? `Demoted: ${policy.last_demote_reason.replaceAll("_", " ")}`
      : ({ 3: "All demo permissions currently active", 2: "Reversible migrations allowed; destructive blocked", 1: "Downstream failures observed — read-only inspection", 0: "Quarantined — zero operations permitted" }[tier] || "");
    $("#tel-version").textContent = `v${policy.policy_version}`;

    for (let rung = 0; rung <= 3; rung += 1) {
      const element = $(`#rung-t${rung}`);
      element.classList.toggle("active", tier === rung);
      element.classList.toggle("revoked", tier < 3 && tier === rung);
    }
    $$(".envelope-item").forEach((item) => item.classList.toggle("active", tier >= Number(item.dataset.minTier)));

    if (lastTier !== null && tier < lastTier) {
      showRevokedBanner("PERMISSION REVOKED — error budget consumed", policy.last_alert_id || "signoz-alert-demote");
    }
    lastTier = tier;
    return policy;
  } catch (error) {
    $("#status-dot").className = "status-dot";
    $("#status-label").textContent = "Disconnected";
    throw error;
  }
}

async function post(path) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" } });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.reason || data.detail?.error || "Request failed";
    throw new Error(detail);
  }
  return data;
}

async function runAction(button, action) {
  button.disabled = true;
  try { await action(); }
  catch (error) { addEvent("ACTION_FAILED", "DENIED", error.message); }
  finally { button.disabled = false; }
}

$("#btn-healthy").addEventListener("click", (event) => runAction(event.currentTarget, async () => {
  const data = await post("/api/demo/run-healthy");
  addEvent("run_release_task", data.outcomes.every((outcome) => outcome.ok) ? "ALLOWED" : "DENIED", `Task ${data.task_id} completed through broker`);
  await refreshPolicy();
}));

$("#btn-inject").addEventListener("click", (event) => runAction(event.currentTarget, async () => {
  await post("/api/demo/inject-migration-failure");
  addEvent("inject_migration_fault", "ALLOWED", "Migration dependency fault injected into downstream service");
}));

$("#btn-failures").addEventListener("click", (event) => runAction(event.currentTarget, async () => {
  const data = await post("/api/demo/run-failures");
  const count = data.outcomes.length;
  failures += count;
  updateBudget();
  addEvent("apply_migration", "FAILED", `${count} downstream failures — HTTP 502 from migration service. Error spans exported to SigNoz.`);
  await refreshPolicy();
}));

$("#btn-delete").addEventListener("click", (event) => runAction(event.currentTarget, async () => {
  const data = await post("/api/demo/request-delete");
  const result = data.outcome;
  if (result.ok) addEvent("delete_staging_table", "ALLOWED", "Destructive cleanup granted by broker");
  else {
    const traceId = result.detail?.trace_id || "policy-denial";
    const reason = result.detail?.reason || "AUTONOMY_TIER_DENIED — T1 is insufficient for destructive action";
    addEvent("delete_staging_table", "DENIED", reason, traceId);
    showRevokedBanner("AUTONOMY_TIER_DENIED — destructive action blocked", traceId);
  }
  await refreshPolicy();
}));

$("#btn-alert").addEventListener("click", (event) => runAction(event.currentTarget, async () => {
  await post("/api/demo/simulate-alert");
  addEvent("signoz_alert_demote", "REVOKED", "SigNoz alert webhook received — agent demoted from T3 to T1 (Read-Only)");
  showRevokedBanner("SigNoz alert fired — agent autonomy revoked", "signoz-alert");
  await refreshPolicy();
}));

$("#btn-reset").addEventListener("click", (event) => runAction(event.currentTarget, async () => {
  await post("/api/demo/reset");
  failures = 0;
  lastTier = null;
  updateBudget();
  $("#revoked-banner").hidden = true;
  addEvent("admin_policy_reset", "ALLOWED", "Agent policy restored to T3 (Full Authority)");
  await refreshPolicy();
}));

$("#btn-refresh").addEventListener("click", () => refreshPolicy().catch((error) => addEvent("policy_refresh", "DENIED", error.message)));

document.addEventListener("keydown", (event) => {
  if (["INPUT", "TEXTAREA"].includes(event.target.tagName)) return;
  const targets = { 1: "#btn-healthy", 2: "#btn-inject", 3: "#btn-failures", 4: "#btn-delete", r: "#btn-refresh" };
  const button = $(targets[event.key.toLowerCase()]);
  if (button && !button.disabled) { event.preventDefault(); button.click(); }
});

updateBudget();
refreshPolicy()
  .then(() => addEvent("connect_broker", "ALLOWED", "Instrument panel connected to LEASH policy broker"))
  .catch((error) => addEvent("connect_broker", "DENIED", `Connection failed: ${error.message}`));
window.setInterval(() => { refreshPolicy().catch(() => {}); renderEvents(); }, 3000);
