import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { EASE_IN, EASE_IN_OUT, EASE_OUT, lerp, pop, squash } from "../anim";
import { Bean, CAST } from "../components/Bean";
import { Ar, Bubble } from "../components/Bubble";
import { CatJump } from "../components/Cat";
import { Phone, phoneSize } from "../components/Phone";
import { C, FONT } from "../theme";

/**
 * Beat 1 — Hook (0–6 s, 180 frames)
 * A: Raka at a warung, confused about riba, phone in hand.
 * B: close-up of the phone (pengantar.png); the cat bursts out of the screen
 *    with "Yuk, belajar!", dives back in, camera plunges into the screen.
 */
export const HOOK_LEN = 180;
const CUT = 78; // A -> B

// Shared cue frames (also used by audio cues)
export const HOOK_CUES = {
  rakaIn: 2,
  thought: 10,
  catOut: 84,
  yuk: 92,
  catDive: 140,
  plunge: 150,
};

const Awning: React.FC<{ y?: number }> = ({ y = 0 }) => {
  const n = 12;
  const w = 1920 / n;
  return (
    <svg width={1920} height={170} style={{ position: "absolute", left: 0, top: y }}>
      <rect x={0} y={0} width={1920} height={92} fill={C.teal700} />
      {Array.from({ length: n }).map((_, i) => (
        <g key={i}>
          <rect x={i * w} y={0} width={w / 2} height={110} fill={C.white} />
          <path
            d={`M${i * w} 110 A ${w / 4} ${w / 4} 0 0 0 ${i * w + w / 2} 110 Z`}
            fill={C.white}
          />
          <rect x={i * w + w / 2} y={0} width={w / 2} height={110} fill={C.teal700} />
          <path
            d={`M${i * w + w / 2} 110 A ${w / 4} ${w / 4} 0 0 0 ${i * w + w} 110 Z`}
            fill={C.teal700}
          />
        </g>
      ))}
    </svg>
  );
};

const ShotA: React.FC<{ f: number }> = ({ f }) => {
  const rise = pop(f, HOOK_CUES.rakaIn, 11, 140);
  const [sx, sy] = squash(f, HOOK_CUES.rakaIn + 8, 0.06);
  const tilt = Math.sin(f / 9) * 2.5;
  const words: Array<[React.ReactNode, number]> = [
    ["Ini ", 10],
    [<Ar key="r">riba</Ar>, 15],
    [" bukan,", 20],
    [" ya?", 25],
  ];
  const bubbleIn = pop(f, HOOK_CUES.thought, 10, 180);
  const q = (start: number, x: number, y: number, rot: number, size: number) => {
    const s = pop(f, start, 8, 200);
    return (
      <div
        style={{
          position: "absolute",
          left: x,
          top: y + Math.sin((f + start) / 6) * 8,
          fontFamily: FONT,
          fontWeight: 900,
          fontSize: size,
          color: C.teal700,
          scale: String(s),
          rotate: `${rot + Math.sin((f + start) / 7) * 6}deg`,
        }}
      >
        ?
      </div>
    );
  };
  return (
    <AbsoluteFill
      style={{
        background: C.teal100,
        scale: String(lerp(f, [0, CUT], [1, 1.06])),
      }}
    >
      <Awning y={-20} />
      {/* counter */}
      <div
        style={{
          position: "absolute",
          left: -40,
          right: -40,
          top: 930,
          height: 200,
          background: C.sand,
          borderTop: `14px solid ${C.sandDark}`,
        }}
      />
      {/* jars on the counter */}
      {[1380, 1560, 1730].map((x, i) => (
        <div
          key={x}
          style={{
            position: "absolute",
            left: x,
            top: 800 - (i % 2) * 20,
            width: 120,
            height: 140 + (i % 2) * 20,
            borderRadius: "30px 30px 26px 26px",
            background: i === 1 ? C.teal300 : C.teal200,
            boxShadow: `0 6px 0 0 ${C.teal300}`,
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 18,
              right: 18,
              top: -22,
              height: 30,
              borderRadius: 10,
              background: C.teal700,
            }}
          />
        </div>
      ))}
      {/* Raka close-up */}
      <div
        style={{
          position: "absolute",
          left: -60,
          top: 0,
          width: 1250,
          height: 2000,
          translate: `0px ${lerp(rise, [0, 1], [900, -120])}px`,
          rotate: `${tilt}deg`,
          scale: `${sx} ${sy}`,
          transformOrigin: "50% 60%",
        }}
      >
        <Bean
          {...CAST.raka}
          acc="phone"
          expr="confused"
          armL={148}
          armR={8}
          look={-0.6}
          blink={f > 40 && f < 44 ? 1 : 0}
          height={2000}
          style={{ left: 0, top: 0 }}
        />
      </div>
      {q(30, 900, 170, -14, 120)}
      {q(36, 985, 110, 12, 84)}
      {/* thought bubble */}
      <div
        style={{
          position: "absolute",
          left: 1010,
          top: 330,
          scale: String(bubbleIn),
          transformOrigin: "0% 100%",
        }}
      >
        <Bubble fontSize={76} tail="left" style={{ left: 0, top: 0 }}>
          {words.map(([w, start], i) => (
            <span
              key={i}
              style={{
                display: "inline-block",
                whiteSpace: "pre",
                scale: String(pop(f, start, 9, 220)),
                translate: `0px ${lerp(f, [start, start + 6], [20, 0], EASE_OUT)}px`,
              }}
            >
              {w}
            </span>
          ))}
        </Bubble>
      </div>
    </AbsoluteFill>
  );
};

const SCREEN_W = 400;
const P = phoneSize(SCREEN_W);
const PHONE_LEFT = 960 - P.w / 2 - 120;
const PHONE_TOP = 96;
// point inside the screen we plunge into: a blank white band near the bottom of pengantar.png
const PLUNGE = {
  x: PHONE_LEFT + P.bezel + SCREEN_W * 0.5,
  y: PHONE_TOP + P.bezel + P.screenH * 0.875,
};
const SCREEN_CENTER = {
  x: PHONE_LEFT + P.w / 2,
  y: PHONE_TOP + P.bezel + P.screenH * 0.45,
};

const Hand: React.FC = () => (
  // drawn BEHIND the phone: only palm/fingers outside the phone body show
  <svg
    width={760}
    height={760}
    viewBox="0 0 760 760"
    style={{ position: "absolute", left: PHONE_LEFT - 160, top: 520, overflow: "visible" }}
  >
    <rect x={260} y={420} width={300} height={500} rx={120} fill={C.skin2} />
    <path d="M140 380 C110 520 190 640 330 640 L520 640 C580 640 600 560 600 520 L600 360 Z" fill={C.skin2} />
    {/* thumb on the left */}
    <rect x={118} y={240} width={110} height={250} rx={55} fill={C.skin2} rotate={-8} />
    {/* fingers peeking on the right */}
    {[150, 240, 330].map((y) => (
      <rect key={y} x={560} y={y} width={120} height={78} rx={39} fill={C.skin2} />
    ))}
    <rect x={540} y={420} width={110} height={70} rx={35} fill={C.skin2} />
  </svg>
);

const ShotB: React.FC<{ f: number }> = ({ f }) => {
  const g = f; // absolute frame in Hook
  const inScale = lerp(g, [CUT, CUT + 12], [1.08, 1], EASE_OUT);
  const plunge = lerp(g, [HOOK_CUES.plunge, HOOK_LEN], [0, 1], EASE_IN);
  const zoom = 1 + plunge * 11;
  const rot = lerp(g, [CUT, HOOK_CUES.plunge], [-6, -4]) * (1 - plunge);

  // Cat: bursts from screen centre to the upper right, then dives back in.
  const out = pop(g, HOOK_CUES.catOut, 10, 150);
  const dive = lerp(g, [HOOK_CUES.catDive, HOOK_CUES.catDive + 12], [0, 1], EASE_IN_OUT);
  const restX = 1430;
  const restY = 560;
  const catX = SCREEN_CENTER.x + (restX - SCREEN_CENTER.x) * out * (1 - dive);
  const catY = SCREEN_CENTER.y + (restY - SCREEN_CENTER.y) * out * (1 - dive);
  const catScale = Math.max(0, (0.15 + 0.85 * Math.min(out, 1.2)) * (1 - dive * 0.9));
  const [csx, csy] = squash(g, HOOK_CUES.catOut + 7, 0.16);
  const catVisible = g >= HOOK_CUES.catOut && g < HOOK_CUES.catDive + 12;
  const bob = Math.sin(g / 6) * 10;

  const yuk = pop(g, HOOK_CUES.yuk, 9, 200);
  const yukOut = lerp(g, [HOOK_CUES.catDive + 3, HOOK_CUES.catDive + 9], [1, 0], EASE_IN);

  return (
    <AbsoluteFill style={{ background: C.teal100, overflow: "hidden" }}>
      {/* soft rings behind the phone */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: SCREEN_CENTER.x - (380 + i * 170),
            top: SCREEN_CENTER.y - (380 + i * 170),
            width: (380 + i * 170) * 2,
            height: (380 + i * 170) * 2,
            borderRadius: "50%",
            border: `40px solid ${C.white}`,
            opacity: 0.55 - i * 0.15,
            scale: String(1 + Math.sin((g - i * 6) / 10) * 0.02),
          }}
        />
      ))}
      <AbsoluteFill
        style={{
          transformOrigin: `${PLUNGE.x}px ${PLUNGE.y}px`,
          scale: String(inScale * zoom),
          rotate: `${rot}deg`,
        }}
      >
        <Hand />
        <Phone screen="pengantar" width={SCREEN_W} style={{ left: PHONE_LEFT, top: PHONE_TOP }} />
      </AbsoluteFill>
      {catVisible ? (
        <div
          style={{
            position: "absolute",
            left: catX - 150,
            top: catY - 170 + (dive > 0 ? 0 : bob * out),
            width: 300,
            height: 340,
            scale: `${catScale * csx} ${catScale * csy}`,
            rotate: `${lerp(out, [0, 1], [-30, 8]) + dive * -40}deg`,
            transformOrigin: "50% 80%",
          }}
        >
          <CatJump height={340} style={{ left: 0, top: 0 }} />
        </div>
      ) : null}
      {g >= HOOK_CUES.yuk && yukOut > 0 ? (
        <div
          style={{
            position: "absolute",
            left: 1150,
            top: 170,
            scale: String(yuk * yukOut),
            transformOrigin: "0% 100%",
          }}
        >
          <Bubble fontSize={84} tail="bottom-left" style={{ left: 0, top: 0 }}>
            Yuk, belajar!
          </Bubble>
        </div>
      ) : null}
      {/* white bloom as we reach the blank part of the screen */}
      <AbsoluteFill
        style={{ background: C.white, opacity: lerp(g, [HOOK_LEN - 8, HOOK_LEN], [0, 1]) }}
      />
    </AbsoluteFill>
  );
};

export const Hook: React.FC = () => {
  const f = useCurrentFrame();
  return f < CUT ? <ShotA f={f} /> : <ShotB f={f} />;
};
