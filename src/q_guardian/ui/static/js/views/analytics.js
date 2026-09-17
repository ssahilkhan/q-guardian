/* Q-Guardian Console — Analytics view.
 * Cross-dataset analytics over saved report JSON files (benchmarks,
 * evaluations, baselines) via /api/v1/analytics/cross. Aggregates, ranks,
 * compares classical vs quantum and analyzes generalization using the
 * framework analytics pipeline — results are always real, never synthesized.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function renderInputs(inputs) {
    if (!inputs || !inputs.length) return U.emptyState("No inputs resolved.");
    var rows = inputs.map(function (input) {
      return [
        { value: input.dataset_id, cls: "cell-mono cell-strong" },
        input.source || "—",
        input.scope || "—",
        input.pool || "—",
        { value: U.fmtNum(input.samples), cls: "cell-mono" },
        input.threshold != null ? Number(input.threshold).toFixed(4) : "—",
        U.text((input.providers || []).join(", ")),
      ];
    });
    return U.table(["Dataset", "Source", "Scope", "Pool", "Samples", "Threshold", "Providers"], rows);
  }

  function renderCompatibility(compat) {
    if (!compat) return "";
    var html =
      '<div class="card"><div class="card-head"><div class="card-title">Compatibility</div></div>' +
      U.keyValue([{ label: "Aggregatable", html: U.statusBadge(compat.compatible ? "valid" : "down") }]);
    if (compat.errors && compat.errors.length) {
      html += U.errorState("Errors: " + compat.errors.join("; "));
    }
    if (compat.warnings && compat.warnings.length) {
      html += U.note("Warnings: " + compat.warnings.join("; "));
    }
    html += "</div>";
    return html;
  }

  function renderAggregation(aggregation) {
    if (!aggregation || !aggregation.providers) return "";
    var html = '<div class="card"><div class="card-head"><div class="card-title">Aggregates</div>' +
      '<div class="card-sub">Mode: ' + U.text(aggregation.mode || "macro") + "</div></div>";
    var providers = Object.keys(aggregation.providers);
    providers.forEach(function (provider) {
      var block = aggregation.providers[provider] || {};
      var metrics = block.metrics || {};
      var rows = Object.keys(metrics).map(function (metric) {
        var stat = metrics[metric] || {};
        return [
          { value: metric, cls: "cell-mono cell-strong" },
          Number(stat.mean).toFixed(4),
          Number(stat.std).toFixed(4),
          { value: stat.datasets != null ? U.fmtNum(stat.datasets) : "—", cls: "cell-mono" },
        ];
      });
      html +=
        '<div class="card-head sub"><div class="card-title">' + U.text(provider) + "</div></div>" +
        (rows.length ? U.table(["Metric", "Mean", "Std", "Datasets"], rows) : U.emptyState("No comparable metrics."));
    });
    if (aggregation.fallback_count) {
      html += U.note(aggregation.fallback_count + " result(s) used weight 1.0 (unknown sample size).");
    }
    html += "</div>";
    return html;
  }

  function renderLeaderboards(leaderboards) {
    if (!leaderboards || !Object.keys(leaderboards).length) return "";
    var html = '<div class="card"><div class="card-head"><div class="card-title">Ranks</div>' +
      '<div class="card-sub">Cross-dataset leaderboards by average rank</div></div>';
    Object.keys(leaderboards).forEach(function (metric) {
      var board = leaderboards[metric] || {};
      var list = board.leaderboard || [];
      if (!list.length) return;
      var rows = list.map(function (entry) {
        return [
          { value: entry.provider, cls: "cell-strong" },
          U.text(entry.class || "—"),
          { value: entry.average_rank != null ? Number(entry.average_rank).toFixed(4) : "—", cls: "cell-mono" },
          { value: entry.datasets_ranked != null ? U.fmtNum(entry.datasets_ranked) : "—", cls: "cell-mono" },
          { value: entry.mean_value != null ? Number(entry.mean_value).toFixed(4) : "—", cls: "cell-mono" },
        ];
      });
      html +=
        '<div class="card-head sub"><div class="card-title">' + U.text(metric) + "</div></div>" +
        U.table(["Provider", "Class", "Avg Rank", "Datasets", "Mean"], rows);
    });
    html += "</div>";
    return html;
  }

  function renderComparison(comparison) {
    if (!comparison) return "";
    var html = '<div class="card"><div class="card-head"><div class="card-title">Classical vs Quantum</div></div>';
    var classes = comparison.classes || {};
    Object.keys(classes).forEach(function (cls) {
      var summary = classes[cls] || {};
      if (!(summary.providers || []).length) return;
      var rows = Object.keys(summary.metrics || {}).map(function (metric) {
        var stat = summary.metrics[metric];
        return [
          { value: metric, cls: "cell-mono cell-strong" },
          Number(stat.mean).toFixed(4),
          Number(stat.std).toFixed(4),
          { value: stat.datasets != null ? stat.datasets : "—", cls: "cell-mono" },
        ];
      });
      html +=
        '<div class="card-head sub"><div class="card-title">' + U.text(cls) + "</div>" +
        '<div class="card-sub">' + U.text((summary.providers || []).join(", ") + " · datasets: " + (summary.datasets || []).join(", ")) + "</div></div>" +
        (rows.length ? U.table(["Metric", "Mean", "Std", "Datasets"], rows) : "");
    });
    var deltas = comparison.deltas || {};
    var deltaKeys = Object.keys(deltas);
    if (deltaKeys.length) {
      var deltaRows = deltaKeys.map(function (metric) {
        var delta = deltas[metric] || {};
        return [
          { value: metric, cls: "cell-mono cell-strong" },
          Number(delta.classical_mean).toFixed(4),
          Number(delta.quantum_mean).toFixed(4),
          Number(delta.delta).toFixed(4),
          U.text(delta.conclusion || "—"),
        ];
      });
      html +=
        '<div class="card-head sub"><div class="card-title">Deltas (classical − quantum)</div></div>' +
        U.table(["Metric", "Classical", "Quantum", "Delta", "Conclusion"], deltaRows);
    }
    var conclusions = comparison.conclusions || [];
    if (conclusions.length) {
      html += U.note(conclusions.join(" · "));
    }
    html += "</div>";
    return html;
  }

  function renderGeneralization(generalization) {
    if (!generalization) return "";
    var html = '<div class="card"><div class="card-head"><div class="card-title">Generalization</div>' +
      '<div class="card-sub">Provider ' + U.text(generalization.provider || "—") + " · internal vs external pools</div></div>";
    var perExternal = generalization.per_external || [];
    if (perExternal.length) {
      var rows = perExternal.map(function (row) {
        return [
          { value: row.dataset_id, cls: "cell-mono cell-strong" },
          { value: row.samples, cls: "cell-mono" },
          row.f1 != null ? Number(row.f1).toFixed(4) : "—",
          row.roc_auc != null ? Number(row.roc_auc).toFixed(4) : "—",
        ];
      });
      html += U.table(["Dataset", "Samples", "F1", "ROC-AUC"], rows);
    }
    var gaps = generalization.gaps || [];
    if (gaps.length) {
      var gapRows = gaps.map(function (gap) {
        return [
          { value: gap.metric, cls: "cell-mono cell-strong" },
          Number(gap.internal_mean).toFixed(4),
          Number(gap.external_mean).toFixed(4),
          Number(gap.gap).toFixed(4),
          U.text(gap.note || "—"),
        ];
      });
      html +=
        '<div class="card-head sub"><div class="card-title">Internal → External Gaps</div></div>' +
        U.table(["Metric", "Internal", "External", "Delta", "Note"], gapRows);
    }
    if (generalization.conclusion) {
      html += U.note(generalization.conclusion);
    }
    html += "</div>";
    return html;
  }

  function renderReport(report) {
    var html =
      '<div class="grid grid-4">' +
      U.statCard("Inputs", report.inputs ? report.inputs.length : "—", "report files", "info") +
      U.statCard("Mode", report.aggregation_mode || "—", "aggregation", "") +
      U.statCard("Aggregatable", report.compatibility && report.compatibility.compatible ? "yes" : "no", "compatible", report.compatibility && report.compatibility.compatible ? "success" : "block") +
      U.statCard("Generated", report.generated_at ? U.fmtDateTime(report.generated_at) : "—", "timestamp", "") +
      "</div>" +
      renderInputs(report.inputs) +
      renderCompatibility(report.compatibility) +
      renderAggregation(report.aggregation) +
      renderLeaderboards(report.leaderboards) +
      renderComparison(report.comparison) +
      renderGeneralization(report.generalization) +
      '<div class="card"><div class="card-head"><div class="card-title">Full Report</div>' +
      '<div class="card-sub">Complete serialized cross-dataset analytics document</div></div>' +
      U.codeBlock(report) +
      "</div>";
    return html;
  }

  QG.views.analytics = {
    title: "Analytics",
    group: "overview",
    render: async function (el) {
      el.innerHTML =
        '<div class="page-head">' +
        "<div>" +
        '<h2 class="page-title">Cross-Dataset Analytics</h2>' +
        '<p class="page-sub">Analyze saved report JSON files (benchmarks, evaluations, baselines) with the framework aggregation pipeline: per-dataset inputs, compatibility, aggregates, leaderboards, classical-vs-quantum comparison and generalization.</p>' +
        "</div>" +
        "</div>" +

        '<div class="card">' +
        '<div class="card-head"><div><div class="card-title">Run Analysis</div>' +
        '<div class="card-sub">Enter report JSON paths relative to the artifact root, one per line (e.g. training/&lt;run&gt;/benchmark/*.json or reports/*/*.json). Expand wildcards by listing explicit files.</div></div></div>' +
        '<form id="analyticsForm">' +
        '<div class="field">' +
        '<label for="filesInput">Report JSON files</label>' +
        '<textarea id="filesInput" rows="5" placeholder="training/my-run/benchmark/cross_validation.json&#10;reports/analytics/my-name/report.json"></textarea>' +
        "</div>" +
        '<div class="row grid grid-3">' +
        '<div class="field"><label for="modeSelect">Aggregation mode</label>' +
        '<select id="modeSelect">' +
        "<option value=\"macro\">macro</option>" +
        "<option value=\"weighted\">weighted</option>" +
        "<option value=\"micro\">micro</option>" +
        "</select></div>" +
        '<div class="field"><label for="strictBox">Strict compatibility</label>' +
        '<div class="check-box"><input id="strictBox" type="checkbox" checked /> <span>require full compatibility</span></div></div>' +
        '<div class="field"><label>&nbsp;</label>' +
        '<button type="submit" class="btn primary" id="analyticsBtn">Run Analysis</button></div>' +
        "</div>" +
        "</form>" +
        '<div id="analyticsError"></div>' +
        "</div>" +
        '<div id="analyticsResult"></div>';

      var errorSlot = el.querySelector("#analyticsError");
      var resultSlot = el.querySelector("#analyticsResult");
      var runBtn = el.querySelector("#analyticsBtn");

      el.querySelector("#analyticsForm").addEventListener("submit", async function (event) {
        event.preventDefault();
        errorSlot.innerHTML = "";
        resultSlot.innerHTML = "";
        var raw = el.querySelector("#filesInput").value.trim();
        if (!raw) {
          errorSlot.innerHTML = U.errorState("Enter at least one report JSON path.");
          return;
        }
        var files = raw
          .split(/\r?\n/)
          .map(function (line) { return line.trim(); })
          .filter(Boolean);
        var body = {
          files: files,
          mode: el.querySelector("#modeSelect").value,
          strict: el.querySelector("#strictBox").checked,
        };
        runBtn.disabled = true;
        resultSlot.innerHTML = U.loadingState("Running cross-dataset analysis…");
        try {
          var payload = await api.post(api.endpoints.analyticsCross, body);
          var report = api.data(payload);
          resultSlot.innerHTML = renderReport(report || {});
        } catch (err) {
          resultSlot.innerHTML = "";
          errorSlot.innerHTML = U.errorState(err.message || "Analysis failed.");
        } finally {
          runBtn.disabled = false;
        }
      });
    },
  };
})();