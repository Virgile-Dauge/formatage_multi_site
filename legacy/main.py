import re
import os
import logging
from pypdf import PdfReader, PdfWriter
from pypdf.errors import EmptyFileError
import argparse
from pathlib import Path
import pandas as pd
import sys
import fitz
import shutil

from mpl import export_table_as_pdf
from rich.logging import RichHandler

# Configuration du logger pour utiliser Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger()

# POUR UTILISER CE SCRIPT, DESCENDRE A LA LIGNE "__name__" == "__main__"
# Regex patterns pour extraire les informations
date_pattern = r'VOTRE FACTURE DU (\d{2})\/(\d{2})\/(\d{4})'
client_name_pattern = r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)'
group_name_pattern = r'Regroupement de facturation\s*:\s*\((.*?)\)'
group_name_pattern = r'Regroupement de facturation\s*:\s*\(([\s\S]*?)\)'
pdl_pattern = r'Référence PDL : (\d{14})'

def split_bill_pdfs(pdf_file_path, output_dir="output_pdfs",  start_keyword="www.enargia.eus", regex_dict=None):
    
    # Un peu compliqué, en vrai séparer en sous pdfs puis trier les pdfs après en regroup ou indiv me parait plus simple
    # Ouvrir le fichier PDF
    try:
        reader = PdfReader(pdf_file_path)
        # Continuez avec le reste du traitement
    except EmptyFileError as e:
        logger.error(f"Erreur : {e} '{pdf_file_path}'")
        return
    #reader = PdfReader(pdf_file_path)
    num_pages = len(reader.pages)
    writer = None

    date = None
    client_name = None
    group_name = None
    pdl_name = None
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for i in range(num_pages):
        page = reader.pages[i]
        text = page.extract_text()

        # Rechercher le mot-clé indiquant le début d'un nouveau sous-PDF
        if start_keyword in text:
            if writer:
                # Enregistrer le PDF précédent avant de commencer un nouveau
                if "group_name" in regex_dict.keys() and group_name and date and client_name:
                    logger.info(f"Enregistrement du PDF: {date}-{client_name} - {group_name}.pdf")
                    output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {group_name}.pdf")
                elif "pdl_name" in regex_dict.keys() and pdl_name and date and client_name:
                    output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {pdl_name}.pdf")
                else:
                    output_pdf_path = None
                if output_pdf_path:
                    # Enlever les métadonnées pour alléger le fichier
                    with open(output_pdf_path, "wb") as output_pdf:
                        writer.write(output_pdf)
                writer = None

            # Créer un nouveau writer pour le prochain sous-PDF
            writer = PdfWriter()
            writer.add_page(page)

            # Extraire la date
            date_match = re.search(date_pattern, text)
            if date_match:
                date = f"{date_match.group(3)}{date_match.group(2)}{date_match.group(1)}"#.replace("\n", " ")

            # Extraire le nom du client
            client_name_match = re.search(client_name_pattern, text)
            if client_name_match:
                client_name = client_name_match.group(1).strip().replace(" ", "_")  # Remplace les espaces par "_"

            # Extraire le nom du groupement
            group_name_match = re.search(group_name_pattern, text, re.DOTALL)
            if group_name_match:
                group_name = group_name_match.group(1).strip().replace("\n"," ")

            pdl_match = re.search(pdl_pattern, text)
            if pdl_match:
                pdl_name = pdl_match.group(1)

        elif writer:
            # Ajouter la page actuelle au writer en cours
            writer.add_page(page)

    # Enregistrer le dernier PDF
    if writer:
        if "group_name" in regex_dict.keys() and group_name and date and client_name:
            output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {group_name}.pdf")
        elif "pdl_name" in regex_dict.keys() and pdl_name and date and client_name:
            output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {pdl_name}.pdf")
        else:
            output_pdf_path = None
        if output_pdf_path:
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)

def split_pdfs_recursive(data_dir, output_dir, regex_dict):
    logger.info(f"Parcours du répertoire {data_dir}")
    for file in data_dir.iterdir():
        if file.is_file() and file.suffix == ".pdf":
            logger.info(f"Extraction des pdfs dans le fichier {file}")
            split_bill_pdfs(file, output_dir, "www.enargia.eus", regex_dict)
        elif file.is_dir() and not file.name == output_dir.name :
            split_pdfs_recursive(file, output_dir, regex_dict)

def split_global_bills(data_dir, output_dir):
    # Factures globales par groupement
    regex_dict = {"date": date_pattern, "client_name":client_name_pattern, "group_name": group_name_pattern}
    split_pdfs_recursive(data_dir, output_dir, regex_dict)

def split_unit_bills(data_dir, output_dir):
    # Factures unitaires
    regex_dict = {"date": date_pattern, "client_name": client_name_pattern, "pdl_name": pdl_pattern}
    split_pdfs_recursive(data_dir, output_dir,  regex_dict)

def merge_pdfs_by_group(groups, merge_dir):
    merged_pdf_files = []
    # fusioner par groupement
    for group in groups:
        df = pd.read_excel(merge_dir / str(group) / f"{group}.xlsx")
        pdls = df["PRM"]
        group = str(group)
        pdf_files = [filename for filename in (merge_dir / group).iterdir() if filename.suffix == ".pdf"]
        
        if len(pdf_files) != len(pdls) + 2:
            logger.warning(f"Le nombre de fichiers PDF ({len(pdf_files)}) ne correspond pas au nombre de PDL ({len(pdls)}) pour le groupe {group}.")

        merger = PdfWriter()
        # ajoute la facture globale en premier
        for pdf in pdf_files:
            if normalize(group) in normalize(pdf.name) and not pdf.name.startswith("Table"):
                # Extraire la date et le nom du fichier
                filename_parts = pdf.stem.split('-')
                if len(filename_parts) >= 2:
                    date = filename_parts[0].strip()
                    name = filename_parts[1].strip()
                merger.append(pdf)
                pdf_files.remove(pdf)

        # ajoute le tableau récapitulatif
        for pdf in pdf_files:
            if pdf.name.startswith("Table") and normalize(group) in normalize(pdf.name):
                merger.append(pdf)
                pdf_files.remove(pdf)

        # Rajoute les factures unitaires dans l'ordre d'apparition du tableau.
        for pdl in pdls:
            for pdf in pdf_files:
                if str(pdl) in pdf.name:
                    merger.append(pdf)
                    pdf_files.remove(pdf)
        if len(pdf_files) != 0:
            logger.warning(f"Certains PDF n'ont pas été fusionnés: {pdf_files}")
        
        name = 'CAPB' if name == 'COMMUNAUTE_AGGLOMERATION_PAYS_BASQUE' else name
        merger.write((merge_dir) / f"{date}-{name}-{group}.pdf")
        merged_pdf_files.append(merge_dir / f"{date}-{name}-{group}.pdf")
        merger.close()
        logger.info(f"Fusionné: {date}-{name}-{group}.pdf")
    return merged_pdf_files


def group_name_from_filename(filename: str) -> str:
    return ' - '.join(filename.stem.replace(' - ', '-').split('-')[2:])

def sort_pdfs_by_group(df, groups, pdl_dir, group_dir, merge_dir):
    uncopied = []
    # print(list(filenames))
    for pdf_file in pdl_dir.glob('*.pdf'):
        # Extraire le PDL à partir du nom de fichier (ex: _123456789.pdf)
        # On suppose que le numéro PDL est avant l'extension du fichier
        pdl_number = pdf_file.stem.split('-')[-1].replace(' ', '')  #le PDL est après le dernier '-'

        # Chercher ce PDL dans le DataFrame
        matching_row = df[df['PRM'] == int(pdl_number)]
        
        if not matching_row.empty:
            # Obtenir le nom du dossier groupement correspondant
            groupement_dir = str(matching_row['groupement'].values[0])

            # Définir le chemin du dossier de destination
            destination_dir = merge_dir / groupement_dir
            
            # Créer le dossier de destination s'il n'existe pas
            destination_dir.mkdir(parents=True, exist_ok=True)
            
            # Copier le fichier PDF dans le bon dossier
            shutil.copy(pdf_file, destination_dir / pdf_file.name)
        else:
            uncopied += [pdf_file]
        
    for pdf_file in group_dir.glob('*.pdf'):
        # Extraire le nom du groupe à partir du nom de fichier
        # Supposons que le format du fichier est du type 'date-EPIC_HABITAT_REGION - GROUP - MORE_GROUP_INFO.pdf'
        # On veut extraire le groupe entre les deux tirets dans le nom du fichier.
        
        group_name = group_name_from_filename(pdf_file)

        # Définir le chemin du dossier de destination basé sur le groupe
        destination_dir = merge_dir / group_name
        # Créer le répertoire cible s'il n'existe pas
        if not destination_dir.exists():
            uncopied += [pdf_file]
        else:
            # Copier le fichier PDF dans le bon dossier
            shutil.copy(pdf_file, destination_dir / pdf_file.name)
    if uncopied:   
        logger.warn(f'Uncopied files : {uncopied}')

def sort_xls_by_group(df, groups, merge_dir=None):
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
        group_dir.mkdir(exist_ok=True)
        
        # Enregistrer les données triées dans un fichier Excel
        df_groupement.to_excel(group_dir / f"{group}.xlsx", index=False)

def export_tables_as_pdf(groups, merge_dir):
    for group in groups:
        group_dir = merge_dir / str(group)
        df_g = pd.read_excel(group_dir / f"{group}.xlsx")
        export_table_as_pdf(df_g, group_dir / f"Table_{group}.pdf")

def normalize(string):
    return str(string).replace(" ", "").replace("-", "").lower()

def compress_pdfs(pdf_files, output_dir):
    for pdf_file in pdf_files:
        doc = fitz.open(pdf_file)
        if not doc.page_count == 0:
            doc.save(output_dir / pdf_file.name, garbage=4, deflate=True)
            doc.close()


if __name__ == "__main__":
    # En gros : dans le dossier data_dir doivent se trouver : 
    # - Un dossier input dans lequel il doit y avoir "factures details.xlsx", 
    # et des dossiers/sous dossiers peu importe avec les .pdf unitaires + les pdf de regroupement
    # L'arboresence de input et le chemin des pdf importe peu tant que le xslx est à la racine
    # Chemin du dossier principal contenant les factures unitaires
    # RENTRER LE NOM DU DOSSIER ICI
    # data_dir = "~/data/enargia/multisite_legacy/test_data"
    # data_dir = "~/data/enargia/multisite/bordereau"
    

    parser = argparse.ArgumentParser(description="Définir le répertoire de données")
    parser.add_argument("data_dir", type=str, help="Le chemin du répertoire de données")
    args = parser.parse_args()
    
    data_dir = args.data_dir

    data_dir = Path(data_dir).expanduser()
    output_dir = data_dir / "output" / "extract"
    output_dir.mkdir(exist_ok=True, parents=True)
    merge_dir = data_dir / "output" / "merge"
    merge_dir.mkdir(exist_ok=True, parents=True)
    res_dir = data_dir / "output" / "results"
    res_dir.mkdir(exist_ok=True, parents=True)

    logger.info("Défusionnage des factures globales...")
    # Dans chaque gros PDF : Si "Regroupement de facturation" on extrait les pages corresp
    split_global_bills(data_dir / 'input', output_dir / "regroupe")
    logger.info("Fin du défusionnage des factures globales \n")

    logger.info("Défusionnage des factures unitaires...")
    # Dans chaque gros PDF : si Référence PDL ok (aka 14 num) on extrait les pages corresp
    split_unit_bills(data_dir / 'input', output_dir / "indiv")
    logger.info("Fin du défusionnage des factures unitaires \n")

    logger.info(f"Lecture du fichier Excel 'factures details.xlsx' pour retrouver les regroupement et PDL associés")
    # Lecture des données Excel
    df = pd.read_excel(data_dir / 'input' / "factures details.xlsx", sheet_name='Sheet1')
    groups = df.groupby("groupement").filter(lambda x: len(x)>=1)["groupement"].unique()

    if "nan" in groups:
        groups = groups.remove("nan")

    # Filtrer les groupes pour n'avoir que ceux trouvés dans les factures de regroupement
    global_bills_dir = output_dir / "regroupe"
    found_groups = set([group_name_from_filename(f) for f in global_bills_dir.glob("*.pdf")])

    logger.info(found_groups)
    groups = [group for group in groups if group in found_groups]
    logger.info(groups)
    logger.info("Tri des fichiers Excel défusionnés \n")
    sort_xls_by_group(df, groups, merge_dir)

    logger.info("Export en PDF des tableurs Excel  \n")
    export_tables_as_pdf(groups, merge_dir)

    logger.info("Tri des fichiers PDF défusionnés \n")
    sort_pdfs_by_group(df, groups, output_dir / 'indiv', output_dir / 'regroupe', merge_dir)

    logger.info("Fusion des PDF par groupement")
    merged_pdf_files = merge_pdfs_by_group(groups, merge_dir)
    logger.info("Fin de la fusion")

    logger.info("Reduce PDF size")
    compress_pdfs(merged_pdf_files, res_dir)
