/* Q-Guardian Console — Documentation view.
 * Static guidance for operating this console, the API surface and the
 * detection pipeline, plus live version/environment info.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  var ENDPOINTS = [
    ["GET", "/api/v1/health", "Liveness and database health"],
    ["GET", "/api/v1/system/version", "Version and environment"],
    ["GET", "/api/v1/system/status", "Operational status"],
    ["GET", "/api/v1/console/summary", "Overview aggregates"],
    ["GET", "/api/v1/console/rules", "Detection rule catalog"],
    ["GET", "/api/v1/console/models", "ML model and quantum status"],
    ["GET", "/api/v1/console/components", "Pipeline stage inventory"],
    ["GET", "/api/v1/console/configuration", "Sanitized configuration"],
    ["GET", "/api/v1/console/research", "Research artifact snapshot"],
    ["GET", "/api/v1/analysis", "Scan history (paginated)"],
    ["GET", "/api/v1/analysis/{id}", "Single scan record"],
    ["POST", "/api/v1/analysis/scan", "Run the detection pipeline on a prompt"],
  ];

  QG.views.documentation = {
    title: "Documentation",
    group: "system",
    render: async function (el) {
      var version = null;
      try {
        var payload = await api.get(api.endpoints.version);
        version = api.data(payload);
      } catch (err) {
        /* keep version null; the footer already reports connectivity */
      }

      var rows = ENDPOINTS.map(function (endpoint) {
        return [
          U.badge(endpoint[0], endpoint[0] === "GET" ? "info" : "accent"),
          { value: endpoint[1], cls: "cell-mono" },
          endpoint[2],
        ];
      });

      el.innerHTML =
        '<div class="page-head">' +
        "<div>" +
        '<h2 class="page-title">Documentation</h2>' +
        '<p class="page-sub">How this console works and how it talks to the Q-Guardian API. Full interactive reference is available on the <a href="/docs">/docs</a> and <a href="/redoc">/redoc</a> pages.</p>' +
        "</div>" +
        "</div>" +

        '<div class="grid grid-3">' +
        U.statCard("Application", version ? version.application : "—", "", "") +
        U.statCard("Version", version ? version.version : "—", version ? "environment: " + version.environment : "", "") +
        U.statCard("Python", version ? version.python_version : "—", "", "") +
        "</div>" +

        '<div class="card"><div class="card-head"><div class="card-title">About</div></div>' +
        '<div class="prose">' +
        "<p>Q-Guardian is a <strong>hybrid quantum-classical framework</strong> for runtime security of autonomous AI agents. This console is a read-mostly control plane over the existing detection pipeline:</p>" +
        "<ul>" +
        "<li><strong>Normalization</strong> — Unicode NFKC, hidden-character stripping, whitespace collapsing.</li>" +
        "<li><strong>Validation</strong> — length, line, encoding and structural input limits.</li>" +
        "<li><strong>Feature extraction</strong> — statistical, keyword and structural features.</li>" +
        "<li><strong>Rule engine</strong> — built-in and custom detection rules.</li>" +
        "<li><strong>Classical ML</strong> — Isolation Forest, Random Forest, XGBoost detectors (when models are loaded and ML is enabled).</li>" +
        "<li><strong>Quantum</strong> — local simulator and optional Qiskit backends for hybrid fusion (research layer, not in the default scan path).</li>" +
        "<li><strong>Decision</strong> — ALLOW / WARN / REVIEW / BLOCK cascade with risk scoring.</li>" +
        "</ul>" +
        "<p>Scan history is bounded to the most recent 200 analyses and lives in process memory — it resets when the server restarts.</p>" +
        "</div>" +
        "</div>" +

        '<div class="card"><div class="card-head"><div class="card-title">Console API</div></div>' +
        U.table(["Method", "Path", "Purpose"], rows) +
        "</div>" +

        '<div class="card"><div class="card-head"><div class="card-title">Research Data</div></div>' +
        '<div class="prose">' +
        "<p>Research pages read real, on-disk artifacts through <code>/api/v1/console/research</code>:</p>" +
        "<ul>" +
        "<li><strong>Training</strong> — JSONL datasets under <code>data/</code> and trained model storage under <code>models/ml/</code> (metadata only).</li>" +
        "<li><strong>Evaluation</strong> — the cross-validation report at <code>docs/output/evaluation/report.json</code>.</li>" +
        "<li><strong>Benchmarks</strong> — suite results from <code>scripts/benchmarks/results_*.json</code> and load tests from <code>scripts/loadtest/results/*.json</code>.</li>" +
        "</ul>" +
        "<p>Reads are bounded and read-only: nothing is re-run and binary model files are never deserialized.</p>" +
        "</div>" +
        "</div>";
    },
  };
})();
