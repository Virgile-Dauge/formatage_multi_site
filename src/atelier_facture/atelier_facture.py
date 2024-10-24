import re

import numpy as np
import argparse
from pathlib import Path
import pandas as pd
from pandas import DataFrame

import shutil 
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from facturix import process_invoices

# local imports
from rich_components import process_with_rich_progress, rich_status_table, rich_directory_tree 
from fusion import create_grouped_invoices, create_grouped_single_invoice
from empaquetage import process_BT_csv
from pdf_utils import compress_pdfs

from logger_config import setup_logger, logger
      
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

def process_inputs(input_path: Path, atelier_dir: Path, indiv_dir: Path, console, regex_dict: dict[str, str]=None):
    if regex_dict is None:
        regex_dict = {
                'date': r'VOTRE FACTURE\s*(?:DE\s*RESILIATION\s*)?DU\s*(\d{2})\/(\d{2})\/(\d{4})',
                'client_name': r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)',
                'group_name': r'Regroupement de facturation\s*:\s*\((.*?)\)',
                'pdl': r'Référence PDL : (\d{14})',
                'invoice_id': r'N° de facture\s*:\s*(\d{14})'
            }
    
    zip_list = []
    if input_path.is_file() and input_path.suffix == '.zip':
        zip_list = [input_path]
    elif input_path.is_dir():
        zip_list = list(input_path.glob('*.zip'))

    if not zip_list:
        console.print("Aucun fichier zip trouvé. Étape ignorée.", style="yellow")
    else:
        for zip_path in zip_list:
            batch_dir = atelier_dir / zip_path.stem
            batch_dir.mkdir(exist_ok=True)
            console.print(Panel.fit(f"Traitement commencé pour [bold]{zip_path}[/bold]", style="green"))
            group_pdfs, individual_pdfs, errors = process_with_rich_progress(zip_path, indiv_dir, batch_dir, regex_dict, console)
            
            result_panel = Panel(
                f"""
                [bold green]Processing Results:[/bold green]
                Number of Group PDFs: {len(group_pdfs)}
                Number of Individual PDFs: {len(individual_pdfs)}
                Number of Errors: {len(errors)}

                """,
                title=f"Données extraites de {zip_path.name}",
            )

            console.print(result_panel)
def main():
    parser = argparse.ArgumentParser(description="Traitement des factures")
    parser.add_argument("atelier_path", type=str, help="Chemin du répertoire atelier")
    parser.add_argument("-i", "--input", type=str, help="Chemin vers le fichier zip d'entrée, ou le dossier de zips d'entrée.")
    parser.add_argument("-f", "--force", action="store_true", help="Supprime tous les fichiers intermédiaires (pas les fichiers bruts extraits)")
    parser.add_argument('-v', '--verbose', action='count', default=0, help="Plus de logs (e.g., -v or -vv)")
    args = parser.parse_args()

    # Configure the logger based on verbosity
    setup_logger(args.verbose)
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
    console.print(Panel.fit("Étape 1: Traitement des entrées", style="bold magenta"))
    if args.input:
        process_inputs(Path(args.input), atelier_dir, indiv_dir, console)

    # =======================Étape 2: Liste des dossiers dans l'atelier================
    console.print(Panel.fit("Étape 2: Liste des dossiers dans l'atelier", style="bold magenta"))
    subdirs = [d for d in atelier_dir.iterdir() if d.is_dir() and d.name not in ['group', 'indiv']]
    console.print("Dossiers trouvés :", style="cyan")
    for d in subdirs:
        console.print(f"  - {d.name}", style="cyan")

    # =======================Étape 3 : Traitement des dossiers=========================
    batch_status = {}
    for subdir in subdirs:
        console.print(Panel.fit(f"Traitement du dossier : {subdir.name}", style="bold blue"))
        # ===================Prep Étape 3 : suppr dossiers si nécessaire================
        if args.force:
            # Supprimer tous les dossiers dans subdir
            logger.info(f"Suppression des anciens résultats dans {subdir}.")
            # Step 1: List and log directories
            dirs_to_remove = [item for item in subdir.iterdir() if item.is_dir()]

            # Log the directories marked for removal
            for dir_path in dirs_to_remove:
                logger.info(f"supp dossier: {dir_path}")

            # Step 2: Delete the directories
            for dir_path in dirs_to_remove:
                shutil.rmtree(dir_path)
            
            # Supprimer BT_updated s'il existe
            bt_updated_path = subdir / 'BT_updated.csv'
            if bt_updated_path.exists():
                logger.info(f"supp fichier : {bt_updated_path}")
                bt_updated_path.unlink()

        # ===================Étape 3A : Fusion des factures=============================
        console.print("Étape 3A : Fusion des factures", style="yellow")
        # pour chaque dossier, on crée un sous-dossier group_mult et group_mono
        # dans lequels on va respectivement générer les factures regroupement et les factures regroupement mono PDL
        
        batch_status[subdir] = {'fusion': False, 'facturx': False}
        # group_mult_dir = subdir / 'group_mult'
        # group_mono_dir = subdir / 'group_mono'
        # group_mult_dir.mkdir(exist_ok=True)
        # group_mono_dir.mkdir(exist_ok=True)
        group_dir = subdir / 'group'
        group_dir.mkdir(exist_ok=True)
        xlsx_file = subdir / f"{subdir.name}.xlsx"

        if xlsx_file.exists():
            df = pd.read_excel(xlsx_file, sheet_name='Sheet1')
            # Remplacer les tirets moyens par des tirets courts
            df = df.replace('–', '-', regex=True)
            # console.print(f"Fusion des factures pour [bold]{subdir.name}[/bold]", style="green")
            nunique_groupements = df['groupement'].dropna().nunique() - 1
            nunique_group_multi = df.groupby("groupement").filter(lambda x: len(x) > 1)["groupement"].nunique() - 1
            nunique_group_mono = df.groupby("groupement").filter(lambda x: len(x) == 1)["groupement"].nunique()
            # Create a panel with both pieces of information
            panel_content = Text.assemble(
                ("Nombre de groupements uniques : ", "cyan"),
                (f"{nunique_groupements}\n", "cyan bold"),
                ("Nombre de groupements multi pdl : ", "cyan"),
                (f"{nunique_group_multi}\n", "cyan bold"),
                ("Nombre de groupements mono pdl : ", "cyan"),
                (f"{nunique_group_mono}\n", "cyan bold"),
                "\n\n",
                ("Fusion des factures pour ", "green"),
                (f"{subdir.name}", "green bold")
            )
            
            panel = Panel(
                panel_content,
                title=f"Batch {subdir.name}",
                border_style="blue"
            )
            console.print(panel)
            if not any(group_dir.glob('*.pdf')):

                
                
                # TODO quand ok, remplacer merge_dir par tmp_dir
                merged_pdf_files = create_grouped_invoices(df=df, indiv_dir=indiv_dir, group_dir=subdir, merge_dir=subdir / 'fusion')
                compress_pdfs(merged_pdf_files, group_dir)

                create_grouped_single_invoice(df=df, indiv_dir=indiv_dir, output_dir=group_dir)


                batch_status[subdir]['fusion'] = f"{len(list(group_dir.glob('*.pdf')))}/{nunique_groupements}"
                
            else:
                console.print(f"Le dossier [bold]{group_dir}[/bold] existe déjà. Fusion ignorée.", style="yellow")
                batch_status[subdir]['fusion'] = True
        else:
            console.print(f"Fichier Excel [bold]{xlsx_file.name}[/bold] non trouvé. Fusion ignorée.", style="red")
            continue
        
        # ===================Étape 3B : Création des factures factur-x====================
        console.print("Étape 3B : Création des factures factur-x", style="yellow")

        # Plusieurs sous-étapes ici :
        
        bt_csv_files = list(subdir.glob("BT*.csv"))
        pdfa3_dir = subdir / "pdf3a"
        facturx_dir = subdir / "facturx"
        # compressed_facturx_dir = subdir / "compressed_facturx"
        # compressed_facturx_dir.mkdir(exist_ok=True)
        bt_up_path = subdir / "BT_updated.csv"

        conform_pdf : bool = not any(pdfa3_dir.glob('*.pdf'))
        bt_df = process_BT_csv(group_dir, subdir)
        if bt_df is None:
            console.print(f"Fichier BT.csv non trouvé dans [bold]{subdir}[/bold]. Création des factures factur-x ignorée.", style="red")
            batch_status[subdir]['facturx'] = True
            continue

        if not any(facturx_dir.glob('*.pdf')):
            console.print(f"Création des Factur-X pour [bold]{subdir.name}[/bold]", style="green")
            errors = process_invoices(bt_df, pdfa3_dir, facturx_dir, conform_pdf=conform_pdf)
            batch_status[subdir]['facturx'] = f"{len(list(facturx_dir.glob('*.pdf')))}/{len(list(group_dir.glob('*.pdf')))}"

            if errors:
                logger.warning(f"Erreurs lors de la création des factures factur-x : {errors}")

        # if not any(compressed_facturx_dir.glob('*.pdf')):
        #     #compress_pdfs(list(Path(facturx_dir).glob('*.pdf')), compressed_facturx_dir)
        #     batch_status[subdir]['facturx'] = f'{len(facturx_dir.glob('*.pdf'))}/{len(bt_df)}'

    # =======================Étape 4: factures individuelles===============================
    console.print(Panel.fit("Étape 4 : Création des factures factur-x individuelles", style="bold magenta"))
    bt_up_path = indiv_dir / "BT_updated.csv"
    if not bt_up_path.exists() or args.force:
        bt_df = process_BT_csv(indiv_dir, indiv_dir)
    else:
        bt_df = pd.read_csv(bt_up_path)
    indiv_pdfa3_dir = indiv_dir / "pdf3a"
    indiv_facturx_dir = indiv_dir / 'facturx'
    indiv_pdfa3_dir.mkdir(exist_ok=True)
    indiv_facturx_dir.mkdir(exist_ok=True)
    if bt_df is not None and not any(indiv_facturx_dir.glob('*.pdf')):
        errors = process_invoices(bt_df, indiv_pdfa3_dir, indiv_facturx_dir, 
                                conform_pdf=not any(indiv_pdfa3_dir.glob('*.pdf')))
        if errors:
            logger.warning(f"Erreurs lors de la création des factures individuelles : {errors}")
    console.print(Panel.fit("Traitement terminé", style="bold green"))
    # =======================Étape 5: état des lieux de l'atelier==========================
    
    
    # tree = rich_directory_tree(atelier_dir, 2)
    # console.print("\n[bold blue]Directory Structure:[/bold blue]")
    # console.print(tree)

    console.print(rich_status_table(batch_status))

if __name__ == "__main__":
    main()