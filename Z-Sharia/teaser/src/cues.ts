import { FINALE_CUES } from "./scenes/Finale";
import { GAMIFY_CUES } from "./scenes/Gamify";
import { HOOK_CUES } from "./scenes/Hook";
import { JOURNEY_CUES } from "./scenes/Journey";

// Scene start frames on the master timeline (30 fps)
export const T = {
  hook: 0,
  journey: 180,
  gamify: 540,
  finale: 750,
  end: 900,
};

export type Sfx = "pop" | "pop_small" | "whoosh" | "coin" | "click" | "rise";
export type Cue = { at: number; sfx: Sfx; vol: number; note: string };

const J = T.journey;
const G = T.gamify;
const F = T.finale;

/** Every sound effect, pinned to the frame of the event it belongs to. */
export const CUES: Cue[] = [
  { at: T.hook + HOOK_CUES.rakaIn, sfx: "pop_small", vol: 0.55, note: "Raka bounces in" },
  { at: T.hook + HOOK_CUES.thought, sfx: "pop_small", vol: 0.45, note: "thought bubble" },
  { at: T.hook + HOOK_CUES.catOut, sfx: "pop", vol: 0.9, note: "cat jumps out of the phone" },
  { at: T.hook + HOOK_CUES.yuk, sfx: "pop_small", vol: 0.5, note: "'Yuk, belajar!' bubble" },
  { at: T.hook + HOOK_CUES.catDive, sfx: "pop", vol: 0.6, note: "cat dives back in" },
  { at: T.hook + HOOK_CUES.plunge, sfx: "whoosh", vol: 0.85, note: "camera plunges into the screen" },

  { at: J + JOURNEY_CUES.cards[0] + 9, sfx: "click", vol: 0.8, note: "beranda card lands" },
  { at: J + JOURNEY_CUES.hop1, sfx: "pop", vol: 0.7, note: "surfer hops" },
  { at: J + JOURNEY_CUES.pan1, sfx: "whoosh", vol: 0.7, note: "pan through phone portal" },
  { at: J + JOURNEY_CUES.cards[1] + 9, sfx: "click", vol: 0.8, note: "soal card lands" },
  { at: J + JOURNEY_CUES.hop2, sfx: "pop", vol: 0.7, note: "surfer hops" },
  { at: J + JOURNEY_CUES.pan2, sfx: "whoosh", vol: 0.7, note: "pan through phone portal" },
  { at: J + JOURNEY_CUES.cards[2] + 9, sfx: "click", vol: 0.8, note: "selesai card lands" },
  { at: J + JOURNEY_CUES.coin1, sfx: "coin", vol: 0.75, note: "XP coins burst" },
  { at: J + JOURNEY_CUES.coin2 + 1, sfx: "coin", vol: 0.5, note: "XP coins burst (2nd)" },

  { at: G + GAMIFY_CUES.wallIn, sfx: "whoosh", vol: 0.75, note: "mosaic wall slides in" },
  { at: G + GAMIFY_CUES.ding1, sfx: "coin", vol: 0.55, note: "reward tiles pop" },
  { at: G + GAMIFY_CUES.ding2, sfx: "coin", vol: 0.45, note: "reward tiles pop" },
  { at: G + GAMIFY_CUES.panel, sfx: "whoosh", vol: 0.7, note: "dark panel rises" },
  { at: G + GAMIFY_CUES.stackLand, sfx: "click", vol: 0.85, note: "card stack lands" },
  { at: G + GAMIFY_CUES.fanLand, sfx: "click", vol: 0.6, note: "cards fan out" },
  { at: G + GAMIFY_CUES.flame, sfx: "coin", vol: 0.7, note: "streak flame" },
  { at: G + GAMIFY_CUES.trophy, sfx: "coin", vol: 0.6, note: "league trophy" },

  { at: F + FINALE_CUES.burst, sfx: "pop", vol: 0.85, note: "crew bursts up" },
  { at: F + FINALE_CUES.jump, sfx: "pop", vol: 0.85, note: "everyone jumps" },
  { at: F + FINALE_CUES.wipe, sfx: "whoosh", vol: 0.55, note: "teal wipe" },
  { at: F + FINALE_CUES.logo - 12, sfx: "rise", vol: 0.55, note: "rising accent into logo" },
];
