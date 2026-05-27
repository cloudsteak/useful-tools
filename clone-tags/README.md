# clone-tags

MP3 ID3 tag-ek teljes klónozása WAV fájlokba — Rekordbox-kompatibilis.

Minden ID3v2 frame 1:1-ben átmásolódik (TXXX, GEOB, APIC, PRIV, COMM, TIT2, TPE1, TBPM, TKEY, stb.), beleértve a Rekordbox proprietary adatokat: cue pontok, beatgrid, hot cue-k, memory cue-k, loops, color tags, waveform adatok, artwork.

## Telepítés (uv)

```bash
cd clone-tags

# venv létrehozása
uv venv

# dependency-k telepítése a pyproject.toml alapján
uv sync
```

Gyors összefoglaló:

- **Futtatás (ajánlott):** `uv run clone-tags ...`
- **Alternatíva:** `uv run python clone_tags.py ...`
- **Aktiválás:** nem szükséges

## Használat

```bash
# CSV formátum (mapping.csv):
#   track01.mp3;track01.wav
#   track02.mp3;track02.wav
#   # komment sorok és üres sorok megengedettek

# Dry-run (nem módosít semmit, csak megmutatja mit csinálna)
uv run clone-tags --dir /path/to/zenek --csv mapping.csv --dry-run

# Éles futtatás
uv run clone-tags --dir /path/to/zenek --csv mapping.csv

# Egyedi report útvonal
uv run clone-tags --dir /path/to/zenek --csv mapping.csv --report /tmp/my_report.csv
```

## Output

- **Konzol:** soronként státusz (OK / DRYRUN / SKIP / ERROR) + frame szám és típusok
- **Report CSV:** automatikusan a `--dir` mappába `clone_tags_report_<timestamp>.csv` néven (dry-run esetén `_dryrun` suffix-szel)
  - Oszlopok: `mp3;wav;status;frame_count;frame_types;bytes_written;message`
- **Exit code:** 0 ha minden OK, 1 ha volt hiba, 2 ha argumentum hiba

## Működési logika

1. MP3 megnyitás → összes ID3v2 frame kiolvasása
2. Frame-ek `deepcopy`-val átmásolva (a GEOB/APIC bináris payload védelmében)
3. WAV meglévő ID3 chunk törlése (tiszta lap)
4. Frame-ek `HashKey`-alapú hozzárendelése (több TXXX/GEOB/PRIV is megmarad)
5. Mentés ID3v2.3 verzióban ha az MP3 is 2.3 volt (Rekordbox ezt preferálja)

## Backup ajánlás

Első éles futtatás előtt érdemes backup-ot csinálni:

```bash
rsync -a zenek/ zenek_backup_$(date +%Y%m%d)/
```
