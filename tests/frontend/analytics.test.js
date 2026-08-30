/* Q-Guardian Console — dependency-free tests for the historical analytics
 * module (src/q_guardian/ui/static/js/analytics.js). Runs on plain Node
 * with no packages:  node tests/frontend/analytics.test.js
 *
 * These tests verify that analytics are computed from the real scan-record
 * shape the backend sends (analysis_id, decision, risk_score, is_valid,
 * finding_count, high_severity_count, processing_time_ms, timestamp,
 * payload.findings[], payload.metadata[]) and that no metric is fabricated.
 */
"use strict";

var assert = require("node:assert");
process.env.TZ = "UTC";
var A = require("../../src/q_guardian/ui/static/js/analytics.js");

function scan(overrides) {
  var base = {
    analysis_id: "abc12345",
    decision: "allow",
    risk_score: 0.12,
    is_valid: true,
    finding_count: 0,
    high_severity_count: 0,
    processing_time_ms: 4.2,
    timestamp: "2026-08-29T16:42:00Z",
    payload: {
      findings: [],
      metadata: { ml_findings_count: 0, rule_findings_count: 0 },
    },
  };
  var item = Object.assign({}, base, overrides || {});
  item.payload = Object.assign({ findings: [] }, base.payload, (overrides && overrides.payload) || {});
  return item;
}

(function testNormalizeDecision() {
  assert.strictEqual(A.normalizeDecision("allow"), "allow");
  assert.strictEqual(A.normalizeDecision("ALLOW"), "allow");
  assert.strictEqual(A.normalizeDecision("allowed"), "allow");
  assert.strictEqual(A.normalizeDecision("block"), "block");
  assert.strictEqual(A.normalizeDecision(null), "");
  console.log("ok — normalizeDecision");
})();

(function testDecisionCounts() {
  var items = [
    scan({ decision: "allow" }),
    scan({ decision: "ALLOW" }),
    scan({ decision: "review" }),
    scan({ decision: "block" }),
    scan({ decision: "warn" }),
  ];
  var counts = A.decisionCounts(items);
  assert.deepStrictEqual(counts, { allow: 2, warn: 1, review: 1, block: 1 });
  console.log("ok — decisionCounts");
})();

(function testSeverityAndCategoryCounts() {
  var findings = [
    { category: "prompt_injection", severity: "high" },
    { category: "prompt_injection", severity: "medium" },
    { category: "jailbreak", severity: "critical" },
  ];
  var items = [scan({ payload: { findings: findings } })];
  var severities = A.severityCounts(items);
  assert.deepStrictEqual(severities, { info: 0, low: 0, medium: 1, high: 1, critical: 1 });
  var cats = A.categoryFrequency(items);
  assert.strictEqual(cats.length, 2);
  assert.strictEqual(cats[0].category, "prompt_injection");
  assert.strictEqual(cats[0].count, 2);
  console.log("ok — severityCounts + categoryFrequency");
})();

(function testMlSummary() {
  var inactive = scan({ payload: { metadata: { ml_findings_count: 0 } } });
  var withMl = scan({ decision: "block", payload: { metadata: { ml_findings_count: 2, ml_risk_score: 0.9 } } });
  var summary = A.mlSummary([inactive, withMl]);
  assert.deepStrictEqual(summary, { scans_with_ml: 1, findings: 2 });
  console.log("ok — mlSummary");
})();

(function testSummarize() {
  var items = [
    scan({ risk_score: 0.0, processing_time_ms: 10, is_valid: true, high_severity_count: 0 }),
    scan({ risk_score: 0.8, processing_time_ms: 30, is_valid: false, high_severity_count: 2 }),
  ];
  var summary = A.summarize(items);
  assert.strictEqual(summary.total, 2);
  assert.ok(Math.abs(summary.avg_risk - 0.4) < 1e-9);
  assert.ok(Math.abs(summary.avg_processing_ms - 20) < 1e-9);
  assert.strictEqual(summary.invalid_count, 1);
  assert.strictEqual(summary.high_severity_count, 2);
  assert.strictEqual(summary.decisions.allow, 2);
  assert.strictEqual(summary.ml.scans_with_ml, 0);
  assert.strictEqual(summary.categories.length, 0);
  console.log("ok — summarize");
})();

(function testWithinHours() {
  var now = Date.now();
  var old = scan({ timestamp: new Date(now - 48 * 3600000).toISOString() });
  var fresh = scan({ timestamp: new Date(now - 2 * 3600000).toISOString() });
  var filtered = A.withinHours([old, fresh], 24);
  assert.strictEqual(filtered.length, 1);
  assert.strictEqual(filtered[0].analysis_id, fresh.analysis_id);
  assert.strictEqual(A.withinHours([old, fresh], null).length, 2);
  console.log("ok — withinHours");
})();

(function testScanVolume() {
  var items = [
    scan({ timestamp: "2026-08-29T10:00:00Z" }),
    scan({ timestamp: "2026-08-29T11:00:00Z" }),
    scan({ timestamp: "2026-08-30T10:00:00Z" }),
  ];
  var volume = A.scanVolume(items, A.DAY_MS);
  assert.strictEqual(volume.length, 2);
  var day0 = volume[0];
  var day1 = volume[1];
  assert.ok(day0.t < day1.t);
  assert.strictEqual(day0.count, 2);
  assert.strictEqual(day1.count, 1);
  assert.ok(day0.label);
  console.log("ok — scanVolume");
})();

(function testMetricTrend() {
  var items = [
    scan({ timestamp: "2026-08-29T12:00:00Z", risk_score: 0.1 }),
    scan({ timestamp: "2026-08-29T13:00:00Z", risk_score: 0.5 }),
  ];
  var trend = A.metricTrend(items, function (item) { return item.risk_score; });
  assert.strictEqual(trend.length, 2);
  assert.ok(trend[0].t < trend[1].t);
  assert.strictEqual(trend[0].value, 0.1);
  assert.strictEqual(trend[1].value, 0.5);
  var withNull = A.metricTrend(
    [scan({ timestamp: "2026-08-29T14:00:00Z", risk_score: null })],
    function (item) { return item.risk_score; }
  );
  assert.strictEqual(withNull.length, 0);
  console.log("ok — metricTrend");
})();

(function testGroupByDay() {
  var items = [
    scan({ timestamp: "2026-08-29T10:00:00Z" }),
    scan({ timestamp: "2026-08-29T22:30:00Z" }),
    scan({ timestamp: "2026-08-28T09:00:00Z" }),
  ];
  var groups = A.groupByDay(items);
  assert.strictEqual(groups.length, 2);
  assert.ok(groups[0].day > groups[1].day, "groups sorted most recent first");
  assert.strictEqual(groups[0].entries.length, 2);
  assert.strictEqual(groups[1].entries.length, 1);
  assert.ok(groups[0].label);
  console.log("ok — groupByDay");
})();

console.log("\nAll analytics frontend tests passed.");