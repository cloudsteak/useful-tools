# Upload Videos to S3

Bash script for preparing MP4 and PDF files, uploading them to S3, attaching training annotations, configuring download metadata, and printing download links.

## What it does

1. **Lists** all `.mp4` and `.pdf` files in the given folder (non-recursive)
2. **Renames** files in place: removes Hungarian accents and replaces spaces with `_`
3. **Uploads** renamed files to the specified S3 bucket and prefix
4. **Attaches S3 annotations** (`training-info`) with file names, training description, and related links
5. **Sets download metadata** via [`set-s3-download`](../set-s3-download/set-s3-download.sh) so files are served as attachments
6. **Prints download links** for every processed file

## Features

- Unicode-safe renaming (handles macOS NFD filenames, e.g. `e` + combining accent instead of a single accented character)
- **Never re-uploads** existing S3 objects at the same key (`head-object` check + `aws s3 cp --skip-existing`)
- Skips download-metadata updates when `Content-Disposition: attachment` is already set
- Safe to re-run: already renamed local files and already uploaded S3 objects are left unchanged
- Optional CloudFront domain for CDN links; without it, direct S3 HTTPS links are printed
- Detects rename collisions before any upload starts
- Attaches the same structured annotation to every uploaded object for queryability

## Requirements

- Bash 3.2+
- Python 3 (Unicode normalization and annotation JSON)
- [AWS CLI](https://aws.amazon.com/cli/) **2.35.6+** for S3 annotations (`put-object-annotation`)
- AWS credentials with `s3:PutObject`, `s3:PutObjectAnnotation`, and `s3:GetObjectAnnotation` on the target bucket
- Executable [`set-s3-download.sh`](../set-s3-download/set-s3-download.sh)

## Usage

```bash
chmod +x upload-videos-to-s3.sh

./upload-videos-to-s3.sh <local_dir> <bucket/path/> [cloudfront_domain]
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `local_dir` | Folder containing MP4/PDF files to upload |
| `bucket/path/` | S3 bucket and optional prefix, e.g. `my-bucket/videos/2026/` |
| `cloudfront_domain` | Optional. If omitted, direct S3 HTTPS links are printed |

The bucket/path accepts both `my-bucket/folder/subfolder/` and `s3://my-bucket/folder/subfolder/`.

### Training description file

Place either `kepzes.md` or `description.md` in the upload folder (non-recursive). The file is **not** uploaded; its content is stored in S3 annotations.

- The full Markdown content is stored in the `description` field
- Links are extracted automatically from Markdown links, autolinks, and bare URLs

Example `kepzes.md`:

```markdown
# AWS Bedrock képzés – 2026.01

Ez a modul bemutatja a Bedrock alapfunkcióit és az agentic AI mintákat.

## Linkek

- [Bedrock dokumentáció](https://docs.aws.amazon.com/bedrock/)
- <https://cloudmentor.hu/>
```

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
| `Jegyzet - Bevezető.pdf` | `Jegyzet_-_Bevezeto.pdf` |

Accented characters (e.g. `á`, `é`, `ő`) are removed. Spaces become `_`.

### S3 annotation

Each uploaded object receives a `training-info` annotation (JSON), for example:

```json
{
  "files": [
    "AWS_Bedrock_01.mp4",
    "AWS_Bedrock_02.mp4",
    "Jegyzet_-_Bevezeto.pdf"
  ],
  "description": "# AWS Bedrock képzés – 2026.01\n\nEz a modul bemutatja...",
  "description_format": "markdown",
  "links": [
    "https://docs.aws.amazon.com/bedrock/",
    "https://cloudmentor.hu/"
  ]
}
```

Read annotations with:

```bash
aws s3api get-object-annotation \
  --bucket my-bucket \
  --key training/videos/2026/AWS_Bedrock_01.mp4 \
  --annotation-name training-info ./training-info.json
```

See also: [AWS S3 annotations overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/annotations-overview.html).

### Download links

Without CloudFront:

```
https://my-bucket.s3.eu-north-1.amazonaws.com/training/videos/2026/My_First_Video.mp4
https://my-bucket.s3.us-east-1.amazonaws.com/training/videos/2026/Jegyzet.pdf
```

With CloudFront:

```
https://cdn.example.com/training/videos/2026/My_First_Video.mp4
https://cdn.example.com/training/videos/2026/Jegyzet.pdf
```

## Output

The script prints progress in labeled sections:

```
=== Fájlok listája (MP4, PDF) ===
=== Átnevezés ===
=== S3 feltöltés (s3://bucket/prefix/) ===
=== S3 annotációk (training-info) ===
=== Letöltési metaadatok beállítása ===
=== Letöltési linkek ===
https://...
```

> Console section headers and status messages are in Hungarian in the script itself.

## Notes

- Only files directly in the given folder are processed (no subfolders).
- Name collisions after normalization abort the script before upload.
- Existing S3 objects are **never overwritten**; only missing objects are uploaded.
- Download metadata is only updated on objects that are not yet configured for attachment download.
- Annotations are refreshed on every run (metadata only, not the file content).
- Annotations are always stored at S3 Standard pricing, regardless of the object's storage class.
- AWS region is resolved from the target bucket location (`get-bucket-location`), not from local CLI defaults

## Related

- [`set-s3-download.sh`](../set-s3-download/set-s3-download.sh) — sets `Content-Type` and `Content-Disposition` on S3 objects for forced download. Can also be run standalone:

```bash
./set-s3-download.sh <bucket> <prefix> [region]
```
