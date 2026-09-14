#!/usr/bin/env python3
"""Rafraîchit data/us.json et data/fr.json.

Sources automatiques : FRED (clé gratuite, variable FRED_API_KEY), BCE et BIS (sans clé).
Les séries INSEE passent par leur republication OCDE sur FRED. Le reste vient de manual/*.json.
Règle : on n'écrase jamais une valeur existante par une erreur. En cas d'échec réseau,
l'ancienne valeur est conservée et l'erreur est listée dans le champ "errors".
"""
import json, os, re, sys, datetime, urllib.request, urllib.parse

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
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

# ---------- BIS : écart crédit/PIB ----------
def bis_gap(country):
    """Credit-to-GDP gap BIS (API SDMX v2, puis v1 en secours). Clé : Q.<pays>.P.A.C"""
    urls = [f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q.{country}.P.A.C?lastNObservations=2&format=csv",
            f"https://stats.bis.org/api/v1/data/WS_CREDIT_GAP/Q.{country}.P.A.C/all?lastNObservations=2&format=csv"]
    err = None
    for url in urls:
        try:
            rows = [l.split(",") for l in get(url).strip().splitlines()]
            head = rows[0]; it, iv = head.index("TIME_PERIOD"), head.index("OBS_VALUE")
            vals = [(r[it], float(r[iv])) for r in rows[1:] if len(r) > iv and r[iv]]
            vals.sort()
            return round(vals[-1][1], 1), round(vals[-2][1], 1), vals[-1][0]
        except Exception as e:
            err = e
    raise err

# ---------- séries OCDE via FRED (identifiants candidats, le premier qui répond gagne) ----------
def fred_try(candidates, fn):
    err = None
    for sid in candidates:
        try: return fn(sid)
        except Exception as e: err = e
    raise err

def sahm_monthly(series):
    """Règle de Sahm sur un taux de chômage mensuel : moy. 3 mois − plus bas des 12 mois précédents (et idem un mois avant)."""
    o = fred(series, 16); v = [x[1] for x in o]  # du plus récent au plus ancien
    ma = lambda k: sum(v[k:k+3]) / 3
    cur = ma(0) - min(ma(k) for k in range(1, 13))
    prev = ma(1) - min(ma(k) for k in range(2, 14))
    return round(cur, 2), round(prev, 2), o[0][0][:7]

# ---------- CAPE Shiller (page multpl.com) ----------
def cape():
    html = get("https://www.multpl.com/shiller-pe")
    m = re.search(r"Current Shiller PE Ratio[^0-9]{0,80}?(\d{1,3}\.\d{1,2})", html, re.S)
    if not m: raise RuntimeError("valeur introuvable sur la page")
    return float(m.group(1)), None, TODAY

# ---------- bandeau de contexte ----------
def fr_fmt(v, dec=1, unit=""):
    return (f"{v:,.{dec}f}".replace(",", " ").replace(".", ",") + unit)
def context_us():
    out = []
    for label, sid, dec, unit in [("Taux US 10 ans", "DGS10", 2, " %"), ("Chômage", "UNRATE", 1, " %"),
                                  ("S&P 500", "SP500", 0, ""), ("VIX", "VIXCLS", 1, "")]:
        try: out.append([label, fr_fmt(fred(sid, 1)[0][1], dec, unit)])
        except Exception: pass
    return out
def context_fr():
    out = []
    for label, sids, dec, unit in [("OAT 10 ans", ["IRLTLT01FRM156N"], 2, " %"), ("Chômage", ["LRHUTTTTFRM156S", "LRUNTTTTFRM156S"], 1, " %"),
                                   ("Inflation (a/a)", ["CPALTT01FRM659N", "FRACPIALLMINMEI"], 1, " %")]:
        try: out.append([label, fr_fmt(fred_try(sids, lambda x: fred(x, 1)[0][1]), dec, unit)])
        except Exception: pass
    return out

# ---------- plans de collecte ----------
US = {
    "yc":      lambda: fred_last2("T10Y3M"),
    "hy":      lambda: fred_last2("BAMLH0A0HYM2"),
    "nfci":    lambda: fred_last2("NFCI"),
    "sahm":    lambda: fred_last2("SAHMREALTIME"),
    "claims":  lambda: fred_last2("IC4WSA", 1 / 1000),
    "cfnai":   lambda: fred_last2("CFNAIMA3"),
    "cli":     lambda: fred_try(["USALOLITONOSTSAM", "USALOLITOAASTSAM"], fred_last2),
    "permits": lambda: fred_yoy("PERMIT"),
    "cass":    lambda: fred_yoy("FRGSHPUSM649NCIS"),
    "cu":      lambda: fred_yoy("PCOPPUSDM"),
    "gap":     lambda: bis_gap("US"),
    "cape":    cape,
}
FR = {
    "oatbund": lambda: (lambda fr, de: (round((fr[0][1] - de[0][1]) * 100), round((fr[1][1] - de[1][1]) * 100), fr[0][0][:7]))
                       (fred("IRLTLT01FRM156N", 2), fred("IRLTLT01DEM156N", 2)),
    "oat":     lambda: fred_last2("IRLTLT01FRM156N"),
    "hy":      lambda: fred_last2("BAMLHE00EHYIOAS"),
    "ciss":    ecb_ciss,
    "climat":  lambda: fred_try(["BSCICP03FRM665S", "BSCICP02FRM460S"], fred_last2),
    "menages": lambda: fred_try(["CSCICP03FRM665S", "CSCICP02FRM460S"], fred_last2),
    "sahm":    lambda: fred_try(["LRHUTTTTFRM156S", "LRUNTTTTFRM156S"], sahm_monthly),
    "ipi":     lambda: fred_try(["FRAPROINDMISMEI", "FRAPROINDQISMEI"], fred_yoy),
    "cu":      lambda: fred_yoy("PCOPPUSDM"),
    "gap":     lambda: bis_gap("FR"),
}

CONTEXT = {"us": context_us, "fr": context_fr}

def refresh(name, plan):
    path, mpath = f"data/{name}.json", f"manual/{name}.json"
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"values": {}}
    man = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {"values": {}}
    ctx = CONTEXT[name]() or man.get("context") or old.get("context", [])
    out = {"updated": TODAY, "context": ctx, "values": dict(old["values"]), "errors": []}
    for k, fn in plan.items():
        if man["values"].get(k, {}).get("force"):
            continue
        try:
            v, p, d = fn()
            if p is None and out["values"].get(k, {}).get("value") not in (None, v): p = out["values"][k]["value"]
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
