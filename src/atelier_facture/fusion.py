import re
import os
import shutil
from pathlib import Path
import pandas as pd
from pandas import DataFrame

from pypdf import PdfWriter

from mpl import export_table_as_pdf
from pdf_utils import ajouter_ligne_regroupement
import logging
from rich.logging import RichHandler
# Configuration du logger pour utiliser Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger()

def merge_pdfs_by_group(groups: list[str], merge_dir: Path) -> list[Path]:
    """
    Fusionne les fichiers PDF par groupement.

    Cette fonction prend une liste de groupes et un répertoire de fusion, puis fusionne les fichiers PDF
    associés à chaque groupe en un seul fichier PDF par groupe.

    Paramètres:
    groups (list): Liste des groupes à traiter.
    merge_dir (Path): Répertoire où se trouvent les fichiers PDF à fusionner.

    Retourne:
    list: Liste des chemins des fichiers PDF fusionnés.
    """
    merged_pdf_files = []
    
    # Fusionner par groupement
    for group in groups:
        # Lire le fichier Excel contenant les informations des PDLs pour le groupe
        df = pd.read_excel(merge_dir / str(group) / f"{group}.xlsx")
        pdls = df["PRM"]
        group = str(group)
        
        # Récupérer tous les fichiers PDF dans le répertoire du groupe
        pdf_files = [f.resolve() for f in (merge_dir / group).iterdir() if f.suffix == ".pdf"]
        
        merger = PdfWriter()
        
        # Vérifier si le nombre de fichiers PDF correspond au nombre de PDLs + 2 (facture globale et tableau)
        if len(pdf_files) != len(pdls) + 2:
            logger.warning(f"Le nombre de fichiers PDF ({len(pdf_files)}) ne correspond pas au nombre de PDL ({len(pdls)}) pour le groupe {group}.")
        
        # Identifier les PDLs manquants
        pdf_pdls = [re.search(r'(\d{14})', pdf.stem).group(1) for pdf in pdf_files if re.search(r'(\d{14})', pdf.stem)]
        pdf_pdls = [pdl for pdl in pdf_pdls if pdl is not None]
        missing_pdls = set(pdls.astype(str)) - set(pdf_pdls)
        
        if missing_pdls:
            logger.warning(f"Les PDLs suivants sont manquants dans les fichiers PDF: {missing_pdls}")
        
        # Trouver la facture globale du groupement
        group_pdf = [f for f in pdf_files if normalize(group) in normalize(f.name) and not f.name.startswith("Table") and not re.search(r'\d{14}$', f.stem)]
        
        if len(group_pdf) > 1:
            logger.warning(f'Plusieurs factures de groupement ont été trouvées pour {group}!')
            logger.warning(group_pdf)
            group_pdf = [group_pdf[1]]
        
        if not group_pdf:
            logger.warning(f"Aucune facture de groupement n'a été trouvée dans le même dossier pour {group}!")
        else:
            # Ajouter la facture globale en premier
            merger.append(group_pdf[0])
            pdf_files.remove(group_pdf[0])
            filename_parts = group_pdf[0].stem.split('-')
            if len(filename_parts) >= 2:
                date = filename_parts[0].strip()
                name = filename_parts[1].strip()
        
        # Trouver le fichier PDF du tableau
        table_pdf = [f for f in pdf_files if f.name.startswith("Table") and normalize(group) in normalize(f.name)]
        merger.append(table_pdf[0])
        pdf_files.remove(table_pdf[0])

        # Ajouter les factures unitaires dans l'ordre d'apparition du tableau
        for pdl in pdls:
            for pdf in pdf_files:
                if str(pdl) in pdf.name:
                    merger.append(pdf)
                    pdf_files.remove(pdf)
        
        if len(pdf_files) != 0:
            logger.warning(f"Certains PDF n'ont pas été fusionnés: {pdf_files}")
        
        # Renommer le fichier de sortie si nécessaire
        name = 'CAPB' if name == 'COMMUNAUTE_AGGLOMERATION_PAYS_BASQUE' else name
        output_pdf_path = merge_dir / f"{date}-{name}-{group}.pdf"
        merger.write(output_pdf_path)
        merged_pdf_files.append(output_pdf_path)
        merger.close()
        logger.info(f"Fusionné: {output_pdf_path}")
    
    return merged_pdf_files

def group_name_from_filename(filename: Path) -> str:
    """
    Extrait le nom du groupe à partir du nom de fichier.

    Cette fonction prend un nom de fichier, remplace les occurrences de ' - ' par '-',
    divise le nom de fichier en utilisant '-' comme séparateur, et joint les parties
    à partir de la troisième partie avec ' - '.

    Paramètres:
    filename (str): Le nom du fichier dont on veut extraire le nom du groupe.

    Retourne:
    str: Le nom du groupe extrait du nom de fichier.
    """
    return ' - '.join(filename.stem.replace(' - ', '-').split('-')[2:])

def sort_pdfs_by_group(df: DataFrame, pdl_dir: Path, group_dir: Path, merge_dir: Path, symlink: bool=False):
    """
    Trie les fichiers PDF par groupement en fonction des informations fournies dans un DataFrame.

    Paramètres:
    df (DataFrame): Le DataFrame contenant les informations de groupement et de PDL.
    pdl_dir (Path): Le répertoire contenant les fichiers PDF des PDL.
    group_dir (Path): Le répertoire contenant les fichiers PDF des groupements.
    merge_dir (Path): Le répertoire où les fichiers triés seront enregistrés.
    symlink (bool): Indique s'il faut créer des liens symboliques au lieu de copier les fichiers. Par défaut False.

    Cette fonction trie les fichiers PDF des PDL et des groupements dans des sous-dossiers spécifiques
    basés sur les informations de groupement fournies dans le DataFrame.
    """
    for pdf_file in pdl_dir.glob('*.pdf'):
        # Extraire le PDL à partir du nom de fichier (ex: _123456789.pdf)
        # On suppose que le numéro PDL est avant l'extension du fichier
        pdl_number = pdf_file.stem.split('-')[-1].replace(' ', '')  # le PDL est après le dernier '-'

        # Chercher ce PDL dans le DataFrame
        matching_row = df[df['PRM'] == int(pdl_number)]
        
        if not matching_row.empty:
            # Obtenir le nom du dossier groupement correspondant
            groupement_dir = str(matching_row['groupement'].values[0])

            # Définir le chemin du dossier de destination
            destination_dir = merge_dir / groupement_dir
            
            # Créer le dossier de destination s'il n'existe pas
            if destination_dir.exists():
                # Copier le fichier PDF dans le bon dossier
                if symlink:
                    os.symlink(pdf_file, destination_dir / pdf_file.name)
                else:
                    shutil.copy(pdf_file, destination_dir / pdf_file.name)

    for pdf_file in group_dir.glob('*.pdf'):
        # Extraire le nom du groupe à partir du nom de fichier
        group_name = group_name_from_filename(pdf_file)

        # Définir le chemin du dossier de destination basé sur le groupe
        destination_dir = merge_dir / group_name
        
        if destination_dir.exists():
            # Copier le fichier PDF dans le bon dossier
            shutil.copy(pdf_file, destination_dir / pdf_file.name)

def sort_xls_by_group(df: DataFrame, groups: list[str], merge_dir: Path=None):
    """
    Trie le fichier Excel par groupement et crée un excel par groupement dans des sous-dossiers spécifiques.

    Paramètres:
    df (DataFrame): Le DataFrame contenant les données à trier.
    groups (list): Liste des groupements uniques.
    merge_dir (Path, optionnel): Le répertoire où les fichiers triés seront enregistrés. Par défaut, None.

    Cette fonction filtre les données pour chaque groupement spécifique, réorganise les colonnes pour
    que la colonne 'groupement' soit en premier, et enregistre les données triées dans un fichier Excel
    dans un sous-dossier nommé d'après le groupement.
    """
    # Nom de la colonne de groupement
    group_col_name = "groupement"
    
    for group in groups:
        # Filtrer les données pour le groupement spécifique
        df_groupement = df[df[group_col_name] == group]
        
        # Réorganiser les colonnes pour que 'groupement' soit en premier
        colonnes = [group_col_name] + [col for col in df.columns if col != group_col_name]
        df_groupement = df_groupement[colonnes]
        
        # Créer le répertoire pour le groupement s'il n'existe pas
        group_dir = merge_dir / str(group)
        group_dir.mkdir(exist_ok=True, parents=True)
        
        # Enregistrer les données triées dans un fichier Excel
        df_groupement.to_excel(group_dir / f"{group}.xlsx", index=False)

def export_tables_as_pdf(groups: list[str], merge_dir: Path):
    """
    Exporte les tables Excel en fichiers PDF pour chaque groupement.

    Paramètres:
    groups (list[str]): Liste des noms de groupements.
    merge_dir (Path): Chemin vers le répertoire contenant les fichiers Excel des groupements.

    Cette fonction lit les fichiers Excel pour chaque groupement, supprime la colonne 'membre' si elle existe,
    et exporte les données restantes en fichiers PDF.
    """
    for group in groups:
        group_dir = merge_dir / str(group)
        df_g = pd.read_excel(group_dir / f"{group}.xlsx")
        # On enlève la colonne 'membre' pour l'export
        if 'membre' in df_g.columns:
            df_g = df_g.drop('membre', axis=1)

        export_table_as_pdf(df_g, group_dir / f"Table_{group}.pdf")

def create_grouped_invoices(df: DataFrame, indiv_dir: Path, group_dir: Path, merge_dir: Path) -> list[Path]:
    """
    Crée des factures groupées à partir des données fournies.

    Paramètres:
    df (DataFrame): Le DataFrame contenant les données des factures.
    indiv_dir (Path): Le chemin vers le répertoire contenant les factures unitaires.
    group_dir (Path): Le chemin vers le répertoire contenant les factures de regroupement.
    merge_dir (Path): Le chemin vers le répertoire où les factures groupées seront enregistrées.

    Retourne:
    list[Path]: Une liste des chemins des fichiers PDF fusionnés.
    """
    # Détecter les groupes avec plusieurs PDLs
    groups = df.groupby("groupement").filter(lambda x: len(x) >= 1)["groupement"].unique()

    if "nan" in groups:
        groups = groups.remove("nan")
    
    # Filtrer les groupes pour n'avoir que ceux trouvés dans les factures de regroupement
    found_groups = set([group_name_from_filename(f) for f in group_dir.glob("*.pdf")])
    groups = [g for g in groups if g in found_groups]
    logger.info(f"Groupements à traiter : {groups}")
    
    logger.info("Tri des fichiers Excel défusionnés \n")
    sort_xls_by_group(df, groups, merge_dir)

    logger.info("Export en PDF des tableurs Excel \n")
    export_tables_as_pdf(groups, merge_dir)

    logger.info("Tri des fichiers PDF défusionnés \n")
    sort_pdfs_by_group(df, indiv_dir, group_dir, merge_dir)

    logger.info("Fusion des PDF par groupement")
    merged_pdf_files = merge_pdfs_by_group(groups, merge_dir)
    logger.info("└── Fin de la fusion")
    
    return merged_pdf_files

def normalize(string: str) -> str:
    return str(string).replace(" ", "").replace("-", "").lower()

def create_grouped_single_invoice(df: DataFrame, indiv_dir: Path, group_dir: Path, merge_dir: Path) -> Path:
    # Detect groups with only one line in df
    single_line_groups = df.groupby('groupement').filter(lambda x: len(x) == 1)
    # Remove 'nan' group if it exists
    single_line_groups = single_line_groups[single_line_groups['groupement'] != 'nan']
    logger.info(f"Groupes avec une seule ligne : {single_line_groups['groupement'].tolist()}")
    for _, row in single_line_groups.iterrows():
        #print(row)
        group = row['groupement']
        prm = row['PRM']
        matching_files = list(indiv_dir.glob(f"*{prm}*.pdf"))
        if matching_files:
            ajouter_ligne_regroupement(matching_files[0], indiv_dir, f'Regroupement de facturation : ({group})')
        else:
            logger.warning(f"Aucun fichier trouvé pour le pdl {prm} du groupe à pdl unique {group}")