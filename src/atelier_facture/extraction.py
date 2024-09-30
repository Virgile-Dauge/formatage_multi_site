import os
import re
import logging
import zipfile
import tempfile
import shutil

from pypdf import PdfReader, PdfWriter, PageObject
from pypdf.generic import ArrayObject, ByteStringObject
from pypdf.errors import EmptyFileError
from pathlib import Path
from typing import Callable, Any
from pandas import DataFrame

logger = logging.getLogger(__name__)

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
        
        if group_name and date and client_name:
            output_pdf_path = group_dir / f"{date}-{client_name} - {group_name}.pdf"
            group.append(output_pdf_path)
        elif pdl_name and date and client_name:
            output_pdf_path = indiv_dir / f"{date}-{client_name} - {pdl_name}.pdf"
            indiv.append(output_pdf_path)
        else:
            logger.warning(f"Unable to categorize PDF. date: {date}, client_name: {client_name}, group_name: {group_name}, pdl_name: {pdl_name}")
            return
        metadata = {
            '/Title': f"Facture {invoice_id} pour {client_name}",
            '/ClientName': client_name,
            '/GroupName': group_name,
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

        return groups, indivs, errors
    finally:
        shutil.rmtree(temp_dir)  # Clean up temp directory

def main():
    import argparse
    from rich.tree import Tree
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

    parser = argparse.ArgumentParser(description="Split PDF files based on specific patterns.")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input ZIP file containing PDF files")
    parser.add_argument('-w', '--workspace', type=str, required=True, help="Output workspace directory for split PDF files")
    args = parser.parse_args()
    input_zip = Path(args.input)
    workspace_dir = Path(args.workspace)

    workspace_dir.mkdir(parents=True, exist_ok=True)

    regex_dict = {
        'date': r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})',
        'client_name': r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)',
        'group_name': r'Regroupement de facturation\s*:\s*\((.*?)\)',
        'pdl': r'Référence PDL : (\d{14})',
        'invoice_id': r'N° de facture\s*:\s*(\d{14})'
    }
    
    def text_progress_handler(task: str, current: int, total: int):
        if task == "Extracting PDFs":
            print("Extraction complete")
        elif task == "Processing PDFs":
            print(f"Processing PDF {current}/{total}")
        elif task == "Cleanup":
            print("Cleanup complete")


    console = Console()

    def create_progress_handler():
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )
        extract_task = None
        process_task = None

        def progress_handler(task: str, current: int, total: int):
            nonlocal extract_task, process_task

            if task == "Extracting PDFs":
                console.print("[green]Extracting PDFs")
            elif task == "Processing PDFs":
                if current == 1:  # Start a new progress bar for processing
                    process_task = progress.add_task("[green]Processing PDFs", total=total)
                    progress.start()
                if process_task is not None:
                    progress.update(process_task, completed=current)
                if current == total:
                    progress.stop()
            elif task == "Cleanup":
                console.print("[green]Cleanup complete")

        return progress_handler
    indiv_dir = workspace_dir / 'indiv'
    group_dir = workspace_dir / input_zip.stem
    # Use the progress handler in your main code
    progress_handler = create_progress_handler()
    group_pdfs, individual_pdfs, errors = process_zipped_pdfs(
        input_zip, indiv_dir, group_dir, regex_dict, progress_callback=progress_handler
    )
        # Create a panel with the resulting information
    result_panel = Panel(
        f"""
        [bold green]Processing Results:[/bold green]
        Workspace Directory: {workspace_dir}
        Number of Group PDFs: {len(group_pdfs)}
        Number of Individual PDFs: {len(individual_pdfs)}
        Number of Errors: {len(errors)}
        """,
        title="Summary",
        # expand=False,
        # border_style="green",
    )

    # Display the panel
    console.print(result_panel)
if __name__ == "__main__":
    main()

