import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { EASE_IN, EASE_IN_OUT, EASE_OUT, lerp, pop, squash } from "../anim";
import { Bean, CAST } from "../components/Bean";
import { Label } from "../components/Bubble";
import { CatHead } from "../components/Cat";
import { Check, Chest, Coin, Flame, Sparkle, Trophy } from "../components/Icons";
import { Phone, ScreenName } from "../components/Phone";
import { C } from "../theme";

/**
 * Beat 3 — Gamification (18–25 s, 210 frames)
 * A: mosaic wall of screenshot tiles + reward tiles, columns sliding.
 * B: dark-teal panel rises; streak / liga / profil cards drop as a stack and
 *    fan out like a hand of cards. Only numbers that exist in the screenshots.
 */
export const GAMIFY_LEN = 210;
export const GAMIFY_CUES = {
  wallIn: 0,
  ding1: 8,
  ding2: 19,
  panel: 92,
  stackLand: 115,
  fan: 122,
  fanLand: 131,
  flame: 138,
  trophy: 146,
  shrink: 198,
};

type Tile =
  | { k: "shot"; s: ScreenName }
  | { k: "icon"; i: "flame" | "coin" | "chest" | "trophy" }
  | { k: "check" }
  | { k: "cat" }
  | { k: "char"; c: keyof typeof CAST };

const TW = 250;
const GAP = 28;
const SQ = 250;
const TALL = 540;

const COLS: Tile[][] = [
  [{ k: "icon", i: "coin" }, { k: "shot", s: "profil" }, { k: "check" }, { k: "shot", s: "soal" }],
  [{ k: "shot", s: "beranda" }, { k: "char", c: "nisa" }, { k: "icon", i: "flame" }, { k: "shot", s: "liga" }],
  [{ k: "check" }, { k: "icon", i: "chest" }, { k: "shot", s: "selesai" }, { k: "cat" }],
  [{ k: "shot", s: "streak" }, { k: "cat" }, { k: "icon", i: "trophy" }, { k: "shot", s: "pengantar" }],
  [{ k: "icon", i: "flame" }, { k: "shot", s: "soal" }, { k: "char", c: "dimas" }, { k: "check" }],
  [{ k: "char", c: "harun" }, { k: "shot", s: "liga" }, { k: "icon", i: "coin" }, { k: "shot", s: "beranda" }],
  [{ k: "shot", s: "selesai" }, { k: "check" }, { k: "icon", i: "chest" }, { k: "char", c: "fikri" }],
  [{ k: "icon", i: "trophy" }, { k: "shot", s: "streak" }, { k: "cat" }, { k: "shot", s: "profil" }],
];

const tileH = (t: Tile) => (t.k === "shot" ? TALL : SQ);

const TileView: React.FC<{ t: Tile; f: number }> = ({ t, f }) => {
  const h = tileH(t);
  const base: React.CSSProperties = {
    position: "relative",
    width: TW,
    height: h,
    borderRadius: 24,
    overflow: "hidden",
  };
  if (t.k === "shot") {
    return (
      <div style={{ ...base, background: C.white, boxShadow: `0 6px 0 0 ${C.neutral300}`, overflow: "visible" }}>
        <Phone screen={t.s} width={196} style={{ left: (TW - 214) / 2, top: (h - 450) / 2 }} />
      </div>
    );
  }
  if (t.k === "icon") {
    const I = { flame: Flame, coin: Coin, chest: Chest, trophy: Trophy }[t.i];
    return (
      <div style={{ ...base, background: C.gold100, boxShadow: `0 6px 0 0 #F2D6A6`, overflow: "visible" }}>
        <I size={140} style={{ left: 55, top: 50, rotate: `${Math.sin(f / 6) * 6}deg` }} />
      </div>
    );
  }
  if (t.k === "check") {
    return (
      <div style={{ ...base, background: C.teal500, boxShadow: `0 6px 0 0 ${C.teal600}`, overflow: "visible" }}>
        <Check size={150} color={C.white} style={{ left: 50, top: 50 }} />
      </div>
    );
  }
  if (t.k === "cat") {
    return (
      <div style={{ ...base, background: C.white, boxShadow: `0 6px 0 0 ${C.neutral300}`, overflow: "visible" }}>
        <CatHead size={180} style={{ left: 35, top: 40 }} />
      </div>
    );
  }
  return (
    <div style={{ ...base, background: C.teal200 }}>
      <Bean {...CAST[t.c]} expr="happy" armL={150 + Math.sin(f / 4) * 20} armR={20} height={520} style={{ left: -38, top: 10 }} />
    </div>
  );
};

const Mosaic: React.FC<{ f: number }> = ({ f }) => {
  const slide = lerp(f, [0, 12], [520, 0], EASE_OUT);
  return (
    <AbsoluteFill style={{ background: C.teal100, overflow: "hidden" }}>
      <AbsoluteFill style={{ translate: `${slide - f * 1.6}px ${-60}px`, rotate: "-8deg", scale: "1.18" }}>
        {COLS.map((col, ci) => {
          const dir = ci % 2 === 0 ? -1 : 1;
          const off = dir * f * 2.6 + (ci % 2 ? -900 : -300);
          const tiles = [...col, ...col, ...col];
          let y = 0;
          return (
            <div key={ci} style={{ position: "absolute", left: -260 + ci * (TW + GAP), top: off }}>
              {tiles.map((t, ti) => {
                const top = y;
                y += tileH(t) + GAP;
                const s = pop(f, ci * 0.6 + (ti % 4) * 0.6 - 5, 10, 190);
                return (
                  <div key={ti} style={{ position: "absolute", left: 0, top, scale: String(s) }}>
                    <TileView t={t} f={f} />
                  </div>
                );
              })}
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const FAN: Array<{ s: ScreenName; x: number; r: number }> = [
  { s: "streak", x: -470, r: -9 },
  { s: "profil", x: 470, r: 9 },
  { s: "liga", x: 0, r: 0 }, // front
];

const Fan: React.FC<{ f: number }> = ({ f }) => {
  const rise = lerp(f, [GAMIFY_CUES.panel, GAMIFY_CUES.panel + 14], [1180, 0], EASE_OUT);
  const drop = pop(f, GAMIFY_CUES.stackLand - 9, 11, 170);
  const fan = pop(f, GAMIFY_CUES.fan, 12, 140);
  const [sx, sy] = squash(f, GAMIFY_CUES.stackLand, 0.07);
  const shrink = lerp(f, [GAMIFY_CUES.shrink, GAMIFY_LEN], [1, 0.05], EASE_IN);
  const labelIn = pop(f, 124, 10, 190);
  const labelOut = lerp(f, [200, 206], [1, 0]);
  const flame = pop(f, GAMIFY_CUES.flame, 8, 200);
  const trophy = pop(f, GAMIFY_CUES.trophy, 8, 200);
  return (
    <AbsoluteFill style={{ translate: `0px ${rise}px` }}>
      <div style={{ position: "absolute", left: 0, top: -120, width: 1920, height: 1400, background: C.teal700, borderRadius: "140px 140px 0 0" }} />
      <AbsoluteFill style={{ scale: String(shrink), transformOrigin: "50% 60%" }}>
        {f >= GAMIFY_CUES.stackLand - 9
          ? FAN.map((c, i) => (
              <div
                key={c.s}
                style={{
                  position: "absolute",
                  left: 960 - 174 + c.x * fan,
                  top: 250 + Math.abs(c.r) * 3 * fan,
                  width: 348,
                  height: 728,
                  translate: `0px ${lerp(drop, [0, 1], [-1200, 0])}px`,
                  rotate: `${c.r * fan + (1 - fan) * (i - 1) * 4}deg`,
                  scale: `${sx} ${sy}`,
                  transformOrigin: "50% 100%",
                }}
              >
                <Phone screen={c.s} width={320} style={{ left: 0, top: 0 }} />
              </div>
            ))
          : null}
        <Flame size={170} style={{ left: 110, top: 770, scale: String(flame), rotate: `${Math.sin(f / 5) * 6}deg` }} />
        <Trophy size={170} style={{ left: 1640, top: 770, scale: String(trophy), rotate: `${Math.sin(f / 6) * 5}deg` }} />
        <Sparkle size={60} style={{ left: 250, top: 700, scale: String(flame * (0.8 + 0.2 * Math.sin(f / 3))) }} />
        <Sparkle size={50} style={{ left: 1610, top: 720, scale: String(trophy * (0.8 + 0.2 * Math.sin(f / 3 + 1))) }} />
        {f >= 123 ? (
          <Label
            fontSize={74}
            edge={C.teal800}
            style={{
              left: 960,
              top: 56,
              translate: "-50% 0px",
              scale: String(Math.max(0, labelIn * labelOut)),
            }}
          >
            Jaga streak, naik liga
          </Label>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Gamify: React.FC = () => {
  const f = useCurrentFrame();
  const labelIn = pop(f, 16, 10, 190);
  const labelOut = lerp(f, [90, 96], [1, 0], EASE_IN_OUT);
  return (
    <AbsoluteFill style={{ background: C.teal700 }}>
      {f < GAMIFY_CUES.panel + 16 ? (
        <>
          <Mosaic f={f} />
          {f >= 15 && f < 97 ? (
            <Label
              fontSize={88}
              bg={C.teal700}
              color={C.white}
              edge={C.teal900}
              style={{
                left: 960,
                top: 470,
                translate: "-50% 0px",
                scale: String(Math.max(0, labelIn * labelOut)),
              }}
            >
              Belajarnya kayak main game
            </Label>
          ) : null}
        </>
      ) : null}
      {f >= GAMIFY_CUES.panel ? <Fan f={f} /> : null}
    </AbsoluteFill>
  );
};

