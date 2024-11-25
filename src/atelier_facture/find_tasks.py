import pandas as pd
from pandas import DataFrame
from pathlib import Path

from file_naming import compose_filename
from mpl import export_table_as_pdf
from pdf_utils import concat_pdfs, ajouter_ligne_regroupement_doc, apply_pdf_transformations

def detection(df: DataFrame):
    """
    Détecte et attribue le type d'entrée pour chaque ligne du DataFrame.

    Cette fonction catégorise chaque ligne du DataFrame en 'groupement', 'pdl', ou 'mono'
    en fonction des valeurs dans les colonnes 'pdl' et 'groupement'.

    Args:
        df (DataFrame): Le DataFrame à analyser.

    Returns:
        None: La fonction modifie le DataFrame en place.
    """
    df['type'] = 'Indeterminé'
    group_mask = (df['pdl'].isna() | (df['pdl'] == ''))
    df.loc[group_mask, 'type'] = 'groupement'
    df.loc[~group_mask, 'type'] = 'pdl'

    # Detection 'mono' type for unique values in 'groupement' column
    groupement_counts = df['groupement'].value_counts()
    unique_groupements = groupement_counts[groupement_counts == 1].index
    df.loc[df['groupement'].isin(unique_groupements), 'type'] = 'mono'

def fusion_groupes(df: DataFrame, output_dir: Path):
    df.sort_values(['membre', 'groupement', 'type', 'pdl'], inplace=True)
    # Ajout de la colonne 'fichier_enrichi' si elle n'existe pas
    if 'fichier_enrichi' not in df.columns:
        df['fichier_enrichi'] = ''

    meta_columns = ['fichier_extrait','fichier_enrichi', 'type']
    # Grouper par 'groupement'
    grouped = df.groupby('groupement')
    
    # Parcourir chaque groupement
    for group_name, group_data in grouped:
        group_meta = group_data.iloc[0].to_dict()
 
        enhanced_pdf = output_dir / f"{compose_filename(group_meta, format_type='groupement')}.pdf"
        # Création du PDF enrichi pour le groupement Mono
        if group_meta['type'] == 'mono':
            
            transformations = [
                (ajouter_ligne_regroupement_doc, group_meta['groupement'])
                # Add more transformations as needed
            ]
            apply_pdf_transformations(group_meta['fichier_extrait'], enhanced_pdf, transformations)
        
        # Création du PDF enrichi pour le groupement
        else:
            # Ajouter la facture de groupement 
            to_concat = [group_meta['fichier_extrait']]
            
            # Extraction des lignes pdl 
            pdl = group_data[group_data['type'] == 'pdl']

            # On crée le pdf tableau
            table_name = output_dir / f"{compose_filename(group_meta, format_type='table')}.pdf"
            export_table_as_pdf(pdl.drop(columns=meta_columns), table_name)

            # On ajoute le tableau crée  
            to_concat += [table_name]
            # Liste des PRM pour ce groupement (exclure les valeurs manquantes)
            to_concat += pdl['fichier_extrait'].tolist()
            
            # Fichier de groupement enrichi 
            concat_pdfs(to_concat, enhanced_pdf)
        
        # Mettre à jour la colonne 'fichier_enrichi' pour ce groupement
        df.loc[df['groupement'] == group_name, 'fichier_enrichi'] = enhanced_pdf

    return df

if __name__ == "__main__":
    p = Path("~/data/enargia/tests/").expanduser()
    ip = p / 'extrait'
    ep = p / 'enrichi'
    df = pd.read_csv(ip / 'todo.csv', sep=',', encoding='utf-8', dtype=str)
    detection(df)
    print(df)
    result = fusion_groupes(df, ep)
    print(df)
    df.to_csv(ep / "enrichi.csv")
    # print(result)