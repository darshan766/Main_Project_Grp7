/* Resume Analyzer — frontend
 * Talks to the FastAPI backend (same origin by default).
 * To point at a backend running elsewhere: open index.html?api=http://localhost:8000
 */
(() => {
  "use strict";

  const API_ROOT = (new URLSearchParams(location.search).get("api") || window.API_BASE || "").replace(/\/$/, "");
  const API = API_ROOT + "/api";
  const MAX_MB = 5;
  const ALLOWED = [".pdf", ".docx"];

  const SAMPLE_JD =
    "Backend Engineer\n\nRequired: Python, FastAPI or Django, SQL (PostgreSQL), REST API design, Git, strong communication.\n\nPreferred: Docker, Kubernetes, AWS, Machine Learning exposure.";

  /* ---------- tiny DOM helpers (all text goes through textContent: resume text is untrusted) ---------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  function h(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "style") node.setAttribute("style", v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }
  const clear = (node) => { node.replaceChildren(); return node; };

  /* ---------- state ---------- */
  const state = { id: null, profile: null, ats: null, feedback: null, fbLoading: false };
  let suppressHash = false;
  let loadingTimer = null;

  const views = { upload: $("#view-upload"), loading: $("#view-loading"), results: $("#view-results") };
  function show(name) {
    for (const [k, v] of Object.entries(views)) v.hidden = k !== name;
    $("#resetBtn").hidden = name !== "results";
    window.scrollTo({ top: 0 });
  }

  /* ---------- networking ---------- */
  async function api(path, options = {}) {
    let res;
    try {
      res = await fetch(API + path, options);
    } catch {
      throw new Error(
        `Can't reach the analyzer service${API_ROOT ? " at " + API_ROOT : ""}. Check that it's running (uvicorn app.main:app) and try again.`
      );
    }
    let body = null;
    try { body = await res.json(); } catch { /* non-JSON body */ }
    if (!res.ok) {
      const err = new Error(formatDetail(body && body.detail) || `The service returned an error (${res.status}).`);
      err.status = res.status;
      throw err;
    }
    return body;
  }
  function formatDetail(d) {
    if (!d) return "";
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => e.msg || JSON.stringify(e)).join("; ");
    return JSON.stringify(d);
  }

  /* ---------- toast ---------- */
  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 4200);
  }

  /* ---------- upload flow ---------- */
  const dropzone = $("#dropzone");
  const fileInput = $("#fileInput");

  function uploadError(msg) {
    const box = $("#uploadError");
    box.textContent = msg || "";
    box.hidden = !msg;
  }

  function validateFile(file) {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED.includes(ext)) return `“${file.name}” isn't a supported type. Upload a PDF or DOCX file.`;
    if (file.size > MAX_MB * 1024 * 1024) return `That file is ${(file.size / 1048576).toFixed(1)} MB. The limit is ${MAX_MB} MB.`;
    if (file.size === 0) return "That file is empty.";
    return "";
  }

  async function handleFile(file) {
    uploadError("");
    const problem = validateFile(file);
    if (problem) return uploadError(problem);

    startLoading();
    try {
      const form = new FormData();
      form.append("file", file);
      const { resume_id } = await api("/resume/upload", { method: "POST", body: form });
      const [profile, ats] = await Promise.all([
        api(`/resume/${resume_id}`),
        api(`/resume/${resume_id}/ats-score`),
      ]);
      openResults(resume_id, profile, ats, true);
    } catch (err) {
      stopLoading();
      show("upload");
      uploadError(err.message);
    } finally {
      fileInput.value = "";
    }
  }

  function startLoading() {
    show("loading");
    $("#loadingTitle").textContent = "Reading your resume…";
    $("#loadingSub").textContent = "Extracting text, finding sections, scoring ATS checks.";
    clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => {
      $("#loadingSub").textContent = "Still working. The first upload can take longer while the language models load.";
    }, 7000);
  }
  function stopLoading() { clearTimeout(loadingTimer); }

  fileInput.addEventListener("change", () => fileInput.files[0] && handleFile(fileInput.files[0]));
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("is-over"); $("#dropTitle").textContent = "Release to analyze"; })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("is-over"); $("#dropTitle").textContent = "Drop your resume here"; })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) {
      if (files.length > 1) toast("One resume at a time. Using the first file.");
      handleFile(files[0]);
    }
  });
  // Don't let a missed drop navigate the browser to the file
  ["dragover", "drop"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));

  /* ---------- results ---------- */
  function openResults(id, profile, ats, updateHash) {
    stopLoading();
    Object.assign(state, { id, profile, ats, feedback: null, fbLoading: false });
    if (updateHash) { suppressHash = true; location.hash = `#/r/${id}`; }

    renderSheet(profile);
    renderAts(ats, profile);
    clear($("#jdResult")); $("#jdText").value = ""; $("#jdError").hidden = true;
    clear($("#pane-fb"));
    selectTab("ats");
    show("results");
  }

  async function loadFromHash() {
    const m = location.hash.match(/^#\/r\/([\w-]+)$/);
    if (!m) { stopLoading(); show("upload"); return; }
    if (state.id === m[1] && state.profile) { show("results"); return; }
    startLoading();
    $("#loadingTitle").textContent = "Reopening your analysis…";
    try {
      const [profile, ats] = await Promise.all([api(`/resume/${m[1]}`), api(`/resume/${m[1]}/ats-score`)]);
      openResults(m[1], profile, ats, false);
    } catch (err) {
      stopLoading();
      suppressHash = true; location.hash = "#/";
      show("upload");
      uploadError(err.status === 404 ? "We couldn't find that analysis. Upload the resume again to get a fresh one." : err.message);
    }
  }
  window.addEventListener("hashchange", () => {
    if (suppressHash) { suppressHash = false; return; }
    loadFromHash();
  });

  $("#resetBtn").addEventListener("click", () => {
    Object.assign(state, { id: null, profile: null, ats: null, feedback: null });
    uploadError("");
    suppressHash = true; location.hash = "#/";
    show("upload");
  });
  $("#brand").addEventListener("click", (e) => {
    if (state.id) { e.preventDefault(); $("#resetBtn").click(); }
  });

  /* ---------- parsed resume sheet ---------- */
  function renderSheet(p) {
    const sheet = clear($("#sheet"));
    const c = p.contact || {};
    const skills = p.skills || {};

    sheet.append(
      h("h2", { class: "name" }, c.name || "Name not detected"),
      h("div", { class: "contact" },
        contactBit(c.email, "No email found", true),
        contactBit(c.phone, "No phone found", true),
        contactBit(c.location),
        contactBit(c.linkedin)
      )
    );

    if (p.summary) sheet.append(section("Summary", h("p", { class: "summary" }, p.summary)));

    const groups = [
      ["Technical", skills.technical],
      ["Tools", skills.tools],
      ["Soft skills", skills.soft],
    ].filter(([, list]) => list && list.length);
    let idx = 0;
    sheet.append(section("Skills found",
      groups.length
        ? groups.map(([label, list]) =>
            h("div", { class: "chip-group" },
              h("div", { class: "chip-group-label" }, label),
              h("div", { class: "skills" }, list.map((s) => h("span", { class: "skill", style: `--i:${idx++}` }, s)))))
        : h("p", { class: "empty-note" }, "No skills from the known skills list were detected.")
    ));

    const exp = p.experience || [];
    sheet.append(section("Experience",
      exp.length
        ? exp.map((e) => h("div", { class: "entry" },
            h("div", { class: "entry-head" },
              h("span", { class: "entry-title" }, e.title || "Untitled role"),
              h("span", { class: "entry-sub" }, dateRange(e.start_date, e.end_date))),
            e.company && h("div", { class: "entry-sub" }, e.company),
            e.description && h("p", { class: "entry-desc" }, e.description)))
        : h("p", { class: "empty-note" }, "No experience section was detected.")
    ));

    const edu = p.education || [];
    sheet.append(section("Education",
      edu.length
        ? edu.map((e) => h("div", { class: "entry" },
            h("div", { class: "entry-head" },
              h("span", { class: "entry-title" }, e.degree || "Degree not detected"),
              h("span", { class: "entry-sub" }, dateRange(e.start_year, e.end_year))),
            h("div", { class: "entry-sub" }, [e.institution, e.gpa != null ? `GPA ${e.gpa}` : null].filter(Boolean).join(" · "))))
        : h("p", { class: "empty-note" }, "No education section was detected.")
    ));

    const projects = p.projects || [];
    if (projects.length) sheet.append(section("Projects", projects.map((pr) =>
      h("div", { class: "entry" },
        h("span", { class: "entry-title" }, pr.title || "Untitled project"),
        pr.description && h("p", { class: "entry-desc" }, pr.description)))));

    const certs = p.certifications || [];
    if (certs.length) sheet.append(section("Certifications", h("ul", { class: "entry-desc", style: "padding-left:1.1em;margin:0" }, certs.map((c2) => h("li", null, c2)))));

    const conf = p.parsed_confidence_score ?? 0;
    if (conf < 0.6) {
      sheet.append(h("p", { class: "parse-note" },
        `We could only read ${Math.round(conf * 100)}% of the key fields with confidence. If something above looks wrong, the layout may be hard for software to read.`));
    }
  }
  function section(title, ...body) { return h("section", null, h("h3", null, title), ...body); }
  function contactBit(value, missingText, flagMissing) {
    if (value) return h("span", null, value);
    return flagMissing ? h("span", { class: "missing" }, missingText) : null;
  }
  function dateRange(a, b) {
    if (a == null && b == null) return "";
    return `${a ?? "?"} – ${b ?? "Present"}`;
  }

  /* ---------- ATS pane ---------- */
  const tone = (n) => (n >= 80 ? "good" : n >= 60 ? "mid" : "bad");

  function renderAts(ats, profile) {
    const pane = clear($("#pane-ats"));
    const score = ats.ats_score ?? 0;
    const t = tone(score);
    const passed = Math.round(score / 20);
    const verdict = score >= 100 ? "Passes every check" : score >= 80 ? "Nearly there" : score >= 60 ? "Some details may be lost" : "Likely to lose information";

    pane.append(
      h("div", null,
        h("div", { class: "score-head" },
          h("div", { class: "score-num" }, String(score), h("small", null, "/ 100")),
          h("div", { class: `verdict ${t}` }, verdict)),
        h("div", { class: "gauge", role: "img", "aria-label": `${passed} of 5 ATS checks passed` },
          [0, 1, 2, 3, 4].map((i) => h("span", { class: i < passed ? `on ${t}` : "" }))),
        h("p", { class: "gauge-cap" }, `${passed} of 5 checks passed: standard sections, email, phone, length, and clean text.`))
    );

    const issues = ats.issues || [];
    pane.append(
      issues.length
        ? h("div", null,
            h("h3", { class: "block-title" }, "Fix these first"),
            h("ul", { class: "notes" }, issues.map((i) => h("li", null, i))))
        : h("div", { class: "allgood" }, "Nothing to fix here. A screening system should read this resume cleanly.")
    );

    const conf = Math.round((profile.parsed_confidence_score ?? 0) * 100);
    const fill = h("i", { style: "width:0%" });
    pane.append(h("div", { class: "parse-meter" },
      h("h3", { class: "block-title", style: "margin-bottom:4px" }, "How much we could read"),
      h("div", { class: "meter" }, fill),
      h("div", { class: "meter-row" },
        h("span", null, "Name, email, skills, education and experience found"),
        h("span", null, `${conf}%`))));
    requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = conf + "%")));
  }

  /* ---------- tabs ---------- */
  const tabBtns = $$('[role="tab"]');
  function selectTab(name, focus) {
    for (const b of tabBtns) {
      const on = b.dataset.tab === name;
      b.setAttribute("aria-selected", on);
      b.tabIndex = on ? 0 : -1;
      $("#pane-" + b.dataset.tab).hidden = !on;
      if (on && focus) b.focus();
    }
    if (name === "fb") loadFeedback();
  }
  tabBtns.forEach((b, i) => {
    b.addEventListener("click", () => selectTab(b.dataset.tab));
    b.addEventListener("keydown", (e) => {
      const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (dir) { e.preventDefault(); selectTab(tabBtns[(i + dir + tabBtns.length) % tabBtns.length].dataset.tab, true); }
    });
  });

  /* ---------- job match ---------- */
  $("#jdSample").addEventListener("click", () => { $("#jdText").value = SAMPLE_JD; $("#jdText").focus(); });

  $("#jdForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#jdError"); err.hidden = true;
    const text = $("#jdText").value.trim();
    if (text.length < 20) {
      err.textContent = "Paste the full job description. A few words isn't enough to find skills.";
      err.hidden = false; $("#jdText").focus(); return;
    }
    const btn = $("#jdSubmit");
    btn.disabled = true; btn.textContent = "Matching…";
    try {
      const res = await api(`/resume/${state.id}/match-jd`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: text }),
      });
      renderJd(res);
      $("#jdResult").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false;
    } finally {
      btn.disabled = false; btn.textContent = "Match against this job";
    }
  });

  function renderJd(r) {
    const box = clear($("#jdResult"));
    const all = [r.matched_skills, r.missing_critical_skills, r.missing_preferred_skills].flat();
    if (!all.length) {
      box.append(h("div", { class: "fit" },
        h("ul", { class: "notes" }, h("li", null,
          h("span", { class: "where" }, "No skills recognised"),
          "We couldn't find any skills from our skills list in that description, so there's nothing to score. Try the full posting, with skills named explicitly."))));
      return;
    }
    const t = tone(r.jd_fit_score);
    const fill = h("i", { class: t, style: "width:0%" });
    box.append(h("div", { class: "fit" },
      h("h3", { class: "block-title", style: "margin:0" }, "How well you fit"),
      h("div", { class: "fit-num" }, String(r.jd_fit_score), h("small", null, "/ 100")),
      h("div", { class: "meter" }, fill)));
    requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = r.jd_fit_score + "%")));

    box.append(...[
      r.missing_critical_skills.length
        ? group("Required skills missing from your resume", "These are listed as requirements. Add them if you have the experience.", r.missing_critical_skills, "crit")
        : h("div", { class: "allgood" }, "Your resume covers every required skill we detected."),
      r.matched_skills.length > 0 && group("Skills you have that they want", null, r.matched_skills, "match"),
      r.missing_preferred_skills.length > 0 && group("Nice-to-haves you're missing", "Listed as preferred. Not blockers.", r.missing_preferred_skills, "pref"),
      r.transferable_skills.length > 0 && group("Related skills you could lean on", "Close enough to a missing skill that it's worth mentioning how they connect.", r.transferable_skills, "xfer")
    ].filter(Boolean));
  }
  function group(title, why, list, cls) {
    return h("div", { class: "group" },
      h("h4", null, title),
      why && h("p", { class: "why" }, why),
      h("div", { class: "chips" }, list.map((s) => h("span", { class: `chip ${cls}` }, s))));
  }

  /* ---------- feedback ---------- */
  async function loadFeedback() {
    const pane = $("#pane-fb");
    if (state.feedback) return;       // already rendered
    if (state.fbLoading) return;
    state.fbLoading = true;
    clear(pane).append(h("div", { class: "fb-loading" }, h("span", { class: "spinner" }), "Reading your bullet points. This can take a few seconds when AI feedback is on."));
    try {
      const res = await api(`/resume/${state.id}/feedback`);
      state.feedback = res.suggestions || [];
      renderFeedback(state.feedback);
    } catch (ex) {
      clear(pane).append(
        h("p", { class: "form-error" }, ex.message),
        h("button", { class: "btn btn-ghost retry", type: "button" }, "Try again"));
      $(".retry", pane).addEventListener("click", loadFeedback);
    } finally {
      state.fbLoading = false;
    }
  }

  function renderFeedback(list) {
    const pane = clear($("#pane-fb"));
    if (!list.length) {
      pane.append(
        h("div", { class: "allgood" }, "No suggestions came back for this resume."),
        h("p", { class: "muted", style: "font-size:.9rem" }, "Deeper, AI-written suggestions appear here when the service has an Anthropic API key set."));
      return;
    }
    const bySection = new Map();
    for (const s of list) {
      if (!bySection.has(s.section)) bySection.set(s.section, []);
      bySection.get(s.section).push(s.suggestion);
    }
    pane.append(h("h3", { class: "block-title", style: "margin:0" }, `${list.length} ${list.length === 1 ? "suggestion" : "suggestions"}`));
    for (const [sec, items] of bySection) {
      pane.append(h("ul", { class: "notes" },
        items.map((txt) => h("li", null, h("span", { class: "where" }, sec), txt))));
    }
  }

  /* ---------- boot ---------- */
  loadFromHash();
})();
