/* Q-Guardian Console — Models view.
 * Classical ML model registry status from /console/models. Quantum
 * backends and fusion strategies live on the dedicated Quantum page.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  QG.views.models = {
    title: "Models",
    group: "analysis",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading model status…");
      try {
        var payload = await api.get(api.endpoints.models);
        var status = api.data(payload) || {};
        var ml = status.ml || {};

        var rows = (ml.models || []).map(function (model) {
          return [
            { value: model.name, cls: "cell-strong" },
            model.model_type || "—",
            model.backend || "—",
            model.version || "—",
            U.statusBadge(model.status),
            model.description || "—",
          ];
        });

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Classical ML Models</h2>' +
          '<p class="page-sub">Registered detectors and classifiers in the model registry. Inference runs only when ML is enabled and models are loaded.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshModels">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("ML Active", ml.active ? "Yes" : "No", "", ml.active ? "success" : "warning") +
          U.statCard("Detectors", ml.detector_count, "registered", "success") +
          U.statCard("Classifiers", ml.classifier_count, "registered", "success") +
          U.statCard("Loaded Models", ml.loaded_models + " / " + ml.total_models, "loaded / total", ml.loaded_models > 0 ? "success" : "warning") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Model Registry</div></div>' +
          (rows.length
            ? U.table(["Name", "Type", "Backend", "Version", "Status", "Description"], rows)
            : U.emptyState("No models registered. Train and load models through the framework.")) +
          "</div>";

        el.querySelector("#refreshModels").addEventListener("click", function () {
          QG.views.models.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load model status.");
      }
    },
  };
})();
