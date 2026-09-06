/* Q-Guardian Console — Login view.
 * Accepts username/password (registered account or provisioned via
 * AUTH_USERS) or a directly pasted JWT access token / API key; also
 * lets a first-time operator register a persistent account. Never logs
 * or renders credential values. On success the operator is returned to
 * the intended destination (the `next` query param) or the dashboard.
 * The API base URL can be overridden for a cloud deployment with
 * ?__api=http://host:port.
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
        '<p class="page-sub">Use a registered account, provisioned credentials, or paste an API key / JWT access token.</p>' +
        "</div>" +
        "</div>" +

        '<div class="card" style="max-width:420px;">' +
        '<div class="tabs" role="tablist">' +
        '<button class="tab active" id="tabLogin" type="button" role="tab">Sign in</button>' +
        '<button class="tab" id="tabRegister" type="button" role="tab">Create account</button>' +
        "</div>" +

        '<div id="formLogin">' +
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

        '<div id="formRegister" hidden>' +
        '<form id="registerForm">' +
        '<div class="field">' +
        '<label for="regUser">Username</label>' +
        '<input id="regUser" type="text" autocomplete="username" minlength="3" maxlength="64" required />' +
        '<div class="field-hint">Letters, digits, _ . - (3-64 characters)</div>' +
        "</div>" +
        '<div class="field">' +
        '<label for="regPass">Password</label>' +
        '<input id="regPass" type="password" autocomplete="new-password" minlength="8" required />' +
        '<div class="field-hint">At least 8 characters</div>' +
        "</div>" +
        '<div class="field">' +
        '<label for="regPassConfirm">Confirm password</label>' +
        '<input id="regPassConfirm" type="password" autocomplete="new-password" minlength="8" required />' +
        '<div class="field-hint">Re-enter the password to catch typos</div>' +
        "</div>" +
        '<div class="row end"><button type="submit" class="btn primary" id="registerBtn">Create account & sign in</button></div>' +
        "</form>" +
        '<div id="registerError"></div>' +
        "</div>" +
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

      var registerForm = el.querySelector("#registerForm");
      var regUser = el.querySelector("#regUser");
      var regPass = el.querySelector("#regPass");
      var regPassConfirm = el.querySelector("#regPassConfirm");
      var registerBtn = el.querySelector("#registerBtn");
      var registerError = el.querySelector("#registerError");

      var credPaste = el.querySelector("#credPaste");
      var credBtn = el.querySelector("#credBtn");
      var credError = el.querySelector("#credError");

      var tabLogin = el.querySelector("#tabLogin");
      var tabRegister = el.querySelector("#tabRegister");
      var formLogin = el.querySelector("#formLogin");
      var formRegister = el.querySelector("#formRegister");

      function showTab(which) {
        var loginActive = which === "login";
        tabLogin.classList.toggle("active", loginActive);
        tabRegister.classList.toggle("active", !loginActive);
        formLogin.hidden = !loginActive;
        formRegister.hidden = loginActive;
      }
      tabLogin.addEventListener("click", function () { showTab("login"); });
      tabRegister.addEventListener("click", function () { showTab("register"); });

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

      registerForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        registerError.innerHTML = "";
        if (regPass.value !== regPassConfirm.value) {
          registerError.innerHTML = U.errorState("Passwords do not match.");
          return;
        }
        registerBtn.disabled = true;
        try {
          var payload = await api.post(api.endpoints.register, {
            username: regUser.value.trim(),
            password: regPass.value,
          });
          var rdata = api.data(payload);
          /* Registration succeeded — now log straight in so the operator
           * lands on the dashboard authenticated. */
          var loginPayload = await api.post(api.endpoints.login, {
            username: regUser.value.trim(),
            password: regPass.value,
          });
          var loginData = api.data(loginPayload);
          QG.auth.setSession({
            tokens: loginData.tokens,
            username: loginData.username || rdata.username,
          });
          window.location.replace(next);
        } catch (err) {
          registerError.innerHTML = U.errorState(err.message || "Account creation failed.");
        } finally {
          registerBtn.disabled = false;
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