/* Q-Guardian Console — Datasets view.
 * Product-workflow dataset management: catalog + access status from
 * /api/v1/datasets, dataset-authentication state from /auth-status, and an
 * inventory of on-disk prepared data from /prepared. Preparation is
 * scheduled as an asynchronous job via POST /{dataset_id}/prepare.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  var ACCESS_LABELS = {
    public: "public",
    authenticated: "authenticated",
    gated: "gated",
    private: "private",
  };

  function accessBadge(access) {
    if (!access) return U.statusBadge("unknown");
    var accessType = ACCESS_LABELS[access.access_type] || access.access_type || "unknown";
    var tone = "low";
    if (access.is_accessible) tone = "success";
    else if (accessType === "gated" || accessType === "private") tone = "block";
    else if (accessType === "authenticated") tone = "warn";
    return '<span class="badge badge-' + tone + '">' + U.text(accessType) + "</span>";
  }

  function tokenStatus(auth) {
    if (!auth) return U.statusBadge("unknown");
    if (auth.token_configured) {
      return auth.token_format_valid === false
        ? '<span class="badge badge-block">invalid format</span>'
        : U.statusBadge("valid");
    }
    return U.statusBadge("disabled");
  }

  function renderAuth(auth) {
    if (!auth) return U.emptyState("Authentication status is unavailable.");
    return U.keyValue([
      { label: "Provider", value: auth.provider || "—", mono: true },
      { label: "Token Env Var", value: auth.token_env_var || "—", mono: true },
      { label: "Token Configured", html: U.statusBadge(auth.token_configured ? "enabled" : "disabled") },
      { label: "Token Status", html: tokenStatus(auth) },
      { label: "Message", value: auth.message || "—" },
    ]);
  }

  function renderJob(job) {
    if (!job) return "";
    return (
      '<div class="card">' +
      '<div class="card-head"><div><div class="card-title">Preparation Queued</div>' +
      '<div class="card-sub">Job ' + U.text(job.kind || "") + " · " + U.text(job.label || "") + "</div></div></div>" +
      U.keyValue([
        { label: "Job ID", value: job.job_id, mono: true },
        { label: "Status", html: U.jobBadge(job.status) },
        { label: "Created", value: U.fmtDateTime(job.created_at) },
        { label: "Output", value: job.output_dir || "—", mono: true },
      ]) +
      "</div>"
    );
  }

  function renderCatalog(catalog) {
    return U.table(
      ["Dataset ID", "Name", "Source", "Access", "Token", "Max Samples", "Groups", ""],
      catalog.map(function (entry) {
        var access = entry.access || {};
        return [
          { value: entry.dataset_id, cls: "cell-mono cell-strong" },
          entry.name || "—",
          entry.source_type || "—",
          accessBadge(access),
          entry.requires_token ? "yes" : "no",
          { value: entry.max_samples != null ? U.fmtNum(entry.max_samples) : "—", cls: "cell-mono" },
          U.text((entry.groups || []).join(", ")),
          {
            html:
              '<button type="button" class="btn ghost" data-prepare="' + U.esc(entry.dataset_id) + '">Prepare</button>',
          },
        ];
      })
    );
  }

  QG.views.datasets = {
    title: "Datasets",
    group: "overview",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading datasets…");
      try {
        var catalogPayload, authPayload, preparedPayload;
        try {
          catalogPayload = await api.get(api.endpoints.datasets);
        } catch (e) {
          catalogPayload = { data: [] };
        }
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
        var catalog = api.data(catalogPayload) || [];
        var auth = api.data(authPayload);
        var prepared = api.data(preparedPayload) || [];

        var preparedSamples = 0;
        prepared.forEach(function (entry) {
          Object.keys(entry.pools || {}).forEach(function (pool) {
            preparedSamples += Number((entry.pools[pool] || {}).samples || 0);
          });
        });

        var preparedRows = prepared.map(function (entry) {
          var pools = [];
          Object.keys(entry.pools || {}).forEach(function (pool) {
            var stats = entry.pools[pool] || {};
            pools.push(pool + ": " + U.fmtNum(stats.samples || 0));
          });
          return [
            { value: entry.id, cls: "cell-mono cell-strong" },
            entry.kind || "—",
            (entry.dataset_ids || []).join(", ") || "—",
            pools.join(" · ") || "—",
            U.fmtDateTime(entry.generated_at),
          ];
        });

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Datasets</h2>' +
          '<p class="page-sub">The packaged dataset catalog with access state. Datasets are prepared on demand through server-side background jobs; results land under the artifact root and feed the detector training pipeline.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshDatasets">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("Catalog", catalog.length, "registered datasets", "info") +
          U.statCard("Public", catalog.filter(function (d) { return !(d.requires_token || ((d.access || {}).requires_token)); }).length, "no token required", "success") +
          U.statCard("Gated", catalog.filter(function (d) { return !!(d.requires_token || ((d.access || {}).requires_token)); }).length, "token required", "") +
          U.statCard("Prepared", prepared.length, U.fmtNum(preparedSamples) + " samples staged", "success") +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Dataset Authentication</div>' +
          '<div class="card-sub">Server-side Hugging Face token state — the token value is never exposed</div></div>' +
          renderAuth(auth) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Catalog & Preparation</div>' +
          '<div class="card-sub">Prepare a dataset to download, normalize, split and persist it on-disk</div></div>' +
          '<div id="catalogWrap"></div>' +
          '<div id="jobResult"></div>' +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Prepared Data</div>' +
          '<div class="card-sub">Persisted dataset manifests and their pool statistics</div></div>' +
          (preparedRows.length ? U.table(["ID", "Kind", "Datasets", "Pools", "Generated"], preparedRows) : U.emptyState("No datasets are prepared yet. Use Prepare above to stage one.")) +
          "</div>" +
          '<div id="prepareError"></div>';

        var errors = el.querySelector("#prepareError");
        var jobSlot = el.querySelector("#jobResult");

        function bindPrepare() {
          var buttons = el.querySelectorAll("[data-prepare]");
          buttons.forEach(function (button) {
            button.addEventListener("click", async function () {
              var dsId = button.getAttribute("data-prepare");
              errors.innerHTML = "";
              jobSlot.innerHTML = "";
              button.disabled = true;
              try {
                var payload = await api.post(api.endpoints.datasets + "/" + encodeURIComponent(dsId) + "/prepare", {});
                var job = api.data(payload);
                jobSlot.innerHTML = renderJob(job);
                U.toast("Preparation queued for " + dsId + ".", "success");
                QG.views.datasets.render(el);
              } catch (err) {
                errors.innerHTML = U.errorState(err.message || "Could not queue preparation.");
              } finally {
                button.disabled = false;
              }
            });
          });
        }

        el.querySelector("#catalogWrap").innerHTML = renderCatalog(catalog);
        bindPrepare();

        el.querySelector("#refreshDatasets").addEventListener("click", function () {
          QG.views.datasets.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load datasets.");
      }
    },
  };
})();