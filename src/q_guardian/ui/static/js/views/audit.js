/* Q-Guardian Console — Audit view.
 * Aggregated security posture: pipeline health, configuration hardening,
 * and the recent scan activity trail. All data comes from the live API;
 * the console keeps no audit store of its own.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  QG.views.audit = {
    title: "Audit",
    group: "system",
    render: async function (el) {
      el.innerHTML = U.loadingState("Compiling audit view…");
      try {
        var [summaryPayload, configPayload, historyPayload] = await Promise.all([
          api.get(api.endpoints.summary),
          api.get(api.endpoints.configuration),
          api.get(api.endpoints.analysis + "?limit=50"),
        ]);
        var summary = api.data(summaryPayload);
        var config = api.data(configPayload);
        var history = api.envelope(historyPayload);

        var security = config.security || {};
        var app = config.application || {};
        var db = config.database || {};
        var ml = config.ml || {};

        var posture = [
          {
            label: "Secret Key Configured",
            html: U.statusBadge(security.secret_key_configured ? "enabled" : "disabled"),
          },
          { label: "JWT Algorithm", value: security.jwt_algorithm || "—", mono: true },
          { label: "JWT Expiry", value: security.jwt_expiration_minutes != null ? security.jwt_expiration_minutes + " min" : "—" },
          {
            label: "Database Configured",
            html: U.statusBadge(db.configured ? "enabled" : "disabled"),
          },
          { label: "Database URL", value: db.url_redacted || "—", mono: true },
          {
            label: "Classical ML Enabled",
            html: U.statusBadge(ml.enabled ? "enabled" : "disabled"),
          },
          {
            label: "XGBoost Available",
            html: U.statusBadge(ml.xgboost_available ? "enabled" : "disabled"),
          },
          { label: "Environment", value: app.environment || "—" },
          { label: "Version", value: app.version || "—", mono: true },
        ];

        var historyCounts = summary.history || {};

        var activity = (history.items || []).map(function (item) {
          return {
            time: U.fmtDateTime(item.timestamp),
            html:
              '<a class="row-link" href="#/detection/' + encodeURIComponent(item.analysis_id) + '">' +
              U.text(item.analysis_id.slice(0, 8)) +
              "</a> " +
              U.decisionBadge(item.decision) +
              " · risk " + Math.round(Number(item.risk_score || 0) * 100) + "%" +
              " · " + item.finding_count + " finding" + (item.finding_count === 1 ? "" : "s"),
          };
        });

        var components = (summary.components || []).map(function (component) {
          return [
            { value: component.name, cls: "cell-strong" },
            U.statusBadge(component.status),
            component.detail,
          ];
        });

        var activityHtml =
          '<div class="timeline">' +
          (activity.length
            ? activity.map(function (entry) {
                return (
                  '<div class="timeline-item"><span class="tl-time">' + entry.time + "</span><span>" + entry.html + "</span></div>"
                );
              }).join("")
            : '<div class="timeline-item"><span class="tl-time"></span><span class="muted">No scan activity recorded in this session.</span></div>') +
          "</div>";

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Audit</h2>' +
          '<p class="page-sub">Security posture and recent activity. The console surfaces live pipeline state — it maintains no separate audit log.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshAudit">Refresh</button>' +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Security Posture</div></div>' +
          U.keyValue(posture) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Decision Distribution</div>' +
          '<div class="card-sub">' + U.fmtNum(historyCounts.total || 0) + " scans this session</div></div>" +
          '<div class="distribution">' +
          [
            { label: "Blocked", count: historyCounts.blocked || 0, cls: "block" },
            { label: "Review", count: historyCounts.review || 0, cls: "review" },
            { label: "Warning", count: historyCounts.warn || 0, cls: "warning" },
            { label: "Allowed", count: historyCounts.allowed || 0, cls: "success" },
          ]
            .map(function (row) {
              var pct = historyCounts.total ? Math.round((row.count / historyCounts.total) * 100) : 0;
              return (
                '<div class="dist-row"><span class="dist-label">' + row.label + "</span>" +
                '<div class="dist-track"><div class="dist-fill ' + row.cls + '" style="width:' + pct + '%"></div></div>' +
                '<span class="dist-value">' + row.count + "</span></div>"
              );
            })
            .join("") +
          "</div>" +
          "</div>" +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Pipeline Health</div></div>' +
          U.table(["Stage", "Status", "Details"], components) +
          "</div>" +

          '<div class="card"><div class="card-head"><div class="card-title">Recent Activity</div></div>' +
          activityHtml +
          "</div>";

        el.querySelector("#refreshAudit").addEventListener("click", function () {
          QG.views.audit.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not compile the audit view.");
      }
    },
  };
})();
