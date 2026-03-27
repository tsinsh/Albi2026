"""
generate_carreaux.py
À lancer UNE SEULE FOIS pour générer le fichier albi_carreaux_200m.geojson
utilisé par la couche "Carreaux 200m" de l'application.

Il construit des polygones carrés 200m×200m à partir des ID Filosofi,
puis filtre ceux qui intersectent la commune d'Albi.

Résultat : albi_carreaux_200m.geojson (~810 carreaux, quelques Mo)
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import box
import re

print("1. Lecture du fichier Filosofi (peut prendre 30s)...")
colonnes = [
    'Idcar_200m', 'Men', 'Men_pauv', 'Log_soc', 'Men_prop',
    'Men_fmp', 'Ind', 'Ind_18_24', 'Ind_25_39'
]
df = pd.read_csv(
    "Filosofi2017_carreaux_200m_met.csv",
    usecols=colonnes, sep=None, engine='python'
)

print("2. Construction des polygones carrés 200m×200m (EPSG:3035)...")
def parse_idcar(idcar):
    m = re.search(r'N(\d+)E(\d+)', str(idcar))
    if m:
        y0 = float(m.group(1))   # coin bas
        x0 = float(m.group(2))   # coin gauche
        return box(x0, y0, x0 + 200, y0 + 200)
    return None

df['geometry'] = df['Idcar_200m'].apply(parse_idcar)
df = df.dropna(subset=['geometry'])

gdf = gpd.GeoDataFrame(df, geometry='geometry', crs='EPSG:3035')
gdf = gdf.to_crs('EPSG:4326')

print("3. Chargement des contours d'Albi...")
gdf_albi = gpd.read_file("contours-france-entiere-latest-v2.geojson")
gdf_albi = gdf_albi[gdf_albi['codeCommune'] == '81004'].to_crs('EPSG:4326')
albi_union = gdf_albi.geometry.union_all()

print("4. Filtrage sur Albi...")
gdf_albi_car = gdf[gdf.geometry.intersects(albi_union)].copy()
print(f"   → {len(gdf_albi_car)} carreaux retenus")

# Calculs des indicateurs
gdf_albi_car['Taux_Pauvrete']             = (gdf_albi_car['Men_pauv'] / gdf_albi_car['Men']) * 100
gdf_albi_car['Taux_Logement_Social']      = (gdf_albi_car['Log_soc']  / gdf_albi_car['Men']) * 100
gdf_albi_car['Taux_Proprietaires']        = (gdf_albi_car['Men_prop'] / gdf_albi_car['Men']) * 100
gdf_albi_car['Taux_Familles_Mono']        = (gdf_albi_car['Men_fmp']  / gdf_albi_car['Men']) * 100
gdf_albi_car['Taux_Jeunes_18_39']         = ((gdf_albi_car['Ind_18_24'] + gdf_albi_car['Ind_25_39']) / gdf_albi_car['Ind']) * 100
gdf_albi_car['Taux_Locataires_Prives']    = ((gdf_albi_car['Men'] - gdf_albi_car['Men_prop'] - gdf_albi_car['Log_soc']) / gdf_albi_car['Men']) * 100

cols_export = [
    'Idcar_200m', 'Men', 'Ind',
    'Taux_Pauvrete', 'Taux_Logement_Social', 'Taux_Proprietaires',
    'Taux_Familles_Mono', 'Taux_Jeunes_18_39', 'Taux_Locataires_Prives',
    'geometry'
]
gdf_albi_car[cols_export].to_file("albi_carreaux_200m.geojson", driver="GeoJSON")
print("✅ Fichier 'albi_carreaux_200m.geojson' généré.")
print("   → Lance maintenant python app.py pour accéder à la couche Carreaux.")
