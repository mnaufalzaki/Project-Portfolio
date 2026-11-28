import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { EASE_IN_OUT, EASE_OUT, hop, lerp, pop, squash } from "../anim";
import { Bean, CAST } from "../components/Bean";
import { Label } from "../components/Bubble";
import { CatJump } from "../components/Cat";
import { Coin, Sparkle } from "../components/Icons";
import { Phone, ScreenName } from "../components/Phone";
import { C, FONT } from "../theme";

/**
 * Beat 2 — Learning journey (6–18 s, 360 frames)
 * Raka + the cat surf on a phone through three everyday-finance places.
 * The camera trucks right (like the reference's gallery pan), passing through
 * a giant phone frame between places. In each place one screenshot card
 * bounces in with one short label.
 */
export const JOURNEY_LEN = 360;

export const JOURNEY_CUES = {
  pan1: 104,
  pan2: 224,
  hop1: 100,
  hop2: 220,
  cards: [10, 136, 258] as const, // drop starts; lands ~ +9
  coin1: 270,
  coin2: 277,
};
const LAND = 9;
const PAN_LEN = 30;

const camX = (f: number) =>
  lerp(f, [JOURNEY_CUES.pan1, JOURNEY_CUES.pan1 + PAN_LEN], [0, 1920], EASE_IN_OUT) +
  lerp(f, [JOURNEY_CUES.pan2, JOURNEY_CUES.pan2 + PAN_LEN], [0, 1920], EASE_IN_OUT);

const panSpeed = (f: number) => Math.abs(camX(f + 1) - camX(f));

const PANELS: Array<{
  bg: string;
  screen: ScreenName;
  label: string;
  labelIn: number;
  labelOut: number;
}> = [
  { bg: "#FFF4E2", screen: "beranda", label: "Belajar 5 menit sehari", labelIn: 28, labelOut: 100 },
  { bg: C.teal100, screen: "soal", label: "Kuis interaktif", labelIn: 150, labelOut: 220 },
  { bg: "#F3F9F8", screen: "selesai", label: "Kumpulkan XP", labelIn: 274, labelOut: 356 },
];

const WAVE_Y = 884;

const waveY = (x: number, phase: number) =>
  WAVE_Y + 16 * Math.sin((x + phase) / 150) + 7 * Math.sin((x + phase * 1.3) / 61);

const Wave: React.FC<{ phase: number }> = ({ phase }) => {
  const pts: string[] = [];
  for (let x = -20; x <= 1940; x += 20) pts.push(`${x},${waveY(x, phase).toFixed(1)}`);
  const foam: React.ReactNode[] = [];
  for (let x = -40; x <= 1960; x += 44) {
    const xx = x - ((phase * 0.9) % 44);
    foam.push(<circle key={x} cx={xx} cy={waveY(xx, phase) + 2} r={15} fill={C.white} />);
  }
  return (
    <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
      {foam}
      <polygon points={`-20,1100 ${pts.join(" ")} 1940,1100`} fill={C.teal500} />
      <polygon
        points={`-20,1100 ${pts.map((p) => {
          const [x, y] = p.split(",").map(Number);
          return `${x},${y + 90}`;
        }).join(" ")} 1940,1100`}
        fill={C.teal600}
      />
    </svg>
  );
};

const Stall: React.FC<{ x: number; w: number; stripe: string; y?: number }> = ({ x, w, stripe, y = 400 }) => {
  const n = Math.round(w / 80);
  const sw = w / n;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: 900 - y }}>
      <div style={{ position: "absolute", left: 20, top: 40, width: 22, height: 900, background: C.teal700, borderRadius: 11 }} />
      <div style={{ position: "absolute", right: 20, top: 40, width: 22, height: 900, background: C.teal700, borderRadius: 11 }} />
      <svg width={w} height={130} style={{ position: "absolute", left: 0, top: 0 }}>
        {Array.from({ length: n }).map((_, i) => (
          <g key={i}>
            <rect x={i * sw} y={0} width={sw} height={84} fill={i % 2 ? C.white : stripe} />
            <path d={`M${i * sw} 84 A ${sw / 2} ${sw / 2} 0 0 0 ${(i + 1) * sw} 84 Z`} fill={i % 2 ? C.white : stripe} />
          </g>
        ))}
        <rect x={0} y={0} width={w} height={16} fill={C.teal700} rx={8} />
      </svg>
    </div>
  );
};

const Produce: React.FC<{ x: number; y: number; color: string; n?: number }> = ({ x, y, color, n = 6 }) => (
  <svg width={220} height={120} style={{ position: "absolute", left: x, top: y, overflow: "visible" }}>
    {Array.from({ length: n }).map((_, i) => {
      const row = i < 3 ? 0 : 1;
      const cx = 40 + (i % 3) * 56 + row * 28;
      const cy = 90 - row * 42;
      return <circle key={i} cx={cx} cy={cy} r={30} fill={color} />;
    })}
  </svg>
);

const Tree: React.FC<{ x: number; s?: number }> = ({ x, s = 1 }) => (
  <div style={{ position: "absolute", left: x, top: 880 - 520 * s, width: 300 * s, height: 520 * s }}>
    <div style={{ position: "absolute", left: 130 * s, top: 250 * s, width: 40 * s, height: 280 * s, background: C.teal800, borderRadius: 20 * s }} />
    <div style={{ position: "absolute", left: 0, top: 60 * s, width: 300 * s, height: 260 * s, background: C.teal600, borderRadius: 130 * s }} />
    <div style={{ position: "absolute", left: 50 * s, top: 0, width: 200 * s, height: 200 * s, background: C.teal500, borderRadius: 100 * s }} />
  </div>
);

const Bunting: React.FC<{ x: number; w: number; y: number; f: number }> = ({ x, w, y, f }) => (
  <svg width={w} height={120} style={{ position: "absolute", left: x, top: y, overflow: "visible" }}>
    <path d={`M0 10 Q ${w / 2} 60 ${w} 10`} stroke={C.teal700} strokeWidth={5} fill="none" />
    {Array.from({ length: 12 }).map((_, i) => {
      const t = (i + 0.5) / 12;
      const px = t * w;
      const py = 10 + 4 * 50 * t * (1 - t);
      const sw = Math.sin(f / 8 + i) * 6;
      const col = [C.teal500, C.white, C.teal700][i % 3];
      return <path key={i} d={`M${px - 24} ${py} L${px + 24} ${py} L${px + sw} ${py + 56} Z`} fill={col} />;
    })}
  </svg>
);

const wave = (f: number, phase = 0) => 150 + 22 * Math.sin(f / 4.5 + phase);

const PanelPasar: React.FC<{ f: number }> = ({ f }) => (
  <>
    <Bunting x={200} w={1500} y={20} f={f} />
    <Stall x={-60} w={520} stripe={C.teal700} y={430} />
    <div style={{ position: "absolute", left: -60, top: 740, width: 520, height: 160, background: C.sand, borderRadius: 18, boxShadow: `0 8px 0 0 ${C.sandDark}` }} />
    <Produce x={0} y={640} color={C.teal300} />
    <Produce x={220} y={640} color={C.sandDark} />
    <Stall x={640} w={560} stripe={C.teal500} y={380} />
    <Bean {...CAST.harun} expr="happy" armR={wave(f)} armL={20} height={400} style={{ left: 790, top: 880 - 395 }} />
    <div style={{ position: "absolute", left: 640, top: 720, width: 560, height: 180, background: C.sand, borderRadius: 18, boxShadow: `0 8px 0 0 ${C.sandDark}` }} />
    <Produce x={660} y={620} color={C.teal600} />
    <Produce x={900} y={620} color={C.teal300} n={5} />
    <div style={{ position: "absolute", left: 1500, top: 700, width: 170, height: 190, background: C.sandDark, borderRadius: "60px 60px 30px 30px" }} />
    <div style={{ position: "absolute", left: 1640, top: 730, width: 150, height: 160, background: C.sand, borderRadius: "50px 50px 26px 26px" }} />
  </>
);

const PanelKampus: React.FC<{ f: number }> = ({ f }) => (
  <>
    <Tree x={-40} s={1.1} />
    <Tree x={1640} s={0.95} />
    {/* faculty building */}
    <div style={{ position: "absolute", left: 520, top: 330, width: 760, height: 570, background: C.white, borderRadius: 18 }} />
    <svg width={860} height={180} style={{ position: "absolute", left: 470, top: 170 }}>
      <path d="M20 170 L430 16 L840 170 Z" fill={C.teal700} />
      <circle cx={430} cy={112} r={34} fill={C.teal100} />
    </svg>
    {[0, 1, 2, 3, 4, 5].map((i) => (
      <div key={i} style={{ position: "absolute", left: 560 + i * 128, top: 380, width: 48, height: 470, background: C.teal200, borderRadius: 24 }} />
    ))}
    <div style={{ position: "absolute", left: 470, top: 840, width: 860, height: 60, background: C.teal200, borderRadius: 14 }} />
    <Bean {...CAST.nisa} expr="happy" armL={wave(f, 1)} armR={30} height={380} style={{ left: 770, top: 884 - 376 }} />
    <Bean {...CAST.dimas} expr="wow" armR={wave(f, 2.2)} armL={18} look={-1} height={390} style={{ left: 990, top: 884 - 386 }} />
  </>
);

const PanelBank: React.FC<{ f: number }> = ({ f }) => (
  <>
    <div style={{ position: "absolute", left: 480, top: 300, width: 820, height: 600, background: C.teal700, borderRadius: 26 }} />
    <div style={{ position: "absolute", left: 480, top: 300, width: 820, height: 40, background: C.teal800, borderRadius: "26px 26px 0 0" }} />
    <div
      style={{
        position: "absolute",
        left: 560,
        top: 370,
        width: 660,
        height: 92,
        background: C.white,
        borderRadius: 20,
        boxShadow: `0 6px 0 0 ${C.teal800}`,
        fontFamily: FONT,
        fontWeight: 900,
        fontSize: 52,
        color: C.teal700,
        letterSpacing: 6,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      BANK SYARIAH
    </div>
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ position: "absolute", left: 560 + i * 240, top: 520, width: 180, height: 220, background: C.teal100, borderRadius: "90px 90px 16px 16px" }} />
    ))}
    <div style={{ position: "absolute", left: 1540, top: 760, width: 120, height: 130, background: C.teal700, borderRadius: "16px 16px 36px 36px" }} />
    <div style={{ position: "absolute", left: 1500, top: 600, width: 200, height: 190, background: C.teal500, borderRadius: 100 }} />
    <Bean {...CAST.fikri} expr="happy" armR={wave(f, 0.6)} armL={16} height={390} style={{ left: 850, top: 884 - 386 }} />
  </>
);

/** Giant empty phone frame standing at a panel boundary: we pass through it. */
const Portal: React.FC<{ x: number }> = ({ x }) => (
  <div
    style={{
      position: "absolute",
      left: x - 300,
      top: 90,
      width: 600,
      height: 1100,
      borderRadius: 90,
      border: `44px solid ${C.ink}`,
      boxShadow: `0 10px 0 0 #151B1A`,
    }}
  />
);

export const Journey: React.FC = () => {
  const f = useCurrentFrame();
  const cam = camX(f);
  const speed = panSpeed(f);
  const phase = cam * 0.8 + f * 7;

  // surfer
  const hopY =
    hop(f, JOURNEY_CUES.hop1, 26) * 150 + hop(f, JOURNEY_CUES.hop2, 26) * 150;
  const [sx1, sy1] = squash(f, JOURNEY_CUES.hop1 + 26, 0.1);
  const [sx2, sy2] = squash(f, JOURNEY_CUES.hop2 + 26, 0.1);
  const sx = f > JOURNEY_CUES.hop2 ? sx2 : sx1;
  const sy = f > JOURNEY_CUES.hop2 ? sy2 : sy1;
  const boardX = 520;
  const boardY = waveY(boardX, phase) - 6 - hopY;
  const boardTilt = 6 * Math.cos((boardX + phase) / 150) + Math.sin(f / 7) * 2 - lerp(speed, [0, 90], [0, 8]);
  const intro = lerp(f, [0, 16], [1.35, 1], EASE_OUT);

  return (
    <AbsoluteFill style={{ background: C.white, overflow: "hidden" }}>
      <AbsoluteFill style={{ scale: String(intro), transformOrigin: "50% 60%" }}>
        {/* world (scenery + cards) */}
        <AbsoluteFill style={{ translate: `${-cam}px 0px` }}>
          {PANELS.map((p, i) => (
            <div key={i} style={{ position: "absolute", left: i * 1920, top: 0, width: 1920, height: 1080, background: p.bg, overflow: "hidden" }}>
              {i === 0 ? <PanelPasar f={f} /> : i === 1 ? <PanelKampus f={f} /> : <PanelBank f={f} />}
            </div>
          ))}
          <Portal x={1920} />
          <Portal x={3840} />
        </AbsoluteFill>

        {/* speed streaks during pans */}
        {speed > 5
          ? [180, 330, 520, 700].map((y, i) => (
              <div
                key={y}
                style={{
                  position: "absolute",
                  left: 1920 - ((i * 523 + f * 90) % 2400),
                  top: y,
                  width: 420,
                  height: 14,
                  borderRadius: 7,
                  background: C.white,
                  opacity: lerp(speed, [5, 90], [0, 0.85]),
                }}
              />
            ))
          : null}

        <Wave phase={phase} />

        {/* surfer: Raka + cat riding a phone */}
        <div
          style={{
            position: "absolute",
            left: boardX - 230,
            top: boardY - 560,
            width: 460,
            height: 600,
            rotate: `${boardTilt}deg`,
            transformOrigin: "50% 95%",
            scale: `${sx} ${sy}`,
          }}
        >
          <Bean
            {...CAST.raka}
            expr={speed > 20 ? "wow" : "happy"}
            armL={100 + Math.sin(f / 6) * 10}
            armR={70 + Math.sin(f / 5) * 10}
            height={350}
            style={{ left: 40, top: 556 - 350 * (316 / 320) }}
          />
          <CatJump height={220} style={{ left: 230, top: 556 - 214, rotate: `${Math.sin(f / 5) * 5}deg` }} />
          {/* the phone-board (side view) */}
          <div style={{ position: "absolute", left: 0, top: 552, width: 460, height: 40, borderRadius: 20, background: C.ink, boxShadow: `0 6px 0 0 #151B1A` }} />
          <div style={{ position: "absolute", left: 24, top: 552, width: 412, height: 10, borderRadius: 5, background: C.teal300 }} />
        </div>

        {/* screenshot cards (world space, so they ride the pan) */}
        {PANELS.map((p, i) => {
          const start = JOURNEY_CUES.cards[i];
          if (f < start) return null;
          const d = pop(f, start, 10, 160);
          const [csx, csy] = squash(f, start + LAND, 0.08);
          const x = i * 1920 + 1240 - cam;
          return (
            <div
              key={p.screen}
              style={{
                position: "absolute",
                left: x,
                top: 108,
                width: 372,
                height: 780,
                translate: `0px ${lerp(d, [0, 1], [-1100, 0])}px`,
                rotate: `${lerp(d, [0, 1], [14, 3])}deg`,
                scale: `${csx} ${csy}`,
                transformOrigin: "50% 100%",
              }}
            >
              <Phone screen={p.screen} width={340} style={{ left: 0, top: 0 }} />
            </div>
          );
        })}

        {/* XP coins + sparkles burst from the "selesai" card */}
        {f >= JOURNEY_CUES.coin1
          ? [0, 1, 2, 3].map((k) => {
              const st = JOURNEY_CUES.coin1 + k * 4;
              const t = lerp(f, [st, st + 22], [0, 1], EASE_OUT);
              const vis = lerp(f, [st, st + 3, st + 40, st + 50], [0, 1, 1, 0]);
              const ang = (-150 + k * 34) * (Math.PI / 180);
              const cx = 3840 + 1420 - cam + Math.cos(ang) * 320 * t;
              const cy = 200 + Math.sin(ang) * 220 * t + 80 * t * t;
              return k % 2 === 0 ? (
                <Coin key={k} size={92} style={{ left: cx - 46, top: cy - 46, opacity: vis, scale: String(pop(f, st, 8, 200)) }} />
              ) : (
                <Sparkle key={k} size={70} style={{ left: cx - 35, top: cy - 35, opacity: vis, rotate: `${f * 4}deg` }} />
              );
            })
          : null}

        {/* one label per place */}
        {PANELS.map((p) => {
          if (f < p.labelIn - 1 || f > p.labelOut + 8) return null;
          const s = pop(f, p.labelIn, 10, 190);
          const out = lerp(f, [p.labelOut, p.labelOut + 8], [1, 0], EASE_IN_OUT);
          return (
            <Label
              key={p.label}
              fontSize={76}
              style={{
                left: 110,
                top: 110,
                scale: String(Math.max(0, s * out)),
                transformOrigin: "0% 50%",
                rotate: `${lerp(s, [0, 1], [-6, 0])}deg`,
              }}
            >
              {p.label}
            </Label>
          );
        })}
      </AbsoluteFill>
      <AbsoluteFill style={{ background: C.white, opacity: lerp(f, [0, 10], [1, 0]) }} />
    </AbsoluteFill>
  );
};
