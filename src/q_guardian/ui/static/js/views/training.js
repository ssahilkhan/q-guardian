/* Q-Guardian Console — Training view.
 * Product-workflow detector training: list persisted runs, start a
 * prepare+train job and evaluate trained checkpoints against the evaluation
 * pipeline. Sources are /api/v1/training and /api/v1/datasets.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function numberOrUndefined(value) {
    if (value == null || value === "") return undefined;
    var parsed = Number(value);
    return isNaN(parsed) ? undefined : parsed;
  }

  function renderJob(job) {
    if (!job) return "";
    return (
      '<div class="card">' +
      '<div class="card-head"><div><div class="card-title">Job Queued</div>' +
      '<div class="card-sub">' + U.text(job.label || "") + " · " + U.text(job.kind || "") + "</div></div></div>" +
      U.keyValue([
        { label: "Job ID", value: job.job_id, mono: true },
        { label: "Status", html: U.jobBadge(job.status) },
        { label: "Created", value: U.fmtDateTime(job.created_at) },
        { label: "Output", value: job.output_dir || "—", mono: true },
      ]) +
      "</div>"
    );
  }

  function runsTable(runs) {
    if (!runs.length) {
      return U.emptyState("No training runs recorded yet. Use the Train form above to schedule one.");
    }
    var rows = runs.map(function (run) {
      var model = run.model || {};
      var metric = run.metrics || {};
      return [
        {
          html: '<a class="row-link" href="#/training/' + encodeURIComponent(run.name) + '">' + U.text(run.name) + "</a>",
          title: run.name,
        },
        U.fmtDateTime(run.created_at),
        U.text((run.train_sources || []).join(", ") || "—"),
        model.exists ? (model.quantum ? "quantum" : "classical") : "no model",
        { value: metric.train_samples != null ? U.fmtNum(metric.train_samples) : "—", cls: "cell-mono" },
        run.evaluation_exists ? '<span class="badge badge-success">evaluated</span>' : "—",
      ];
    });
    return U.table(["Run", "Created", "Train Sources", "Model", "Train Samples", "Evaluation"], rows);
  }

  function renderDatasetSelector(catalog, selected) {
    selected = selected || [];
    if (!catalog || !catalog.length) {
      return '<div class="field" id="dsSelection"><span class="field-note">No datasets are available in the catalog.</span></div>';
    }
    var boxes = catalog
      .map(function (entry) {
        var checked = selected.indexOf(entry.dataset_id) !== -1;
        return (
          '<label class="check-item" title="' + U.esc(entry.name || entry.dataset_id) + '">' +
          '<input type="checkbox" value="' + U.esc(entry.dataset_id) + '"' + (checked ? " checked" : "") + (entry.requires_token ? ' data-gated="1"' : "") + " /> " +
          U.text(entry.dataset_id) +
          (entry.requires_token ? ' <span class="badge badge-low">gated</span>' : "") +
          "</label>"
        );
      })
      .join("");
    return (
      '<div class="field">' +
      '<label for="dsSelection">Train on datasets</label>' +
      '<div class="check-grid" id="dsSelection">' + boxes + "</div>" +
      '<span class="field-note">Unchecked sources leave the training sources unchanged (server default). Gated datasets require a configured token.</span>' +
      "</div>"
    );
  }

  function detailView(el, name) {
    el.innerHTML = U.loadingState("Loading training run…");
    return api
      .get(api.endpoints.training + "/" + encodeURIComponent(name))
      .then(function (payload) {
        var run = api.data(payload);
        if (!run) throw new Error("Training run not found.");
        var model = run.model || {};
        var metrics = run.metrics || {};
        var config = run.config || {};
        var dataCfg = config.datasets || {};
        var modelCfg = config.model || {};
        var seed = config.seed != null ? config.seed : "—";

        var splits = run.splits || {};
        var splitsRows = Object.keys(splits).map(function (pool) {
          var count = splits[pool];
          if (typeof count === "object" && count !== null) {
            return [
              { value: pool, cls: "cell-strong" },
              U.fmtNum(count.samples != null ? count.samples : 0),
              U.fmtNum(count.benign != null ? count.benign : 0),
              U.fmtNum(count.malicious != null ? count.malicious : 0),
            ];
          }
          return [
            { value: pool, cls: "cell-strong" },
            U.fmtNum(count || 0),
            "—",
            "—",
          ];
        });

        var evalRow = (run.evaluation || {}).summary || {};

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Training Run</h2>' +
          '<p class="page-sub mono">' + U.text(name) + "</p>" +
          "</div>" +
          '<a class="btn ghost" href="#/training">Back to runs</a>' +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("Model", model.exists ? (model.quantum ? "quantum" : "classical") : "no checkpoint", model.n_estimators ? model.n_estimators + " estimators" : "", model.exists ? "success" : "low") +
          U.statCard("Train Samples", metrics.train_samples != null ? U.fmtNum(metrics.train_samples) : "—", "used for fitting", "") +
          U.statCard("Validation Ratio", config.validation_ratio != null ? (Number(config.validation_ratio) * 100).toFixed(0) + "%" : "—", "seed " + seed, "") +
          U.statCard("Evaluation", run.evaluation_exists ? "available" : "not run", "", run.evaluation_exists ? "success" : "low") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Configuration</div></div>' +
          U.keyValue([
            { label: "Created", value: U.fmtDateTime(run.created_at) },
            { label: "Train Sources", value: (dataCfg.train || []).join(", ") || "—" },
            { label: "Test Sources", value: (dataCfg.test || []).join(", ") || "—" },
            { label: "Validation Ratio", value: config.validation_ratio != null ? config.validation_ratio : "—" },
            { label: "Seed", value: seed },
            { label: "Max Samples / Class", value: config.max_samples_per_class != null ? config.max_samples_per_class : "—" },
            { label: "Threshold", value: config.threshold != null ? config.threshold : "—" },
            { label: "Contamination", value: modelCfg.contamination != null ? modelCfg.contamination : "—" },
            { label: "Quantum", html: U.statusBadge(modelCfg.quantum ? "enabled" : "disabled") },
            { label: "Quantum Shots", value: modelCfg.quantum_shots != null ? modelCfg.quantum_shots : "—" },
            { label: "Quantum Features", value: modelCfg.quantum_feature_count != null ? modelCfg.quantum_feature_count : "—" },
          ]) +
          "</div>" +

          (splitsRows.length
            ? '<div class="card"><div class="card-head"><div class="card-title">Split Sizes</div></div>' +
              U.table(["Pool", "Samples", "Benign", "Malicious"], splitsRows) +
              "</div>"
            : "") +

          '<div class="card"><div class="card-head"><div class="card-title">Metrics</div></div>' +
          U.keyValue([
            { label: "Train Samples", value: metrics.train_samples != null ? metrics.train_samples : "—" },
            { label: "Validation Samples", value: metrics.validation_samples != null ? metrics.validation_samples : "—" },
            { label: "Elapsed (s)", value: metrics.elapsed_seconds != null ? metrics.elapsed_seconds : "—" },
          ]) +
          "</div>" +

          (run.evaluation && Object.keys(evalRow).length
            ? '<div class="card"><div class="card-head"><div class="card-title">Evaluation Summary</div>' +
              '<div class="card-sub">Computed by the evaluation pipeline on internal and external pools</div></div>' +
              U.keyValue(
                Object.keys(evalRow).map(function (key) {
                  var value = evalRow[key];
                  return {
                    label: key.replace(/_/g, " "),
                    value: typeof value === "object" && value !== null ? JSON.stringify(value) : value,
                    mono: typeof value === "number",
                  };
                })
              ) +
              "</div>"
            : "") +

          '<div class="card"><div class="card-head"><div>' +
          '<div class="card-title">Evaluation Report</div>' +
          (run.evaluation_exists
            ? '<div class="card-sub">Generate a downloadable report from the Reports page</div>'
            : '<div class="card-sub">No evaluation recorded for this run yet</div>') +
          "</div>" +
          (model.exists
            ? '<button type="button" class="btn primary" id="evaluateRunBtn">Evaluate</button>'
            : "") +
          "</div>" +
          (run.evaluation_markdown ? '<pre class="code-block">' + U.esc(run.evaluation_markdown) + "</pre>" : (model.exists ? U.emptyState("Run the evaluation to produce a report.") : "")) +
          "</div>" +
          '<div id="evalJob"></div>' +
          (run.training_log
            ? '<div class="card"><div class="card-head"><div class="card-title">Training Log</div>' +
              '<div class="card-sub">Last lines of the training run output</div></div>' +
              '<pre class="code-block">' + U.esc(run.training_log) + "</pre>" +
              "</div>"
            : "");

        var evalBtn = el.querySelector("#evaluateRunBtn");
        if (evalBtn) {
          evalBtn.addEventListener("click", async function () {
            var slot = el.querySelector("#evalJob");
            slot.innerHTML = U.loadingState("Queuing evaluation…");
            evalBtn.disabled = true;
            try {
              var payload = await api.post(api.endpoints.trainingEvaluate(name), {});
              var job = api.data(payload);
              slot.innerHTML = renderJob(job) + U.note("Evaluation runs asynchronously; refresh this run after it finishes.") + '<a class="btn ghost" href="#/training/' + encodeURIComponent(name) + '">Refresh run</a>';
              U.toast("Evaluation queued.", "success");
            } catch (err) {
              slot.innerHTML = U.errorState(err.message || "Could not queue evaluation.");
            } finally {
              evalBtn.disabled = false;
            }
          });
        }
      });
  }

  QG.views.training = {
    title: "Training",
    group: "overview",
    render: async function (el, params) {
      if (params && params.id) {
        return detailView(el, params.id);
      }
      el.innerHTML = U.loadingState("Loading training runs…");
      try {
        var runsPayload = await api.get(api.endpoints.training);
        var catalogPayload = await api.get(api.endpoints.datasets);
        var runs = api.data(runsPayload) || [];
        var catalog = api.data(catalogPayload) || [];

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Detector Training</h2>' +
          '<p class="page-sub">Schedule prepare+train jobs for the hybrid threat detector and evaluate trained checkpoints. Training runs asynchronously — refresh to see progress and new runs.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshTraining">Refresh</button>' +
          "</div>" +

          '<div class="card">' +
          '<div class="card-head"><div><div class="card-title">Train a Detector</div>' +
          '<div class="card-sub">Choose training datasets and optional hyperparameters; the dataset preparation and hybrid training run as a background job.</div></div></div>' +
          '<form id="trainForm">' +
          renderDatasetSelector(catalog) +
          '<div class="row grid grid-3">' +
          '<div class="field"><label for="runName">Run name (optional)</label>' +
          '<input id="runName" type="text" maxlength="80" placeholder="auto-generated" /></div>' +
          '<div class="field"><label for="validationRatio">Validation ratio</label>' +
          '<input id="validationRatio" type="number" min="0" max="0.99" step="0.05" placeholder="server default" /></div>' +
          '<div class="field"><label for="seedInput">Seed</label>' +
          '<input id="seedInput" type="number" min="0" step="1" placeholder="server default" /></div>' +
          '</div><div class="row grid grid-3">' +
          '<div class="field"><label for="maxSamples">Max samples / class</label>' +
          '<input id="maxSamples" type="number" min="1" step="1" placeholder="server default" /></div>' +
          '<div class="field"><label for="estInput">Estimators (n_estimators)</label>' +
          '<input id="estInput" type="number" min="1" step="1" placeholder="server default" /></div>' +
          '<div class="field"><label for="contamInput">Contamination</label>' +
          '<input id="contamInput" type="number" min="0" max="1" step="0.01" placeholder="server default" /></div>' +
          "</div>" +
          '<div class="row grid grid-3">' +
          '<div class="field"><label for="thresholdInput">Decision threshold</label>' +
          '<input id="thresholdInput" type="number" min="0" max="1" step="0.01" placeholder="server default" /></div>' +
          '<div class="field"><label for="quantumBox">Enable quantum provider</label>' +
          '<div class="check-box"><input id="quantumBox" type="checkbox" /> <span>QSVM provider</span></div></div>' +
          '<div class="field"><label for="qShotsInput">Quantum shots</label>' +
          '<input id="qShotsInput" type="number" min="1" step="1" placeholder="e.g. 128" /></div>' +
          "</div>" +
          '<div class="row end"><button type="submit" class="btn primary" id="trainBtn">Start Training</button></div>' +
          "</form>" +
          '<div id="trainError"></div>' +
          '<div id="trainJob"></div>' +
          "</div>" +

          '<div class="section-title">Training Runs</div>' +
          '<div class="card" style="padding:0;box-shadow:none;border:none;background:transparent;">' +
          runsTable(runs) +
          "</div>";

        var errorSlot = el.querySelector("#trainError");
        var jobSlot = el.querySelector("#trainJob");
        var trainBtn = el.querySelector("#trainBtn");

        el.querySelector("#trainForm").addEventListener("submit", async function (event) {
          event.preventDefault();
          errorSlot.innerHTML = "";
          jobSlot.innerHTML = "";
          var datasetIds = [];
          var boxes = el.querySelectorAll("#dsSelection input[type=checkbox]:checked");
          boxes.forEach(function (box) {
            datasetIds.push(box.value);
          });
          var body = {
            dataset_ids: datasetIds.length ? datasetIds : undefined,
            name: el.querySelector("#runName").value || undefined,
            validation_ratio: numberOrUndefined(el.querySelector("#validationRatio").value),
            seed: numberOrUndefined(el.querySelector("#seedInput").value),
            max_samples_per_class: numberOrUndefined(el.querySelector("#maxSamples").value),
            n_estimators: numberOrUndefined(el.querySelector("#estInput").value),
            contamination: numberOrUndefined(el.querySelector("#contamInput").value),
            threshold: numberOrUndefined(el.querySelector("#thresholdInput").value),
            quantum: el.querySelector("#quantumBox").checked || undefined,
            quantum_shots: numberOrUndefined(el.querySelector("#qShotsInput").value),
          };
          trainBtn.disabled = true;
          try {
            var payload = await api.post(api.endpoints.training, body);
            var job = api.data(payload);
            jobSlot.innerHTML = renderJob(job) + U.note("Training runs asynchronously; the run appears in the list once it finishes.") + '<a class="btn ghost" href="#/training">Go to training runs</a>';
            U.toast("Training job queued (" + job.job_id + ").", "success");
          } catch (err) {
            errorSlot.innerHTML = U.errorState(err.message || "Could not queue training.");
          } finally {
            trainBtn.disabled = false;
          }
        });

        el.querySelector("#refreshTraining").addEventListener("click", function () {
          QG.views.training.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load training runs.");
      }
    },
  };
})();