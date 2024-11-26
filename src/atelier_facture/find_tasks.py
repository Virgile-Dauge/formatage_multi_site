import argparse
import pandas as pd
from pandas import DataFrame
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from logger_config import setup_logger, logger
from file_naming import compose_filename
from mpl import export_table_as_pdf
from pdf_utils import concat_pdfs, ajouter_ligne_regroupement_doc, apply_pdf_transformations
from pedagogie import afficher_arborescence_travail, etat_avancement
from extraction import process_zipped_pdfs_enhanced
from facturix import process_invoices

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
    if 'pdf' not in df.columns:
        df['pdf'] = ''

    meta_columns = ['fichier_extrait','pdf', 'type', 'date']
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
                    logger.warning(f"Pas de 'fichier_extrait' pour facture {row['id']} dans le groupe {row['groupement']}")
                else:
                    to_concat.append(fichier)
            
            # Fichier de groupement enrichi 
            concat_pdfs(to_concat, enhanced_pdf)
        
        # Mettre à jour la colonne 'fichier_enrichi' pour ce groupement
        df.loc[df['id'] == group_meta['id'], 'pdf'] = enhanced_pdf

    # Copie des valeurs de 'fichier_extrait' dans 'fichier_enrichi' si non définies
    mask_non_defini = df['pdf'].isin([False, pd.NA, None, ''])
    df.loc[mask_non_defini, 'pdf'] = df.loc[mask_non_defini, 'fichier_extrait']
    return df

def vers_facturx(df: DataFrame, csv: Path, output_dir: Path):
    # Charger le CSV dans une DataFrame BT
    bt_df = pd.read_csv(csv, dtype=str)
    
    # Fusionner bt_df avec df en utilisant 'BT-1' et 'id' comme clés
    merged_df = pd.merge(bt_df, df[['id', 'pdf']], left_on='BT-1', right_on='id', how='left')

    # Supprimer la colonne 'id', elle n'est pas nécessaire après la fusion
    merged_df = merged_df.drop('id', axis=1)

    errors = process_invoices(merged_df, output_dir, output_dir, conform_pdf=False)
    return errors

def main():
    parser = argparse.ArgumentParser(description="Traitement des factures")
    parser.add_argument("atelier_path", type=str, help="Chemin du répertoire atelier")
    parser.add_argument("-i", "--input", type=str, help="Chemin vers le fichier zip d'entrée, ou le dossier de zips d'entrée.")
    parser.add_argument("-f", "--force", action="store_true", help="Supprime tous les fichiers intermédiaires (pas les fichiers bruts extraits)")
    parser.add_argument('-v', '--verbose', action='count', default=0, help="Plus de logs (e.g., -v or -vv)")
    args = parser.parse_args()

    # Configuration des loggs based on verbosity
    setup_logger(args.verbose)
    console = Console()

    p = Path(args.atelier_path).expanduser()
    ip = p / 'extrait'
    ep = p / 'enrichi'
    fp = p / 'facturx'

    # Création des repertoires de travail
    for dir_path in [ip, ep, fp]:
        dir_path.mkdir(parents=True, exist_ok=True)

    # =======================Étape 0: Définition du répertoire de travail==============
    console.print(Panel.fit("Étape 0: Définition du répertoire de travail", style="bold magenta"))
    afficher_arborescence_travail(console, p, ip, ep, fp)

    # =======================Étape 1: Extraction des données===========================
    if args.input:
        input_path = Path(args.input).expanduser()
        process_zipped_pdfs_enhanced(input_path, r"N° de facture\s*:\s*(\d{14})", ip)
        # TODO

    # =======================Étape 2: Lecture des consignes============================
    df = pd.read_csv(p / 'todo.csv', sep=',', encoding='utf-8', dtype=str)
    detection(df)
    etat_avancement(console, df, ip, ep, fp)

    # =======================Étape 3: Création des pdfs enrichis=======================
    result = fusion_groupes(df, ep)
    etat_avancement(console, df, ip, ep, fp)
    # =======================Étape 4: Création des factures Factur-X===================
    bt_df = vers_facturx(df, p / 'bt.csv', fp)

if __name__ == "__main__":
    main()
    # p = Path("~/data/enargia/tests/").expanduser()
    # ip = p / 'extrait'
    # ep = p / 'enrichi'
    # fp = p / 'facturx'
    # df = pd.read_csv(ip / 'todo.csv', sep=',', encoding='utf-8', dtype=str)
    # detection(df)
    # print(df)
    # result = fusion_groupes(df, ep)
    # print(df)
    # bt_df = vers_facturx(df, p / 'bt.csv', fp)
    # df.to_csv(p / "todo_enrichi.csv", index=False)
    # bt_df.to_csv(p / "bt_up.csv", index=False)
    # print(result)