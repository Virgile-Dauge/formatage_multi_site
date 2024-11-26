import argparse
from pathlib import Path
import pandas as pd
from rich.console import Console

from atelier_facture import extract_metadata_and_update_df
from facturix import process_invoices

def main():
    parser = argparse.ArgumentParser(description="Traitement des factures individuelles")
    parser.add_argument("indiv_dir", type=Path, help="Chemin vers le répertoire individuel")
    parser.add_argument("--forcer_pdfa3", "-fp", action="store_true", help="Forcer la création de PDF/A-3")
    args = parser.parse_args()

    indiv_dir = args.indiv_dir
    console = Console()

    console.print("Étape 3B : Création du zip avec facturix", style="yellow")
    bt_csv_files = list(indiv_dir.glob("BT*.csv"))
    pdfa3_dir = indiv_dir / "pdf3a"
    facturx_dir = indiv_dir / "facturx"
    pdfa3_dir.mkdir(parents=True, exist_ok=True)
    facturx_dir.mkdir(parents=True, exist_ok=True)
    bt_up_path = indiv_dir / "BT_updated.csv"
    
    conform_pdf = not bt_up_path.exists() or args.forcer_pdfa3
    if bt_csv_files and bt_csv_files[0].exists():
        bt_df = pd.read_csv(bt_csv_files[0]).replace('–', '-', regex=True)
        total_bt_entries = len(bt_df)
        pdfs = list(indiv_dir.glob('*.pdf'))
        bt_df = extract_metadata_and_update_df(pdfs, bt_df)
        bt_df.to_csv(bt_up_path, index=False)

        errors = process_invoices(bt_df, pdfa3_dir, facturx_dir, conform_pdf=conform_pdf)
    else:
        console.print("Aucun fichier BT.csv trouvé dans le répertoire individuel.", style="red")
        return

if __name__ == "__main__":
    main()