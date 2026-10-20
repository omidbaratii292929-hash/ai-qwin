/* OMID Industrial AI Agent — منطق داشبورد
   © هوشمندسازی صنعت امید — ما می‌سازیم تا شما راحت زندگی کنید
   طراح و سازندهٔ اصلی: مهندس امید براتی
   بدون هیچ منبع خارجی؛ همهٔ فراخوانی‌ها same-origin هستند. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  readToken: localStorage.getItem("omid_read_token") || "",
  controlToken: localStorage.getItem("omid_control_token") || "",
};

/* ---------- شبکه ---------- */
async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (state.readToken) headers["Authorization"] = "Bearer " + state.readToken;
  if (state.controlToken) headers["X-OMID-Control-Token"] = state.controlToken;
  const resp = await fetch(path, Object.assign({}, opts, { headers }));
  let body = null;
  try { body = await resp.json(); } catch (_) { /* پاسخ غیر JSON */ }
  if (!resp.ok) {
    const detail = body && body.detail ? body.detail : ("HTTP " + resp.status);
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function renderError(el, err) {
  el.innerHTML = "";
  const div = document.createElement("div");
  div.className = "item";
  const tag = document.createElement("span");
  tag.className = "tag err";
  tag.textContent = "خطا";
  div.appendChild(tag);
  div.appendChild(document.createTextNode(" " + String(err.message || err)));
  el.appendChild(div);
}

function pretty(obj) { return JSON.stringify(obj, null, 2); }

function jsonPanel(el, obj) { el.textContent = pretty(obj); }

/* ---------- توکن‌ها ---------- */
function initTokens() {
  $("#read-token").value = state.readToken;
  $("#control-token").value = state.controlToken;
  $("#save-tokens").addEventListener("click", () => {
    state.readToken = $("#read-token").value.trim();
    state.controlToken = $("#control-token").value.trim();
    localStorage.setItem("omid_read_token", state.readToken);
    localStorage.setItem("omid_control_token", state.controlToken);
    $("#token-note").textContent = "ذخیره شد (فقط در همین مرورگر).";
    setTimeout(() => { $("#token-note").textContent = ""; }, 2500);
    refreshStatus();
  });
}

/* ---------- تب‌ها ---------- */
const TABS = [
  ["overview", "نمای کلی"],
  ["agent", "عامل هوشمند"],
  ["devices", "تجهیزات"],
  ["safety", "ایمنی و حالت‌ها"],
  ["twin", "شبیه‌سازی و Twin"],
  ["knowledge", "دانش (RAG)"],
  ["memory", "حافظه"],
  ["events", "رویدادها"],
  ["diagnostics", "تشخیص عیب"],
  ["about", "درباره پروژه"],
];

function initTabs() {
  const nav = $("#tabs");
  TABS.forEach(([id, label], i) => {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.dataset.tab = id;
    btn.addEventListener("click", () => activateTab(id));
    nav.appendChild(btn);
    if (i === 0) btn.classList.add("active");
  });
  $$(".tab").forEach((sec, i) => { if (i === 0) sec.classList.add("active"); });
}

function activateTab(id) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
  $$(".tab").forEach((s) => s.classList.toggle("active", s.dataset.tab === id));
  const loaders = {
    overview: refreshStatus, devices: loadDevices, safety: loadSafety,
    twin: loadTwin, memory: () => memSearch(), events: loadEvents,
    diagnostics: loadFindings, about: loadAbout,
  };
  if (loaders[id]) loaders[id]().catch(() => {});
}

/* ---------- وضعیت و نشان‌ها ---------- */
async function refreshStatus() {
  let st;
  try { st = await api("/api/status"); }
  catch (err) {
    $("#mode-badge").textContent = "خطای اتصال";
    $("#mode-badge").className = "badge danger";
    const cards = $("#status-cards");
    if (cards && !cards.dataset.errShown) {
      cards.innerHTML = "";
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = "<h4>اتصال به API</h4>";
      const v = document.createElement("div");
      v.className = "value small";
      v.textContent = "ناموفق: " + err.message + " — توکن خواندن را بررسی کنید.";
      card.appendChild(v);
      cards.appendChild(card);
      cards.dataset.errShown = "1";
    }
    return;
  }
  $("#status-cards").dataset.errShown = "";
  const safety = st.safety || {};
  const modeEl = $("#mode-badge");
  modeEl.textContent = "حالت: " + (safety.mode || "?");
  modeEl.className = "badge " + (safety.mode === "control" ? "danger" : safety.mode === "simulate" ? "ok" : "warn");

  const aiEl = $("#ai-badge");
  const ai = st.ai || {};
  aiEl.textContent = ai.configured
    ? ("AI: " + (ai.available ? "سالم" : "قطع") + (ai.model ? " (" + ai.model + ")" : ""))
    : "AI: پیکربندی‌نشده (قواعد-محور)";
  aiEl.className = "badge " + (ai.configured ? (ai.available ? "ok" : "danger") : "warn");

  const estopEl = $("#estop-badge");
  estopEl.textContent = "E-STOP: " + (safety.estop_active ? "فعال" : "عادی");
  estopEl.className = "badge " + (safety.estop_active ? "danger" : "ok");

  const cards = [
    ["نسخه", st.version], ["uptime (ثانیه)", st.uptime_s],
    ["دستگاه‌ها", st.devices_count], ["ابزارهای مجاز", st.tools],
    ["اسناد دانش", st.knowledge_docs], ["یافته‌های اخیر", st.recent_findings],
    ["رویدادهای حافظه", st.memory ? st.memory.events : "-"],
    ["حداکثر ریسک مجاز", safety.max_risk_in_mode],
  ];
  const box = $("#status-cards");
  box.innerHTML = "";
  cards.forEach(([title, value]) => {
    const card = document.createElement("div");
    card.className = "card";
    const h = document.createElement("h4"); h.textContent = title;
    const v = document.createElement("div"); v.className = "value"; v.textContent = String(value ?? "-");
    card.appendChild(h); card.appendChild(v); box.appendChild(card);
  });
}

/* ---------- درباره/برند ---------- */
async function loadAbout() {
  const about = await api("/api/about");
  $("#project-name").textContent = about.project_name || "OMID Industrial AI Agent";
  $("#company-line").textContent = (about.company_name || "") + " — " + (about.tagline || "");
  $("#footer-text").textContent = about.footer || "";
  $("#footer-meta").textContent = "نسخه " + (about.version || "?") + " | حالت ایمنی: " + (about.safety_mode || "?");
  const box = $("#about-box");
  box.innerHTML = "";
  const lines = [
    ["پروژه", about.project_name + " (" + (about.project_name_fa || "") + ")"],
    ["شرکت", about.company_name],
    ["شعار رسمی", about.tagline],
    ["طراح و سازندهٔ اصلی", about.lead_designer_and_creator],
    ["همکاران", (about.collaborators || []).join("، ")],
    ["مخزن", about.repository || "-"],
    ["نسخه", about.version],
  ];
  lines.forEach(([k, v]) => {
    const item = document.createElement("div");
    item.className = "item";
    item.textContent = k + ": " + v;
    box.appendChild(item);
  });
  if (about.notice) {
    const n = document.createElement("div");
    n.className = "item muted";
    n.textContent = "⚠ " + about.notice;
    box.appendChild(n);
  }
}

/* ---------- عامل ---------- */
function initAgent() {
  $("#agent-send").addEventListener("click", async () => {
    const text = $("#agent-input").value.trim();
    const out = $("#agent-result");
    if (!text) { out.textContent = "متن درخواست خالی است."; return; }
    out.textContent = "در حال اجرا…";
    try {
      const task = await api("/api/agent/request", { method: "POST", body: JSON.stringify({ text }) });
      out.textContent = (task.result_summary || "") + "\n\n" + pretty(task);
    } catch (err) { renderError(out, err); }
  });
  $("#tasks-refresh").addEventListener("click", loadTasks);
}

async function loadTasks() {
  const box = $("#tasks-list");
  try {
    const data = await api("/api/tasks?limit=15");
    box.innerHTML = "";
    (data.tasks || []).forEach((t) => {
      const item = document.createElement("div");
      item.className = "item";
      const tag = document.createElement("span");
      tag.className = "tag " + (t.status === "completed" ? "ok" : t.status === "failed" ? "err" : "");
      tag.textContent = t.status;
      item.appendChild(tag);
      item.appendChild(document.createTextNode(" " + t.id + " — " + t.goal.slice(0, 80)));
      if (t.status === "waiting_confirm") {
        const btn = document.createElement("button");
        btn.className = "btn warn";
        btn.classList.add("ms");
        btn.textContent = "تأیید عملیات فیزیکی";
        btn.addEventListener("click", async () => {
          try {
            const res = await api("/api/tasks/" + t.id + "/confirm", { method: "POST" });
            jsonPanel(box, res);
          } catch (e2) { renderError(box, e2); }
        });
        item.appendChild(btn);
      }
      box.appendChild(item);
    });
    if (!box.children.length) box.textContent = "وظیفه‌ای ثبت نشده است.";
  } catch (err) { renderError(box, err); }
}

/* ---------- تجهیزات ---------- */
function initDevices() {
  $("#discover-serial").addEventListener("click", () => discover("serial"));
  $("#discover-network").addEventListener("click", () => discover("network"));
  $("#drivers-refresh").addEventListener("click", loadDevices);
}

async function discover(scope) {
  const box = $("#devices-list");
  try {
    const res = await api("/api/devices/discover", { method: "POST", body: JSON.stringify({ scope }) });
    jsonPanel(box, res);
    loadDevices().catch(() => {});
  } catch (err) { renderError(box, err); }
}

async function loadDevices() {
  const dBox = $("#devices-list");
  const drBox = $("#drivers-list");
  try {
    const [devs, drivers] = await Promise.all([api("/api/devices"), api("/api/drivers")]);
    drBox.innerHTML = "";
    (drivers.drivers || []).forEach((d) => {
      const item = document.createElement("div");
      item.className = "item";
      const tag = document.createElement("span");
      tag.className = "tag " + (d.backend === "simulated" ? "sim" : "ok");
      tag.textContent = d.backend === "simulated" ? "SIMULATION" : "LIVE";
      item.appendChild(tag);
      item.appendChild(document.createTextNode(" " + d.name + " | " + d.protocol + " | " + d.device_id));
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.classList.add("ms");
      btn.textContent = "خواندن وضعیت";
      btn.addEventListener("click", async () => {
        try { jsonPanel(drBox, await api("/api/drivers/" + d.name + "/status", { method: "POST" })); }
        catch (e2) { renderError(drBox, e2); }
      });
      item.appendChild(btn);
      drBox.appendChild(item);
    });
    dBox.innerHTML = "";
    (devs.devices || []).forEach((d) => {
      const item = document.createElement("div");
      item.className = "item";
      item.textContent = d.id + " | " + d.kind + "/" + d.protocol + " | وضعیت: " + d.status +
        " | اطمینان: " + d.confidence + (d.notes ? " | " + d.notes : "");
      dBox.appendChild(item);
    });
    if (!devs.devices || !devs.devices.length) dBox.textContent = "دستگاهی ثبت نشده — ابتدا کشف را اجرا کنید.";
  } catch (err) { renderError(dBox, err); }
}

/* ---------- ایمنی ---------- */
function initSafety() {
  $("#estop-btn").addEventListener("click", async () => {
    if (!confirm("توقف اضطراری فعال شود؟ همهٔ عملیات ریسک‌دار متوقف می‌شوند.")) return;
    try { jsonPanel($("#safety-state"), await api("/api/safety/estop", { method: "POST", body: JSON.stringify({ reason: "از داشبورد" }) })); }
    catch (err) { renderError($("#safety-state"), err); }
    refreshStatus().catch(() => {});
  });
  $("#mode-apply").addEventListener("click", async () => {
    try {
      const res = await api("/api/safety/mode", {
        method: "POST",
        body: JSON.stringify({ mode: $("#mode-select").value, confirm: $("#mode-confirm").value.trim() }),
      });
      jsonPanel($("#safety-state"), res);
    } catch (err) { renderError($("#safety-state"), err); }
    refreshStatus().catch(() => {});
  });
  $("#estop-release").addEventListener("click", async () => {
    try {
      const res = await api("/api/safety/estop/release", { method: "POST", body: JSON.stringify({ confirm: $("#estop-confirm").value.trim() }) });
      jsonPanel($("#safety-state"), res);
    } catch (err) { renderError($("#safety-state"), err); }
    refreshStatus().catch(() => {});
  });
}

async function loadSafety() { jsonPanel($("#safety-state"), await api("/api/safety")); }

/* ---------- Twin ---------- */
function initTwin() {
  $("#mv-preview").addEventListener("click", async () => {
    const num = (id) => { const v = $(id).value; return v === "" ? null : Number(v); };
    try {
      const res = await api("/api/twin/preview", {
        method: "POST",
        body: JSON.stringify({ x: num("#mv-x"), y: num("#mv-y"), z: num("#mv-z"), feed: num("#mv-feed") }),
      });
      jsonPanel($("#twin-state"), res);
    } catch (err) { renderError($("#twin-state"), err); }
  });
}

async function loadTwin() { jsonPanel($("#twin-state"), await api("/api/twin")); }

/* ---------- دانش ---------- */
function initKnowledge() {
  $("#kb-search").addEventListener("click", async () => {
    const q = $("#kb-query").value.trim();
    const box = $("#kb-results");
    if (!q) return;
    try {
      const res = await api("/api/knowledge/search?q=" + encodeURIComponent(q));
      box.innerHTML = "";
      (res.hits || []).forEach((h) => {
        const item = document.createElement("div");
        item.className = "item";
        const tag = document.createElement("span");
        tag.className = "tag ok";
        tag.textContent = "امتیاز " + h.score;
        item.appendChild(tag);
        item.appendChild(document.createTextNode(" " + h.source_path + " (قطعه " + h.chunk_index + ")\n" + h.snippet));
        box.appendChild(item);
      });
      if (!(res.hits || []).length) box.textContent = "نتیجه‌ای یافت نشد — اسناد نمایه‌شده: " + res.docs_indexed;
    } catch (err) { renderError(box, err); }
  });
  $("#kb-docs").addEventListener("click", async () => {
    try { jsonPanel($("#kb-results"), await api("/api/knowledge/docs")); }
    catch (err) { renderError($("#kb-results"), err); }
  });
}

/* ---------- حافظه ---------- */
function initMemory() {
  $("#mem-search").addEventListener("click", memSearch);
  $("#mem-ops").addEventListener("click", async () => {
    try { jsonPanel($("#mem-results"), await api("/api/memory/operations")); }
    catch (err) { renderError($("#mem-results"), err); }
  });
  $("#mem-prefs").addEventListener("click", async () => {
    try { jsonPanel($("#mem-results"), await api("/api/memory/prefs")); }
    catch (err) { renderError($("#mem-results"), err); }
  });
}

async function memSearch() {
  const q = $("#mem-query").value.trim();
  try { jsonPanel($("#mem-results"), await api("/api/memory/search?q=" + encodeURIComponent(q))); }
  catch (err) { renderError($("#mem-results"), err); }
}

/* ---------- رویدادها ---------- */
function initEvents() {
  $("#events-refresh").addEventListener("click", loadEvents);
}

async function loadEvents() {
  const box = $("#events-list");
  const sev = $("#events-severity").value;
  try {
    const res = await api("/api/events?limit=120" + (sev ? "&severity=" + sev : ""));
    box.innerHTML = "";
    (res.events || []).slice().reverse().forEach((e) => {
      const item = document.createElement("div");
      item.className = "item";
      const tag = document.createElement("span");
      tag.className = "tag " + (e.severity === "critical" || e.severity === "error" ? "err" : e.severity === "warning" ? "sim" : "");
      tag.textContent = e.severity;
      item.appendChild(tag);
      item.appendChild(document.createTextNode(" " + e.ts + " [" + e.type + "] " + e.message));
      box.appendChild(item);
    });
    if (!box.children.length) box.textContent = "رویدادی ثبت نشده است.";
  } catch (err) { renderError(box, err); }
}

/* ---------- تشخیص عیب ---------- */
function initDiag() {
  $("#diag-scan").addEventListener("click", async () => {
    try { jsonPanel($("#diag-results"), await api("/api/diagnostics/scan", { method: "POST" })); }
    catch (err) { renderError($("#diag-results"), err); }
  });
  $("#diag-findings").addEventListener("click", loadFindings);
}

async function loadFindings() {
  try { jsonPanel($("#diag-results"), await api("/api/diagnostics/findings")); }
  catch (err) { renderError($("#diag-results"), err); }
}

/* ---------- راه‌اندازی ---------- */
function init() {
  initTokens();
  initTabs();
  initAgent();
  initDevices();
  initSafety();
  initTwin();
  initKnowledge();
  initMemory();
  initEvents();
  initDiag();
  loadAbout().catch(() => {});
  refreshStatus().catch(() => {});
  loadTasks().catch(() => {});
  setInterval(() => { if ($("#tabs button.active").dataset.tab === "overview") refreshStatus().catch(() => {}); }, 5000);
}

document.addEventListener("DOMContentLoaded", init);
