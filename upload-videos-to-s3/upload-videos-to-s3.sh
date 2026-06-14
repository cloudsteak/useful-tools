#!/bin/bash
# upload-videos-to-s3.sh
# Rename MP4 files, upload to S3, set download metadata, and print download links.
#
# Usage:
#   ./upload-videos-to-s3.sh <local_dir> <bucket/path/> [cloudfront_domain]
#
# Example:
#   ./upload-videos-to-s3.sh ./videos my-bucket/training/videos/2026/ cdn.example.com

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SET_S3_DOWNLOAD="${SCRIPT_DIR}/../set-s3-download/set-s3-download.sh"

usage() {
    cat <<EOF
Használat: $(basename "$0") <helyi_mappa> <bucket/eleresi/ut> [cloudfront_domain]

Paraméterek:
  helyi_mappa        A feltöltendő MP4 fájlokat tartalmazó mappa
  bucket/eleresi/ut  S3 bucket és opcionális prefix (pl. my-bucket/videos/2026/)
  cloudfront_domain  Opcionális CloudFront domain (pl. d1234.cloudfront.net).
                     Ha nincs megadva, közvetlen S3 HTTPS linkek készülnek.

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

s3_object_exists() {
    local key="$1"
    aws s3api head-object \
        --bucket "$S3_BUCKET" \
        --key "$key" \
        --region "$REGION" \
        >/dev/null 2>&1
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
REGION="${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}"
REGION="${REGION:-us-east-1}"

MANIFEST="$(mktemp)"
NAMES_FILE="$(mktemp)"
trap 'rm -f "$MANIFEST" "$NAMES_FILE"' EXIT

mp4_files="$(find "$LOCAL_DIR" -maxdepth 1 -type f -iname '*.mp4' | sort || true)"

if [[ -z "$mp4_files" ]]; then
    echo "Nincs MP4 fájl a mappában: $LOCAL_DIR"
    exit 0
fi

echo "=== MP4 fájlok listája ==="
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    echo "  $(basename "$file")"
done <<< "$mp4_files"
echo ""

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
done <<< "$mp4_files"
echo ""

echo "=== S3 feltöltés (s3://${S3_BUCKET}/${S3_PREFIX}) ==="
sort "$MANIFEST" | while IFS='|' read -r new_name file; do
    s3_key="${S3_PREFIX}${new_name}"
    s3_uri="s3://${S3_BUCKET}/${s3_key}"

    if s3_object_exists "$s3_key"; then
        echo "  kihagyva (már létezik): $new_name"
    else
        echo "  feltöltés: $new_name"
        aws s3 cp "$file" "$s3_uri" --region "$REGION"
    fi
done
echo ""

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
