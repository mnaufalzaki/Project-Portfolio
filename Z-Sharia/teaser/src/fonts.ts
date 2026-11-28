import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import { FONT } from "./theme";

const faces: Array<[string, "normal" | "italic"]> = [
  ["600", "normal"],
  ["800", "normal"],
  ["900", "normal"],
  ["600", "italic"],
  ["800", "italic"],
  ["900", "italic"],
];

export const fontsLoaded = Promise.all(
  faces.map(([weight, style]) =>
    loadFont({
      family: FONT,
      url: staticFile(`fonts/nunito-latin-${weight}-${style}.woff2`),
      weight,
      style,
      display: "block",
    }),
  ),
);
