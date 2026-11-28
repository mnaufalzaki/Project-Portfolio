import React from "react";
import { AbsoluteFill } from "remotion";
import { Bean, CAST } from "./components/Bean";
import { CatJump, CatHead } from "./components/Cat";
import { Flame, Coin, Chest, Trophy } from "./components/Icons";
import { Phone } from "./components/Phone";
import { C } from "./theme";

export const CastSheet: React.FC = () => (
  <AbsoluteFill style={{ background: C.teal100 }}>
    <Bean {...CAST.raka} expr="confused" acc="phone" armL={150} height={420} style={{ left: 40, top: 80 }} />
    <Bean {...CAST.nisa} expr="happy" armL={160} height={420} style={{ left: 330, top: 80 }} />
    <Bean {...CAST.dimas} expr="wow" armR={150} height={420} style={{ left: 620, top: 80 }} />
    <Bean {...CAST.harun} expr="grin" armR={120} height={420} style={{ left: 910, top: 80 }} />
    <Bean {...CAST.fikri} expr="happy" armL={30} height={420} style={{ left: 1200, top: 80 }} />
    <CatJump height={340} style={{ left: 1500, top: 120 }} />
    <CatHead size={160} style={{ left: 60, top: 700 }} />
    <Flame size={120} style={{ left: 300, top: 720 }} />
    <Coin size={120} style={{ left: 460, top: 720 }} />
    <Chest size={120} style={{ left: 620, top: 720 }} />
    <Trophy size={120} style={{ left: 780, top: 720 }} />
    <Phone screen="beranda" width={200} style={{ left: 1000, top: 560 }} />
  </AbsoluteFill>
);
