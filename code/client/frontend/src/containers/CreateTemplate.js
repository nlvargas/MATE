import React, { useState, useEffect } from 'react';
import XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import { useCookies } from 'react-cookie';
import { useI18n } from '../i18n';

// "Setup" step (was a bare form; same prop contract as before, restyled to
// match the validated mockup: toggle switches, chip lists, add-row inputs).
// Defines which attributes/sections/topics exist before any roster is
// uploaded -- these three lists drive both the downloadable roster template
// and (later) the optimizer's parameter shape, so nothing here is cosmetic.
export default function CreateTemplate(props) {
  const { step, setStep, attributes, setAttributes,
          preferences, setPreferences, modules, setModules,
          preferencesNumber, setPreferencesNumber } = props;
  const { t } = useI18n();
  const [cookies, setCookie] = useCookies(
    ['attributes', 'preferences', 'modules', 'preferencesNumber']
  );
  const [haveAttributes, setHaveAttributes] = useState(false);
  const [havePreferences, setHavePreferences] = useState(false);
  const [haveModules, setHaveModules] = useState(false);
  const [newAttribute, setNewAttribute] = useState("");
  const [newPreference, setNewPreference] = useState("");
  const [newModule, setNewModule] = useState("");
  const [showLink, setShowLink] = useState(false);
  const [wbout, setWbout] = useState("");
  const [cookiesLoaded, setCookiesLoaded] = useState(false);
  const [preferencesNumberOptions, setPreferencesNumberOptions] = useState([...Array(preferencesNumber + 1).keys()]);

  useEffect(() => {
    if (cookies && !cookiesLoaded) {
      if (cookies.attributes && cookies.attributes.length) {
        setAttributes(cookies.attributes);
        setHaveAttributes(true);
      }
      if (cookies.preferences && cookies.preferences.length) {
        setPreferences(cookies.preferences);
        setPreferencesNumberOptions([...Array(cookies.preferences.length + 1).keys()]);
        setHavePreferences(true);
      }
      if (cookies.preferencesNumber) {
        setPreferencesNumber(parseInt(cookies.preferencesNumber));
      }
      if (cookies.modules && cookies.modules.length) {
        setModules(cookies.modules);
        setHaveModules(true);
      }
      setCookiesLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cookies, cookiesLoaded]);

  function addAttribute() {
    if (!newAttribute.trim()) return;
    setAttributes(attributes.concat(newAttribute.trim()));
    setNewAttribute("");
  }

  function addPreference() {
    if (!newPreference.trim()) return;
    setPreferences(preferences.concat(newPreference.trim()));
    setNewPreference("");
    setPreferencesNumberOptions(preferencesNumberOptions.concat(preferencesNumberOptions.length));
  }

  function addModule() {
    if (!newModule.trim()) return;
    setModules(modules.concat(newModule.trim()));
    setNewModule("");
  }

  function onEnter(fn) {
    return (e) => { if (e.key === "Enter") fn(); };
  }

  function removeAt(list, setList, index) {
    setList(list.filter((_, i) => i !== index));
  }

  function removePreference(index) {
    removeAt(preferences, setPreferences, index);
    setPreferencesNumberOptions(preferencesNumberOptions.slice(0, -1));
    if (preferencesNumber > preferences.length - 1) {
      setPreferencesNumber(Math.max(0, preferences.length - 1));
    }
  }

  function generateTemplate() {
    const wb = XLSX.utils.book_new();
    wb.SheetNames.push("Alumnos");
    const r = ["Nombre"];
    attributes.forEach((attr) => r.push(attr));
    modules.forEach((mod) => r.push("Disponibilidad " + mod));
    for (let p = 1; p <= preferencesNumber; p++) r.push("Preferencia " + p);
    const ws = XLSX.utils.aoa_to_sheet([r]);
    wb.Sheets["Alumnos"] = ws;
    setWbout(XLSX.write(wb, { bookType: 'xlsx', type: 'binary' }));
    setShowLink(true);
  }

  function downloadTemplate() {
    function s2ab(s) {
      const buf = new ArrayBuffer(s.length);
      const view = new Uint8Array(buf);
      for (let i = 0; i < s.length; i++) view[i] = s.charCodeAt(i) & 0xFF;
      return buf;
    }
    saveAs(new Blob([s2ab(wbout)], { type: "application/octet-stream" }), 'template.xlsx');
  }

  function next() {
    setCookie('attributes', attributes, { path: '/' });
    setCookie('modules', modules, { path: '/' });
    setCookie('preferences', preferences, { path: '/' });
    setCookie('preferencesNumber', preferencesNumber, { path: '/' });
    setStep(step + 1);
  }

  function Switch({ checked, onChange }) {
    return (
      <label className="switch">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="track" />
      </label>
    );
  }

  function ChipList({ items, onRemove, emptyLabel }) {
    if (!items.length) return <div className="empty-hint">{emptyLabel}</div>;
    return (
      <div className="chip-row">
        {items.map((item, index) => (
          <div className="chip" key={index}>
            {item}
            <button onClick={() => onRemove(index)} aria-label={t("remove")}>&times;</button>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="main-inner single"><div>
      <div className="page-head">
        <h2>{t("setupTitle")}</h2>
        <p>{t("setupIntro")}</p>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>{t("attributesTitle")}</h3>
          <div className="toggle-row" style={{ gap: 8 }}>
            <span className="t-sub" style={{ maxWidth: 220, textAlign: "right" }}>{t("attributesQuestion")}</span>
            <Switch checked={haveAttributes} onChange={setHaveAttributes} />
          </div>
        </div>
        <p className="card-sub">{t("attributesHelp")}</p>
        {haveAttributes && (
          <div>
            <ChipList items={attributes} onRemove={(i) => removeAt(attributes, setAttributes, i)} emptyLabel={t("emptyAttributes")} />
            <div className="add-row">
              <input type="text" value={newAttribute} placeholder={t("newAttributePlaceholder")}
                     onKeyPress={onEnter(addAttribute)} onChange={(e) => setNewAttribute(e.target.value)} />
              <button className="btn" onClick={addAttribute}>{t("addAttribute")}</button>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <h3>{t("sectionsTitle")}</h3>
          <div className="toggle-row" style={{ gap: 8 }}>
            <span className="t-sub" style={{ maxWidth: 220, textAlign: "right" }}>{t("sectionsQuestion")}</span>
            <Switch checked={haveModules} onChange={setHaveModules} />
          </div>
        </div>
        <p className="card-sub">{t("sectionsHelp")}</p>
        {haveModules && (
          <div>
            <ChipList items={modules} onRemove={(i) => removeAt(modules, setModules, i)} emptyLabel={t("emptySections")} />
            <div className="add-row">
              <input type="text" value={newModule} placeholder={t("newSectionPlaceholder")}
                     onKeyPress={onEnter(addModule)} onChange={(e) => setNewModule(e.target.value)} />
              <button className="btn" onClick={addModule}>{t("addSection")}</button>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <h3>{t("topicsTitle")}</h3>
          <div className="toggle-row" style={{ gap: 8 }}>
            <span className="t-sub" style={{ maxWidth: 220, textAlign: "right" }}>{t("topicsQuestion")}</span>
            <Switch checked={havePreferences} onChange={setHavePreferences} />
          </div>
        </div>
        <p className="card-sub">{t("topicsHelp")}</p>
        {havePreferences && (
          <div>
            <ChipList items={preferences} onRemove={removePreference} emptyLabel={t("emptyTopics")} />
            <div className="add-row">
              <input type="text" value={newPreference} placeholder={t("newTopicPlaceholder")}
                     onKeyPress={onEnter(addPreference)} onChange={(e) => setNewPreference(e.target.value)} />
              <button className="btn" onClick={addPreference}>{t("addTopic")}</button>
            </div>
            <div className="solo-line">
              <label>{t("topicsRankLabel")}</label>
              <select className="num-inline" value={preferencesNumber} onChange={(e) => setPreferencesNumber(parseInt(e.target.value))}>
                {preferencesNumberOptions.map((x) => (<option key={x} value={x}>{x}</option>))}
              </select>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <div className="btn-row" style={{ marginTop: 0 }}>
          <button className="btn" onClick={generateTemplate}>{t("generateTemplate")}</button>
          {showLink && <button className="btn" onClick={downloadTemplate}>{t("downloadTemplate")}</button>}
        </div>
      </div>

      <div className="nav-row">
        <button className="btn" disabled>{t("back")}</button>
        <button className="btn btn-primary" onClick={next}>{t("next")}</button>
      </div>
    </div></div>
  );
}
