import os
import re
import zipfile
import tempfile
import shutil
import pymupdf

from pathlib import Path
from typing import Callable
import pandas as pd
from pandas import DataFrame

from atelier_facture.utils import pdf_utils, file_naming, pedagogie

from atelier_facture.utils import logger, setup_logger

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
        formatted_data['membre'] = file_naming.abbreviate_long_text_to_acronym(formatted_data['membre'], 15)

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
            filename = file_naming.compose_filename(data, format_type)
            
            # Définir le chemin de sauvegarde du fichier PDF
            output_path: Path = output_folder / f"{filename}.pdf"
            
            # Créer le PDF avec les pages séléctionnées
            pdf_utils.partial_pdf_copy(doc, start_page, end_page, output_path, metadata={"title": f"Facture {data['id']}"})

            transformations = [
                (pdf_utils.remplacer_texte_doc, "Votre espace client  : https://client.enargia.eus", "Votre espace client : https://suiviconso.enargia.eus"),
                (pdf_utils.caviarder_texte_doc, "Votre identifiant :", 290, 45),
            ]
            if format_type == 'groupement':
                transformations.append((pdf_utils.ajouter_ligne_regroupement_doc, data['groupement']))
            pdf_utils.apply_pdf_transformations(output_path, output_path, transformations)

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

def main():
    setup_logger(2)
    zip_path: Path  = Path("~/data/enargia/tests/test_avoir.zip").expanduser()
    output_folder: Path = Path("~/data/enargia/tests/extractioon_test").expanduser()

    # Appliquer le décorateur dynamiquement
    process_zip_with_progress = pedagogie.with_progress_bar("Découpage des pdfs...")(process_zip)
    
    # Appeler la fonction décorée
    expected: DataFrame
    extracted: DataFrame
    expected, extracted = process_zip_with_progress(zip_path, output_folder)

if __name__ == "__main__":
    main()

