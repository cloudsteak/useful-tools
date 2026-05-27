#!/usr/bin/env python3
"""
clone_tags.py - MP3 ID3 tag-ek teljes klónozása WAV fájlokba.

Minden ID3v2 frame átmásolódik 1:1-ben (TXXX, GEOB, APIC, PRIV, COMM, stb.),
beleértve a Rekordbox proprietary adatokat (cue-k, beatgrid, hot cue-k,
memory cue-k, loops, color tags, waveform adatok).

A CSV formátum soronként:  mp3_filename;wav_filename
(A fájloknak a --dir mappában kell lenniük.)

Használat (aktivált venv-ben):
    python clone_tags.py --dir /path/to/folder --csv mapping.csv [--dry-run]
"""

from __future__ import annotations

import argparse
import copy
import csv
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mutagen.apev2 import APEv2, APENoHeaderError
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.wave import WAVE


# ----------------------------------------------------------------------
# RIFF INFO (Tag3) támogatás — forrás: MP3 APE tag (Tag3)
# ----------------------------------------------------------------------

# APE kulcs → RIFF INFO chunk ID megfeleltetés (kis/nagybetű-érzéketlen keresés)
_APE_TO_RIFF: dict[str, str] = {
    "title":    "INAM",
    "artist":   "IART",
    "album":    "IPRD",
    "genre":    "IGNR",
    "year":     "ICRD",
    "track":    "ITRK",
    "comment":  "ICMT",
    "bpm":      "IBPM",
    "key":      "IKEY",
    "composer": "IMUS",
    "encoder":  "ISFT",
    "band":     "IENG",
}


def _build_riff_info(ape_tags: APEv2 | None) -> bytes:
    """LIST INFO chunk összeállítása az MP3 APE tag-jeiből (Tag3 → Tag3)."""
    if ape_tags is None:
        return b""

    subchunks = b""
    seen: set[str] = set()

    for ape_key, ape_val in ape_tags.items():
        riff_id = _APE_TO_RIFF.get(ape_key.lower())
        if riff_id is None or riff_id in seen:
            continue
        value = str(ape_val).strip()
        if not value:
            continue
        try:
            data = value.encode("latin-1") + b"\x00"
        except UnicodeEncodeError:
            data = value.encode("utf-8") + b"\x00"
        size = len(data)
        subchunks += riff_id.encode("ascii") + struct.pack("<I", size) + data
        if size % 2 != 0:
            subchunks += b"\x00"
        seen.add(riff_id)

    if not subchunks:
        return b""

    list_content = b"INFO" + subchunks
    list_chunk = b"LIST" + struct.pack("<I", len(list_content)) + list_content
    if len(list_content) % 2 != 0:
        list_chunk += b"\x00"
    return list_chunk


def _rewrite_riff(wav_path: Path, *, drop_list_info: bool = False,
                  append: bytes = b"") -> None:
    """Nyers RIFF újraírás: nem-ASCII ID-jű chunk-ok eltávolítása,
    opcionálisan a régi LIST INFO kihagyása és új chunk hozzáfűzése."""
    data = wav_path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Nem valid WAV fájl")

    out = b""
    i = 12
    while i + 8 <= len(data):
        fourcc = data[i:i + 4]
        size = struct.unpack_from("<I", data, i + 4)[0]
        chunk_total = 8 + size + (size % 2)

        # Nem-printable ASCII ID-jű chunk-ok kihagyása (pl. ID3\x04)
        if not all(0x20 <= b <= 0x7E for b in fourcc):
            i += chunk_total
            continue

        if drop_list_info and fourcc == b"LIST" and data[i + 8:i + 12] == b"INFO":
            i += chunk_total
            continue

        out += data[i:i + chunk_total]
        i += chunk_total

    out += append
    wav_path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(out)) + b"WAVE" + out)


def _write_riff_info(wav_path: Path, info_chunk: bytes) -> None:
    """LIST INFO chunk beírása (vagy cseréje) a WAV RIFF struktúrájába."""
    _rewrite_riff(wav_path, drop_list_info=True, append=info_chunk)


# ----------------------------------------------------------------------
# Eredmény modell
# ----------------------------------------------------------------------

@dataclass
class Result:
    mp3: str
    wav: str
    status: str  # OK | ERROR | DRYRUN | SKIP
    frame_count: int = 0
    frame_types: list[str] = field(default_factory=list)
    bytes_written: int = 0
    message: str = ""


# ----------------------------------------------------------------------
# Fő logika
# ----------------------------------------------------------------------

def read_mp3_tags(mp3_path: Path) -> tuple[ID3, APEv2 | None]:
    """Kiolvassa az MP3 ID3 (Tag2) és APE (Tag3) tag-jeit."""
    mp3 = MP3(str(mp3_path))
    if mp3.tags is None:
        raise ValueError("nincs ID3 tag az MP3-ban")
    try:
        ape = APEv2(str(mp3_path))
    except APENoHeaderError:
        ape = None
    return mp3.tags, ape


def clone_tags(mp3_path: Path, wav_path: Path, dry_run: bool) -> Result:
    """Egy MP3 -> WAV tag klónozás elvégzése."""
    result = Result(mp3=mp3_path.name, wav=wav_path.name, status="ERROR")

    # Létezés ellenőrzés
    if not mp3_path.is_file():
        result.message = "MP3 nem található"
        return result
    if not wav_path.is_file():
        result.message = "WAV nem található"
        return result

    # MP3 tag olvasás (Tag2: ID3v2, Tag3: APE)
    try:
        src_tags, ape_tags = read_mp3_tags(mp3_path)
    except ID3NoHeaderError:
        result.message = "MP3-ban nincs ID3 header"
        return result
    except Exception as e:
        result.message = f"MP3 olvasási hiba: {e}"
        return result

    # Frame-ek összegyűjtése: deepcopy + v2.3-ra konvertálás
    # (ha a forrás v2.4, az UTF-8 kódolású frame-ek – COMM, TKEY, TXXX, stb. –
    # elveszhetnek implicit konverzióban; update_to_v23() ezt kezeli rendesen)
    working_tags = copy.deepcopy(src_tags)
    working_tags.update_to_v23()
    frames = list(working_tags.values())
    result.frame_count = len(frames)
    result.frame_types = sorted({f.FrameID for f in frames})

    if result.frame_count == 0:
        result.message = "nincs másolandó frame"
        result.status = "SKIP"
        return result

    # Dry-run: itt megállunk
    if dry_run:
        result.status = "DRYRUN"
        result.message = f"{result.frame_count} frame másolódna"
        return result

    # WAV megnyitás, meglévő ID3 tisztítása
    try:
        # Nem-standard chunk-ok (pl. ID3\x04) eltávolítása hogy mutagen meg tudja nyitni
        _rewrite_riff(wav_path)
        wav = WAVE(str(wav_path))
        if wav.tags is not None:
            wav.delete()          # ID3 chunk eltávolítása a WAV-ból
            wav = WAVE(str(wav_path))  # újra betöltés
        if wav.tags is None:
            wav.add_tags()

        # Source ID3 verzió és flag-ek átvétele, hogy bitre ugyanaz legyen
        wav.tags.version = src_tags.version

        # Frame-ek hozzáadása egyenként
        for frame in frames:
            # A HashKey biztosítja hogy pl. több TXXX/PRIV/GEOB frame
            # egymás mellett megmarad (mindnek egyedi HashKey-e van)
            wav.tags[frame.HashKey] = frame

        # Mindig v2.3-ként mentünk: Rekordbox ezt preferálja, és az
        # update_to_v23() már elvégezte a frame konverziót
        wav.tags.save(str(wav_path), v2_version=3)

        # RIFF INFO chunk (Tag3) írása – forrás: MP3 APE (Tag3), nem ID3
        info_chunk = _build_riff_info(ape_tags)
        if info_chunk:
            _write_riff_info(wav_path, info_chunk)

        # Tényleges fájlméret infó a reporthoz
        result.bytes_written = wav_path.stat().st_size
        result.status = "OK"
        result.message = f"{result.frame_count} frame átírva (ID3 + RIFF INFO)"
    except Exception as e:
        result.message = f"WAV írási hiba: {e}"

    return result


# ----------------------------------------------------------------------
# CSV feldolgozás
# ----------------------------------------------------------------------

def load_csv(csv_path: Path) -> list[tuple[str, str]]:
    """CSV beolvasás. Formátum: mp3;wav vagy mp3,wav soronként. Komment: #"""
    pairs: list[tuple[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        for lineno, row in enumerate(reader, start=1):
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            if len(row) < 2:
                # Fallback: ha a sor egyetlen elemként jött be, próbáljuk
                # kézzel szeparálni ';' vagy ',' mentén.
                raw = row[0] if row else ""
                if ";" in raw:
                    parts = raw.split(";", 1)
                    pairs.append((parts[0].strip(), parts[1].strip()))
                    continue
                if "," in raw:
                    parts = raw.split(",", 1)
                    pairs.append((parts[0].strip(), parts[1].strip()))
                    continue
                print(f"  FIGYELEM: {csv_path.name}:{lineno} - hibás sor, kihagyva: {row}",
                      file=sys.stderr)
                continue
            pairs.append((row[0].strip(), row[1].strip()))
    return pairs


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

def print_report(results: list[Result], dry_run: bool) -> None:
    total = len(results)
    ok = sum(1 for r in results if r.status == "OK")
    dryrun = sum(1 for r in results if r.status == "DRYRUN")
    skip = sum(1 for r in results if r.status == "SKIP")
    errors = sum(1 for r in results if r.status == "ERROR")

    print()
    print("=" * 70)
    print(f"  ÖSSZEGZÉS  {'(DRY-RUN)' if dry_run else ''}")
    print("=" * 70)
    print(f"  Összes fájlpár    : {total}")
    print(f"  Sikeres           : {ok}")
    if dry_run:
        print(f"  Dry-run rendben   : {dryrun}")
    print(f"  Kihagyva          : {skip}")
    print(f"  Hibás             : {errors}")
    print("=" * 70)

    if errors:
        print("\nHIBÁS FÁJLOK:")
        for r in results:
            if r.status == "ERROR":
                print(f"  [X] {r.mp3} -> {r.wav}")
                print(f"      {r.message}")

    if skip:
        print("\nKIHAGYOTT FÁJLOK:")
        for r in results:
            if r.status == "SKIP":
                print(f"  [-] {r.mp3} -> {r.wav}: {r.message}")


def write_report_csv(results: list[Result], out_path: Path) -> None:
    """Részletes CSV report - minden fájlpár egy sor."""
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["mp3", "wav", "status", "frame_count",
                    "frame_types", "bytes_written", "message"])
        for r in results:
            w.writerow([
                r.mp3,
                r.wav,
                r.status,
                r.frame_count,
                ",".join(r.frame_types),
                r.bytes_written,
                r.message,
            ])


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="MP3 ID3 tag-ek teljes klónozása WAV fájlokba (Rekordbox-kompatibilis).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-d", "--dir", required=True, type=Path,
                   help="Mappa ahol az MP3 és WAV fájlok vannak")
    p.add_argument("-c", "--csv", required=True, type=Path,
                   help="CSV mapping fájl (mp3;wav soronként)")
    p.add_argument("--dry-run", action="store_true",
                   help="Nem módosít, csak megmutatja mit csinálna")
    p.add_argument("--report", type=Path, default=None,
                   help="Részletes CSV report útvonal (alapértelmezett: auto timestamp)")
    args = p.parse_args()

    base_dir: Path = args.dir.expanduser().resolve()
    if not base_dir.is_dir():
        print(f"HIBA: a mappa nem létezik: {base_dir}", file=sys.stderr)
        return 2

    if not args.csv.is_file():
        print(f"HIBA: a CSV nem létezik: {args.csv}", file=sys.stderr)
        return 2

    pairs = load_csv(args.csv)
    if not pairs:
        print("HIBA: nincs feldolgozható sor a CSV-ben", file=sys.stderr)
        return 2

    print(f"Mappa    : {base_dir}")
    print(f"CSV      : {args.csv}")
    print(f"Fájlpár  : {len(pairs)}")
    print(f"Mód      : {'DRY-RUN (nem módosít)' if args.dry_run else 'ÍRÁS'}")
    print("-" * 70)

    results: list[Result] = []
    for idx, (mp3_name, wav_name) in enumerate(pairs, start=1):
        mp3_path = base_dir / mp3_name
        wav_path = base_dir / wav_name
        print(f"[{idx:>4}/{len(pairs)}] {mp3_name}  ->  {wav_name}")
        r = clone_tags(mp3_path, wav_path, args.dry_run)
        results.append(r)

        marker = {"OK": "✓", "DRYRUN": "→", "SKIP": "-", "ERROR": "✗"}[r.status]
        print(f"          {marker} {r.status}: {r.message}")
        if r.frame_count and r.status in ("OK", "DRYRUN"):
            print(f"            frame-ek ({r.frame_count}): {', '.join(r.frame_types)}")

    print_report(results, args.dry_run)

    # Report CSV
    if args.report is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_dryrun" if args.dry_run else ""
        report_path = base_dir / f"clone_tags_report_{ts}{suffix}.csv"
    else:
        report_path = args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report_csv(results, report_path)
    print(f"\nRészletes report: {report_path}")

    # Exit code: 0 ha minden OK vagy dry-run, 1 ha volt hiba
    return 0 if not any(r.status == "ERROR" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
