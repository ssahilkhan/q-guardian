/* Q-Guardian Console — client-side auth session.
 * Holds the JWT access/refresh tokens (or a pasted API key) in
 * sessionStorage for the lifetime of the tab, attaches them to API
 * requests and reacts to 401 responses. Tokens are never logged and
 * never rendered; logout clears the session entirely.
 */
(function () {
  "use strict";

  var QG = (window.QG = window.QG || {});

  var KEY_ACCESS = "qg.access";
  var KEY_REFRESH = "qg.refresh";
  var KEY_KIND = "qg.kind"; // "bearer" | "api_key"
  var KEY_USER = "qg.user"; // display name only

  function storage() {
    try {
      return window.sessionStorage;
    } catch (e) {
      return null;
    }
  }

  function get(name) {
    var s = storage();
    return s ? s.getItem(name) : null;
  }

  function set(name, value) {
    var s = storage();
    if (s) value == null ? s.removeItem(name) : s.setItem(name, value);
  }

  QG.auth = {
    /* True when any usable credential is present. */
    isAuthed: function () {
      return Boolean(get(KEY_ACCESS));
    },

    kind: function () {
      return get(KEY_KIND) || "bearer";
    },

    user: function () {
      return get(KEY_USER) || "";
    },

    /* Persist a login result: {tokens:{access,refresh}, username} or a
     * single pasted credential with an explicit kind. */
    setSession: function (session) {
      if (session.tokens && session.tokens.access) {
        set(KEY_ACCESS, session.tokens.access);
        set(KEY_REFRESH, session.tokens.refresh || "");
        set(KEY_KIND, "bearer");
      } else if (session.credential) {
        set(KEY_ACCESS, session.credential);
        set(KEY_REFRESH, "");
        set(KEY_KIND, session.kind === "api_key" ? "api_key" : "bearer");
      }
      set(KEY_USER, session.username || "");
    },

    clear: function () {
      set(KEY_ACCESS, null);
      set(KEY_REFRESH, null);
      set(KEY_KIND, null);
      set(KEY_USER, null);
    },

    refresh: function () {
      return get(KEY_REFRESH) || "";
    },

    /* Headers to attach to every API request. The API key header name
     * matches the server default (X-API-Key); JWTs go in Authorization. */
    headers: function () {
      var token = get(KEY_ACCESS);
      if (!token) return {};
      if (get(KEY_KIND) === "api_key") {
        return { "X-API-Key": token };
      }
      return { Authorization: "Bearer " + token };
    },

    /* Exchange the stored refresh token for a new access token. */
    rotate: async function () {
      var refreshToken = get(KEY_REFRESH);
      if (!refreshToken) return false;
      try {
        var payload = await QG.api.post(QG.api.endpoints.refresh, {
          refresh_token: refreshToken,
        });
        var data = QG.api.data(payload);
        if (!data || !data.tokens || !data.tokens.access) return false;
        set(KEY_ACCESS, data.tokens.access);
        if (data.username) set(KEY_USER, data.username);
        return true;
      } catch (err) {
        return false;
      }
    },

    /* Called by the API client on 401. Tries one silent refresh; if that
     * fails, drops the session and routes to the login view. Returns true
     * when the caller may retry the original request once. */
    handleUnauthorized: async function () {
      var rotated = await this.rotate();
      if (rotated) return true;
      this.clear();
      if (window.QG.console && window.QG.console.requireLogin) {
        window.QG.console.requireLogin();
      }
      return false;
    },

    logout: function () {
      this.clear();
      if (window.QG.console && window.QG.console.onLogout) {
        window.QG.console.onLogout();
      }
    },
  };
})();
