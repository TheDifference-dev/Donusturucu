"""Video → ses (ve ses → ses) dönüştürme. ffmpeg, pip paketiyle (imageio-ffmpeg) birlikte gelir."""
from __future__ import annotations

import re

from .core import Job, Result, ToolError, find_ffmpeg, run, stem, zip_if_many

VIDEO = ["mp4", "mov", "mkv", "avi", "webm", "wmv", "flv", "m4v", "3gp", "mpeg", "mpg", "ts", "mts"]
AUDIO = ["mp3", "wav", "m4a", "aac", "ogg", "opus", "flac", "wma", "amr"]

CODECS = {
    "mp3": ["-c:a", "libmp3lame"],
    "m4a": ["-c:a", "aac"],
    "aac": ["-c:a", "aac", "-f", "adts"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis"],
    "opus": ["-c:a", "libopus"],
}
LOSSLESS = {"wav", "flac"}


def _time(v: str | None) -> str | None:
    """'90', '1:30', '00:01:30.5' kabul eder."""
    if not v or not str(v).strip():
        return None
    v = str(v).strip().replace(",", ".")
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", v):
        raise ToolError(f"Zaman biçimi anlaşılamadı: '{v}'. Örnek: 1:30 veya 00:01:30")
    return v


def video_to_audio(job: Job) -> Result:
    files = job.need(1, exts=VIDEO + AUDIO)
    ff = find_ffmpeg()
    if not ff:
        raise ToolError("ffmpeg bulunamadı. 'pip install imageio-ffmpeg' ile kurulabilir.")
    fmt = job.opt("format", "mp3")
    if fmt not in CODECS:
        raise ToolError("Desteklenmeyen ses biçimi.")
    bitrate = job.opt("bitrate", "192k")
    start, end = _time(job.opt("start")), _time(job.opt("end"))
    outs, notes = [], []
    for f in files:
        p = job.path(f"{stem(f)}.{fmt}")
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-y"]
        if start:
            cmd += ["-ss", start]
        if end:
            cmd += ["-to", end]
        cmd += ["-i", str(f), "-vn", "-map", "0:a:0?"] + CODECS[fmt]
        if fmt not in LOSSLESS:
            cmd += ["-b:a", bitrate]
        if job.flag("mono"):
            cmd += ["-ac", "1"]
        sr = job.opt("samplerate")
        if sr and sr != "auto":
            cmd += ["-ar", str(sr)]
        filters = []
        if job.flag("normalize"):
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        if job.flag("fade"):
            filters.append("afade=t=in:d=1")
        if filters:
            cmd += ["-af", ",".join(filters)]
        if fmt == "mp3":
            cmd += ["-id3v2_version", "3"]
        cmd.append(str(p))
        r = run(cmd, timeout=3600)
        if r.returncode != 0 or not p.exists() or p.stat().st_size < 100:
            err = r.stderr.decode(errors="ignore").strip()
            if "does not contain any stream" in err or "matches no streams" in err or not err:
                err = "Dosyada ses kanalı yok."
            p.unlink(missing_ok=True)
            notes.append(f"{f.name}: {err[:300]}")
            continue
        outs.append(p)
    if not outs:
        raise ToolError("\n".join(notes))
    return Result(zip_if_many(job, outs, "sesler.zip"), note="\n".join(notes) or None)
