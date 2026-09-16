import React, { useState } from 'react';
import ReactTooltip from 'react-tooltip';

let nextId = 0;

/** Small "i" info-bubble with a hover tooltip, used next to parameters that need a one-line explanation. */
export default function InfoTip({ text }) {
  const [id] = useState(() => `infotip-${nextId++}`);
  return (
    <span className="info-icon" tabIndex={0} data-tip={text} data-for={id}>
      i
      <ReactTooltip id={id} place="top" effect="solid" className="info-tip-bubble" />
    </span>
  );
}
