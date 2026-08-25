/* Q-Guardian Console — Scanner view.
 * Prompt submission through POST /api/v1/analysis/scan and an inline
 * verdict, with a link through to the full detection record.
 * Shows real pipeline stage execution and ML results when available.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function pipelineVisualization(item) {
    var metadata = (item.payload && item.payload.metadata) || {};
    var mlFindingsCount = metadata.ml_findings_count || 0;
    var ruleFindingsCount = metadata.rule_findings_count || 0;
    var mlActive = mlFindingsCount > 0 || (metadata.ml_risk_score !== undefined);

    var stages = [
      { name: "Input", status: "done", detail: "Prompt received" },
      { name: "Normalization", status: "done", detail: "Unicode NFKC, whitespace collapsed" },
      { name: "Validation", status: item.is_valid ? "done" : "warn", detail: item.is_valid ? "Passed" : "Issues detected" },
      { name: "Feature Extraction", status: "done", detail: "Statistical, keyword, structural features" },
      { name: "Rule Engine", status: ruleFindingsCount > 0 ? "warn" : "done", detail: ruleFindingsCount + " finding" + (ruleFindingsCount === 1 ? "" : "s") },
    ];

    if (mlActive) {
      stages.push({ name: "Classical ML", status: mlFindingsCount > 0 ? "warn" : "done", detail: mlFindingsCount + " ML finding" + (mlFindingsCount === 1 ? "" : "s") });
      if (metadata.ml_risk_score !== undefined) {
        stages[stages.length - 1].detail += " (risk: " + (Number(metadata.ml_risk_score) * 100).toFixed(1) + "%)";
      }
    } else {
      stages.push({ name: "Classical ML", status: "off", detail: "Not active (no models loaded)" });
    }

    stages.push({ name: "Decision", status: "done", detail: item.decision.toUpperCase() });

    var rows = stages.map(function (stage) {
      var icon = stage.status === "done" ? "check" : stage.status === "warn" ? "warn" : stage.status === "off" ? "off" : "wait";
      var cls = stage.status === "done" ? "success" : stage.status === "warn" ? "warning" : stage.status === "off" ? "low" : "neutral";
      return [
        { html: '<span class="pipeline-icon pipeline-' + icon + '"></span>', cls: "cell-icon" },
        { value: stage.name, cls: "cell-strong" },
        U.badge(icon === "check" ? "Done" : icon === "warn" ? "Alert" : icon === "off" ? "Off" : "Wait", cls),
        stage.detail,
      ];
    });

    return U.table(["", "Stage", "Status", "Detail"], rows);
  }

  function renderResult(el, item) {
    var payload = item.payload || {};
    var findings = payload.findings || [];
    var body = item.finding_count + " finding" + (item.finding_count === 1 ? "" : "s") +
      " · risk " + Math.round(Number(item.risk_score || 0) * 100) + "% · " +
      (item.processing_time_ms == null ? "—" : item.processing_time_ms + " ms");
    var recommendations = {
      allowed: "No threats detected — the prompt is safe to allow.",
      warn: "Low-risk content detected — allow with monitoring.",
      review: "Suspicious content detected — route to human review.",
      block: "Threat detected — the prompt was blocked.",
    };
    var recommendation = payload.recommendation || recommendations[item.decision] || "";
    el.innerHTML =
      U.verdictBanner(item.decision, null, recommendation) +
      '<div class="card">' +
      '<div class="card-head"><div><div class="card-title">Result Summary</div>' +
      '<div class="card-sub">' + U.fmtDateTime(item.timestamp) + "</div></div>" +
      '<a class="btn primary" href="#/detection/' + encodeURIComponent(item.analysis_id) + '">Open Full Report</a>' +
      "</div>" +
      U.keyValue([
        { label: "Analysis ID", value: item.analysis_id, mono: true },
        { label: "Decision", html: U.decisionBadge(item.decision) },
        { label: "Risk Score", value: Math.round(Number(item.risk_score || 0) * 100) + "%" },
        { label: "Findings", value: item.finding_count },
        { label: "High / Critical", value: item.high_severity_count },
        { label: "Processing Time", value: item.processing_time_ms == null ? "—" : item.processing_time_ms + " ms" },
        { label: "Validation", html: U.statusBadge(item.is_valid ? "valid" : "invalid") },
        { label: "Body", value: String(body), mono: true },
      ]) +
      "</div>" +

      '<div class="card"><div class="card-head"><div class="card-title">Pipeline Execution</div></div>' +
      pipelineVisualization(item) +
      "</div>" +

      (findings.length
        ? '<div class="card"><div class="card-head"><div class="card-title">Findings</div>' +
          '<div class="card-sub">' + findings.length + " detected</div></div>" +
          findingsTable(findings) +
          "</div>"
        : "");
  }

  function findingsTable(findings) {
    if (!findings || !findings.length) {
      return U.emptyState("No findings.");
    }
    var rows = findings.map(function (f) {
      return [
        { value: f.rule_name || f.rule_id || "—", cls: "cell-strong" },
        U.text(U.categoryLabel(f.category)),
        U.severityBadge(f.severity),
        { value: Math.round(Number(f.confidence || 0) * 100) + "%", cls: "cell-mono" },
        f.description,
      ];
    });
    return U.table(["Rule", "Category", "Severity", "Confidence", "Description"], rows);
  }

  QG.views.scanner = {
    title: "Scanner",
    group: "overview",
    render: async function (el) {
      el.innerHTML =
        '<div class="page-head">' +
        "<div>" +
        '<h2 class="page-title">Prompt Scanner</h2>' +
        '<p class="page-sub">Run any prompt through the Q-Guardian detection pipeline: normalization, validation, feature extraction, rule engine and optional classical ML inference.</p>' +
        "</div>" +
        "</div>" +

        '<div class="card">' +
        '<div class="card-head"><div><div class="card-title">Analyze a Prompt</div>' +
        '<div class="card-sub">Paste input text; Q-Guardian returns a security decision (allow / warn / review / block) with findings.</div></div></div>' +
        '<form id="scanForm">' +
        '<div class="field">' +
        '<label for="scanInput">Prompt text</label>' +
        '<textarea id="scanInput" rows="8" maxlength="100000" placeholder="Enter a prompt to analyze…"></textarea>' +
        "</div>" +
        '<div class="row end"><button type="submit" class="btn primary">Run Analysis</button></div>' +
        "</form>" +
        '<div id="scanError"></div>' +
        "</div>" +
        '<div id="scanResult"></div>';

      var form = el.querySelector("#scanForm");
      var input = el.querySelector("#scanInput");
      var result = el.querySelector("#scanResult");
      var errorBox = el.querySelector("#scanError");

      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        var prompt = input.value.trim();
        errorBox.innerHTML = "";
        result.innerHTML = "";
        if (!prompt) {
          errorBox.innerHTML = U.errorState("Enter a prompt to analyze.");
          return;
        }
        result.innerHTML = U.loadingState("Running the detection pipeline…");
        try {
          var payload = await api.post(api.endpoints.scan, { prompt: prompt });
          var item = api.data(payload);
          renderResult(result, item);
        } catch (err) {
          result.innerHTML = "";
          errorBox.innerHTML = U.errorState(err.message || "Scan failed.");
        }
      });
    },
  };
})();
