import React from 'react';
import { useI18n } from '../i18n';

/**
 * A dual-thumb range slider: two overlapping native <input type="range">
 * elements (pointer-events disabled on the input itself, re-enabled only on
 * the thumb via CSS in theme.css) plus a separate track/fill div pair drawn
 * under them for the visual bar. The input's own box is sized to exactly
 * match the thumb (see .dslider-input in theme.css) so the browser
 * centers the native track inside it -- no manual pixel-offset hacks that
 * drift between browsers. Class names (.dslider*) match the validated
 * mate-redesign mockup 1:1.
 *
 * `label` is what a screen reader announces for each thumb ("Minimum
 * <label>" / "Maximum <label>") -- without it, both native range inputs
 * announce as bare, indistinguishable "slider"s, since this component
 * carries no visible text label of its own (the two callers-provided pill
 * texts, e.g. an attribute value or topic name, sit next to the slider in
 * the DOM but aren't programmatically associated with these inputs).
 * Optional so existing call sites don't break, but every call site in this
 * app passes one.
 */
export default function DualSlider({ min, max, step = 1, lo, hi, onChangeLo, onChangeHi, suffix = "", formatValue, label }) {
  const { t } = useI18n();
  const range = Math.max(1, max - min);
  const pct = (v) => ((v - min) / range) * 100;
  const fmt = formatValue || ((v) => `${v}${suffix}`);
  const loLabel = label ? `${t("sliderMinLabel")} ${label}` : undefined;
  const hiLabel = label ? `${t("sliderMaxLabel")} ${label}` : undefined;

  function handleLo(e) {
    const v = Math.min(Number(e.target.value), hi - step >= min ? hi - step : hi);
    onChangeLo(Math.min(v, hi));
  }

  function handleHi(e) {
    const v = Math.max(Number(e.target.value), lo + step <= max ? lo + step : lo);
    onChangeHi(Math.max(v, lo));
  }

  return (
    <div className="dslider">
      <div className="dslider-track">
        <div
          className="dslider-fill"
          style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }}
        />
      </div>
      <input
        className="dslider-input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={lo}
        onChange={handleLo}
        aria-label={loLabel}
      />
      <input
        className="dslider-input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={hi}
        onChange={handleHi}
        aria-label={hiLabel}
      />
      <div className="dslider-label" style={{ left: `${pct(lo)}%` }}>
        {fmt(lo)}
      </div>
      <div className="dslider-label" style={{ left: `${pct(hi)}%` }}>
        {fmt(hi)}
      </div>
    </div>
  );
}
