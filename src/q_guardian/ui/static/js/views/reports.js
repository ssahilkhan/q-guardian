/* Q-Guardian Console — Reports view.
 * Product-workflow report artifacts: inventory, on-demand generation and
 * download of scan / training / analytics reports. Reports are rendered from
 * real persisted artifacts; download content is fetched with auth headers and
 * saved via a Blob.
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  QG.views = QG.views || {};
  var api = QG.api;
  var U = QG.ui;

  var KIND_LABELS = {
    scan: "Security scan summary",
    training: "Training evaluation",
    analytics: "Cross-dataset analytics",
  };

  function downloadBlob(text, filename, mime) {
    var blob = new Blob([text], { type: mime || "application/octet-stream" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  }

  function renderInventory(entries) {
    if (!entries || !entries.length) {
      return U.emptyState("No report artifacts available. Generate one with the form above.");
    }
    var rows = entries.map(function (entry) {
      return [
        { value: entry.report_id, cls: "cell-mono cell-strong" },
        U.text(entry.kind || "—"),
        { value: entry.format, cls: "cell-mono" },
        { value: U.fmtBytes(entry.size), cls: "cell-mono" },
        U.fmtDateTime(entry.generated_at),
        {
          html:
            '<button type="button" class="btn ghost" data-download="' + U.esc(entry.report_id) + '" data-format="' + U.esc(entry.format) + '">Download</button>',
        },
      ];
    });
    return U.table(["Report ID", "Kind", "Format", "Size", "Generated", ""], rows);
  }

  function reportTargetOptions(entries) {
    var ids = [];
    (entries || []).forEach(function (entry) {
      if (ids.indexOf(entry.report_id) === -1) ids.push(entry.report_id);
    });
    ids.sort();
    var groups = { scan: [], training: [], analytics: [] };
    ids.forEach(function (id) {
      if (id.indexOf("scan:") === 0) groups.scan.push(id);
      else if (id.indexOf("training:") === 0) groups.training.push(id);
      else if (id.indexOf("analytics:") === 0) groups.analytics.push(id);
    });
    function optionsFor(items) {
      return items
        .map(function (id) {
          return '<option value="' + U.esc(id) + '">' + U.text(id) + "</option>";
        })
        .join("");
    }
    var html =
      '<optgroup label="Security scans">' + (optionsFor(groups.scan) || '<option value="">No scans with reports</option>') + "</optgroup>" +
      '<optgroup label="Training runs">' + (optionsFor(groups.training) || '<option value="">No evaluated runs</option>') + "</optgroup>" +
      '<optgroup label="Analytics">' + (optionsFor(groups.analytics) || '<option value="">No analytics reports</option>') + "</optgroup>";
    return html;
  }

  QG.views.reports = {
    title: "Reports",
    group: "overview",
    render: async function (el) {
      el.innerHTML = U.loadingState("Loading reports…");
      try {
        var payload = await api.get(api.endpoints.reports);
        var entries = api.data(payload) || [];

        el.innerHTML =
          '<div class="page-head">' +
          "<div>" +
          '<h2 class="page-title">Reports</h2>' +
          '<p class="page-sub">Generated report artifacts, rendered from real persisted sources — security scan summaries, training evaluations and cross-dataset analytics. Downloads carry API authentication and resolve strictly inside the artifact root.</p>' +
          "</div>" +
          '<button type="button" class="btn ghost" id="refreshReports">Refresh</button>' +
          "</div>" +

          '<div class="card">' +
          '<div class="card-head"><div><div class="card-title">Generate Report</div>' +
          '<div class="card-sub">Pick a source type and a persisted source id to (re)materialize its standard formats.</div></div></div>' +
          '<form id="reportForm">' +
          '<div class="row grid grid-3">' +
          '<div class="field"><label for="reportKind">Kind</label>' +
          '<select id="reportKind">' +
          "<option value=\"scan\">scan</option>" +
          "<option value=\"training\">training</option>" +
          "<option value=\"analytics\">analytics</option>" +
          "</select></div>" +
          '<div class="field" style="grid-column: span 2;"><label for="reportSource">Source id</label>' +
          '<select id="reportSource">' + reportTargetOptions(entries) + "</select>" +
          '<span class="field-note" id="reportKindNote">' + U.text(KIND_LABELS.scan) + "</span></div>" +
          "</div>" +
          '<div class="row end"><button type="submit" class="btn primary" id="reportBtn">Generate</button></div>' +
          "</form>" +
          '<div id="reportError"></div>' +
          '<div id="reportResult"></div>' +
          "</div>" +

          '<div class="section-title">All Reports</div>' +
          '<div class="card" style="padding:0;box-shadow:none;border:none;background:transparent;">' +
          renderInventory(entries) +
          "</div>";

        var errorSlot = el.querySelector("#reportError");
        var resultSlot = el.querySelector("#reportResult");
        var reportBtn = el.querySelector("#reportBtn");
        var kindSelect = el.querySelector("#reportKind");
        var sourceSelect = el.querySelector("#reportSource");

        kindSelect.addEventListener("change", function () {
          sourceSelect.innerHTML = reportTargetOptions(entries);
          var note = el.querySelector("#reportKindNote");
          if (note) note.textContent = KIND_LABELS[kindSelect.value] || "";
        });

        el.querySelector("#reportForm").addEventListener("submit", async function (event) {
          event.preventDefault();
          errorSlot.innerHTML = "";
          resultSlot.innerHTML = "";
          var reportId = sourceSelect.value;
          if (!reportId) {
            errorSlot.innerHTML = U.errorState("Choose a source id to generate a report for.");
            return;
          }
          reportBtn.disabled = true;
          try {
            var payload = await api.post(api.endpoints.reports, {
              kind: kindSelect.value,
              report_id: reportId,
            });
            var result = api.data(payload) || {};
            var formats = (result.formats || []).join(", ");
            resultSlot.innerHTML =
              '<div class="card">' +
              '<div class="card-head"><div><div class="card-title">Report Available</div>' +
              '<div class="card-sub">' + U.text(result.report_id || reportId) + " · " + (result.entries || []).length + " format(s) (" + U.text(formats || "—") + ")</div></div></div>" +
              "</div>";
            U.toast("Report generated.", "success");
            QG.views.reports.render(el);
          } catch (err) {
            errorSlot.innerHTML = U.errorState(err.message || "Could not generate report.");
          } finally {
            reportBtn.disabled = false;
          }
        });

        var refreshBtn = el.querySelector("#refreshReports");
        if (refreshBtn) {
          refreshBtn.addEventListener("click", function () {
            QG.views.reports.render(el);
          });
        }

        var downloadButtons = el.querySelectorAll("[data-download]");
        downloadButtons.forEach(function (button) {
          button.addEventListener("click", async function () {
            var reportId = button.getAttribute("data-download");
            var format = button.getAttribute("data-format") || "md";
            button.disabled = true;
            try {
              var data = await api.text(api.endpoints.reportDownload(reportId, format));
              var filename = reportId.replace(/[^\w.-]+/g, "_") + "." + format;
              downloadBlob(data, filename);
              U.toast("Downloaded " + filename + ".", "success");
            } catch (err) {
              U.toast(err.message || "Download failed.", "error");
            } finally {
              button.disabled = false;
            }
          });
        });
      } catch (err) {
        el.innerHTML = U.errorState(err.message || "Could not load reports.");
      }
    },
  };
})();