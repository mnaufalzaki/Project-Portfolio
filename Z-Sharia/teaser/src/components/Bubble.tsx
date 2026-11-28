import React from "react";
import { C, FONT } from "../theme";

/** White speech bubble with a solid bottom edge and a tail. */
export const Bubble: React.FC<{
  children: React.ReactNode;
  fontSize?: number;
  tail?: "left" | "right" | "bottom-left" | "bottom-right";
  style?: React.CSSProperties;
  pad?: [number, number];
}> = ({ children, fontSize = 64, tail = "bottom-left", style, pad = [28, 44] }) => {
  const edge = Math.round(fontSize * 0.09);
  const tailSize = fontSize * 0.55;
  const tailStyle: React.CSSProperties =
    tail === "bottom-left"
      ? { left: fontSize * 0.7, bottom: -tailSize * 0.62 - edge, rotate: "45deg" }
      : tail === "bottom-right"
        ? { right: fontSize * 0.7, bottom: -tailSize * 0.62 - edge, rotate: "45deg" }
        : tail === "left"
          ? { left: -tailSize * 0.45, top: "42%", rotate: "45deg" }
          : { right: -tailSize * 0.45, top: "42%", rotate: "45deg" };
  return (
    <div style={{ position: "absolute", ...style }}>
      <div
        style={{
          position: "relative",
          background: C.white,
          borderRadius: fontSize * 0.42,
          boxShadow: `0 ${edge}px 0 0 ${C.neutral300}`,
          padding: `${pad[0]}px ${pad[1]}px`,
          fontFamily: FONT,
          fontWeight: 900,
          fontSize,
          color: C.ink,
          whiteSpace: "nowrap",
          lineHeight: 1.1,
        }}
      >
        <div
          style={{
            position: "absolute",
            width: tailSize,
            height: tailSize,
            background: C.white,
            borderRadius: 6,
            boxShadow:
              tail.startsWith("bottom") ? `${edge * 0.7}px ${edge * 0.7}px 0 0 ${C.neutral300}` : undefined,
            ...tailStyle,
          }}
        />
        <span style={{ position: "relative" }}>{children}</span>
      </div>
    </div>
  );
};

/** Big pill label: one short message per scene. */
export const Label: React.FC<{
  children: React.ReactNode;
  fontSize?: number;
  bg?: string;
  color?: string;
  edge?: string;
  style?: React.CSSProperties;
}> = ({
  children,
  fontSize = 72,
  bg = C.white,
  color = C.teal700,
  edge = C.neutral300,
  style,
}) => {
  const e = Math.round(fontSize * 0.1);
  return (
    <div
      style={{
        position: "absolute",
        background: bg,
        color,
        borderRadius: fontSize * 0.5,
        boxShadow: `0 ${e}px 0 0 ${edge}`,
        padding: `${fontSize * 0.3}px ${fontSize * 0.62}px ${fontSize * 0.34}px`,
        fontFamily: FONT,
        fontWeight: 900,
        fontSize,
        lineHeight: 1.05,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** Arabic-origin terms are italicised. */
export const Ar: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={{ fontStyle: "italic" }}>{children}</span>
);
