import React from "react";
import { C } from "../theme";

/**
 * Original "bean" characters for the Z-Sharia teaser.
 * Flat, rounded, no outlines. Round head on a bean torso with stubby legs.
 * viewBox 0 0 200 320, feet touch y=316, centre x=100.
 */
export type Hair = "short" | "sidepart" | "curly" | "peci" | "hijab";
export type Expr = "happy" | "grin" | "confused" | "wow";
export type Acc = "none" | "book" | "apron" | "blazer" | "backpack" | "phone";

export type BeanProps = {
  skin: string;
  hair: Hair;
  hairColor?: string; // hijab colour when hair = hijab
  shirt: string;
  sleeve?: string;
  pants?: string;
  glasses?: boolean;
  acc?: Acc;
  expr?: Expr;
  armL?: number; // degrees, 0 = hanging down, 90 = out sideways, 170 = up
  armR?: number;
  blink?: number; // 0 open .. 1 closed
  look?: number; // pupil shift x, -1..1
  height: number;
  style?: React.CSSProperties;
};

const SH_L = { x: 60, y: 172 };
const SH_R = { x: 140, y: 172 };
const ARM = 66;

const armEnd = (side: "L" | "R", a: number) => {
  const r = (a * Math.PI) / 180;
  const s = side === "L" ? SH_L : SH_R;
  const dir = side === "L" ? -1 : 1;
  return { x: s.x + dir * Math.sin(r) * ARM, y: s.y + Math.cos(r) * ARM };
};

export const Bean: React.FC<BeanProps> = ({
  skin,
  hair,
  hairColor = C.ink,
  shirt,
  sleeve,
  pants = C.inkSoft,
  glasses,
  acc = "none",
  expr = "happy",
  armL = 12,
  armR = 12,
  blink = 0,
  look = 0,
  height,
  style,
}) => {
  const sl = sleeve ?? shirt;
  const eL = armEnd("L", armL);
  const eR = armEnd("R", armR);
  const eyeRy = 11 * (1 - blink * 0.9);
  const px = look * 4;
  const hijab = hair === "hijab";
  const faceR = hijab ? 52 : 62;
  const faceCy = hijab ? 98 : 92;

  const brows =
    expr === "confused" ? (
      <>
        <path d="M66 70 Q78 58 90 66" stroke={C.ink} strokeWidth="6" fill="none" strokeLinecap="round" />
        <path d="M110 76 Q122 76 134 80" stroke={C.ink} strokeWidth="6" fill="none" strokeLinecap="round" />
      </>
    ) : expr === "wow" ? (
      <>
        <path d="M68 68 Q78 60 90 66" stroke={C.ink} strokeWidth="6" fill="none" strokeLinecap="round" />
        <path d="M110 66 Q122 60 132 68" stroke={C.ink} strokeWidth="6" fill="none" strokeLinecap="round" />
      </>
    ) : (
      <>
        <path d="M68 74 Q78 68 90 72" stroke={C.ink} strokeWidth="6" fill="none" strokeLinecap="round" />
        <path d="M110 72 Q122 68 132 74" stroke={C.ink} strokeWidth="6" fill="none" strokeLinecap="round" />
      </>
    );

  const mouth =
    expr === "happy" ? (
      <g>
        <path d="M84 116 Q100 140 116 116 Z" fill="#4A2622" />
        <path d="M92 127 Q100 136 108 127 Q100 122 92 127 Z" fill="#E98A86" />
      </g>
    ) : expr === "grin" ? (
      <path d="M86 118 Q100 130 114 118" stroke="#4A2622" strokeWidth="6" fill="none" strokeLinecap="round" />
    ) : expr === "wow" ? (
      <ellipse cx="100" cy="124" rx="8" ry="10" fill="#4A2622" />
    ) : (
      <path d="M86 124 Q93 118 100 124 Q107 130 114 122" stroke="#4A2622" strokeWidth="6" fill="none" strokeLinecap="round" />
    );

  const dy = hijab ? 6 : 0; // hijab face sits a bit lower

  const arm = (e: { x: number; y: number }, s: { x: number; y: number }) => (
    <g>
      <line x1={s.x} y1={s.y} x2={e.x} y2={e.y} stroke={sl} strokeWidth="24" strokeLinecap="round" />
      <circle cx={e.x} cy={e.y} r="13" fill={skin} />
    </g>
  );

  return (
    <svg
      viewBox="0 0 200 320"
      style={{
        position: "absolute",
        height,
        width: (height * 200) / 320,
        overflow: "visible",
        ...style,
      }}
    >
      {/* backpack behind torso */}
      {acc === "backpack" ? <rect x="44" y="160" width="112" height="92" rx="34" fill={C.teal700} /> : null}

      {/* legs + shoes */}
      <rect x="70" y="244" width="24" height="64" rx="12" fill={pants} />
      <rect x="106" y="244" width="24" height="64" rx="12" fill={pants} />
      <ellipse cx="80" cy="310" rx="17" ry="9" fill={C.ink} />
      <ellipse cx="120" cy="310" rx="17" ry="9" fill={C.ink} />

      {/* torso */}
      <rect x="50" y="146" width="100" height="120" rx="46" fill={shirt} />
      {acc === "blazer" ? (
        <g>
          <path d="M84 150 L100 196 L116 150 Z" fill={C.white} />
          <path d="M96 160 L104 160 L106 196 L100 204 L94 196 Z" fill={C.teal500} />
          <rect x="118" y="196" width="18" height="10" rx="3" fill={C.white} />
        </g>
      ) : null}
      {acc === "apron" ? (
        <g>
          <rect x="62" y="178" width="76" height="82" rx="22" fill={C.teal700} />
          <rect x="84" y="208" width="32" height="20" rx="8" fill={C.teal600} />
          <path d="M70 178 L66 152 M130 178 L134 152" stroke={C.teal700} strokeWidth="6" strokeLinecap="round" />
        </g>
      ) : null}
      {acc === "backpack" ? (
        <g>
          <path d="M66 156 L72 232" stroke={C.teal500} strokeWidth="9" strokeLinecap="round" />
          <path d="M134 156 L128 232" stroke={C.teal500} strokeWidth="9" strokeLinecap="round" />
        </g>
      ) : null}

      {/* hijab drape (behind face, over shoulders) */}
      {hijab ? (
        <g>
          <path
            d="M30 100 C30 52 62 22 100 22 C138 22 170 52 170 100 C170 140 160 176 150 196 C130 206 70 206 50 196 C40 176 30 140 30 100 Z"
            fill={hairColor}
          />
        </g>
      ) : null}

      {/* head */}
      <circle cx="100" cy={faceCy} r={faceR} fill={skin} />

      {/* hair */}
      {hair === "short" ? (
        <path
          d="M37 96 C32 46 64 24 102 26 C140 28 170 52 163 96 C156 76 140 64 118 62 C112 70 100 72 86 68 C70 70 48 78 37 96 Z"
          fill={hairColor}
        />
      ) : null}
      {hair === "sidepart" ? (
        <path
          d="M38 92 C34 46 66 26 104 28 C142 30 168 54 162 92 C150 70 132 58 110 56 C96 64 78 58 70 50 C60 62 46 72 38 92 Z"
          fill={hairColor}
        />
      ) : null}
      {hair === "curly" ? (
        <g fill={hairColor}>
          {[
            [44, 74], [52, 52], [70, 36], [92, 28], [114, 28], [134, 38], [150, 54], [158, 76],
            [62, 60], [84, 46], [108, 44], [130, 54], [100, 38], [76, 50], [124, 46],
          ].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={i < 8 ? 19 : 17} />
          ))}
        </g>
      ) : null}
      {hair === "peci" ? (
        <g>
          <path d="M40 92 C40 74 44 66 52 62 L58 62 L56 92 Z" fill={C.ink} />
          <path d="M160 92 C160 74 156 66 148 62 L142 62 L144 92 Z" fill={C.ink} />
          <path d="M48 64 C48 36 64 26 100 26 C136 26 152 36 152 64 Z" fill={C.ink} />
          <rect x="46" y="58" width="108" height="12" rx="6" fill="#141A19" />
        </g>
      ) : null}
      {hijab ? (
        <path d="M48 96 C48 60 72 40 100 40 C128 40 152 60 152 96 C146 70 126 56 100 56 C74 56 54 70 48 96 Z" fill={hairColor} />
      ) : null}

      {/* face */}
      <g transform={`translate(0 ${dy})`}>
        <ellipse cx="70" cy="114" rx="9" ry="6" fill={C.cheek} opacity="0.55" />
        <ellipse cx="130" cy="114" rx="9" ry="6" fill={C.cheek} opacity="0.55" />
        <ellipse cx={80 + px} cy="96" rx="8" ry={eyeRy} fill={C.ink} />
        <ellipse cx={120 + px} cy="96" rx="8" ry={eyeRy} fill={C.ink} />
        {blink < 0.5 ? (
          <>
            <circle cx={83 + px} cy="92" r="3" fill={C.white} />
            <circle cx={123 + px} cy="92" r="3" fill={C.white} />
          </>
        ) : null}
        {glasses ? (
          <g fill="none" stroke={C.ink} strokeWidth="5">
            <circle cx="80" cy="96" r="18" />
            <circle cx="120" cy="96" r="18" />
            <path d="M98 94 Q100 90 102 94" />
          </g>
        ) : null}
        {brows}
        {mouth}
      </g>

      {/* arms */}
      {arm(eL, SH_L)}
      {arm(eR, SH_R)}
      {acc === "book" ? (
        <g transform={`translate(${eR.x} ${eR.y}) rotate(-12)`}>
          <rect x="-6" y="-34" width="40" height="52" rx="6" fill={C.teal700} />
          <rect x="-2" y="-30" width="6" height="44" rx="3" fill={C.teal500} />
        </g>
      ) : null}
      {acc === "phone" ? (
        <g transform={`translate(${eL.x} ${eL.y}) rotate(-14)`}>
          <rect x="-18" y="-46" width="34" height="58" rx="8" fill={C.ink} />
          <rect x="-14" y="-42" width="26" height="46" rx="5" fill={C.teal100} />
          <circle cx="-1" cy="0" r="13" fill={skin} />
        </g>
      ) : null}
    </svg>
  );
};

// The cast (all original). Ages/roles from the brief.
export const CAST = {
  raka: {
    skin: C.skin2,
    hair: "short" as Hair,
    shirt: C.teal500,
    sleeve: C.teal600,
    glasses: true,
    acc: "none" as Acc,
  }, // mahasiswa berkacamata
  nisa: {
    skin: C.skin1,
    hair: "hijab" as Hair,
    hairColor: C.teal700,
    shirt: C.sand,
    pants: C.teal800,
    acc: "book" as Acc,
  }, // mahasiswi berhijab
  dimas: {
    skin: C.skin4,
    hair: "curly" as Hair,
    shirt: C.inkSoft,
    pants: C.teal700,
    acc: "backpack" as Acc,
  }, // mahasiswa
  harun: {
    skin: C.skin3,
    hair: "peci" as Hair,
    shirt: C.sand,
    pants: C.inkSoft,
    acc: "apron" as Acc,
  }, // pedagang pasar
  fikri: {
    skin: "#C98E5E",
    hair: "sidepart" as Hair,
    shirt: C.teal700,
    sleeve: C.teal700,
    pants: C.ink,
    acc: "blazer" as Acc,
  }, // pegawai bank syariah
};
