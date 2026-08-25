/* Q-Guardian Console — Login view.
 * Accepts username/password (provisioned via AUTH_USERS) or a
 * directly pasted JWT access token / API key. Never logs or renders
 * credential values. On success the operator is returned to the
 * intended destination (the `next` query param) or the dashboard.
 */
(function () {
  "use strict";

  var QG = (window.QG = window.QG || {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  QG.views.login = {
    title: "Login",
    group: "overview",
    render: function (el, params) {
      var next = params && params.next ? decodeURIComponent(params.next) : "#/dashboard";

      el.innerHTML =
        '<div class="page-head">' +
        "<div>" +
        '<h2 class="page-title">Sign in to Q-Guardian</h2>' +
        '<p class="page-sub">Use provisioned credentials or paste an API key / JWT access token.</p>' +
        "</div>" +
        "</div>" +

        '<div class="card" style="max-width:420px;">' +
        '<div class="card-head"><div class="card-title">Username / Password</div></div>' +
        '<form id="loginForm">' +
        '<div class="field">' +
        '<label for="loginUser">Username</label>' +
        '<input id="loginUser" type="text" autocomplete="username" required />' +
        "</div>" +
        '<div class="field">' +
        '<label for="loginPass">Password</label>' +
        '<input id="loginPass" type="password" autocomplete="current-password" required />' +
        "</div>" +
        '<div class="row end"><button type="submit" class="btn primary" id="loginBtn">Sign in</button></div>' +
        "</form>" +
        '<div id="loginError"></div>' +
        "</div>" +

        '<div class="card" style="max-width:420px; margin-top:16px;">' +
        '<div class="card-head"><div class="card-title">Paste Credential</div>' +
        '<div class="card-sub">JWT access token (Bearer) or API key</div></div>' +
        '<div class="field">' +
        '<label for="credPaste">Paste token</label>' +
        '<textarea id="credPaste" rows="3" placeholder="eyJhbGciOi... or qg_live_..."></textarea>' +
        "</div>" +
        '<div class="row end"><button type="button" class="btn secondary" id="credBtn">Verify & Sign in</button></div>' +
        '<div id="credError"></div>' +
        "</div>";

      var loginForm = el.querySelector("#loginForm");
      var loginUser = el.querySelector("#loginUser");
      var loginPass = el.querySelector("#loginPass");
      var loginBtn = el.querySelector("#loginBtn");
      var loginError = el.querySelector("#loginError");

      var credPaste = el.querySelector("#credPaste");
      var credBtn = el.querySelector("#credBtn");
      var credError = el.querySelector("#credError");

      loginForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        loginError.innerHTML = "";
        loginBtn.disabled = true;
        try {
          var payload = await api.post(api.endpoints.login, {
            username: loginUser.value.trim(),
            password: loginPass.value,
          });
          var data = api.data(payload);
          QG.auth.setSession({ tokens: data.tokens, username: data.username });
          window.location.replace(next);
        } catch (err) {
          loginError.innerHTML = U.errorState(err.message || "Sign in failed.");
        } finally {
          loginBtn.disabled = false;
        }
      });

      credBtn.addEventListener("click", async function () {
        var raw = credPaste.value.trim();
        credError.innerHTML = "";
        if (!raw) {
          credError.innerHTML = U.errorState("Paste a token first.");
          return;
        }
        credBtn.disabled = true;
        /* Probe the credential against /system/version to determine
         * whether it works as a Bearer token or an API key. We try
         * Bearer first because it's the default. */
        var kind = "bearer";
        try {
          await QG.api.request(api.endpoints.version, {
            method: "GET",
            headers: { Authorization: "Bearer " + raw },
          });
        } catch (e) {
          if (e.status === 401) {
            kind = "api_key";
            try {
              await QG.api.request(api.endpoints.version, {
                method: "GET",
                headers: { "X-API-Key": raw },
              });
            } catch (e2) {
              credError.innerHTML = U.errorState(e2.message || "Invalid credential.");
              credBtn.disabled = false;
              return;
            }
          } else {
            credError.innerHTML = U.errorState(e.message || "Verification failed.");
            credBtn.disabled = false;
            return;
          }
        }
        QG.auth.setSession({ credential: raw, kind: kind, username: "" });
        window.location.replace(next);
      });
    },
  };
})();