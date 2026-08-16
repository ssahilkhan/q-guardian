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

  async function request(path, options) {
    var opts = Object.assign({ headers: {} }, options || {});
    if (opts.body) {
      opts.headers["Content-Type"] = "application/json";
    }
    var response;
    try {
      response = await fetch(path, opts);
    } catch (networkError) {
      var err = new Error(
        "Cannot reach the Q-Guardian API at " +
          path +
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
      var message =
        typeof detail === "string" ? detail : JSON.stringify(detail);
      var failure = new Error(message);
      failure.status = response.status;
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
    },
  };
})();
