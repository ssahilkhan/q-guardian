/* Q-Guardian Console — Security Scans view.
 * Product-workflow security scanning: start a cross-validation (cv) or model
 * evaluation (model_eval) scan job and browse the persisted scan history with
 * verdicts and fusion detection metrics.
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
      '<div class="card-head"><div><div class="card-title">Scan Queued</div>' +
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

  function targetOptions(prepared, runs) {
    var options = [];
    if (prepared && prepared.length) {
      options.push(
        '<optgroup label="Prepared datasets">' +
          prepared
            .map(function (entry) {
              return '<option value="' + U.esc(entry.id) + '">' + U.text(entry.id) + "</option>";
            })
            .join("") +
          "</optgroup>"
      );
    }
    var trained = (runs || []).filter(function (run) {
      return (run.model || {}).exists;
    });
    if (trained.length) {
      options.push(
        '<optgroup label="Trained runs (model_eval)">' +
          trained
            .map(function (run) {
              return '<option value="' + U.esc(run.name) + '">' + U.text(run.name) + "</option>";
            })
            .join("") +
          "</optgroup>"
      );
    }
    return options.join("");
  }

  function renderHistory(scans) {
    if (!scans || !scans.length) {
      return U.emptyState("No security scans recorded yet. Use the form above to start one.");
    }
    var rows = scans.map(function (scan) {
      var verdict = scan.verdict || {};
      return [
        {
          html: '<a class="row-link" href="#/scans/' + encodeURIComponent(scan.scan_id) + '">' + U.text(scan.scan_id) + "</a>",
          title: scan.scan_id,
        },
        U.fmtDateTime(scan.created_at),
        scan.scan_type || scan.kind || "—",
        { value: scan.target || "—", cls: "cell-mono" },
        U.jobBadge(scan.status),
        U.verdictBadge(verdict.level),
        (scan.error ? '<span class="text-dim" title="' + U.esc(scan.error) + '">failed</span>' : U.fmtDateTime(scan.finished_at)),
      ];
    });
    return U.table(["Scan", "Created", "Type", "Target", "Status", "Verdict", "Finished"], rows);
  }

  QG.views.scans = {
    title: "Security Scans",
    group: "overview",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading security scans…");
      try {
        var scansPayload = await api.get(api.endpoints.scans);
        var preparedPayload = await api.get(api.endpoints.datasetsPrepared);
        var runNamesPayload = await api.get(api.endpoints.training);
        var scans = api.data(scansPayload) || [];
        var prepared = api.data(preparedPayload) || [];
        var runs = api.data(runNamesPayload) || [];

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Security Scans</h2>' +
          '<p class="page-sub">Run the hybrid evaluator over a prepared dataset or trained detector (cross-validation, or direct model evaluation) and review verdicts computed from measured fusion detection rates.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshScans">Refresh</button>' +
          "</div>" +

          '<div class="card">' +
          '<div class="card-head"><div><div class="card-title">Start a Security Scan</div>' +
          '<div class="card-sub">Scanning runs asynchronously; the verdict below is derived from the measured fusion detection rate (recall).</div></div></div>' +
          '<form id="scanForm">' +
          '<div class="row grid grid-3">' +
          '<div class="field"><label for="scanType">Scan type</label>' +
          '<select id="scanType">' +
          '<option value="cv">Cross-validation (cv)</option>' +
          '<option value="model_eval">Model evaluation (model_eval)</option>' +
          "</select></div>" +
          "<div class=\"field\" id=\"targetField\"><label for=\"scanTarget\">Target</label>" +
          '<select id="scanTarget">' + (targetOptions(prepared, runs) || '<option value="">No prepared targets available</option>') + "</select></div>" +
          '<div class="field"><label for="scanK">Folds (k)</label>' +
          '<input id="scanK" type="number" min="2" max="10" step="1" value="3" /></div>' +
          "</div>" +
          '<div class="row grid grid-3">' +
          '<div class="field"><label for="scanSeed">Seed</label>' +
          '<input id="scanSeed" type="number" min="0" step="1" value="42" /></div>' +
          '<div class="field"><label for="scanThreshold">Decision threshold</label>' +
          '<input id="scanThreshold" type="number" min="0" max="1" step="0.01" value="0.5" /></div>' +
          '<div class="field"><label for="scanAblate">Provider ablation</label>' +
          '<div class="check-box"><input id="scanAblate" type="checkbox" /> <span>also run ablation</span></div></div>' +
          "</div>" +
          '<div class="row end"><button type="submit" class="btn primary" id="scanBtn">Start Scan</button></div>' +
          "</form>" +
          '<div id="scanError"></div>' +
          '<div id="scanJob"></div>' +
          "</div>" +

          '<div class="section-title">Scan History</div>' +
          '<div class="card" style="padding:0;box-shadow:none;border:none;background:transparent;">' +
          renderHistory(scans) +
          "</div>";

        var errorSlot = el.querySelector("#scanError");
        var jobSlot = el.querySelector("#scanJob");
        var scanBtn = el.querySelector("#scanBtn");
        var typeSelect = el.querySelector("#scanType");
        var targetSelect = el.querySelector("#scanTarget");

        el.querySelector("#scanForm").addEventListener("submit", async function (event) {
          event.preventDefault();
          errorSlot.innerHTML = "";
          jobSlot.innerHTML = "";
          var type = typeSelect.value;
          var target = targetSelect.value;
          if (!target) {
            errorSlot.innerHTML = U.errorState("Choose a prepared dataset or trained run as the scan target.");
            return;
          }
          var body = {
            type: type,
            target: target,
            k: numberOrUndefined(el.querySelector("#scanK").value) || undefined,
            seed: numberOrUndefined(el.querySelector("#scanSeed").value) || undefined,
            threshold: numberOrUndefined(el.querySelector("#scanThreshold").value) || undefined,
            ablate: el.querySelector("#scanAblate").checked || undefined,
          };
          scanBtn.disabled = true;
          try {
            var payload = await api.post(api.endpoints.scans, body);
            var job = api.data(payload);
            jobSlot.innerHTML = renderJob(job) + U.note("The scan runs in the background; refresh to see the verdict.") + '<a class="btn ghost" href="#/scans">Refresh scans</a>';
            U.toast("Security scan queued (" + job.job_id + ").", "success");
          } catch (err) {
            errorSlot.innerHTML = U.errorState(err.message || "Could not queue the scan.");
          } finally {
            scanBtn.disabled = false;
          }
        });

        el.querySelector("#refreshScans").addEventListener("click", function () {
          QG.views.scans.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load security scans.");
      }
    },
  };
})();