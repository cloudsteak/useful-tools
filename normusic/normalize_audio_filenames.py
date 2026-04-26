from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path


ACCENT_MAP = str.maketrans(
    {
        "á": "a",
        "ä": "a",
        "é": "e",
        "ë": "e",
        "í": "i",
        "ï": "i",
        "ó": "o",
        "ö": "o",
        "ő": "o",
        "ú": "u",
        "ü": "u",
        "ű": "u",
        "ÿ": "y",
        "Á": "A",
        "Ä": "A",
        "É": "E",
        "Ë": "E",
        "Í": "I",
        "Ï": "I",
        "Ó": "O",
        "Ö": "O",
        "Ő": "O",
        "Ú": "U",
        "Ü": "U",
        "Ű": "U",
        "Ÿ": "Y",
    }
)

WORD_RE = re.compile(r"[A-Za-z0-9]+")
SUPPORTED_EXTENSIONS = {".wav", ".mp3"}


def normalize_stem(stem: str) -> str:
    text = stem.translate(ACCENT_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(" - ", "-")

    def title_word(match: re.Match[str]) -> str:
        word = match.group(0)
        return word[0].upper() + word[1:].lower()

    return WORD_RE.sub(title_word, text)


def find_audio_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def plan_renames(files: list[Path]) -> tuple[list[tuple[Path, Path]], list[str]]:
    planned: list[tuple[Path, Path]] = []
    errors: list[str] = []
    targets: dict[Path, Path] = {}
    source_inodes: set[tuple[int, int]] = set()
    for file in files:
        try:
            stat = file.stat()
            source_inodes.add((stat.st_dev, stat.st_ino))
        except OSError:
            continue

    for src in files:
        new_name = normalize_stem(src.stem) + src.suffix
        dst = src.with_name(new_name)

        if dst == src:
            continue

        existing_source = targets.get(dst)
        if existing_source is not None and existing_source != src:
            errors.append(
                f"Nevutkozes: '{existing_source.name}' es '{src.name}' ugyanarra a celra menne: '{dst.name}'"
            )
            continue

        if dst.exists():
            try:
                stat = dst.stat()
                dst_inode = (stat.st_dev, stat.st_ino)
            except OSError:
                dst_inode = None

            if dst_inode not in source_inodes:
                errors.append(
                    f"Cel fajl mar letezik: '{dst}' (forras: '{src}')"
                )
                continue

        targets[dst] = src
        planned.append((src, dst))

    return planned, errors


def execute_renames(planned: list[tuple[Path, Path]]) -> None:
    temp_moves: list[tuple[Path, Path]] = []

    for index, (src, _) in enumerate(planned):
        temp = src.with_name(f".normusic_tmp_{index}_{src.name}")
        while temp.exists():
            index += 1
            temp = src.with_name(f".normusic_tmp_{index}_{src.name}")
        src.rename(temp)
        temp_moves.append((temp, src))

    for (temp, original_src), (_, dst) in zip(temp_moves, planned, strict=True):
        if original_src == dst:
            temp.rename(original_src)
            continue
        temp.rename(dst)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WAV es MP3 fajlnevek normalizalasa egy mappan belul."
    )
    parser.add_argument("directory", type=Path, help="Gyokermappa")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak listaz, atnevezest nem hajt vegre.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root: Path = args.directory

    if not root.exists() or not root.is_dir():
        print(f"Hiba: a megadott utvonal nem letezo mappa: {root}", file=sys.stderr)
        return 1

    files = find_audio_files(root)
    planned, errors = plan_renames(files)
    total_files = len(files)
    wav_count = sum(1 for f in files if f.suffix.lower() == ".wav")
    mp3_count = sum(1 for f in files if f.suffix.lower() == ".mp3")
    planned_count = len(planned)
    unchanged_count = total_files - planned_count
    warning_count = len(errors)

    def print_stats() -> None:
        print(f"Osszes audio fajl: {total_files}")
        print(f"WAV fajl: {wav_count}")
        print(f"MP3 fajl: {mp3_count}")
        print(f"Atnevezendo fajl: {planned_count}")
        print(f"Valtozatlan fajl: {unchanged_count}")
        print(f"Warning: {warning_count}")

    for error in errors:
        print(f"[WARN] {error}", file=sys.stderr)

    if not planned:
        print("Nincs atnevezendo fajl.")
        print_stats()
        return 0 if not errors else 2

    mode = "DRY-RUN" if args.dry_run else "ATNEVEZES"
    print(f"{mode}: {planned_count} fajl")

    for src, dst in planned:
        print(f"{src} -> {dst}")

    if not args.dry_run:
        execute_renames(planned)

    print_stats()

    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
