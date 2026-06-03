#!/bin/bash
# set-s3-download.sh
# S3 objektumok átállítása letöltésre kényszerítésre

set -euo pipefail

BUCKET="mentor-klub-kepzesek"
PREFIX="it/github-vscode-2026/"
REGION="eu-north-1"

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
