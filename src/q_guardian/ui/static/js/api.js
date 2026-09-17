/* Q-Guardian Console — API client.
 * Thin fetch wrapper around the v1 REST API. All responses use the
 * standard ResponseSchema envelope ({success, message, data, ...}) or the
 * paginated envelope ({data: [...], total, page, page_size, total_pages}).
 */
(function () {
  "use strict";

  var QG = (window.QG = window.QG || {});

  function isPlainObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  function authHeaders() {
    return (QG.auth && typeof QG.auth.headers === "function") ? QG.auth.headers() : {};
  }

  /* Resolve the API base URL. Defaults to the same origin that serves the
   * console; override with ?__api= or the qg.apiBase query/hash for a
   * separate (e.g. cloud) deployment. Trailing slashes are trimmed. */
  function baseUrl() {
    var custom = QG.apiBase;
    if (!custom) {
      try {
        var q = parseHashQuery(window.location.hash);
        if (q.__api) custom = q.__api;
      } catch (e) { /* ignore */ }
      if (!custom) {
        var m = (window.location.search || "").match(/[?&]__api=([^&]+)/);
        if (m) custom = decodeURIComponent(m[1]);
      }
    }
    if (custom) {
      return String(custom).replace(/\/+$/, "");
    }
    return "";
  }

  function parseHashQuery(hash) {
    var out = {};
    var raw = (hash || "").replace(/^#/, "");
    var q = raw.split("?").slice(1).join("?");
    q.split("&").forEach(function (pair) {
      if (!pair) return;
      var eq = pair.indexOf("=");
      if (eq === -1) out[decodeURIComponent(pair)] = "";
      else out[decodeURIComponent(pair.slice(0, eq))] = decodeURIComponent(pair.slice(eq + 1));
    });
    return out;
  }

  function fullUrl(path) {
    var base = baseUrl();
    return base ? base + path : path;
  }

  async function request(path, options) {
    var opts = Object.assign({ headers: {} }, options || {});
    var auth = authHeaders();
    for (var key in auth) {
      if (Object.prototype.hasOwnProperty.call(auth, key)) {
        opts.headers[key] = auth[key];
      }
    }
    if (opts.body) {
      opts.headers["Content-Type"] = "application/json";
    }
    var url = fullUrl(path);
    var response;
    try {
      response = await fetch(url, opts);
    } catch (networkError) {
      var err = new Error(
        "Cannot reach the Q-Guardian API at " +
          url +
          ". Is the server running?"
      );
      err.cause = networkError;
      throw err;
    }

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
      /* The backend error envelope is {error: {code, message, details}};
       * surface the human-readable message instead of the whole object. */
      var message =
        typeof detail === "string"
          ? detail
          : detail && detail.message
            ? detail.message
            : JSON.stringify(detail);
      var failure = new Error(message);
      failure.status = response.status;
      if (failure.status === 401 && QG.auth && typeof QG.auth.handleUnauthorized === "function") {
        var retry = await QG.auth.handleUnauthorized();
        if (retry) {
          return request(path, options);
        }
      }
      throw failure;
    }

    return payload;
  }

  QG.api = {
    request: request,

    get: function (path) {
      return request(path, { method: "GET" });
    },

    post: function (path, body) {
      return request(path, { method: "POST", body: JSON.stringify(body) });
    },

    delete: function (path) {
      return request(path, { method: "DELETE" });
    },

    /* Fetch a raw (non-envelope) response body, e.g. generated report files.
     * Throws on HTTP errors with the backend error detail when available. */
    text: async function (path) {
      var opts = { method: "GET", headers: {} };
      var auth = authHeaders();
      for (var key in auth) {
        if (Object.prototype.hasOwnProperty.call(auth, key)) {
          opts.headers[key] = auth[key];
        }
      }
      var response = await fetch(fullUrl(path), opts);
      var body = await response.text();
      var payload = null;
      try {
        payload = JSON.parse(body);
      } catch (e) { /* non-JSON body */ }
      if (!response.ok) {
        var detail =
          (payload && (payload.detail || payload.message || payload.error)) ||
          "Request failed (HTTP " + response.status + ")";
        var message =
          typeof detail === "string"
            ? detail
            : detail && detail.message
              ? detail.message
              : JSON.stringify(detail);
        throw new Error(message);
      }
      return payload !== null ? payload : body;
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

    endpoints: {
      login: "/api/v1/auth/login",
      register: "/api/v1/auth/register",
      refresh: "/api/v1/auth/refresh",
      logout: "/api/v1/auth/logout",
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

      /* Product workflow APIs (datasets, training, scans, analytics, reports). */
      datasets: "/api/v1/datasets",
      datasetsAuthStatus: "/api/v1/datasets/auth-status",
      datasetsPrepared: "/api/v1/datasets/prepared",
      training: "/api/v1/training",
      trainingEvaluate: function (name) {
        return "/api/v1/training/" + encodeURIComponent(name) + "/evaluate";
      },
      scans: "/api/v1/scans",
      analyticsSummary: "/api/v1/analytics/summary",
      analyticsCross: "/api/v1/analytics/cross",
      reports: "/api/v1/reports",
      reportDownload: function (reportId, format) {
        return (
          "/api/v1/reports/" +
          encodeURIComponent(reportId) +
          "/download?format=" +
          encodeURIComponent(format || "md")
        );
      },
    },
  };
})();
