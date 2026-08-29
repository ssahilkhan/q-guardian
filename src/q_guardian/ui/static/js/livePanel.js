/* Q-Guardian Console — Live Scan Dashboard panel helper.
 * Renders the real-time progress of a single scan subscription into a
 * provided container, using QG.live (the WebSocket client) and QG.ui.
 *
 * The backend scan is synchronous, so the panel connects after the scan is
 * submitted, requests the retained __replay__ snapshot and shows the
 * genuine lifecycle: scan.started (running) then scan.completed with the
 * real stage statuses and result payload, or scan.failed on error. No fake
 * progress is produced by the client — everything shown is a real backend
 * event. Stage statuses (and the notification) are grounded in the actual
 * backend execution.
 *
 * attach(container, options) fills the container with the panel markup and
 * returns a dispose() function that unsubscribes listeners and closes the
 * socket, so views can tear it down when they re-render.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  var live = QG.live;
  var U = QG.ui;

  var STAGE_LABELS = {
    normalize: "Normalization",
    validate: "Validation",
    features: "Feature Extraction",
    rules: "Rule Engine",
    ml: "Classical ML",
    quantum: "Quantum",
    decision: "Decision Engine",
    response: "Response",
  };

  function stageBadge(status) {
    if (status === "completed" || status === "active") {
      return U.badge("Completed", "success");
    }
    if (status === "running") {
      return U.badge("Running", "accent");
    }
    if (status === "inactive") {
      return U.badge("Skipped", "neutral");
    }
    return U.statusBadge(status);
  }

  function renderStages(stages) {
    return (
      '<div class="live-stages">' +
      stages
        .map(function (stage) {
          return (
            '<div class="live-stage">' +
            '<div class="live-stage-label">' +
            (STAGE_LABELS[stage.id] || stage.id) +
            "</div>" +
            '<div class="live-stage-status">' +
            stageBadge(stage.status) +
            "</div>" +
            "</div>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function renderRunning() {
    return (
      '<div class="live-running">' +
      '<div class="spinner" aria-hidden="true"></div>' +
      "<span>Scan pipeline running…</span>" +
      "</div>"
    );
  }

  function stateLabel(connectionState) {
    var map = {
      CONNECTING: "Connecting…",
      CONNECTED: "Live",
      RECONNECTING: "Reconnecting…",
      DISCONNECTED: "Disconnected",
    };
    return map[connectionState] || "Disconnected";
  }

  function attach(container, scanId, options) {
    options = options || {};
    var onResult = options.onResult || function () {};
    var onDone = options.onDone || function () {};

    container.innerHTML =
      '<div class="card live-panel">' +
      '<div class="card-head">' +
      "<div>" +
      '<div class="card-title">Live Scan</div>' +
      '<div class="card-sub">Real-time progress streamed from the scan pipeline.</div>' +
      "</div>" +
      '<div class="live-sub">' +
      '<span class="live-badge off" aria-hidden="true">&#9679;</span>' +
      '<span class="live-sub-state">' + stateLabel(live.state()) + "</span>" +
      "</div>" +
      "</div>" +
      '<div class="live-watch">' +
      '<div data-live-stages></div>' +
      '<div data-live-error></div>' +
      '<div data-live-result></div>' +
      "</div>" +
      "</div>";

    var stateEl = container.querySelector(".live-sub-state");
    var badgeEl = container.querySelector(".live-badge");
    var stagesHost = container.querySelector('[data-live-stages]');
    var errorHost = container.querySelector('[data-live-error]');
    var resultHost = container.querySelector('[data-live-result]');

    function markBadge(connectionState) {
      badgeEl.className =
        "live-badge " +
        (connectionState === "CONNECTED"
          ? "on"
          : connectionState === "CONNECTING"
            ? "connecting"
            : "off");
    }

    function onState(connectionState) {
      stateEl.textContent = stateLabel(connectionState);
      markBadge(connectionState);
    }

    function onEvent(event) {
      if (!event || !event.type) return;
      if (event.type === "scan.started") {
        stagesHost.innerHTML = renderRunning();
        return;
      }
      if (event.type === "scan.completed") {
        errorHost.innerHTML = "";
        stagesHost.innerHTML = renderStages(event.stages);
        resultHost.innerHTML = "";
        if (event.result) {
          onResult(resultHost, event.result);
        } else {
          resultHost.innerHTML = U.note("Scan completed, but no result payload was returned.");
        }
        onDone(true);
        return;
      }
      if (event.type === "scan.failed") {
        stagesHost.innerHTML = "";
        errorHost.innerHTML = U.errorState(
          (event.message || "The scan pipeline failed.") +
            (event.error ? " (" + event.error + ")" : "")
        );
        onDone(false);
        return;
      }
    }

    live.onState(onState);
    live.onEvent(onEvent);
    markBadge(live.state());
    live.connect(scanId);

    return function dispose() {
      live.offState(onState);
      live.offEvent(onEvent);
      live.close();
    };
  }

  QG.livePanel = {
    attach: attach,
  };
})();
