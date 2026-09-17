/* Q-Guardian Console — Settings view.
 * Product-workflow settings that the operator can inspect from the console:
 * dataset authentication state and the on-disk artifact workspace. All values
 * come from real endpoints; secret material is never exposed.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function renderAuth(auth) {
    if (!auth) return U.emptyState("Dataset authentication status is unavailable.");
    return U.keyValue([
      { label: "Provider", value: auth.provider || "—", mono: true },
      { label: "Token Env Var", value: auth.token_env_var || "—", mono: true },
      { label: "Token Configured", html: U.statusBadge(auth.token_configured ? "enabled" : "disabled") },
      {
        label: "Token Valid",
        html:
          auth.token_format_valid === null || auth.token_format_valid === undefined
            ? "—"
            : U.statusBadge(auth.token_format_valid ? "valid" : "down"),
      },
      { label: "Message", value: auth.message || "—" },
    ]);
  }

  function renderPrepared(prepared) {
    if (!prepared || !prepared.length) {
      return U.emptyState("Nothing is prepared on disk yet.");
    }
    var rows = prepared.map(function (entry) {
      var poolCounts = [];
      Object.keys(entry.pools || {}).forEach(function (pool) {
        var stats = entry.pools[pool] || {};
        poolCounts.push(pool + ": " + U.fmtNum(stats.samples || 0));
      });
      return [
        { value: entry.id, cls: "cell-mono cell-strong" },
        entry.kind || "—",
        (entry.dataset_ids || []).join(", ") || "—",
        poolCounts.join(" · ") || "—",
        U.fmtDateTime(entry.generated_at),
      ];
    });
    return U.table(["ID", "Kind", "Datasets", "Pools", "Generated"], rows);
  }

  QG.views.settings = {
    title: "Settings",
    group: "system",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading settings…");
      try {
        var authPayload, preparedPayload, reportsPayload, runsPayload;
        try {
          authPayload = await api.get(api.endpoints.datasetsAuthStatus);
        } catch (e) {
          authPayload = { data: null };
        }
        try {
          preparedPayload = await api.get(api.endpoints.datasetsPrepared);
        } catch (e) {
          preparedPayload = { data: [] };
        }
        try {
          reportsPayload = await api.get(api.endpoints.reports);
        } catch (e) {
          reportsPayload = { data: [] };
        }
        try {
          runsPayload = await api.get(api.endpoints.training);
        } catch (e) {
          runsPayload = { data: [] };
        }
        var auth = api.data(authPayload);
        var prepared = api.data(preparedPayload) || [];
        var reports = api.data(reportsPayload) || [];
        var runs = api.data(runsPayload) || [];

        var totalSamples = 0;
        prepared.forEach(function (entry) {
          Object.keys(entry.pools || {}).forEach(function (pool) {
            totalSamples += Number((entry.pools[pool] || {}).samples || 0);
          });
        });

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Settings</h2>' +
          '<p class="page-sub">The product workflow’s configuration surface: dataset authentication and the artifact workspace. Secrets and tokens are never shown — only their presence and validity.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshSettings">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("Prepared Artifacts", prepared.length, "on disk", "info") +
          U.statCard("Prepared Samples", U.fmtNum(totalSamples), "across pools", "") +
          U.statCard("Training Runs", runs.length, "persisted", "info") +
          U.statCard("Report Files", reports.length, "artifact entries", "") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Dataset Authentication</div>' +
          '<div class="card-sub">Server-side Hugging Face token used by dataset preparation — the token value is never exposed to the console</div></div>' +
          renderAuth(auth) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Prepared Data Workspace</div>' +
          '<div class="card-sub">Dataset manifests persisted under the artifact root</div></div>' +
          renderPrepared(prepared) +
          "</div>";

        var refreshBtn = el.querySelector("#refreshSettings");
        if (refreshBtn) {
          refreshBtn.addEventListener("click", function () {
            QG.views.settings.render(el);
          });
        }
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load settings.");
      }
    },
  };
})();