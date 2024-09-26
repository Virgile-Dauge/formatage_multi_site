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

# Try to import Rich, but have a fallback if it's not available
try:
    from rich.progress import Progress, TaskID
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.pretty import pprint
    from rich.panel import Panel
    rich_available = True
except ImportError:
    rich_available = False

# Custom logger setup
def setup_logger():
    """
    Set up and return a logger, using Rich if available, otherwise using basic logging.

    Returns:
        logging.Logger: Configured logger object.
    """
    if rich_available:
        logging.basicConfig(
            level="INFO",
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True)]
        )
        logger = logging.getLogger("rich")
    else:
        logging.basicConfig(
            level="INFO",
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="[%X]"
        )
        logger = logging.getLogger("basic")
    
    return logger

# Global logger
logger = setup_logger()

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

def split_pdf(pdf_file_path: Path, output_dir: Path, regex_dict, start_keyword: str="www.enargia.eus", ) -> tuple[list[Path], list[Path], Path]:
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
    
    # Ouvrir le fichier PDF
    try:
        reader = PdfReader(pdf_file_path)
    except EmptyFileError as e:
        logger.error(f"Erreur : {e} '{pdf_file_path}'")
        return group, indiv, [pdf_file_path]
    
    
    def save_current_pdf() -> None:
        nonlocal writer, group, indiv
        if not writer:
            return
        
        if group_name and date and client_name:
            output_pdf_path = output_dir / 'group' / f"{date}-{client_name} - {group_name}.pdf"
            group.append(output_pdf_path)
        elif pdl_name and date and client_name:
            output_pdf_path = output_dir / 'indiv' / f"{date}-{client_name} - {pdl_name}.pdf"
            indiv.append(output_pdf_path)
        else:
            logger.warning(f"Unable to categorize PDF. date: {date}, client_name: {client_name}, group_name: {group_name}, pdl_name: {pdl_name}")
            return
        
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
                save_current_pdf()

            writer = PdfWriter()
            writer.add_page(page)

            # Extract invoice number
            invoice_match = re.search(regex_dict['invoice_id'], text)
            if invoice_match:
                invoice_number = invoice_match.group(1)
                # Convert invoice number to bytes and pad or truncate to 16 bytes
                id_bytes = invoice_number.encode('utf-8')[:16].ljust(16, b'\0')
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
                client_name = client_name_match.group(1).strip().replace(" ", "_")  # Remplace les espaces par "_"

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

def split_pdfs(input_dir: Path, output_dir: Path, regex_dict, progress_callback=None) -> tuple[list[Path], list[Path], list[Path]]:
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
    total_pdfs = len(pdfs)
    logger.info(f"{total_pdfs} pdfs détectés dans {input_dir}")
    groups = []
    indivs = []
    errors = []
    for i, pdf in enumerate(pdfs):
        group, indiv, error = split_pdf(pdf, output_dir, regex_dict=regex_dict)
        groups += group
        indivs += indiv
        errors += error
        if progress_callback:
            progress_callback(i + 1, total_pdfs)

    return groups, indivs, errors

def rich_progress_callback(progress: Progress, task: TaskID):
    """
    Progress callback for Rich progress bar.
    """
    def update(current: int, total: int):
        progress.update(task, completed=current, total=total)
    return update

def simple_progress_callback(i: int, total: int):
    """
    Simple console progress callback.
    """
    logging.info(f'Traitement des PDF : {i}/{total} ({i/total:.1%})')

def process_and_split_pdfs(input_path: Path, output_dir: Path, regex_dict):
    """
    Extract PDFs from nested zip files, process them, and clean up.

    Args:
        input_path (Path): Path to the input zip file or directory.
        output_dir (Path): Path to the output directory.
        regex_dict (dict): Dictionary of regex patterns.

    Returns:
        tuple: Lists of group PDFs, individual PDFs, and errors.
    """
    logger.info(f"Starting to process input from {input_path}")
    temp_dir = extract_nested_pdfs(input_path)
    
    try:
        if rich_available:
            with Progress() as progress:
                task = progress.add_task("[green]Traitement des PDF...", total=None)
                callback = rich_progress_callback(progress, task)
                return split_pdfs(temp_dir, output_dir, regex_dict, callback)
        else:
            return split_pdfs(temp_dir, output_dir, regex_dict, simple_progress_callback)
    finally:
        shutil.rmtree(temp_dir)  # Clean up temp directory
        logger.info("Temporary directory cleaned up")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Split PDF files based on specific patterns.")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input ZIP file containing PDF files")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output directory for split PDF files")
    args = parser.parse_args()
    input_zip = Path(args.input)
    output_dir = Path(args.output)

    output_dir.mkdir(parents=True, exist_ok=True)

    regex_dict = {
        'date': r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})',
        'client_name': r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)',
        'group_name': r'Regroupement de facturation\s*:\s*\((.*?)\)',
        'pdl': r'Référence PDL : (\d{14})',
        'invoice_id': r'N° de facture\s*:\s*(\d{14})'
    }
    console = Console()
    groups, indivs, errors = process_and_split_pdfs(input_zip, output_dir, regex_dict)
    console.print(Panel.fit(
        f"[green]Processing complete![/green]\n"
        f"Group PDFs: {len(groups)}\n"
        f"Individual PDFs: {len(indivs)}\n"
        f"Errors: {len(errors)}",
        title="Results",
        border_style="bold"
    ))

    if errors:
        console.print("[yellow]The following files encountered errors:[/yellow]")
        for error in errors:
            console.print(f"  - {error}")

if __name__ == "__main__":
    main()

