export function Hero() {
  return (
    <header className="hero">
      <div className="hero-copy">
        <h1>Can I Park Here, Chicago?</h1>
        <p className="hero-sub">
          Verify if you can park legally, and sign up to get daily notifications updating
          you on street cleaning, events, and more so you never get another ticket!
        </p>
      </div>
      <Skyline />
    </header>
  );
}

function Skyline() {
  return (
    <svg className="skyline" viewBox="0 0 420 200" aria-hidden="true">
      <rect width="420" height="200" fill="#9fcbee" rx="16" />
      <g fill="#6497bf">
        <rect x="18" y="120" width="34" height="70" rx="2" />
        <rect x="58" y="92" width="26" height="98" rx="2" />
        <rect x="90" y="108" width="30" height="82" rx="2" />
        <rect x="126" y="60" width="22" height="130" rx="2" />
        <rect x="132" y="40" width="10" height="22" />
        <rect x="154" y="100" width="34" height="90" rx="2" />
        <rect x="194" y="78" width="24" height="112" rx="2" />
        <rect x="224" y="112" width="30" height="78" rx="2" />
        <rect x="260" y="86" width="26" height="104" rx="2" />
        <rect x="292" y="122" width="34" height="68" rx="2" />
        <rect x="332" y="98" width="24" height="92" rx="2" />
        <rect x="362" y="128" width="40" height="62" rx="2" />
        <rect x="0" y="182" width="420" height="18" />
      </g>
      <g fill="#fff">
        <rect x="63" y="102" width="4" height="6" />
        <rect x="71" y="102" width="4" height="6" />
        <rect x="63" y="116" width="4" height="6" />
        <rect x="131" y="72" width="4" height="7" />
        <rect x="139" y="72" width="4" height="7" />
        <rect x="131" y="90" width="4" height="7" />
        <rect x="199" y="90" width="4" height="6" />
        <rect x="207" y="90" width="4" height="6" />
        <rect x="265" y="98" width="4" height="6" />
        <rect x="273" y="98" width="4" height="6" />
        <rect x="300" y="134" width="4" height="6" />
        <rect x="308" y="134" width="4" height="6" />
      </g>
      {/* parking sign */}
      <rect x="332" y="140" width="3" height="44" fill="#01016f" />
      <rect
        x="319"
        y="130"
        width="29"
        height="26"
        rx="5"
        fill="#fff"
        stroke="#01016f"
        strokeWidth="2"
      />
      <text x="333.5" y="150" fontSize="16" fontWeight="700" fill="#01016f" textAnchor="middle">
        P
      </text>
      {/* car */}
      <g fill="#01016f">
        <path d="M262 176c1-6 4-10 8-10h20c4 0 7 3 9 8l3 8h-44l4-14Z" />
        <rect x="258" y="181" width="46" height="9" rx="3" />
      </g>
      <circle cx="269" cy="190" r="4" fill="#000" />
      <circle cx="295" cy="190" r="4" fill="#000" />
    </svg>
  );
}
