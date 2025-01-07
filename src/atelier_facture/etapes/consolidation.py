from pandas import DataFrame
from atelier_facture.utils import logger

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
    # Apply zfill only to valid numeric-like strings
    df['id'] = df['id'].apply(
    lambda x: x.zfill(14) if x.isdigit() else x
    )
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

    if len(consignes_groupement) != len(merged):
        logger.warning(
            f"Incohérence dans les tailles des données : consignes_groupement contient {len(consignes_groupement)} lignes, "
            f"mais seulement {len(merged)} lignes fusionnées. Certaines clés 'groupement' pourraient manquer dans 'extrait'."
        )
    # Mettre à jour la colonne 'id' de 'consignes' à partir de 'id' de 'extrait'
    # Crée un dictionnaire pour le mapping
    mapping = merged.set_index('groupement')['id_extrait'].to_dict()

    # Met à jour la colonne 'id' en utilisant map
    consignes.loc[consignes['type'] == 'groupement', 'id'] = consignes.loc[
        consignes['type'] == 'groupement', 'groupement'
    ].map(mapping)
    # consignes.loc[consignes['type'] == 'groupement', 'id'] = merged['id_extrait'].values
    
    non_matching_ids = set(consignes['id']).difference(set(extrait['id']))

    # Filtrer les lignes correspondantes dans consignes
    non_matching_rows = consignes[consignes['id'].isin(non_matching_ids)]

    # Log un warning par ID non matché, incluant le groupement
    for _, row in non_matching_rows.iterrows():
        logger.warning(
            f"ID non trouvé dans extrait : {row['id']} | Groupement : {row['groupement']} | Type : {row.get('type', 'N/A')}"
        )
    
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