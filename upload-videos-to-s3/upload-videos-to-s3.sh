#!/bin/bash
# upload-videos-to-s3.sh
# Rename MP4/PDF files, upload to S3, attach training annotations, set download metadata, and print download links.
#
# Usage:
#   ./upload-videos-to-s3.sh <local_dir> <bucket/path/> [cloudfront_domain]
#
# Example:
#   ./upload-videos-to-s3.sh ./videos my-bucket/training/videos/2026/ cdn.example.com

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SET_S3_DOWNLOAD="${SCRIPT_DIR}/../set-s3-download/set-s3-download.sh"
ANNOTATION_NAME="training-info"

usage() {
    cat <<EOF
Használat: $(basename "$0") <helyi_mappa> <bucket/eleresi/ut> [cloudfront_domain]

Paraméterek:
  helyi_mappa        A feltöltendő MP4 és PDF fájlokat tartalmazó mappa
  bucket/eleresi/ut  S3 bucket és opcionális prefix (pl. my-bucket/videos/2026/)
  cloudfront_domain  Opcionális CloudFront domain (pl. d1234.cloudfront.net).
                     Ha nincs megadva, közvetlen S3 HTTPS linkek készülnek.

A mappában opcionálisan elhelyezhető kepzes.md vagy description.md fájl:
  - A teljes markdown tartalom kerül a leírásba.
  - A linkek automatikusan kinyerésre kerülnek (markdown, autolink, nyers URL).

Példa:
  $(basename "$0") ./videos my-bucket/training/module1/
  $(basename "$0") ./videos my-bucket/training/module1/ cdn.example.com
EOF
}

normalize_stem() {
    local stem="$1"
    python3 -c '
import sys
import unicodedata

ACCENT_MAP = str.maketrans(
    {
        "á": "a", "ä": "a", "é": "e", "ë": "e", "í": "i", "ï": "i",
        "ó": "o", "ö": "o", "ő": "o", "ú": "u", "ü": "u", "ű": "u", "ÿ": "y",
        "Á": "A", "Ä": "A", "É": "E", "Ë": "E", "Í": "I", "Ï": "I",
        "Ó": "O", "Ö": "O", "Ő": "O", "Ú": "U", "Ü": "U", "Ű": "U", "Ÿ": "Y",
    }
)

text = sys.argv[1].translate(ACCENT_MAP)
text = unicodedata.normalize("NFKD", text)
text = "".join(ch for ch in text if not unicodedata.combining(ch))
print(text.replace(" ", "_"))
' "$stem"
}

parse_s3_target() {
    local target="$1"

    target="${target#s3://}"
    target="${target%/}"

    if [[ -z "$target" ]]; then
        echo "Hiba: érvénytelen S3 cél: '$1'" >&2
        exit 1
    fi

    if [[ "$target" != */* ]]; then
        S3_BUCKET="$target"
        S3_PREFIX=""
    else
        S3_BUCKET="${target%%/*}"
        S3_PREFIX="${target#*/}/"
    fi
}

normalize_cloudfront_domain() {
    local domain="$1"
    domain="${domain#https://}"
    domain="${domain#http://}"
    domain="${domain%/}"
    echo "$domain"
}

resolve_bucket_region() {
    local bucket="$1"
    local location

    location="$(aws s3api get-bucket-location --bucket "$bucket" --output text 2>/dev/null || true)"
    location="${location//$'\n'/}"

    case "$location" in
        ""|None|null)
            echo "us-east-1"
            ;;
        EU)
            echo "eu-west-1"
            ;;
        *)
            echo "$location"
            ;;
    esac
}

find_description_file() {
    local dir="$1"

    for candidate in kepzes.md description.md; do
        if [[ -f "${dir%/}/$candidate" ]]; then
            echo "${dir%/}/$candidate"
            return 0
        fi
    done
}

s3_annotations_supported() {
    aws s3api put-object-annotation help >/dev/null 2>&1
}

build_annotation_payload() {
    local description_file="${1:--}"
    local manifest_file="$2"
    local output_file="$3"

    python3 -c '
import json
import re
import sys

description_path = sys.argv[1]
manifest_path = sys.argv[2]
output_path = sys.argv[3]

URL_PATTERN = re.compile(r"https?://[^\s\)\]<>\"]+")


def normalize_url(url: str) -> str:
    return url.rstrip(".,;:)\"'\''")


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(r"\[[^\]]*\]\((https?://[^\)]+)\)", text):
        url = normalize_url(match.group(1))
        if url not in seen:
            seen.add(url)
            links.append(url)

    for match in re.finditer(r"<(https?://[^>]+)>", text):
        url = normalize_url(match.group(1))
        if url not in seen:
            seen.add(url)
            links.append(url)

    for match in URL_PATTERN.finditer(text):
        url = normalize_url(match.group(0))
        if url not in seen:
            seen.add(url)
            links.append(url)

    return links


files = []
with open(manifest_path, encoding="utf-8") as manifest:
    for line in manifest:
        line = line.strip()
        if not line:
            continue
        files.append(line.split("|", 1)[0])

description = ""
links: list[str] = []
if description_path != "-":
    with open(description_path, encoding="utf-8") as handle:
        description = handle.read().strip()
    links = extract_links(description)

payload = {
    "files": sorted(files),
    "description": description,
    "description_format": "markdown",
    "links": links,
}

with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
' "$description_file" "$manifest_file" "$output_file"
}

s3_object_exists() {
    local key="$1"
    aws s3api head-object \
        --bucket "$S3_BUCKET" \
        --key "$key" \
        --region "$REGION" \
        >/dev/null 2>&1
}

upload_to_s3() {
    local local_file="$1"
    local s3_key="$2"
    local s3_uri="s3://${S3_BUCKET}/${s3_key}"

    if s3_object_exists "$s3_key"; then
        echo "  meglévő S3 objektum (nem töltődik fel újra): $s3_key"
        return 0
    fi

    echo "  feltöltés: $s3_key"
    aws s3 cp "$local_file" "$s3_uri" --region "$REGION" --skip-existing
}

put_object_annotation() {
    local key="$1"
    local payload_file="$2"

    aws s3api put-object-annotation \
        --bucket "$S3_BUCKET" \
        --key "$key" \
        --annotation-name "$ANNOTATION_NAME" \
        --annotation-payload "$payload_file" \
        --region "$REGION"
}

check_name_collision() {
    local new_name="$1"
    local original_name="$2"
    local names_file="$3"

    if grep -Fxq "$new_name" "$names_file" 2>/dev/null; then
        local previous
        previous="$(grep -F "$new_name|" "$names_file" | head -n 1 | cut -d'|' -f2)"
        if [[ "$previous" != "$original_name" ]]; then
            echo "Hiba: névütközés – '$previous' és '$original_name' ugyanarra a névre menne: '$new_name'" >&2
            exit 1
        fi
    fi

    echo "${new_name}|${original_name}" >> "$names_file"
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
    exit 1
fi

LOCAL_DIR="$1"
S3_TARGET="$2"
CF_DOMAIN=""
if [[ $# -eq 3 ]]; then
    CF_DOMAIN="$(normalize_cloudfront_domain "$3")"
fi

if [[ ! -d "$LOCAL_DIR" ]]; then
    echo "Hiba: a megadott mappa nem létezik: $LOCAL_DIR" >&2
    exit 1
fi

if [[ ! -x "$SET_S3_DOWNLOAD" ]]; then
    echo "Hiba: nem található a set-s3-download script: $SET_S3_DOWNLOAD" >&2
    exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "Hiba: az aws CLI nincs telepítve vagy nem elérhető." >&2
    exit 1
fi

parse_s3_target "$S3_TARGET"
REGION="$(resolve_bucket_region "$S3_BUCKET")"

echo "S3 bucket régió: ${REGION}"
echo ""

MANIFEST="$(mktemp)"
NAMES_FILE="$(mktemp)"
ANNOTATION_PAYLOAD="$(mktemp)"
trap 'rm -f "$MANIFEST" "$NAMES_FILE" "$ANNOTATION_PAYLOAD"' EXIT

upload_files="$(find "$LOCAL_DIR" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.pdf' \) | sort || true)"
DESCRIPTION_FILE="$(find_description_file "$LOCAL_DIR" || true)"

if [[ -z "$upload_files" ]]; then
    echo "Nincs MP4 vagy PDF fájl a mappában: $LOCAL_DIR"
    exit 0
fi

echo "=== Fájlok listája (MP4, PDF) ==="
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    echo "  $(basename "$file")"
done <<< "$upload_files"
echo ""

if [[ -n "$DESCRIPTION_FILE" ]]; then
    echo "Képzés leírás forrása: $(basename "$DESCRIPTION_FILE")"
    echo ""
fi

echo "=== Átnevezés ==="
while IFS= read -r file; do
    [[ -z "$file" ]] && continue

    filename="$(basename "$file")"
    stem="${filename%.*}"
    ext="${filename##*.}"
    new_stem="$(normalize_stem "$stem")"
    new_name="${new_stem}.${ext}"

    check_name_collision "$new_name" "$filename" "$NAMES_FILE"

    if [[ "$filename" == "$new_name" ]]; then
        echo "  változatlan: $filename"
    else
        target_path="${LOCAL_DIR%/}/$new_name"
        if [[ -e "$target_path" && "$target_path" != "$file" ]]; then
            echo "Hiba: a célfájl már létezik: $target_path (forrás: $filename)" >&2
            exit 1
        fi
        mv "$file" "$target_path"
        echo "  $filename -> $new_name"
        file="$target_path"
    fi

    printf '%s|%s\n' "$new_name" "$file" >> "$MANIFEST"
done <<< "$upload_files"
echo ""

echo "=== S3 feltöltés (s3://${S3_BUCKET}/${S3_PREFIX}) ==="
echo "  Megjegyzés: a már létező objektumok nem kerülnek felülírásra."
sort "$MANIFEST" | while IFS='|' read -r new_name file; do
    s3_key="${S3_PREFIX}${new_name}"
    upload_to_s3 "$file" "$s3_key"
done
echo ""

if s3_annotations_supported; then
    echo "=== S3 annotációk (${ANNOTATION_NAME}) ==="
    if [[ -n "$DESCRIPTION_FILE" ]]; then
        build_annotation_payload "$DESCRIPTION_FILE" "$MANIFEST" "$ANNOTATION_PAYLOAD"
    else
        build_annotation_payload "-" "$MANIFEST" "$ANNOTATION_PAYLOAD"
    fi

    sort "$MANIFEST" | while IFS='|' read -r new_name file; do
        s3_key="${S3_PREFIX}${new_name}"
        echo "  annotáció: $new_name"
        put_object_annotation "$s3_key" "$ANNOTATION_PAYLOAD"
    done
    echo ""
else
    echo "Figyelmeztetés: az aws CLI nem támogatja az S3 annotációkat (legalább 2.35.6 szükséges)." >&2
    echo "  Az annotációk kihagyva. Frissítsd az AWS CLI-t, majd futtasd újra a scriptet." >&2
    echo ""
fi

echo "=== Letöltési metaadatok beállítása ==="
"$SET_S3_DOWNLOAD" "$S3_BUCKET" "$S3_PREFIX" "$REGION"
echo ""

echo "=== Letöltési linkek ==="
sort "$MANIFEST" | while IFS='|' read -r new_name file; do
    if [[ -n "$CF_DOMAIN" ]]; then
        echo "https://${CF_DOMAIN}/${S3_PREFIX}${new_name}"
    else
        echo "https://${S3_BUCKET}.s3.${REGION}.amazonaws.com/${S3_PREFIX}${new_name}"
    fi
done
