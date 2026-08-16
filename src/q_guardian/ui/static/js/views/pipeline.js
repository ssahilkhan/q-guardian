/* Q-Guardian Console — Pipeline view.
 * Stage inventory with live availability from /console/components plus a
 * truthful flow description: quantum is a research layer, not part of the
 * default scan path.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  QG.views.pipeline = {
    title: "Pipeline",
    group: "analysis",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading pipeline stages…");
      try {
        var payload = await api.get(api.endpoints.components);
        var stages = api.data(payload) || [];
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
          '<div class="card"><div class="card-head"><div class="card-title">Pipeline Stages</div></div>' +
          U.table(["Stage", "Status", "Details"], rows) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Execution Order</div></div>' +
          '<div class="prose"><p>Every prompt is processed in this order:</p><ol class="timeline">' +
          ["Normalize", "Validate", "Extract features", "Apply rules", "Optional classical ML", "Decide", "Respond"].map(function (step) {
            return "<li>" + U.text(step) + "</li>";
          }).join("") +
          "</ol><p>Quantum fusion strategies and backends are shown under <a href=\"#/quantum\">Quantum</a> and are treated as research capabilities.</p></div>" +
          "</div>" +
          "</div>";
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load pipeline stages.");
      }
    },
  };
})();
