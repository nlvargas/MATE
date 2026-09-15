import React from 'react';

/**
 * Single-thumb sibling of DualSlider (see that component's comment for why
 * the track/fill/input layering looks the way it does -- same CSS classes,
 * just one <input type="range"> instead of two, so the shared .dslider*
 * rules in theme.css already apply as-is).
 */
export default function SingleSlider({ min, max, step = 1, value, onChange, suffix = "", formatValue }) {
  const range = Math.max(1, max - min);
  const pct = (v) => ((v - min) / range) * 100;
  const fmt = formatValue || ((v) => `${v}${suffix}`);

  function handleChange(e) {
    onChange(Number(e.target.value));
  }

  return (
    <div className="dslider">
      <div className="dslider-track">
        <div className="dslider-fill" style={{ left: 0, width: `${pct(value)}%` }} />
      </div>
      <input
        className="dslider-input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={handleChange}
      />
      <div className="dslider-label" style={{ left: `${pct(value)}%` }}>
        {fmt(value)}
      </div>
    </div>
  );
}
