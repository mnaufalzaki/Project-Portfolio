import React from "react";
import { Img, staticFile } from "remotion";
import { C, SHOT_H, SHOT_W } from "../theme";

export type ScreenName =
  | "beranda"
  | "pengantar"
  | "soal"
  | "selesai"
  | "streak"
  | "liga"
  | "profil";

/**
 * Flat phone mockup. The screenshot is shown whole, at its native aspect
 * ratio (no crop, no redraw, no fake status bar). `width` is the SCREEN width.
 * Depth = solid bottom edge, no soft shadow.
 */
export const Phone: React.FC<{
  screen: ScreenName;
  width: number;
  bezel?: number;
  body?: string;
  edge?: string;
  style?: React.CSSProperties;
}> = ({ screen, width, bezel, body = C.ink, edge = "#151B1A", style }) => {
  const b = bezel ?? Math.round(width * 0.045);
  const screenH = (width * SHOT_H) / SHOT_W;
  const outerW = width + b * 2;
  const outerH = screenH + b * 2;
  const rOuter = Math.round(width * 0.12);
  const rInner = Math.max(6, rOuter - b);
  const edgeH = Math.max(4, Math.round(width * 0.018));
  return (
    <div
      style={{
        position: "absolute",
        width: outerW,
        height: outerH + edgeH,
        ...style,
      }}
    >
      {/* solid bottom edge */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: edgeH,
          width: outerW,
          height: outerH,
          borderRadius: rOuter,
          background: edge,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: outerW,
          height: outerH,
          borderRadius: rOuter,
          background: body,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: b,
          top: b,
          width,
          height: screenH,
          borderRadius: rInner,
          overflow: "hidden",
          background: C.white,
        }}
      >
        <Img
          src={staticFile(`screens/${screen}.png`)}
          style={{ width, height: screenH, display: "block" }}
        />
      </div>
    </div>
  );
};

export const phoneSize = (width: number) => {
  const b = Math.round(width * 0.045);
  const screenH = (width * SHOT_H) / SHOT_W;
  return {
    w: width + b * 2,
    h: screenH + b * 2 + Math.max(4, Math.round(width * 0.018)),
    bezel: b,
    screenH,
  };
};
