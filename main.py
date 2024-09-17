import os
import re
import logging
from pypdf import PdfReader, PdfWriter
from pypdf.errors import EmptyFileError
from pypdf import PageObject
import argparse
from pathlib import Path
import pandas as pd
from pandas import DataFrame
import sys
import shutil
import fitz

from pdf_utils import ajouter_ligne_regroupement
from mpl import export_table_as_pdf

from rich.logging import RichHandler
from rich.pretty import pprint

# Configuration du logger pour utiliser Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger()

# Regex patterns pour extraire les informations
date_pattern = r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})'
client_name_pattern = r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)'
pdl_pattern = r'Référence PDL : (\d{14})'

def extract_group_name(text: str) -> str | None:
    """
    Extrait le nom du groupe à partir d'un texte donné en recherchant une expression spécifique.

    Cette fonction utilise une expression régulière pour trouver le texte entre parenthèses après 
    "Regroupement de facturation :". Elle gère également les parenthèses imbriquées.

    Paramètres:
    text (str): Le texte à analyser.

    Retourne:
    str: Le nom du groupe extrait du texte, ou None si le motif n'est pas trouvé.
    """
    # Regex pour trouver le début de la parenthèse
    pattern = r'Regroupement de facturation\s*:\s*\('
    match = re.search(pattern, text)
    
    if match:
        start = match.end()  # Fin du match pour le début de la parenthèse
        parentheses_count = 1
        end = start
        
        # On parcourt la chaîne à partir de la première parenthèse pour trouver la fermeture correspondante
        while parentheses_count > 0 and end < len(text):
            if text[end] == '(':
                parentheses_count += 1
            elif text[end] == ')':
                parentheses_count -= 1
            end += 1
        
        # Retourner le contenu à l'intérieur des parenthèses imbriquées
        return text[start:end-1].strip().replace('\n', ' ')
    return None

def copy_pdf(source: Path, dest: Path):
    """
    Copie les fichiers PDF d'un répertoire source vers un répertoire de destination.

    Cette fonction vérifie d'abord l'existence des répertoires source et destination, 
    puis copie les fichiers PDF du répertoire source qui ne sont pas déjà présents 
    dans le répertoire de destination.

    Paramètres:
    source (Path): Le chemin du répertoire source contenant les fichiers PDF à copier.
    dest (Path): Le chemin du répertoire de destination où les fichiers PDF seront copiés.

    Retourne:
    None
    """

    source.mkdir(exist_ok=True, parents=True)
    factures_unitaires = list(source.glob('*.pdf'))

    dest.mkdir(exist_ok=True, parents=True)
    factures_dest = set(dest.glob('*.pdf'))

    to_copy = [f for f in factures_unitaires if f not in factures_dest]
    if to_copy:
        logger.info(f"Copie de {len(to_copy)} factures indiv depuis : {source_unitaires_dir}")
        for file in to_copy:
            shutil.copy(file, dest / file.name)
    
def safe_extract_text(page: PageObject) -> str | None:
    """
    Extrait le texte d'une page PDF de manière sécurisée.

    Paramètres:
    page (Page): La page PDF dont le texte doit être extrait.

    Retourne:
    str: Le texte extrait de la page, ou None en cas d'erreur.
    """
    try:
        return page.extract_text()
    except AttributeError as e:
        logger.error(f"Erreur lors de l'extraction du texte de la page : {e}")
        return None

def split_pdf(pdf_file_path: Path, output_dir: Path,  start_keyword: str="www.enargia.eus", regex_dict=None) -> tuple[list[Path], list[Path], Path]:
    """
    Divise un fichier PDF en plusieurs sous-PDF basés sur un mot-clé de début de pdf.

    Paramètres:
    - pdf_file_path (Path): Le chemin du fichier PDF à diviser.
    - output_dir (Path): Le répertoire où les sous-PDF seront enregistrés.
    - start_keyword (str): Le mot-clé indiquant le début d'un nouveau sous-PDF. Par défaut "www.enargia.eus".
    - regex_dict (dict, optionnel): Un dictionnaire contenant des motifs regex pour extraire des informations spécifiques du texte PDF.

    Retourne:
    - tuple: Trois listes contenant respectivement les chemins des fichiers PDF de groupe, les chemins des fichiers PDF individuels et les erreurs rencontrées.
    """
    indiv = []
    group = []
    
    # Ouvrir le fichier PDF
    try:
        reader = PdfReader(pdf_file_path)
    except EmptyFileError as e:
        logger.error(f"Erreur : {e} '{pdf_file_path}'")
        return group, indiv, [pdf_file_path]
    
    num_pages = len(reader.pages)
    writer = None

    date = None
    client_name = None
    group_name = None
    pdl_name = None
    
    # Créer les répertoires de sortie s'ils n'existent pas
    (output_dir / 'group').mkdir(exist_ok=True, parents=True)
    (output_dir / 'indiv').mkdir(exist_ok=True, parents=True)

    for i in range(num_pages):
        page = reader.pages[i]
        text = safe_extract_text(page)
        if text is None:
            logger.error(f"Impossible d'extraire le texte de la page {i} de {pdf_file_path}. Arrêt de l'exécution.")
            return group, indiv, [pdf_file_path]

        # Rechercher le mot-clé indiquant le début d'un nouveau sous-PDF
        if start_keyword in text:
            if writer:
                # Enregistrer le PDF précédent avant de commencer un nouveau
                if group_name and date and client_name:
                    output_pdf_path = output_dir / 'group' / f"{date}-{client_name} - {group_name}.pdf"
                    group.append(output_pdf_path)
                elif pdl_name and date and client_name:
                    output_pdf_path = output_dir / 'indiv' / f"{date}-{client_name} - {pdl_name}.pdf"
                    indiv.append(output_pdf_path)
                else:
                    output_pdf_path = None
                
                if output_pdf_path:
                    # Enlever les métadonnées pour alléger le fichier
                    with open(output_pdf_path, "wb") as output_pdf:
                        logger.debug(f"Enregistrement du PDF: {output_pdf_path}.")
                        writer.write(output_pdf)
                writer = None

            # Créer un nouveau writer pour le prochain sous-PDF
            writer = PdfWriter()
            writer.add_page(page)

            # Extraire la date
            date_match = re.search(date_pattern, text)
            if date_match:
                date = f"{date_match.group(3)}{date_match.group(2)}{date_match.group(1)}"

            # Extraire le nom du client
            client_name_match = re.search(client_name_pattern, text)
            if client_name_match:
                client_name = client_name_match.group(1).strip().replace(" ", "_")  # Remplace les espaces par "_"

            # Extraire le nom du groupement
            group_name = extract_group_name(text)

            # Extraire le nom du PDL
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
            group.append(output_pdf_path)
        elif pdl_name and date and client_name:
            output_pdf_path = output_dir / 'indiv' / f"{date}-{client_name} - {pdl_name}.pdf"
            indiv.append(output_pdf_path)
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
        group_dir.mkdir(exist_ok=True)
        
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

def create_grouped_invoices(df: DataFrame, group_dir: Path, merge_dir: Path) -> list[Path]:
    """
    Crée des factures groupées à partir des données fournies.

    Paramètres:
    df (DataFrame): Le DataFrame contenant les données des factures.
    group_dir (Path): Le chemin vers le répertoire contenant les factures de regroupement.
    merge_dir (Path): Le chemin vers le répertoire où les factures groupées seront enregistrées.

    Retourne:
    list[Path]: Une liste des chemins des fichiers PDF fusionnés.
    """
    # Détecter les groupes avec plusieurs PDLs
    groups = df.groupby("groupement").filter(lambda x: len(x) > 1)["groupement"].unique()

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
    sort_pdfs_by_group(df, source_unitaires_dir, group_dir, merge_dir)

    logger.info("Fusion des PDF par groupement")
    merged_pdf_files = merge_pdfs_by_group(groups, merge_dir)
    logger.info("└── Fin de la fusion")
    
    return merged_pdf_files

def normalize(string: str) -> str:
    return str(string).replace(" ", "").replace("-", "").lower()

def compress_pdfs(pdf_files: list[Path], output_dir: Path):
    """
    Compresse une liste de fichiers PDF et les enregistre dans un répertoire de sortie.

    Paramètres:
    pdf_files (list[Path]): Liste des chemins des fichiers PDF à compresser.
    output_dir (Path): Chemin du répertoire où les fichiers PDF compressés seront enregistrés.
    """
    for pdf_file in pdf_files:
        doc = fitz.open(pdf_file)
        if not doc.page_count == 0:
            doc.save(output_dir / pdf_file.name, garbage=4, deflate=True)
            doc.close()
            
def check_missing_pdl(df: DataFrame, pdl_dir: Path) -> set[str]:
    """
    Vérifie que tous les PDLs présents dans 'lien.xlsx' sont dans les factures individuelles.

    Paramètres:
    df (DataFrame): Le dataframe contenant les informations des PDLs.
    pdl_dir (Path): Le chemin vers le répertoire contenant les factures individuelles.

    Retourne:
    set[str]: Un ensemble de PDLs manquants dans les factures individuelles.
    """
    logger.info("Vérification que tous les PDLs présents dans 'lien.xlsx' sont dans les factures individuelles.")
    pdl_in_lien = set(df["PRM"].astype(str))
    #pdl_in_sources = set()
    pdl_pattern = r'(\d{14})'
    pdl_in_sources = {re.search(pdl_pattern, pdf_path.stem).group(1) for pdf_path in pdl_dir.glob("*.pdf") if re.search(pdl_pattern, pdf_path.stem)}
    missing_pdls = pdl_in_lien - pdl_in_sources
    if missing_pdls:
        logger.warning(f"└── Les PDLs suivants sont manquants dans les factures individuelles: {missing_pdls}")
        missing_pdls_file = data_dir / "output" / "missing_pdls.csv"
        df_missing_pdls = df[df["PRM"].astype(str).isin(missing_pdls)]
        df_missing_pdls.to_csv(missing_pdls_file, index=False)
        logger.info(f"    └── Les PDLs manquants ont été enregistrés dans {missing_pdls_file}")
        
    else:
        logger.info("└── Tous les PDLs présents dans 'lien.xlsx' sont dans les factures individuelles.")
    return missing_pdls

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Définir le répertoire de données")
    parser.add_argument("data_dir", type=str, help="Le chemin du répertoire de données")
    parser.add_argument("-ec", "--extra_check", action="store_true", help="Vérifie que tous les PDLs présents dans 'lien.xlsx' sont dans les factures individuelles")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Augmente le niveau de verbosité (utilisez -v ou -vv pour plus de détails)")
    args = parser.parse_args()

    # Configurer le niveau de verbosité
    if args.verbose == 1:
        logger.setLevel(logging.INFO)
    elif args.verbose >= 2:
        logger.setLevel(logging.DEBUG)
    
    # définition de l'arborescence
    data_dir = args.data_dir

    data_dir = Path(data_dir).expanduser()
    
    source_unitaires_dir = data_dir.parent / 'source_unitaires'
    
    input_dir = data_dir / 'input'
    output_dir = data_dir / 'output' 
    
    extract_dir = output_dir / 'extract'
    indiv_dir = extract_dir / 'indiv'
    group_dir = extract_dir / 'group'
    
    merge_dir = output_dir / 'merge'
    
    res_dir = output_dir / 'results'
    
    indiv_dir.mkdir(exist_ok=True, parents=True)
    group_dir.mkdir(exist_ok=True, parents=True)
    merge_dir.mkdir(exist_ok=True, parents=True)
    res_dir.mkdir(exist_ok=True, parents=True)
    
    source_unitaires_dir.mkdir(exist_ok=True, parents=True)
    
    
    # Extraction
    logger.info("Extraction des factures...")
    # regex_dict = {"date": date_pattern, "client_name":client_name_pattern, "group_name": group_name_pattern, "pdl_name": pdl_pattern}
    regex_dict = {"date": date_pattern, "client_name":client_name_pattern, "pdl_name": pdl_pattern}
    group, indiv, errors = split_pdfs(input_dir, extract_dir, regex_dict)
    logger.info("└── Factures extraites :")
    logger.info(f"     - {len(set(group))} groupes")
    logger.info(f"     - {len(set(indiv))} individuelles")
    if errors:
        logger.warning("Erreurs :")
        logger.warning(errors)
        errors_csv_path = output_dir / "errors.csv"
        df_errors = pd.DataFrame(errors, columns=['error'])
        df_errors.to_csv(errors_csv_path, index=False)
        logger.info(f"Les erreurs ont été enregistrées dans {errors_csv_path}")

    # On consolide le dossier des factures unitaires 
    # en y copiant les nouvelles factures unitaires
    for file in indiv_dir.glob('*.pdf'):
        if not (source_unitaires_dir / file.name).exists():
            shutil.copy(file, source_unitaires_dir / file.name)

    logger.info(f"Lecture du fichier Excel 'lien.xlsx' pour retrouver les regroupement et PDL associés")
    if not (data_dir / 'input' / "lien.xlsx").exists():
        logger.warning("└── Le fichier 'lien.xlsx' est introuvable. Arrêt de l'exécution.")
        sys.exit(0)
        
    # Lecture des données Excel
    df = pd.read_excel(data_dir / 'input' / "lien.xlsx", sheet_name='Sheet1')
    
    # Remplacer les tirets moyens par des tirets courts
    df = df.replace('–', '-', regex=True)
    
    if args.extra_check:
        check_missing_pdl(df, source_unitaires_dir)
    
    # Détecter les groupes qui n'ont qu'une seule ligne dans df
    single_line_groups = df.groupby("groupement").filter(lambda x: len(x) == 1)["groupement"].unique()
    if "nan" in single_line_groups:
        single_line_groups = single_line_groups.remove("nan")
    
    #single_line_groups = [g for g in single_line_groups if g in found_groups]
    logger.info(f"Groupes avec une seule ligne : {single_line_groups}")
    
    matching_files_dict = {
        g: [file for file in source_unitaires_dir.glob(f"*{df[df['groupement'] == g]['PRM'].values[0]}*.pdf")][0]
        for g in single_line_groups
    }

    for g, f in matching_files_dict.items():
        ajouter_ligne_regroupement(f, f'Regroupement de facturation : ({g})')
    
    merged_pdf_files = create_grouped_invoices(df=df, group_dir=group_dir, merge_dir=merge_dir)

    logger.info("Reduce PDF size")
    compress_pdfs(merged_pdf_files, res_dir)
