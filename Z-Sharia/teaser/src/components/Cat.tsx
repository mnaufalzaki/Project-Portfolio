import React from "react";
import { Img, staticFile } from "remotion";

/**
 * The Z-Sharia cat, straight from the provided maskot_final.png
 * (cut out to transparent PNGs by tools/cutout_mascot.py).
 * Native sizes: jump 298x341, head 360x357 — keep display size near these
 * so the bitmap stays crisp.
 */
export const CatJump: React.FC<{
  height: number;
  style?: React.CSSProperties;
  flip?: boolean;
}> = ({ height, style, flip }) => (
  <Img
    src={staticFile("mascot/cat_jump.png")}
    style={{
      position: "absolute",
      height,
      width: (height * 298) / 341,
      scale: flip ? "-1 1" : undefined,
      ...style,
    }}
  />
);

export const CatHead: React.FC<{ size: number; style?: React.CSSProperties }> = ({
  size,
  style,
}) => (
  <Img
    src={staticFile("mascot/cat_head.png")}
    style={{ position: "absolute", width: size, height: (size * 357) / 360, ...style }}
  />
);
