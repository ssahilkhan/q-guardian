/* Q-Guardian Console — Benchmarks view.
 * Benchmark suites (scripts/benchmarks/results_*.json) and load-test
 * results (scripts/loadtest/results/*.json), read from disk via
 * /console/research.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function suitesCard(benchmarks) {
    var suites = benchmarks.suites || [];
    if (!benchmarks.present || !suites.length) {
      return U.emptyState("No benchmark suites saved. Run the benchmark scripts (scripts/benchmarks/) to generate results_*.json files.");
    }
    return suites
      .map(function (suite) {
        var rows = (suite.results || []).map(function (row) {
          return [
            { value: row.name || "—", cls: "cell-strong" },
            row.iterations == null ? "—" : U.fmtNum(row.iterations),
            { value: typeof row.avg_us === "number" ? row.avg_us.toFixed(1) + " µs" : "—", cls: "cell-mono" },
            { value: typeof row.p50_us === "number" ? row.p50_us.toFixed(1) + " µs" : "—", cls: "cell-mono" },
            { value: typeof row.p95_us === "number" ? row.p95_us.toFixed(1) + " µs" : "—", cls: "cell-mono" },
            { value: typeof row.p99_us === "number" ? row.p99_us.toFixed(1) + " µs" : "—", cls: "cell-mono" },
            { value: typeof row.ops_per_sec === "number" ? U.fmtNum(row.ops_per_sec) : "—", cls: "cell-mono" },
          ];
        });
        return (
          '<div class="card"><div class="card-head"><div class="card-title">' + U.text(suite.suite || suite.file) + "</div>" +
          '<div class="card-sub">' + U.text(suite.file) + "</div></div>" +
          (rows.length
            ? U.table(["Benchmark", "Iterations", "Avg (µs)", "p50 (µs)", "p95 (µs)", "p99 (µs)", "Ops/sec"], rows)
            : U.emptyState("No results recorded in this suite.")) +
          "</div>"
        );
      })
      .join("");
  }

  function loadTestsCard(loadtests) {
    if (!loadtests.length) {
      return U.emptyState("No load-test results found under scripts/loadtest/results/.");
    }
    var rows = loadtests.map(function (run) {
      return [
        { value: run.scenario_name || "—", cls: "cell-strong" },
        U.fmtNum(run.total_requests),
        run.error_rate == null ? "—" : U.fmtPct(run.error_rate),
        { value: run.avg_latency_ms == null ? "—" : run.avg_latency_ms.toFixed(2) + " ms", cls: "cell-mono" },
        { value: run.p50_latency_ms == null ? "—" : run.p50_latency_ms.toFixed(2) + " ms", cls: "cell-mono" },
        { value: run.p95_latency_ms == null ? "—" : run.p95_latency_ms.toFixed(2) + " ms", cls: "cell-mono" },
        { value: run.p99_latency_ms == null ? "—" : run.p99_latency_ms.toFixed(2) + " ms", cls: "cell-mono" },
        { value: run.throughput_rps == null ? "—" : run.throughput_rps.toFixed(1) + " rps", cls: "cell-mono" },
        { value: run.duration_seconds == null ? "—" : run.duration_seconds.toFixed(1) + " s", cls: "cell-mono" },
        { value: run.memory_peak_mb == null ? "—" : run.memory_peak_mb.toFixed(2) + " MB", cls: "cell-mono" },
      ];
    });
    return U.table(
      ["Scenario", "Requests", "Error Rate", "Avg Lat", "p50", "p95", "p99", "Throughput", "Duration", "Peak Mem"],
      rows
    );
  }

  QG.views.benchmarks = {
    title: "Benchmarks",
    group: "research",
    render: async function (el) {
      el.innerHTML = U.loadingState("Reading benchmark results…");
      try {
        var payload = await api.get(api.endpoints.research);
        var research = api.data(payload) || {};
        var benchmarks = research.benchmarks || {};
        var loadtests = research.loadtests || [];

        var avgLatency = 0;
        loadtests.forEach(function (run) {
          if (run.avg_latency_ms != null) avgLatency += run.avg_latency_ms;
        });
        var avg = loadtests.length ? avgLatency / loadtests.length : null;

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Benchmarks</h2>' +
          '<p class="page-sub">Performance measurements saved by the benchmark and load-test scripts. The console reads the saved JSON results from disk.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshBenchmarks">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-3">' +
          U.statCard("Benchmark Suites", (benchmarks.suites || []).length, "results_*.json files", benchmarks.present ? "success" : "low") +
          U.statCard("Load-Test Runs", loadtests.length, "under results/", loadtests.length ? "success" : "low") +
          U.statCard("Avg Latency", avg == null ? "—" : avg.toFixed(2) + " ms", "across runs", "") +
          "</div>" +

          (benchmarks.note ? U.note(benchmarks.note) : "") +

          '<div class="section-title">Benchmark Suites</div>' +
          suitesCard(benchmarks) +

          '<div class="section-title">Load-Test Results</div>' +
          '<div class="card">' + loadTestsCard(loadtests) + "</div>";

        el.querySelector("#refreshBenchmarks").addEventListener("click", function () {
          QG.views.benchmarks.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not read benchmark results.");
      }
    },
  };
})();
