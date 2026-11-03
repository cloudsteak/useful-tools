#!/usr/bin/env python3
"""Legenerálja az index.html-t a template.html-ből és a település-adatokból.

Használat: python3 build.py settlement_points.csv
Adatforrás: OpenStreetMap place node-ok (ODbL), k-monitor/parlament repó.
"""
import csv, json, os, sys

COUNTY = {"01": "Budapest", "02": "Baranya", "03": "Bács-Kiskun", "04": "Békés",
          "05": "Borsod-Abaúj-Zemplén", "06": "Csongrád-Csanád", "07": "Fejér",
          "08": "Győr-Moson-Sopron", "09": "Hajdú-Bihar", "10": "Heves",
          "11": "Jász-Nagykun-Szolnok", "12": "Komárom-Esztergom", "13": "Nógrád",
          "14": "Pest", "15": "Somogy", "16": "Szabolcs-Szatmár-Bereg", "17": "Tolna",
          "18": "Vas", "19": "Veszprém", "20": "Zala"}

dist = json.load(open("distances.json", encoding="utf-8")) if os.path.exists("distances.json") else {}
rows = []
with open(sys.argv[1], encoding="utf-8") as f:
    lines = (l for l in f if not l.startswith("#"))
    for r in csv.DictReader(lines):
        rows.append([r["name"], COUNTY[r["id"][:2]], round(float(r["lat"]), 4), round(float(r["lon"]), 4), dist.get(r["name"])])
rows.sort(key=lambda r: r[0])
tpl = open("template.html", encoding="utf-8").read()
open("index.html", "w", encoding="utf-8").write(tpl.replace("__DATA__", json.dumps(rows, ensure_ascii=False, separators=(",", ":"))))
print(len(rows), "település")
