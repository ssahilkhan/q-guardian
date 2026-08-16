/* Q-Guardian Console — Training view.
 * Research artifacts for model training: JSONL datasets and the trained
 * model storage directory, read from disk via /console/research. Nothing
 * here re-runs training.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function datasetsCard(datasets) {
    if (!datasets.length) {
      return U.emptyState("No JSONL datasets found under data/.");
    }
    var rows = datasets.map(function (dataset) {
      return [
        { value: dataset.name, cls: "cell-mono cell-strong" },
        U.fmtBytes(dataset.size),
        dataset.rows == null ? "—" : U.fmtNum(dataset.rows),
        dataset.fields.length ? dataset.fields.join(", ") : "—",
        dataset.note || "—",
      ];
    });
    return U.table(["Dataset", "Size", "Rows", "Fields (first record)", "Note"], rows);
  }

  function artifactsCard(artifacts) {
    if (!artifacts.length) {
      return U.emptyState("No trained model artifacts found under models/ml/. Train models through the framework to populate this view.");
    }
    var rows = artifacts.map(function (artifact) {
      return [
        { value: artifact.name, cls: "cell-mono cell-strong" },
        artifact.kind || "file",
        U.fmtBytes(artifact.size),
        U.fmtDateTime(artifact.modified),
      ];
    });
    return U.table(["Artifact", "Kind", "Size", "Modified"], rows);
  }

  QG.views.training = {
    title: "Training",
    group: "research",
    render: async function (el) {
      el.innerHTML = U.loadingState("Reading training artifacts…");
      try {
        var payload = await api.get(api.endpoints.research);
        var research = api.data(payload) || {};
        var datasets = research.datasets || [];
        var artifacts = research.model_artifacts || [];

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Training</h2>' +
          '<p class="page-sub">On-disk research artifacts used by model training and evaluation. The console only reads existing files — it never trains or modifies models.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshTraining">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("Datasets", datasets.length, "JSONL under data/", "info") +
          U.statCard("Total Rows", datasets.reduce(function (sum, d) { return sum + (d.rows || 0); }, 0), "across datasets", "info") +
          U.statCard("Model Artifacts", artifacts.length, "under models/ml/", "success") +
          U.statCard("Artifact Size", U.fmtBytes(artifacts.reduce(function (sum, a) { return sum + (a.size || 0); }, 0)), "on disk", "") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Datasets</div>' +
          '<div class="card-sub">Inventoried from data/*.jsonl</div></div>' +
          datasetsCard(datasets) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Trained Model Storage</div>' +
          '<div class="card-sub">Metadata only — binary model contents are never deserialized</div></div>' +
          artifactsCard(artifacts) +
          "</div>";

        el.querySelector("#refreshTraining").addEventListener("click", function () {
          QG.views.training.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not read training artifacts.");
      }
    },
  };
})();
