/* Q-Guardian Console — Scanner view.
 * Prompt submission through POST /api/v1/analysis/scan and an inline
 * verdict, with a link through to the full detection record.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function renderResult(el, item) {
    var payload = item.payload || {};
    var findings = payload.findings || [];
    var body =
      item.finding_count + " finding" + (item.finding_count === 1 ? "" : "s") +
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
      "</div>";
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
