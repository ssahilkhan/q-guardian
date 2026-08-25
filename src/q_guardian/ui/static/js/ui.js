/* Q-Guardian Console — shared UI helpers.
 * Rendering primitives used by every view: escaping, formatting, badges,
 * stat cards, risk bars, verdict banners, empty/error/loading states,
 * key/value grids and the toast notification.
 */
(function () {
  "use strict";

  var QG = (window.QG = window.QG || {});
  var U = {};

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function text(value) {
    return esc(value);
  }

  function fmtBytes(bytes) {
    if (bytes == null || isNaN(bytes)) return "—";
    var value = Number(bytes);
    if (value < 1024) return value + " B";
    var units = ["KB", "MB", "GB"];
    var index = -1;
    do {
      value = value / 1024;
      index += 1;
    } while (value >= 1024 && index < units.length - 1);
    return value.toFixed(value >= 100 ? 0 : 1) + " " + units[index];
  }

  function fmtMs(ms) {
    if (ms == null || isNaN(ms)) return "—";
    var value = Number(ms);
    if (value >= 1000) return value.toFixed(2) + " s";
    return value.toFixed(2) + " ms";
  }

  function fmtNum(value) {
    if (value == null || isNaN(value)) return "—";
    return Number(value).toLocaleString("en-US");
  }

  function fmtPct(value) {
    if (value == null || isNaN(value)) return "—";
    return (Number(value) * 100).toFixed(2) + "%";
  }

  function fmtDateTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return date.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function relTime(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    var seconds = Math.round((date.getTime() - Date.now()) / 1000);
    var abs = Math.abs(seconds);
    var future = seconds < 0 ? " ago" : " from now";
    var unit;
    var count;
    if (abs < 60) {
      unit = "sec";
      count = abs;
    } else if (abs < 3600) {
      unit = "min";
      count = Math.round(abs / 60);
    } else if (abs < 86400) {
      unit = "hr";
      count = Math.round(abs / 3600);
    } else {
      unit = "day";
      count = Math.round(abs / 86400);
    }
    return count + " " + unit + future;
  }

  /* ---- Decision / severity / status metadata ------------------------- */

  var DECISIONS = {
    allow: { label: "Allowed", cls: "allowed" },
    allowed: { label: "Allowed", cls: "allowed" },
    warn: { label: "Warning", cls: "warn" },
    warning: { label: "Warning", cls: "warn" },
    review: { label: "Review", cls: "review" },
    block: { label: "Blocked", cls: "block" },
    blocked: { label: "Blocked", cls: "block" },
  };

  function decisionMeta(value) {
    var key = String(value || "").toLowerCase();
    return (
      DECISIONS[key] || { label: String(value || "Unknown"), cls: "allowed" }
    );
  }

  var SEVERITIES = {
    info: { label: "Info", cls: "neutral" },
    low: { label: "Low", cls: "low" },
    medium: { label: "Medium", cls: "medium" },
    high: { label: "High", cls: "high" },
    critical: { label: "Critical", cls: "critical" },
  };

  function severityMeta(value) {
    var key = String(value || "").toLowerCase();
    return (
      SEVERITIES[key] || { label: String(value || "Unknown"), cls: "neutral" }
    );
  }

  var CATEGORIES = {
    prompt_injection: "Prompt Injection",
    jailbreak: "Jailbreak",
    role_manipulation: "Role Manipulation",
    system_prompt_leak: "System Prompt Leak",
    data_exfiltration: "Data Exfiltration",
    excessive_encoding: "Excessive Encoding",
    suspicious_formatting: "Suspicious Formatting",
    oversized_prompt: "Oversized Prompt",
    malformed_input: "Malformed Input",
    unknown: "Unknown",
  };

  function categoryLabel(value) {
    var key = String(value || "").toLowerCase();
    return CATEGORIES[key] || String(value || "Unknown");
  }

  function badge(value, cls) {
    cls = cls || "neutral";
    return '<span class="badge badge-' + esc(cls) + '">' + text(value) + "</span>";
  }

  function decisionBadge(value) {
    var meta = decisionMeta(value);
    return badge(meta.label, meta.cls);
  }

  function severityBadge(value) {
    var meta = severityMeta(value);
    return badge(meta.label, meta.cls);
  }

  function statusBadge(value) {
    var key = String(value || "").toLowerCase();
    var map = {
      active: "success",
      enabled: "success",
      true: "success",
      valid: "success",
      healthy: "success",
      operational: "success",
      installed: "success",
      available: "warn",
      degraded: "warn",
      false: "warn",
      disabled: "low",
      inactive: "low",
      idle: "low",
      offline: "low",
      down: "block",
      failed: "block",
      missing: "block",
      not_installed: "low",
    };
    return badge(key, map[key] || "neutral");
  }

  /* ---- Higher-level widgets ------------------------------------------- */

  function statCard(label, value, foot, tone) {
    tone = tone || "";
    return (
      '<div class="stat-card">' +
      '<span class="stat-label">' +
      (tone ? '<span class="badge badge-' + tone + ' badge-dot"></span>' : "") +
      text(label) +
      "</span>" +
      '<span class="stat-value">' +
      (value == null || value === "" ? "—" : text(value)) +
      "</span>" +
      (foot ? '<span class="stat-foot">' + text(foot) + "</span>" : "") +
      "</div>"
    );
  }

  function riskBar(score) {
    var value = Number(score);
    if (isNaN(value)) value = 0;
    value = Math.max(0, Math.min(1, value));
    var pct = Math.round(value * 100);
    var tone = value >= 0.75 ? "block" : value >= 0.5 ? "review" : value >= 0.25 ? "warn" : "";
    return (
      '<div class="risk-bar">' +
      '<div class="risk-label">Risk score &mdash; ' + pct + "%</div>" +
      '<div class="risk-track"><div class="risk-fill ' + tone + '" style="width:' + pct + '%"></div></div>' +
      "</div>"
    );
  }

  var VERDICT_ICONS = {
    allowed:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    review:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    block:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>',
  };

  function verdictBanner(decision, title, body) {
    var meta = decisionMeta(decision);
    var icon = VERDICT_ICONS[meta.cls] || VERDICT_ICONS.allowed;
    return (
      '<div class="verdict-banner ' + meta.cls + '" role="status">' +
      '<div class="verdict-icon">' + icon + "</div>" +
      "<div>" +
      "<h3>" + text(title || meta.label) + "</h3>" +
      (body ? "<p>" + text(body) + "</p>" : "") +
      "</div>" +
      "</div>"
    );
  }

  function emptyState(message) {
    return (
      '<div class="empty-state"><p>' + text(message || "No data available.") + "</p></div>"
    );
  }

  function errorState(message) {
    return (
      '<div class="error-state" role="alert">' +
      '<span>' + text(message || "An unexpected error occurred.") + "</span>" +
      "</div>"
    );
  }

  function loadingState(message) {
    message = message || "Loading…";
    return (
      '<div class="loading-inline"><div class="spinner" aria-hidden="true"></div>' +
      text(message) +
      "</div>"
    );
  }

  function note(message, tone) {
    tone = tone || "";
    return (
      '<div class="note">' +
      '<svg class="note-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>' +
      "<span>" + text(message) + "</span>" +
      "</div>"
    );
  }

  function keyValue(items) {
    if (!items || !items.length) return emptyState("No values.");
    var rows = items
      .map(function (item) {
        return (
          '<div class="kv-item">' +
          '<div class="kv-key">' + text(item.label) + "</div>" +
          '<div class="kv-value' + (item.mono ? " mono" : "") + '">' +
          (item.html ? item.html : text(item.value)) +
          "</div>" +
          "</div>"
        );
      })
      .join("");
    return '<div class="kv-grid">' + rows + "</div>";
  }

  function codeBlock(json) {
    var content = json;
    if (typeof json !== "string") {
      try {
        content = JSON.stringify(json, null, 2);
      } catch (e) {
        content = String(json);
      }
    }
    return '<pre class="code-block">' + esc(content) + "</pre>";
  }

  /* ---- Table helper ---------------------------------------------------- */

  function table(headers, rows) {
    if (!rows || !rows.length) {
      return (
        '<div class="table-wrap"><table class="data-table"><thead><tr>' +
        headers
          .map(function (header) {
            return "<th>" + esc(header) + "</th>";
          })
          .join("") +
        '</tr></thead><tbody><tr class="empty-row"><td colspan="' +
        headers.length +
        '">No rows to display.</td></tr></tbody></table></div>'
      );
    }
    var head = headers
      .map(function (header) {
        return "<th>" + (header instanceof Object ? esc(header.label) : esc(header)) + "</th>";
      })
      .join("");
    var body = rows
      .map(function (row) {
        return (
          "<tr>" +
          row
            .map(function (cell) {
              if (cell == null || cell === "") return "<td>—</td>";
              if (cell instanceof Object) {
                var content =
                  cell.html != null ? cell.html : text(cell.value == null ? "" : cell.value);
                return (
                  "<td" +
                  (cell.cls ? ' class="' + esc(cell.cls) + '"' : "") +
                  (cell.title ? ' title="' + esc(cell.title) + '"' : "") +
                  ">" +
                  content +
                  "</td>"
                );
              }
              return "<td>" + text(cell) + "</td>";
            })
            .join("") +
          "</tr>"
        );
      })
      .join("");
    return (
      '<div class="table-wrap"><table class="data-table"><thead><tr>' +
      head +
      "</tr></thead><tbody>" +
      body +
      "</tbody></table></div>"
    );
  }

  /* ---- Toast ----------------------------------------------------------- */

  var toastTimer = null;

  function toast(message, tone, duration) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.className = "toast" + (tone === "error" ? " error" : "");
    el.textContent = message;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.className = "toast hidden";
    }, duration || 3500);
  }

  /* ---- Params ---------------------------------------------------------- */

  function intParam(value, fallback) {
    var parsed = parseInt(value, 10);
    return isNaN(parsed) ? fallback : parsed;
  }

  U.esc = esc;
  U.text = text;
  U.fmtBytes = fmtBytes;
  U.fmtMs = fmtMs;
  U.fmtNum = fmtNum;
  U.fmtPct = fmtPct;
  U.fmtDateTime = fmtDateTime;
  U.relTime = relTime;
  U.decisionMeta = decisionMeta;
  U.severityMeta = severityMeta;
  U.categoryLabel = categoryLabel;
  U.badge = badge;
  U.decisionBadge = decisionBadge;
  U.severityBadge = severityBadge;
  U.statusBadge = statusBadge;
  U.statCard = statCard;
  U.riskBar = riskBar;
  U.verdictBanner = verdictBanner;
  U.emptyState = emptyState;
  U.errorState = errorState;
  U.loadingState = loadingState;
  U.note = note;
  U.keyValue = keyValue;
  U.codeBlock = codeBlock;
  U.table = table;
  U.toast = toast;
  U.intParam = intParam;

  QG.ui = U;

  /* ---- Simple event bus ----------------------------------------------- */

  if (!QG.bus) {
    var listeners = {};
    QG.bus = {
      on: function (event, fn) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(fn);
      },
      off: function (event, fn) {
        if (!listeners[event]) return;
        listeners[event] = listeners[event].filter(function (f) { return f !== fn; });
      },
      emit: function (event, data) {
        (listeners[event] || []).forEach(function (fn) {
          try { fn(data); } catch (e) { /* swallow */ }
        });
      },
    };
  }
})();
