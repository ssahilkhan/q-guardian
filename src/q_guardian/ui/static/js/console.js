/* Q-Guardian Console — shell, navigation and router.
 * Renders the sidebar navigation, topbar breadcrumbs and system status,
 * then routes hash URLs (#/view, #/detection/:id) to the view modules.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  var U = QG.ui;

  var ICONS = {
    dashboard:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    scanner:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    detection:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    pipeline:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    rules:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    models:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/></svg>',
    quantum:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="10" ry="4.5"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(120 12 12)"/></svg>',
    training:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    evaluation:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    benchmarks:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
    audit:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    configuration:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>',
    documentation:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
  };

  var NAV = [
    {
      group: "Overview",
      items: [
        { id: "dashboard", label: "Dashboard", icon: ICONS.dashboard },
        { id: "scanner", label: "Scanner", icon: ICONS.scanner },
      ],
    },
    {
      group: "Analysis",
      items: [
        { id: "detection", label: "Detection", icon: ICONS.detection },
        { id: "pipeline", label: "Pipeline", icon: ICONS.pipeline },
        { id: "rules", label: "Rules", icon: ICONS.rules },
        { id: "models", label: "Models", icon: ICONS.models },
        { id: "quantum", label: "Quantum", icon: ICONS.quantum },
      ],
    },
    {
      group: "Research",
      items: [
        { id: "training", label: "Training", icon: ICONS.training },
        { id: "evaluation", label: "Evaluation", icon: ICONS.evaluation },
        { id: "benchmarks", label: "Benchmarks", icon: ICONS.benchmarks },
      ],
    },
    {
      group: "System",
      items: [
        { id: "audit", label: "Audit", icon: ICONS.audit },
        { id: "configuration", label: "Configuration", icon: ICONS.configuration },
        { id: "documentation", label: "Documentation", icon: ICONS.documentation },
      ],
    },
  ];

  var VIEWS = (QG.views = QG.views || {});
  var appView = null;
  var currentRoute = null;

  function findNavItem(id) {
    for (var i = 0; i < NAV.length; i += 1) {
      for (var j = 0; j < NAV[i].items.length; j += 1) {
        if (NAV[i].items[j].id === id) return NAV[i].items[j];
      }
    }
    return null;
  }

  function parseHash(hash) {
    var raw = (hash || "").replace(/^#/, "");
    var parts = raw.split("/").filter(Boolean);
    var query = {};
    var last = parts[parts.length - 1];
    if (last && last.indexOf("?") !== -1) {
      var pieces = last.split("?");
      parts[parts.length - 1] = pieces[0];
      pieces.slice(1).forEach(function (chunk) {
        chunk.split("&").forEach(function (pair) {
          if (!pair) return;
          var eq = pair.indexOf("=");
          if (eq === -1) {
            query[decodeURIComponent(pair)] = "";
          } else {
            query[decodeURIComponent(pair.slice(0, eq))] = decodeURIComponent(pair.slice(eq + 1));
          }
        });
      });
    }
    return { segments: parts, query: query };
  }

  function resolveRoute(route) {
    var segments = route.segments;
    var first = segments[0] || "dashboard";
    var params = Object.assign({}, route.query);

    if (first === "detection" && segments.length > 1) {
      params.id = decodeURIComponent(segments[1]);
    }

    var view = VIEWS[first];
    if (!view) {
      return { view: null, activeId: first };
    }
    return { view: view, activeId: first, params: params };
  }

  function renderNav(activeId) {
    var nav = document.getElementById("sideNav");
    var html = NAV.map(function (group) {
      var items = group.items
        .map(function (item) {
          return (
            '<a class="nav-item' + (item.id === activeId ? " active" : "") + '" href="#/' + item.id + '">' +
            '<span class="nav-icon" aria-hidden="true">' + item.icon + "</span>" +
            '<span>' + U.text(item.label) + "</span>" +
            "</a>"
          );
        })
        .join("");
      return (
        '<div class="nav-group">' +
        '<span class="nav-group-label">' + U.text(group.group) + "</span>" +
        items +
        "</div>"
      );
    }).join("");
    nav.innerHTML = html;
  }

  function renderCrumbs(view, params) {
    var crumbs = document.getElementById("breadcrumbs");
    var html =
      '<a class="crumb" href="#/dashboard">Console</a>' +
      '<span class="crumb-sep">/</span>';
    if (view && view.crumb) {
      html +=
        '<a class="crumb" href="#/detection">' + U.text(view.title) + "</a>" +
        '<span class="crumb-sep">/</span>' +
        '<span class="crumb current">' + U.text(view.crumb(params)) + "</span>";
    } else if (view) {
      html += '<span class="crumb current">' + U.text(view.title) + "</span>";
    } else {
      html += '<span class="crumb current">Not found</span>';
    }
    crumbs.innerHTML = html;
  }

  function showError(message) {
    if (appView) {
      appView.innerHTML =
        '<div class="page-head"><div><h2 class="page-title">Error</h2></div></div>' +
        U.errorState(message || "Something went wrong while loading this view.");
    }
  }

  function renderUserBar() {
    var el = document.getElementById("userBar");
    if (!el) return;
    var authed = QG.auth && QG.auth.isAuthed();
    var user = (QG.auth && QG.auth.user()) || "";
    if (!authed) {
      el.innerHTML = "";
      return;
    }
    var label = user ? U.text(user) : "Operator";
    el.innerHTML =
      '<span class="user-chip">' + label + "</span>" +
      '<button type="button" class="btn ghost" id="logoutBtn">Log out</button>';
    var btn = el.querySelector("#logoutBtn");
    if (btn) {
      btn.addEventListener("click", function () {
        if (QG.auth && typeof QG.auth.logout === "function") {
          QG.auth.logout();
        }
      });
    }
  }

  function render() {
    var route = parseHash(window.location.hash);
    var resolved = resolveRoute(route);

    renderNav(resolved.activeId);
    renderUserBar();

    /* Route guard: everything except the login view requires an active
     * session. Unauthenticated visitors are routed to the login view. */
    if (resolved.activeId !== "login" && !(QG.auth && QG.auth.isAuthed())) {
      QG.console.requireLogin();
      return;
    }

    if (!resolved.view) {
      renderCrumbs(null, null);
      showError("Unknown route: #/" + resolved.activeId);
      return;
    }

    renderCrumbs(resolved.view, resolved.params);
    appView = document.getElementById("appView");
    if (!appView) return;

    Promise.resolve()
      .then(function () {
        return resolved.view.render(appView, resolved.params);
      })
      .catch(function (err) {
        showError(err && err.message ? err.message : "Unknown error.");
      });
  }

  function setStatus(state, text) {
    var dot = document.getElementById("statusDot");
    var label = document.getElementById("statusText");
    if (dot) dot.className = "pulse " + (state || "");
    if (label) label.textContent = text || "";
  }

  async function refreshStatus() {
    setStatus("checking", "checking…");
    try {
      var payload = await QG.api.get(QG.api.endpoints.health);
      var status = payload && payload.status ? payload.status : "operational";
      if (status === "healthy") {
        setStatus("ok", "operational");
      } else if (status === "degraded") {
        setStatus("degraded", "degraded");
      } else {
        setStatus("ok", String(status));
      }
    } catch (err) {
      setStatus("down", "offline");
    }
  }

  async function loadVersion() {
    var el = document.getElementById("versionInfo");
    if (!el) return;
    try {
      var payload = await QG.api.get(QG.api.endpoints.version);
      var version = QG.api.data(payload);
      el.textContent = "Q-Guardian v" + (version ? version.version : "—");
    } catch (err) {
      el.textContent = "Q-Guardian";
    }
  }

  function boot() {
    window.addEventListener("hashchange", render);
    render();
    loadVersion();
    refreshStatus();
    setInterval(refreshStatus, 20000);
  }

  QG.console = {
    requireLogin: function () {
      var next = window.location.hash || "#/dashboard";
      window.location.hash = "#/login?next=" + encodeURIComponent(next);
    },

    onLogout: function () {
      window.location.hash = "#/login";
    },

    logout: function () {
      if (QG.auth && typeof QG.auth.logout === "function") {
        QG.auth.logout();
      }
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
