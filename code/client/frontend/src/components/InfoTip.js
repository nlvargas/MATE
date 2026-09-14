import React from 'react';
import ReactTooltip from 'react-tooltip';

let nextId = 0;

/** Small "i" info-bubble with a hover tooltip, used next to parameters that need a one-line explanation. */
export default function InfoTip({ text }) {
  const id = React.useRef(`infotip-${nextId++}`);
  return (
    <span className="info-icon" tabIndex={0} data-tip={text} data-for={id.current}>
      i
      <ReactTooltip id={id.current} place="top" effect="solid" className="info-tip-bubble" />
    </span>
  );
}
