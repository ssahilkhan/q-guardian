/* Q-Guardian Console — Pipeline view.
 * Stage inventory with live availability from /console/components plus a
 * truthful flow description: quantum is a research layer, not part of the
 * default scan path. Shows real ML and component status.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function renderFlowDiagram(components) {
    var stageMap = {};
    (components || []).forEach(function (c) { stageMap[c.id] = c; });

    function stageIcon(id) {
      var s = stageMap[id];
      if (!s) return '<span class="pipeline-icon pipeline-off"></span>';
      if (s.status === "active") return '<span class="pipeline-icon pipeline-check"></span>';
      if (s.status === "available") return '<span class="pipeline-icon pipeline-warn" title="Available but not active"></span>';
      return '<span class="pipeline-icon pipeline-off"></span>';
    }

    function stageName(id) {
      var s = stageMap[id];
      return s ? s.name : id;
    }

    var flow = [
      { id: "normalize", next: "validate" },
      { id: "validate", next: "features" },
      { id: "features", next: "rules" },
      { id: "rules", next: "ml" },
      { id: "ml", next: "decision" },
      { id: "decision", next: null },
    ];

    var rows = [];
    flow.forEach(function (step, i) {
      rows.push([
        { html: stageIcon(step.id), cls: "cell-icon" },
        { value: stageName(step.id), cls: "cell-strong" },
        U.statusBadge(stageMap[step.id] ? stageMap[step.id].status : "unavailable"),
        stageMap[step.id] ? stageMap[step.id].detail : "—",
      ]);
      if (step.next) {
        rows.push([
          { html: '<span class="flow-arrow">↓</span>', cls: "cell-icon flow-cell" },
          { html: "", cls: "" },
          { html: "", cls: "" },
          { html: "", cls: "" },
        ]);
      }
    });

    return U.table(["", "Stage", "Status", "Details"], rows);
  }

  QG.views.pipeline = {
    title: "Pipeline",
    group: "analysis",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading pipeline stages…");
      try {
        var results = await Promise.all([
          api.get(api.endpoints.components),
          api.get(api.endpoints.models).catch(function () { return null; }),
        ]);
        var payload = results[0];
        var modelsPayload = results[1];

        var stages = api.data(payload) || [];
        var models = modelsPayload ? api.data(modelsPayload) : {};
        var ml = (models && models.ml) || {};

        var rows = stages.map(function (stage) {
          return [
            { value: stage.name, cls: "cell-strong" },
            U.statusBadge(stage.status),
            stage.detail,
          ];
        });

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Analysis Pipeline</h2>' +
          '<p class="page-sub">The stages a prompt passes through at scan time, with live availability. Classical ML runs only when models are loaded and ML is enabled; quantum fusion is available as a research layer and is not part of the default scan path.</p>' +
          "</div>" +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Pipeline Flow</div>' +
          '<div class="card-sub">Visual execution order with live status</div></div>' +
          renderFlowDiagram(stages) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Stage Details</div></div>' +
          U.table(["Stage", "Status", "Details"], rows) +
          "</div>" +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">ML Pipeline Status</div></div>' +
          U.keyValue([
            { label: "ML Active", html: U.statusBadge(ml.active ? "active" : "inactive") },
            { label: "Detectors", value: ml.detector_count || 0 },
            { label: "Classifiers", value: ml.classifier_count || 0 },
            { label: "Loaded Models", value: (ml.loaded_models || 0) + " / " + (ml.total_models || 0) },
            { label: "Quantum Active", html: U.statusBadge("disabled") },
          ]) +
          U.note("Quantum is a research capability in this release. The default scan pipeline runs normalize → validate → features → rules → optional classical ML → decision.") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Execution Order</div></div>' +
          '<div class="prose"><p>Every prompt is processed in this order:</p><ol class="timeline">' +
          ["Normalize", "Validate", "Extract features", "Apply rules", "Optional classical ML", "Decide", "Respond"].map(function (step) {
            return "<li>" + U.text(step) + "</li>";
          }).join("") +
          "</ol></div>" +
          "</div>";
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load pipeline stages.");
      }
    },
  };
})();
