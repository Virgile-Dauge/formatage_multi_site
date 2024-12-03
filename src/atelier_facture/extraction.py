import os
import re
import zipfile
import tempfile
import shutil
import pymupdf

from pypdf import PdfReader, PdfWriter, PageObject
from pypdf.generic import ArrayObject, ByteStringObject
from pypdf.errors import EmptyFileError
from pathlib import Path
from typing import Callable, Any
import pandas as pd
from pandas import DataFrame

from pdf_utils import remplacer_texte_doc, caviarder_texte_doc, ajouter_ligne_regroupement_doc, apply_pdf_transformations, partial_pdf_copy
from file_naming import compose_filename, abbreviate_long_text_to_acronym
from pedagogie import with_progress_bar, rapport_extraction

from logger_config import logger, setup_logger
def extract_nested_pdfs(input_path: Path) -> Path:
    """
    Extracts all PDFs from nested zip files to a temporary directory.
    
    Args:
    input_path (Path): Path to the input zip file or directory.
    
    Returns:
    Path: Path to the temporary directory containing all extracted PDFs.
    """
    temp_dir = Path(tempfile.mkdtemp())
    
    def extract_zip(zip_path, extract_to):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file in zip_ref.namelist():
                if file.lower().endswith('.pdf'):
                    zip_ref.extract(file, extract_to)
                elif file.lower().endswith('.zip'):
                    nested_zip = extract_to / file
                    zip_ref.extract(file, extract_to)
                    extract_zip(nested_zip, extract_to)
                    os.remove(nested_zip)  # Remove the nested zip after extraction

    if input_path.is_file() and input_path.suffix.lower() == '.zip':
        extract_zip(input_path, temp_dir)
    elif input_path.is_dir():
        for item in input_path.glob('**/*'):
            if item.is_file():
                if item.suffix.lower() == '.pdf':
                    shutil.copy(item, temp_dir)
                elif item.suffix.lower() == '.zip':
                    extract_zip(item, temp_dir)
    else:
        raise ValueError(f"Input path {input_path} is neither a zip file nor a directory")

    return temp_dir

def extract_root_level_csv_xlsx(
    input_path: Path,
    csv_dir: Path,
    xlsx_dir: Path
) -> tuple[list[str], list[str]]:
    """
    Extract root-level CSV and XLSX files from a ZIP file.

    Args:
        input_path (Path): Path to the input ZIP file.
        csv_dir (Path): Directory to save extracted CSV files.
        xlsx_dir (Path): Directory to save extracted XLSX files.

    Returns:
        Tuple[List[str], List[str]]: Lists of extracted CSV and XLSX file paths.
    """
    csvs = []
    xlsxs = []

    if not zipfile.is_zipfile(input_path):
        return csvs, xlsxs
    
    # Create output directories if they don't exist
    csv_dir.mkdir(parents=True, exist_ok=True)
    xlsx_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(input_path, 'r') as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith('.csv') and '/' not in file:
                zip_ref.extract(file, csv_dir)
                csvs.append(str(csv_dir / file))
            elif file.endswith('.xlsx') and '/' not in file:
                zip_ref.extract(file, xlsx_dir)
                xlsxs.append(str(xlsx_dir / file))

    return csvs, xlsxs

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

def split_pdf(pdf_file_path: Path, indiv_dir: Path, group_dir: Path, 
              regex_dict, start_keyword: str="www.enargia.eus", ) -> tuple[list[Path], list[Path], list[Path]]:
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
    required_keys = ['date', 'client_name', 'group_name', 'pdl', 'invoice_id']
    assert set(required_keys).issubset(set(regex_dict.keys())), f"Missing required keys: {set(required_keys) - set(regex_dict.keys())}"

    indiv = []
    group = []
    meta = []
    
    # Ouvrir le fichier PDF
    try:
        reader = PdfReader(pdf_file_path)
    except EmptyFileError as e:
        logger.error(f"Erreur : {e} '{pdf_file_path}'")
        return group, indiv, [pdf_file_path]
    
    
    def save_current_pdf():
        nonlocal writer, group, indiv
        if not writer:
            return
        if date is None or client_name is None or (group_name is None and pdl_name is None):
            logger.warning(f"Unable to categorize PDF. date: {date}, client_name: {client_name}, group_name: {group_name}, pdl_name: {pdl_name}")
            return
        extracted_data = {'date' : date, 'client_name' : client_name, 'group' : group_name, 'pdl' : pdl_name, 'id' : invoice_id}
        if group_name and date and client_name:
            output_pdf_path = group_dir / f"{date}-{client_name} - {group_name}.pdf"
            # TODO:
            # output_pdf_path = group_dir / compose_filename(extracted_data, format_type='group') + '.pdf'
            group.append(output_pdf_path)
        elif pdl_name and date and client_name:
            output_pdf_path = indiv_dir / f"{date}-{client_name} - {pdl_name}.pdf"
            # TODO:
            # output_pdf_path = indiv_dir / compose_filename(extracted_data, format_type='pdl') + '.pdf'
            indiv.append(output_pdf_path)
        else:
            logger.warning(f"Unable to categorize PDF. date: {date}, client_name: {client_name}, group_name: {group_name}, pdl_name: {pdl_name}")
            return
        metadata = {
            '/Title': f"Facture {invoice_id} pour {client_name}",
            '/ClientName': client_name,
            '/GroupName': group_name if group_name is not None else '',
            '/CreationDate': date,
            #'/Subject': client_name,
            '/Application': 'atelier-facture',
            #'/Keywords': group_name,  # Standard field for group name
            '/Pdl': pdl_name,
            '/InvoiceID': invoice_id,
            '/Producer': 'atelier-facture'
        }
        writer.add_metadata(metadata)
        with open(output_pdf_path, "wb") as output_pdf:
            writer.write(output_pdf)
        
        writer = None   
    def safe_extract_text(page: PageObject) -> str | None:
        """
        Extrait le texte d'une page PDF de manière sécurisée.

        Retourne:
        str: Le texte extrait de la page, ou None en cas d'erreur.
        """
        try:
            return page.extract_text()
        except AttributeError as e:
            logger.error(f"Erreur lors de l'extraction du texte de la page : {e}")
            return None

    num_pages = len(reader.pages)
    writer = None

    date = None
    client_name = None
    group_name = None
    pdl_name = None
    
    # Créer les répertoires de sortie s'ils n'existent pas
    indiv_dir.mkdir(exist_ok=True, parents=True)
    group_dir.mkdir(exist_ok=True, parents=True)

    for i in range(num_pages):
        page = reader.pages[i]
        text = safe_extract_text(page)
        if text is None:
            logger.error(f"Impossible d'extraire le texte de la page {i} de {pdf_file_path}. Arrêt de l'exécution.")
            return group, indiv, [pdf_file_path]

        # Rechercher le mot-clé indiquant le début d'un nouveau sous-PDF
        if start_keyword in text:
            if writer:
                save_current_pdf()  

            writer = PdfWriter()
            writer.add_page(page)

            # Extract invoice number
            invoice_match = re.search(regex_dict['invoice_id'], text)
            if invoice_match:
                invoice_id = invoice_match.group(1)
                # Convert invoice number to bytes and pad or truncate to 16 bytes
                id_bytes = invoice_id.encode('utf-8')[:16].ljust(16, b'\0')
                # Create PdfObject for ID
                id_object = ByteStringObject(id_bytes)
                writer._ID = ArrayObject([id_object, id_object])  # Use the same value for both array elements
            else:
                logger.warning(f"No invoice number found for {pdf_file_path}. ID not set.")
            
            # Extraire la date
            date_match = re.search(regex_dict['date'], text)
            if date_match:
                date = f"{date_match.group(3)}{date_match.group(2)}{date_match.group(1)}"

            # Extraire le nom du client
            client_name_match = re.search(regex_dict['client_name'], text)
            if client_name_match:
                client_name = client_name_match.group(1).strip().replace(" ", "_")

            # Extraire le nom du groupement
            group_name = extract_group_name(text)

            # Extraire le nom du PDL
            pdl_match = re.search(regex_dict['pdl'], text)
            if pdl_match:
                pdl_name = pdl_match.group(1)

        elif writer:
            writer.add_page(page)

    # Enregistrer le dernier PDF
    save_current_pdf()              
    return group, indiv, []

def process_zipped_pdfs(
    input_path: Path, 
    indiv_dir: Path,
    group_dir: Path, 
    regex_dict: dict[str, str],
    progress_callback: Callable[[str, int, int, str], None] | None=None
) -> tuple[list[str], list[str], list[str], DataFrame]:
    """
    Extract PDFs from nested zip files to tmp directory, process them, and clean up.

    Args:
        input_path (Path): Path to the input zip file or directory.
        indiv_dir (Path): Path to to put individual invoices.
        group_dir (Path): Path to to put grouped invoices.
        regex_dict (dict): Dictionary of regex patterns.
        progress_callback (Optional[Callable]): Function to call with progress updates.

    Returns:
        tuple: Lists of group PDFs, individual PDFs, and errors.
    """
    def update_progress(task: str, current: int, total: int, detail: str=''):
        if progress_callback:
            progress_callback(task, current, total, detail)
    
    update_progress("Extracting PDFs", 0, 1, "Starting extraction")
    temp_dir = extract_nested_pdfs(input_path)
    update_progress("Extracting PDFs", 1, 1, "Extraction complete")
    update_progress("Extracting csv and xlsx", 0, 1, "Starting extraction")
    extract_root_level_csv_xlsx(input_path, group_dir, group_dir)
    update_progress("Extracting csv and xlsx", 1, 1, "Extraction complete")
    groups = []
    indivs = []
    errors = []

    try:
        pdf_files = list(temp_dir.glob('**/*.pdf'))
        total_pdfs = len(pdf_files)

        for i, pdf in enumerate(pdf_files, 1):
            update_progress("Processing PDFs", i, total_pdfs, pdf)
            group, indiv, error = split_pdf(pdf, indiv_dir, group_dir, regex_dict=regex_dict)
            groups += group
            indivs += indiv
            errors += error

        for pdf in groups+indivs:
            transformations = [
                (remplacer_texte_doc, "Votre espace client  : https://client.enargia.eus", "Votre espace client : https://suiviconso.enargia.eus"),
                (caviarder_texte_doc, "Votre identifiant :", 290, 45),
                (ajouter_ligne_regroupement_doc,)
                # Add more transformations as needed
            ]

            apply_pdf_transformations(pdf, pdf, transformations)
        return groups, indivs, errors
    finally:
        shutil.rmtree(temp_dir)  # Clean up temp directory

def split_pdf_enhanced(pdf_path: str, output_folder: Path) -> dict[str, str]:
    """
    Sépare un fichier PDF en plusieurs fichiers en utilisant un motif regex pour identifier les sections,
    et nomme chaque fichier avec le numéro de facture extrait. Les fichiers sont sauvegardés dans un dossier spécifié
    avec un nom composé à partir des informations de la dataframe.

    :param pdf_path: Chemin du fichier PDF à traiter.
    :param regex_pattern: Motif regex pour extraire les identifiants (ex. numéros de facture).
    :param output_folder: Dossier où les fichiers PDF résultants seront sauvegardés (objet Path).
    :param dataframe: DataFrame contenant les informations composant le nom du PDF.
    """
    logger.info(f"Découpage de {pdf_path.name} :")
    # Créer le dossier de destination s'il n'existe pas
    output_folder.mkdir(parents=True, exist_ok=True)

    res: list[dict[str, str]] = []
    # Charger le PDF source avec le context manager "with"
    with pymupdf.open(pdf_path) as doc:
        # Trouver les pages qui contiennent le motif regex et extraire le numéro de facture
        split_points: list[tuple[int, str]] = []  # Liste de tuples (page_number, identifier)
        for i, page in enumerate(doc):
            extracted_data = extract_and_format_data(page.get_text())
            
            if extracted_data and 'id' in extracted_data:
                logger.debug(f'page#{i}: {extracted_data}')
                split_points.append((i, extracted_data))

        logger.info(f"{len(split_points)} factures trouvées.")
        # Ajouter la fin du document comme dernier point de séparation
        split_points.append((len(doc), None))

        # Créer des fichiers PDF distincts à partir des pages définies par les points de séparation
        for i in range(len(split_points) - 1):
            start_page, data = split_points[i]
            end_page, _ = split_points[i + 1]

            # Composer le nom de fichier
            format_type = 'pdl' if 'pdl' in data else 'groupement'
            filename = compose_filename(data, format_type)
            
            # Définir le chemin de sauvegarde du fichier PDF
            output_path: Path = output_folder / f"{filename}.pdf"
          
            # Créer le PDF avec les pages séléctionnées
            partial_pdf_copy(doc, start_page, end_page, output_path)

            transformations = [
                (remplacer_texte_doc, "Votre espace client  : https://client.enargia.eus", "Votre espace client : https://suiviconso.enargia.eus"),
                (caviarder_texte_doc, "Votre identifiant :", 290, 45),
            ]
            if format_type == 'group':
                transformations.append((ajouter_ligne_regroupement_doc, data['groupement']))
            apply_pdf_transformations(output_path, output_path, transformations)

            data['fichier_extrait'] = str(output_path)
            data['fichier_origine'] = str(pdf_path.name)
            res.append(data)
            logger.info(f"Le fichier {output_path.name} a été extrait.")

    return res

def extract_files_from_zip(zip_file_path, output_folder, to_extract=['consignes.csv', 'facturx.csv']):
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        for file_name in to_extract:
            try:
                zip_ref.extract(file_name, output_folder)
                logger.info(f"Le fichier {file_name} a été extrait avec succès.")
            except KeyError:
                logger.warning(f"Le fichier {file_name} n'a pas été trouvé dans l'archive.")


def process_zip(
    input_path: Path,
    output_dir: Path,
    files_to_extract: list[str]|None=None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[DataFrame, DataFrame]:
    
    if files_to_extract is None:
        files_to_extract = ['consignes.csv', 'facturx.csv']

    temp_dir = extract_nested_pdfs(input_path)
    read = []
    try:
        pdf_files = list(temp_dir.glob('**/*.pdf'))
        total_files = len(pdf_files)

        for i, pdf in enumerate(pdf_files, 1):
            read += split_pdf_enhanced(pdf, output_dir)
            if progress_callback:
                progress_callback(i, total_files)

        extract_files_from_zip(input_path, output_dir, files_to_extract)

        expected : Path = output_dir / files_to_extract[0]
        return pd.DataFrame(read), pd.read_csv(expected, dtype=str)
    
    finally:
        shutil.rmtree(temp_dir)  # Clean up temp directory

def extract_patterns(text: str, patterns: dict[str, str]) -> dict[str, list[str|tuple[str]]]:
    """
    Extrait les correspondances des motifs regex donnés dans le texte.

    :param text: Le texte dans lequel effectuer la recherche.
    :param patterns: Un dictionnaire où les clés sont des noms et les valeurs sont des motifs regex à rechercher.
    :return: Un dictionnaire contenant chaque clé et les correspondances trouvées, ou un dictionnaire vide s'il n'y a aucune correspondance.
    """
    matches: dict[str, list[str]] = {}
    for key, pattern in patterns.items():
        found = re.search(pattern, text, re.DOTALL)
        if found:
            matches[key] = found.groups()
    return matches

def format_extracted_data(data: dict[str, list[str|tuple[str]]]) -> dict[str, str]:
    """
    Formate les données extraites pour les rendre plus lisibles.

    :param data: Un dictionnaire contenant les données extraites.
    :return: Un dictionnaire contenant les données formatées.
    """
    formatted_data = data.copy()

    if 'date' in formatted_data:
        formatted_data['date'] = formatted_data['date'][::-1]
    
    for key, value in formatted_data.items():
        if isinstance(value, tuple):
            formatted_data[key] = ''.join(value).replace('\n', ' ')
        else:
            formatted_data[key] = value

    if 'pdl' in formatted_data and len(formatted_data['pdl']) == 9:
    #     formatted_data['id_groupement'] = formatted_data.pop('pdl')
        formatted_data.pop('pdl')
    
    if 'membre' in formatted_data:
        formatted_data['membre'] = abbreviate_long_text_to_acronym(formatted_data['membre'], 15)

    return formatted_data

def extract_and_format_data(text: str, patterns: dict[str, str]|None=None) -> dict[str, str]:
    """
    Extrait et formate les données du texte en utilisant les motifs regex donnés.

    :param text: Le texte dans lequel effectuer la recherche.
    :param patterns: Un dictionnaire où les clés sont des noms et les valeurs sont des motifs regex à rechercher.
    :return: Un dictionnaire contenant les données formatées, ou un dictionnaire vide s'il n'y a aucune correspondance.
    """
    if patterns is None:
        patterns = {'id': r"N° de facture\s*:\s*(\d{14})",
            # 'date': r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})',
            'date': r"VOTRE.*?DU\s+(\d{2})/(\d{2})/(\d{4})",
            'pdl': r'Référence PDL : (\d+)',
            'groupement': r'Regroupement de facturation\s*:\s*\((.*)\)',
            'membre': r'Nom et Prénom ou\s* Raison Sociale :\s*(.*?)(?=\n|$)'
        }
    extracted_data = extract_patterns(text, patterns)
    formatted_data = format_extracted_data(extracted_data)
    return formatted_data

def main():
    setup_logger(2)
    zip_path: Path  = Path("~/data/enargia/tests/test_avoir.zip").expanduser()
    output_folder: Path = Path("~/data/enargia/tests/extractioon_test").expanduser()

    # Appliquer le décorateur dynamiquement
    process_zip_with_progress = with_progress_bar("Découpage des pdfs...")(process_zip)
    
    # Appeler la fonction décorée
    expected: DataFrame
    extracted: DataFrame
    expected, extracted = process_zip_with_progress(zip_path, output_folder)

    # expected = pd.read_csv(output_folder / "consignes.csv", dtype=str)
    # extracted = pd.read_csv(output_folder / "extracted_data.csv", dtype=str)
    from find_tasks import detection
    detection(expected)
    # rapport_extraction(expected, extracted)

    # Filtrer les lignes de 'attendu' où 'type' est 'groupement'
    condition = (expected['type'] == 'groupement')

    expected['id'] = None
    # Fusionner les lignes avec 'groupement' comme critère
    merged_groupement = expected[condition].merge(extracted, on='groupement', how='left', suffixes=('', '_extracted'))
    expected.loc[condition, 'id'] = merged_groupement['id_extracted']

    # Fusionner les autres lignes avec 'pdl' comme critère
    merged_pdl = expected[~condition].merge(extracted, on='pdl', how='left', suffixes=('', '_extracted'))
    expected.loc[~condition, 'id'] = merged_pdl['id_extracted']
    # extracted.to_csv(output_folder / "extracted_data.csv")
    expected.to_csv(output_folder / "consignes_consolidées.csv")
# def main():
#     import argparse
#     from rich.tree import Tree
#     from rich.live import Live
#     from rich.panel import Panel
#     from rich.layout import Layout
#     from rich.console import Console
#     from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

#     parser = argparse.ArgumentParser(description="Split PDF files based on specific patterns.")
#     parser.add_argument('-i', '--input', type=str, required=True, help="Input ZIP file containing PDF files")
#     parser.add_argument('-w', '--workspace', type=str, required=True, help="Output workspace directory for split PDF files")
#     args = parser.parse_args()
#     input_zip = Path(args.input)
#     workspace_dir = Path(args.workspace)

#     workspace_dir.mkdir(parents=True, exist_ok=True)

#     regex_dict = {
#         'date': r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})',
#         'client_name': r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)',
#         'group_name': r'Regroupement de facturation\s*:\s*\((.*?)\)',
#         'pdl': r'Référence PDL : (\d{14})',
#         'invoice_id': r'N° de facture\s*:\s*(\d{14})'
#     }
    
#     def text_progress_handler(task: str, current: int, total: int):
#         if task == "Extracting PDFs":
#             print("Extraction complete")
#         elif task == "Processing PDFs":
#             print(f"Processing PDF {current}/{total}")
#         elif task == "Cleanup":
#             print("Cleanup complete")


#     console = Console()

#     def create_progress_handler():
#         progress = Progress(
#             SpinnerColumn(),
#             TextColumn("[progress.description]{task.description}"),
#             BarColumn(),
#             TaskProgressColumn(),
#             console=console,
#         )
#         extract_task = None
#         process_task = None

#         def progress_handler(task: str, current: int, total: int):
#             nonlocal extract_task, process_task

#             if task == "Extracting PDFs":
#                 console.print("[green]Extracting PDFs")
#             elif task == "Processing PDFs":
#                 if current == 1:  # Start a new progress bar for processing
#                     process_task = progress.add_task("[green]Processing PDFs", total=total)
#                     progress.start()
#                 if process_task is not None:
#                     progress.update(process_task, completed=current)
#                 if current == total:
#                     progress.stop()
#             elif task == "Cleanup":
#                 console.print("[green]Cleanup complete")

#         return progress_handler
#     indiv_dir = workspace_dir / 'indiv'
#     group_dir = workspace_dir / input_zip.stem
#     # Use the progress handler in your main code
#     progress_handler = create_progress_handler()
#     group_pdfs, individual_pdfs, errors = process_zipped_pdfs(
#         input_zip, indiv_dir, group_dir, regex_dict, progress_callback=progress_handler
#     )
#         # Create a panel with the resulting information
#     result_panel = Panel(
#         f"""
#         [bold green]Processing Results:[/bold green]
#         Workspace Directory: {workspace_dir}
#         Number of Group PDFs: {len(group_pdfs)}
#         Number of Individual PDFs: {len(individual_pdfs)}
#         Number of Errors: {len(errors)}
#         """,
#         title="Summary",
#         # expand=False,
#         # border_style="green",
#     )

#     # Display the panel
#     console.print(result_panel)
if __name__ == "__main__":
    main()

