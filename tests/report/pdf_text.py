"""Extract text from a Chrome-printed PDF using stdlib only.

Chrome embeds Type0/CID fonts, so the page streams carry glyph ids rather than
characters and a plain grep over the file finds nothing. The embedded ToUnicode
CMaps are enough to map them back. Each glyph is positioned individually, so the
result has no reliable word spacing; callers should match against
whitespace-stripped text.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path


def _streams(data: bytes) -> list[bytes]:
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        try:
            out.append(zlib.decompress(data[start:end]))
        except zlib.error:
            continue
    return out


def extract(pdf: Path) -> str:
    data = pdf.read_bytes()
    streams = _streams(data)

    cmap: dict[int, str] = {}
    for st in streams:
        for blk in re.findall(rb"beginbfchar(.*?)endbfchar", st, re.DOTALL):
            for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                cmap[int(src, 16)] = "".join(
                    chr(int(dst[i:i + 4], 16)) for i in range(0, len(dst), 4))
        for blk in re.findall(rb"beginbfrange(.*?)endbfrange", st, re.DOTALL):
            for lo, hi, dst in re.findall(
                    rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                base = int(dst, 16)
                for k, code in enumerate(range(int(lo, 16), int(hi, 16) + 1)):
                    cmap[code] = chr(base + k)

    def decode(hexstr: str) -> str:
        return "".join(cmap.get(int(hexstr[i:i + 4], 16), "")
                       for i in range(0, len(hexstr), 4))

    parts = []
    for st in streams:
        if b"Tj" not in st and b"TJ" not in st:
            continue
        for tm in re.finditer(rb"\[(.*?)\]\s*TJ|<([0-9A-Fa-f]+)>\s*Tj", st, re.DOTALL):
            if tm.group(1) is not None:
                parts.append("".join(decode(h.decode())
                                     for h in re.findall(rb"<([0-9A-Fa-f]+)>", tm.group(1))))
            else:
                parts.append(decode(tm.group(2).decode()))
    # Metadata strings are not in the page streams; scan them separately.
    for key in (b"Title", b"Author", b"Subject", b"Keywords", b"Producer", b"Creator"):
        for m in re.finditer(rb"/" + key + rb"\s*\(((?:[^()\\]|\\.)*)\)", data):
            parts.append(m.group(1).decode("latin-1"))
    for m in re.finditer(rb"/URI\s*\(((?:[^()\\]|\\.)*)\)", data):
        parts.append(m.group(1).decode("latin-1"))
    return "".join(parts)


def squashed(pdf: Path) -> str:
    """Lowercased text with all whitespace removed, for phrase matching."""
    return re.sub(r"\s+", "", extract(pdf)).lower()
