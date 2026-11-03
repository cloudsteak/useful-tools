#!/usr/bin/env python3
"""Egyszeri lekérdezés: közúti távolság (km) Szentendréről minden településre.

Használat:
  export ORS_KEY=a_te_openrouteservice_kulcsod   # ingyenes: openrouteservice.org
  python3 fetch_distances.py settlement_points.csv
Eredmény: distances.json  ({"Település": km, ...}); utána: python3 build.py settlement_points.csv
A kulcs csak ehhez a futtatáshoz kell, az oldalra nem kerül be.
"""
import csv, json, os, sys, urllib.request

ORIGIN = (19.07605, 47.66776)  # lon, lat — Szentendre
KEY = os.environ["ORS_KEY"]

rows = []
with open(sys.argv[1], encoding="utf-8") as f:
    for r in csv.DictReader(l for l in f if not l.startswith("#")):
        rows.append((r["name"], float(r["lon"]), float(r["lat"])))

out = {}
CHUNK = 1000
for i in range(0, len(rows), CHUNK):
    part = rows[i:i + CHUNK]
    body = {"locations": [list(ORIGIN)] + [[lon, lat] for _, lon, lat in part],
            "sources": [0], "metrics": ["distance"], "units": "km"}
    req = urllib.request.Request(
        "https://api.openrouteservice.org/v2/matrix/driving-car",
        data=json.dumps(body).encode(),
        headers={"Authorization": KEY, "Content-Type": "application/json"})
    dists = json.load(urllib.request.urlopen(req, timeout=120))["distances"][0][1:]
    for (name, _, _), d in zip(part, dists):
        if d is not None:
            out[name] = round(d, 1)
    print(f"{min(i + CHUNK, len(rows))}/{len(rows)}")

json.dump(out, open("distances.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("kész:", len(out), "település; hiányzik:", len(rows) - len(out))
