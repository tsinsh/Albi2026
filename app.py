"""
app.py — Boussole Électorale & Matérialiste · Albi 2026
Lancez avec : python app.py  →  http://127.0.0.1:8050

Nouveautés v3 :
  - Onglet "Carreaux 200m" : visualisation Filosofi à la maille fine
  - Onglet "À propos" : guide complet + sources millésimées avec liens
  - Recherche par adresse (API BAN) avec affichage des données du bureau
  - Prêt pour déploiement GitHub + Render (voir README_deploiement.md)
"""

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import geopandas as gpd
import requests
import os
import re
import json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("🔄 Chargement de la Boussole Matérialiste...")

# ─────────────────────────────────────────────────────────────────────────────
# 1. FICHIERS
# ─────────────────────────────────────────────────────────────────────────────
file_excel    = "resultats_albi_2026_final.xlsx"
file_geo      = "albi_contours.geojson"
file_socio    = "albi_sociologie_bureau_FINAL.xlsx"
file_pres     = "albi_presidentielle_2022.xlsx"
file_legis    = "albi_legislatives_2024.xlsx"
file_carreaux = "albi_carreaux_200m.geojson"   # Généré par generate_carreaux.py

if not os.path.exists(file_excel) or not os.path.exists(file_geo):
    raise FileNotFoundError("❌ Fichiers de base introuvables.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. NETTOYAGE DES IDS
# ─────────────────────────────────────────────────────────────────────────────
def clean_id(series):
    return (
        series.astype(str).str.strip()
        .str.replace(r"\D", "", regex=True)
        .replace("", None)
        .astype(float).astype("Int64")
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. CHARGEMENT ET FUSIONS
# ─────────────────────────────────────────────────────────────────────────────
df  = pd.read_excel(file_excel)
gdf = gpd.read_file(file_geo)

gdf_albi = gdf[gdf['codeCommune'] == '81004'].copy()
gdf_albi['id_jointure'] = clean_id(gdf_albi['numeroBureauVote'])
df['id_jointure']       = clean_id(df['id_bv'])

albi_map = gdf_albi.merge(df, on='id_jointure')
print(f"   → {len(albi_map)} bureaux chargés")

if os.path.exists(file_socio):
    df_socio = pd.read_excel(file_socio)
    df_socio['id_jointure'] = clean_id(df_socio['id_bv'])
    df_socio = df_socio.drop(columns=['id_bv'], errors='ignore')
    albi_map = albi_map.merge(df_socio, on='id_jointure', how='left')

# ─────────────────────────────────────────────────────────────────────────────
# 4. CALCULS POLITIQUES
# ─────────────────────────────────────────────────────────────────────────────
for cand, col in [('Guiraud','guiraud'),('Ferrand','ferrand'),
                  ('Suarez','suarez'),('Cabrolier','cabrolier'),('At','at')]:
    if f't1_voix_{col}' in albi_map.columns:
        albi_map[f'Part_{cand}_T1'] = (albi_map[f't1_voix_{col}'] / albi_map['t1_exprimes']) * 100
    if f't2_voix_{col}' in albi_map.columns:
        albi_map[f'Part_{cand}_T2'] = (albi_map[f't2_voix_{col}'] / albi_map['t2_exprimes']) * 100

albi_map['Base_Gauche_T1'] = albi_map.get('t1_voix_ferrand', 0) + albi_map.get('t1_voix_suarez', 0)
albi_map['Taux_Rassemblement_Gauche'] = albi_map.apply(
    lambda r: (r['t2_voix_ferrand'] / r['Base_Gauche_T1']) * 100
    if r.get('Base_Gauche_T1', 0) > 0 else None, axis=1
)
albi_map['Rassemblement_Qualitatif'] = albi_map['Taux_Rassemblement_Gauche'].apply(
    lambda v: "Report élargi (>100%)" if v and v > 100 else
              "Report parfait"        if v and 95 <= v <= 100 else
              "Déperdition modérée"   if v and 80 <= v < 95 else
              "Déperdition forte"     if v and v < 80 else "—"
)
albi_map['Nombre_Abstentionnistes'] = albi_map['t2_inscrits'] - albi_map['t2_votants']

if os.path.exists(file_pres):
    df_pres = pd.read_excel(file_pres)
    df_pres['id_jointure'] = clean_id(df_pres['id_bv'])
    df_pres = df_pres.drop(columns=['id_bv'], errors='ignore')
    albi_map = albi_map.merge(df_pres, on='id_jointure', how='left')
    albi_map['Ecart_JLM_Local'] = albi_map['Voix_JLM_2022'] - albi_map['t2_voix_ferrand']
    if 't1_inscrits' in albi_map.columns:
        albi_map['Taux_JLM_Inscrits']    = albi_map['Voix_JLM_2022']     / albi_map['t1_inscrits'] * 100
        albi_map['Taux_Ferrand_Inscrits']= albi_map['t2_voix_ferrand']   / albi_map['t2_inscrits'] * 100
        albi_map['Ecart_JLM_Norm']       = albi_map['Taux_JLM_Inscrits'] - albi_map['Taux_Ferrand_Inscrits']

if os.path.exists(file_legis):
    df_legis = pd.read_excel(file_legis)
    df_legis['id_jointure'] = clean_id(df_legis['id_bv'])
    df_legis = df_legis.drop(columns=['id_bv'], errors='ignore')
    albi_map = albi_map.merge(df_legis, on='id_jointure', how='left')
    albi_map['Ecart_NFP_Local'] = albi_map['Voix_NFP_2024'] - albi_map['t2_voix_ferrand']
    if 'Taux_Ferrand_Inscrits' in albi_map.columns:
        albi_map['Taux_NFP_Inscrits'] = albi_map['Voix_NFP_2024'] / albi_map['t2_inscrits'] * 100
        albi_map['Ecart_NFP_Norm']    = albi_map['Taux_NFP_Inscrits'] - albi_map['Taux_Ferrand_Inscrits']

HAS_SPLIT_CSP = ('Taux_Cadres_Sup' in albi_map.columns and
                 'Taux_Independants' in albi_map.columns)

albi_map = albi_map.set_index('id_jointure')


# ─────────────────────────────────────────────────────────────────────────────
# 5. CARREAUX 200m (optionnel)
# ─────────────────────────────────────────────────────────────────────────────
gdf_carreaux = None
if os.path.exists(file_carreaux):
    gdf_carreaux = gpd.read_file(file_carreaux)
    print(f"   → {len(gdf_carreaux)} carreaux 200m chargés")
else:
    print("   ⚠ albi_carreaux_200m.geojson absent — lance generate_carreaux.py")


# ─────────────────────────────────────────────────────────────────────────────
# 6. CONSTRUCTION DES OPTIONS DROPDOWN
# ─────────────────────────────────────────────────────────────────────────────
def opt(label, value):
    return {'label': label, 'value': value}

options_dropdown = []
if 'Taux_Ouvriers_Employes' in albi_map.columns:
    options_dropdown.append(opt('⚙️ Taux Ouvriers & Employés (%)', 'Taux_Ouvriers_Employes'))
if HAS_SPLIT_CSP:
    options_dropdown += [
        opt('🎓 Taux Cadres supérieurs (%)', 'Taux_Cadres_Sup'),
        opt('🏪 Taux Artisans / Commerçants / Indépendants (%)', 'Taux_Independants'),
    ]
elif 'Taux_Cadres_Bourgeoisie' in albi_map.columns:
    options_dropdown.append(opt("💼 Taux Cadres & Chefs d'entreprise (agrégé) (%)", 'Taux_Cadres_Bourgeoisie'))

options_dropdown.append(opt("🚪 Nombre d'abstentionnistes (Volume)", 'Nombre_Abstentionnistes'))

if 'Ecart_JLM_Local' in albi_map.columns:
    options_dropdown.append(opt('🔥 Gisement JLM 2022 (Volume brut)', 'Ecart_JLM_Local'))
if 'Ecart_NFP_Local' in albi_map.columns:
    options_dropdown.append(opt('🔥 Gisement NFP 2024 (Volume brut)', 'Ecart_NFP_Local'))
if 'Ecart_JLM_Norm' in albi_map.columns:
    options_dropdown.append(opt('📐 Gisement JLM 2022 (normalisé % inscrits — recommandé)', 'Ecart_JLM_Norm'))
if 'Ecart_NFP_Norm' in albi_map.columns:
    options_dropdown.append(opt('📐 Gisement NFP 2024 (normalisé % inscrits — recommandé)', 'Ecart_NFP_Norm'))

for col, label in [
    ('Taux_Jeunes_18_39',          '👥 Taux de jeunes (18-39 ans) (%)'),
    ('Taux_Familles_Monoparentales','👥 Taux de familles monoparentales (%)'),
    ('Taux_Locataires_Prives',      '👥 Taux de locataires du parc privé (%)'),
]:
    if col in albi_map.columns:
        options_dropdown.append(opt(label, col))

options_dropdown += [
    opt('1er Tour - Ferrand-Lefranc (%)',  'Part_Ferrand_T1'),
    opt('1er Tour - Suarez (PS) (%)',       'Part_Suarez_T1'),
    opt('1er Tour - Guiraud-Chaumeil (%)',  'Part_Guiraud_T1'),
    opt('1er Tour - Cabrolier (%)',          'Part_Cabrolier_T1'),
    opt('1er Tour - At (%)',                 'Part_At_T1'),
    opt('🚨 Taux de Rassemblement Gauche au T2 (%)', 'Taux_Rassemblement_Gauche'),
    opt('2nd Tour - Ferrand-Lefranc (%)',   'Part_Ferrand_T2'),
    opt('2nd Tour - Guiraud-Chaumeil (%)',  'Part_Guiraud_T2'),
    opt('2nd Tour - Cabrolier (%)',          'Part_Cabrolier_T2'),
    opt('2nd Tour - At (%)',                 'Part_At_T2'),
]

default_value = ('Taux_Ouvriers_Employes' if 'Taux_Ouvriers_Employes' in albi_map.columns
                 else options_dropdown[0]['value'])

OPTIONS_CARREAUX = [
    opt('🔴 Taux de pauvreté (%)',            'Taux_Pauvrete'),
    opt('🏠 Taux logement social (%)',         'Taux_Logement_Social'),
    opt('🔑 Taux propriétaires (%)',           'Taux_Proprietaires'),
    opt('👨‍👧 Taux familles monoparentales (%)', 'Taux_Familles_Mono'),
    opt('👥 Taux jeunes 18-39 ans (%)',         'Taux_Jeunes_18_39'),
    opt('📋 Taux locataires privés (%)',        'Taux_Locataires_Prives'),
]


# ─────────────────────────────────────────────────────────────────────────────
# 7. CONTENU "À PROPOS"
# ─────────────────────────────────────────────────────────────────────────────
def make_source_badge(label, url, millesime):
    return html.Div([
        html.A(label, href=url, target="_blank",
               style={"fontWeight": "600", "color": "#dc3545"}),
        html.Span(f" · Millésime : {millesime}",
                  style={"fontSize": "0.85rem", "color": "#6c757d"}),
    ], style={"marginBottom": "6px"})

section_apropos = dbc.Container([
    dbc.Row(dbc.Col([
        html.H3("À propos · Boussole Électorale & Matérialiste", className="mt-3 mb-4 text-danger"),

        # ── Sources ──────────────────────────────────────────────────────────
        html.H5("📦 Sources des données", className="fw-bold mt-3"),
        html.Hr(),
        make_source_badge(
            "Résultats électoraux — Ministère de l'Intérieur",
            "https://www.data.gouv.fr/fr/datasets/elections-legislatives-des-12-et-19-juin-2022-resultats-par-bureau-de-vote/",
            "Municipales 2026 · Législatives 2024 · Présidentielle 2022"
        ),
        make_source_badge(
            "Contours des bureaux de vote — Etalab / data.gouv.fr",
            "https://www.data.gouv.fr/fr/datasets/contours-des-bureaux-de-vote-en-france/",
            "Reconstruction Voronoï 2022 (REU)"
        ),
        make_source_badge(
            "Données carroyées 200m — INSEE Filosofi",
            "https://www.insee.fr/fr/statistiques/7655475",
            "Filosofi 2017 (dernière édition disponible à 200m)"
        ),
        make_source_badge(
            "Structure des populations par IRIS — INSEE",
            "https://www.insee.fr/fr/statistiques/7631774",
            "Recensement 2022 (base IC-évol-struct-pop)"
        ),
        make_source_badge(
            "Géométries IRIS — IGN / IGN GeoServices",
            "https://geoservices.ign.fr/irisge",
            "IRIS_GE 2023"
        ),
        make_source_badge(
            "Base Adresse Nationale (recherche d'adresse)",
            "https://adresse.data.gouv.fr/api-doc/adresse",
            "Mise à jour continue"
        ),

        html.Hr(className="mt-4"),

        # ── Guide des métriques ───────────────────────────────────────────────
        html.H5("📖 Guide des métriques", className="fw-bold mt-3"),

        dbc.Accordion([
            dbc.AccordionItem([
                html.P("Ces métriques représentent la réserve de voix potentielle. Ce sont des volumes physiques d'individus à aller convaincre, pas des pourcentages."),
                html.Ul([
                    html.Li([html.Strong("Gisement JLM 2022 (normalisé) : "),
                             "Écart entre le % d'inscrits ayant voté Mélenchon (Présidentielle 2022) et le % d'inscrits ayant voté pour la gauche locale (Municipales). La version normalisée corrige le biais de participation : la présidentielle mobilise ~75% des inscrits, les municipales ~45%. Un écart positif indique un ancrage idéologique fort mais une non-mobilisation locale."]),
                    html.Li([html.Strong("Gisement NFP 2024 (normalisé) : "),
                             "Même logique avec les Législatives 2024. Cible les électeurs récemment mobilisés par la dynamique d'union."]),
                    html.Li([html.Strong("Abstentionnistes : "),
                             "Volume brut d'inscrits n'ayant pas voté au second tour. Premier indicateur de rentabilité d'une session de porte-à-porte."]),
                ])
            ], title="🔥 Gisements électoraux (priorité terrain)"),

            dbc.AccordionItem([
                html.P("Analyse marxiste des rapports de classe par bureau de vote."),
                html.Ul([
                    html.Li([html.Strong("Taux Ouvriers & Employés : "),
                             "(Ouvriers + Employés) / Pop. 15 ans et + × 100. Mesure la concentration du Bloc Populaire. Corrélé aux revendications salariales et de services publics."]),
                    html.Li([html.Strong("Taux Cadres supérieurs : "),
                             "Cadres et professions intellectuelles supérieures. Zones de force du vote centre-droit."]),
                    html.Li([html.Strong("Taux Artisans / Commerçants / Indépendants : "),
                             "Population électoralement disputée. Sensible à la fiscalité des indépendants et à la concurrence de la grande distribution. Argumentaire spécifique nécessaire."]),
                ])
            ], title="⚙️ Analyse de classe"),

            dbc.AccordionItem([
                html.Ul([
                    html.Li([html.Strong("Jeunes 18-39 ans : "),
                             "Sensibles à l'écologie et à la précarité. Zones à cibler avec des collages spécifiques."]),
                    html.Li([html.Strong("Familles monoparentales : "),
                             "Indicateur fort de besoin en services publics (crèches, cantines gratuites)."]),
                    html.Li([html.Strong("Locataires du parc privé : "),
                             "Subissent l'inflation et la précarité énergétique. Argumentaire : encadrement des loyers."]),
                ])
            ], title="👥 Ciblage démographique"),

            dbc.AccordionItem([
                html.P([
                    html.Strong("Taux de Rassemblement de la Gauche au T2 : "),
                    "= Voix Ferrand T2 / (Voix Ferrand T1 + Voix Suarez T1) × 100."
                ]),
                html.Ul([
                    html.Li([html.Strong("> 100% : "), "Report élargi — la liste a attiré des électeurs au-delà de sa base T1+PS (abstentionnistes mobilisés, électeurs At faisant barrage). Signal positif."]),
                    html.Li([html.Strong("95–100% : "), "Report quasi-parfait."]),
                    html.Li([html.Strong("80–95% : "), "Déperdition modérée — fuite vers l'abstention ou le centre."]),
                    html.Li([html.Strong("< 80% : "), "Déperdition forte — bureaux à analyser en priorité."]),
                ])
            ], title="🚨 Taux de Rassemblement"),

            dbc.AccordionItem([
                html.P("La couche Carreaux 200m utilise les données Filosofi 2017 de l'INSEE à la maille carroyée 200m×200m. C'est la maille la plus fine disponible en open data pour les indicateurs de pauvreté et logement."),
                html.P([
                    "Les contours des bureaux de vote proviennent d'une reconstruction mathématique (Voronoï) à partir du Répertoire Électoral Unique. Aux frontières exactes d'un bureau, le tracé peut différer de quelques mètres du découpage administratif strict. ",
                    html.Strong("Cela n'altère pas la qualité de l'analyse globale d'un quartier.")
                ]),
            ], title="📦 Notes méthodologiques"),

        ], start_collapsed=True, className="mt-2"),

        html.Hr(className="mt-4"),
        html.P([
            "Boussole Électorale · Albi 2026 · Données publiques open data · ",
            html.A("LFI Albi", href="#", style={"color": "#dc3545"})
        ], className="text-muted text-center small mt-3"),
    ]))
], fluid=True)


# ─────────────────────────────────────────────────────────────────────────────
# 8. APP LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    title="Boussole Électorale · Albi",
    suppress_callback_exceptions=True,
)
server = app.server   # Exposé pour Gunicorn (Render/Railway)

app.layout = dbc.Container([
    dbc.Row(dbc.Col(
        html.H1("🗳️ Boussole Électorale & Matérialiste — Albi",
                className="mt-4 mb-3 text-center text-danger fw-bold"),
    )),

    dbc.Tabs(id="tabs-main", active_tab="tab-carte", children=[

        # ── TAB 1 : Carte choroplèthe ────────────────────────────────────────
        dbc.Tab(label="🗺 Carte bureaux", tab_id="tab-carte", children=[
            dbc.Row(dbc.Col(
                html.Div(id='info-metrique',
                         className="text-center text-muted my-2",
                         style={"fontSize": "0.9rem", "fontStyle": "italic"}),
            )),
            dbc.Row([
                dbc.Col([
                    html.Label("Indicateur à cartographier :", className="fw-bold"),
                    dcc.Dropdown(
                        id='select-indicateur',
                        options=options_dropdown,
                        value=default_value,
                        clearable=False,
                        className="mb-3 shadow-sm"
                    )
                ], width=10, className="mx-auto")
            ]),
            dbc.Row(dbc.Col(
                dcc.Graph(id='carte-interactive', style={'height': '72vh'})
            )),
        ]),

        # ── TAB 2 : Carreaux 200m ────────────────────────────────────────────
        dbc.Tab(
            label="📦 Carreaux 200m",
            tab_id="tab-carreaux",
            disabled=(gdf_carreaux is None),
            children=[
                dbc.Row(dbc.Col(
                    dbc.Alert(
                        "Données Filosofi 2017 à la maille 200m×200m — visualisation plus fine que par bureau de vote.",
                        color="info", className="my-2"
                    ) if gdf_carreaux is not None else
                    dbc.Alert(
                        "Lance generate_carreaux.py pour activer cet onglet.",
                        color="warning", className="my-2"
                    )
                )),
                dbc.Row([
                    dbc.Col([
                        html.Label("Indicateur Filosofi :", className="fw-bold"),
                        dcc.Dropdown(
                            id='select-carreau',
                            options=OPTIONS_CARREAUX,
                            value='Taux_Pauvrete',
                            clearable=False,
                            className="mb-3"
                        )
                    ], width=6, className="mx-auto")
                ]) if gdf_carreaux is not None else html.Div(),
                dcc.Graph(id='carte-carreaux', style={'height': '72vh'})
                if gdf_carreaux is not None else html.Div(),
            ]
        ),

        # ── TAB 3 : Recherche par adresse ───────────────────────────────────
        dbc.Tab(label="🔍 Recherche adresse", tab_id="tab-adresse", children=[
            dbc.Row(dbc.Col([
                html.H5("Rechercher une adresse à Albi", className="fw-bold mt-3"),
                html.P("Saisissez une adresse pour obtenir les données sociales et électorales du bureau de vote correspondant.",
                       className="text-muted"),
                dbc.InputGroup([
                    dbc.Input(
                        id='input-adresse',
                        placeholder='Ex : 5 Place du Vigan, Albi',
                        type='text',
                        debounce=False,
                    ),
                    dbc.Button("Rechercher", id='btn-adresse', color="danger", n_clicks=0),
                ], className="mb-3"),
                html.Div(id='adresse-status', className="text-muted small mb-2"),
                html.Div(id='adresse-resultats'),
            ], width=10, className="mx-auto")),

            dbc.Row(dbc.Col(
                dcc.Graph(id='carte-adresse', style={'height': '55vh'})
            )),
        ]),

        # ── TAB 4 : À propos ─────────────────────────────────────────────────
        dbc.Tab(label="ℹ️ À propos", tab_id="tab-apropos", children=[
            section_apropos
        ]),
    ]),
], fluid=True)


# ─────────────────────────────────────────────────────────────────────────────
# 9. CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

# ── Carte choroplèthe ─────────────────────────────────────────────────────────
PALETTE_INFO = {
    'Taux_Ouvriers_Employes':    ('Reds',    "Concentration du Bloc Populaire."),
    'Taux_Cadres_Sup':           ('Blues',   "Cadres supérieurs. Zones centre-droit."),
    'Taux_Cadres_Bourgeoisie':   ('Blues',   "Cadres + indépendants (agrégé)."),
    'Taux_Independants':         ('Purples', "Artisans/commerçants — population disputée."),
    'Nombre_Abstentionnistes':   ('YlOrRd',  "Volume brut d'abstentionnistes."),
    'Ecart_JLM_Local':           ('YlOrRd',  "⚠ Volume brut — préférer la version normalisée pour l'analyse."),
    'Ecart_NFP_Local':           ('YlOrRd',  "⚠ Volume brut — préférer la version normalisée pour l'analyse."),
    'Ecart_JLM_Norm':            ('RdYlGn',  "Gisement JLM normalisé par inscrits. Mesure l'écart idéologique réel."),
    'Ecart_NFP_Norm':            ('RdYlGn',  "Gisement NFP normalisé par inscrits."),
    'Taux_Rassemblement_Gauche': ('RdYlGn',  "Vert = report élargi (>100%) · Rouge = fuite vers l'abstention."),
    'Taux_Jeunes_18_39':         ('Greens',  "18-39 ans. Cibles : écologie et précarité."),
    'Taux_Familles_Monoparentales':('YlOrRd',"Familles monoparentales. Axe : services publics."),
    'Taux_Locataires_Prives':    ('YlOrRd',  "Locataires privés. Axe : encadrement des loyers."),
}

@app.callback(
    Output('carte-interactive', 'figure'),
    Output('info-metrique', 'children'),
    Input('select-indicateur', 'value')
)
def update_carte(indicateur):
    if indicateur not in albi_map.columns:
        return go.Figure(), f"⚠ Colonne '{indicateur}' absente."

    color_scale, info = PALETTE_INFO.get(indicateur, ('Reds', ''))
    if 'Ferrand' in indicateur: color_scale = 'Purples'
    elif 'Suarez' in indicateur: color_scale = 'RdPu'
    elif 'Cabrolier' in indicateur or '_At_' in indicateur: color_scale = 'Blues'
    elif 'Guiraud' in indicateur: color_scale = 'Oranges'

    is_volume = indicateur in ['Nombre_Abstentionnistes', 'Ecart_JLM_Local', 'Ecart_NFP_Local']
    fmt = ':.0f' if is_volume else ':.1f'

    hover = {indicateur: fmt, 't2_votants': True}
    if 'Rassemblement_Qualitatif' in albi_map.columns:
        hover['Rassemblement_Qualitatif'] = True

    fig = px.choropleth_map(
        albi_map,
        geojson=albi_map.geometry,
        locations=albi_map.index,
        color=indicateur,
        color_continuous_scale=color_scale,
        map_style="carto-positron",
        zoom=12.5,
        center={"lat": 43.9285, "lon": 2.1426},
        opacity=0.8,
        hover_name='nom_bv' if 'nom_bv' in albi_map.columns else None,
        hover_data=hover,
        labels={indicateur: "Valeur", 't2_votants': "Votants T2",
                'Rassemblement_Qualitatif': "Qualité du report"},
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    return fig, info


# ── Carreaux 200m ─────────────────────────────────────────────────────────────
@app.callback(
    Output('carte-carreaux', 'figure'),
    Input('select-carreau', 'value'),
)
def update_carreaux(indicateur):
    if gdf_carreaux is None or indicateur not in gdf_carreaux.columns:
        return go.Figure()

    geojson = json.loads(gdf_carreaux.to_json())
    gdf_c = gdf_carreaux.copy().reset_index()

    fig = px.choropleth_map(
        gdf_c,
        geojson=geojson,
        locations=gdf_c.index,
        color=indicateur,
        color_continuous_scale='YlOrRd',
        map_style="carto-positron",
        zoom=12.5,
        center={"lat": 43.9285, "lon": 2.1426},
        opacity=0.75,
        hover_data={indicateur: ':.1f', 'Men': ':.0f'},
        labels={indicateur: "Valeur", 'Men': "Ménages"},
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    return fig


# ── Recherche adresse ─────────────────────────────────────────────────────────
@app.callback(
    Output('adresse-status',    'children'),
    Output('adresse-resultats', 'children'),
    Output('carte-adresse',     'figure'),
    Input('btn-adresse', 'n_clicks'),
    State('input-adresse', 'value'),
    prevent_initial_call=True,
)
def recherche_adresse(n_clicks, adresse):
    if not adresse or not adresse.strip():
        return "Saisissez une adresse.", html.Div(), go.Figure()

    # ── Appel API BAN ─────────────────────────────────────────────────────────
    try:
        r = requests.get(
            "https://api-adresse.data.gouv.fr/search/",
            params={"q": adresse + " Albi", "citycode": "81004", "limit": 1},
            timeout=5
        )
        data = r.json()
    except Exception as e:
        return f"❌ Erreur API BAN : {e}", html.Div(), go.Figure()

    if not data.get("features"):
        return "❌ Adresse introuvable. Essayez avec plus de détails.", html.Div(), go.Figure()

    feat     = data["features"][0]
    lon, lat = feat["geometry"]["coordinates"]
    label_adresse = feat["properties"].get("label", adresse)
    score    = feat["properties"].get("score", 0)

    # ── Trouver le bureau de vote ─────────────────────────────────────────────
    from shapely.geometry import Point
    pt = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326")
    albi_map_geo = albi_map.copy().reset_index()
    albi_map_geo = albi_map_geo.set_geometry('geometry').to_crs("EPSG:4326")
    joined = gpd.sjoin(pt, albi_map_geo, how="left", predicate="within")

    if joined.empty or joined['id_jointure'].isna().all():
        status = f"📍 {label_adresse} — hors périmètre des bureaux de vote d'Albi."
        return status, html.Div(), go.Figure()

    bv = joined.iloc[0]
    bv_id = int(bv['id_jointure'])

    # ── Tableau de données du bureau ─────────────────────────────────────────
    LABELS = {
        'Part_Ferrand_T2': 'Gauche (Ferrand) T2',
        'Part_Guiraud_T2': 'Droite (Guiraud) T2',
        'Taux_Rassemblement_Gauche': 'Taux de rassemblement gauche',
        'Nombre_Abstentionnistes': 'Abstentionnistes',
        'Taux_Ouvriers_Employes': 'Ouvriers & Employés',
        'Taux_Cadres_Sup': 'Cadres supérieurs',
        'Taux_Jeunes_18_39': 'Jeunes 18-39 ans',
        'Taux_Pauvrete': 'Taux de pauvreté',
        'Taux_Logement_Social': 'Logement social',
        'Ecart_JLM_Norm': 'Gisement JLM (normalisé)',
        'Ecart_NFP_Norm': 'Gisement NFP (normalisé)',
    }
    rows = []
    for col, lbl in LABELS.items():
        if col in bv.index and not pd.isna(bv[col]):
            val = bv[col]
            fmt = f"{val:.0f}" if col == 'Nombre_Abstentionnistes' else f"{val:.1f}%"
            rows.append(html.Tr([html.Td(lbl, style={"fontWeight": "500"}), html.Td(fmt)]))

    nom_bv = bv.get('nom_bv', f"Bureau {bv_id}")
    tableau = dbc.Table(
        [html.Thead(html.Tr([html.Th("Indicateur"), html.Th("Valeur")])),
         html.Tbody(rows)],
        bordered=True, hover=True, size="sm", className="mt-2"
    )
    resultats = html.Div([
        dbc.Alert(f"📍 {label_adresse} → {nom_bv} (confiance geocodage : {score:.0%})",
                  color="success", className="mt-2"),
        tableau,
    ])

    # ── Carte avec point ─────────────────────────────────────────────────────
    bv_row = albi_map_geo[albi_map_geo['id_jointure'] == bv_id]
    geojson_bv = json.loads(bv_row.to_json())
    fig = go.Figure()

    # Fond de carte + bureau mis en évidence
    fig.add_trace(go.Choroplethmapbox(
        geojson=json.loads(albi_map.reset_index().set_geometry('geometry').to_crs('EPSG:4326').to_json()),
        locations=list(range(len(albi_map))),
        z=[0.3] * len(albi_map),
        colorscale=[[0, "#eeeeee"], [1, "#eeeeee"]],
        showscale=False,
        marker_opacity=0.4,
        marker_line_width=1,
        hoverinfo='skip',
    ))
    fig.add_trace(go.Choroplethmapbox(
        geojson=geojson_bv,
        locations=[0],
        z=[1],
        colorscale=[[0, "#dc3545"], [1, "#dc3545"]],
        showscale=False,
        marker_opacity=0.65,
        marker_line_width=2,
        name=str(nom_bv),
        hoverinfo='skip',
    ))
    fig.add_trace(go.Scattermapbox(
        lat=[lat], lon=[lon], mode="markers+text",
        marker=dict(size=14, color="#dc3545"),
        text=[label_adresse], textposition="top right",
        textfont=dict(size=11, color="#dc3545"),
        name="Adresse",
    ))
    fig.update_layout(
        mapbox=dict(style="carto-positron", center={"lat": lat, "lon": lon}, zoom=14),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        showlegend=False,
    )
    return f"📍 {label_adresse}", resultats, fig


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
