/* Q-Guardian Console — Dashboard view (Complete Dashboard).
 * Overview aggregates from /console/summary, /console/research, /health
 * plus a quick-scan control and recent analyses. Every number comes from
 * the live API — nothing is hardcoded.
 * Section order follows dashboard priority: system health, live protection
 * (rules/ML), security verdicts, quantum state, historical trends,
 * training status, recent activity.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;
  var A = QG.analytics;

  function renderDistribution(history) {
    var total = history.total || 0;
    if (!total) return U.emptyState("No scans recorded yet. Run a scan from the Scanner page.");
    var rows = [
      { key: "allowed", label: "Allowed", count: history.allowed || 0, cls: "success" },
      { key: "warn", label: "Warning", count: history.warn || 0, cls: "warning" },
      { key: "review", label: "Review", count: history.review || 0, cls: "review" },
      { key: "block", label: "Blocked", count: history.blocked || 0, cls: "block" },
    ];
    var bars = rows
      .map(function (row) {
        var pct = Math.round((row.count / total) * 100);
        return (
          '<div class="dist-row">' +
          '<span class="dist-label">' + row.label + "</span>" +
          '<div class="dist-track"><div class="dist-fill ' + row.cls + '" style="width:' + pct + '%"></div></div>' +
          '<span class="dist-value">' + U.fmtNum(row.count) + "</span>" +
          "</div>"
        );
      })
      .join("");
    return '<div class="distribution">' + bars + "</div>";
  }

  /* Real quantum state derived from the backend /console/models payload. */
  function quantumState(quantum) {
    var active = quantum && quantum.active === true;
    var backends = (quantum && quantum.backends) || [];
    var installed = backends.filter(function (b) { return b.installed; });
    var strategies = (quantum && quantum.fusion_strategies) || [];
    if (active) {
      return {
        label: "Active",
        cls: "success",
        detail: "Hybrid fusion is enabled in the scan path.",
      };
    }
    if (installed.length) {
      return {
        label: "Available — Not Executed",
        cls: "warning",
        detail:
          installed.map(function (b) { return b.name; }).join(", ") +
          " available; quantum is a research layer and is not executed in the default scan path.",
      };
    }
    return {
      label: "Unavailable",
      cls: "neutral",
      detail: "No quantum backends are installed. Quantum is research-only.",
    };
  }

  function renderComponents(summary, health) {
    var stages = (summary && summary.components) || [];
    var ml = (summary && summary.ml) || {};
    var quantum = (summary && summary.quantum) || {};
    if (!stages.length) return U.emptyState("No pipeline components reported.");

    var qState = quantumState(quantum);
    var rows = stages.map(function (component) {
      var status = component.status;
      var detail = component.detail || "";
      if (component.id === "ml") {
        status = ml.active ? "active" : "available";
        detail = ml.active
          ? (ml.detector_count || 0) + " detector(s), " + (ml.classifier_count || 0) + " classifier(s) active"
          : "no models loaded — scan path is rule-only";
      }
      if (component.id === "quantum") {
        status = qState.cls === "success" ? "active" : qState.cls === "warning" ? "available" : "disabled";
        detail = qState.detail;
      }
      return [
        { value: component.name, cls: "cell-strong" },
        U.badge(status === "active" ? "Active" : status === "available" ? "Available" : status === "disabled" ? "Disabled" : String(status), statusMap(status)),
        detail,
      ];
    });

    var dbStatus = health && (health.database && health.database.status);
    rows.push([
      { value: "Database", cls: "cell-strong" },
      U.badge(dbStatus === "healthy" ? "Connected" : dbStatus === "unhealthy" ? "Disconnected" : health ? "Degraded" : "Unknown", dbStatus === "healthy" ? "success" : "warning"),
      dbStatus === "healthy" ? "MongoDB reachable (live ping)" : (health && health.database && health.database.message) || "Database health unavailable",
    ]);
    return U.table(["Stage", "Status", "Details"], rows);
  }

  function statusMap(status) {
    if (status === "active") return "success";
    if (status === "available") return "warn";
    if (status === "disabled") return "low";
    return "neutral";
  }

  function renderRecent(history) {
    if (!history.items || !history.items.length) {
      return U.emptyState("No scans recorded yet.");
    }
    var rows = history.items.map(function (item) {
      return [
        {
          html: '<a class="row-link" href="#/detection/' + encodeURIComponent(item.analysis_id) + '">' +
            U.text(item.analysis_id.slice(0, 8)) + "</a>",
          title: item.analysis_id,
        },
        U.fmtDateTime(item.timestamp),
        U.decisionBadge(item.decision),
        { value: Math.round(Number(item.risk_score || 0) * 100) + "%", cls: "cell-mono" },
        item.finding_count,
        item.processing_time_ms == null ? "—" : item.processing_time_ms + " ms",
      ];
    });
    return U.table(
      ["Analysis", "Timestamp", "Decision", "Risk", "Findings", "Time"],
      rows
    );
  }

  function renderVolumeTrend(items) {
    if (!items.length) {
      return U.emptyState("No scan records to plot yet.");
    }
    var volume = A.scanVolume(items, A.DAY_MS);
    var bars = volume.map(function (bucket) {
      return { label: bucket.label, value: bucket.count, title: bucket.label + ": " + bucket.count + " scans", clsKey: "accent" };
    });
    return U.chart.bars({
      data: bars,
      height: 150,
      empty: "No scan records to plot yet.",
      ariaLabel: "Scan volume per day from retained scan records: " + bars.map(function (b) { return b.label + " = " + b.value; }).join(", "),
    });
  }

  function renderTrainingStatus(research) {
    var datasets = (research && research.datasets) || [];
    var artifacts = (research && research.model_artifacts) || [];
    var evaluation = (research && research.evaluation) || {};
    var artifactBytes = artifacts.reduce(function (sum, a) { return sum + (a.size || 0); }, 0);
    var hasArtifacts = datasets.length > 0 || artifacts.length > 0 || evaluation.present;

    var status = hasArtifacts ? "Artifacts on disk" : "No training artifacts";
    var cls = hasArtifacts ? "success" : "low";
    var detail =
      datasets.length + " dataset" + (datasets.length === 1 ? "" : "s") + " · " +
      artifacts.length + " model file" + (artifacts.length === 1 ? "" : "s") + " · " +
      U.fmtBytes(artifactBytes) + " · evaluation " + (evaluation.present ? "present" : "not generated");

    return (
      '<div class="card">' +
      '<div class="card-head"><div><div class="card-title">Training Status</div>' +
      '<div class="card-sub">Backend surface for training is artifact inventory via GET /console/research — the API exposes no live training run or progress events.</div></div>' +
      '<a class="btn ghost" href="#/training">View Training</a>' +
      "</div>" +
      '<div class="kv-grid" style="margin-bottom:6px;">' +
      '<div class="kv-item"><div class="kv-key">State</div><div class="kv-value">' + U.badge(status, cls) + " — No live run</div></div>" +
      '<div class="kv-item"><div class="kv-key">Artifacts</div><div class="kv-value">' + U.text(detail) + "</div></div>" +
      "</div>" +
      U.note("The backend does not expose a running training process, progress events or per-epoch metrics. This card reports the real on-disk training artifacts only.") +
      "</div>"
    );
  }

  function healthBadge(status) {
    if (status === "healthy") return U.badge("Healthy", "success");
    if (status === "degraded") return U.badge("Degraded", "warn");
    return U.badge("Unknown", "neutral");
  }

  QG.views.dashboard = {
    title: "Dashboard",
    group: "overview",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading dashboard…");
      try {
        var results = await Promise.all([
          api.get(api.endpoints.summary),
          api.get(api.endpoints.analysis + "?limit=50"),
          api.get(api.endpoints.health).catch(function () { return null; }),
          api.get(api.endpoints.research).catch(function () { return null; }),
        ]);
        var summaryPayload = results[0];
        var historyPayload = results[1];
        var healthPayload = results[2];
        var researchPayload = results[3];

        var summary = api.data(summaryPayload);
        var history = api.envelope(historyPayload);
        var research = researchPayload ? api.data(researchPayload) : {};
        var health = healthPayload ? (healthPayload.status || healthPayload.data && healthPayload.data.status || "unknown") : "unknown";
        var healthFull = healthPayload || {};

        var components = (summary.components || []).length;
        var rules = summary.rules || {};
        var ml = summary.ml || {};
        var quantum = summary.quantum || {};
        var backends = quantum.backends || [];
        var installed = backends.filter(function (b) {
          return b.installed;
        }).length;
        var historyCounts = summary.history || {};
        var qState = quantumState(quantum);

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Security Overview</h2>' +
          '<p class="page-sub">Real-time posture of the Q-Guardian runtime security pipeline: system health, detection rules, model availability, quantum research backends, historical scan trends and training artifacts. Every value comes from the live API.</p>' +
          "</div>" +
          "</div>" +

          '<div class="card">' +
          '<div class="card-head"><div><div class="card-title">Quick Scan</div>' +
          '<div class="card-sub">Submit a prompt through the full analysis pipeline (normalize, validate, features, rules, optional ML).</div></div></div>' +
          '<form id="dashboardScanForm">' +
          '<div class="field">' +
          '<textarea id="dashboardScanInput" rows="3" maxlength="100000" placeholder="Paste a prompt to analyze…"></textarea>' +
          "</div>" +
          '<div class="row end"><button type="submit" class="btn primary" id="dashboardScanBtn">Analyze Prompt</button></div>' +
          "</form>" +
          "</div>" +

          '<div class="section-title">System Health</div>' +
          '<div class="grid grid-4">' +
          U.statCard("System Health", health === "healthy" ? "Healthy" : health === "degraded" ? "Degraded" : "Unknown", "from /health", health === "healthy" ? "success" : "warning") +
          U.statCard("Detection Rules", rules.enabled != null ? rules.enabled + " / " + rules.total : rules.total, "enabled / total", "success") +
          U.statCard("ML Models", ml.loaded_models + " / " + ml.total_models, (ml.active ? "active" : "no models loaded"), ml.active ? "success" : "warning") +
          U.statCard("Quantum", qState.label, qState.detail, qState.cls === "success" ? "success" : qState.cls === "warning" ? "warning" : "low") +
          "</div>" +

          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">System Components</div>' +
          '<div class="card-sub">Live stage &amp; dependency status (from /summary, /health)</div></div>' +
          renderComponents(summary, healthFull) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Quantum Layer</div>' +
          '<div class="card-sub">Backend-reported state — never assumed</div></div>' +
          U.keyValue([
            { label: "State", html: U.badge(qState.label, qState.cls === "success" ? "success" : qState.cls === "warning" ? "warn" : "low") },
            { label: "Backends Installed", value: installed + " / " + backends.length },
            { label: "Fusion Strategies", value: (quantum.fusion_strategies || []).length },
            { label: "Executed in Scan Path", html: U.badge(quantum.active ? "Yes" : "No", quantum.active ? "success" : "low") },
          ]) +
          U.note(qState.detail) +
          "</div>" +
          "</div>" +

          renderTrainingStatus(research) +

          '<div class="section-title">Security Verdicts &amp; Trends</div>' +
          '<div class="grid grid-2">' +
          '<div class="card"><div class="card-head"><div class="card-title">Decision Distribution</div>' +
          '<div class="card-sub">' + U.fmtNum(historyCounts.total || 0) + " scans this session</div></div>" +
          renderDistribution(historyCounts) +
          "</div>" +
          '<div class="card"><div class="card-head"><div class="card-title">Scan Volume Trend</div>' +
          '<div class="card-sub">Daily volume from the ' + history.items.length + " most recent retained scans (GET /api/v1/analysis)</div></div>" +
          renderVolumeTrend(history.items) +
          "</div>" +
          "</div>" +

          '<div class="section-title">Recent Scans</div>' +
          '<div class="card" style="padding:0;box-shadow:none;border:none;background:transparent;">' +
          renderRecent(history) +
          "</div>" +
          '<div class="pagination"><a class="btn ghost" href="#/analytics">Open Historical Analytics →</a>' +
          '<span>Recent scans link to full reports.</span></div>';

        var form = el.querySelector("#dashboardScanForm");
        var input = el.querySelector("#dashboardScanInput");
        var btn = el.querySelector("#dashboardScanBtn");
        form.addEventListener("submit", async function (event) {
          event.preventDefault();
          var prompt = input.value.trim();
          if (!prompt) {
            U.toast("Enter a prompt to analyze.", "error");
            return;
          }
          btn.disabled = true;
          try {
            var result = await api.post(api.endpoints.scan, { prompt: prompt });
            var item = api.data(result);
            U.toast("Analysis completed — " + item.decision);
            window.location.hash = "#/detection/" + encodeURIComponent(item.analysis_id);
          } catch (err) {
            U.toast(err.message || "Scan failed.", "error");
          } finally {
            btn.disabled = false;
          }
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load dashboard.");
      }
    },
  };
})();