/* Q-Guardian Console — Scan History detail view.
 * Full record of a single persisted security scan: verdict, dataset profile,
 * per-provider metrics and scores summary.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function verdictReason(verdict) {
    var reason = verdict && verdict.reason;
    return reason || "No verdict was recorded for this scan.";
  }

  function renderMetrics(metrics) {
    if (!metrics || !Object.keys(metrics).length) {
      return U.emptyState("No provider metrics recorded for this scan.");
    }
    var rows = [];
    var providers = Object.keys(metrics);
    providers.forEach(function (provider) {
      var block = metrics[provider] || {};
      Object.keys(block).forEach(function (metric) {
        var value = block[metric];
        var shown;
        if (typeof value === "object" && value !== null) {
          shown = value.mean != null ? Number(value.mean).toFixed(4) : JSON.stringify(value);
        } else if (typeof value === "number") {
          shown = value.toFixed(6);
        } else {
          shown = value;
        }
        rows.push([
          { value: provider, cls: "cell-mono" },
          { value: metric, cls: "cell-mono" },
          shown,
        ]);
      });
    });
    return U.table(["Provider", "Metric", "Value"], rows);
  }

  QG.views.scan_history = {
    title: "Scan History",
    group: "overview",
    render: async function (el, params) {
      if (!params || !params.id) {
        el.innerHTML = U.errorState("No scan selected.");
        return;
      }
      el.innerHTML = U.loadingState("Loading scan record…");
      try {
        var payload = await api.get(api.endpoints.scans + "/" + encodeURIComponent(params.id));
        var scan = api.data(payload);
        if (!scan) throw new Error("Scan record not found.");

        var verdict = scan.verdict || {};
        var dataset = scan.dataset || {};
        var categories = dataset.categories || {};
        var scores = scan.scores_summary || {};
        var verdictTone = "allow";
        if (verdict.level === "high_risk") verdictTone = "block";
        else if (verdict.level === "review") verdictTone = "review";
        else if (verdict.level === "unknown") verdictTone = "warn";

        var categoryRows = Object.keys(categories).map(function (category) {
          return [
            { value: category || "—", cls: "cell-mono cell-strong" },
            { value: categories[category], cls: "cell-mono" },
          ];
        });

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Security Scan</h2>' +
          '<p class="page-sub mono">' + U.text(scan.scan_id) + "</p>" +
          "</div>" +
          '<a class="btn ghost" href="#/scans">Back to scan history</a>' +
          "</div>" +

          U.verdictBanner(verdictTone, "Verdict: " + ((verdict.label || verdict.level || "unknown")), verdictReason(scan)) +

          '<div class="card"><div class="card-head"><div class="card-title">Scan Record</div></div>' +
          U.keyValue([
            { label: "Scan ID", value: scan.scan_id, mono: true },
            { label: "Status", html: U.jobBadge(scan.status) },
            { label: "Type", value: scan.scan_type || scan.kind || "—" },
            { label: "Target", value: scan.target || "—", mono: true },
            { label: "Label", value: scan.label || "—" },
            { label: "Created", value: U.fmtDateTime(scan.created_at) },
            { label: "Started", value: U.fmtDateTime(scan.started_at) },
            { label: "Finished", value: U.fmtDateTime(scan.finished_at) },
            {
              label: "Error",
              html: scan.error ? '<span class="text-dim">' + U.text(scan.error) + "</span>" : "—",
            },
          ]) +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Dataset Profile</div>' +
          '<div class="card-sub">Statistics of the evaluation pool this scan ran over</div></div>' +
          '<div class="grid grid-3" style="margin:0;">' +
          U.statCard("Total", dataset.total != null ? U.fmtNum(dataset.total) : "—", "samples", "") +
          U.statCard("Threats", dataset.threats != null ? U.fmtNum(dataset.threats) : "—", "malicious", "b") +
          U.statCard("Benign", dataset.benign != null ? U.fmtNum(dataset.benign) : "—", "benign", "") +
          "</div>" +
          (dataset.threat_ratio != null ? U.note("Threat ratio: " + Number(dataset.threat_ratio).toFixed(3)) : "") +
          (categoryRows.length ? U.table(["Category", "Count"], categoryRows) : "") +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Scores Summary</div></div>' +
          U.keyValue([
            { label: "Scored Samples", value: scores.samples != null ? U.fmtNum(scores.samples) : "—" },
            { label: "Positives", value: scores.positives != null ? U.fmtNum(scores.positives) : "—" },
            { label: "Negatives", value: scores.negatives != null ? U.fmtNum(scores.negatives) : "—" },
          ]) +
          "</div>" +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Provider Metrics</div>' +
          '<div class="card-sub">Per-provider detection metrics collected by the framework pipeline</div></div>' +
          renderMetrics(scan.metrics) +
          "</div>" +

          (scan.note ? U.note(scan.note) : "");
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load the scan record.");
      }
    },
  };
})();