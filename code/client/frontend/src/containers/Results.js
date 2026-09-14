import React from 'react';
import XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import { useI18n } from '../i18n';

function statusClass(statusName) {
  // "good" (proven optimal), "accent" (feasible but the solver hit its
  // time/gap limit before proving optimality -- still a usable result,
  // just worth a visually distinct badge from a clean OPTIMAL), or "warn"
  // for anything else. See theme.css's .badge-accent / .run-status.accent
  // for the same three-way distinction used elsewhere on this page.
  if (!statusName) return "";
  const s = statusName.toUpperCase();
  if (s === "OPTIMAL") return "good";
  if (s === "FEASIBLE") return "accent";
  return "warn";
}

export default function Results({ runResult, attributes, goConfigure }) {
  const { t, tf } = useI18n();

  if (!runResult) {
    return (
      <div className="main-inner single"><div>
        <div className="page-head"><h2>{t("resultsTitle")}</h2></div>
        <div className="card" style={{ textAlign: "center", padding: "44px 24px" }}>
          <h3 style={{ marginBottom: 6 }}>{t("resultsEmptyTitle")}</h3>
          <p className="card-sub" style={{ margin: "0 auto 16px", maxWidth: "42ch" }}>{t("resultsEmpty")}</p>
          {goConfigure && (
            <button className="btn btn-primary" onClick={goConfigure}>{t("resultsEmptyBtn")}</button>
          )}
        </div>
      </div></div>
    );
  }

  if (runResult.queued) {
    const email = (runResult._context && runResult._context.email) || "";
    return (
      <div className="main-inner single"><div>
        <div className="page-head"><h2>{t("resultsTitle")}</h2></div>
        <div className="card">
          <div className="card-head"><h3>{t("queuedTitle")}</h3></div>
          <p className="card-sub" style={{ margin: 0 }}>{tf("queuedBody", { email })}</p>
        </div>
      </div></div>
    );
  }

  if (!runResult.factible) {
    const causes = runResult.causes || [];
    return (
      <div className="main-inner single"><div>
        <div className="page-head"><h2>{t("resultsTitle")}</h2></div>
        <div className="card">
          <div className="card-head"><h3>{t("resultsInfeasibleTitle")}</h3></div>
          <p className="card-sub" style={{ marginBottom: 14 }}>{t("resultsInfeasibleBody")}</p>
          {causes.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: 18, color: "var(--ink-soft)", fontSize: 12.5, lineHeight: 1.8 }}>
              {causes.map((c, i) => (<li key={i}>{c}</li>))}
            </ul>
          ) : (
            <p className="card-sub" style={{ margin: 0 }}>{t("resultsInfeasibleFallback")}</p>
          )}
          <div className="modal-box" style={{ marginTop: 16, fontSize: 11.5 }}>{t("infeasibleDiagnosisNote")}</div>
        </div>
      </div></div>
    );
  }

  function downloadXlsx() {
    const wb = XLSX.utils.book_new();
    const header = ["Group", "Student ID", ...attributes, "Preference rank in group"];
    const rows = [header];
    runResult.groups.forEach((g) => {
      g.students.forEach((s) => {
        rows.push([
          g.group_name,
          s.id,
          ...attributes.map((a) => (s.attributes ? s.attributes[a] : "")),
          "",
        ]);
      });
    });
    const ws = XLSX.utils.aoa_to_sheet(rows);
    wb.SheetNames.push("Grupos");
    wb.Sheets["Grupos"] = ws;
    const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
    saveAs(new Blob([wbout], { type: "application/octet-stream" }), "mate_results.xlsx");
  }

  const outcome = runResult.preference_outcome || {};
  const totalOutcome = Object.values(outcome).reduce((a, b) => a + b, 0) || 1;
  const maxOutcome = Math.max(1, ...Object.values(outcome));
  const studentsPlaced = runResult.groups.reduce((a, g) => a + g.size, 0);

  const tiles = [
    [t("statGroupsFormed"), runResult.groups.length],
    [t("statStudentsPlaced"), studentsPlaced],
    [t("statSolveTime"), runResult.solve_time ? `${runResult.solve_time.toFixed(1)}s` : "?"],
  ];

  return (
    <div className="main-inner single"><div>
      <div className="page-head">
        <h2>{t("resultsTitle")}</h2>
        <p><span className={`badge badge-${statusClass(runResult.status)}`}>{runResult.status}</span></p>
      </div>

      <div className="card">
        <div className="tile-row">
          {tiles.map(([label, val]) => (
            <div className="tile" key={label}>
              <div className="tile-val mono">{val}</div>
              <div className="tile-label">{label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-head"><h3>{t("prefOutcomesTitle")}</h3></div>
        <p className="card-sub">{t("prefOutcomesSub")}</p>
        {Object.entries(outcome).map(([rank, count]) => (
          <div className="dist-row" key={rank}>
            <div className="dist-topic">{rank === "none" ? "none" : tf("choiceN", { n: rank })}</div>
            <div className="dist-bar-line">
              <div className="dist-track">
                <div className={`dist-fill ${rank === "none" ? "none" : "seg1"}`} style={{ width: `${(count / maxOutcome) * 100}%` }} />
              </div>
              <span className="dist-val">{count} ({Math.round((count / totalOutcome) * 100)}%)</span>
            </div>
          </div>
        ))}
        <div className="btn-row">
          <button className="btn" style={{ width: "100%", justifyContent: "center" }} onClick={downloadXlsx}>⬇ {t("downloadResults")}</button>
        </div>
      </div>

      <div className="card">
        <div className="card-head"><h3>{t("groupRoster")}</h3></div>
        {runResult.groups.map((g) => (
          <div className="group-card" key={g.group}>
            <div className="group-card-head">
              <h4>{g.group_name}</h4>
              <span className="group-card-count">{tf("studentsInGroup", { count: g.size })}</span>
            </div>
            <div className="group-student-list">
              {g.students.map((s) => (
                <span className="group-student-chip" key={s.id}>{s.id}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div></div>
  );
}
