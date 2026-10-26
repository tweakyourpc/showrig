"""Kokoro-82M text to speech, run in whichever Python has kokoro installed.

python tts_kokoro.py <job.json>   job: {voice, speed, items: [{text, out}]}
Writes 24 kHz mono WAVs; Showrig levels and resamples them afterwards.
"""
from __future__ import annotations

import json
import os
import socket
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def offline_connect(*args, **kwargs):
    """Fail immediately if a speech dependency tries to download anything."""
    raise OSError("Offline speech requires preinstalled models; network access is disabled.")


socket.socket.connect = offline_connect

import numpy as np
import soundfile as sf
import torch
import spacy
from kokoro import KPipeline

_spacy_load = spacy.load


def load_language_model(name, **kwargs):
    """Recover a broken serialized English tokenizer using spaCy's English defaults."""
    try:
        return _spacy_load(name, **kwargs)
    except OverflowError as exc:
        if not str(name).startswith("en_core_web_") or "C ssize_t" not in str(exc):
            raise
        print("Using the standard English tokenizer: the installed serialized tokenizer could not load.", file=sys.stderr)
        return _spacy_load(name, **{**kwargs, "exclude": list(kwargs.get("exclude", [])) + ["tokenizer"]})


spacy.load = load_language_model

checking = sys.argv[1] == "--check"
job = {"voice": sys.argv[2], "speed": 1.0, "items": [{"text": "Your film is ready."}]} if checking else json.load(open(sys.argv[1]))
pipe = KPipeline(lang_code=job["voice"][0], device="cuda" if torch.cuda.is_available() else "cpu")
for item in job["items"]:
    audio = np.concatenate([a.numpy() for _, _, a in pipe(item["text"], voice=job["voice"], speed=job["speed"])])
    if not len(audio):
        raise RuntimeError("The speech engine returned no audio.")
    if not checking:
        sf.write(item["out"], audio, 24000)
    print(item.get("out", "Offline speech ready"), round(len(audio) / 24000, 2), flush=True)
