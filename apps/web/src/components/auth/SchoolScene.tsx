/**
 * Ilustracao plana da escola (so formas SVG, nas cores da marca) das telas de acesso. Enfeite: nao e lida
 * por leitor de tela. `SchoolScene` e a do painel do computador; `SchoolSceneMini` a do cabecalho do celular.
 */
const WHITE = "#ffffff";
const NAVY = "#182c7a";

export function SchoolScene({ className = "" }: { className?: string }) {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="212 500 668 400" preserveAspectRatio="xMaxYMax meet" fill="none" className={className}>
      <path d="M300 900 C330 790 560 800 880 660 L880 900 Z" fill="#4b89f4" fillOpacity="0.38" />
      <path d="M300 900 C380 790 600 740 880 770 L880 900 Z" fill={NAVY} fillOpacity="0.28" />
      <path d="M260 900 C400 842 580 818 880 832 L880 900 Z" fill={NAVY} fillOpacity="0.92" />
      <g fill={WHITE} fillOpacity="0.9">
        <ellipse cx="700" cy="590" rx="44" ry="15" />
        <circle cx="688" cy="577" r="18" />
        <circle cx="716" cy="581" r="14" />
      </g>
      <g fill={WHITE} fillOpacity="0.75">
        <ellipse cx="322" cy="655" rx="34" ry="12" />
        <circle cx="313" cy="645" r="14" />
        <circle cx="334" cy="648" r="11" />
      </g>
      <polygon points="425,705 560,640 695,705" fill="#98c7ff" />
      <rect x="445" y="705" width="230" height="127" fill={WHITE} />
      <rect x="520" y="610" width="80" height="102" fill={WHITE} />
      <polygon points="510,612 560,565 610,612" fill="#7bb3ff" />
      <path d="M560 565V528" stroke={WHITE} strokeWidth="3" strokeLinecap="round" />
      <polygon points="560,528 592,538 560,548" fill="#98c7ff" />
      <circle cx="560" cy="650" r="17" fill="#eaf1ff" stroke={NAVY} strokeWidth="3" />
      <path d="M560 650V638M560 650L569 655" stroke={NAVY} strokeWidth="3" strokeLinecap="round" />
      <g fill="#98c7ff">
        <rect x="458" y="740" width="32" height="40" rx="6" />
        <rect x="496" y="740" width="32" height="40" rx="6" />
        <rect x="592" y="740" width="32" height="40" rx="6" />
        <rect x="630" y="740" width="32" height="40" rx="6" />
      </g>
      <path d="M540 832V790a20 20 0 0 1 40 0V832Z" fill={NAVY} />
      <rect x="528" y="828" width="64" height="8" rx="2" fill={WHITE} fillOpacity="0.9" />
      <circle cx="606" cy="800" r="6.5" fill={NAVY} />
      <rect x="599" y="808" width="14" height="24" rx="6" fill="#346ae3" />
      <circle cx="634" cy="804" r="6.5" fill={NAVY} />
      <rect x="627" y="812" width="14" height="20" rx="6" fill="#7bb3ff" />
      <circle cx="656" cy="810" r="5.5" fill={NAVY} />
      <rect x="650" y="817" width="12" height="15" rx="5" fill="#346ae3" />
      <g fill={WHITE} fillOpacity="0.92">
        <rect x="290" y="808" width="130" height="5" />
        <rect x="290" y="828" width="130" height="5" />
        {[292, 310, 328, 346, 364, 382, 400].map((x) => (
          <rect key={x} x={x} y="796" width="8" height="46" rx="2" />
        ))}
      </g>
      <rect x="752" y="800" width="8" height="40" fill={WHITE} />
      <ellipse cx="756" cy="776" rx="30" ry="42" fill="#98c7ff" />
      <rect x="806" y="812" width="6" height="28" fill={WHITE} />
      <ellipse cx="809" cy="796" rx="20" ry="28" fill="#7bb3ff" />
    </svg>
  );
}

export function SchoolSceneMini({ className = "" }: { className?: string }) {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 390 262" preserveAspectRatio="xMaxYMax slice" fill="none" className={className}>
      <path d="M0 150C90 120 200 190 390 130V262H0Z" fill="#4b89f4" fillOpacity="0.34" />
      <g fill={WHITE} fillOpacity="0.85">
        <ellipse cx="338" cy="68" rx="22" ry="8" />
        <circle cx="331" cy="60" r="10" />
        <circle cx="347" cy="62" r="8" />
      </g>
      <g fill={WHITE} fillOpacity="0.7">
        <ellipse cx="267" cy="92" rx="17" ry="6" />
        <circle cx="261" cy="86" r="8" />
        <circle cx="274" cy="88" r="6" />
      </g>
      <path d="M150 262C210 224 310 214 390 224V262Z" fill={NAVY} fillOpacity="0.9" />
      <polygon points="234,192 292,164 350,192" fill="#98c7ff" />
      <rect x="244" y="192" width="96" height="40" fill={WHITE} />
      <rect x="272" y="148" width="40" height="46" fill={WHITE} />
      <polygon points="266,150 292,128 318,150" fill="#7bb3ff" />
      <path d="M292 128V112" stroke={WHITE} strokeWidth="2" strokeLinecap="round" />
      <polygon points="292,112 306,117 292,122" fill="#98c7ff" />
      <circle cx="292" cy="170" r="8" fill="#eaf1ff" stroke={NAVY} strokeWidth="2" />
      <path d="M292 170V165M292 170L296 172" stroke={NAVY} strokeWidth="1.6" strokeLinecap="round" />
      <g fill="#98c7ff">
        <rect x="251" y="203" width="12" height="16" rx="3" />
        <rect x="267" y="203" width="12" height="16" rx="3" />
        <rect x="305" y="203" width="12" height="16" rx="3" />
        <rect x="321" y="203" width="12" height="16" rx="3" />
      </g>
      <path d="M282 232V214a10 10 0 0 1 20 0V232Z" fill={NAVY} />
      <rect x="371" y="214" width="3" height="16" fill={WHITE} />
      <ellipse cx="372.5" cy="204" rx="11" ry="17" fill="#98c7ff" />
      <g fill={WHITE} fillOpacity="0.9">
        <rect x="204" y="214" width="46" height="3" />
        <rect x="204" y="224" width="46" height="3" />
        {[206, 216, 226, 236].map((x) => (
          <rect key={x} x={x} y="207" width="4" height="24" rx="1" />
        ))}
      </g>
    </svg>
  );
}
