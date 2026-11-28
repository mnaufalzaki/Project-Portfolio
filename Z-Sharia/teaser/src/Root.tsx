import React from "react";
import { Composition, continueRender, delayRender, Folder } from "remotion";
import { CastSheet } from "./CastSheet";
import { fontsLoaded } from "./fonts";
import { Finale, FINALE_LEN } from "./scenes/Finale";
import { Gamify, GAMIFY_LEN } from "./scenes/Gamify";
import { Hook, HOOK_LEN } from "./scenes/Hook";
import { Journey, JOURNEY_LEN } from "./scenes/Journey";
import { Teaser, TEASER_LEN } from "./Teaser";
import { FPS, H, W } from "./theme";

const handle = delayRender("fonts");
fontsLoaded.then(() => continueRender(handle));

const dims = { width: W, height: H, fps: FPS };

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="ZSharia-Teaser" component={Teaser} durationInFrames={TEASER_LEN} {...dims} />
    <Folder name="Scenes">
      <Composition id="Hook" component={Hook} durationInFrames={HOOK_LEN} {...dims} />
      <Composition id="Journey" component={Journey} durationInFrames={JOURNEY_LEN} {...dims} />
      <Composition id="Gamify" component={Gamify} durationInFrames={GAMIFY_LEN} {...dims} />
      <Composition id="Finale" component={Finale} durationInFrames={FINALE_LEN} {...dims} />
      <Composition id="CastSheet" component={CastSheet} durationInFrames={1} {...dims} />
    </Folder>
  </>
);
