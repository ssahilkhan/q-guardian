/* Q-Guardian Console — Rules view.
 * The active rule catalog from /console/rules. Read-only: rules are
 * managed through the framework, not through this console.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  function patternCount(rule) {
    var patterns = rule.patterns || [];
    var keywords = rule.keywords || [];
    return patterns.length + " / " + keywords.length;
  }

  QG.views.rules = {
    title: "Rules",
    group: "analysis",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading detection rules…");
      try {
        var payload = await api.get(api.endpoints.rules);
        var rules = api.data(payload) || [];
        var rows = rules.map(function (rule) {
          return [
            { value: rule.name, cls: "cell-strong" },
            U.text(U.categoryLabel(rule.category)),
            U.severityBadge(rule.severity),
            { value: Math.round(Number(rule.confidence || 0) * 100) + "%", cls: "cell-mono" },
            U.statusBadge(rule.enabled ? "enabled" : "disabled"),
            patternCount(rule),
            rule.description,
          ];
        });

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Detection Rules</h2>' +
          '<p class="page-sub">' + rules.length + " rules registered in the rule engine. The catalog is read-only from the console — rule configuration belongs to the framework.</p>" +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshRules">Refresh</button>' +
          "</div>" +
          U.table(
            ["Name", "Category", "Severity", "Confidence", "State", "Patterns / Keywords", "Description"],
            rows
          );

        el.querySelector("#refreshRules").addEventListener("click", function () {
          QG.views.rules.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load detection rules.");
      }
    },
  };
})();
