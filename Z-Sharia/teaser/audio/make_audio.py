#!/usr/bin/env python3
"""
Z-Sharia teaser — original music bed + sound effects, synthesised from scratch.

  python3 audio/make_audio.py            # writes public/audio/*.wav

Music: 120 BPM (one beat = exactly 15 frames at 30 fps), C major, I–V–vi–IV.
  0–6 s   hook      : soft plucks + shaker, bass from bar 3
  6–18 s  journey   : full groove (kick, clap, shaker, bass, plucks, bell motif)
  18–25 s gamify    : + bell arpeggios
  25–27 s finale    : build (clap 8ths crescendo)
  27 s    logo hit  : big C chord on the downbeat (frame 810), rings out,
                      clean fade to silence by 29.9 s
SFX: pop, pop_small, whoosh, coin, click, rise — placed in Remotion by src/cues.ts.
Levels: music peaks at -8 dBFS, SFX files peak between -2 and -4 dBFS; Remotion cue
volumes (src/cues.ts) keep the final mix under -1.5 dBFS with music sitting below the SFX.
"""
import os
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
BPM = 120
BEAT = 60 / BPM  # 0.5 s
BAR = 4 * BEAT
DUR = 30.0
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "audio")
rng = np.random.default_rng(7)


def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def db(x):
    return 10 ** (x / 20)


def lowpass(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), "low")
    return signal.lfilter(b, a, x)


def highpass(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), "high")
    return signal.lfilter(b, a, x)


def bandpass(x, lo, hi, order=2):
    b, a = signal.butter(order, [lo / (SR / 2), hi / (SR / 2)], "band")
    return signal.lfilter(b, a, x)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def fade_edges(x, a=0.002, r=0.01):
    n = len(x)
    na, nr = int(a * SR), int(r * SR)
    env = np.ones(n)
    if na:
        env[:na] = np.linspace(0, 1, na)
    if nr:
        env[-nr:] = np.linspace(1, 0, nr)
    return x * env


# ---------------------------------------------------------------- instruments
def pluck(freq, dur=0.6, bright=1.0):
    t = t_axis(dur)
    y = np.zeros_like(t)
    for k, amp in enumerate([1.0, 0.5, 0.28, 0.16, 0.09], start=1):
        y += amp * bright ** (k - 1) * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (5 + 3 * k))
    return fade_edges(y, 0.003, 0.02)


def bell(freq, dur=1.2):
    t = t_axis(dur)
    y = (
        np.sin(2 * np.pi * freq * t) * np.exp(-t * 3.2)
        + 0.35 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 7)
        + 0.15 * np.sin(2 * np.pi * freq * 5.4 * t) * np.exp(-t * 12)
    )
    return fade_edges(y, 0.002, 0.05)


def bass(freq, dur=0.42):
    t = t_axis(dur)
    y = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
    env = np.minimum(1, t / 0.008) * np.exp(-t * 4.0)
    return fade_edges(y * env, 0.002, 0.03)


def kick(dur=0.3):
    t = t_axis(dur)
    f = 45 + 85 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return fade_edges(np.sin(ph) * np.exp(-t * 11), 0.001, 0.02)


def clap(dur=0.18):
    t = t_axis(dur)
    n = rng.standard_normal(len(t))
    env = np.zeros_like(t)
    for off in (0, 0.011, 0.022):
        env += (t >= off) * np.exp(-np.maximum(t - off, 0) * 55)
    return fade_edges(bandpass(n, 900, 5000) * env * 0.6, 0.001, 0.02)


def shaker(dur=0.07):
    t = t_axis(dur)
    n = highpass(rng.standard_normal(len(t)), 6000)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return fade_edges(n * env * 0.35, 0.001, 0.005)


def pad(freqs, dur, attack=0.05, release=2.2):
    t = t_axis(dur)
    y = np.zeros_like(t)
    for f in freqs:
        for det in (-0.12, 0.0, 0.12):
            ff = f * 2 ** (det / 12)
            # soft saw via a few harmonics
            for k in range(1, 7):
                y += (1 / k) * np.sin(2 * np.pi * ff * k * t + rng.uniform(0, 6.28))
    y = lowpass(y, 2200)
    env = np.minimum(1, t / attack) * np.exp(-t / release)
    return y * env / (len(freqs) * 3)


def place(buf, clip, at, gain=1.0, pan=0.0):
    i = int(round(at * SR))
    if i >= buf.shape[0]:
        return
    n = min(len(clip), buf.shape[0] - i)
    l = np.cos((pan + 1) * np.pi / 4)
    r = np.sin((pan + 1) * np.pi / 4)
    buf[i : i + n, 0] += clip[:n] * gain * l * 1.414
    buf[i : i + n, 1] += clip[:n] * gain * r * 1.414


# ---------------------------------------------------------------------- music
C4 = 60
CHORDS = [  # I V vi IV in C
    [C4, C4 + 4, C4 + 7],
    [C4 - 5, C4 - 1, C4 + 2],
    [C4 - 3, C4, C4 + 4],
    [C4 - 7, C4 - 3, C4],
]
ROOTS = [36, 43, 45, 41]  # C2 G2 A2 F2
MOTIF = [  # (beat offset within 2 bars, midi)
    (0, 79), (1, 76), (1.5, 79), (2, 81), (3, 79),
    (4, 84), (5, 81), (5.5, 79), (6, 76), (7, 79),
]


def make_music():
    buf = np.zeros((int(DUR * SR), 2))
    HIT = 27.0  # frame 810, logo downbeat
    nbars = int(HIT / BAR) + 1
    for b in range(nbars):
        t0 = b * BAR
        if t0 >= HIT:
            break
        chord = CHORDS[b % 4]
        root = ROOTS[b % 4]
        hook = t0 < 6
        journey = 6 <= t0 < 18
        gamify = 18 <= t0 < 25
        build = 25 <= t0 < HIT
        for beat in range(4):
            tb = t0 + beat * BEAT
            if tb >= HIT:
                break
            # plucked chord stabs on the off-beats (on the beat in the hook)
            stab_t = tb if hook else tb + BEAT / 2
            if stab_t < HIT:
                for j, n in enumerate(chord):
                    place(buf, pluck(midi(n + 12), 0.5, 0.8), stab_t + j * 0.006, 0.12 if hook else 0.10, pan=(-0.3, 0, 0.3)[j])
            # shaker 8ths
            for h in (0, 0.5):
                ts = tb + h * BEAT
                if ts < HIT:
                    place(buf, shaker(), ts, 0.10 if hook else 0.16, pan=0.35)
            if not hook or b >= 2:
                # bass: root on 1 and 3, fifth on the "and" of 4
                if beat in (0, 2):
                    place(buf, bass(midi(root)), tb, 0.40)
                if beat == 3 and (journey or gamify):
                    place(buf, bass(midi(root + 7), 0.25), tb + BEAT / 2, 0.30)
            if journey or gamify or build:
                if beat in (0, 2):
                    place(buf, kick(), tb, 0.55)
                if beat in (1, 3):
                    place(buf, clap(), tb, 0.30, pan=-0.1)
            if build:
                # clap 8ths crescendo into the hit
                for h in (0, 0.5):
                    ts = tb + h * BEAT
                    if ts < HIT:
                        prog = (ts - 25) / (HIT - 25)
                        place(buf, clap(0.12), ts, 0.10 + 0.25 * prog, pan=0.15)
        # bell motif over journey (every 2 bars)
        if (journey or gamify) and b % 2 == 1:
            pass
        if journey and b % 2 == 1:
            for off, n in MOTIF:
                tm = t0 - BAR + off * BEAT
                if 6 <= tm < 18:
                    place(buf, bell(midi(n)), tm, 0.09, pan=0.2)
        if gamify:
            arp = [chord[0] + 24, chord[1] + 24, chord[2] + 24, chord[1] + 24]
            for k in range(8):
                ta = t0 + k * BEAT / 2
                if ta < 25:
                    place(buf, bell(midi(arp[k % 4]), 0.5), ta, 0.07, pan=(-0.4 if k % 2 else 0.4))
    # logo hit: big C chord + kick + bell sparkle, then a clean decay
    place(buf, kick(0.4), HIT, 0.7)
    place(buf, bass(midi(36), 1.6), HIT, 0.5)
    for j, n in enumerate([60, 64, 67, 72, 76]):
        place(buf, pluck(midi(n), 1.6, 0.9), HIT + j * 0.008, 0.12, pan=(-0.4, -0.2, 0, 0.2, 0.4)[j])
    p = pad([midi(48), midi(55), midi(60), midi(64), midi(67)], DUR - HIT, attack=0.02, release=3.0)
    place(buf, p, HIT, 0.5)
    place(buf, bell(midi(84), 2.0), HIT, 0.10)
    place(buf, bell(midi(88), 2.0), HIT + 0.12, 0.08)

    # gentle intro fade + final fade to true silence before 30 s
    t = np.arange(buf.shape[0]) / SR
    env = np.clip(t / 0.25, 0, 1)
    env *= np.clip((29.9 - t) / (29.9 - 28.4), 0, 1) ** 1.3
    buf *= env[:, None]
    # gentle glue: soft-knee saturation then normalise to -12 dBFS peak
    buf = np.tanh(buf * 1.2) / 1.2
    buf *= db(-8) / np.max(np.abs(buf))
    return buf


# ------------------------------------------------------------------------ sfx
def sfx_pop(small=False):
    dur = 0.16 if small else 0.22
    t = t_axis(dur)
    f0, f1 = (520, 1250) if small else (260, 900)
    f = f0 + (f1 - f0) * (1 - np.exp(-t * 60))
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * (38 if small else 26))
    click = highpass(rng.standard_normal(len(t)), 2000) * np.exp(-t * 400) * 0.25
    y = fade_edges(body + click, 0.0005, 0.01)
    return np.stack([y, y], 1)


def sfx_whoosh():
    dur = 0.9
    t = t_axis(dur)
    n = rng.standard_normal(len(t))
    # sweep a band-pass by processing in short blocks
    out = np.zeros_like(n)
    blk = 512
    zi = None
    for i in range(0, len(n), blk):
        u = i / len(n)
        fc = 350 + 2600 * np.sin(np.pi * min(u * 1.15, 1)) ** 1.5
        b, a = signal.butter(2, [max(fc * 0.55, 60) / (SR / 2), min(fc * 1.6, 20000) / (SR / 2)], "band")
        if zi is None:
            zi = signal.lfilter_zi(b, a) * 0
        seg, zi = signal.lfilter(b, a, n[i : i + blk], zi=zi)
        out[i : i + blk] = seg
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2.2
    y = out * env
    pan = np.linspace(-0.7, 0.7, len(t))
    l = y * np.cos((pan + 1) * np.pi / 4)
    r = y * np.sin((pan + 1) * np.pi / 4)
    return np.stack([fade_edges(l), fade_edges(r)], 1)


def sfx_coin():
    dur = 1.2
    t = t_axis(dur)
    y = np.zeros_like(t)
    for start, f in ((0.0, 987.77), (0.075, 1318.51)):
        tt = np.clip(t - start, 0, None)
        on = (t >= start).astype(float)
        y += on * (
            np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5)
            + 0.35 * np.sin(2 * np.pi * f * 2 * tt) * np.exp(-tt * 9)
            + 0.12 * np.sin(2 * np.pi * f * 3.01 * tt) * np.exp(-tt * 14)
        ) * np.minimum(1, tt / 0.002)
    y = fade_edges(y, 0.001, 0.08)
    return np.stack([y * 0.95, y], 1)


def sfx_click():
    dur = 0.08
    t = t_axis(dur)
    tick = np.sin(2 * np.pi * 2300 * t) * np.exp(-t * 160)
    thud = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 70) * 0.6
    n = bandpass(rng.standard_normal(len(t)), 2000, 7000) * np.exp(-t * 300) * 0.2
    y = fade_edges(tick + thud + n, 0.0005, 0.01)
    return np.stack([y, y], 1)


def sfx_rise():
    # 0.4 s ascending bell arpeggio + airy riser, landing exactly at 0.4 s
    # (the logo downbeat), then a sparkle that rings out.
    dur = 2.4
    lead = 0.4
    t = t_axis(dur)
    y = np.zeros((len(t), 2))
    notes = [72, 76, 79, 84, 88]
    for k, n in enumerate(notes):
        at = k * lead / len(notes)
        b = bell(midi(n), 1.0)
        i = int(at * SR)
        pan = -0.5 + k * 0.25
        y[i : i + len(b), 0] += b[: len(t) - i] * 0.5 * np.cos((pan + 1) * np.pi / 4) * 1.4
        y[i : i + len(b), 1] += b[: len(t) - i] * 0.5 * np.sin((pan + 1) * np.pi / 4) * 1.4
    nz = highpass(rng.standard_normal(len(t)), 3000)
    env = np.clip(t / lead, 0, 1) ** 2 * (t < lead) + (t >= lead) * np.exp(-(t - lead) * 10)
    y += (nz * env * 0.18)[:, None]
    for n, g in ((96, 0.35), (100, 0.25), (103, 0.2)):
        b = bell(midi(n), 1.8)
        i = int(lead * SR)
        y[i : i + len(b), :] += (b[: len(t) - i] * g)[:, None]
    y[:, 0] = fade_edges(y[:, 0], 0.002, 0.3)
    y[:, 1] = fade_edges(y[:, 1], 0.002, 0.3)
    return y


def norm(x, peak_db=-6.0):
    return x * (db(peak_db) / np.max(np.abs(x)))


def write(name, x):
    x = np.clip(x, -1, 1)
    wavfile.write(os.path.join(OUT, name), SR, (x * 32767).astype(np.int16))
    pk = 20 * np.log10(np.max(np.abs(x)) + 1e-12)
    print(f"{name:22s} {len(x) / SR:6.2f}s  peak {pk:6.1f} dBFS")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    write("music.wav", make_music())
    write("sfx_pop.wav", norm(sfx_pop(), -2))
    write("sfx_pop_small.wav", norm(sfx_pop(True), -4))
    write("sfx_whoosh.wav", norm(sfx_whoosh(), -3))
    write("sfx_coin.wav", norm(sfx_coin(), -4))
    write("sfx_click.wav", norm(sfx_click(), -4))
    write("sfx_rise.wav", norm(sfx_rise(), -2))
