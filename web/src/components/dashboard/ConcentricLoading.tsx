function makeScallopedPath(radius: number, lobes: number, amplitude: number) {
  const steps = lobes * 32;
  const points = Array.from({ length: steps }, (_, index) => {
    const angle = (index / steps) * Math.PI * 2;
    const distance = radius * (1 + amplitude * Math.cos(lobes * angle));
    const x = 160 + Math.cos(angle) * distance;
    const y = 160 + Math.sin(angle) * distance;
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  });

  return `${points.join(" ")} Z`;
}

export function ConcentricLoading() {
  return (
    <div className="concentric-loading" role="status" aria-label="Waiting for live alerts">
      <svg viewBox="0 0 320 320" aria-hidden="true">
        <defs>
          <pattern id="concentric-dot-grid" width="16" height="16" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.8" fill="#75819a" fillOpacity="0.24" />
          </pattern>
          <radialGradient id="concentric-core">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.28" />
            <stop offset="56%" stopColor="#ff007a" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="320" height="320" fill="url(#concentric-dot-grid)" />
        <circle cx="160" cy="160" r="144" fill="url(#concentric-core)" />
        <g className="concentric-ring concentric-ring--outer">
          <path d={makeScallopedPath(116, 12, 0.12)} />
        </g>
        <g className="concentric-ring concentric-ring--middle">
          <path d={makeScallopedPath(82, 12, 0.12)} />
        </g>
        <g className="concentric-ring concentric-ring--inner">
          <path d={makeScallopedPath(50, 12, 0.1)} />
        </g>
      </svg>
    </div>
  );
}