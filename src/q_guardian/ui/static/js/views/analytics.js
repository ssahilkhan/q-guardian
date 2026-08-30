/* Q-Guardian Console — Historical Analytics view.
 * Timeline, trends, charts and aggregates derived from REAL persisted scan
 * records returned by GET /api/v1/analysis. Every count on this page is
 * computed from the records actually served by the backend — nothing is
 * fabricated or simulated.
 *
 * Scope note (shown on the page): the backend keeps a bounded in-memory
 * history (200 records is the session maximum), so the ranges below are
 * client-side filters over exactly what the API returned. They never
 * pretend to represent more history than the backend holds.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;
  var A = QG.analytics;

  var VERDICT_FILTERS = [
    { key: "all", label: "All" },
    { key: "block", label: "Blocked" },
    { key: "review", label: "Review" },
    { key: "warn", label: "Warning" },
    { key: "allow", label: "Allowed" },
  ];

  var RANGE_KEYS = ["24h", "7d", "30d", "all"];

  var SEVERITY_LABELS = {
    info: "Info",
    low: "Low",
    medium: "Medium",
    high: "High",
    critical: "Critical",
  };

  function nonZeroEntries(counts) {
    return Object.keys(counts)
      .map(function (key) {
        return { label: labelOf(key), value: counts[key], key: key };
      })
      .filter(function (entry) { return entry.value > 0; });
  }

  function labelOf(key) {
    var labels = {
      allow: "Allowed",
      block: "Blocked",
      review: "Review",
      warn: "Warning",
    };
    return labels[key] || SEVERITY_LABELS[key] || key;
  }

  function severityOfScan(item) {
    var findings = (item.payload && item.payload.findings) || [];
    var order = ["info", "low", "medium", "high", "critical"];
    var highest = null;
    findings.forEach(function (finding) {
      var sev = String((finding && finding.severity) || "").toLowerCase();
      var rank = order.indexOf(sev);
      if (rank > highest) highest = rank;
    });
    return highest == null ? null : order[highest];
  }

  function categoriesOfScan(item) {
    var findings = (item.payload && item.payload.findings) || [];
    var seen = {};
    findings.forEach(function (finding) {
      var category = String((finding && finding.category) || "unknown").toLowerCase();
      seen[category] = true;
    });
    return Object.keys(seen).map(function (key) { return U.categoryLabel(key); });
  }

  function mlText(item) {
    var metadata = (item.payload && item.payload.metadata) || {};
    var count = metadata.ml_findings_count || 0;
    var hasMl = count > 0 || metadata.ml_risk_score !== undefined;
    if (!hasMl) return "ML inactive";
    var risk = metadata.ml_risk_score;
    return (
      "ML: " + count + " finding" + (count === 1 ? "" : "s") +
      (risk !== undefined ? " (risk " + Math.round(Number(risk) * 100) + "%)" : "")
    );
  }

  function searchMatches(item, query) {
    var text = item.analysis_id + " " +
      item.decision + " " +
      (item.payload && (item.payload.original_prompt || "")) + " " +
      JSON.stringify((item.payload && item.payload.findings) || []);
    return text.toLowerCase().indexOf(query) !== -1;
  }

  function renderTimeline(records) {
    if (!records.length) {
      return U.emptyState("No scans in the selected range.");
    }
    var groups = A.groupByDay(records);
    var html = groups.map(function (group) {
      var items = group.entries.map(function (item) {
        var highest = severityOfScan(item);
        var cats = categoriesOfScan(item);
        var time = new Date(item.timestamp).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        });
        return (
          '<div class="tl-row">' +
          '<span class="tl-time" aria-hidden="true">' + U.text(time) + "</span>" +
          '<div class="tl-body">' +
          '<span class="tl-summary">' +
          '<a class="row-link" href="#/detection/' + encodeURIComponent(item.analysis_id) + '">' +
          U.text(item.analysis_id.slice(0, 8)) + "</a> " +
          U.decisionBadge(item.decision) +
          " · risk " + Math.round(Number(item.risk_score || 0) * 100) + "%" +
          (highest ? " · " + U.severityBadge(highest) : "") +
          "</span>" +
          '<span class="tl-detail">' +
          (cats.length ? U.text(U.categoryLabel(cats.join(", "))) : U.text("No detected categories")) +
          " · " + U.text(mlText(item)) +
          " · " + U.statusBadge(item.is_valid ? "valid" : "invalid") +
          '<span class="tl-meta">' + U.fmtDateTime(item.timestamp) + "</span>" +
          "</span>" +
          "</div>" +
          "</div>"
        );
      });
      return (
        '<div class="tl-group">' +
        '<div class="tl-day">' + U.text(group.label) + "</div>" +
        items.join("") +
        "</div>"
      );
    }).join("");
    return '<div class="timeline analytics-timeline">' + html + "</div>";
  }

  function chartCard(title, sub, body) {
    return (
      '<div class="card"><div class="card-head"><div class="card-title">' +
      U.text(title) + "</div>" +
      (sub ? '<div class="card-sub">' + U.text(sub) + "</div>" : "") +
      "</div>" + body + "</div>"
    );
  }

  QG.views.analytics = {
    title: "Analytics",
    group: "analysis",
    render: async function (el, params) {
      var decisionFilter = params && params.decision ? params.decision : "all";
      if (VERDICT_FILTERS.every(function (f) { return f.key !== decisionFilter; })) {
        decisionFilter = "all";
      }
      var rangeKey = params && params.range ? params.range : "all";
      if (RANGE_KEYS.indexOf(rangeKey) === -1) rangeKey = "all";

      var state = { decision: decisionFilter, range: rangeKey, query: "" };

      function renderBody(records) {
        var range = A.RANGES[state.range];
        var ranged = A.withinHours(records, range.hours);
        var query = state.query.trim().toLowerCase();
        var visible = query
          ? ranged.filter(function (item) { return searchMatches(item, query); })
          : ranged;
        if (state.decision !== "all") {
          visible = visible.filter(function (item) {
            return A.normalizeDecision(item.decision) === state.decision;
          });
        }

        var summary = A.summarize(visible);
        var allSummary = A.summarize(records);
        var hourWindow = range.hours !== null && range.hours <= 48;
        var volume = A.scanVolume(visible, hourWindow ? A.HOUR_MS : A.DAY_MS);
        var riskTrend = A.metricTrend(visible, function (item) {
          return item.risk_score == null ? null : Number(item.risk_score) * 100;
        });
        var processingTrend = A.metricTrend(visible, function (item) {
          return item.processing_time_ms;
        });

        var decisions = nonZeroEntries(summary.decisions).map(function (entry) {
          return {
            label: entry.label,
            value: entry.value,
            title: entry.label + ": " + entry.value + " scans",
            clsKey: entry.key === "allow" ? "allow" : entry.key === "warn" ? "warn" : entry.key === "review" ? "review" : "block",
          };
        });
        var severities = nonZeroEntries(summary.severities).map(function (entry) {
          return {
            label: entry.label,
            value: entry.value,
            title: entry.label + " severity findings: " + entry.value,
            clsKey: entry.key === "critical" ? "critical" : entry.key === "high" ? "high" : entry.key === "medium" ? "medium" : entry.key === "low" ? "low" : "info",
          };
        });
        var categories = summary.categories.map(function (entry) {
          var label = U.categoryLabel(entry.category);
          return {
            label: label,
            value: entry.count,
            title: label + ": " + entry.count + " findings",
            clsKey: "accent",
          };
        });
        var volumeBars = volume.map(function (bucket) {
          return { label: bucket.label, value: bucket.count, title: bucket.label + ": " + bucket.count + " scans", clsKey: "accent" };
        });
        var riskPoints = riskTrend.map(function (point) {
          return { label: point.label, value: point.value };
        });
        var processingPoints = processingTrend.map(function (point) {
          return { label: point.label, value: point.value };
        });

        var volumeChart = volumeBars.length
          ? U.chart.bars({
              data: volumeBars,
              height: 150,
              empty: "No scans in the selected range.",
              ariaLabel: "Scan volume over time. " + volumeBars.map(function (b) { return b.label + ": " + b.value; }).join(", "),
            })
          : U.note("No scans in the selected range.");
        var riskChart = U.chart.line({
          data: riskPoints,
          height: 150,
          valueSuffix: "%",
          empty: "No risk scores in the selected range.",
          notEnough: "At least two scans with risk scores are needed to plot a risk trend.",
          clsKey: "review",
        });
        var processingChart = U.chart.line({
          data: processingPoints,
          height: 150,
          valueSuffix: " ms",
          empty: "No processing times in the selected range.",
          notEnough: "At least two scans are needed to plot a processing-time trend.",
          clsKey: "accent",
        });

        var verdictCards =
          '<div class="grid grid-4">' +
          U.statCard("Scans in Range", visible.length, range.label + " · of " + records.length + " retained", "") +
          U.statCard("Avg Risk", summary.avg_risk == null ? "—" : U.fmtPct(summary.avg_risk), "across scans in range", "warning") +
          U.statCard("High / Critical Findings", summary.high_severity_count, "across scan findings", summary.high_severity_count > 0 ? "block" : "success") +
          U.statCard("Avg Processing", summary.avg_processing_ms == null ? "—" : U.fmtMs(summary.avg_processing_ms), "per scan in range", "") +
          "</div>";

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Historical Analytics</h2>' +
          '<p class="page-sub">Trends, distributions and a scan timeline computed from the real scan records the backend has retained this session. Range, verdict and text filters run client-side over exactly these records.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshAnalytics">Refresh</button>' +
          "</div>" +

          U.note("Data source: GET /api/v1/analysis (the backend's retained scan history, bounded to 200 records in this release). Filters apply to what the API returned — they do not represent database-wide history. " +
            (allSummary.total ? allSummary.total + " records retained." : "No records retained yet — run a scan from the Scanner page.")) +

          '<div class="card">' +
          '<div class="toolbar" style="margin-bottom:0;">' +
          '<input type="search" id="analyticsSearch" class="search-input" placeholder="Search scans, prompts, findings…" aria-label="Search scans" />' +
          '<div class="chips" role="group" aria-label="Filter by verdict">' +
          VERDICT_FILTERS.map(function (f) {
            return '<button type="button" class="chip' + (f.key === state.decision ? " active" : "") + '" data-verdict="' + f.key + '">' + U.text(f.label) + "</button>";
          }).join("") +
          "</div></div>" +
          '<div class="toolbar" style="margin-bottom:0;">' +
          '<div class="chips" role="group" aria-label="Filter by time range">' +
          RANGE_KEYS.map(function (key) {
            return '<button type="button" class="chip' + (key === state.range ? " active" : "") + '" data-range="' + key + '">' + U.text(A.RANGES[key].label) + "</button>";
          }).join("") +
          "</div>" +
          "<span class='pagination-note'>Filters are applied to the " + records.length + " retained record" + (records.length === 1 ? "" : "s") + ".</span>" +
          "</div>" +
          "</div>" +

          verdictCards +

          '<div class="grid grid-2">' +
          chartCard("Verdict Distribution", visible.length + " scans in range", decisions.length
            ? U.chart.horizBars(decisions, "No scans in the selected range.")
            : U.note("No scans in the selected range.")) +
          chartCard("Severity Distribution", "from detection findings", severities.length
            ? U.chart.horizBars(severities, "No findings recorded in the selected range.")
            : U.note("No findings recorded in the selected range.")) +
          "</div>" +

          '<div class="grid grid-2">' +
          chartCard("Scan Volume", hourWindow ? "hourly buckets" : "daily buckets", volumeChart) +
          chartCard("Risk Trend", "% risk score per scan", riskChart) +
          "</div>" +

          '<div class="grid grid-2">' +
          chartCard("Processing Time Trend", "pipeline latency per scan (ms)", processingChart) +
          chartCard("Detection Categories", "frequency across findings", categories.length
            ? U.chart.horizBars(categories, "No findings recorded in the selected range.")
            : U.note("No findings recorded in the selected range.")) +
          "</div>" +

          '<div class="grid grid-3">' +
          U.statCard("Scans with ML", summary.ml.scans_with_ml, "of scans in range that ran ML inference", summary.ml.scans_with_ml > 0 ? "info" : "low") +
          U.statCard("ML Findings", summary.ml.findings, "from ML inference in range", summary.ml.findings > 0 ? "warning" : "success") +
          U.statCard("Invalid Inputs", summary.invalid_count, "validation failures in range", summary.invalid_count > 0 ? "warning" : "success") +
          "</div>" +

          (summary.ml.scans_with_ml === 0
            ? U.note("Classical ML inference was inactive for the scans in this range (no models loaded in the pipeline). ML values are reported only when the backend records them.")
            : "") +

          '<div class="section-title">Scan Timeline</div>' +
          '<div class="card">' +
          renderTimeline(visible) +
          "</div>";

        var search = el.querySelector("#analyticsSearch");
        if (search) search.value = state.query;
      }

      el.innerHTML = U.loadingState("Computing historical analytics…");
      try {
        var payload = await api.get(api.endpoints.analysis + "?limit=200");
        var envelope = api.envelope(payload);
        var records = envelope.items;

        renderBody(records);

        el.querySelector("#refreshAnalytics").addEventListener("click", function () {
          QG.views.analytics.render(el);
        });
        var search = el.querySelector("#analyticsSearch");
        if (search) {
          search.addEventListener("input", function () {
            state.query = search.value;
            renderBody(records);
          });
        }
        el.querySelectorAll("[data-verdict]").forEach(function (chip) {
          chip.addEventListener("click", function () {
            state.decision = chip.dataset.verdict;
            window.location.hash = "#/analytics" +
              (state.decision !== "all" ? "?decision=" + state.decision + "&range=" + state.range : "?range=" + state.range);
          });
        });
        el.querySelectorAll("[data-range]").forEach(function (chip) {
          chip.addEventListener("click", function () {
            state.range = chip.dataset.range;
            window.location.hash = "#/analytics" +
              (state.decision !== "all" ? "?decision=" + state.decision + "&range=" + state.range : "?range=" + state.range);
          });
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load historical analytics.");
      }
    },
  };
})();