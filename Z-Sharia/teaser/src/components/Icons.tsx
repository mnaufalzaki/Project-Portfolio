import React from "react";
import { C } from "../theme";

type P = { size: number; style?: React.CSSProperties };
const wrap = (size: number, style?: React.CSSProperties): React.CSSProperties => ({
  position: "absolute",
  width: size,
  height: size,
  overflow: "visible",
  ...style,
});

// Reward icons — the only things allowed to be gold.

export const Flame: React.FC<P> = ({ size, style }) => (
  <svg viewBox="0 0 100 100" style={wrap(size, style)}>
    <path
      d="M50 96 C26 96 14 80 14 62 C14 42 30 32 34 14 C46 24 50 34 50 44 C56 38 58 30 58 24 C76 38 86 52 86 64 C86 82 72 96 50 96 Z"
      fill={C.gold700}
      transform="translate(0 5)"
    />
    <path
      d="M50 96 C26 96 14 80 14 62 C14 42 30 32 34 14 C46 24 50 34 50 44 C56 38 58 30 58 24 C76 38 86 52 86 64 C86 82 72 96 50 96 Z"
      fill={C.gold}
    />
    <path
      d="M50 88 C38 88 32 80 32 70 C32 60 40 54 44 46 C50 54 56 58 60 64 C64 70 66 74 66 76 C66 84 60 88 50 88 Z"
      fill="#FBD08F"
    />
  </svg>
);

export const Coin: React.FC<P> = ({ size, style }) => (
  <svg viewBox="0 0 100 100" style={wrap(size, style)}>
    <circle cx="50" cy="56" r="42" fill={C.gold700} />
    <circle cx="50" cy="50" r="42" fill={C.gold} />
    <circle cx="50" cy="50" r="27" fill="none" stroke={C.gold700} strokeWidth="9" />
    <circle cx="50" cy="50" r="13" fill="#FBD08F" />
  </svg>
);

export const Chest: React.FC<P> = ({ size, style }) => (
  <svg viewBox="0 0 100 100" style={wrap(size, style)}>
    <rect x="10" y="40" width="80" height="50" rx="12" fill={C.gold700} transform="translate(0 6)" />
    <rect x="10" y="40" width="80" height="50" rx="12" fill={C.gold} />
    <path d="M10 46 C10 26 22 16 50 16 C78 16 90 26 90 46 Z" fill={C.gold700} transform="translate(0 4)" />
    <path d="M10 46 C10 26 22 16 50 16 C78 16 90 26 90 46 Z" fill="#FBC56F" />
    <rect x="10" y="44" width="80" height="8" fill={C.gold700} />
    <rect x="42" y="50" width="16" height="22" rx="7" fill={C.ink} />
  </svg>
);

export const Trophy: React.FC<P> = ({ size, style }) => (
  <svg viewBox="0 0 100 100" style={wrap(size, style)}>
    <g transform="translate(0 5)" fill={C.gold700}>
      <path d="M28 10 H72 V40 C72 56 62 64 50 64 C38 64 28 56 28 40 Z" />
      <rect x="30" y="78" width="40" height="14" rx="6" />
    </g>
    <path d="M28 18 C12 18 10 28 12 36 C14 44 22 48 30 46" fill="none" stroke={C.gold} strokeWidth="8" strokeLinecap="round" />
    <path d="M72 18 C88 18 90 28 88 36 C86 44 78 48 70 46" fill="none" stroke={C.gold} strokeWidth="8" strokeLinecap="round" />
    <path d="M28 10 H72 V40 C72 56 62 64 50 64 C38 64 28 56 28 40 Z" fill={C.gold} />
    <rect x="44" y="60" width="12" height="20" fill={C.gold} />
    <rect x="30" y="76" width="40" height="14" rx="6" fill={C.gold} />
    <path d="M50 22 L54 32 L64 32 L56 38 L59 48 L50 42 L41 48 L44 38 L36 32 L46 32 Z" fill="#FBD08F" />
  </svg>
);

/** Small white check on teal — "lesson done" tile. */
export const Check: React.FC<P & { color?: string }> = ({ size, style, color = C.teal700 }) => (
  <svg viewBox="0 0 100 100" style={wrap(size, style)}>
    <path d="M24 52 L42 70 L76 32" fill="none" stroke={color} strokeWidth="13" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const Sparkle: React.FC<P & { color?: string }> = ({ size, style, color = C.gold }) => (
  <svg viewBox="0 0 100 100" style={wrap(size, style)}>
    <path d="M50 4 C54 36 64 46 96 50 C64 54 54 64 50 96 C46 64 36 54 4 50 C36 46 46 36 50 4 Z" fill={color} />
  </svg>
);
