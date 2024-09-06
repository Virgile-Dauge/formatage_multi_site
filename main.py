import re
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

# Regex patterns pour extraire les informations
date_pattern = r'VOTRE FACTURE DU (\d{2})\/(\d{2})\/(\d{4})'
client_name_pattern = r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)'
group_name_pattern = r'Regroupement de facturation\s*:\s*\((.*?)\)'
group_name_pattern = r'Regroupement de facturation\s*:\s*\(([\s\S]*?)\)'
pdl_pattern = r'Référence PDL : (\d{14})'

def safe_extract_text(page):
    try:
        return page.extract_text()
    except AttributeError as e:
        print(f"Error extracting text from page: {e}")
        return None

def split_pdf(pdf_file_path, output_dir="output_pdfs",  start_keyword="www.enargia.eus", regex_dict=None) -> tuple[list[Path], list[Path], Path]:
    indiv = []
    group = []
    # Ouvrir le fichier PDF
    try:
        reader = PdfReader(pdf_file_path)
        # Continuez avec le reste du traitement
    except EmptyFileError as e:
        logger.error(f"Erreur : {e} '{pdf_file_path}'")
        return group, indiv, [pdf_file_path]
    #reader = PdfReader(pdf_file_path)
    num_pages = len(reader.pages)
    writer = None

    date = None
    client_name = None
    group_name = None
    pdl_name = None
    (output_dir / 'group').mkdir(exist_ok=True, parents=True)
    (output_dir / 'indiv').mkdir(exist_ok=True, parents=True)

    for i in range(num_pages):
        page = reader.pages[i]
        text = safe_extract_text(page)
        if text is None:
            logger.error(f"Impossible d'extraire le texte de la page {i} de {pdf_file_path} Arrêt de l'exécution.")
            return group, indiv, [pdf_file_path]

        # Rechercher le mot-clé indiquant le début d'un nouveau sous-PDF
        if start_keyword in text:
            if writer:
                # Enregistrer le PDF précédent avant de commencer un nouveau
                if group_name and date and client_name:
                    output_pdf_path = output_dir / 'group' / f"{date}-{client_name} - {group_name}.pdf"
                    group += [output_pdf_path]
                elif pdl_name and date and client_name:
                    output_pdf_path = output_dir / 'indiv' / f"{date}-{client_name} - {pdl_name}.pdf"
                    indiv += [output_pdf_path]
                else:
                    output_pdf_path = None
                if output_pdf_path:
                    # Enlever les métadonnées pour alléger le fichier
                    with open(output_pdf_path, "wb") as output_pdf:
                        logger.info(f"Enregistrement du PDF: {output_pdf_path}.")
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
        if group_name and date and client_name:
            output_pdf_path = output_dir / 'group' / f"{date}-{client_name} - {group_name}.pdf"
            group += [output_pdf_path]
        elif pdl_name and date and client_name:
            output_pdf_path = output_dir / 'indiv' / f"{date}-{client_name} - {pdl_name}.pdf"
            indiv += [output_pdf_path]
        else:
            output_pdf_path = None
        if output_pdf_path:
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)
                
    return group, indiv, []

def split_pdfs(input_dir: Path, output_dir: Path, regex_dict) -> tuple[list[Path], list[Path], list[Path]]:
    """
    Cette fonction divise les fichiers PDF trouvés dans le répertoire d'entrée en fonction des expressions régulières fournies.
    
    Paramètres:
    input_dir (Path): Le répertoire contenant les fichiers PDF à traiter.
    output_dir (Path): Le répertoire où les fichiers PDF divisés seront enregistrés.
    regex_dict (dict): Un dictionnaire contenant les motifs regex pour extraire les informations nécessaires des PDF.
    
    Retourne:
    tuple: Trois listes contenant respectivement les chemins des fichiers PDF de groupe, les chemins des fichiers PDF individuels et les erreurs rencontrées.
    """
    pdfs = list(input_dir.rglob('*.pdf'))
    logger.info(f"{len(pdfs)} pdfs détectés dans {input_dir}")
    groups = []
    indivs = []
    errors = []
    for pdf in pdfs:
        group, indiv, error = split_pdf(pdf, output_dir, regex_dict=regex_dict)
        groups += group
        indivs += indiv
        errors += error
        
    return groups, indivs, errors

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
    parser = argparse.ArgumentParser(description="Définir le répertoire de données")
    parser.add_argument("data_dir", type=str, help="Le chemin du répertoire de données")
    parser.add_argument("-ec", "--extra_check", action="store_true", help="Vérifie que tous les PDLs présents dans 'lien.xlsx' sont dans les factures individuelles")
    args = parser.parse_args()
    
    data_dir = args.data_dir

    data_dir = Path(data_dir).expanduser()
    output_dir = data_dir / "output" / "extract"
    output_dir.mkdir(exist_ok=True, parents=True)
    merge_dir = data_dir / "output" / "merge"
    merge_dir.mkdir(exist_ok=True, parents=True)
    res_dir = data_dir / "output" / "results"
    res_dir.mkdir(exist_ok=True, parents=True)

    logger.info("Extraction des factures...")
    regex_dict = {"date": date_pattern, "client_name":client_name_pattern, "group_name": group_name_pattern, "pdl_name": pdl_pattern}
    group, indiv, errors = split_pdfs(data_dir / 'input', output_dir, regex_dict)
    logger.info("Fin d'extraction des factures.")
    logger.info("Factures extraites :")
    logger.info(f" - {len(set(group))} groupes")
    logger.info(f" - {len(set(indiv))} individuelles")
    if errors:
        logger.warning("Erreurs :")
        logger.warning(errors)
        errors_csv_path = data_dir / "output" / "errors.csv"
        df_errors = pd.DataFrame(errors, columns=['error'])
        df_errors.to_csv(errors_csv_path, index=False)
        logger.info(f"Les erreurs ont été enregistrées dans {errors_csv_path}")


    logger.info(f"Lecture du fichier Excel 'lien.xlsx' pour retrouver les regroupement et PDL associés")
    if not (data_dir / 'input' / "lien.xlsx").exists():
        logger.warning("Le fichier 'lien.xlsx' est introuvable. Arrêt de l'exécution.")
        sys.exit(0)
        
    # Lecture des données Excel
    df = pd.read_excel(data_dir / 'input' / "lien.xlsx", sheet_name='Sheet1')
    
    
    if args.extra_check:
        logger.info("Vérification des PDLs dans 'lien.xlsx' par rapport aux factures individuelles...")
        pdl_in_lien = set(df["PRM"].astype(str))
        pdl_in_indiv = set()
        pdl_pattern = r'(\d{14})'
        pdl_in_indiv = {re.search(pdl_pattern, pdf_path.stem).group(1) for pdf_path in (output_dir / 'indiv').glob("*.pdf") if re.search(pdl_pattern, pdf_path.stem)}
        missing_pdls = pdl_in_lien - pdl_in_indiv
        if missing_pdls:
            logger.warning(f"Les PDLs suivants sont manquants dans les factures individuelles: {missing_pdls}")
            missing_pdls_file = data_dir / "output" / "missing_pdls.csv"
            df_missing_pdls = df[df["PRM"].astype(str).isin(missing_pdls)]
            df_missing_pdls.to_csv(missing_pdls_file, index=False)
            logger.info(f"Les PDLs manquants ont été enregistrés dans {missing_pdls_file}")
        else:
            logger.info("Tous les PDLs présents dans 'lien.xlsx' sont dans les factures individuelles.")
    
    groups = df.groupby("groupement").filter(lambda x: len(x)>=1)["groupement"].unique()

    if "nan" in groups:
        groups = groups.remove("nan")

    # Filtrer les groupes pour n'avoir que ceux trouvés dans les factures de regroupement
    global_bills_dir = output_dir / "group"
    found_groups = set([group_name_from_filename(f) for f in global_bills_dir.glob("*.pdf")])

    logger.info(found_groups)
    groups = [group for group in groups if group in found_groups]
    logger.info(groups)
    logger.info("Tri des fichiers Excel défusionnés \n")
    sort_xls_by_group(df, groups, merge_dir)

    logger.info("Export en PDF des tableurs Excel  \n")
    export_tables_as_pdf(groups, merge_dir)

    logger.info("Tri des fichiers PDF défusionnés \n")
    sort_pdfs_by_group(df, groups, output_dir / 'indiv', output_dir / 'group', merge_dir)

    logger.info("Fusion des PDF par groupement")
    merged_pdf_files = merge_pdfs_by_group(groups, merge_dir)
    logger.info("Fin de la fusion")

    logger.info("Reduce PDF size")
    compress_pdfs(merged_pdf_files, res_dir)
