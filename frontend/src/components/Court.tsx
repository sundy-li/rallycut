export default function Court() {
  return (
    <svg viewBox="0 0 680 330" className="court" fill="none" aria-hidden="true">
      <defs>
        <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">
          <path d="M 36 0 L 0 0 0 36" stroke="#96b4a6" strokeOpacity=".07" />
        </pattern>
        <linearGradient
          id="table"
          x1="340"
          y1="94"
          x2="340"
          y2="256"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#263d35" />
          <stop offset="1" stopColor="#1c2d27" />
        </linearGradient>
      </defs>
      <rect width="680" height="330" fill="url(#grid)" />
      <ellipse cx="344" cy="278" rx="221" ry="20" fill="#000" opacity=".25" />
      <path
        d="m166 256 16 25m332-25-12 25M253 112l-3 15m179-15 3 15"
        stroke="#53655c"
        strokeWidth="7"
      />
      <path
        d="m233 91 215 0 102 161H132L233 91Z"
        fill="url(#table)"
        stroke="#7b9d8d"
        strokeWidth="1.5"
      />
      <path
        d="M340 92v160M185 171h316"
        stroke="#a7c7b8"
        strokeWidth="1.3"
        opacity=".65"
      />
      <path d="M183 168v-27h320v27" stroke="#c2d3ca" strokeWidth="1.5" />
      <path
        d="M184 143h318M184 150h318M184 157h318"
        stroke="#82998e"
        strokeWidth=".7"
      />
      {Array.from({ length: 39 }, (_, i) => (
        <path
          key={i}
          d={`M${188 + i * 8} 142v24`}
          stroke="#82998e"
          strokeWidth=".5"
        />
      ))}
      <path
        d="M245 199Q321 23 438 113"
        stroke="#c2ef83"
        strokeWidth="2"
        strokeDasharray="4 7"
        opacity=".65"
      />
      <circle cx="438" cy="113" r="7" fill="#d7f3b2" />
      <circle cx="438" cy="113" r="15" stroke="#b7df81" opacity=".15" />
      <path d="m132 252 0 7h418v-7" stroke="#44594e" strokeWidth="2" />
    </svg>
  );
}
