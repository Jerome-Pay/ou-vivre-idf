# Où vivre en IDF

Carte interactive des 1 285 communes d'Île-de-France (Paris découpé en arrondissements), notées sur 10 selon 8 critères (sécurité, enseignement, transports…), calculées à partir de données publiques plutôt que d'avis d'habitants.

**Ouvrir la carte :** double-cliquer sur `docs/index.html` (aucun serveur nécessaire).

- Survol d'une commune : détail des 8 notes
- Clic, recherche ou classement : fiche détaillée avec les indicateurs bruts et un lien vers les avis sur ville-ideale.fr
- « Colorer par » : affiche un seul critère
- « Pondérations » : règle l'importance de chaque critère dans la note globale
- `index.html#c=92071` ouvre directement une commune (code INSEE)

## Mettre à jour les données

```bash
pip install pandas numpy pyarrow
bash scripts/download.sh          # ≈ 220 Mo dans data/raw/
python scripts/build_data.py      # régénère docs/data.js
```

## Méthode

| Critère | Indicateur | Source |
|---|---|---|
| Sécurité | Faits de délinquance pour 1 000 hab. (moyenne 2023-2025, hors stupéfiants, escroqueries et violences intrafamiliales) | SSMSI |
| Enseignement | IPS moyen des écoles + note à l'écrit du brevet des collèges | Éducation nationale |
| Transports | Gares et stations accessibles, pondérées par mode (75 %) + distance à Châtelet (25 %) | IDFM |
| Santé | Équipements de santé accessibles, en nombre et par habitant | INSEE BPE 2025 |
| Commerces | Commerces accessibles | INSEE BPE 2025 |
| Environnement | Part de surface non artificialisée (espaces verts publics pour Paris) | OCS GE / Cerema, Paris Open Data |
| Sports et loisirs | Équipements sportifs et de loisirs, en nombre et par habitant | INSEE BPE 2025 |
| Culture | Cinémas, théâtres, musées, bibliothèques, conservatoires | INSEE BPE 2025 |

« Accessible » : somme des équipements pondérée par une décroissance gaussienne de la distance au centre de la commune (rayon de 1 à 3 km selon le critère).

Chaque indicateur est converti en note /10 de façon linéaire (log pour les indicateurs asymétriques), entre le 2e percentile (0) et le 98e percentile (10) des communes d'IDF. Sur la carte, le gris correspond à la médiane régionale du critère affiché.

**Limites :** la délinquance est rapportée aux résidents, ce qui pénalise les quartiers commerçants et touristiques. L'IPS mesure le profil social des familles, pas la qualité pédagogique. Pour les grandes communes rurales, le « centre » géométrique n'est pas toujours le bourg.

## Sources et licences

| Données | Producteur | Licence |
|---|---|---|
| Délinquance enregistrée (édition juillet 2026) | Ministère de l'Intérieur – SSMSI | Licence Ouverte 2.0 |
| Base permanente des équipements 2025 | INSEE | Licence Ouverte 2.0 |
| IPS écoles/collèges, valeur ajoutée des collèges | Ministère de l'Éducation nationale | Licence Ouverte 2.0 |
| Gares et stations | Île-de-France Mobilités | Licence Ouverte 2.0 |
| Artificialisation des sols (OCS GE) | Mon diagnostic artificialisation / Cerema | Licence Ouverte 2.0 |
| Espaces verts | Ville de Paris | ODbL |
| Contours des communes | IGN Admin Express, via geo.api.gouv.fr | Licence Ouverte 2.0 |
| Fond de carte (Plan IGN v2) | IGN – Géoplateforme | Licence Ouverte 2.0 |

Données téléchargées en octobre 2026. Projet personnel, sans lien avec ville-ideale.fr : aucune donnée de ce site n'est utilisée, la carte se contente de renvoyer vers ses pages.
