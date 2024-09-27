import re
import logging


import argparse
from pathlib import Path
import pandas as pd
from pandas import DataFrame
import shutil
import fitz

from rich.console import Console
from rich.panel import Panel
from rich.logging import RichHandler

# local imports
from rich_components import process_with_rich_progress, rich_status_table, rich_directory_tree 
from fusion import create_grouped_invoices
# Configuration du logger pour utiliser Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger()

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

def main():
    parser = argparse.ArgumentParser(description="Traitement des factures")
    parser.add_argument("atelier_path", type=str, help="Chemin du répertoire atelier")
    parser.add_argument("-i", "--input_zip", type=str, help="Chemin vers le fichier zip d'entrée.")
    parser.add_argument("-ff", "--forcer_fusion", action="store_true", help="Forcer la fusion des factures même si le dossier existe déjà")
    parser.add_argument("-fz", "--forcer_zip", action="store_true", help="Forcer la création du zip même si le dossier existe déjà")
    args = parser.parse_args()
    console = Console()
    # =======================Étape 0: Définition du répertoire de travail==============
    console.print(Panel.fit("Étape 0: Définition du répertoire de travail", style="bold magenta"))
    atelier_dir = Path(args.atelier_path)
    if not atelier_dir.exists():
        console.print(f"Le répertoire atelier [bold]{atelier_dir}[/bold] n'existe pas. Création en cours...", style="yellow")
        atelier_dir.mkdir(parents=True)
    console.print(f"Répertoire de travail : [bold green]{atelier_dir}[/bold green]")

    indiv_dir = atelier_dir / "indiv"
    indiv_dir.mkdir(exist_ok=True)
    # =======================Étape 1: Traitement du zip d'entrée=======================
    console.print(Panel.fit("Étape 1: Traitement du zip d'entrée", style="bold magenta"))
    if args.input_zip:
        zip_path = Path(args.input_zip)
        
        batch_dir = atelier_dir / zip_path.stem
        batch_dir.mkdir(exist_ok=True)
        regex_dict = {
            'date': r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})',
            'client_name': r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)',
            'group_name': r'Regroupement de facturation\s*:\s*\((.*?)\)',
            'pdl': r'Référence PDL : (\d{14})',
            'invoice_id': r'N° de facture\s*:\s*(\d{14})'
        }

        group_pdfs, individual_pdfs, errors = process_with_rich_progress(zip_path, indiv_dir, batch_dir, regex_dict, console)
        #group_pdfs, individual_pdfs, errors = process_zipped_pdfs(zip_path, indiv_dir, batch_dir, regex_dict)
        console.print(f"Traitement terminé pour [bold]{zip_path}[/bold]", style="green")
        result_panel = Panel(
            f"""
            [bold green]Processing Results:[/bold green]
            Number of Group PDFs: {len(group_pdfs)}
            Number of Individual PDFs: {len(individual_pdfs)}
            Number of Errors: {len(errors)}
            """,
            title="Données extraites",
            # expand=False,
            # border_style="green",
        )

        # Display the panel
        console.print(result_panel)
    else:
        console.print("Aucun fichier d'entrée spécifié. Étape ignorée.", style="yellow")


    # =======================Étape 2: Liste des dossiers dans l'atelier================
    console.print(Panel.fit("Étape 2: Liste des dossiers dans l'atelier", style="bold magenta"))
    subdirs = [d for d in atelier_dir.iterdir() if d.is_dir() and d.name not in ['group', 'indiv']]
    console.print("Dossiers trouvés :", style="cyan")
    for d in subdirs:
        console.print(f"  - {d.name}", style="cyan")

    # =======================Étape 3 : Traitement des dossiers=========================
    batch_status = {}
    for subdir in subdirs:
        batch_status[subdir] = {'fusion': False, 'zipping': False}
        console.print(Panel.fit(f"Traitement du dossier : {subdir.name}", style="bold blue"))
        
        xlsx_file = subdir / f"{subdir.name}.xlsx"
        # ===================Étape 3A : Fusion des factures=============================
        console.print("Étape 3A : Fusion des factures", style="yellow")
        if xlsx_file.exists():
            factures_groupees_dir = subdir / "factures_groupees"
            if not any(factures_groupees_dir.glob('*.pdf')) or args.forcer_fusion:
                factures_groupees_dir.mkdir(exist_ok=True)
                df = pd.read_excel(xlsx_file, sheet_name='Sheet1')
                # Remplacer les tirets moyens par des tirets courts
                df = df.replace('–', '-', regex=True)
                merged_pdf_files = create_grouped_invoices(df=df, indiv_dir=indiv_dir, group_dir=subdir, merge_dir=subdir / 'fusion')
                compress_pdfs(merged_pdf_files, factures_groupees_dir)
                console.print(f"Fusion des factures pour [bold]{subdir.name}[/bold]", style="green")
            else:
                console.print(f"Le dossier [bold]{factures_groupees_dir}[/bold] existe déjà. Fusion ignorée.", style="yellow")
            batch_status[subdir]['fusion'] = True
        else:
            console.print(f"Fichier Excel [bold]{xlsx_file.name}[/bold] non trouvé. Fusion ignorée.", style="red")
        # ===================Étape 3B : Création du zip avec facturix====================
        console.print("Étape 3B : Création du zip avec facturix", style="yellow")
        factures_groupees_dir = subdir / "factures_groupees"
        bt_csv = factures_groupees_dir / "BT.csv"
        if bt_csv.exists():
            factures_zipees_dir = subdir / "factures_zipees"
            if not factures_zipees_dir.exists() or args.forcer_zip:
                factures_zipees_dir.mkdir(exist_ok=True)
                # Utilisation de facturix pour créer le zip
                # package_invoices(str(factures_groupees_dir), str(factures_zipees_dir))
                console.print(f"Création du zip pour [bold]{subdir.name}[/bold]", style="green")
            else:
                console.print(f"Le dossier [bold]{factures_zipees_dir}[/bold] existe déjà. Création du zip ignorée.", style="yellow")
                batch_status[subdir]['zipping'] = True
        else:
            console.print(f"Fichier BT.csv non trouvé dans [bold]{factures_groupees_dir}[/bold]. Création du zip ignorée.", style="red")


    console.print(Panel.fit("Traitement terminé", style="bold green"))
    # =======================Étape 4: état des lieux de l'atelier==========================
    

    tree = rich_directory_tree(atelier_dir, 2)
    console.print("\n[bold blue]Directory Structure:[/bold blue]")
    console.print(tree)

    console.print(rich_status_table(batch_status))

if __name__ == "__main__":
    main()