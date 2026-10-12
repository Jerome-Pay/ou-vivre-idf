#!/usr/bin/env bash
# Télécharge les données open data brutes dans data/raw/ (≈ 220 Mo, surtout la BPE).
# Les URL static.data.gouv.fr changent à chaque nouveau millésime : vérifier sur la page du jeu de données.
set -euo pipefail
mkdir -p "$(dirname "$0")/../data/raw"
cd "$(dirname "$0")/../data/raw"

GEO="https://geo.api.gouv.fr/communes"
EDU="https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets"
ACAD='academie in ("PARIS","CRETEIL","VERSAILLES")'

# Contours
curl -sSL -o communes_idf.geojson "$GEO?codeRegion=11&format=geojson&geometry=contour&fields=nom,code,population,codeDepartement"
curl -sSL -o arrondissements_paris.geojson "$GEO?codeDepartement=75&type=arrondissement-municipal&format=geojson&geometry=contour&fields=nom,code,population,codeDepartement"

# Sécurité : SSMSI, base communale de la délinquance
# https://www.data.gouv.fr/fr/datasets/bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales/
curl -sSL -o delinquance.parquet "https://static.data.gouv.fr/resources/bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales/20260709-120017/donnee-comm-data.gouv-parquet-2025-geographie2026-produit-le2026-06-25.parquet"

# Equipements : INSEE, Base Permanente des Equipements 2025 (fichier officiel insee.fr, Licence Ouverte)
curl -sSL -o bpe25.parquet "https://www.insee.fr/fr/statistiques/fichier/8217525/BPE25.parquet"

# Transports : IDFM, gares et stations
curl -sSL -o gares.csv "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/emplacement-des-gares-idf/exports/csv?delimiter=%3B"

# Enseignement (codes région académiques : IDF = 10)
curl -sSL -G -o ips_ecoles.csv "$EDU/fr-en-ips-ecoles-ap2022/exports/csv" --data-urlencode "delimiter=;" --data-urlencode 'where=code_region="10"'
curl -sSL -G -o ips_colleges.csv "$EDU/fr-en-ips-colleges-ap2022/exports/csv" --data-urlencode "delimiter=;" --data-urlencode "where=$ACAD"
curl -sSL -G -o va_colleges.csv "$EDU/fr-en-indicateurs-valeur-ajoutee-colleges/exports/csv" --data-urlencode "delimiter=;" --data-urlencode "where=$ACAD"

# Environnement : artificialisation (OCS GE) + espaces verts de Paris
curl -sSL -o artif_commune.csv "https://static.data.gouv.fr/resources/artificialisation-des-collectivites-de-france/20260129-121544/artif-commune.csv"
curl -sSL -G -o paris_espaces_verts.json "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/espaces_verts/records" \
  --data-urlencode "select=adresse_codepostal as cp,sum(surface_totale_reelle) as surface_m2" \
  --data-urlencode 'where=categorie != "Cimetière" and categorie != "Bois"' \
  --data-urlencode "group_by=adresse_codepostal" --data-urlencode "limit=100"

ls -la
