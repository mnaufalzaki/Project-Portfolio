import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { EASE_IN_OUT, EASE_OUT, hop, lerp, pop, squash } from "../anim";
import { Bean, BeanProps, CAST } from "../components/Bean";
import { CatHead, CatJump } from "../components/Cat";
import { C, FONT } from "../theme";

/**
 * Beat 4 — Finale (25–30 s, 150 frames)
 * A: everyone bursts up in a beam of light and jumps with the cat.
 * B: teal logo card — Z-Sharia, tagline, SYLS 2026.
 */
export const FINALE_LEN = 150;
export const FINALE_CUES = {
  burst: 4,
  jump: 28,
  wipe: 49,
  logo: 60,
};

type Member = { who: keyof typeof CAST; x: number; h: number; rot: number; delay: number; expr: BeanProps["expr"] };
const CREW: Member[] = [
  { who: "dimas", x: 520, h: 440, rot: -10, delay: 6, expr: "wow" },
  { who: "harun", x: 1400, h: 440, rot: 10, delay: 7, expr: "happy" },
  { who: "nisa", x: 735, h: 470, rot: -5, delay: 3, expr: "happy" },
  { who: "fikri", x: 1185, h: 470, rot: 5, delay: 4, expr: "happy" },
  { who: "raka", x: 960, h: 500, rot: 0, delay: 1, expr: "happy" },
];

const Crowd: React.FC<{ f: number }> = ({ f }) => {
  const beam = lerp(f, [0, 10], [0, 1], EASE_OUT);
  const j = hop(f, FINALE_CUES.jump, 22) * 130;
  const [sx, sy] = squash(f, FINALE_CUES.jump + 22, 0.09);
  return (
    <AbsoluteFill style={{ background: C.teal100, overflow: "hidden" }}>
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
        <polygon
          points={`${960 - 160 * beam},1080 ${960 + 160 * beam},1080 ${960 + 900 * beam},-40 ${960 - 900 * beam},-40`}
          fill={C.white}
        />
      </svg>
      {CREW.map((m) => {
        const up = pop(f, FINALE_CUES.burst + m.delay * 0.6, 11, 150);
        const p = CAST[m.who];
        const armUp = 155 + Math.sin(f / 4 + m.delay) * 14;
        return (
          <div
            key={m.who}
            style={{
              position: "absolute",
              left: m.x - (m.h * 200) / 320 / 2,
              top: 1010 - m.h,
              width: (m.h * 200) / 320,
              height: m.h,
              translate: `0px ${lerp(up, [0, 1], [900, 0]) - j}px`,
              rotate: `${m.rot + Math.sin(f / 7 + m.delay) * 3}deg`,
              scale: `${sx} ${sy}`,
              transformOrigin: "50% 100%",
            }}
          >
            <Bean {...p} expr={m.expr} armL={armUp} armR={armUp + 6} height={m.h} style={{ left: 0, top: 0 }} />
          </div>
        );
      })}
      {/* the cat, front and centre */}
      {(() => {
        const up = pop(f, FINALE_CUES.burst, 10, 160);
        return (
          <div
            style={{
              position: "absolute",
              left: 960 - 150,
              top: 1060 - 340,
              width: 300,
              height: 340,
              translate: `0px ${lerp(up, [0, 1], [900, 0]) - j * 1.25}px`,
              rotate: `${Math.sin(f / 6) * 6}deg`,
              scale: `${sx} ${sy}`,
              transformOrigin: "50% 100%",
            }}
          >
            <CatJump height={340} style={{ left: 0, top: 0 }} />
          </div>
        );
      })()}
    </AbsoluteFill>
  );
};

const Logo: React.FC<{ f: number }> = ({ f }) => {
  const card = pop(f, FINALE_CUES.logo, 11, 170);
  const tile = pop(f, FINALE_CUES.logo + 6, 9, 200);
  const word = "Z-Sharia".split("");
  const tag = lerp(f, [FINALE_CUES.logo + 20, FINALE_CUES.logo + 32], [0, 1], EASE_OUT);
  const pill = pop(f, FINALE_CUES.logo + 30, 10, 190);
  return (
    <>
      {/* floating dots for life (teal-100 on teal-500, no text) */}
      {[
        [180, 180, 40],
        [1720, 220, 56],
        [260, 860, 64],
        [1640, 880, 36],
        [980, 70, 28],
      ].map(([x, y, r], i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: x - r,
            top: y - r + Math.sin(f / 9 + i) * 12,
            width: r * 2,
            height: r * 2,
            borderRadius: r,
            background: C.teal100,
            opacity: 0.35,
            scale: String(pop(f, FINALE_CUES.logo + i * 2, 10, 160)),
          }}
        />
      ))}
      <div
        style={{
          position: "absolute",
          left: 260,
          top: 190,
          width: 1400,
          height: 520,
          borderRadius: 56,
          background: C.white,
          boxShadow: `0 14px 0 0 ${C.teal700}`,
          scale: String(card),
        }}
      >
        <div style={{ position: "absolute", left: 0, right: 0, top: 70, display: "flex", justifyContent: "center", alignItems: "center", gap: 48 }}>
          <div
            style={{
              position: "relative",
              width: 230,
              height: 230,
              borderRadius: 52,
              background: C.white,
              border: `6px solid ${C.neutral300}`,
              boxShadow: `0 8px 0 0 ${C.neutral300}`,
              scale: String(tile),
              rotate: `${lerp(tile, [0, 1], [-20, 0])}deg`,
              overflow: "hidden",
            }}
          >
            <CatHead size={196} style={{ left: 11, top: 22 }} />
          </div>
          <div style={{ fontFamily: FONT, fontWeight: 900, fontSize: 176, color: C.teal700, letterSpacing: -2, lineHeight: 1 }}>
            {word.map((ch, i) => (
              <span
                key={i}
                style={{
                  display: "inline-block",
                  color: ch === "-" ? C.gold : C.teal700,
                  scale: String(pop(f, FINALE_CUES.logo + 10 + i * 1.5, 9, 220)),
                  translate: `0px ${lerp(f, [FINALE_CUES.logo + 10 + i * 1.5, FINALE_CUES.logo + 18 + i * 1.5], [40, 0], EASE_OUT)}px`,
                }}
              >
                {ch}
              </span>
            ))}
          </div>
        </div>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 352,
            textAlign: "center",
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 54,
            color: C.ink,
            opacity: tag,
            translate: `0px ${(1 - tag) * 24}px`,
          }}
        >
          Melek keuangan syariah, satu pelajaran sehari
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 960,
          top: 790,
          translate: "-50% 0px",
          scale: String(pill),
          background: C.teal700,
          color: C.white,
          borderRadius: 50,
          boxShadow: `0 8px 0 0 ${C.teal800}`,
          padding: "18px 56px 20px",
          fontFamily: FONT,
          fontWeight: 900,
          fontSize: 56,
          letterSpacing: 8,
        }}
      >
        SYLS 2026
      </div>
    </>
  );
};

export const Finale: React.FC = () => {
  const f = useCurrentFrame();
  const r = lerp(f, [FINALE_CUES.wipe, FINALE_CUES.logo + 2], [0, 1250], EASE_IN_OUT);
  return (
    <AbsoluteFill style={{ background: C.teal100 }}>
      {f < FINALE_CUES.logo + 2 ? <Crowd f={f} /> : null}
      {f >= FINALE_CUES.wipe ? (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <div
            style={{
              position: "absolute",
              left: 960 - r,
              top: 600 - r,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              background: C.teal500,
            }}
          />
          {f >= FINALE_CUES.logo ? <Logo f={f} /> : null}
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
