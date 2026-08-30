/* Q-Guardian Console — Historical analytics computations.
 * Pure functions that derive timeline groups, trend series and aggregates
 * from *real* scan records returned by GET /api/v1/analysis. The module is
 * isomorphic so the same code runs in the browser (window.QG.analytics) and
 * under Node for the dependency-free frontend tests (module.exports).
 *
 * All inputs are the AnalysisItemSchema records the backend actually sends:
 *   { analysis_id, decision, risk_score, is_valid, finding_count,
 *     high_severity_count, processing_time_ms, timestamp, payload }
 * and payload.findings[].{category, severity, ...} plus
 * payload.metadata.{ml_findings_count, ml_risk_score, ...}.
 *
 * Nothing here fabricates data: every metric is counted from the items it is
 * given. If a metric cannot be computed reliably it is omitted.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.QG = root.QG || {};
    root.QG.analytics = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var HOUR_MS = 3600000;
  var DAY_MS = 86400000;

  function normalizeDecision(value) {
    var key = String(value || "").toLowerCase();
    if (key === "allowed") return "allow";
    return key;
  }

  function timestampOf(item) {
    if (!item || !item.timestamp) return NaN;
    var t = new Date(item.timestamp);
    return isNaN(t.getTime()) ? NaN : t.getTime();
  }

  function payloadOf(item) {
    return (item && item.payload) || {};
  }

  function findingsOf(item) {
    return payloadOf(item).findings || [];
  }

  function metadataOf(item) {
    return payloadOf(item).metadata || {};
  }

  /* ---- Filters --------------------------------------------------------- */

  function withinHours(items, hours) {
    if (hours == null) return items;
    var cutoff = Date.now() - hours * HOUR_MS;
    return items.filter(function (item) {
      var t = timestampOf(item);
      return !isNaN(t) && t >= cutoff;
    });
  }

  /* ---- Aggregation ------------------------------------------------------ */

  function decisionCounts(items) {
    var counts = { allow: 0, warn: 0, review: 0, block: 0 };
    items.forEach(function (item) {
      var key = normalizeDecision(item && item.decision);
      if (counts[key] !== undefined) counts[key] += 1;
    });
    return counts;
  }

  function severityCounts(items) {
    var counts = { info: 0, low: 0, medium: 0, high: 0, critical: 0 };
    items.forEach(function (item) {
      findingsOf(item).forEach(function (finding) {
        var key = String((finding && finding.severity) || "").toLowerCase();
        if (counts[key] !== undefined) counts[key] += 1;
      });
    });
    return counts;
  }

  function categoryFrequency(items) {
    var map = {};
    items.forEach(function (item) {
      findingsOf(item).forEach(function (finding) {
        var key = String((finding && finding.category) || "unknown").toLowerCase();
        if (!map[key]) map[key] = 0;
        map[key] += 1;
      });
    });
    return Object.keys(map)
      .map(function (key) {
        return { category: key, count: map[key] };
      })
      .sort(function (a, b) {
        return b.count - a.count;
      });
  }

  function mlSummary(items) {
    var scansWithMl = 0;
    var findings = 0;
    items.forEach(function (item) {
      var metadata = metadataOf(item);
      var count = metadata.ml_findings_count || 0;
      var hasMl = count > 0 || metadata.ml_risk_score !== undefined;
      if (hasMl) {
        scansWithMl += 1;
        findings += count;
      }
    });
    return { scans_with_ml: scansWithMl, findings: findings };
  }

  function summarize(items) {
    var decisions = decisionCounts(items);
    var severities = severityCounts(items);
    var ml = mlSummary(items);
    var riskScores = [];
    var processingTimes = [];
    var invalid = 0;
    var highSeverity = 0;
    items.forEach(function (item) {
      var risk = Number(item && item.risk_score);
      if (!isNaN(risk) && risk !== null && item.risk_score != null) {
        riskScores.push(Math.max(0, Math.min(1, risk)));
      }
      var ms = Number(item && item.processing_time_ms);
      if (!isNaN(ms) && item.processing_time_ms != null) {
        processingTimes.push(ms);
      }
      if (item && item.is_valid === false) invalid += 1;
      highSeverity += Number(item && item.high_severity_count) || 0;
    });

    function average(values) {
      if (!values.length) return null;
      return values.reduce(function (a, b) { return a + b; }, 0) / values.length;
    }

    return {
      total: items.length,
      decisions: decisions,
      severities: severities,
      categories: categoryFrequency(items),
      ml: ml,
      avg_risk: average(riskScores),
      avg_processing_ms: average(processingTimes),
      invalid_count: invalid,
      high_severity_count: highSeverity,
    };
  }

  /* ---- Time series ------------------------------------------------------- */

  function scanVolume(items, bucketMs) {
    var buckets = {};
    items.forEach(function (item) {
      var t = timestampOf(item);
      if (isNaN(t)) return;
      var key = Math.floor(t / bucketMs) * bucketMs;
      if (!buckets[key]) buckets[key] = 0;
      buckets[key] += 1;
    });
    return Object.keys(buckets)
      .map(function (key) {
        var t = Number(key);
        return { t: t, label: bucketLabel(t, bucketMs), count: buckets[key] };
      })
      .sort(function (a, b) { return a.t - b.t; });
  }

  function bucketLabel(t, bucketMs) {
    var date = new Date(t);
    if (bucketMs < HOUR_MS * 24) {
      return (
        String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0")
      );
    }
    return (
      date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
    );
  }

  function metricTrend(items, pick) {
    var points = [];
    items.forEach(function (item) {
      var t = timestampOf(item);
      if (isNaN(t)) return;
      var value = pick(item);
      if (value == null || isNaN(Number(value))) return;
      points.push({ t: t, label: bucketLabel(t, HOUR_MS * 6), value: Number(value) });
    });
    points.sort(function (a, b) { return a.t - b.t; });
    return points;
  }

  /* ---- Timeline grouping -------------------------------------------------- */

  function groupByDay(items) {
    var groups = {};
    items.forEach(function (item) {
      var t = timestampOf(item);
      if (isNaN(t)) return;
      var day = new Date(t);
      day.setHours(0, 0, 0, 0);
      var key = day.getTime();
      if (!groups[key]) {
        groups[key] = {
          day: key,
          label: day.toLocaleDateString("en-US", {
            weekday: "short",
            month: "short",
            day: "numeric",
          }),
          entries: [],
        };
      }
      groups[key].entries.push(item);
    });
    return Object.keys(groups)
      .map(function (key) { return groups[key]; })
      .sort(function (a, b) { return b.day - a.day; });
  }

  /* ---- Range helpers (client-side, documented as such) -------------------- */

  var RANGES = {
    "24h": { hours: 24, label: "Last 24 hours" },
    "7d": { hours: 7 * 24, label: "Last 7 days" },
    "30d": { hours: 30 * 24, label: "Last 30 days" },
    all: { hours: null, label: "All time" },
  };

  return {
    HOUR_MS: HOUR_MS,
    DAY_MS: DAY_MS,
    normalizeDecision: normalizeDecision,
    timestampOf: timestampOf,
    withinHours: withinHours,
    decisionCounts: decisionCounts,
    severityCounts: severityCounts,
    categoryFrequency: categoryFrequency,
    mlSummary: mlSummary,
    summarize: summarize,
    scanVolume: scanVolume,
    bucketLabel: bucketLabel,
    metricTrend: metricTrend,
    groupByDay: groupByDay,
    RANGES: RANGES,
  };
});