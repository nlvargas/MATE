import React, { useState } from 'react';
import { render } from "react-dom";
import { CookiesProvider } from 'react-cookie';

import { I18nProvider, useI18n } from './i18n';
import CreateTemplate from './containers/CreateTemplate';
import UploadTemplate from './containers/UploadTemplate';
import CreateGroups from './containers/CreateGroups';
import Results from './containers/Results';
import HowItWorks from './containers/HowItWorks';

const STEP_SETUP = 1;
const STEP_UPLOAD = 2;
const STEP_CONFIGURE = 3;
const STEP_RESULTS = 4;

function WizardForm() {
  const { t, tf, lang, setLang } = useI18n();

  const [attributes, setAttributes] = useState([]);
  const [preferences, setPreferences] = useState([]);
  const [modules, setModules] = useState([]);
  const [options, setOptions] = useState({});
  const [preferencesNumber, setPreferencesNumber] = useState(0);
  const [students, setStudents] = useState([]);
  const [step, setStep] = useState(STEP_SETUP);
  const [runResult, setRunResult] = useState(null);
  const [howOpen, setHowOpen] = useState(false);

  const uploadUnlocked = true; // Setup has no hard requirements (all three sections are optional yes/no).
  const configureUnlocked = students.length > 0;
  const resultsUnlocked = runResult !== null;

  function goTo(target, unlocked) {
    if (unlocked) setStep(target);
  }

  function page() {
    switch (step) {
      case STEP_SETUP:
        return <CreateTemplate step={step} setStep={setStep}
                                attributes={attributes} setAttributes={setAttributes}
                                preferences={preferences} setPreferences={setPreferences}
                                preferencesNumber={preferencesNumber} setPreferencesNumber={setPreferencesNumber}
                                modules={modules} setModules={setModules} />;
      case STEP_UPLOAD:
        return <UploadTemplate step={step} setStep={setStep}
                                attributes={attributes} preferences={preferences} modules={modules}
                                preferencesNumber={preferencesNumber}
                                options={options} setOptions={setOptions}
                                students={students} setStudents={setStudents} />;
      case STEP_CONFIGURE:
        return <CreateGroups step={step} setStep={setStep}
                              attributes={attributes} preferences={preferences} modules={modules}
                              preferencesNumber={preferencesNumber}
                              options={options} students={students}
                              setRunResult={setRunResult} goResults={() => setStep(STEP_RESULTS)} />;
      case STEP_RESULTS:
        return <Results runResult={runResult} attributes={attributes}
                         goConfigure={configureUnlocked ? () => setStep(STEP_CONFIGURE) : undefined} />;
      default:
        return null;
    }
  }

  const steps = [
    { n: STEP_SETUP, label: t("step1_label"), desc: t("step1_desc"), unlocked: true },
    { n: STEP_UPLOAD, label: t("step2_label"), desc: t("step2_desc"), unlocked: uploadUnlocked },
    { n: STEP_CONFIGURE, label: t("step3_label"), desc: t("step3_desc"), unlocked: configureUnlocked },
    { n: STEP_RESULTS, label: t("results_tab"), desc: t("results_tab_desc"), unlocked: resultsUnlocked },
  ];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div className="brand-text"><b>{t("appName")}</b><span>{t("appTagline")}</span></div>
        </div>
        <div className="topbar-spacer" />
        <div className="lang-toggle" role="group" aria-label="Language">
          <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>EN</button>
          <button className={lang === "es" ? "active" : ""} onClick={() => setLang("es")}>ES</button>
        </div>
      </header>

      <div className="body-grid">
        <nav className="rail">
          {steps.map((s) => {
            const done = s.n === STEP_RESULTS ? !!runResult : step > s.n;
            return (
              <button
                key={s.n}
                className={`rail-step ${step === s.n ? "active" : ""} ${done ? "done" : ""}`}
                disabled={!s.unlocked}
                onClick={() => goTo(s.n, s.unlocked)}
              >
                <div className="rail-num">{done ? "✓" : s.n}</div>
                <div>
                  <div className="rail-label">{s.label}</div>
                  <div className="rail-desc">{s.desc}</div>
                </div>
              </button>
            );
          })}

          <div className="rail-foot mono" style={{ fontSize: 11, color: "var(--ink-faint)", padding: "10px" }}>
            {tf("railStudents", { count: students.length })}
          </div>

          <div className="rail-how">
            <button className="btn btn-ghost btn-sm" style={{ width: "100%", justifyContent: "center" }} onClick={() => setHowOpen(true)}>
              {t("how_tab")}
            </button>
          </div>
        </nav>

        <main className="main">
          {page()}
        </main>
      </div>

      {howOpen && <HowItWorks onClose={() => setHowOpen(false)} />}
    </div>
  );
}

export default function App() {
  return (
    <CookiesProvider>
      <I18nProvider>
        <WizardForm />
      </I18nProvider>
    </CookiesProvider>
  );
}

const container = document.getElementById("app");
document.body.classList.add("mate-body");
render(<App />, container);
