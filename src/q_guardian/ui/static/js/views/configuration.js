/* Q-Guardian Console — Configuration view.
 * Sanitized application configuration from /console/configuration.
 * Secrets and internal filesystem paths are redacted server-side.
 * Shows authentication and security settings.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  var SECTION_TITLES = {
    application: "Application",
    database: "Database",
    security: "Authentication & Security",
    prompt_security: "Prompt Security",
    ml: "Machine Learning",
  };

  function sectionCard(name, section) {
    var items = Object.keys(section).map(function (key) {
      var value = section[key];
      var html;
      if (typeof value === "boolean") {
        html = U.statusBadge(value ? "enabled" : "disabled");
      } else if (typeof value === "object" && value !== null) {
        html = U.text(JSON.stringify(value));
      } else {
        html = U.text(value == null ? "—" : value);
      }
      return {
        label: key.replace(/_/g, " "),
        html: html,
        mono: typeof value === "string" || typeof value === "number",
      };
    });
    if (!items.length) return "";
    return (
      '<div class="card"><div class="card-head"><div class="card-title">' +
      U.text(SECTION_TITLES[name] || name.replace(/_/g, " ")) +
      "</div></div>" +
      U.keyValue(items) +
      "</div>"
    );
  }

  QG.views.configuration = {
    title: "Configuration",
    group: "system",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading configuration…");
      try {
        var payload = await api.get(api.endpoints.configuration);
        var config = api.data(payload) || {};

        var sections = Object.keys(config)
          .map(function (name) {
            return sectionCard(name, config[name]);
          })
          .join("");

        /* Show auth info from the client side */
        var authInfo = "";
        var storedAuth = api.getStoredAuth();
        if (storedAuth) {
          authInfo =
            '<div class="card"><div class="card-head"><div class="card-title">Client Authentication</div></div>' +
            U.keyValue([
              { label: "Authenticated", html: U.statusBadge("enabled") },
              { label: "Username", value: storedAuth.username || "—" },
              { label: "Roles", value: (storedAuth.roles || []).join(", ") || "—" },
              { label: "Token", value: storedAuth.access ? storedAuth.access.substring(0, 20) + "…" : "—" },
            ]) +
            "</div>";
        }

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Configuration</h2>' +
          '<p class="page-sub">A read-only, sanitized view of the running application. Secret values (secret keys, tokens, passwords) and internal filesystem paths are never exposed.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshConfig">Refresh</button>' +
          "</div>" +
          U.note("Redacted: secret keys, tokens, passwords, credentialed URLs and *_path / *_dir values.") +
          authInfo +
          sections;

        el.querySelector("#refreshConfig").addEventListener("click", function () {
          QG.views.configuration.render(el);
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load configuration.");
      }
    },
  };
})();
