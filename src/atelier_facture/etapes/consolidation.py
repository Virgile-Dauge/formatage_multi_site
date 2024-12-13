from pandas import DataFrame

def detection_type(df: DataFrame) -> DataFrame:
    """
    Détecte et attribue le type d'entrée pour chaque ligne du DataFrame.

    Cette fonction catégorise chaque ligne du DataFrame en 'groupement', 'pdl', ou 'mono'
    en fonction des valeurs dans les colonnes 'pdl' et 'groupement'.
    """
    df = df.copy()
    df['type'] = 'Indeterminé'
    group_mask = (df['pdl'].isna() | (df['pdl'] == ''))
    df.loc[group_mask, 'type'] = 'groupement'
    df.loc[~group_mask, 'type'] = 'pdl'

    # Detection 'mono' type for unique values in 'groupement' column
    groupement_counts = df['groupement'].value_counts()
    unique_groupements = groupement_counts[groupement_counts == 1].index
    df.loc[df['groupement'].isin(unique_groupements), 'type'] = 'mono'

    return df

def consolidation_consignes(extrait: DataFrame, consignes: DataFrame) -> DataFrame:
    consignes['id'] = consignes['id'].astype(str).apply(
        lambda x: str(int(float(x))).zfill(14) if x and x.replace('.', '', 1).isdigit() and x.endswith('.0') else x
    )
    consignes = detection_type(consignes)
    # Filtrer les lignes de 'consignes' où 'type' est égal à 'groupement'
    consignes_groupement = consignes[consignes['type'] == 'groupement']

    # Faire un merge entre 'consignes_groupement' et 'extrait' sur la clé 'groupement'
    merged = consignes_groupement.merge(extrait[['groupement', 'id']], on='groupement', suffixes=('_consignes', '_extrait'))
    # Mettre à jour la colonne 'id' de 'consignes' à partir de 'id' de 'extrait'
    consignes.loc[consignes['type'] == 'groupement', 'id'] = merged['id_extrait'].values

    # Fusion des données extraites dans les consignes sur clé "id"
    consolide = consignes.merge(extrait[['id', 'date', 'fichier_extrait']], on='id', how='left', suffixes=('', '_extrait'))

    consolide = consolide.loc[:, ~consolide.columns.str.startswith('Unnamed')]
    return consolide

def consolidation_facturx(consignes_consolidees: DataFrame, facturx: DataFrame) -> DataFrame:

    # Filtrer les lignes de 'consignes' où 'type' est égal à 'groupement'
    consignes_groupement = consignes_consolidees[consignes_consolidees['type'] == 'groupement']
    print(consignes_groupement.columns)
    print(facturx.columns)
    facturx = facturx.merge(consignes_groupement[['groupement', 'id']], on='groupement', how='left', suffixes=('', '_consignes'))

    if 'id_consignes' in facturx.columns:
        facturx['id'] = facturx['id'].combine_first(facturx['id_consignes'])
        facturx.drop(columns=['id_consignes'], inplace=True)

    # facturx.drop(columns=['id_consignes', 'groupement'], inplace=True)
    facturx['id'] = facturx['id'].astype(str).apply(
        lambda x: str(int(float(x))).zfill(14) if x and x.replace('.', '', 1).isdigit() and x.endswith('.0') else x
    )
    return facturx