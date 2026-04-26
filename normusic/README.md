# NorMusic – Normalize Audio Filenames

**NorMusic** is a command-line tool that normalizes WAV and MP3 filenames in a directory tree. It strips accented characters, applies title-case formatting, and replaces ` - ` separators consistently so that filenames are clean and portable across systems.

## Features

- Recursively scans a directory for `.wav` and `.mp3` files
- Replaces accented/special characters (e.g. `á→a`, `ö→o`, `ű→u`, including uppercase variants)
- Applies title-case to each word in the filename
- Preserves ` - ` separators by converting them to `-`
- Detects and reports naming conflicts before renaming
- `--dry-run` mode to preview changes without modifying any files
- Safe two-phase rename to avoid collisions on case-insensitive file systems

## Requirements

- Python 3.13

## Installation

```bash
cd normusic
pip install .
```

This installs the `normusic` command.

## Usage

```bash
# Preview renames (no files are changed)
normusic --dry-run /path/to/music

# Apply renames
normusic /path/to/music
```

## Output

```
ATNEVEZES: 3 fajl
/music/éneklés.mp3 -> /music/Enekles.mp3
...
Osszes audio fajl: 10
WAV fajl: 4
MP3 fajl: 6
Atnevezendo fajl: 3
Valtozatlan fajl: 7
Warning: 0
```

Exit codes:
| Code | Meaning |
|------|---------|
| `0`  | Success, no warnings |
| `2`  | Completed with warnings (e.g. naming conflicts) |
| `1`  | Fatal error (directory not found) |
