"""Construit docs/data.js : contours des communes d'Ile-de-France + notes /10 par critère.

Sources (toutes en open data, téléchargées dans data/raw/ par scripts/download.sh) :
  - Contours communes / arrondissements : geo.api.gouv.fr
  - Sécurité : SSMSI, base communale de la délinquance enregistrée (data.gouv.fr)
  - Commerces, santé, sports et loisirs, culture : INSEE, Base Permanente des Equipements 2025 (insee.fr)
  - Transports : IDFM, emplacement des gares et stations
  - Enseignement : Education nationale, IPS des écoles + résultats écrits au DNB par collège
  - Environnement : Cerema / Mon diagnostic artificialisation (OCS GE) + espaces verts de Paris

Chaque critère est d'abord mesuré par un indicateur brut, puis converti en note /10 par une
échelle linéaire (éventuellement logarithmique) bornée par les 2e et 98e percentiles des communes d'IDF.
La note globale est la moyenne des 8 notes.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data.js"

DEPS_IDF = ["75", "77", "78", "91", "92", "93", "94", "95"]

# Projection locale en km (équirectangulaire centrée sur Paris, suffisant à l'échelle de l'IDF)
LON0, LAT0 = 2.3488, 48.8534  # Châtelet
KX = 111.32 * math.cos(math.radians(LAT0))
KY = 110.57


def to_km(lon, lat):
    return (np.asarray(lon) - LON0) * KX, (np.asarray(lat) - LAT0) * KY


# --------------------------------------------------------------------------- géométries

def ring_centroid(ring):
    """Centroïde et aire (signée) d'un anneau, en km."""
    x, y = to_km([p[0] for p in ring], [p[1] for p in ring])
    cross = x[:-1] * y[1:] - x[1:] * y[:-1]
    a = cross.sum() / 2
    if abs(a) < 1e-12:
        return x.mean(), y.mean(), 0.0
    cx = ((x[:-1] + x[1:]) * cross).sum() / (6 * a)
    cy = ((y[:-1] + y[1:]) * cross).sum() / (6 * a)
    return cx, cy, a


def geom_centroid_area(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    sx = sy = sa = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            cx, cy, a = ring_centroid(ring)
            a = abs(a) if i == 0 else -abs(a)  # trous soustraits
            sx += cx * a
            sy += cy * a
            sa += a
    return sx / sa, sy / sa, sa


def simplify_geom(geom, ndigits=4):
    """Arrondit les coordonnées (~10 m) et retire les points consécutifs dupliqués."""
    def ring(r):
        out = []
        for lon, lat in r:
            p = [round(lon, ndigits), round(lat, ndigits)]
            if not out or out[-1] != p:
                out.append(p)
        if out[0] != out[-1]:
            out.append(out[0])
        return out if len(out) >= 4 else None

    def poly(p):
        rings = [ring(r) for r in p]
        return [r for r in rings if r] if rings[0] else None

    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": poly(geom["coordinates"])}
    polys = [q for q in (poly(p) for p in geom["coordinates"]) if q]
    return {"type": "MultiPolygon", "coordinates": polys}


def load_units():
    communes = json.loads((RAW / "communes_idf.geojson").read_text(encoding="utf8"))["features"]
    arrs = json.loads((RAW / "arrondissements_paris.geojson").read_text(encoding="utf8"))["features"]
    feats = [f for f in communes if f["properties"]["code"] != "75056"] + arrs
    rows = []
    for f in feats:
        p = f["properties"]
        cx, cy, area = geom_centroid_area(f["geometry"])
        rows.append({
            "code": p["code"], "nom": p["nom"], "dep": p["codeDepartement"],
            "pop": p.get("population") or 0, "x": cx, "y": cy, "area_km2": area,
        })
    units = pd.DataFrame(rows).set_index("code")
    geoms = {f["properties"]["code"]: simplify_geom(f["geometry"]) for f in feats}
    return units, geoms


# --------------------------------------------------------------------------- outils

def scale_note(s, higher_is_better=True, log=False):
    """Indicateur brut -> note /10, linéaire entre le 2e et le 98e percentile des communes d'IDF.

    log=True pour les indicateurs très asymétriques (taux de délinquance, nombre d'équipements accessibles).
    """
    t = np.log1p(s) if log else s
    lo, hi = t.quantile(0.02), t.quantile(0.98)
    x = ((t - lo) / (hi - lo)).clip(0, 1)
    return ((x if higher_is_better else 1 - x) * 10).round(1)


def accessibility(units, px, py, weights=None, sigma_km=1.0, chunk=200):
    """Somme des équipements pondérée par une décroissance gaussienne de la distance au centroïde."""
    px, py = np.asarray(px, float), np.asarray(py, float)
    w = np.ones_like(px) if weights is None else np.asarray(weights, float)
    ux, uy = units["x"].to_numpy(), units["y"].to_numpy()
    out = np.empty(len(units))
    for i in range(0, len(units), chunk):
        dx = ux[i:i + chunk, None] - px[None, :]
        dy = uy[i:i + chunk, None] - py[None, :]
        out[i:i + chunk] = (np.exp(-(dx * dx + dy * dy) / (2 * sigma_km ** 2)) * w).sum(axis=1)
    return pd.Series(out, index=units.index)


def fill_from_neighbours(units, s, k=3):
    """Communes sans valeur (pas d'école, de collège...) : moyenne des k communes voisines renseignées."""
    known = s.dropna()
    kx, ky = units.loc[known.index, "x"].to_numpy(), units.loc[known.index, "y"].to_numpy()
    out = s.copy()
    for code in s.index[s.isna()]:
        d = np.hypot(kx - units.at[code, "x"], ky - units.at[code, "y"])
        out[code] = known.to_numpy()[np.argsort(d)[:k]].mean()
    return out


# --------------------------------------------------------------------------- critères

CRIMES = [
    "Violences physiques hors cadre familial",
    "Violences sexuelles",
    "Vols avec armes",
    "Vols violents sans arme",
    "Vols sans violence contre des personnes",
    "Cambriolages de logement",
    "Vols de véhicule",
    "Vols dans les véhicules",
    "Vols d'accessoires sur véhicules",
    "Destructions et dégradations volontaires",
]


def securite(units):
    d = pd.read_parquet(RAW / "delinquance.parquet")
    d = d[d["CODGEO_2026"].isin(units.index) & d["annee"].between(2023, 2025)
          & d["indicateur"].astype(str).isin(CRIMES)]
    # Petites communes : chiffres non diffusés (secret statistique) -> on prend l'estimation fournie
    taux = d["taux_pour_mille"].where(d["est_diffuse"] == "diff", d["complement_info_taux"])
    d = d.assign(taux=taux)
    par_an = d.groupby(["CODGEO_2026", "annee"])["taux"].sum()
    s = par_an.groupby(level=0).mean().reindex(units.index)
    return s, scale_note(s, higher_is_better=False, log=True)


BPE_CATS = {
    # critère : (filtre sur DOM/SDOM, sigma en km, part de la note venant de l'offre par habitant)
    "commerces": (lambda b: b["DOM"] == "B", 1.0, 0.0),
    "sante": (lambda b: b["SDOM"].isin(["D1", "D2", "D3"]), 2.0, 0.5),
    "sports_loisirs": (lambda b: b["SDOM"].isin(["F1", "F2"]), 2.0, 0.5),
    "culture": (lambda b: b["SDOM"] == "F3", 3.0, 0.0),
}


def equipements(units):
    b = pd.read_parquet(RAW / "bpe25.parquet", columns=["DOM", "SDOM", "LONGITUDE", "LATITUDE"],
                        filters=[("REG", "=", "11")]).dropna(subset=["LONGITUDE", "LATITUDE"])
    res = {}
    for crit, (filt, sigma, part_par_hab) in BPE_CATS.items():
        sub = b[filt(b)]
        px, py = to_km(sub["LONGITUDE"], sub["LATITUDE"])
        s = accessibility(units, px, py, sigma_km=sigma)
        note = scale_note(s, log=True)
        if part_par_hab:
            # offre rapportée à la population vivant dans le même rayon (à la manière de l'APL de la DREES),
            # pour ne pas mesurer seulement la densité urbaine
            demande = accessibility(units, units["x"], units["y"], weights=units["pop"], sigma_km=sigma)
            ratio = s / demande.clip(lower=1) * 1000
            note = ((1 - part_par_hab) * note + part_par_hab * scale_note(ratio, log=True)).round(1)
        res[crit] = (s, note)
    return res


MODE_WEIGHT = {"METRO": 1.0, "RER": 1.5, "TRAIN": 1.2, "TRAMWAY": 0.6, "VAL": 0.6, "CABLE": 0.4}


def transports(units):
    g = pd.read_csv(RAW / "gares.csv", sep=";")
    lat, lon = g["geo_point_2d"].str.split(",", expand=True).astype(float).T.values
    px, py = to_km(lon, lat)
    w = g["mode"].str.upper().map(MODE_WEIGHT).fillna(0.6)
    # une ligne par (gare, ligne) : un pôle multi-lignes compte plus qu'une gare simple
    acces = accessibility(units, px, py, weights=w, sigma_km=1.0)
    dist_paris = np.hypot(units["x"], units["y"])
    note = (0.75 * scale_note(acces, log=True) + 0.25 * scale_note(dist_paris, higher_is_better=False)).round(1)
    return acces, dist_paris, note


def enseignement(units):
    e = pd.read_csv(RAW / "ips_ecoles.csv", sep=";", dtype={"code_insee_de_la_commune": str})
    e = e[e["rentree_scolaire"] == e["rentree_scolaire"].max()].copy()
    e["ips"] = pd.to_numeric(e["ips"], errors="coerce")  # colonne texte ("NS" pour non significatif)
    ips =e.groupby("code_insee_de_la_commune")["ips"].mean().reindex(units.index)

    c = pd.read_csv(RAW / "ips_colleges.csv", sep=";", dtype={"code_insee_de_la_commune": str})
    uai_commune = c.drop_duplicates("uai").set_index("uai")["code_insee_de_la_commune"]
    va = pd.read_csv(RAW / "va_colleges.csv", sep=";", dtype=str)
    va = va[va["session"] == va["session"].max()].copy()
    va["code"] = va["uai"].map(uai_commune)
    # collèges parisiens absents de la table IPS : "PARIS 12" -> 75112
    paris = va["code"].isna() & va["commune"].str.match(r"PARIS \d+$", na=False)
    va.loc[paris, "code"] = "751" + va.loc[paris, "commune"].str.extract(r"(\d+)$")[0].str.zfill(2)
    va["note_ecrit"] = pd.to_numeric(va["note_a_l_ecrit_g"], errors="coerce")
    dnb = va.dropna(subset=["code", "note_ecrit"]).groupby("code")["note_ecrit"].mean().reindex(units.index)

    ips_f, dnb_f = fill_from_neighbours(units, ips), fill_from_neighbours(units, dnb)
    note = (0.5 * scale_note(ips_f) + 0.5 * scale_note(dnb_f)).round(1)
    return ips_f, dnb_f, note


BOIS_PARIS_M2 = {"75116": 8.46e6, "75112": 9.95e6}  # Bois de Boulogne, Bois de Vincennes


def environnement(units):
    a = pd.read_csv(RAW / "artif_commune.csv", dtype={"commune_code": str})
    a["code"] = a["commune_code"].str.zfill(5)
    nat = (100 - a.set_index("code")["pourcent_artif_2"]).reindex(units.index)

    # Paris n'est pas découpé par arrondissement : part d'espaces verts publics à la place
    ev = json.loads((RAW / "paris_espaces_verts.json").read_text(encoding="utf8"))["results"]
    for r in ev:
        cp = r["cp"]
        if not cp or not cp.startswith("750"):
            continue
        code = "751" + cp[-2:]
        if code in units.index:
            surf = r["surface_m2"] + BOIS_PARIS_M2.get(code, 0)
            nat[code] = 100 * surf / 1e6 / units.at[code, "area_km2"]
    return nat, scale_note(nat)


# --------------------------------------------------------------------------- assemblage

CRITERES = ["securite", "enseignement", "transports", "sante", "commerces",
            "environnement", "sports_loisirs", "culture"]


def main():
    units, geoms = load_units()
    print(f"{len(units)} communes/arrondissements")

    raw, notes = {}, {}
    raw["crimes_pour_mille"], notes["securite"] = securite(units)
    for crit, (s, n) in equipements(units).items():
        raw[f"acces_{crit}"], notes[crit] = s, n
    raw["acces_gares"], raw["dist_paris_km"], notes["transports"] = transports(units)
    raw["ips_ecoles"], raw["note_ecrit_dnb"], notes["enseignement"] = enseignement(units)
    raw["pct_non_artificialise"], notes["environnement"] = environnement(units)

    notes = pd.DataFrame(notes)[CRITERES]
    missing = notes.isna().sum()
    if missing.any():
        print("Valeurs manquantes (remplies par la médiane 5.0) :\n", missing[missing > 0])
    notes = notes.fillna(5.0)
    notes["globale"] = notes[CRITERES].mean(axis=1).round(1)
    raw = pd.DataFrame(raw)

    features = []
    for code, u in units.iterrows():
        features.append({
            "type": "Feature",
            "geometry": geoms[code],
            "properties": {
                "code": code, "nom": u["nom"], "dep": u["dep"], "pop": int(u["pop"]),
                "notes": {k: float(v) for k, v in notes.loc[code].items()},
                "brut": {
                    "crimes_pour_mille": round(float(raw.at[code, "crimes_pour_mille"]), 1)
                    if pd.notna(raw.at[code, "crimes_pour_mille"]) else None,
                    "ips_ecoles": round(float(raw.at[code, "ips_ecoles"]), 1),
                    "note_ecrit_dnb": round(float(raw.at[code, "note_ecrit_dnb"]), 1),
                    "pct_non_artificialise": round(float(raw.at[code, "pct_non_artificialise"]), 1)
                    if pd.notna(raw.at[code, "pct_non_artificialise"]) else None,
                    "dist_paris_km": round(float(raw.at[code, "dist_paris_km"]), 1),
                },
            },
        })
    fc = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.IDF_DATA = " + json.dumps(fc, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf8")
    print(f"Ecrit {OUT} ({OUT.stat().st_size / 1e6:.1f} Mo)")

    summary = notes.join(units[["nom"]]).sort_values("globale", ascending=False)
    print("\nTop 10 :\n", summary.head(10)[["nom", "globale"] + CRITERES].to_string())
    print("\nFlop 5 :\n", summary.tail(5)[["nom", "globale"]].to_string())
    print("\nCorrélations entre critères :\n", notes[CRITERES].corr().round(2).to_string())


if __name__ == "__main__":
    main()
