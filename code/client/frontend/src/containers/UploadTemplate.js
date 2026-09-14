import React, { useState, useMemo } from 'react';
import axios from 'axios';
import { useI18n } from '../i18n';
import Spinner from '../components/Spinner';

// "Upload roster" step. Posts the filled-in template to /dev/upload/, then
// shows a summary built entirely from what that endpoint actually returned
// (options = per-attribute value counts, students = full roster) -- no
// separate summary endpoint needed.
export default function UploadTemplate(props) {
  const { step, setStep, setOptions, setStudents, options, students,
          attributes, modules, preferences, preferencesNumber } = props;
  const { t, tf } = useI18n();
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  function onFileUpload() {
    // Plain Promise chain, not async/await: the babel config here has no
    // regenerator-runtime polyfill, so a compiled async function throws
    // "regeneratorRuntime is not defined" the moment it hits an await.
    if (!selectedFile) return;
    const formData = new FormData();
    formData.append("attributes", attributes);
    formData.append("modules", modules);
    formData.append("preferencesNumber", preferencesNumber);
    formData.append("file", selectedFile, selectedFile.name);
    setUploading(true);
    setError(null);
    axios.post("/dev/upload/", formData)
      .then((response) => {
        setOptions(JSON.parse(response.data.a));
        setStudents(JSON.parse(response.data.students));
      })
      .catch((err) => {
        setError(t("uploadError"));
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => setUploading(false));
  }

  const sectionCounts = useMemo(() => {
    if (!modules.length || !students.length) return null;
    const counts = {};
    modules.forEach((m, i) => {
      counts[m] = students.filter((s) => Number(s.disponibilities[i]) === 1).length;
    });
    return counts;
  }, [modules, students]);

  const prefMatrix = useMemo(() => {
    if (!preferences.length || !students.length || !preferencesNumber) return null;
    const matrix = {};
    preferences.forEach((p) => { matrix[p] = Array(preferencesNumber).fill(0); });
    students.forEach((s) => {
      const prefs = s.modelPreferences || {};
      for (let rank = 1; rank <= preferencesNumber; rank++) {
        const topic = prefs[String(rank)];
        if (topic && matrix[topic]) matrix[topic][rank - 1] += 1;
      }
    });
    return matrix;
  }, [preferences, preferencesNumber, students]);

  const maxSectionCount = sectionCounts ? Math.max(1, ...Object.values(sectionCounts)) : 1;

  return (
    <div className="main-inner single">
      <div>
        <div className="page-head">
          <h2>{t("uploadTitle")}</h2>
          <p>{t("uploadHelp")}</p>
        </div>

        <div className="card">
          <div className="dropzone">
            <b>{t("chooseFile")}</b>
            <p>{selectedFile ? selectedFile.name : t("noFileChosen")}</p>
            <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
              <label className="btn btn-primary" style={{ cursor: "pointer" }}>
                {t("chooseFile")}
                <input type="file" accept=".xlsx" style={{ display: "none" }}
                       onChange={(e) => setSelectedFile(e.target.files[0] || null)} />
              </label>
              <button className="btn" disabled={uploading || !selectedFile} onClick={onFileUpload}>
                {uploading ? <Spinner label={t("uploading")} /> : t("uploadButton")}
              </button>
            </div>
          </div>
          {error && <div className="run-status warn">{error}</div>}
          {students.length > 0 && !uploading && (
            <div className="run-status good">✓ {t("uploadSuccess")}</div>
          )}
        </div>

        {students.length > 0 && (
          <div className="card">
            <div className="card-head"><h3>{t("rosterSummary")}</h3></div>
            <p className="card-sub">{tf("studentsUploaded", { count: students.length })}</p>

            {options && Object.keys(options).map((attr) => (
              <div className="pill-group" key={attr} style={{ marginBottom: 14 }}>
                <div className="dist-topic">{tf("byAttribute", { attribute: attr })}</div>
                <div className="chip-row" style={{ marginBottom: 0 }}>
                  {Object.entries(options[attr]).map(([value, count]) => (
                    <span className="pill" key={value}>{value} · {count}</span>
                  ))}
                </div>
              </div>
            ))}

            {sectionCounts && (
              <div className="pill-group" style={{ marginBottom: 14 }}>
                <div className="dist-topic">{t("bySection")}</div>
                <div className="chip-row" style={{ marginBottom: 0 }}>
                  {Object.entries(sectionCounts).map(([mod, count]) => (
                    <span className="pill" key={mod}>{mod} · {count}</span>
                  ))}
                </div>
              </div>
            )}

            {prefMatrix && (
              <div>
                <div className="dist-topic">{t("preferenceDistribution")}</div>
                <div className="dist-legend">
                  <span><span className="dist-swatch" style={{ background: "var(--accent)" }} />{tf("choiceN", { n: 1 })}</span>
                  <span><span className="dist-swatch" style={{ background: "var(--accent-2)" }} />{tf("choiceN", { n: 2 })}</span>
                </div>
                {Object.entries(prefMatrix).map(([topic, counts]) => (
                  <div className="dist-row" key={topic}>
                    <div className="dist-topic">{topic}</div>
                    {counts.map((c, i) => (
                      <div className="dist-bar-line" key={i}>
                        <div className="dist-track">
                          <div className={`dist-fill ${i === 0 ? "seg1" : "seg2"}`} style={{ width: `${(c / maxSectionCount) * 100}%` }} />
                        </div>
                        <span className="dist-val">{tf("choiceN", { n: i + 1 })} · {c}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="nav-row">
          <button className="btn" onClick={() => setStep(step - 1)}>{t("back")}</button>
          <button className="btn btn-primary" disabled={students.length === 0} onClick={() => setStep(step + 1)}>{t("next")}</button>
        </div>
      </div>
    </div>
  );
}
