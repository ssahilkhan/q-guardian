/* Q-Guardian Console — shell, navigation and router.
 * Renders the sidebar navigation, topbar breadcrumbs and system status,
 * then routes hash URLs (#/view, #/detection/:id) to the view modules.
 * Includes authentication gating: unauthenticated users see a login form;
 * authenticated users see the full console.
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
    analytics:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
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
    logout:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    user:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
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
        { id: "analytics", label: "Analytics", icon: ICONS.analytics },
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

  /* ---- Authentication gate -------------------------------------------- */

  function renderLoginScreen() {
    var main = document.querySelector(".workspace");
    if (!main) return;
    main.innerHTML =
      '<div class="login-container">' +
      '<div class="login-card">' +
      '<div class="login-brand">' +
      '<img class="brand-mark" src="/ui/favicon.svg" alt="" aria-hidden="true" />' +
      "<h1>Q-Guardian</h1>" +
      '<p>Runtime Security Console</p>' +
      "</div>" +
      '<form id="loginForm" class="login-form" autocomplete="on">' +
      '<div class="field">' +
      '<label for="loginUser">Username</label>' +
      '<input type="text" id="loginUser" name="username" autocomplete="username" placeholder="Enter username" required />' +
      "</div>" +
      '<div class="field">' +
      '<label for="loginPass">Password</label>' +
      '<input type="password" id="loginPass" name="password" autocomplete="current-password" placeholder="Enter password" required />' +
      "</div>" +
      '<div id="loginError"></div>' +
      '<div class="row end"><button type="submit" class="btn primary" id="loginBtn">Sign In</button></div>' +
      "</form>" +
      '<div class="login-footer">' +
      "<p>No account? Configure users via the <code>AUTH_USERS</code> environment variable.</p>" +
      "</div>" +
      "</div>" +
      "</div>";

    var form = document.getElementById("loginForm");
    var errorBox = document.getElementById("loginError");
    var btn = document.getElementById("loginBtn");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var username = document.getElementById("loginUser").value.trim();
      var password = document.getElementById("loginPass").value;
      errorBox.innerHTML = "";
      btn.disabled = true;
      btn.textContent = "Signing in…";

      QG.api
        .login(username, password)
        .then(function () {
          renderConsole();
        })
        .catch(function (err) {
          errorBox.innerHTML = U.errorState(err.message || "Login failed.");
          btn.disabled = false;
          btn.textContent = "Sign In";
        });
    });

    /* Focus the username field */
    setTimeout(function () {
      var el = document.getElementById("loginUser");
      if (el) el.focus();
    }, 50);
  }

  function renderConsole() {
    /* Restore the full console shell */
    var main = document.querySelector(".workspace");
    if (!main) return;
    main.innerHTML =
      '<header class="topbar">' +
      '<nav id="breadcrumbs" class="breadcrumbs" aria-label="Breadcrumb"></nav>' +
      '<div class="topbar-right">' +
      '<div class="user-info" id="userInfo"></div>' +
      '<div class="sys-status">' +
      '<span class="pulse" id="statusDot" aria-hidden="true"></span>' +
      '<span id="statusText">checking…</span>' +
      "</div>" +
      "</div>" +
      "</header>" +
      '<main id="appView" class="content">' +
      '<div id="bootState" class="empty-state">' +
      '<div class="spinner" aria-hidden="true"></div>' +
      "<p>Loading console…</p>" +
      "</div>" +
      "</main>";

    updateUserInfo();
    render();
    loadVersion();
    refreshStatus();
    setInterval(refreshStatus, 20000);
  }

  function updateUserInfo() {
    var el = document.getElementById("userInfo");
    if (!el) return;
    var user = QG.api.getCurrentUser();
    if (user) {
      el.innerHTML =
        '<span class="user-badge">' +
        ICONS.user +
        "<span>" + U.text(user.username) + "</span>" +
        "</span>" +
        '<button type="button" class="btn ghost btn-sm" id="logoutBtn" title="Sign out">' +
        ICONS.logout +
        "</button>";
      var logoutBtn = document.getElementById("logoutBtn");
      if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
          QG.api.logout();
          renderLoginScreen();
        });
      }
    }
  }

  /* ---- Navigation / routing ------------------------------------------- */

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
    if (!nav) return;
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
    if (!crumbs) return;
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

  function render() {
    var route = parseHash(window.location.hash);
    var resolved = resolveRoute(route);

    renderNav(resolved.activeId);

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
        if (err && err.authError) {
          renderLoginScreen();
          return;
        }
        showError(err && err.message ? err.message : "Unknown error.");
      });
  }

  /* ---- Status --------------------------------------------------------- */

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
    var el = document.getElementById("sidebarVersion");
    if (!el) return;
    try {
      var payload = await QG.api.get(QG.api.endpoints.version);
      var version = QG.api.data(payload);
      el.textContent = "Q-Guardian v" + (version ? version.version : "—");
    } catch (err) {
      el.textContent = "Q-Guardian";
    }
  }

  /* ---- Rate limit notification ------------------------------------------ */

  function showRateLimitToast(message) {
    /* Remove existing toast if present */
    var existing = document.getElementById("rateLimitToast");
    if (existing) existing.remove();

    var toast = document.createElement("div");
    toast.id = "rateLimitToast";
    toast.className = "rate-limit-toast";
    toast.innerHTML =
      '<span class="toast-icon">⏳</span>' +
      '<span class="toast-message">' + U.text(message) + "</span>" +
      '<button type="button" class="toast-close" title="Dismiss">&times;</button>';
    document.body.appendChild(toast);

    /* Auto-dismiss after 5 seconds */
    var dismissTimer = setTimeout(function () {
      toast.remove();
    }, 5000);

    /* Close button */
    toast.querySelector(".toast-close").addEventListener("click", function () {
      clearTimeout(dismissTimer);
      toast.remove();
    });
  }

  /* ---- Auth event handlers -------------------------------------------- */

  function onAuthExpired() {
    renderLoginScreen();
  }

  function onAuthLogout() {
    renderLoginScreen();
  }

  /* ---- Boot ----------------------------------------------------------- */

  function boot() {
    QG.bus.on("auth:expired", onAuthExpired);
    QG.bus.on("auth:logout", onAuthLogout);
    QG.bus.on("rate:limited", function (data) {
      showRateLimitToast(data.message);
    });

    if (QG.api.isLoggedIn()) {
      /* Verify token is still valid by calling /me */
      QG.api
        .get(QG.api.endpoints.auth + "/me")
        .then(function () {
          renderConsole();
        })
        .catch(function () {
          QG.api.logout();
          renderLoginScreen();
        });
    } else {
      renderLoginScreen();
    }

    window.addEventListener("hashchange", function () {
      if (QG.api.isLoggedIn()) render();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
