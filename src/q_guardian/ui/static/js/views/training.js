/* Q-Guardian Console — Training view.
 * Training status + research artifacts for model training: JSONL datasets,
 * the trained model storage directory and the evaluation report, all read
 * from disk via /console/research.
 *
 * The backend exposes ONLY artifact inventory for training — there is no
 * live training run, progress endpoint, WebSocket event stream or per-epoch
 * metrics. This view therefore reports the training state truthfully
 * (UNAVAILABLE for a live run) and surfaces the real artifacts that exist.
 * Nothing here re-runs training and nothing is simulated.
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

  function evaluationRows(evaluation, artifacts) {
    var trainingFiles = artifacts.filter(function (artifact) {
      return /\.(pkl|joblib|pt|onnx|json)$/i.test(artifact.name);
    });
    return U.table(
      ["Artifact", "Status", "Details"],
      [
        [
          { value: "Evaluation report", cls: "cell-strong" },
          U.badge(evaluation.present ? "Present" : "Not generated", evaluation.present ? "success" : "low"),
          evaluation.present
            ? (evaluation.generated_at ? "Generated " + U.fmtDateTime(evaluation.generated_at) : "Report on disk") + (evaluation.scores_csv ? " · scores.csv" : "") + (evaluation.report_md ? " · report.md" : "")
            : (evaluation.note || "Run `python scripts/evaluate_pipeline.py` to generate one."),
        ],
        [
          { value: "Trained model files", cls: "cell-strong" },
          U.badge(trainingFiles.length ? "Present" : "None under models/ml/", trainingFiles.length ? "success" : "low"),
          trainingFiles.length
            ? trainingFiles.map(function (a) { return a.name; }).join(", ")
            : "Trained artifacts in this repo live under examples/qg_state/ but the backend research reader only inventories models/ml/.",
        ],
        [
          { value: "Live training run", cls: "cell-strong" },
          U.badge("Unavailable", "low"),
          "The backend exposes no training process, progress endpoint, or event stream. No progress is displayed or simulated.",
        ],
      ]
    );
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
        var evaluation = research.evaluation || {};

        var hasArtifacts = datasets.length > 0 || artifacts.length > 0;
        var stateCls = hasArtifacts ? "success" : "low";
        var stateLabel = hasArtifacts ? "Artifacts on disk" : "No artifacts found";

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Training</h2>' +
          '<p class="page-sub">Training status and on-disk research artifacts used by model training and evaluation. The console only reads existing files — it never trains, never simulates a run, and never shows progress the backend does not report.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshTraining">Refresh</button>' +
          "</div>" +

          '<div class="card">' +
          '<div class="card-head"><div class="card-title">Training Status</div></div>' +
          U.keyValue([
            { label: "State", html: U.badge(stateLabel, stateCls) },
            { label: "Live Run", html: U.badge("Not running", "low") },
            { label: "Progress", value: "Unavailable" },
            { label: "Epoch / Loss / Accuracy", value: "Not reported by backend" },
          ]) +
          U.note("The backend does not expose a running training process, progress percentage, epoch counts or loss/accuracy metrics through any console API or event stream. This view reports the authoritative training status available: the real artifacts on disk. If a live training endpoint is added later, this card can consume it.") +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("Datasets", datasets.length, "JSONL under data/", "info") +
          U.statCard("Total Rows", datasets.reduce(function (sum, d) { return sum + (d.rows || 0); }, 0), "across datasets", "info") +
          U.statCard("Model Artifacts", artifacts.length, "under models/ml/", "success") +
          U.statCard("Artifact Size", U.fmtBytes(artifacts.reduce(function (sum, a) { return sum + (a.size || 0); }, 0)), "on disk", "") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Training Run &amp; Artifact Status</div>' +
          '<div class="card-sub">Metadata only — binary model contents are never deserialized</div></div>' +
          evaluationRows(evaluation, artifacts) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Datasets</div>' +
          '<div class="card-sub">Inventoried from data/*.jsonl</div></div>' +
          datasetsCard(datasets) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Trained Model Storage</div>' +
          '<div class="card-sub">Metadata only — binary model contents are never deserialized</div></div>' +
          artifactsCard(artifacts) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Evaluation Report</div></div>' +
          (evaluation.present
            ? U.keyValue([
                { label: "Status", html: U.badge("Present", "success") },
                { label: "Generated", value: evaluation.generated_at ? U.fmtDateTime(evaluation.generated_at) : "—" },
                { label: "Attachments", value: [evaluation.scores_csv ? "scores.csv" : null, evaluation.report_md ? "report.md" : null].filter(Boolean).join(", ") || "—" },
              ]) + (evaluation.note ? U.note(evaluation.note) : "")
            : U.note(evaluation.note || "No evaluation report found on disk.")) +
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