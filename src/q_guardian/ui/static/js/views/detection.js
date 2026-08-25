/* Q-Guardian Console — Detection view (history list + full report).
 * Reads the bounded scan history through GET /api/v1/analysis and
 * individual records through GET /api/v1/analysis/{id}.
 * Handles auth errors and shows real persistent backend data.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  var FILTERS = [
    { key: "all", label: "All" },
    { key: "block", label: "Blocked" },
    { key: "review", label: "Review" },
    { key: "warn", label: "Warning" },
    { key: "allow", label: "Allowed" },
  ];

  var FEATURE_LABELS = {
    length: "Length (chars)",
    word_count: "Word count",
    line_count: "Line count",
    token_estimate: "Token estimate",
    special_char_count: "Special characters",
    code_block_count: "Code blocks",
    url_count: "URLs",
    markdown_usage: "Markdown syntax",
    repeated_patterns: "Repeated patterns",
    entropy: "Entropy",
    suspicious_keywords: "Suspicious keywords",
    has_unicode_escaped: "Unicode escapes",
    has_html_tags: "HTML tags",
    uppercase_ratio: "Uppercase ratio",
    digit_ratio: "Digit ratio",
  };

  function listView(el, filter) {
    var pageSize = 20;

    async function load() {
      el.innerHTML = U.loadingState("Loading scan history…");
      try {
        var payload = await api.get(
          api.endpoints.analysis + "?limit=" + pageSize
        );
        var envelope = api.envelope(payload);
        var items = envelope.items;
        if (filter !== "all") {
          items = items.filter(function (item) {
            return String(item.decision).toLowerCase() === filter;
          });
        }
        var rows = items.map(function (item) {
          return [
            {
              html:
                '<a class="row-link" href="#/detection/' + encodeURIComponent(item.analysis_id) + '">' +
                U.text(item.analysis_id.slice(0, 8)) +
                "</a>",
              title: item.analysis_id,
            },
            U.fmtDateTime(item.timestamp),
            U.decisionBadge(item.decision),
            { value: Math.round(Number(item.risk_score || 0) * 100) + "%", cls: "cell-mono" },
            item.finding_count,
            item.high_severity_count,
            item.processing_time_ms == null ? "—" : item.processing_time_ms + " ms",
          ];
        });
        var chips = FILTERS.map(function (f) {
          return (
            '<button type="button" class="chip' +
            (f.key === filter ? " active" : "") +
            '" data-filter="' + f.key + '">' + U.text(f.label) + "</button>"
          );
        }).join("");

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Detection</h2>' +
          '<p class="page-sub">Scan records produced this session. Each entry links to a full report with findings, features and the pipeline decision.</p>' +
          "</div>" +
          "</div>" +
          '<div class="toolbar"><div class="chips">' + chips + "</div>" +
          '<button type="button" class="btn ghost" id="refreshDetection">Refresh</button>' +
          "</div>" +
          U.table(
            ["Analysis", "Timestamp", "Decision", "Risk", "Findings", "High / Critical", "Time"],
            rows
          ) +
          '<div class="pagination"><span>Session history (bounded to the last 200 scans).</span></div>';

        el.querySelectorAll(".chip").forEach(function (chip) {
          chip.addEventListener("click", function () {
            window.location.hash = "#/detection?decision=" + chip.dataset.filter;
          });
        });
        var refresh = el.querySelector("#refreshDetection");
        if (refresh) refresh.addEventListener("click", load);
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load scan history.");
      }
    }

    return load();
  }

  function featureRows(features) {
    var items = [];
    Object.keys(FEATURE_LABELS).forEach(function (key) {
      if (features[key] === undefined) return;
      items.push({
        label: FEATURE_LABELS[key],
        value: formatFeature(key, features[key]),
        mono: typeof features[key] === "number",
      });
    });
    var extras = features.metadata || {};
    Object.keys(extras).forEach(function (key) {
      items.push({
        label: key.replace(/_/g, " "),
        value: JSON.stringify(extras[key]),
        mono: true,
      });
    });
    return items;
  }

  function formatFeature(key, value) {
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "number" && key === "entropy") return value.toFixed(2);
    if (typeof value === "number" && /ratio/.test(key)) return (value * 100).toFixed(1) + "%";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
    if (value === null || value === undefined) return "—";
    return value;
  }

  function findingsTable(findings) {
    if (!findings || !findings.length) {
      return U.emptyState("No findings — nothing triggered a detection rule.");
    }
    var rows = findings.map(function (finding) {
      return [
        { value: finding.rule_name || finding.rule_id || "—", cls: "cell-strong" },
        U.text(U.categoryLabel(finding.category)),
        U.severityBadge(finding.severity),
        { value: Math.round(Number(finding.confidence || 0) * 100) + "%", cls: "cell-mono" },
        finding.description,
      ];
    });
    return U.table(
      ["Rule", "Category", "Severity", "Confidence", "Description"],
      rows
    );
  }

  function detailView(el, analysisId) {
    el.innerHTML = U.loadingState("Loading detection report…");
    return api
      .get(api.endpoints.analysis + "/" + encodeURIComponent(analysisId))
      .then(function (payload) {
        var item = api.data(payload);
        if (!item) throw new Error("Analysis record not found.");
        var full = item.payload || {};
        var features = full.features || {};
        var findings = full.findings || [];
        var metadata = full.metadata || {};
        var metaItems = Object.keys(metadata).map(function (key) {
          var value = metadata[key];
          return {
            label: key.replace(/_/g, " "),
            value: typeof value === "string" ? value : JSON.stringify(value),
            mono: true,
          };
        });
        var recommendation = full.recommendation || "See decision above.";

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Detection Report</h2>' +
          '<p class="page-sub">' + U.text(item.analysis_id) + "</p>" +
          "</div>" +
          '<a class="btn ghost" href="#/detection">Back to Detection</a>' +
          "</div>" +
          U.verdictBanner(item.decision, null, recommendation) +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Analysis</div></div>' +
          U.keyValue([
            { label: "Analysis ID", value: item.analysis_id, mono: true },
            { label: "Timestamp", value: U.fmtDateTime(item.timestamp) },
            { label: "Decision", html: U.decisionBadge(item.decision) },
            { label: "Validation", html: U.statusBadge(full.validation_status || (item.is_valid ? "valid" : "invalid")) },
            { label: "Processing Time", value: item.processing_time_ms == null ? "—" : item.processing_time_ms + " ms" },
            { label: "Findings", value: item.finding_count },
            { label: "High / Critical", value: item.high_severity_count },
          ]) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Risk Assessment</div></div>' +
          U.riskBar(item.risk_score) +
          '<div class="section-title">Metadata</div>' +
          (metaItems.length
            ? U.keyValue(metaItems)
            : U.emptyState("No pipeline metadata recorded.")) +
          "</div>" +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Findings</div>' +
          '<div class="card-sub">' + findings.length + " detected</div></div>" +
          findingsTable(findings) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Extracted Features</div></div>' +
          U.keyValue(featureRows(features)) +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Original Prompt</div></div>' +
          '<pre class="code-block">' + U.esc(full.original_prompt || "—") + "</pre>" +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Normalized Prompt</div></div>' +
          '<pre class="code-block">' + U.esc(full.normalized_prompt || "—") + "</pre>" +
          "</div>" +
          "</div>";
      })
      .catch(function (err) {
        if (err && err.authError) {
          el.innerHTML = U.errorState("Session expired. Please log in again.");
          return;
        }
        el.innerHTML =
          U.errorState(err.message || "Could not load the detection report.");
      });
  }

  QG.views.detection = {
    title: "Detection",
    group: "analysis",
    render: function (el, params) {
      if (params && params.id) {
        return detailView(el, params.id);
      }
      var filter = params && params.decision ? params.decision : "all";
      if (FILTERS.every(function (f) { return f.key !== filter; })) {
        filter = "all";
      }
      return listView(el, filter);
    },
    crumb: function (params) {
      return params && params.id ? params.id.slice(0, 8) : null;
    },
  };
})();
