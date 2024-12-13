from pathlib import Path
import pandas as pd
from pandas import DataFrame

from file_naming import compose_filename
from mpl import export_table_as_pdf
from pdf_utils import ajouter_ligne_regroupement_doc, apply_pdf_transformations, concat_pdfs, compress_pdf_inplace

from logger_config import logger

def fusion_groupes(df: DataFrame, output_dir: Path):

    df.sort_values(['groupement', 'type', 'pdl'], inplace=True)
    # Ajout de la colonne 'fichier_enrichi' si elle n'existe pas
    if 'pdf' not in df.columns:
        df['pdf'] = ''

    meta_columns = ['fichier_extrait', 'pdf', 'type', 'date']
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
            # Filtrer les NaN et afficher un avertissement pour chaque NaN
            for index, row in pdl.iterrows():
                fichier = row['fichier_extrait']
                if pd.isna(fichier):
                    logger.warning(f"Pas de 'fichier_extrait' {row['id']} : fichier enrichi groupement {row['groupement']} créé sans.")
                else:
                    to_concat.append(fichier)

            # Fichier de groupement enrichi 
            concat_pdfs(to_concat, enhanced_pdf)
            # compressed_pdf = enhanced_pdf.with_name(f"{enhanced_pdf.stem}_compressed{enhanced_pdf.suffix}")
            # compress_pdf(enhanced_pdf, compressed_pdf)
            compress_pdf_inplace(enhanced_pdf)
        
        # Mettre à jour la colonne 'fichier_enrichi' pour ce groupement
        df.loc[df['id'] == group_meta['id'], 'pdf'] = enhanced_pdf

    # Copie des valeurs de 'fichier_extrait' dans 'fichier_enrichi' si non définies
    mask_non_defini = df['pdf'].isin([False, pd.NA, None, ''])
    df.loc[mask_non_defini, 'pdf'] = df.loc[mask_non_defini, 'fichier_extrait']
    return df