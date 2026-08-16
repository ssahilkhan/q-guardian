/* Q-Guardian Console — application logic (vanilla JS, no dependencies). */

(function () {
  "use strict";

  var API = "/api/v1";

  /* ---------------------------------------------------------- utilities */

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function truncate(value, max) {
    var text = String(value == null ? "" : value);
    if (text.length <= max) return text;
    return text.slice(0, max) + "…";
  }

  function fmtTime(value) {
    if (!value) return "—";
    var d = new Date(value);
    return isNaN(d.getTime()) ? String(value) : d.toLocaleString();
  }

  function fmtNumber(value, digits) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    return n.toFixed(digits == null ? 2 : digits);
  }

  function elem(html) {
    var tpl = document.createElement("template");
    tpl.innerHTML = html.trim();
    return tpl.content.firstElementChild;
  }

  function showToast(message) {
    var toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(function () {
      toast.classList.add("hidden");
    }, 3200);
  }

  function decisionClass(decision) {
    var d = String(decision || "").toUpperCase();
    if (d === "ALLOW") return "allow";
    if (d === "WARN") return "warn";
    if (d === "REVIEW") return "review";
    if (d === "BLOCK") return "block";
    return "invalid";
  }

  function severityClass(severity) {
    return "sev-" + String(severity || "info").toLowerCase();
  }

  function badgeClass(decision) {
    var d = String(decision || "").toUpperCase();
    if (d === "ALLOW") return "green";
    if (d === "WARN") return "amber";
    if (d === "REVIEW") return "orange";
    if (d === "BLOCK") return "red";
    return "muted";
  }

  async function api(path, options) {
    var response = await fetch(API + path, options);
    var body = await response.json().catch(function () { return null; });
    if (!response.ok || !body || body.success === false) {
      var detail = body && (body.detail || (body.error && (body.error.message || body.error)));
      if (typeof detail === "object") detail = JSON.stringify(detail);
      throw new Error(detail || ("Request failed with status " + response.status));
    }
    return body.data;
  }

  /* ---------------------------------------------------------- routing */

  var routes = ["overview", "scanner", "history", "rules", "models", "configuration", "about"];

  function navigate() {
    var hash = window.location.hash.replace(/^#\/?/, "");
    var name = routes.indexOf(hash) !== -1 ? hash : "overview";
    routes.forEach(function (r) {
      var view = document.getElementById("view-" + r);
      if (view) view.classList.toggle("active", r === name);
      var tab = document.querySelector('.tab[data-tab="' + r + '"]');
      if (tab) tab.classList.toggle("active", r === name);
    });
    window.scrollTo(0, 0);
    loadView(name);
  }

  function loadView(name) {
    if (name === "overview") loadOverview();
    if (name === "history") loadHistory();
    if (name === "rules") loadRules();
    if (name === "models") loadModels();
    if (name === "configuration") loadConfiguration();
  }

  window.addEventListener("hashchange", navigate);

  /* ---------------------------------------------------------- status */

  async function refreshStatus() {
    try {
      var data = await api("/system/status");
      var ok = data && data.status === "operational";
      document.getElementById("statusDot").className = "pulse " + (ok ? "ok" : "down");
      document.getElementById("statusText").textContent = ok ? "Operational" : "Degraded";
    } catch (err) {
      document.getElementById("statusDot").className = "pulse down";
      document.getElementById("statusText").textContent = "Offline";
    }
  }

  async function refreshVersion() {
    try {
      var data = await api("/system/version");
      document.getElementById("versionInfo").textContent =
        (data ? data.application : "Q-Guardian") + " v" + (data ? data.version : "?");
    } catch (e) {
      document.getElementById("versionInfo").textContent = "Q-Guardian";
    }
  }

  /* ---------------------------------------------------------- renderers */

  function renderDecisionBanner(item) {
    var payload = item.payload || {};
    var decision = String(item.decision || payload.decision || "UNKNOWN");
    var cls = decisionClass(decision);
    var recommendation = payload.recommendation || "No recommendation provided.";
    var html =
      '<div class="banner ' + cls + '">' +
        '<div class="banner-title">' +
          "<span>" + escapeHtml(decision) + "</span>" +
          '<span class="badge">risk ' + fmtNumber(item.risk_score, 3) + "</span>" +
        "</div>" +
        "<p>" + escapeHtml(recommendation) + "</p>" +
      "</div>";
    return html;
  }

  function renderMeta(item) {
    var payload = item.payload || {};
    return (
      '<div class="detail-list">' +
        '<div class="detail-row"><span class="k">Analysis ID</span><span class="v">' + escapeHtml(item.analysis_id) + "</span></div>" +
        '<div class="detail-row"><span class="k">Timestamp</span><span class="v">' + escapeHtml(fmtTime(item.timestamp || payload.timestamp)) + "</span></div>" +
        '<div class="detail-row"><span class="k">Processing time</span><span class="v">' + fmtNumber(item.processing_time_ms, 2) + " ms</span></div>" +
        '<div class="detail-row"><span class="k">Validation</span><span class="v">' + escapeHtml(payload.validation_status || (item.is_valid ? "valid" : "invalid")) + "</span></div>" +
        '<div class="detail-row"><span class="k">Truncated</span><span class="v">' + (payload.truncated ? "yes" : "no") + "</span></div>" +
      "</div>"
    );
  }

  function renderFindings(findings) {
    if (!findings || !findings.length) {
      return '<p class="muted">No findings — input is considered safe.</p>';
    }
    var ordered = findings.slice().sort(function (a, b) {
      var order = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
      return (order[String(a.severity).toLowerCase()] ?? 5) - (order[String(b.severity).toLowerCase()] ?? 5);
    });
    var html = ordered.map(function (f) {
      var sev = String(f.severity || "info").toUpperCase();
      return (
        '<div class="finding ' + severityClass(f.severity) + '">' +
          '<div class="finding-head">' +
            '<span class="sev">' + escapeHtml(sev) + "</span>" +
            "<span>" + escapeHtml(f.category || "finding") + "</span>" +
          "</div>" +
          "<p>" + escapeHtml(f.description || "") + "</p>" +
          (f.matched_text ? "<pre>" + escapeHtml(f.matched_text) + "</pre>" : "") +
          '<div class="meta">confidence ' + fmtNumber(f.confidence, 3) +
            (f.detected_at ? " · " + escapeHtml(fmtTime(f.detected_at)) : "") + "</div>" +
        "</div>"
      );
    }).join("");
    return html;
  }

  function renderFeatures(features) {
    if (!features || !Object.keys(features).length) {
      return '<p class="muted">No features extracted.</p>';
    }
    var items = Object.keys(features).sort().map(function (key) {
      var value = features[key];
      var display = typeof value === "object" ? JSON.stringify(value) : value;
      return (
        '<div class="feature-item">' +
          '<div class="k">' + escapeHtml(key) + "</div>" +
          '<div class="v">' + escapeHtml(display) + "</div>" +
        "</div>"
      );
    }).join("");
    return '<div class="feature-grid">' + items + "</div>";
  }

  function renderFullResult(item) {
    var payload = item.payload || {};
    return (
      renderDecisionBanner(item) +
      '<div class="card">' +
        "<h3>Overview</h3>" + renderMeta(item) +
      "</div>" +
      '<div class="card">' +
        "<h3>Findings (" + item.finding_count + ")</h3>" + renderFindings(payload.findings) +
      "</div>" +
      '<div class="card">' +
        "<h3>Features</h3>" + renderFeatures(payload.features) +
      "</div>" +
      '<div class="card">' +
        "<h3>Normalized Prompt</h3>" +
        "<pre>" + escapeHtml(payload.normalized_prompt || payload.prompt || "(empty)") + "</pre>" +
      "</div>"
    );
  }

  function renderStat(label, value, cls) {
    return (
      '<div class="stat">' +
        '<div class="stat-label">' + escapeHtml(label) + "</div>" +
        '<div class="stat-value ' + (cls || "") + '">' + escapeHtml(value) + "</div>" +
      "</div>"
    );
  }

  /* ---------------------------------------------------------- scanner */

  async function runScan(prompt, resultTargetId, errorTargetId, buttonId) {
    var button = document.getElementById(buttonId);
    var errorBox = document.getElementById(errorTargetId);
    if (button) button.disabled = true;
    if (errorBox) errorBox.classList.add("hidden");

    try {
      if (!prompt || !prompt.trim()) {
        throw new Error("Please enter a prompt to analyze.");
      }
      var item = await api("/analysis/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt }),
      });
      var target = document.getElementById(resultTargetId);
      if (target) target.innerHTML = renderFullResult(item);
      showToast("Analysis complete: " + (item.decision || "done"));
    } catch (err) {
      if (errorBox) {
        errorBox.textContent = err.message;
        errorBox.classList.remove("hidden");
      } else {
        showToast(err.message);
      }
    } finally {
      if (button) button.disabled = false;
    }
  }

  /* ---------------------------------------------------------- overview */

  async function loadOverview() {
    try {
      var summary = await api("/console/summary");
      var history = summary.history || {};
      var ml = summary.ml || {};

      var stats = [
        renderStat("Pipeline Status", "Operational", "ok"),
        renderStat("Components Active", summary.components ? summary.components.filter(function (c) { return c.status === "active"; }).length + " / " + summary.components.length : "—"),
        renderStat("Rules Enabled", String(summary.rules ? summary.rules.enabled : "—") + " / " + (summary.rules ? summary.rules.total : "—")),
        renderStat("ML Detectors", String(ml.detector_count || 0)),
        renderStat("Models Loaded", String(ml.loaded_models || 0)),
        renderStat("Scans (session)", String(history.total || 0)),
        renderStat("Blocked", String(history.blocked || 0), history.blocked ? "danger" : "ok"),
        renderStat("Quantum Backends", String(summary.quantum ? summary.quantum.backends.length : 0)),
      ];
      document.getElementById("overviewStats").innerHTML = stats.join("");

      renderComponents(summary.components || []);
    } catch (err) {
      document.getElementById("overviewStats").innerHTML =
        '<p class="empty-state">Failed to load overview: ' + escapeHtml(err.message) + "</p>";
    }
  }

  function renderComponents(components) {
    var html = components.map(function (c) {
      var badge = c.status === "active"
        ? '<span class="badge green">active</span>'
        : c.status === "available"
          ? '<span class="badge muted">available</span>'
          : '<span class="badge amber">' + escapeHtml(c.status) + "</span>";
      return (
        '<div class="rule">' +
          '<div class="rule-head"><span class="rule-id">' + escapeHtml(c.id) + "</span>" + badge + "</div>" +
          '<p><strong>' + escapeHtml(c.name) + "</strong> — " + escapeHtml(c.detail) + "</p>" +
        "</div>"
      );
    }).join("");
    document.getElementById("componentsList").innerHTML = html || '<p class="empty-state">No components reported.</p>';
  }

  /* ---------------------------------------------------------- history */

  async function loadHistory() {
    var box = document.getElementById("historyTable");
    try {
      var items = await api("/analysis?limit=100");
      if (!items || !items.length) {
        box.innerHTML = '<p class="empty-state">No scans yet — run one from the Scanner.</p>';
        return;
      }
      var rows = items.map(function (item) {
        return (
          "<tr data-id=\"" + escapeHtml(item.analysis_id) + "\">" +
            "<td>" + escapeHtml(fmtTime(item.timestamp)) + "</td>" +
            "<td><span class=\"badge " + badgeClass(item.decision) + "\">" + escapeHtml(item.decision) + "</span></td>" +
            "<td>" + fmtNumber(item.risk_score, 3) + "</td>" +
            "<td>" + item.finding_count + "</td>" +
            "<td>" + item.high_severity_count + "</td>" +
            "<td>" + fmtNumber(item.processing_time_ms, 2) + " ms</td>" +
            "<td>" + escapeHtml(truncate(item.payload && item.payload.prompt, 70)) + "</td>" +
          "</tr>"
        );
      }).join("");
      box.innerHTML =
        '<table><thead><tr>' +
          "<th>Time</th><th>Decision</th><th>Risk</th><th>Findings</th><th>High</th><th>Latency</th><th>Prompt</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table>";
      box.querySelectorAll("tbody tr").forEach(function (tr) {
        tr.classList.add("clickable");
        tr.addEventListener("click", function () {
          openHistoryDetail(tr.getAttribute("data-id"));
        });
      });
    } catch (err) {
      box.innerHTML = '<p class="empty-state">Failed to load history: ' + escapeHtml(err.message) + "</p>";
    }
  }

  async function openHistoryDetail(id) {
    try {
      var item = await api("/analysis/" + encodeURIComponent(id));
      document.getElementById("resultPanel").innerHTML =
        '<h2 class="row between" style="justify-content:space-between;display:flex">' +
          "<span>Analysis " + escapeHtml(id) + "</span>" +
          '<button type="button" class="btn ghost" id="closeDetail">Close</button>' +
        "</h2>" +
        renderFullResult(item);
      var close = document.getElementById("closeDetail");
      if (close) close.addEventListener("click", function () {
        document.getElementById("resultPanel").innerHTML = "";
      });
      document.getElementById("resultPanel").scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      showToast(err.message);
    }
  }

  /* ---------------------------------------------------------- rules */

  async function loadRules() {
    var box = document.getElementById("rulesList");
    try {
      var rules = await api("/console/rules");
      if (!rules || !rules.length) {
        box.innerHTML = '<p class="empty-state">No rules registered.</p>';
        return;
      }
      var html = rules.map(function (rule) {
        var enabled = rule.enabled !== false;
        var badge = enabled
          ? '<span class="badge green">enabled</span>'
          : '<span class="badge muted">disabled</span>';
        return (
          '<div class="rule">' +
            '<div class="rule-head">' +
              '<span class="rule-id">' + escapeHtml(rule.rule_id || rule.name || "rule") + "</span>" +
              badge +
            "</div>" +
            "<p>" + escapeHtml(rule.description || rule.pattern || rule.message || "") + "</p>" +
            '<div class="rule-meta">' +
              (rule.category ? "category " + escapeHtml(rule.category) + " · " : "") +
              (rule.severity ? "severity " + escapeHtml(rule.severity) + " · " : "") +
              "confidence " + fmtNumber(rule.confidence, 2) +
            "</div>" +
          "</div>"
        );
      }).join("");
      box.innerHTML = html;
    } catch (err) {
      box.innerHTML = '<p class="empty-state">Failed to load rules: ' + escapeHtml(err.message) + "</p>";
    }
  }

  /* ---------------------------------------------------------- models */

  async function loadModels() {
    try {
      var data = await api("/console/models");
      var ml = data.ml || {};
      var quantum = data.quantum || {};

      var mlRows = (ml.models || []).map(function (m) {
        var badge = m.status === "loaded"
          ? '<span class="badge green">loaded</span>'
          : '<span class="badge muted">' + escapeHtml(m.status || "unloaded") + "</span>";
        return (
          "<tr><td>" + escapeHtml(m.name) + "</td>" +
          "<td>" + escapeHtml(m.model_type) + "</td>" +
          "<td>" + escapeHtml(m.backend) + "</td>" +
          "<td>" + escapeHtml(m.version) + "</td>" +
          "<td>" + badge + "</td>" +
          "<td>" + escapeHtml(m.description || "") + "</td></tr>"
        );
      }).join("");
      document.getElementById("mlModelsList").innerHTML =
        '<div class="rule-meta" style="margin-bottom:10px">' +
          "ML active: <strong>" + (ml.active ? "yes" : "no") + "</strong> · " +
          "detectors: " + (ml.detector_count || 0) + " · classifiers: " + (ml.classifier_count || 0) + " · " +
          "loaded: " + (ml.loaded_models || 0) + " / " + (ml.total_models || 0) +
        "</div>" +
        (mlRows
          ? '<div class="table-wrap"><table><thead><tr>' +
              "<th>Model</th><th>Type</th><th>Backend</th><th>Version</th><th>Status</th><th>Description</th>" +
            "</tr></thead><tbody>" + mlRows + "</tbody></table></div>"
          : '<p class="empty-state">No ML models registered. Models are optional — the rule engine alone protects prompts.</p>');

      var qRows = (quantum.backends || []).map(function (b) {
        var badge = b.installed
          ? '<span class="badge green">installed</span>'
          : '<span class="badge muted">not installed</span>';
        return (
          "<tr><td>" + escapeHtml(b.name) + "</td>" +
          "<td>" + escapeHtml(b.description) + "</td>" +
          "<td>" + (b.requires ? escapeHtml(b.requires) : "none") + "</td>" +
          "<td>" + badge + "</td></tr>"
        );
      }).join("");
      document.getElementById("quantumList").innerHTML = qRows
        ? '<div class="table-wrap"><table><thead><tr>' +
            "<th>Backend</th><th>Description</th><th>Required SDK</th><th>Availability</th>" +
          "</tr></thead><tbody>" + qRows + "</tbody></table></div>"
        : '<p class="empty-state">No quantum backends reported.</p>';

      var fusion = (quantum.fusion_strategies || []).map(function (s) {
        return '<span class="badge" style="margin:0 6px 6px 0">' + escapeHtml(s) + "</span>";
      }).join("");
      document.getElementById("fusionList").innerHTML =
        fusion || '<p class="empty-state">No fusion strategies reported.</p>';
    } catch (err) {
      document.getElementById("mlModelsList").innerHTML =
        '<p class="empty-state">Failed to load models: ' + escapeHtml(err.message) + "</p>";
    }
  }

  /* ---------------------------------------------------------- configuration */

  function renderConfigGroup(title, obj) {
    if (!obj) return "";
    var rows = Object.keys(obj).sort().map(function (key) {
      var value = obj[key];
      var display = typeof value === "object" ? JSON.stringify(value) : String(value);
      return (
        '<div class="detail-row"><span class="k">' + escapeHtml(key) + "</span>" +
        '<span class="v">' + escapeHtml(display) + "</span></div>"
      );
    }).join("");
    return (
      '<div class="card"><h3>' + escapeHtml(title) + "</h3>" +
      '<div class="detail-list">' + rows + "</div></div>"
    );
  }

  async function loadConfiguration() {
    var box = document.getElementById("configContent");
    try {
      var config = await api("/console/configuration");
      var groups = [
        ["Application", config.application],
        ["Database", config.database],
        ["Security", config.security],
        ["Prompt Security", config.prompt_security],
        ["ML", config.ml],
      ];
      box.innerHTML = groups.map(function (pair) {
        return renderConfigGroup(pair[0], pair[1]);
      }).join("");
    } catch (err) {
      box.innerHTML = '<p class="empty-state">Failed to load configuration: ' + escapeHtml(err.message) + "</p>";
    }
  }

  /* ---------------------------------------------------------- wire-up */

  function onReady() {
    document.getElementById("scanForm").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var input = document.getElementById("scanInput");
      runScan(input.value, "resultPanel", "scanError", "scanSubmit");
    });

    document.getElementById("quickScanForm").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var input = document.getElementById("quickScanInput");
      runScan(input.value, "resultPanel", "quickScanError", "quickScanBtn").then(function () {
        window.location.hash = "#/scanner";
      });
    });

    document.getElementById("refreshHistory").addEventListener("click", loadHistory);
    document.getElementById("refreshRules").addEventListener("click", loadRules);
    document.getElementById("refreshModels").addEventListener("click", loadModels);
    document.getElementById("refreshConfig").addEventListener("click", loadConfiguration);

    refreshStatus();
    refreshVersion();
    navigate();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
