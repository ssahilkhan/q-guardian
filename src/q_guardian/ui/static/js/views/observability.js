/* Q-Guardian Console — Observability view.
 * Consumes GET /api/v1/console/observability which exposes the live
 * in-process metrics registry fed by the response-timing middleware.
 * Shows request counts/latency per route, error rates, scan decisions,
 * and uptime. All data is real; no fabricated percentiles. The view
 * clearly labels state as LIVE / STALE / UNAVAILABLE based on fetch
 * success and timestamp freshness.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  var REFRESH_MS = 15000;
  var STALE_AFTER_MS = 30000;

  function formatMs(value) {
    if (value == null || isNaN(value)) return "—";
    var v = Number(value);
    if (v >= 1000) return (v / 1000).toFixed(2) + " s";
    return v.toFixed(2) + " ms";
  }

  function routeTable(routes) {
    if (!routes || !routes.length) return U.emptyState("No request data recorded yet.");
    var rows = routes.map(function (r) {
      var errorRate = r.count ? (r.count - (r.status_code < 400 ? r.count : 0)) / r.count : 0;
      return [
        { value: U.badge(r.method, r.method === "GET" ? "info" : "accent") },
        { value: r.route, cls: "cell-mono cell-strong" },
        { value: r.status_code, cls: "cell-mono", title: "HTTP status" },
        { value: U.fmtNum(r.count), cls: "cell-mono" },
        { value: formatMs(r.avg_ms), cls: "cell-mono", title: "Average handling time" },
        { value: formatMs(r.max_ms), cls: "cell-mono", title: "Maximum handling time" },
      ];
    });
    return U.table(["Method", "Route", "Status", "Count", "Avg Latency", "Max Latency"], rows);
  }

  function decisionBars(decisions) {
    if (!decisions || !Object.keys(decisions).length) {
      return U.emptyState("No scan decisions recorded yet.");
    }
    var total = Object.values(decisions).reduce(function (sum, v) { return sum + (Number(v) || 0); }, 0);
    if (!total) return U.emptyState("No scan decisions recorded yet.");
    var order = ["allow", "warn", "review", "block"];
    var bars = order
      .filter(function (k) { return decisions[k]; })
      .map(function (k) {
        var count = Number(decisions[k]) || 0;
        var pct = Math.round((count / total) * 100);
        var cls = k === "block" ? "block" : k === "review" ? "review" : k === "warn" ? "warn" : "success";
        return (
          '<div class="dist-row">' +
          '<span class="dist-label">' + U.text(k.charAt(0).toUpperCase() + k.slice(1)) + "</span>" +
          '<div class="dist-track"><div class="dist-fill ' + cls + '" style="width:' + pct + '%"></div></div>' +
          '<span class="dist-value">' + U.fmtNum(count) + "</span>" +
          "</div>"
        );
      });
    return '<div class="distribution">' + bars.join("") + "</div>";
  }

  function statusBadge(label, tone) {
    return '<span class="badge badge-' + tone + '">' + U.text(label) + "</span>";
  }

  function renderState(state) {
    var now = Date.now();
    var age = state.fetched_at ? now - state.fetched_at : null;
    var fresh = age != null && age < STALE_AFTER_MS;
    var badge = fresh
      ? statusBadge("LIVE", "success")
      : state.error
        ? statusBadge("UNAVAILABLE", "block")
        : statusBadge("STALE", "warn");
    return badge + " (last updated " + (age != null ? Math.round(age / 1000) + " s ago" : "never") + ")";
  }

  QG.views.observability = {
    title: "Observability",
    group: "system",
    render: async function (el) {
      var fetchError = null;
      var fetchedAt = null;
      var data = null;

      function doFetch() {
        return api
          .get(api.endpoints.observability)
          .then(function (payload) {
            data = api.data(payload) || {};
            fetchedAt = Date.now();
            fetchError = null;
            return data;
          })
          .catch(function (err) {
            fetchError = err;
            throw err;
          });
      }

      function paint() {
        if (!data && fetchError) {
          el.innerHTML = U.errorState(fetchError.message || "Could not load observability data.");
          return;
        }
        var state = { fetched_at: fetchedAt, error: fetchError };
        var meta = data || {};
        var generated = meta.generated_at ? U.fmtDateTime(meta.generated_at) : "—";
        var uptime = meta.uptime_seconds != null ? Math.round(meta.uptime_seconds) + " s" : "—";
        var totalReq = meta.total_requests != null ? U.fmtNum(meta.total_requests) : "—";
        var errCount = meta.error_count != null ? U.fmtNum(meta.error_count) : "—";
        var errRate = meta.error_rate != null ? (meta.error_rate * 100).toFixed(2) + "%" : "—";

        var routeHtml = routeTable(meta.routes);
        var decisionHtml = decisionBars(meta.scan_decisions);

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Observability</h2>' +
          '<p class="page-sub">Live operational metrics from the in-process registry (fed by the response-timing middleware). No percentiles are computed; average and maximum latencies are shown per route template. Counters reset on server restart.</p>' +
          "</div>" +
          '<div class="row end">' +
          renderState(state) +
          '<button type="button" class="btn ghost" id="refreshObs">Refresh</button>' +
          "</div>" +
          "</div>" +

          '<div class="grid grid-4">' +
          U.statCard("State", "", renderState(state), "") +
          U.statCard("Uptime", uptime, "", "") +
          U.statCard("Total Requests", totalReq, "", "") +
          U.statCard("Error Rate", errRate, errCount + " errors", "") +
          "</div>" +

          (meta.note ? U.note(meta.note) : "") +

          '<div class="card"><div class="card-head"><div class="card-title">Per-Route Requests & Latency</div></div>' +
          routeHtml +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Scan Decisions</div></div>' +
          decisionHtml +
          "</div>";
      }

      el.innerHTML = U.loadingState("Loading observability metrics…");
      try {
        await doFetch();
        paint();
      } catch (e) {
        paint(); // shows error
      }

      var interval = setInterval(function () {
        doFetch().then(paint).catch(paint);
      }, REFRESH_MS);

      // Cleanup on unload/re-render
      if (!el._obsCleanup) {
        el._obsCleanup = function () { clearInterval(interval); };
      }
      var oldCleanup = el._obsCleanup;
      el._obsCleanup = function () {
        clearInterval(interval);
        oldCleanup && oldCleanup();
      };

      var refreshBtn = el.querySelector("#refreshObs");
      if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
          doFetch().then(paint).catch(paint);
        });
      }
    },
  };
})();