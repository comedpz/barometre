#!/usr/bin/env python3
"""Rafraîchit data/us.json et data/fr.json.

Sources automatiques : FRED (clé gratuite, variable FRED_API_KEY), BCE Data Portal (sans clé),
INSEE BDM (optionnel, variable INSEE_TOKEN). Le reste vient de manual/*.json.
Règle : on n'écrase jamais une valeur existante par une erreur. En cas d'échec réseau,
l'ancienne valeur est conservée et l'erreur est listée dans le champ "errors".
"""
import json, os, sys, datetime, urllib.request, urllib.parse

FRED_KEY = os.environ.get("FRED_API_KEY", "")
INSEE_TOKEN = os.environ.get("INSEE_TOKEN", "")
TODAY = datetime.date.today().isoformat()
UA = {"User-Agent": "barometre-crise/1.0 (github pages, usage perso)"}

def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")

# ---------- FRED ----------
def fred(series, n=1, freq=None):
    """Renvoie [(date, valeur)] du plus récent au plus ancien, valeurs manquantes ignorées."""
    if not FRED_KEY:
        raise RuntimeError("FRED_API_KEY manquante")
    q = dict(series_id=series, api_key=FRED_KEY, file_type="json", sort_order="desc", limit=n + 12)
    if freq: q["frequency"] = freq
    js = json.loads(get("https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(q)))
    obs = [(o["date"], float(o["value"])) for o in js["observations"] if o["value"] not in (".", "")]
    return obs[:n]

def fred_last(series):
    d, v = fred(series, 1)[0]; return v, v, d

def fred_last2(series, scale=1.0):
    o = fred(series, 2); return o[0][1] * scale, o[1][1] * scale, o[0][0]

def fred_yoy(series):
    """Variation a/a en % d'une série mensuelle, + valeur a/a du mois précédent."""
    o = fred(series, 14)
    def yoy(k): return round((o[k][1] / o[k + 12][1] - 1) * 100, 1)
    return yoy(0), yoy(1), o[0][0][:7]

# ---------- BCE ----------
def ecb_ciss():
    # Indicateur composite de stress systémique, zone euro, quotidien (dataset CISS du Data Portal BCE)
    url = "https://data-api.ecb.europa.eu/service/data/CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX?lastNObservations=10&format=csvdata"
    rows = [l.split(",") for l in get(url).strip().splitlines()]
    head = rows[0]; it, iv = head.index("TIME_PERIOD"), head.index("OBS_VALUE")
    vals = [(r[it], float(r[iv])) for r in rows[1:] if r[iv]]
    return round(vals[-1][1], 3), round(vals[-2][1], 3), vals[-1][0]

# ---------- INSEE (optionnel) ----------
INSEE_IDBANK = {  # à vérifier sur insee.fr : fiche de la série > "Identifiant (idbank)"
    "climat": "001565530",   # climat des affaires, ensemble
    "menages": "000857180",  # confiance des ménages, indicateur synthétique
    "chomage": "001688527",  # taux de chômage BIT, France (hors Mayotte), trimestriel
}
def insee(idbank, n=6):
    if not INSEE_TOKEN:
        raise RuntimeError("INSEE_TOKEN manquant")
    url = f"https://api.insee.fr/series/BDM/V1/data/SERIES_BDM/{idbank}?lastNObservations={n}"
    xml = get(url, {"Authorization": "Bearer " + INSEE_TOKEN, "Accept": "application/xml"})
    import re
    obs = re.findall(r'TIME_PERIOD="([^"]+)"[^>]*OBS_VALUE="([^"]+)"', xml)
    return [(t, float(v)) for t, v in obs]  # ordre croissant

def insee_last(key):
    o = insee(INSEE_IDBANK[key]); return o[-1][1], o[-2][1], o[-1][0]

def insee_sahm():
    o = insee(INSEE_IDBANK["chomage"], 6)  # 6 trimestres
    cur, prev = o[-1][1], o[-2][1]
    return round(cur - min(v for _, v in o[-5:]), 1), round(prev - min(v for _, v in o[-6:-1]), 1), o[-1][0]

# ---------- plans de collecte ----------
US = {
    "yc":      lambda: fred_last2("T10Y3M"),
    "hy":      lambda: fred_last2("BAMLH0A0HYM2"),
    "nfci":    lambda: fred_last2("NFCI"),
    "sahm":    lambda: fred_last2("SAHMREALTIME"),
    "claims":  lambda: fred_last2("IC4WSA", 1 / 1000),
    "permits": lambda: fred_yoy("PERMIT"),
    "cass":    lambda: fred_yoy("FRGSHPUSM649NCIS"),
    "cu":      lambda: fred_yoy("PCOPPUSDM"),
}
FR = {
    "oatbund": lambda: (lambda fr, de: (round((fr[0][1] - de[0][1]) * 100), round((fr[1][1] - de[1][1]) * 100), fr[0][0][:7]))
                       (fred("IRLTLT01FRM156N", 2), fred("IRLTLT01DEM156N", 2)),
    "oat":     lambda: fred_last2("IRLTLT01FRM156N"),
    "hy":      lambda: fred_last2("BAMLHE00EHYIOAS"),
    "ciss":    ecb_ciss,
    "climat":  lambda: insee_last("climat"),
    "menages": lambda: insee_last("menages"),
    "sahm":    insee_sahm,
    "cu":      lambda: fred_yoy("PCOPPUSDM"),
}

def refresh(name, plan):
    path, mpath = f"data/{name}.json", f"manual/{name}.json"
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"values": {}}
    man = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {"values": {}}
    out = {"updated": TODAY, "context": man.get("context", old.get("context", [])), "values": dict(old["values"]), "errors": []}
    for k, fn in plan.items():
        if man["values"].get(k, {}).get("force"):
            continue
        try:
            v, p, d = fn()
            out["values"][k] = {"value": round(v, 3) if v is not None else None, "prev": round(p, 3) if p is not None else None,
                                "date": d, "source": "auto"}
        except Exception as e:
            out["errors"].append(f"{k}: {type(e).__name__} {e}")
    for k, m in man["values"].items():
        if k in plan and not m.get("force"):
            continue
        prev = out["values"].get(k, {}).get("value")
        out["values"][k] = {"value": m.get("value"), "prev": prev if prev != m.get("value") else out["values"].get(k, {}).get("prev"),
                            "date": m.get("date", ""), "source": "manual"}
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(name, "→", len(out["values"]), "valeurs,", len(out["errors"]), "erreurs")
    for e in out["errors"]: print("   ", e)

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    refresh("us", US); refresh("fr", FR)
