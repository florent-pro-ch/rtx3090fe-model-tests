#!/usr/bin/env python3
"""G7 media metadata gate: no PNG, JPEG, WebP, PDF or SVG of the repository carries
location, camera or author metadata, or a text field naming a path or a person.

Scans what would be committed (tracked plus untracked-but-not-ignored files) and
the built site (site/dist). Files under benches/ are frozen, byte-identical copies
of the lab's bench inputs (tools/verify_benches.py recomputes their SHA-256): they
can not be rewritten, so their findings are reported, never failed.

Read, with the standard library only:
  PNG   tEXt, zTXt, iTXt chunks (keyword and text; XMP packets included) and the
        eXIf chunk
  JPEG  APP1 Exif (IFD0, Exif IFD, GPS IFD pointer), APP1 XMP, COM comments
  WebP  EXIF and XMP chunks
  PDF   the document information dictionary (/Author /Creator /Producer /Title
        /Subject /Keywords), in the clear or inside Flate-compressed object
        streams, and XMP metadata
  SVG   <metadata>, dc:creator, and editor attributes carrying file names

Fails on:
  gps      an EXIF GPS IFD, or XMP exif:GPS* properties
  camera   EXIF Make, Model, BodySerialNumber, LensMake/LensModel/LensSerialNumber,
           CameraOwnerName
  author   EXIF Artist, Copyright, XPAuthor, HostComputer; a PNG/PDF/XMP/SVG
           author, artist, creator-person, owner or copyright field that is not
           empty (dc:creator, pdf:Author, /Author, "Author" keyword...)
  path     any metadata text holding a path into a user's home directory
           (macOS or Linux), a drive path, file://, or ~/, e.g. a software field
           or an editor's export path
Other metadata fields (Software, Producer, Title, Description, dates) are counted
and listed with --verbose.

Exceptions: tools/exceptions.json, tool "check_media", rule gps | camera | author |
path, with a reason.

usage:
  tools/check_media.py [--verbose] [PATH ...]     (default: the repository)
Exit status: 0 clean, 1 a finding outside benches/.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO, excepted, load_exceptions, mask, rel, repo_files  # noqa: E402

EXT = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".svg"}
REPORT_ONLY = ("benches/",)
PATH_RE = re.compile(r"(?:/(?:Users|home|root|var/folders|private/var)/[^\s\"'<>]+|[A-Za-z]:\\\\?[^\s\"'<>]+|"
                     r"file:/[^\s\"'<>]+|~/[^\s\"'<>]+)")
PERSON_KEYS = {"author", "artist", "owner", "copyright", "creator-person", "authorsposition",
               "byline", "credit", "rights", "lastmodifiedby", "last modified by", "contact"}
# EXIF tags (IFD0 and Exif IFD)
EXIF_TAGS = {
    0x010F: ("camera", "Make"), 0x0110: ("camera", "Model"), 0x013B: ("author", "Artist"),
    0x8298: ("author", "Copyright"), 0x9C9D: ("author", "XPAuthor"), 0x013C: ("author", "HostComputer"),
    0xA430: ("camera", "CameraOwnerName"), 0xA431: ("camera", "BodySerialNumber"),
    0xA433: ("camera", "LensMake"), 0xA434: ("camera", "LensModel"), 0xA435: ("camera", "LensSerialNumber"),
    0x8825: ("gps", "GPSInfo"),
    0x0131: ("info", "Software"), 0x010E: ("info", "ImageDescription"), 0x0132: ("info", "DateTime"),
    0x9003: ("info", "DateTimeOriginal"), 0x9C9C: ("info", "XPComment"), 0x9286: ("info", "UserComment"),
}
XMP_FIELDS = [
    (re.compile(r"<dc:creator\b.*?</dc:creator>", re.S), "author", "dc:creator"),
    (re.compile(r"<dc:rights\b.*?</dc:rights>", re.S), "author", "dc:rights"),
    (re.compile(r"\b(?:pdf:Author|photoshop:AuthorsPosition|photoshop:Credit|xmpRights:Owner)\b\s*(?:=\s*\"[^\"]+\"|>[^<]+<)"),
     "author", "xmp author"),
    (re.compile(r"\bexif:GPS\w+"), "gps", "exif:GPS"),
    (re.compile(r"\b(?:tiff:Make|tiff:Model|exifEX:BodySerialNumber|aux:SerialNumber|aux:Lens)\b"), "camera",
     "xmp camera"),
]


class Findings:
    def __init__(self):
        self.items: list[tuple[str, str, str]] = []  # (rule, field, value)
        self.info: list[tuple[str, str]] = []

    def add(self, rule: str, fld: str, value: str = ""):
        self.items.append((rule, fld, value))

    def text(self, fld: str, value: str):
        """A free-text metadata field: a path in it fails, a person key fails, else info."""
        value = value.strip("\x00 \t\r\n")
        key = fld.lower().strip()
        if PATH_RE.search(value):
            self.add("path", fld, PATH_RE.search(value).group(0))
        if key in PERSON_KEYS and value:
            self.add("author", fld, value)
        elif value:
            self.info.append((fld, value))
        if "<x:xmpmeta" in value or "<rdf:RDF" in value:
            xmp(value, self)


def xmp(packet: str, f: Findings):
    for rx, rule, name in XMP_FIELDS:
        for m in rx.finditer(packet):
            inner = re.sub(r"<[^>]+>", " ", m.group(0)).strip()
            if rule == "author" and not re.sub(r"\s+", "", inner.split(">", 1)[-1]):
                continue  # an empty creator list
            f.add(rule, name, inner[:80])
    for m in PATH_RE.finditer(packet):
        f.add("path", "xmp", m.group(0))


# ------------------------------------------------------------------ EXIF (TIFF)
def exif(data: bytes, f: Findings):
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        return
    e = "<" if data[:2] == b"II" else ">"
    seen = set()

    def ifd(off: int, depth: int = 0):
        if off in seen or depth > 4 or off + 2 > len(data):
            return
        seen.add(off)
        (n,) = struct.unpack_from(e + "H", data, off)
        for i in range(min(n, 512)):
            p = off + 2 + 12 * i
            if p + 12 > len(data):
                return
            tag, typ, cnt = struct.unpack_from(e + "HHI", data, p)
            if tag == 0x8769:  # Exif IFD
                ifd(struct.unpack_from(e + "I", data, p + 8)[0], depth + 1)
                continue
            if tag not in EXIF_TAGS:
                continue
            rule, name = EXIF_TAGS[tag]
            size = {1: 1, 2: 1, 7: 1}.get(typ, 0) * cnt
            raw = b""
            if size:
                vo = p + 8 if size <= 4 else struct.unpack_from(e + "I", data, p + 8)[0]
                raw = data[vo:vo + size]
            enc = "utf-16-le" if tag in (0x9C9D, 0x9C9C) else "latin-1"
            val = raw.decode(enc, errors="replace").strip("\x00 ")
            if rule == "info":
                f.text(name, val)
            elif rule == "gps" or val or typ not in (1, 2, 7):
                f.add(rule, f"EXIF {name}", val)
        nxt = off + 2 + 12 * n
        if depth == 0 and nxt + 4 <= len(data):
            ifd(struct.unpack_from(e + "I", data, nxt)[0], depth + 1)  # IFD1 (thumbnail)

    ifd(struct.unpack_from(e + "I", data, 4)[0])


# ------------------------------------------------------------------ formats
def png(b: bytes, f: Findings):
    p = 8
    while p + 8 <= len(b):
        ln, typ = struct.unpack_from(">I4s", b, p)
        body = b[p + 8:p + 8 + ln]
        p += 12 + ln
        if typ == b"tEXt":
            k, _, v = body.partition(b"\0")
            f.text(k.decode("latin-1"), v.decode("latin-1"))
        elif typ == b"zTXt":
            k, _, v = body.partition(b"\0")
            try:
                f.text(k.decode("latin-1"), zlib.decompress(v[1:]).decode("latin-1"))
            except zlib.error:
                f.add("path", k.decode("latin-1"), "unreadable zTXt")
        elif typ == b"iTXt":
            k, _, rest = body.partition(b"\0")
            comp, rest = rest[:1], rest[2:]
            _lang, _, rest = rest.partition(b"\0")
            _tk, _, txt = rest.partition(b"\0")
            try:
                txt = zlib.decompress(txt) if comp == b"\x01" else txt
            except zlib.error:
                txt = b""
            f.text(k.decode("latin-1"), txt.decode("utf-8", errors="replace"))
        elif typ == b"eXIf":
            exif(body, f)
        elif typ == b"IEND":
            break


def jpeg(b: bytes, f: Findings):
    p = 2
    while p + 4 <= len(b) and b[p] == 0xFF:
        marker = b[p + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            p += 2
            continue
        if marker == 0xDA:  # start of scan: metadata segments are before it
            break
        (ln,) = struct.unpack_from(">H", b, p + 2)
        seg = b[p + 4:p + 2 + ln]
        if marker == 0xE1 and seg.startswith(b"Exif\0\0"):
            exif(seg[6:], f)
        elif marker == 0xE1 and seg.startswith(b"http://ns.adobe.com/xap/1.0/\0"):
            f.text("XMP", seg.split(b"\0", 1)[1].decode("utf-8", errors="replace"))
        elif marker == 0xFE:
            f.text("Comment", seg.decode("latin-1"))
        elif marker == 0xED:  # Photoshop IRB / IPTC: byline and credits
            f.text("IPTC", re.sub(rb"[^\x20-\x7e]+", b" ", seg).decode("ascii"))
        p += 2 + ln


def webp(b: bytes, f: Findings):
    p = 12
    while p + 8 <= len(b):
        typ, ln = struct.unpack_from("<4sI", b, p)
        body = b[p + 8:p + 8 + ln]
        p += 8 + ln + (ln & 1)
        if typ == b"EXIF":
            exif(body[6:] if body.startswith(b"Exif\0\0") else body, f)
        elif typ == b"XMP ":
            f.text("XMP", body.decode("utf-8", errors="replace"))


PDF_KEYS = ("Author", "Creator", "Producer", "Title", "Subject", "Keywords")


def _pdf_string(s: bytes) -> str:
    s = s.strip()
    if s.startswith(b"<") and not s.startswith(b"<<"):
        h = re.sub(rb"[^0-9A-Fa-f]", b"", s)
        raw = bytes.fromhex(h.decode() + ("0" if len(h) % 2 else ""))
    else:
        raw = re.sub(rb"\\([()\\])", rb"\1", s[1:-1])
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    return raw.decode("latin-1")


def pdf(b: bytes, f: Findings):
    chunks = [b]
    for m in re.finditer(rb"/FlateDecode.*?stream\r?\n(.*?)endstream", b, re.S):
        try:
            chunks.append(zlib.decompress(m.group(1)))
        except zlib.error:
            continue
    for c in chunks:
        for k in PDF_KEYS:
            for m in re.finditer(rb"/" + k.encode() + rb"\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", c):
                val = _pdf_string(m.group(1))
                f.text("author" if k == "Author" else f"PDF {k}", val)
        if b"<x:xmpmeta" in c or b"<rdf:RDF" in c:
            xmp(c.decode("utf-8", errors="replace"), f)


def svg(b: bytes, f: Findings):
    t = b.decode("utf-8", errors="replace")
    for m in re.finditer(r"<metadata\b.*?</metadata>", t, re.S):
        xmp(m.group(0), f)
    for m in re.finditer(r"\b(?:inkscape:export-filename|sodipodi:docname|sodipodi:absref|xlink:href|href)"
                         r"\s*=\s*\"([^\"]*)\"", t):
        if PATH_RE.search(m.group(1)):
            f.add("path", m.group(0).split("=")[0].strip(), PATH_RE.search(m.group(1)).group(0))


READERS = {".png": png, ".jpg": jpeg, ".jpeg": jpeg, ".webp": webp, ".pdf": pdf, ".svg": svg}


def scan(path: Path) -> Findings:
    f = Findings()
    b = path.read_bytes()
    try:
        READERS[path.suffix.lower()](b, f)
    except (struct.error, IndexError, ValueError) as exc:
        f.info.append(("unreadable", f"{type(exc).__name__}: {exc}"))
    return f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("paths", nargs="*", help="files or directories (default: the repository and site/dist)")
    ap.add_argument("--verbose", action="store_true", help="list the other metadata fields too")
    args = ap.parse_args(argv)
    if args.paths:
        files = []
        for p in map(Path, args.paths):
            files += sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    else:
        files = repo_files(REPO)
    files = [p for p in files if p.suffix.lower() in EXT]
    exceptions, exc_errors = load_exceptions("check_media")
    fails, reported, n_info, by_ext = [], [], 0, Counter()
    for p in files:
        r = rel(p)
        by_ext[p.suffix.lower()] += 1
        f = scan(p)
        n_info += len(f.info)
        if args.verbose:
            for k, v in f.info:
                print(f"info   {r}: {k} = {mask(v) if PATH_RE.search(v) else v[:60]!r}")
        for rule, fld, val in f.items:
            line = f"{rule:6} {r}: {fld} {mask(val) if val else '(present)'}"
            if r.startswith(REPORT_ONLY):
                reported.append(line)
            elif excepted(exceptions, r, rule):
                continue
            else:
                fails.append(line)
    for line in fails:
        print(f"FAIL {line}")
    for line in reported:
        print(f"report (frozen bench, not failed) {line}")
    for e in exc_errors:
        print(f"FAIL {e}")
    kinds = ", ".join(f"{k} {v}" for k, v in sorted(by_ext.items())) or "none"
    print(f"check_media: {len(files)} media file(s) ({kinds}) — {len(fails)} finding(s) failed, "
          f"{len(reported)} reported under benches/, {n_info} other metadata field(s)"
          f"{' (--verbose lists them)' if n_info and not args.verbose else ''}")
    return 1 if fails or exc_errors else 0


if __name__ == "__main__":
    sys.exit(main())
