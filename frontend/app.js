/* CivicEase front end. Plain JavaScript, no build step.
 * Privacy: the profile is read from the form only at the moment of checking, sent once,
 * and never written to storage, URLs or logs. Text is inserted with textContent (no innerHTML).
 * Interface text comes from strings.en.json and is translated per language by /api/ui/{lang}. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    config: null, en: {}, ui: {}, scope: null, scheme: null, schemeMs: 0, match: null, explain: null,
    discover: null, lang: "en", audioUrl: null, busy: false, loadingKey: "",
  };
  const TOPICS = ["farmers", "women", "students", "health", "housing", "jobs", "business", "seniors"];
  const STORE_KEY = "civicease.lang"; // only the chosen language is remembered, never personal data

  // ------------------------------------------------------------------ text lookup
  function t(key, vars) {
    let text = state.ui[key] || state.en[key] || key;
    Object.entries(vars || {}).forEach(([k, v]) => { text = text.split("{" + k + "}").join(String(v)); });
    return text;
  }
  function opt(prefix, value) { return t(prefix + "." + value); }

  // ------------------------------------------------------------------ helpers
  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    });
    (children || []).forEach((c) => node.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return node;
  }
  function fill(list, items, makeItem) { list.replaceChildren(...items.map(makeItem)); }
  function showAlert(message, soft) {
    const box = $("alert");
    box.textContent = message;
    box.className = soft ? "alert soft" : "alert";
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function hideAlert() { $("alert").hidden = true; }
  function safeLink(url, text) {
    const a = el("a", { target: "_blank", rel: "noopener noreferrer", text: text || url });
    if (/^https?:\/\//i.test(url)) a.href = url;
    return a;
  }
  function remember(code) { try { localStorage.setItem(STORE_KEY, code); } catch (e) { /* storage may be blocked */ } }
  function recall() { try { return localStorage.getItem(STORE_KEY); } catch (e) { return null; } }

  async function api(path, options) {
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {
      throw { message: t("err.network") };
    }
    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await response.json() : await response.blob();
    if (!response.ok) throw Object.assign({ status: response.status }, data);
    return data;
  }
  function postJSON(path, body, signal) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  }
  function setBusy(on, key) {
    state.busy = on;
    state.loadingKey = on ? key : "";
    $("loading").hidden = !on;
    if (on && key) $("loading-text").textContent = t(key);
    document.querySelectorAll("main button[type=submit], .scheme-list button, .topic, #popular").forEach((b) => (b.disabled = on));
  }

  // ------------------------------------------------------------------ setup
  async function init() {
    try {
      state.en = await api("/strings.en.json");
      state.ui = state.en;
      state.config = await api("/api/config");
    } catch (e) {
      showAlert(e.message || "The service is not available right now.");
      return;
    }
    buildLanguageMenu();
    setupScope();
    setupTabs();
    setupSpeechInput();
    applyUI();
    const saved = recall();
    if (saved && saved !== "en" && state.config.languages[saved]) {
      $("lang-select").value = saved;
      await setLanguage(saved);
    }
  }

  // ------------------------------------------------------------------ apply text to the page
  function fillSelect(select, values, prefix) {
    const previous = select.value;
    select.replaceChildren(el("option", { value: "", text: t("choose") }),
      ...values.map((v) => el("option", { value: v, text: prefix ? opt(prefix, v) : v })));
    select.value = previous;
  }

  function applyUI() {
    const info = state.config.languages[state.lang];
    document.documentElement.lang = state.lang;
    document.documentElement.dir = info.rtl ? "rtl" : "ltr";
    document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => n.setAttribute("placeholder", t(n.dataset.i18nPlaceholder)));
    document.querySelectorAll("[data-i18n-aria]").forEach((n) => n.setAttribute("aria-label", t(n.dataset.i18nAria)));

    const c = state.config;
    fillSelect($("scope-state-select"), c.states, "state");
    fillSelect($("f-state"), c.states, "state");
    fillSelect($("f-occupation"), c.occupations, "occ");
    fillSelect($("f-category"), c.categories, "cat");
    fillSelect($("f-gender"), c.genders, "gen");
    fillSelect($("f-business"), c.business_types, "biz");
    $("link-policy").textContent = Array.isArray(c.link_policy)
      ? t("own.link.policy.only", { sites: c.link_policy.join(", ") })
      : t("own.link.policy.any");
    const note = $("mode-note");
    if (!c.discovery) { note.textContent = t("mode.nosearch"); note.hidden = false; }
    else if (c.ai_mode === "demo") { note.textContent = t("mode.noai"); note.hidden = false; }
    else note.hidden = true;
    fill($("topics"), TOPICS, (k) => {
      const b = el("button", { type: "button", class: "chip topic", text: t("topic." + k) });
      b.addEventListener("click", () => { $("ask-input").value = t("topic." + k); search(); });
      return b;
    });
    if (state.scope) $("scope-label").textContent = scopeLabel();
    if (state.discover) renderDiscover();
    if (state.scheme) renderScheme();
    if (state.explain) renderResult();
    if (state.loadingKey) $("loading-text").textContent = t(state.loadingKey);
  }

  // ------------------------------------------------------------------ language (top right)
  function buildLanguageMenu() {
    const select = $("lang-select");
    select.replaceChildren(...Object.entries(state.config.languages).map(([code, info]) => {
      const text = code === "en" ? "English" : info.native + " (" + info.name + ")";
      return el("option", { value: code, lang: code, text });
    }));
    select.value = state.lang;
    select.addEventListener("change", () => setLanguage(select.value));
  }

  async function setLanguage(code) {
    hideAlert();
    $("ui-note").hidden = true;
    resetAudio();
    if (code === "en") {
      state.ui = state.en;
    } else {
      setBusy(true, "ui.translating");
      try {
        const data = await api("/api/ui/" + encodeURIComponent(code));
        state.ui = data.strings;
        if (!data.translated) {
          $("ui-note").textContent = state.en["ui.failed"];
          $("ui-note").hidden = false;
        }
      } catch (e) {
        state.ui = state.en;
        $("ui-note").textContent = state.en["ui.failed"];
        $("ui-note").hidden = false;
      } finally { setBusy(false); }
    }
    state.lang = code;
    $("lang-select").value = code;
    remember(code);
    applyUI();
    if (state.scheme && state.match) await runExplain();
  }

  // ------------------------------------------------------------------ scope: national or state
  function scopeLabel() {
    return state.scope.level === "national" ? t("scope.label.national") : t("scope.label.state", { state: opt("state", state.scope.state) });
  }

  function setupScope() {
    $("scope-national").addEventListener("click", () => chooseScope("national", null));
    $("scope-state").addEventListener("click", () => {
      const open = $("state-pick").hidden;
      $("state-pick").hidden = !open;
      $("scope-state").setAttribute("aria-expanded", String(open));
      if (open) $("scope-state-select").focus();
    });
    $("state-pick").addEventListener("submit", (e) => {
      e.preventDefault();
      const chosen = $("scope-state-select").value;
      if (!chosen) return showAlert(t("scope.err.state"), true);
      chooseScope("state", chosen);
    });
    $("scope-change").addEventListener("click", () => {
      state.scope = null;
      state.discover = null;
      hideAlert();
      ["scope-bar", "find-card", "scheme-card", "profile-card", "result-card"].forEach((id) => ($(id).hidden = true));
      $("scope-card").hidden = false;
      $("scope-card").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function chooseScope(level, stateName) {
    hideAlert();
    state.scope = { level, state: stateName };
    state.scheme = state.match = state.explain = state.discover = null;
    $("scope-label").textContent = scopeLabel();
    $("scope-card").hidden = true;
    $("scope-bar").hidden = false;
    $("find-card").hidden = false;
    ["scheme-card", "profile-card", "result-card"].forEach((id) => ($(id).hidden = true));
    $("ask-results").replaceChildren();
    $("sources").hidden = true;
    $("ask-input").value = "";
    $("find-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ------------------------------------------------------------------ own document tabs
  function setupTabs() {
    const tabs = Array.from(document.querySelectorAll("[role=tab]"));
    const select = (tab) => {
      tabs.forEach((tb) => {
        const on = tb === tab;
        tb.setAttribute("aria-selected", String(on));
        tb.tabIndex = on ? 0 : -1;
        $(tb.getAttribute("aria-controls")).hidden = !on;
      });
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        select(next);
        next.focus();
      });
    });
    $("form-upload").addEventListener("submit", (e) => {
      e.preventDefault();
      const file = $("file-input").files[0];
      if (!file) return showAlert(t("own.choose_file"), true);
      const form = new FormData();
      form.append("file", file);
      ingest(form);
    });
    $("form-link").addEventListener("submit", (e) => {
      e.preventDefault();
      const form = new FormData();
      form.append("url", $("link-input").value.trim());
      ingest(form);
    });
    $("form-paste").addEventListener("submit", (e) => {
      e.preventDefault();
      const form = new FormData();
      form.append("text", $("paste-input").value);
      ingest(form);
    });
    $("form-ask").addEventListener("submit", (e) => { e.preventDefault(); search(); });
    $("popular").addEventListener("click", () => { $("ask-input").value = ""; search(); });
  }

  // ------------------------------------------------------------------ live discovery
  function schemeButton(item) {
    const parts = [el("span", { class: "nm", text: item.name })];
    if (item.summary) parts.push(el("span", { class: "sm", text: item.summary }));
    if (item.authority) parts.push(el("span", { class: "au", text: item.authority }));
    const b = el("button", { type: "button" }, parts);
    b.addEventListener("click", () => loadDiscovered(item));
    const li = el("li", {}, [b]);
    if (item.url) li.appendChild(el("div", { class: "off" }, [safeLink(item.url, t("find.official"))]));
    return li;
  }

  async function search() {
    if (!state.scope) return;
    hideAlert();
    const query = $("ask-input").value.trim();
    setBusy(true, "find.loading");
    try {
      state.discover = await postJSON("/api/discover", { level: state.scope.level, state: state.scope.state, query });
      renderDiscover();
      if (state.discover.personal_details_removed) showAlert(t("find.pii"), true);
    } catch (e) { showAlert(e.message || t("find.failed")); }
    finally { setBusy(false); }
  }

  function renderDiscover() {
    const data = state.discover;
    const list = $("ask-results");
    if (!data.schemes.length) list.replaceChildren(el("li", { class: "hint", text: t("find.none") }));
    else fill(list, data.schemes, schemeButton);
    $("sources").hidden = false;
    if (data.sources.length) fill($("sources-list"), data.sources, (s) => el("li", {}, [safeLink(s.url, s.title || s.url)]));
    else $("sources-list").replaceChildren(el("li", { text: t("find.nosource") }));
  }

  async function loadDiscovered(item) {
    hideAlert();
    setBusy(true, "scheme.loading");
    try {
      const data = await postJSON("/api/scheme-details", {
        level: state.scope.level, state: state.scope.state, name: item.name, url: item.url || "",
      });
      acceptScheme(data.scheme, data.elapsed_ms);
    } catch (e) { showAlert(e.message || t("scheme.failed")); }
    finally { setBusy(false); }
  }

  async function ingest(form) {
    hideAlert();
    setBusy(true, "own.loading");
    try {
      const data = await api("/api/ingest", { method: "POST", body: form });
      acceptScheme(data.scheme, data.elapsed_ms);
    } catch (e) {
      showAlert(e.message || t("own.failed"));
    } finally { setBusy(false); }
  }

  function acceptScheme(scheme, ms) {
    state.scheme = scheme;
    state.schemeMs = ms;
    state.match = null;
    state.explain = null;
    resetAudio();
    $("result-card").hidden = true;
    renderScheme();
    $("scheme-card").hidden = false;
    $("profile-card").hidden = false;
    prefillState();
    $("scheme-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderScheme() {
    const scheme = state.scheme;
    $("scheme-name").textContent = scheme.name;
    const meta = [scheme.authority, state.schemeMs ? t("scheme.read_in", { sec: (state.schemeMs / 1000).toFixed(1) }) : ""].filter(Boolean);
    $("scheme-meta").textContent = meta.join(" | ");
    $("scheme-summary").textContent = scheme.summary;
    fill($("scheme-warnings"), scheme.warnings || [], (w) => el("li", { text: w }));
    const rules = scheme.eligibility.map((r) => r.text).concat(scheme.exclusions.map((r) => t("scheme.notallowed", { text: r.text })));
    fill($("scheme-rules"), rules.length ? rules : [t("scheme.none")], (x) => el("li", { text: x }));
    fill($("scheme-links"), scheme.official_sources || [], (u) =>
      el("li", {}, [safeLink(u, t("scheme.source", { url: u.replace(/^https?:\/\//, "").slice(0, 60) }))]));
  }

  // ------------------------------------------------------------------ profile and matching
  function prefillState() {
    if (state.scope && state.scope.state && !$("f-state").value) $("f-state").value = state.scope.state;
  }
  function readProfile() {
    const profile = {};
    const text = (id, key) => { const v = $(id).value; if (v) profile[key] = v; };
    text("f-state", "state"); text("f-occupation", "occupation"); text("f-category", "category");
    text("f-gender", "gender"); text("f-business", "business_type");
    if ($("f-income").value !== "") profile.annual_income_lakh = parseFloat($("f-income").value);
    if ($("f-age").value !== "") profile.age = parseInt($("f-age").value, 10);
    return profile;
  }
  function clearProfile() {
    $("form-profile").reset();
    document.querySelectorAll(".field.missing").forEach((f) => f.classList.remove("missing"));
    prefillState(); // the state you picked on the first screen is only a filter, not personal data
  }
  function markMissing(fields) {
    document.querySelectorAll(".field").forEach((f) => f.classList.toggle("missing", fields.includes(f.dataset.field)));
    const first = document.querySelector(".field.missing select, .field.missing input");
    if (first) first.focus();
  }

  async function check(e) {
    e.preventDefault();
    hideAlert();
    if (!state.scheme) return;
    const profile = readProfile();
    setBusy(true, "profile.checking");
    try {
      state.match = await postJSON("/api/match", { scheme: state.scheme, profile });
      document.querySelectorAll(".field.missing").forEach((f) => f.classList.remove("missing"));
      if (!$("keep").checked) clearProfile(); // wipe the details as soon as the answer is back
      await runExplain();
    } catch (err) {
      if (err.error === "missing_fields") {
        markMissing(err.missing);
        showAlert(t("profile.missing") + " " + (err.labels || []).join(", "), true);
      } else {
        showAlert(err.message || t("profile.failed"));
      }
    } finally { setBusy(false); }
  }

  async function runExplain() {
    setBusy(true, "result.preparing");
    try {
      state.explain = await postJSON("/api/explain", { scheme: state.scheme, match: state.match, language: state.lang });
      renderResult();
      $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) { showAlert(err.message || t("result.failed")); }
    finally { setBusy(false); }
  }

  function renderResult() {
    const ex = state.explain, s = ex.sections;
    const result = $("result-card");
    result.lang = ex.language;
    const verdict = $("verdict");
    const icon = { eligible: "✔", ineligible: "✖", conditional: "?" }[state.match.verdict];
    verdict.className = "verdict " + state.match.verdict;
    verdict.replaceChildren(el("span", { class: "ico", "aria-hidden": "true", text: icon }), el("span", { text: s.eligible.verdict_text }));
    const note = $("translation-note");
    note.hidden = ex.notice !== "translation_unavailable";
    note.textContent = t("result.note");

    $("t-what").textContent = s.what.title;
    $("t-eligible").textContent = s.eligible.title;
    $("t-documents").textContent = s.documents.title;
    $("t-how").textContent = s.how.title;
    fill($("b-what"), s.what.items, (x) => el("li", { text: x }));
    fill($("b-eligible"), s.eligible.items, (x, i) => {
      const status = state.match.results[i] ? state.match.results[i].status : "check";
      const mark = { pass: "✔", fail: "✖", check: "?" }[status];
      return el("li", { class: status }, [el("span", { class: "mark", "aria-hidden": "true", text: mark }), el("span", { text: x })]);
    });
    fill($("b-documents"), s.documents.items, (x) => el("li", { text: x }));
    fill($("b-how"), s.how.items, (x) => el("li", { text: x }));
    $("disclaimer").textContent = ex.disclaimer;
    result.hidden = false;
  }

  // ------------------------------------------------------------------ audio
  function resetAudio() {
    if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
    state.audioUrl = null;
    const player = $("player");
    player.pause();
    player.removeAttribute("src");
    player.hidden = true;
    $("device-voice").hidden = true;
    $("audio-status").textContent = "";
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }

  async function listen() {
    if (!state.explain) return;
    const status = $("audio-status"), player = $("player"), button = $("listen");
    if (state.audioUrl) { player.hidden = false; player.play().catch(() => {}); return; }
    button.disabled = true;
    status.textContent = t("audio.preparing");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 25000);
    try {
      const blob = await postJSON("/api/speak", { text: state.explain.script, language: state.explain.language }, controller.signal);
      state.audioUrl = URL.createObjectURL(blob);
      player.src = state.audioUrl;
      player.hidden = false;
      status.textContent = "";
      player.play().catch(() => { status.textContent = t("audio.press_play"); });
    } catch (err) {
      status.textContent = (err && err.message) || t("audio.slow");
      if ("speechSynthesis" in window) $("device-voice").hidden = false;
    } finally {
      clearTimeout(timer);
      button.disabled = false;
    }
  }

  function deviceVoice() {
    if (!state.explain || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(state.explain.script);
    utterance.lang = state.explain.bcp47;
    utterance.onerror = () => { $("audio-status").textContent = t("audio.nodevice"); };
    window.speechSynthesis.speak(utterance);
  }

  // ------------------------------------------------------------------ voice input
  function setupSpeechInput() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return;
    const mic = $("mic");
    mic.hidden = false;
    mic.addEventListener("click", () => {
      const rec = new Recognition();
      rec.lang = state.config.languages[state.lang].bcp47;
      rec.interimResults = false;
      rec.onresult = (ev) => { $("ask-input").value = ev.results[0][0].transcript; search(); };
      rec.onerror = () => showAlert(t("find.mic.err"), true);
      rec.start();
    });
  }

  // ------------------------------------------------------------------ wire up
  $("form-profile").addEventListener("submit", check);
  $("clear").addEventListener("click", clearProfile);
  $("listen").addEventListener("click", listen);
  $("device-voice").addEventListener("click", deviceVoice);
  window.addEventListener("pagehide", () => { clearProfile(); resetAudio(); });
  init();
})();
