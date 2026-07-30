# rekordbox-export

Rekordbox 7 collection export CSV-be — deduplikált, remix/edit/mix nélkül.

A működési elv a [rekordbox-relocator](https://github.com/the1bit/rekordbox-relocator) eszközből származik: a titkosított `master.db` SQLCipher adatbázist olvassa (read-only).

## Mit csinál?

1. Dekriptálja a `~/Library/Pioneer/rekordbox/master.db` fájlt
2. Felismeri a remix/edit/mix alapú duplikációkat
3. Csoportokból **egyetlen** canonical bejegyzést exportál: alap artist + alap title (remix utótagok nélkül)
4. Artist szerinti ABC sorrendben rendez

### Példa

Ezek a collection-ben:

- Lady Gaga, Ariana Grande — Rain On Me (Rabeat Intro Edit)
- Lady Gaga, Ariana Grande — Rain On Me
- Lady Gaga, Ariana Grande, Purple Disco Machine — Rain On Me-Purple Disco Machine Remix-Edit
- Lady Gaga, Ariana Grande, Purple Disco Machine — Rain On Me-Purple Disco Machine Remix

Export eredmény (egyetlen sor, `;` elválasztó):

```text
Artist;Title
Lady Gaga, Ariana Grande;Rain On Me
2 Black;Waves Of Luv
20 Fingers, Gillette;Short short man
```

## Követelmények

- macOS
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- `sqlcipher` (`brew install sqlcipher`)
- Rekordbox **ne legyen futva** export közben

## Telepítés (uv)

```bash
cd rekordbox-export
uv sync
```

## Használat

```bash
# Alap export (aktuális mappába timestamp-es fájlnevekkel)
uv run rekordbox-export

# Egyedi kimeneti útvonalak
uv run rekordbox-export -o collection.csv --duplicates-report skipped.csv

# Csak collection CSV, duplikátum riport nélkül
uv run rekordbox-export -o collection.csv --no-duplicates-report
```

## Output

- **Collection CSV:** deduplikált track lista, `Artist;Title` formátum (pontosvessző, idézőjelek nélkül), artist szerint rendezve
- **Duplikátum riport CSV (opcionális):** mely track-ek kerültek egy csoportba (`CanonicalArtist`, `BaseTitle`, kihagyott változatok)
- **Konzol:** forrás/export számok + duplikátum csoportok
- **Exit code:** 0 = siker, 1 = hiba

## Működési logika

1. Előfeltételek ellenőrzése (`sqlcipher`, `master.db`, rekordbox nem fut)
2. SQLCipher dekriptálás (`~/.rekordbox_key` vagy univerzális kulcs)
3. `djmdContent` + `djmdArtist` JOIN lekérdezés
4. Duplikáció: azonos alapcím + metsző artist halmazok → egy csoport
5. Csoportonként: legrövidebb artist lista + alapcím (zárójelben/hyphen után remix/edit/mix utótag levágva)
6. Egységes artist formátum: `feat.` / `ft.` / `x` / `&` → vesszővel elválasztott lista
7. Hibás `Artist-Title` egy mezőben tárolt rekordok javítása (üres artist mező esetén)

## Kapcsolódó eszközök

- [clone-tags](../clone-tags/README.md) — MP3 ID3 tag klónozás WAV-be (Rekordbox-kompatibilis)
- [rekordbox-relocator](https://github.com/the1bit/rekordbox-relocator) — track útvonalak frissítése
