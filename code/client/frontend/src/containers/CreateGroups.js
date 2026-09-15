import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useCookies } from 'react-cookie';
import { useI18n } from '../i18n';
import DualSlider from '../components/DualSlider';
import SingleSlider from '../components/SingleSlider';
import InfoTip from '../components/InfoTip';
import Spinner from '../components/Spinner';

export default function CreateGroups(props) {
  const { step, setStep, attributes, preferences, modules,
          preferencesNumber, options, students, setRunResult, goResults, auth } = props;
  const { t, tf } = useI18n();

  const [cookies, setCookie] = useCookies(['groupsNumber', 'minStudents', 'maxStudents', 'email', 'maxSolveSeconds']);
  const [cookiesLoaded, setCookiesLoaded] = useState(false);

  const totalStudents = students.length;
  const [groupsNumber, setGroupsNumber] = useState(Math.max(1, Math.min(4, totalStudents)));
  const [minStudents, setMinStudents] = useState(Math.max(1, Math.floor(totalStudents / Math.max(1, groupsNumber)) - 1));
  const [maxStudents, setMaxStudents] = useState(Math.max(1, Math.ceil(totalStudents / Math.max(1, groupsNumber)) + 1));
  const [email, setEmail] = useState("");
  // Bounds and starting value for the max-solve-time slider below, read
  // from window.__MATE_CONFIG__ (see frontend/views.py's index()) instead
  // of hardcoding a copy here, for the same reason syncMaxStudents further
  // down is read that way: this can never drift from the clamp
  // backend/views.py's run_model() actually enforces server-side.
  const syncTmaxMin = window.__MATE_CONFIG__?.syncTmaxMinSeconds ?? 5;
  const syncTmaxMax = window.__MATE_CONFIG__?.syncTmaxMaxSeconds ?? 25;
  const syncTmaxDefault = window.__MATE_CONFIG__?.syncTmaxDefaultSeconds ?? 20;
  const [maxSolveSeconds, setMaxSolveSeconds] = useState(syncTmaxDefault);
  const [sameDay, setSameDay] = useState(false);
  const [usedPreferences, setUsedPreferences] = useState(preferences.length);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);

  useEffect(() => {
    if (cookies && !cookiesLoaded) {
      if (cookies.groupsNumber) setGroupsNumber(Math.min(parseInt(cookies.groupsNumber), Math.max(1, totalStudents)));
      if (cookies.minStudents) setMinStudents(parseInt(cookies.minStudents));
      if (cookies.maxStudents) setMaxStudents(parseInt(cookies.maxStudents));
      if (cookies.email) setEmail(cookies.email);
      if (cookies.maxSolveSeconds) {
        const v = parseInt(cookies.maxSolveSeconds);
        if (!Number.isNaN(v)) setMaxSolveSeconds(Math.min(Math.max(v, syncTmaxMin), syncTmaxMax));
      }
      setCookiesLoaded(true);
    }
    // totalStudents (read above) is intentionally not a dep: this effect
    // is a one-shot "apply saved cookies once" guarded by !cookiesLoaded,
    // so it can never run again after that point regardless of what else
    // (including totalStudents) changes -- adding it would just be a dep
    // that can never actually cause a second run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cookies, cookiesLoaded]);

  // Dynamic outer bounds for the group-size slider: a group obviously can't
  // exceed what's left over once every other group has at least 1 student.
  const sliderMax = Math.max(1, totalStudents - (Math.max(1, groupsNumber) - 1));
  useEffect(() => {
    if (minStudents > sliderMax) setMinStudents(sliderMax);
    if (maxStudents > sliderMax) setMaxStudents(sliderMax);
    if (minStudents > maxStudents) setMinStudents(maxStudents);
    // minStudents/maxStudents are genuine deps (each setState call above is
    // already individually guarded, so including them is safe -- a
    // correction triggers one more run that then finds every condition
    // false) -- without them, a value set out-of-range by some other path
    // (e.g. the cookie-restore effect above) while sliderMax happens not to
    // change would never get re-clamped.
  }, [sliderMax, minStudents, maxStudents]);

  function onGroupsNumberChange(v) {
    const clamped = Math.max(1, Math.min(v, Math.max(1, totalStudents)));
    setGroupsNumber(clamped);
  }

  // -------------------- Attribute bounds --------------------
  const [bounds, setBounds] = useState({});
  useEffect(() => {
    // Only fills in bounds for attribute values that don't have one yet --
    // never overwrites a bound the user already customized. setBounds is
    // now called only when something was actually added (`changed`),
    // instead of unconditionally with a fresh { ...bounds } object every
    // run -- that's what let `bounds` join the deps below without an
    // infinite loop (a fresh-but-identical object every run would have
    // meant "bounds changed" -> re-run -> "bounds changed" -> ... forever).
    let changed = false;
    const b = { ...bounds };
    Object.keys(options || {}).forEach((attr) => {
      Object.keys(options[attr]).forEach((value) => {
        if (!b[value]) { b[value] = { min: 0, max: totalStudents, solo: false }; changed = true; }
      });
    });
    if (changed) setBounds(b);
  }, [options, bounds, totalStudents]);

  function updateBound(value, patch) {
    setBounds((prev) => ({ ...prev, [value]: { ...prev[value], ...patch } }));
  }

  // -------------------- Section rules --------------------
  const [capacity, setCapacity] = useState({});
  const [fixedDay, setFixedDay] = useState({});
  useEffect(() => {
    // Same "only touch what's missing, only setState if something actually
    // changed" shape as the bounds-seeding effect above, and for the same
    // reason: it's what lets capacity/fixedDay/totalStudents safely join
    // the deps instead of needing to be suppressed to avoid a fresh-object-
    // every-run infinite loop.
    let changed = false;
    const cap = { ...capacity };
    const fd = { ...fixedDay };
    modules.forEach((m) => {
      if (cap[m] === undefined) { cap[m] = totalStudents; changed = true; }
      if (!fd[m]) {
        fd[m] = {};
        preferences.forEach((p) => { fd[m][p] = false; });
        changed = true;
      }
    });
    if (changed) {
      setCapacity(cap);
      setFixedDay(fd);
    }
  }, [modules, preferences, capacity, fixedDay, totalStudents]);

  // -------------------- Topic bounds --------------------
  const [prefsBounds, setPrefsBounds] = useState({});
  useEffect(() => {
    // Same shape as the two seeding effects above.
    let changed = false;
    const pb = { ...prefsBounds };
    preferences.forEach((p) => {
      if (!pb[p]) { pb[p] = { min: 0, max: groupsNumber }; changed = true; }
    });
    if (changed) setPrefsBounds(pb);
  }, [preferences, prefsBounds, groupsNumber]);

  function updatePrefBound(pref, patch) {
    setPrefsBounds((prev) => ({ ...prev, [pref]: { ...prev[pref], ...patch } }));
  }

  // -------------------- Client-side feasibility checks --------------------
  const issues = useMemo(() => {
    const found = [];
    if (totalStudents / groupsNumber > maxStudents || totalStudents / groupsNumber < minStudents) {
      found.push(tf("causeGroupSize", { students: totalStudents, groups: groupsNumber, min: minStudents, max: maxStudents }));
    }
    Object.entries(bounds).forEach(([value, b]) => {
      if (!b.solo && b.min > maxStudents) {
        found.push(`${value}: min (${b.min}) > ${t("attributeMax")} (${maxStudents})`);
      }
    });
    if (preferences.length) {
      const minSum = preferences.reduce((acc, p) => acc + ((prefsBounds[p] && prefsBounds[p].min) || 0), 0);
      const maxSum = preferences.reduce((acc, p) => acc + ((prefsBounds[p] && prefsBounds[p].max) || groupsNumber), 0);
      if (minSum > groupsNumber) found.push(t("causeTopic"));
      if (maxSum < groupsNumber) found.push(t("causeTopic"));
    }
    // students[*].disponibilities is a plain array positionally aligned
    // with `modules` (index i = availability for modules[i], same
    // convention UploadTemplate.js's per-module availability count uses)
    // -- so the module's own forEach index below gives its position for
    // free. The previous `modules.indexOf(m)` re-derived that same index
    // from scratch on every single student (inside the .filter()
    // callback), turning an O(modules x students) scan into
    // O(modules^2 x students).
    modules.forEach((m, i) => {
      const avail = students.filter((s) => Number(s.disponibilities[i]) === 1).length;
      if (capacity[m] !== undefined && capacity[m] < minStudents) found.push(t("causeSection"));
      if (avail < minStudents) found.push(t("causeSection"));
    });
    return found;
  }, [bounds, prefsBounds, capacity, groupsNumber, minStudents, maxStudents, totalStudents, preferences, modules, students, t, tf]);

  function runModelRequest() {
    // Plain Promise chain, not async/await: the babel config here has no
    // regenerator-runtime polyfill, so a compiled async function throws
    // "regeneratorRuntime is not defined" the moment it hits an await.
    if (issues.length > 0) return;
    setCookie('groupsNumber', groupsNumber, { path: '/' });
    setCookie('minStudents', minStudents, { path: '/' });
    setCookie('maxStudents', maxStudents, { path: '/' });
    setCookie('email', email, { path: '/' });
    setCookie('maxSolveSeconds', maxSolveSeconds, { path: '/' });

    const body = {
      attributes, preferences, groupsNumber, minStudents, maxStudents,
      bounds, students, capacity, preferencesNumber, options, prefsBounds,
      // tmax is minutes and only means anything on the async/cluster path
      // (a Slurm job budget) -- maxSolveSeconds is the new, unambiguous
      // seconds field the sync path actually reads (views.run_model());
      // see project/settings.py's SYNC_SOLVE_TMAX_MIN/MAX_SECONDS comment
      // for why the server still clamps it regardless of what's sent here.
      usedPreferences, modules, email, tmax: 60, maxSolveSeconds, sameDay, fixedDay,
    };

    setRunning(true);
    setRunError(null);
    setRunResult(null);
    axios.post('/dev/run_model/', body)
      .then((response) => {
        setRunResult({
          ...response.data,
          _context: {
            students: totalStudents, groups: groupsNumber, min: minStudents, max: maxStudents, email,
            // Kept so Results.js can re-run the same roster/settings through
            // /dev/sensitivity/ on demand (see its Sensitivity card) without
            // the parent needing to separately track or re-derive the body
            // this run already sent -- the sensitivity analysis is defined
            // as "what if one bound on *this* request were relaxed", so it
            // has to be the exact same body, not a freshly reconstructed one.
            requestBody: body,
          },
        });
        goResults();
      })
      .catch((err) => {
        // The cluster-submission gate (backend/msft_auth.py) answers with
        // this shape specifically so the UI can point at sign-in instead
        // of showing a generic failure -- everything else still falls
        // back to the generic message.
        if (err.response && err.response.status === 403 && err.response.data && err.response.data.error === "auth_required") {
          setRunError(t("clusterAuthRequired"));
        } else {
          setRunError(t("uploadError"));
        }
        // eslint-disable-next-line no-console
        console.error(err);
      })
      .finally(() => setRunning(false));
  }

  // Small problems solve in-request; larger rosters go to the cluster queue.
  // This is purely a UI indicator (see the "Sync"/"Async" pills below) --
  // the backend decides for itself which path to actually take, based on
  // its own SYNC_SOLVE_MAX_STUDENTS setting (project/settings.py, default
  // 300, overridable via MATE_SYNC_MAX_STUDENTS). Read from
  // window.__MATE_CONFIG__ (injected server-side in index.html -- see
  // frontend/views.py's index()) instead of a second hardcoded copy of
  // that number, so this can never silently drift from what the backend
  // will actually do; the fallback below only matters if this page were
  // ever served without going through that view.
  const syncMaxStudents = window.__MATE_CONFIG__?.syncMaxStudents ?? 300;
  const execPath = totalStudents > syncMaxStudents ? "async" : "sync";

  return (
    <div className="main-inner">
      <div>
        <div className="page-head">
          <h2>{t("configureTitle")}</h2>
          <p>{t("configureHelp")}</p>
        </div>

        <div className="card">
          <div className="card-head"><h3>{t("groupSizeLabel")}</h3></div>
          <p className="card-sub">{t("groupSizeSub")}</p>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <label className="field-label">{t("groupsNumberLabel")}</label>
            <input type="number" className="num-inline" min={1} max={Math.max(1, totalStudents)}
                   value={groupsNumber} onChange={(e) => onGroupsNumberChange(parseInt(e.target.value) || 1)} />
          </div>
          <div className="opt-count" style={{ marginBottom: 2 }}>{t("perGroup")}</div>
          <DualSlider min={1} max={sliderMax} lo={minStudents} hi={maxStudents}
                      onChangeLo={setMinStudents} onChangeHi={setMaxStudents} />

          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 26 }}>
            <label className="field-label">{t("emailLabel")}</label>
            <input type="email" style={{ width: 220 }} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
        </div>

        {attributes.length > 0 && Object.keys(options || {}).length > 0 && (
          <div className="card">
            <div className="card-head"><h3>{t("attributeBoundsTitle")}</h3></div>
            <p className="card-sub">{t("attributeBoundsSub")}</p>
            {Object.keys(options).map((attr) => (
              Object.keys(options[attr]).map((value) => {
                const b = bounds[value] || { min: 0, max: totalStudents, solo: false };
                const count = options[attr][value];
                return (
                  <div className="opt-row" key={value}>
                    <div className="opt-top">
                      <div><span className="opt-name">{value}</span> <span className="opt-count">· {attr}</span></div>
                      <span className="opt-count">{count} {t("markedThis")}</span>
                    </div>
                    <DualSlider min={0} max={Math.max(1, totalStudents)} lo={b.min} hi={b.max === null ? totalStudents : b.max}
                                onChangeLo={(v) => updateBound(value, { min: v })}
                                onChangeHi={(v) => updateBound(value, { max: v })} />
                    <div className="solo-line">
                      <label className="switch" style={{ width: 30, height: 18 }}>
                        <input type="checkbox" checked={b.solo} onChange={(e) => updateBound(value, { solo: e.target.checked })} />
                        <span className="track" />
                      </label>
                      <label>{t("soloToggle")}</label>
                      <InfoTip text={t("soloTooltip")} />
                    </div>
                  </div>
                );
              })
            ))}
          </div>
        )}

        {modules.length > 0 && (
          <div className="card">
            <div className="card-head"><h3>{t("sectionsRulesTitle")}</h3></div>
            <p className="card-sub">{t("sectionsRulesSub")}</p>
            {modules.map((mod) => (
              <div className="opt-row" key={mod}>
                <div className="opt-top">
                  <span className="opt-name">{mod}</span>
                  <span>
                    {t("sectionCapacity")}:{" "}
                    <input type="number" className="num-inline" value={capacity[mod] ?? totalStudents}
                           onChange={(e) => setCapacity((prev) => ({ ...prev, [mod]: parseInt(e.target.value) || 0 }))} />
                  </span>
                </div>
                {preferences.length > 0 && (
                  <>
                    <p className="t-sub" style={{ marginTop: 8, marginBottom: 4 }}>{t("fixedSectionToggle")}</p>
                    {preferences.map((p) => (
                      <div className="toggle-row" key={p} style={{ paddingLeft: 4, marginTop: 4 }}>
                        <span className="t-sub">{p}</span>
                        <label className="switch">
                          <input type="checkbox" checked={!!(fixedDay[mod] && fixedDay[mod][p])}
                                 onChange={(e) => setFixedDay((prev) => ({ ...prev, [mod]: { ...prev[mod], [p]: e.target.checked } }))} />
                          <span className="track" />
                        </label>
                      </div>
                    ))}
                  </>
                )}
              </div>
            ))}
            <div className="toggle-row" style={{ marginTop: 8, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
              <span style={{ fontWeight: 500, fontSize: 12.5 }}>{t("sameSectionToggle")}<InfoTip text={t("sameSectionTooltip")} /></span>
              <label className="switch">
                <input type="checkbox" checked={sameDay} onChange={(e) => setSameDay(e.target.checked)} />
                <span className="track" />
              </label>
            </div>
          </div>
        )}

        {preferences.length > 0 && (
          <div className="card">
            <div className="card-head"><h3>{t("topicsRulesTitle")}</h3></div>
            <p className="card-sub">{t("topicsRulesSub")}</p>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
              <label className="field-label">{t("topicsUsedLabel")}</label>
              <InfoTip text={t("topicsUsedHelp")} />
              <select className="num-inline" value={usedPreferences} onChange={(e) => setUsedPreferences(Math.min(parseInt(e.target.value), preferences.length))}>
                {[...Array(preferences.length + 1).keys()].map((n) => (<option key={n} value={n}>{n}</option>))}
              </select>
            </div>
            {preferences.map((p) => {
              const pb = prefsBounds[p] || { min: 0, max: groupsNumber };
              return (
                <div className="opt-row" key={p}>
                  <div className="opt-top"><span className="opt-name">{p}</span></div>
                  <DualSlider min={0} max={Math.max(1, groupsNumber)} lo={pb.min} hi={pb.max === null ? groupsNumber : pb.max}
                              onChangeLo={(v) => updatePrefBound(p, { min: v })}
                              onChangeHi={(v) => updatePrefBound(p, { max: v })} />
                </div>
              );
            })}
          </div>
        )}

        <div className="nav-row">
          <button className="btn" onClick={() => setStep(step - 1)}>{t("back")}</button>
          <span />
        </div>
      </div>

      <div className="summary">
        <div className="card">
          <div className="card-head"><h3>{t("validationTitle")}</h3></div>
          <div className="stat-line"><span className="stat-label">{t("statStudents")}</span><span className="stat-val">{totalStudents}</span></div>
          <div className="stat-line"><span className="stat-label">{t("statGroups")}</span><span className="stat-val">{groupsNumber}</span></div>
          <div className="stat-line"><span className="stat-label">{t("statSize")}</span><span className="stat-val">{minStudents}–{maxStudents}</span></div>
          <div className="stat-line"><span className="stat-label">{t("statAttrs")}</span><span className="stat-val">{attributes.length}</span></div>
          <div className="stat-line"><span className="stat-label">{t("statTopics")}</span><span className="stat-val">{preferences.length}</span></div>
          <div className="stat-line"><span className="stat-label">{t("statSections")}</span><span className="stat-val">{modules.length}</span></div>
          <div style={{ marginTop: 12 }}>
            {issues.length === 0 ? (
              <span className="badge badge-good"><span className="badge-dot" />{t("feasibleBadge")}</span>
            ) : (
              <>
                <span className="badge badge-warn"><span className="badge-dot" />{issues.length} {t("issuesBadge")}</span>
                <ul className="issues-list">
                  {issues.map((msg, idx) => (<li key={idx}>{msg}</li>))}
                </ul>
              </>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>{t("execTitle")}</h3></div>
          <p className="card-sub" style={{ marginBottom: 8 }}>{t("execSub")}</p>
          <div className="exec-toggle">
            <div className={`exec-opt ${execPath === "sync" ? "active" : ""}`}>{t("execSync")}</div>
            <div className={`exec-opt ${execPath === "async" ? "active" : ""}`}>{t("execAsync")}</div>
          </div>
          {execPath === "sync" && (
            <div style={{ marginTop: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <label className="field-label">{t("maxSolveTimeLabel")}</label>
                <InfoTip text={t("maxSolveTimeTooltip")} />
              </div>
              <SingleSlider min={syncTmaxMin} max={syncTmaxMax} step={1}
                            value={maxSolveSeconds} onChange={setMaxSolveSeconds} suffix="s" />
            </div>
          )}
          {execPath === "async" && !auth.authenticated && (
            <div className="run-status warn" style={{ marginBottom: 10 }}>
              {auth.configured ? t("clusterAuthRequired") : t("clusterAuthNotConfigured")}
              {auth.configured && (
                <div style={{ marginTop: 6 }}>
                  <a className="btn btn-ghost btn-sm" href="/dev/auth/login">{t("signInMicrosoft")}</a>
                </div>
              )}
            </div>
          )}
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 14 }}
                  disabled={running || issues.length > 0 || (execPath === "async" && !auth.authenticated)}
                  onClick={runModelRequest}>
            {running ? <Spinner label={t("running")} /> : t("runButton")}
          </button>
          {runError && (
            <div className="run-status warn">{runError}</div>
          )}
          <div className="solver-line">⚙ {t("solverLine")}</div>
        </div>
      </div>
    </div>
  );
}
