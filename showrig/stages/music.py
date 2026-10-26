"""Music: a score synthesized to the length of the cut, or the user's own track, ducked under the voice.

The synthesized score is deterministic: the same plan and mood always give the same audio.
"""
from __future__ import annotations

import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

from ..project import Film

RATE = 48000
# Mood: tempo, chords (MIDI, one per bar), bass roots, arpeggio on, kick on.
MOODS = {
    "bright": (96, [(57, 60, 64, 69), (53, 57, 60, 65), (48, 55, 60, 64), (55, 59, 62, 67)], [45, 41, 48, 43], True, True),
    "calm": (72, [(48, 55, 60, 64), (55, 59, 62, 67), (57, 60, 64, 69), (53, 57, 60, 65)], [36, 43, 45, 41], True, False),
    "drive": (120, [(52, 59, 64, 67), (48, 55, 60, 64), (55, 59, 62, 67), (50, 57, 62, 66)], [40, 36, 43, 38], True, True),
}


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, cutoff, fs=RATE, output="sos"), x)


def saw(f: float, t: np.ndarray, phase: float = 0.0) -> np.ndarray:
    return 2 * ((f * t + phase) % 1.0) - 1


def score(seconds: float, mood: str) -> np.ndarray:
    """Warm detuned pads, a pulsing sub, a soft arpeggio and a light kick. Stereo, unscaled."""
    bpm, chords, bass, arp_on, kick_on = MOODS[mood]
    beat = 60 / bpm
    bar = 4 * beat
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    left, right = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(7)

    pad = np.zeros(n)
    for b in range(int(seconds / bar) + 1):
        a, z = int(b * bar * RATE), min(n, int((b + 1) * bar * RATE + 0.6 * RATE))
        if a >= n:
            break
        tt = t[a:z] - t[a]
        env = np.minimum(tt / 0.9, 1) * np.exp(-np.maximum(tt - bar, 0) / 0.25)
        chord = chords[b % 4]
        voice = sum(saw(hz(m) * d, tt, rng.random()) for m in chord for d in (0.996, 1.0, 1.004))
        pad[a:z] += voice * env / (len(chord) * 3)
    sweep = 900 + 700 * (0.5 - 0.5 * np.cos(2 * np.pi * t / (8 * bar)))
    pad_f = np.zeros(n)
    block = RATE // 4
    for i in range(0, n, block):  # time-varying cutoff, block-wise
        pad_f[i:i + block] = lowpass(pad[max(0, i - 2000):i + block], float(sweep[i]))[-len(pad[i:i + block]):]
    left += 0.16 * pad_f
    right += 0.16 * np.roll(pad_f, int(0.012 * RATE))

    sub = np.zeros(n)
    for k in range(int(seconds / (beat / 2))):
        a = int(k * beat / 2 * RATE)
        z = min(n, a + int(beat / 2 * RATE))
        tt = t[a:z] - t[a]
        f = hz(bass[int(k * beat / 2 / bar) % 4] - 12)
        sub[a:z] += np.sin(2 * np.pi * f * tt) * np.minimum(tt / 0.01, 1) * np.exp(-tt / 0.22)
    left += 0.22 * sub
    right += 0.22 * sub

    if arp_on:
        arp_l, arp_r = np.zeros(n), np.zeros(n)
        for k in range(int(seconds / (beat / 4))):
            a = int(k * beat / 4 * RATE)
            chord = chords[int(k * beat / 4 / bar) % 4]
            m = chord[[0, 1, 2, 3, 2, 1][k % 6]] + 12
            z = min(n, a + int(0.5 * RATE))
            tt = t[a:z] - t[a]
            note = (np.sin(2 * np.pi * hz(m) * tt) + 0.3 * np.sin(4 * np.pi * hz(m) * tt)) * np.exp(-tt / 0.12)
            (arp_l if k % 2 else arp_r)[a:z] += note * (0.75 if k % 4 == 0 else 0.5)
        left += 0.05 * arp_l + 0.03 * arp_r
        right += 0.05 * arp_r + 0.03 * arp_l

    if kick_on:
        kick = np.zeros(n)
        for k in range(8, int(seconds / beat), 2):  # beats 1 and 3, after the first two bars
            a = int(k * beat * RATE)
            z = min(n, a + int(0.35 * RATE))
            tt = t[a:z] - t[a]
            f = 48 + 90 * np.exp(-tt / 0.03)
            kick[a:z] += np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-tt / 0.12)
        left += 0.25 * kick
        right += 0.25 * kick
    mix = np.stack([left, right], 1)
    return np.tanh(mix * 1.4) / 1.4


def decode(path, seconds: float) -> np.ndarray:
    """The user's track as stereo float at 48 kHz, looped if it is shorter than the film."""
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-protocol_whitelist", "file,pipe,data", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar",
                                   str(RATE), "-"])
    audio = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    need = int(seconds * RATE)
    reps = -(-need // len(audio))
    return np.tile(audio, (reps, 1))[:need]


def build(film: Film, plan: dict) -> str | None:
    m = film.board["music"]
    if m["source"] == "none":
        return None
    dst = film.work / "music.wav"
    speech = [(n["start"] - 0.15, n["start"] + n["duration"] + 0.25) for n in plan["narration"]]
    src = film.asset(m["file"]) if m["source"] == "file" else None
    key = film.fingerprint(plan["duration"], speech, m, src)
    if film.fresh(dst, key):
        return str(dst)
    seconds = plan["duration"]
    mix = decode(src, seconds) if src else score(seconds, m.get("mood", "bright"))
    t = np.arange(len(mix)) / RATE
    duck = np.ones(len(mix))
    for a, z in speech:
        duck[int(max(a, 0) * RATE):int(z * RATE)] = 0.42
    duck = lowpass(duck, 3.0, 1)
    fade = np.minimum(t / 1.5, 1) * np.clip((seconds - t) / 3.0, 0, 1)
    mix = mix * (duck * fade)[:, None]
    mix = mix / (np.max(np.abs(mix)) or 1) * 0.5
    wavfile.write(dst, RATE, (mix * 32767).astype(np.int16))
    film.stamp(dst, key)
    print(f"  music: {'your track' if src else m.get('mood', 'bright') + ' score'}, {seconds:.1f}s, ducked under the voice")
    return str(dst)
