import React from 'react';

/** Tiny CSS-only spinner (see .spinner in theme.css) -- avoids pinning to a spinner library's exact API. */
export default function Spinner({ label }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" />
      {label && <span className="spinner-label">{label}</span>}
    </span>
  );
}
