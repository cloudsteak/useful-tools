#!/usr/bin/env python3
"""
rekordbox_export.py - Rekordbox collection export CSV-be.

Exportálja a collection dalait deduplikálva: remix/edit/mix változatokból
egyetlen canonical bejegyzés marad (alap artist + alap title).

Használat:
    uv run rekordbox-export
    uv run rekordbox-export -o collection.csv --duplicates-report skipped.csv
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from lib.database import decrypt_database, get_all_tracks, verify_prerequisites
from lib.dedup import build_export_entries
from lib.normalize import normalize_track


def write_collection_csv(path: Path, entries: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("Artist;Title\n")
        for artist, title in entries:
            handle.write(f"{artist};{title}\n")


def write_duplicates_report(path: Path, groups) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("Group;CanonicalArtist;BaseTitle;SkippedArtist;SkippedTitle\n")
        for group_index, group in enumerate(groups, start=1):
            for _, artist, title in group.tracks:
                handle.write(
                    f"{group_index};{group.canonical_artist};{group.base_title};{artist};{title}\n"
                )


def print_summary(
    source_count: int,
    export_count: int,
    groups,
) -> None:
    skipped = source_count - export_count
    print(f"Forrás: {source_count} track → export: {export_count} track ({skipped} kihagyva)")
    if not groups:
        print("Duplikátum csoport: nincs találat.")
        return

    print(f"Duplikátum csoport: {len(groups)}")
    print()
    for group_index, group in enumerate(groups, start=1):
        print(f"[{group_index}] {group.canonical_artist} — {group.base_title}")
        for _, artist, title in group.tracks:
            marker = "→" if artist == group.canonical_artist and title == group.base_title else " "
            print(f"  {marker} {artist} — {title}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rekordbox collection export CSV-be (deduplikált, remix nélkül)"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Export CSV útvonala (alapértelmezett: rekordbox_export_<timestamp>.csv)",
    )
    parser.add_argument(
        "--duplicates-report",
        type=Path,
        help="Kihagyott duplikátumok riportja (alapértelmezett: rekordbox_duplicates_<timestamp>.csv)",
    )
    parser.add_argument(
        "--no-duplicates-report",
        action="store_true",
        help="Ne írjon duplikátum riport fájlt",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    ok, error = verify_prerequisites()
    if not ok:
        print(f"Hiba: {error}", file=sys.stderr)
        return 1

    print("Rekordbox adatbázis dekriptálása...")
    if not decrypt_database():
        print(
            "Hiba: az adatbázis dekriptálása sikertelen. "
            "Ellenőrizd a ~/.rekordbox_key fájlt, vagy futtasd a rekordbox-relocator test_key.sh scriptjét.",
            file=sys.stderr,
        )
        return 1

    tracks = [
        (track_id, *normalize_track(artist, title))
        for track_id, artist, title in get_all_tracks()
        if artist.strip() or title.strip()
    ]
    if not tracks:
        print("Nincs exportálható track a collection-ben.", file=sys.stderr)
        return 1

    export_entries, duplicate_groups = build_export_entries(tracks)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or Path(f"rekordbox_export_{timestamp}.csv")
    duplicates_path = None if args.no_duplicates_report else (
        args.duplicates_report or Path(f"rekordbox_duplicates_{timestamp}.csv")
    )

    write_collection_csv(output_path, export_entries)
    print_summary(len(tracks), len(export_entries), duplicate_groups)

    print(f"Export kész: {output_path}")

    if duplicates_path and duplicate_groups:
        write_duplicates_report(duplicates_path, duplicate_groups)
        print(f"Duplikátum riport: {duplicates_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
