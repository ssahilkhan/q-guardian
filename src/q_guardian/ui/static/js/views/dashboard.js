/* Q-Guardian Console — Dashboard view.
 * Overview aggregates from /console/summary plus a quick-scan control and
 * the most recent analyses. All numbers come from the live API.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function renderDistribution(history) {
    var total = history.total || 0;
    if (!total) return U.emptyState("No scans recorded yet. Run a scan from the Scanner page.");
    var rows = [
      { key: "allowed", label: "Allowed", count: history.allowed || 0, cls: "success" },
      { key: "warn", label: "Warning", count: history.warn || 0, cls: "warning" },
      { key: "review", label: "Review", count: history.review || 0, cls: "review" },
      { key: "block", label: "Blocked", count: history.blocked || 0, cls: "block" },
    ];
    var bars = rows
      .map(function (row) {
        var pct = Math.round((row.count / total) * 100);
        return (
          '<div class="dist-row">' +
          '<span class="dist-label">' + row.label + "</span>" +
          '<div class="dist-track"><div class="dist-fill ' + row.cls + '" style="width:' + pct + '%"></div></div>' +
          '<span class="dist-value">' + row.count + "</span>" +
          "</div>"
        );
      })
      .join("");
    return '<div class="distribution">' + bars + "</div>";
  }

  function renderComponents(components) {
    if (!components || !components.length) return U.emptyState("No pipeline components reported.");
    var rows = components.map(function (component) {
      return [
        { value: component.name, cls: "cell-strong" },
        U.statusBadge(component.status),
        component.detail,
      ];
    });
    return U.table(["Stage", "Status", "Details"], rows);
  }

  function renderRecent(history) {
    if (!history.items || !history.items.length) {
      return U.emptyState("No scans recorded yet.");
    }
    var rows = history.items.map(function (item) {
      return [
        {
          html: '<a class="row-link" href="#/detection/' + encodeURIComponent(item.analysis_id) + '">' +
            U.text(item.analysis_id.slice(0, 8)) + "</a>",
          title: item.analysis_id,
        },
        U.fmtDateTime(item.timestamp),
        U.decisionBadge(item.decision),
        { value: Math.round(Number(item.risk_score || 0) * 100) + "%", cls: "cell-mono" },
        item.finding_count,
        item.processing_time_ms == null ? "—" : item.processing_time_ms + " ms",
      ];
    });
    return U.table(
      ["Analysis", "Timestamp", "Decision", "Risk", "Findings", "Time"],
      rows
    );
  }

  QG.views.dashboard = {
    title: "Dashboard",
    group: "overview",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading dashboard…");
      var summaryPayload = await api.get(api.endpoints.summary);
      var historyPayload = await api.get(api.endpoints.analysis + "?limit=6");
      var summary = api.data(summaryPayload);
      var history = api.envelope(historyPayload);

      var components = (summary.components || []).length;
      var rules = summary.rules || {};
      var ml = summary.ml || {};
      var quantum = summary.quantum || {};
      var backends = quantum.backends || [];
      var installed = backends.filter(function (b) {
        return b.installed;
      }).length;
      var historyCounts = summary.history || {};

      el.innerHTML =
        '<div class="page-head">' +
        "<div>" +
        '<h2 class="page-title">Security Overview</h2>' +
        '<p class="page-sub">Real-time posture of the Q-Guardian runtime security pipeline: detection rules, model availability, quantum research backends and recent scan activity.</p>' +
        "</div>" +
        "</div>" +

        '<div class="card">' +
        '<div class="card-head"><div><div class="card-title">Quick Scan</div>' +
        '<div class="card-sub">Submit a prompt through the full analysis pipeline (normalize, validate, features, rules, optional ML).</div></div></div>' +
        '<form id="dashboardScanForm">' +
        '<div class="field">' +
        '<textarea id="dashboardScanInput" rows="3" maxlength="100000" placeholder="Paste a prompt to analyze…"></textarea>' +
        "</div>" +
        '<div class="row end"><button type="submit" class="btn primary" id="dashboardScanBtn">Analyze Prompt</button></div>' +
        "</form>" +
        "</div>" +

        '<div class="grid grid-4">' +
        U.statCard("Pipeline Components", components, "stages reported", "success") +
        U.statCard("Detection Rules", rules.enabled != null ? rules.enabled + " / " + rules.total : rules.total, "enabled / total", "success") +
        U.statCard("ML Models", ml.loaded_models + " / " + ml.total_models, (ml.active ? "active" : "no models loaded"), ml.active ? "success" : "warning") +
        U.statCard("Quantum Backends", installed + " / " + backends.length, "installed / available", "info") +
        "</div>" +

        '<div class="grid grid-2">' +
        '<div class="card"><div class="card-head"><div class="card-title">Decision Distribution</div>' +
        '<div class="card-sub">' + U.fmtNum(historyCounts.total || 0) + " scans in this session" + "</div></div>" +
        renderDistribution(historyCounts) +
        "</div>" +
        '<div class="card"><div class="card-head"><div class="card-title">Pipeline Stages</div></div>' +
        renderComponents(summary.components || []) +
        "</div>" +
        "</div>" +

        '<div class="section-title">Recent Scans</div>' +
        '<div class="card" style="padding:0;box-shadow:none;border:none;background:transparent;">' +
        renderRecent(history) +
        "</div>";

      var form = el.querySelector("#dashboardScanForm");
      var input = el.querySelector("#dashboardScanInput");
      var btn = el.querySelector("#dashboardScanBtn");
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        var prompt = input.value.trim();
        if (!prompt) {
          U.toast("Enter a prompt to analyze.", "error");
          return;
        }
        btn.disabled = true;
        try {
          var result = await api.post(api.endpoints.scan, { prompt: prompt });
          var item = api.data(result);
          U.toast("Analysis completed — " + item.decision);
          window.location.hash = "#/detection/" + encodeURIComponent(item.analysis_id);
        } catch (err) {
          U.toast(err.message || "Scan failed.", "error");
        } finally {
          btn.disabled = false;
        }
      });
    },
  };
})();
