#!/bin/bash
# set-s3-download.sh
# S3 objektumok átállítása letöltésre kényszerítésre
#
# Használat:
#   ./set-s3-download.sh <bucket> <prefix> [region]

set -euo pipefail

usage() {
    cat <<EOF
Használat: $(basename "$0") <bucket> <prefix> [region]

Paraméterek:
  bucket   S3 bucket neve
  prefix   Objektum prefix (pl. videos/2026/)
  region   AWS region (opcionális, alapértelmezés: AWS_DEFAULT_REGION vagy aws configure)

Példa:
  $(basename "$0") my-bucket training/videos/2026/ us-east-1
EOF
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
    exit 1
fi

BUCKET="$1"
PREFIX="$2"
REGION="${3:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
REGION="${REGION:-us-east-1}"

# Biztosítjuk, hogy a prefix per jellel végződjön (ha nem üres)
if [[ -n "$PREFIX" && "$PREFIX" != */ ]]; then
    PREFIX="${PREFIX}/"
fi

# Listázzuk a fájlokat a megadott prefix alatt
aws s3api list-objects-v2 \
    --bucket "$BUCKET" \
    --prefix "$PREFIX" \
    --query 'Contents[].Key' \
    --output text | tr '\t' '\n' | while read -r KEY; do
    
    [ -z "$KEY" ] && continue
    
    # Csak fájlokat, ne "mappákat"
    [[ "$KEY" == */ ]] && continue
    
    # Fájlnév kinyerése a Content-Disposition-höz
    FILENAME=$(basename "$KEY")
    
    echo "Frissítés: $KEY"
    
    aws s3api copy-object \
        --bucket "$BUCKET" \
        --key "$KEY" \
        --copy-source "${BUCKET}/${KEY}" \
        --metadata-directive REPLACE \
        --content-type "application/octet-stream" \
        --content-disposition "attachment; filename=\"${FILENAME}\"" \
        --region "$REGION" \
        > /dev/null
    
    echo "  ✓ Kész"
done

echo ""
echo "Minden objektum frissítve."
