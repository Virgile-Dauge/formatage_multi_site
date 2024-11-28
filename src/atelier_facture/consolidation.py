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

def consolidation(extrait: DataFrame, consignes: DataFrame) -> DataFrame:
    consignes = detection_type(consignes)
    condition = (consignes['type'] == 'groupement')

    # Récupération des id des factures de groupements à partir de la clé "groupement"
    merged_groupement = consignes[condition].merge(extrait, on='groupement', how='left', suffixes=('', '_extrait'))
    consignes.loc[condition, 'id'] = merged_groupement['id_extracted']

    # Fusion des données extraites dans les consignes sur clé "id"
    consolide = consignes.merge(extrait, on='id', how='left')
    return consolide