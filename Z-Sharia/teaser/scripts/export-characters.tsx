// Exports the original vector characters and reward icons as standalone SVG files.
// Run: npm run export:svg
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Bean, CAST } from "../src/components/Bean";
import { Chest, Coin, Flame, Trophy } from "../src/components/Icons";

const out = path.join(process.cwd(), "assets", "characters");
fs.mkdirSync(out, { recursive: true });

const clean = (svg: string, w: number, h: number) =>
  svg
    .replace(/<svg([^>]*?) style="[^"]*"/, `<svg$1 width="${w}" height="${h}"`)
    .replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');

const names: Record<keyof typeof CAST, string> = {
  raka: "raka_mahasiswa_berkacamata",
  nisa: "nisa_mahasiswi_berhijab",
  dimas: "dimas_mahasiswa",
  harun: "pak_harun_pedagang_pasar",
  fikri: "fikri_pegawai_bank_syariah",
};

for (const k of Object.keys(CAST) as Array<keyof typeof CAST>) {
  for (const [pose, props] of [
    ["idle", { expr: "happy" as const, armL: 12, armR: 12 }],
    ["wave", { expr: "happy" as const, armL: 12, armR: 150 }],
    ["cheer", { expr: "happy" as const, armL: 160, armR: 160 }],
  ] as const) {
    const svg = renderToStaticMarkup(<Bean {...CAST[k]} {...props} height={320} />);
    fs.writeFileSync(path.join(out, `${names[k]}_${pose}.svg`), clean(svg, 200, 320));
  }
}
const icons = { flame: Flame, coin: Coin, chest: Chest, trophy: Trophy };
for (const [n, I] of Object.entries(icons)) {
  fs.writeFileSync(path.join(out, `icon_${n}.svg`), clean(renderToStaticMarkup(<I size={100} />), 100, 100));
}
console.log("wrote", fs.readdirSync(out).length, "svg files to", out);
