#!/usr/bin/env python3
import argparse
import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from atelier_facture import utils

from atelier_facture.etapes import extraction, consolidation, fusion, formatage
def main():
    parser = argparse.ArgumentParser(description="Traitement des factures")
    parser.add_argument("atelier_path", type=str, help="Chemin du répertoire atelier")
    parser.add_argument("-i", "--input", type=str, help="Chemin vers le fichier zip d'entrée, ou le dossier de zips d'entrée.")
    parser.add_argument("-f", "--force", action="store_true", help="Supprime tous les fichiers intermédiaires (pas les fichiers bruts extraits)")
    parser.add_argument('-v', '--verbose', action='count', default=0, help="Plus de logs (e.g., -v or -vv)")
    args = parser.parse_args()

    # Configuration des loggs based on verbosity
    utils.setup_logger(args.verbose, log_file="app.log")
    console = Console()

    p = Path(args.atelier_path).expanduser()
    ip = p / 'extrait'
    ep = p / 'enrichi'
    fp = p / 'facturx'

    # Création des repertoires de travail
    for dir_path in [ip, ep, fp]:
        dir_path.mkdir(parents=True, exist_ok=True)

    # =======================Étape 0: Définition du répertoire de travail==============
    console.print(Panel.fit("Étape 0: Définition du répertoire de travail", style="bold magenta"))
    utils.pedagogie.afficher_arborescence_travail(console, p, ip, ep, fp)

    # =======================Étape 1: Extraction des données===========================
    if args.input:
        console.print(Panel.fit("Étape 1: Extraction des données", style="bold magenta"))
        input_path = Path(args.input).expanduser()
        extrait, consignes = extraction.process_zip(input_path, ip)
        extrait.to_csv(ip / 'extrait.csv')
    else:
        # Dans le cas ou aucun zip n'est fourni, on charge les fichiers csv issus d'une précédente extraction
        extrait = pd.read_csv(ip / 'extrait.csv', sep=',', encoding='utf-8', dtype=str)
        consignes = pd.read_csv(ip / 'consignes.csv', sep=',', encoding='utf-8', dtype=str)
    facturx = pd.read_csv(ip / 'facturx.csv', sep=',', encoding='utf-8', dtype=str)
    # =======================Étape 2: Consolidation====================================
    console.print(Panel.fit("Étape 2: Consolidation", style="bold magenta"))
    consignes = consolidation.consolidation_consignes(extrait, consignes)
    consignes.to_csv(p / 'consignes_consolidees.csv')

    facturx = consolidation.consolidation_facturx(consignes, facturx)
    facturx.to_csv(p / 'facturx_consolidees.csv')
    # etat_avancement(console, df, ip, ep, fp)

    # =======================Étape 3: Création des pdfs enrichis=======================
    console.print(Panel.fit("Étape 3: Création des pdfs enrichis", style="bold magenta"))
    enrichis = fusion.fusion_groupes(consignes, ep)
    print(enrichis)
    print(enrichis.columns)
    #etat_avancement(console, df, ip, ep, fp)
    # =======================Étape 4: Création des factures Factur-X===================
    console.print(Panel.fit("Étape 4: Création des factures Factur-X", style="bold magenta"))
    bt_df = formatage.vers_facturx(enrichis, facturx, fp)

if __name__ == "__main__":
    main()