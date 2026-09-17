/* Q-Guardian Console — Dashboard view.
 * Product-workflow overview: aggregates from /api/v1/analytics/summary and
 * the most recent security scans. All numbers come from real persisted
 * artifacts — the console never fabricates a figure.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function renderVerdictDistribution(summary) {
    var scans = summary.scans || {};
    var byVerdict = scans.by_verdict || {};
    var total = scans.total || 0;
    if (!total) return U.emptyState("No security scans recorded yet. Run a security scan from the Security Scans page.");
    var rows = [
      { label: "Low Risk", count: byVerdict.low_risk || 0, cls: "success" },
      { label: "Review", count: byVerdict.review || 0, cls: "review" },
      { label: "High Risk", count: byVerdict.high_risk || 0, cls: "block" },
      { label: "Unknown", count: byVerdict.unknown || 0, cls: "low" },
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

  function renderTimeline(timeline) {
    if (!timeline || !timeline.length) {
      return U.emptyState("No scan activity in the last 14 days.");
    }
    var max = 0;
    timeline.forEach(function (day) {
      if (day.scans > max) max = day.scans;
    });
    var bars = timeline
      .map(function (day) {
        var pct = max ? Math.round((day.scans / max) * 100) : 0;
        var label = new Date(day.date + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "2-digit" });
        return (
          '<div class="dist-row" title="' + U.esc(day.date) + " — " + day.scans + ' scan(s)">' +
          '<span class="dist-label">' + label + "</span>" +
          '<div class="dist-track"><div class="dist-fill info" style="width:' + pct + '%"></div></div>' +
          '<span class="dist-value">' + day.scans + "</span>" +
          "</div>"
        );
      })
      .join("");
    return '<div class="distribution">' + bars + "</div>";
  }

  function renderRecent(scans) {
    if (!scans || !scans.length) {
      return U.emptyState("No security scans recorded yet.");
    }
    var rows = scans.map(function (scan) {
      var verdict = scan.verdict || {};
      return [
        {
          html: '<a class="row-link" href="#/scans/' + encodeURIComponent(scan.scan_id) + '">' +
            U.text(scan.scan_id) + "</a>",
          title: scan.scan_id,
        },
        U.fmtDateTime(scan.created_at),
        scan.scan_type || scan.kind || "—",
        { value: scan.target || "—", cls: "cell-mono" },
        U.jobBadge(scan.status),
        U.verdictBadge(verdict.level),
      ];
    });
    return U.table(["Scan", "Created", "Type", "Target", "Status", "Verdict"], rows);
  }

  function detectionRate(summary) {
    var rate = summary.scans && summary.scans.avg_detection_rate;
    return rate == null ? "—" : U.fmtPct(rate);
  }

  QG.views.dashboard = {
    title: "Dashboard",
    group: "overview",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading dashboard…");
      try {
        var summaryPayload = await api.get(api.endpoints.analyticsSummary);
        var scansPayload = await api.get(api.endpoints.scans + "?limit=6");
        var summary = api.data(summaryPayload) || {};
        var scans = api.data(scansPayload) || [];

        var datasets = summary.datasets || {};
        var training = summary.training || {};
        var data = summary.data || {};
        var scansStats = summary.scans || {};

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Security Posture</h2>' +
          '<p class="page-sub">A live summary of the product workflow: secured datasets, trained detectors, hybrid security scans and cross-pipeline analytics — all derived from persisted artifacts.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshDashboard">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("Prepared Data", datasets.prepared != null ? datasets.prepared : "—", "of " + (datasets.catalog != null ? datasets.catalog : "—") + " catalogued", "success") +
          U.statCard("Trained Models", training.trained_models != null ? training.trained_models : "—", training.runs != null ? training.runs + " training run(s)" : "", "info") +
          U.statCard("Security Scans", scansStats.total != null ? scansStats.total : "—", (scansStats.scans_with_metrics != null ? scansStats.scans_with_metrics : "—") + " with metrics", "") +
          U.statCard("Avg Detection Rate", detectionRate(summary), "fusion recall, scored scans", "") +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Scan Verdicts</div>' +
          '<div class="card-sub">Verdict distribution across all persisted security scans</div></div>' +
          renderVerdictDistribution(summary) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Prepared Data</div>' +
          '<div class="card-sub">Total samples staged by the dataset preparation pipeline</div></div>' +
          '<div class="grid grid-3" style="margin:0;">' +
          U.statCard("Samples", data.prepared_samples != null ? U.fmtNum(data.prepared_samples) : "—", "total prepared", "success") +
          U.statCard("Malicious", data.prepared_malicious != null ? U.fmtNum(data.prepared_malicious) : "—", "threat samples", "b") +
          U.statCard("Benign", data.prepared_benign != null ? U.fmtNum(data.prepared_benign) : "—", "benign samples", "") +
          "</div>" +
          "</div>" +
          "</div>" +

          '<div class="section-title">Recent Security Scans</div>' +
          '<div class="card" style="padding:0;box-shadow:none;border:none;background:transparent;">' +
          renderRecent(scans) +
          "</div>" +

          '<div class="section-title">Scan Activity (14 days)</div>' +
          '<div class="card"><div class="card-head"><div class="card-title">Scans per Day</div>' +
          '<div class="card-sub">Generated ' + U.fmtDateTime(summary.generated_at) + "</div></div>" +
          renderTimeline(summary.timeline) +
          "</div>";

        var refreshBtn = el.querySelector("#refreshDashboard");
        if (refreshBtn) {
          refreshBtn.addEventListener("click", function () {
            QG.views.dashboard.render(el);
          });
        }
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load dashboard.");
        var retry = el.querySelector("#refreshDashboard");
        if (retry) {
          retry.addEventListener("click", function () {
            QG.views.dashboard.render(el);
          });
        }
      }
    },
  };
})();