# Útiköltség kalkulátor

Egyfájlos, függőségmentes widget (`index.html`), WordPressbe iframe-ben beágyazható.
A látogató beírja a település nevét, a kalkulátor kiszámolja az útiköltséget.

- Kiindulás: Szentendre, 40 km-ig ingyenes, fölötte 200 Ft/km (oda-vissza)
- Beállítások: `template.html` tetején a `CONFIG` blokk
- Újragenerálás: `python3 build.py settlement_points.csv` (az `index.html` generált fájl)
- Adatforrás: OpenStreetMap (ODbL) település-pontok, a k-monitor/parlament repóból
- Pontos közúti km: `ORS_KEY=... python3 fetch_distances.py settlement_points.csv` (egyszeri), majd `python3 build.py settlement_points.csv`
