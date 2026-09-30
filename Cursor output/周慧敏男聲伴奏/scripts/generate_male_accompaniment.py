#!/usr/bin/env python3
"""
全新編曲：周慧敏經典情歌風格・男聲伴奏練習版
Original practice accompaniments inspired by 90s Cantopop ballad mood.
Does NOT reproduce copyrighted melodies — chord/pad/rhythm beds only.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from midiutil import MIDIFile

ROOT = Path(__file__).resolve().parents[1]
MIDI_DIR = ROOT / "midi"
WAV_DIR = ROOT / "wav"
MP3_DIR = ROOT / "mp3"
SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

# GM programs
PIANO = 0
EP = 4
STRINGS = 48
WARM_PAD = 89
FINGER_BASS = 33
NYLON_GUITAR = 24
SOFT_DRUM_CH = 9  # channel 9 = drums

# Drum notes (GM)
KICK = 36
SNARE = 38
HH_CLOSED = 42
HH_OPEN = 46
RIDE = 51
TOM_MID = 47


NOTE = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def parse_root(root_name: str) -> str:
    """Accept 'G', 'Em', 'F#m', 'Bb' → pitch-class key in NOTE."""
    if root_name in NOTE:
        return root_name
    if root_name.endswith("m") and root_name[:-1] in NOTE:
        return root_name[:-1]
    raise KeyError(f"Unknown root: {root_name}")


def chord_notes(root_name: str, quality: str, octave: int = 3) -> list[int]:
    root = 12 * octave + NOTE[parse_root(root_name)]
    if quality == "maj":
        intervals = [0, 4, 7]
    elif quality == "min":
        intervals = [0, 3, 7]
    elif quality == "maj7":
        intervals = [0, 4, 7, 11]
    elif quality == "min7":
        intervals = [0, 3, 7, 10]
    elif quality == "dom7":
        intervals = [0, 4, 7, 10]
    elif quality == "sus2":
        intervals = [0, 2, 7]
    elif quality == "sus4":
        intervals = [0, 5, 7]
    elif quality == "add9":
        intervals = [0, 4, 7, 14]
    elif quality == "min9":
        intervals = [0, 3, 7, 10, 14]
    else:
        intervals = [0, 4, 7]
    return [root + i for i in intervals]


@dataclass
class SongSpec:
    slug: str
    title: str
    mood: str
    bpm: int
    key_label: str  # display, e.g. "G major (男聲建議調 / 約降4)"
    # list of (root, quality) per bar — 4/4
    progression: list[tuple[str, str]]
    form: list[tuple[str, int]]  # (section_name, bars) cycling progression chunks
    style: str  # soft_ballad | midtempo | waltzish


SONGS: list[SongSpec] = [
    SongSpec(
        slug="01_最愛_男聲全新編曲",
        title="最愛・男聲全新編曲伴奏",
        mood="溫柔慢板・鋼琴＋弦樂（致敬經典情歌氣氛，原創和弦床）",
        bpm=68,
        key_label="G major（男聲舒適調，相對女聲原調約降 4 個半音）",
        progression=[
            ("G", "maj7"),
            ("Em", "min7"),
            ("C", "maj7"),
            ("D", "sus4"),
            ("G", "maj7"),
            ("Bm", "min7"),
            ("C", "add9"),
            ("D", "dom7"),
            ("Em", "min7"),
            ("Bm", "min7"),
            ("C", "maj7"),
            ("G", "maj"),
            ("Am", "min7"),
            ("D", "dom7"),
            ("G", "maj7"),
            ("D", "sus4"),
        ],
        form=[
            ("intro", 4),
            ("verse", 8),
            ("pre", 4),
            ("chorus", 8),
            ("verse2", 8),
            ("chorus2", 8),
            ("bridge", 4),
            ("chorus3", 8),
            ("outro", 4),
        ],
        style="soft_ballad",
    ),
    SongSpec(
        slug="02_流言_男聲全新編曲",
        title="流言・男聲全新編曲伴奏",
        mood="惘然中板・指彈吉他＋柔和 pad",
        bpm=76,
        key_label="A minor（男聲建議調，相對女聲約降 3–4 個半音）",
        progression=[
            ("Am", "min9"),
            ("F", "maj7"),
            ("C", "maj7"),
            ("G", "maj"),
            ("Am", "min7"),
            ("Em", "min7"),
            ("F", "maj7"),
            ("E", "dom7"),
            ("Dm", "min7"),
            ("G", "dom7"),
            ("C", "maj7"),
            ("Am", "min7"),
            ("F", "add9"),
            ("G", "sus4"),
            ("Am", "min7"),
            ("E", "dom7"),
        ],
        form=[
            ("intro", 4),
            ("verse", 8),
            ("chorus", 8),
            ("verse2", 8),
            ("chorus2", 8),
            ("bridge", 4),
            ("chorus3", 8),
            ("outro", 4),
        ],
        style="soft_ballad",
    ),
    SongSpec(
        slug="03_情網_男聲全新編曲",
        title="情網・男聲全新編曲伴奏",
        mood="纏綿中慢板・電鋼琴＋弦樂 sweep",
        bpm=72,
        key_label="F major（男聲建議調）",
        progression=[
            ("F", "maj7"),
            ("Dm", "min7"),
            ("Gm", "min7"),
            ("C", "dom7"),
            ("F", "maj7"),
            ("Bb", "maj7"),
            ("Am", "min7"),
            ("C", "sus4"),
            ("Bb", "maj7"),
            ("F", "maj"),
            ("Gm", "min7"),
            ("C", "dom7"),
            ("Dm", "min7"),
            ("Bb", "add9"),
            ("F", "maj7"),
            ("C", "dom7"),
        ],
        form=[
            ("intro", 4),
            ("verse", 8),
            ("pre", 4),
            ("chorus", 8),
            ("verse2", 8),
            ("chorus2", 8),
            ("bridge", 4),
            ("final", 8),
            ("outro", 4),
        ],
        style="soft_ballad",
    ),
    SongSpec(
        slug="04_心軟_男聲全新編曲",
        title="心軟・男聲全新編曲伴奏",
        mood="輕柔告白・明亮大調慢板",
        bpm=70,
        key_label="D major（男聲建議調）",
        progression=[
            ("D", "maj7"),
            ("Bm", "min7"),
            ("G", "maj7"),
            ("A", "sus4"),
            ("D", "maj7"),
            ("F#m", "min7"),
            ("G", "add9"),
            ("A", "dom7"),
            ("Bm", "min7"),
            ("F#m", "min7"),
            ("G", "maj7"),
            ("D", "maj"),
            ("Em", "min7"),
            ("A", "dom7"),
            ("D", "maj7"),
            ("A", "sus4"),
        ],
        form=[
            ("intro", 4),
            ("verse", 8),
            ("chorus", 8),
            ("verse2", 8),
            ("chorus2", 8),
            ("bridge", 4),
            ("chorus3", 8),
            ("outro", 4),
        ],
        style="soft_ballad",
    ),
    SongSpec(
        slug="05_紅顏知己_男聲全新編曲",
        title="紅顏知己・男聲全新編曲伴奏",
        mood="知性中板・尼龍吉他＋輕鼓點",
        bpm=82,
        key_label="E minor（男聲建議調）",
        progression=[
            ("Em", "min7"),
            ("C", "maj7"),
            ("G", "maj"),
            ("D", "maj"),
            ("Em", "min9"),
            ("Am", "min7"),
            ("C", "add9"),
            ("B", "dom7"),
            ("Am", "min7"),
            ("Em", "min7"),
            ("C", "maj7"),
            ("G", "maj"),
            ("Am", "min7"),
            ("D", "sus4"),
            ("Em", "min7"),
            ("B", "dom7"),
        ],
        form=[
            ("intro", 4),
            ("verse", 8),
            ("chorus", 8),
            ("verse2", 8),
            ("chorus2", 8),
            ("bridge", 4),
            ("chorus3", 8),
            ("outro", 4),
        ],
        style="midtempo",
    ),
    SongSpec(
        slug="06_從今開始_男聲全新編曲",
        title="從今開始・男聲全新編曲伴奏",
        mood="開朗希望・流行中板",
        bpm=88,
        key_label="C major（男聲建議調）",
        progression=[
            ("C", "maj7"),
            ("G", "maj"),
            ("Am", "min7"),
            ("F", "maj7"),
            ("C", "maj"),
            ("Em", "min7"),
            ("F", "add9"),
            ("G", "sus4"),
            ("Am", "min7"),
            ("F", "maj7"),
            ("C", "maj7"),
            ("G", "dom7"),
            ("F", "maj7"),
            ("G", "maj"),
            ("C", "maj7"),
            ("G", "sus4"),
        ],
        form=[
            ("intro", 4),
            ("verse", 8),
            ("pre", 4),
            ("chorus", 8),
            ("verse2", 8),
            ("chorus2", 8),
            ("bridge", 4),
            ("final", 8),
            ("outro", 4),
        ],
        style="midtempo",
    ),
]


def expand_bars(song: SongSpec) -> list[tuple[str, tuple[str, str]]]:
    """Expand form into (section, chord) per bar, cycling progression."""
    bars: list[tuple[str, tuple[str, str]]] = []
    prog = song.progression
    idx = 0
    for section, n in song.form:
        for _ in range(n):
            bars.append((section, prog[idx % len(prog)]))
            idx += 1
    return bars


def add_note(midi, track, channel, pitch, time, duration, volume, tempo):
    midi.addNote(track, channel, pitch, time, duration, volume)


def write_song(song: SongSpec) -> Path:
    bars = expand_bars(song)
    n_tracks = 6
    midi = MIDIFile(n_tracks)
    tempo = song.bpm
    for t in range(n_tracks):
        midi.addTempo(t, 0, tempo)
        midi.addTimeSignature(t, 0, 4, 2, 24, 8)

    # Track map: 0 piano, 1 EP/guitar, 2 strings, 3 pad, 4 bass, 5 drums(ch9)
    midi.addProgramChange(0, 0, 0, PIANO)
    midi.addProgramChange(1, 1, 0, EP if song.style == "soft_ballad" else NYLON_GUITAR)
    midi.addProgramChange(2, 2, 0, STRINGS)
    midi.addProgramChange(3, 3, 0, WARM_PAD)
    midi.addProgramChange(4, 4, 0, FINGER_BASS)
    # drums on channel 9 — program ignored

    beat = 0.0  # in beats; 1 bar = 4 beats
    for bar_i, (section, (root, quality)) in enumerate(bars):
        notes = chord_notes(root, quality, octave=3)
        high = chord_notes(root, quality, octave=4)
        bass_root = 12 * 2 + NOTE[parse_root(root)]

        is_chorus = section.startswith("chorus") or section in ("final",)
        is_intro = section in ("intro", "outro")
        is_bridge = section == "bridge"

        # --- Piano block / arpeggio ---
        vol_p = 48 if is_intro else (62 if is_chorus else 55)
        if song.style == "soft_ballad":
            # broken arpeggio: 8th notes
            arp = notes + [high[0]] + notes[1:]
            for i, p in enumerate(arp[:8]):
                add_note(midi, 0, 0, p, beat + i * 0.5, 0.55, vol_p - (i % 3) * 2, tempo)
            # soft top chord on beat 1
            for p in high[:3]:
                add_note(midi, 0, 0, p + 12, beat, 3.5, max(28, vol_p - 20), tempo)
        else:
            # midtempo: syncopated comping
            for p in notes:
                add_note(midi, 0, 0, p, beat, 1.8, vol_p, tempo)
                add_note(midi, 0, 0, p, beat + 2.0, 1.6, vol_p - 4, tempo)

        # --- EP / Guitar color ---
        vol_g = 40 if is_intro else (52 if is_chorus else 45)
        for p in high[:4]:
            add_note(midi, 1, 1, p, beat + 0.0, 3.8, vol_g, tempo)
        if not is_intro:
            # light pluck motif (original, not melodic copy)
            motif = [high[0], high[1], high[0] - 2 if high[0] - 2 > 50 else high[0], high[2]]
            for i, p in enumerate(motif):
                add_note(midi, 1, 1, p, beat + 1.0 + i * 0.5, 0.4, vol_g - 8, tempo)

        # --- Strings ---
        vol_s = 28 if is_intro else (46 if is_chorus else 34)
        if is_bridge:
            vol_s += 8
        for p in notes:
            add_note(midi, 2, 2, p + 12, beat, 4.0, vol_s, tempo)

        # --- Warm pad ---
        for p in notes[:3]:
            add_note(midi, 3, 3, p, beat, 4.0, 22 if is_intro else 30, tempo)

        # --- Bass ---
        vol_b = 0 if is_intro and bar_i < 2 else (58 if is_chorus else 50)
        if vol_b:
            add_note(midi, 4, 4, bass_root, beat, 1.5, vol_b, tempo)
            add_note(midi, 4, 4, bass_root, beat + 2.0, 1.5, vol_b - 4, tempo)
            if is_chorus or song.style == "midtempo":
                fifth = bass_root + 7
                add_note(midi, 4, 4, fifth, beat + 3.0, 0.8, vol_b - 10, tempo)

        # --- Drums ---
        if not (is_intro and bar_i < 2):
            kick_v = 70 if is_chorus else 58
            snare_v = 62 if is_chorus else 48
            hh_v = 42 if is_chorus else 34
            # kick on 1 and 3
            add_note(midi, 5, SOFT_DRUM_CH, KICK, beat, 0.4, kick_v, tempo)
            add_note(midi, 5, SOFT_DRUM_CH, KICK, beat + 2.0, 0.4, kick_v - 6, tempo)
            # soft snare / clap on 2 and 4
            if not is_intro:
                add_note(midi, 5, SOFT_DRUM_CH, SNARE, beat + 1.0, 0.3, snare_v, tempo)
                add_note(midi, 5, SOFT_DRUM_CH, SNARE, beat + 3.0, 0.3, snare_v - 4, tempo)
            # hihat 8ths
            for i in range(8):
                note = HH_OPEN if (is_chorus and i == 7) else HH_CLOSED
                add_note(midi, 5, SOFT_DRUM_CH, note, beat + i * 0.5, 0.25, hh_v - (i % 2) * 4, tempo)
            if is_chorus and bar_i % 4 == 3:
                add_note(midi, 5, SOFT_DRUM_CH, TOM_MID, beat + 3.5, 0.3, 55, tempo)

        beat += 4.0

    # ending chord sustain
    last_root, last_q = bars[-1][1]
    end_notes = chord_notes(last_root, last_q, 3) + chord_notes(last_root, last_q, 4)
    for p in end_notes:
        add_note(midi, 0, 0, p, beat, 6.0, 50, tempo)
        add_note(midi, 2, 2, p, beat, 6.0, 40, tempo)

    MIDI_DIR.mkdir(parents=True, exist_ok=True)
    out = MIDI_DIR / f"{song.slug}.mid"
    with open(out, "wb") as f:
        midi.writeFile(f)
    return out


def render_audio(mid_path: Path) -> tuple[Path, Path]:
    WAV_DIR.mkdir(parents=True, exist_ok=True)
    MP3_DIR.mkdir(parents=True, exist_ok=True)
    wav = WAV_DIR / (mid_path.stem + ".wav")
    mp3 = MP3_DIR / (mid_path.stem + ".mp3")
    # fluidsynth render
    subprocess.run(
        [
            "fluidsynth",
            "-ni",
            "-g",
            "0.7",
            SF2,
            str(mid_path),
            "-F",
            str(wav),
            "-r",
            "44100",
        ],
        check=True,
        capture_output=True,
    )
    # soft limiter / loudness normalize lightly via ffmpeg
    tmp = wav.with_suffix(".norm.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            str(tmp),
        ],
        check=True,
        capture_output=True,
    )
    tmp.replace(wav)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(mp3),
        ],
        check=True,
        capture_output=True,
    )
    return wav, mp3


def main():
    print(f"Output root: {ROOT}")
    catalog = []
    for song in SONGS:
        print(f"Writing MIDI: {song.title} @ {song.bpm} BPM / {song.key_label}")
        mid = write_song(song)
        print(f"  -> {mid}")
        wav, mp3 = render_audio(mid)
        print(f"  -> {wav.name}, {mp3.name}")
        bars = expand_bars(song)
        duration_sec = (len(bars) * 4 + 6) * 60 / song.bpm
        catalog.append(
            {
                "file": mp3.name,
                "title": song.title,
                "mood": song.mood,
                "bpm": song.bpm,
                "key": song.key_label,
                "bars": len(bars),
                "approx_sec": round(duration_sec),
            }
        )
    # write machine catalog
    import json

    (ROOT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done.", len(catalog), "tracks")


if __name__ == "__main__":
    main()
