/* Q-Guardian Console — Quantum view.
 * Quantum research layer status from /console/models: fusion strategies
 * and backend availability. Quantum is NOT part of the default scan path;
 * this page states that explicitly and shows the research status clearly.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function quantumState(quantum) {
    var active = quantum && quantum.active === true;
    var backends = (quantum && quantum.backends) || [];
    var installed = backends.filter(function (b) { return b.installed; });
    if (active) {
      return {
        label: "Active",
        cls: "success",
        detail: "Hybrid quantum fusion is active in the scan path.",
      };
    }
    if (installed.length) {
      return {
        label: "Available — Not Executed",
        cls: "warn",
        detail: installed.map(function (b) { return b.name; }).join(", ") +
          " available; quantum is a research layer and is not executed in the default scan path.",
      };
    }
    return {
      label: "Unavailable",
      cls: "low",
      detail: "No quantum backends are installed. Quantum is research-only.",
    };
  }

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
        var localSim = backends.filter(function (b) { return b.name === "local-simulator"; });
        var localAvailable = localSim.length > 0 && localSim[0].installed;
        var state = quantumState(quantum);

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

        var interfaceOnly = quantum.fusion_interface_only || [];
        var interfaceNote = interfaceOnly.length
          ? " Interface-only strategy (not implemented): " + interfaceOnly.join(", ") + "."
          : "";

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Quantum Research Layer</h2>' +
          '<p class="page-sub">Quantum backends and hybrid fusion strategies shipped with the framework, reported from /console/models. State is derived from the live backend payload — this console never assumes quantum activity.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshQuantum">Refresh</button>' +
          "</div>" +

          '<div class="card">' +
          '<div class="card-head"><div class="card-title">Quantum State</div></div>' +
          U.keyValue([
            { label: "State", html: U.badge(state.label, state.cls) },
            { label: "Active in Scan Path", html: U.badge(quantum.active ? "Yes" : "No", quantum.active ? "success" : "low") },
            { label: "Backends Installed", value: installed + " / " + backends.length },
            { label: "Fusion Strategies", value: strategies.length },
          ]) +
          U.note(state.detail) +
          "</div>" +

          U.note("Quantum is not part of the default scan path in this release (the backend reports active=false). The default scan pipeline runs normalize → validate → features → rules → optional classical ML → decision.") +

          '<div class="grid grid-4">' +
          U.statCard("Status", state.label, state.cls === "success" ? "hybrid fusion active" : "not executed in scan path", state.cls === "success" ? "success" : state.cls === "warn" ? "warning" : "low") +
          U.statCard("Backends", installed + " / " + backends.length, "installed", installed > 0 ? "success" : "low") +
          U.statCard("Fusion Strategies", strategies.length, "implemented", strategies.length > 0 ? "info" : "low") +
          U.statCard("Local Simulator", localAvailable ? "Available" : "Not Found", localAvailable ? "ships with the framework" : "reported by backend as unavailable", localAvailable ? "success" : "warning") +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Fusion Strategies</div>' +
          '<div class="card-sub">' + strategies.length + " implemented</div></div>" +
          '<div class="chips" style="gap:8px;">' + strategyChips + "</div>" +
          (interfaceOnly.length
            ? '<div class="card-sub" style="margin-top:10px;">Interface only (not implemented): ' + U.text(interfaceOnly.join(", ")) + "</div>"
            : "") +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Backend Availability</div>' +
          '<div class="card-sub">' + installed + " of " + backends.length + " installed</div></div>" +
          (rows.length
            ? U.table(["Backend", "Requires SDK", "Installed", "Description"], rows)
            : U.emptyState("No quantum backends reported.")) +
          "</div>" +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">How Quantum Fits</div></div>' +
          '<div class="prose"><ol class="timeline">' +
          ["Prompt normalized", "Features extracted", "Rule engine runs", "Classical ML runs (if enabled)", "Fusion strategy combines scores (if quantum active)", "Decision: ALLOW / WARN / REVIEW / BLOCK"].map(function (step) {
            return "<li>" + U.text(step) + "</li>";
          }).join("") +
          "</ol></div>" +
          U.note("In the current release quantum is research-only. Hybrid fusion is opt-in and requires Qiskit SDK and a compatible backend.") +
          "</div>";

        var refresh = el.querySelector("#refreshQuantum");
        if (refresh) refresh.addEventListener("click", function () {
          QG.views.quantum.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load quantum status.");
      }
    },
  };
})();
