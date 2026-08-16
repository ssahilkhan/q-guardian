/* Q-Guardian Console — Quantum view.
 * Quantum research layer status from /console/models: fusion strategies
 * and backend availability. Quantum is NOT part of the default scan path;
 * this page states that explicitly.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  QG.views.quantum = {
    title: "Quantum",
    group: "analysis",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading quantum status…");
      try {
        var payload = await api.get(api.endpoints.models);
        var status = api.data(payload) || {};
        var quantum = status.quantum || {};
        var backends = quantum.backends || [];
        var strategies = quantum.fusion_strategies || [];
        var installed = backends.filter(function (b) { return b.installed; }).length;

        var rows = backends.map(function (backend) {
          return [
            { value: backend.name, cls: "cell-strong" },
            backend.requires || "none",
            U.statusBadge(backend.installed ? "installed" : "not_installed"),
            backend.description || "—",
          ];
        });

        var strategyChips = strategies.length
          ? strategies.map(function (name) {
              return '<span class="badge badge-accent">' + U.text(name) + "</span>";
            }).join(" ")
          : U.emptyState("No fusion strategies configured.");

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Quantum Research Layer</h2>' +
          '<p class="page-sub">Quantum backends and hybrid fusion strategies shipped with the framework. This layer is experimental and is not part of the default scan path — rule and classical ML analysis run first.</p>' +
          "</div>" +
          "</div>" +

          U.note("Quantum is a research capability in this release. The default scan pipeline runs normalize → validate → features → rules → optional classical ML → decision.") +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Fusion Strategies</div>' +
          '<div class="card-sub">' + strategies.length + " implemented</div></div>" +
          '<div class="chips" style="gap:8px;">' + strategyChips + "</div>" +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Backend Availability</div>' +
          '<div class="card-sub">' + installed + " of " + backends.length + " installed</div></div>" +
          (rows.length
            ? U.table(["Backend", "Requires SDK", "Installed", "Description"], rows)
            : U.emptyState("No quantum backends reported.")) +
          "</div>" +
          "</div>";
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load quantum status.");
      }
    },
  };
})();
