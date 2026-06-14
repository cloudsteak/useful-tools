# Upload Videos to S3

Bash script for preparing MP4 files, uploading them to S3, configuring download metadata, and printing download links.

## What it does

1. **Lists** all `.mp4` files in the given folder (non-recursive)
2. **Renames** files in place: removes Hungarian accents and replaces spaces with `_`
3. **Uploads** renamed files to the specified S3 bucket and prefix
4. **Sets download metadata** via [`set-s3-download`](../set-s3-download/set-s3-download.sh) so files are served as attachments
5. **Prints download links** for every processed file

## Features

- Unicode-safe renaming (handles macOS NFD filenames, e.g. `e` + combining accent instead of a single accented character)
- Skips S3 upload when the object already exists at the target key
- Safe to re-run: already renamed local files and already uploaded S3 objects are skipped
- Optional CloudFront domain for CDN links; without it, direct S3 HTTPS links are printed
- Detects rename collisions before any upload starts

## Requirements

- Bash 3.2+
- Python 3 (Unicode normalization)
- [AWS CLI](https://aws.amazon.com/cli/) configured with credentials for the target bucket
- Executable [`set-s3-download.sh`](../set-s3-download/set-s3-download.sh)

## Usage

```bash
chmod +x upload-videos-to-s3.sh

./upload-videos-to-s3.sh <local_dir> <bucket/path/> [cloudfront_domain]
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `local_dir` | Folder containing MP4 files to upload |
| `bucket/path/` | S3 bucket and optional prefix, e.g. `my-bucket/videos/2026/` |
| `cloudfront_domain` | Optional. If omitted, direct S3 HTTPS links are printed |

The bucket/path accepts both `my-bucket/folder/subfolder/` and `s3://my-bucket/folder/subfolder/`.

### Examples

Single line (recommended for paths with spaces):

```bash
./upload-videos-to-s3.sh "./videos/My Course" my-bucket/training/videos/2026/
```

With CloudFront:

```bash
./upload-videos-to-s3.sh \
  "./videos" \
  "my-bucket/training/videos/2026/" \
  "cdn.example.com"
```

When using line continuations, make sure `\` is the **last character** on the line (no trailing spaces).

### Rename example

Filenames are normalized for S3 compatibility:

| Before | After |
|--------|-------|
| `My First Video.mp4` | `My_First_Video.mp4` |
| `Lesson 02 - Getting Started.mp4` | `Lesson_02_-_Getting_Started.mp4` |
| `Demo recording (final).mp4` | `Demo_recording_(final).mp4` |

Accented characters (e.g. `á`, `é`, `ő`) are removed. Spaces become `_`.

### Download links

Without CloudFront:

```
https://my-bucket.s3.us-east-1.amazonaws.com/training/videos/2026/My_First_Video.mp4
```

With CloudFront:

```
https://cdn.example.com/training/videos/2026/My_First_Video.mp4
```

## Output

The script prints progress in labeled sections:

```
=== MP4 file list ===
=== Renaming ===
  unchanged: already_normalized.mp4
  old_name.mp4 -> new_name.mp4
=== S3 upload (s3://bucket/prefix/) ===
  uploading: new_file.mp4
  skipped (already exists): existing_file.mp4
=== Download metadata setup ===
=== Download links ===
https://...
```

> Console section headers and status messages are in Hungarian in the script itself.

## Notes

- Only files directly in the given folder are processed (no subfolders).
- Name collisions after normalization abort the script before upload.
- Existing S3 objects are not re-uploaded; download links are still printed for all local MP4 files.
- AWS region resolution order: `AWS_DEFAULT_REGION` → `aws configure get region` → `us-east-1`.

## Related

- [`set-s3-download.sh`](../set-s3-download/set-s3-download.sh) — sets `Content-Type` and `Content-Disposition` on S3 objects for forced download. Can also be run standalone:

```bash
./set-s3-download.sh <bucket> <prefix> [region]
```
