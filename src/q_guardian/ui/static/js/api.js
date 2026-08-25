/* Q-Guardian Console — API client.
 * Centralized fetch wrapper with JWT authentication, 401/403/429 handling,
 * token refresh, and rate-limit awareness. All responses use the standard
 * ResponseSchema envelope ({success, message, data, ...}) or the
 * paginated envelope ({data: [...], total, page, page_size, total_pages}).
 */
(function () {
  "use strict";

  var QG = (window.QG = window.QG || {});

  /* ---- Token management ----------------------------------------------- */

  var AUTH_KEY = "qg_auth";

  function getStoredAuth() {
    try {
      var raw = localStorage.getItem(AUTH_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function storeAuth(data) {
    try {
      localStorage.setItem(AUTH_KEY, JSON.stringify(data));
    } catch (e) {
      /* storage full or private mode — ignore */
    }
  }

  function clearAuth() {
    try {
      localStorage.removeItem(AUTH_KEY);
    } catch (e) {
      /* ignore */
    }
  }

  function getAccessToken() {
    var auth = getStoredAuth();
    return auth ? auth.access : null;
  }

  function getRefreshToken() {
    var auth = getStoredAuth();
    return auth ? auth.refresh : null;
  }

  function getCurrentUser() {
    var auth = getStoredAuth();
    return auth
      ? { username: auth.username, roles: auth.roles || [] }
      : null;
  }

  function isLoggedIn() {
    return !!getAccessToken();
  }

  /* ---- Helpers -------------------------------------------------------- */

  function isPlainObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  /* ---- Token refresh -------------------------------------------------- */

  var refreshPromise = null;

  function tryRefresh() {
    var refresh = getRefreshToken();
    if (!refresh) return Promise.resolve(false);

    /* Deduplicate concurrent refresh attempts */
    if (refreshPromise) return refreshPromise;

    refreshPromise = fetch(requestUrl("/api/v1/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refresh }),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("refresh failed");
        return resp.json();
      })
      .then(function (data) {
        storeAuth({
          access: data.access,
          refresh: data.refresh,
          username: data.username,
          roles: data.roles,
        });
        return true;
      })
      .catch(function () {
        clearAuth();
        return false;
      })
      .finally(function () {
        refreshPromise = null;
      });

    return refreshPromise;
  }

  /* ---- URL helper ----------------------------------------------------- */

  function requestUrl(path) {
    return path;
  }

  /* ---- Core request --------------------------------------------------- */

  async function request(path, options) {
    var opts = Object.assign({ headers: {} }, options || {});

    /* Attach Authorization header if we have a token */
    var token = getAccessToken();
    if (token && !opts.headers["Authorization"]) {
      opts.headers["Authorization"] = "Bearer " + token;
    }

    if (opts.body) {
      opts.headers["Content-Type"] = "application/json";
    }

    var response;
    try {
      response = await fetch(requestUrl(path), opts);
    } catch (networkError) {
      var err = new Error(
        "Cannot reach the Q-Guardian API at " +
          path +
          ". Is the server running?"
      );
      err.cause = networkError;
      throw err;
    }

    /* ---- 401 handling: try refresh once, then emit auth error --------- */
    if (response.status === 401) {
      var refreshed = await tryRefresh();
      if (refreshed) {
        /* Retry the original request with the new token */
        token = getAccessToken();
        if (token) {
          opts.headers["Authorization"] = "Bearer " + token;
        }
        try {
          response = await fetch(requestUrl(path), opts);
        } catch (networkError) {
          throw new Error("Cannot reach the Q-Guardian API after token refresh.");
        }
      }
      if (response.status === 401) {
        clearAuth();
        var authErr = new Error("Session expired. Please log in again.");
        authErr.status = 401;
        authErr.authError = true;
        QG.bus && QG.bus.emit("auth:expired");
        throw authErr;
      }
    }

    /* ---- 403 handling ------------------------------------------------- */
    if (response.status === 403) {
      var forbiddenErr = new Error("Access denied. You do not have permission for this action.");
      forbiddenErr.status = 403;
      var body403 = null;
      try { body403 = await response.json(); } catch (e) { /* ignore */ }
      if (body403 && body403.detail) forbiddenErr.message = body403.detail;
      throw forbiddenErr;
    }

    /* ---- 429 rate-limit handling --------------------------------------- */
    if (response.status === 429) {
      var retryAfter = response.headers.get("Retry-After");
      var seconds = retryAfter ? parseInt(retryAfter, 10) : null;
      var rateMsg = "Request limit reached. Please wait";
      if (seconds && seconds > 0) {
        rateMsg += " " + seconds + " seconds";
      }
      rateMsg += " before trying again.";
      var rateErr = new Error(rateMsg);
      rateErr.status = 429;
      rateErr.retryAfter = seconds;
      /* Emit event so the UI can show a global notification */
      QG.bus && QG.bus.emit("rate:limited", { retryAfter: seconds, message: rateMsg });
      throw rateErr;
    }

    /* ---- Parse response ----------------------------------------------- */
    var payload = null;
    try {
      payload = await response.json();
    } catch (parseError) {
      /* non-JSON body */
    }

    if (!response.ok || (isPlainObject(payload) && payload.success === false)) {
      var detail =
        (payload && (payload.detail || payload.message || payload.error)) ||
        "Request failed (HTTP " + response.status + ")";
      var message =
        typeof detail === "string" ? detail : JSON.stringify(detail);
      var failure = new Error(message);
      failure.status = response.status;
      throw failure;
    }

    return payload;
  }

  /* ---- Public API ----------------------------------------------------- */

  QG.api = {
    request: request,

    get: function (path) {
      return request(path, { method: "GET" });
    },

    post: function (path, body) {
      return request(path, { method: "POST", body: JSON.stringify(body) });
    },

    /* Unwrap the `data` field of a standard envelope. */
    data: function (payload) {
      return payload ? payload.data : null;
    },

    /* Normalize a paginated envelope (or a plain array) into a consistent
     * shape: { items, total, page, page_size, total_pages }. */
    envelope: function (payload) {
      if (isPlainObject(payload) && Array.isArray(payload.data)) {
        var data = payload.data;
        return {
          items: data,
          total:
            typeof payload.total === "number" ? payload.total : data.length,
          page: typeof payload.page === "number" ? payload.page : 1,
          page_size:
            typeof payload.page_size === "number" ? payload.page_size : data.length,
          total_pages:
            typeof payload.total_pages === "number"
              ? payload.total_pages
              : Math.max(1, data.length ? Math.ceil(data.length / (payload.page_size || data.length)) : 1),
        };
      }
      var items = Array.isArray(payload) ? payload : [];
      return {
        items: items,
        total: items.length,
        page: 1,
        page_size: items.length,
        total_pages: 1,
      };
    },

    /* ---- Auth helpers ------------------------------------------------- */
    login: function (username, password) {
      return request("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: username, password: password }),
      }).then(function (data) {
        storeAuth({
          access: data.access,
          refresh: data.refresh,
          username: data.username,
          roles: data.roles,
        });
        QG.bus && QG.bus.emit("auth:login", { username: data.username, roles: data.roles });
        return data;
      });
    },

    logout: function () {
      clearAuth();
      QG.bus && QG.bus.emit("auth:logout");
    },

    getStoredAuth: getStoredAuth,
    getCurrentUser: getCurrentUser,
    isLoggedIn: isLoggedIn,

    endpoints: {
      health: "/api/v1/health",
      version: "/api/v1/system/version",
      status: "/api/v1/system/status",
      summary: "/api/v1/console/summary",
      rules: "/api/v1/console/rules",
      models: "/api/v1/console/models",
      components: "/api/v1/console/components",
      configuration: "/api/v1/console/configuration",
      research: "/api/v1/console/research",
      analysis: "/api/v1/analysis",
      scan: "/api/v1/analysis/scan",
      auth: "/api/v1/auth",
    },
  };
})();
