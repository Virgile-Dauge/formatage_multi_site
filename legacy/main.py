import re
import os
from pypdf import PdfReader, PdfWriter
from pathlib import Path
import pandas as pd
import sys
import fitz
from mpl import export_table_as_pdf


# POUR UTILISER CE SCRIPT, DESCENDRE A LA LIGNE "__name__" == "__main__"
# Regex patterns pour extraire les informations
date_pattern = r'VOTRE FACTURE DU (\d{2})\/(\d{2})\/(\d{4})'
client_name_pattern = r'Nom et Prénom ou\s* Raison Sociale :\s*(.*)'
group_name_pattern = r'Regroupement de facturation\s*:\s*\((.*?)\)'
pdl_pattern = r'Référence PDL : (\d{14})'

def split_bill_pdfs(pdf_file_path, output_dir="output_pdfs",  start_keyword="www.enargia.eus", regex_dict=None):
    # Ouvrir le fichier PDF
    reader = PdfReader(pdf_file_path)
    num_pages = len(reader.pages)
    writer = None

    date = None
    client_name = None
    group_name = None
    pdl_name = None
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for i in range(num_pages):
        page = reader.pages[i]
        text = page.extract_text()

        # Rechercher le mot-clé indiquant le début d'un nouveau sous-PDF
        if start_keyword in text:
            if writer:
                # Enregistrer le PDF précédent avant de commencer un nouveau
                if "group_name" in regex_dict.keys() and group_name and date and client_name:
                    output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {group_name}.pdf")
                elif "pdl_name" in regex_dict.keys() and pdl_name and date and client_name:
                    output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {pdl_name}.pdf")
                else:
                    output_pdf_path = None
                if output_pdf_path:
                    # Enlever les métadonnées pour alléger le fichier
                    with open(output_pdf_path, "wb") as output_pdf:
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
                group_name = group_name_match.group(1).strip().replace("\n","")

            pdl_match = re.search(pdl_pattern, text)
            if pdl_match:
                pdl_name = pdl_match.group(1)

        elif writer:
            # Ajouter la page actuelle au writer en cours
            writer.add_page(page)

    # Enregistrer le dernier PDF
    if writer:
        if "group_name" in regex_dict.keys() and group_name and date and client_name:
            output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {group_name}.pdf")
        elif "pdl_name" in regex_dict.keys() and pdl_name and date and client_name:
            output_pdf_path = os.path.join(output_dir, f"{date}-{client_name} - {pdl_name}.pdf")
        else:
            output_pdf_path = None
        if output_pdf_path:
            with open(output_pdf_path, "wb") as output_pdf:
                writer.write(output_pdf)


def split_pdfs_recursive(data_dir, output_dir, regex_dict):

    print(f"Parcours du répertoire {data_dir}")
    for file in data_dir.iterdir():
        if file.is_file() and file.suffix == ".pdf":
            print(f"Défusionnage du fichier {file}")
            split_bill_pdfs(file, output_dir, "www.enargia.eus", regex_dict)
        elif file.is_dir() and not file.name == output_dir.name :
            split_pdfs_recursive(file, output_dir, regex_dict)

def split_global_bills(data_dir, output_dir):
    # Factures globales par groupement
    regex_dict = {"date": date_pattern, "client_name":client_name_pattern, "group_name": group_name_pattern}
    split_pdfs_recursive(data_dir, output_dir, regex_dict)

def split_unit_bills(data_dir, output_dir):
    # Factures unitaires
    regex_dict = {"date": date_pattern, "client_name": client_name_pattern, "pdl_name": pdl_pattern}
    split_pdfs_recursive(data_dir, output_dir,  regex_dict)

def merge_pdfs_by_group(groups, merge_dir):
    merged_pdf_files = []
    # fusioner par groupement
    for group in groups:
        df = pd.read_excel(merge_dir / str(group) / f"{group}.xlsx")
        pdls = df["PRM"]
        group = str(group)
        pdf_files = [filename for filename in (merge_dir / group).iterdir() if filename.suffix == ".pdf"]
        merger = PdfWriter()
        # ajoute la facture globale en premier
        for pdf in pdf_files:
            if normalize(group) in normalize(pdf.name) and not pdf.name.startswith("Table"):
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
            print(f"Certains PDF n'ont pas été fusionnés: {pdf_files}")
        merger.write((merge_dir) / f"{group}.pdf")
        merged_pdf_files.append(merge_dir / f"{group}.pdf")
        merger.close()
        print(f"Fusionné: {group}.pdf")
    return merged_pdf_files


def sort_pdfs_by_group(df, groups, output_dir, merge_dir):
    for group in groups:
        pdls = df[df["groupement"] == group]["PRM"]
        for pdl in pdls:
            for filename in output_dir.iterdir():
                if str(pdl) in filename.name and filename.suffix == ".pdf":
                    print(filename)
                    filename.rename(merge_dir / group / filename.name)
                elif normalize(group) in normalize(filename.name):
                    filename.rename(merge_dir / group / filename.name)

def sort_xls_by_group(df, groups,  merge_dir=None):
    # Filtrer les données pour le groupement spécifique
    group_col_name = "groupement"
    for group in groups:
        df_groupement = df[df[group_col_name] == group]
        colonnes = [group_col_name] + [col for col in df.columns if col != group_col_name]
        df_groupement = df_groupement[colonnes]
        group_dir = merge_dir / str(group)
        group_dir.mkdir(exist_ok=True)
        df_groupement.to_excel( group_dir / f"{group}.xlsx", index=False)

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

    # Chemin du dossier principal contenant les factures unitaires
    # RENTRER LE NOM DU DOSSIER ICI
    data_dir = "./test_data"

    data_dir = Path(data_dir)
    output_dir = data_dir / "extract"
    output_dir.mkdir(exist_ok=True)
    merge_dir = data_dir / "merge"
    merge_dir.mkdir(exist_ok=True)
    res_dir = data_dir / "results"
    res_dir.mkdir(exist_ok=True)

    print("Défusionnage des factures globales...")
    split_global_bills(data_dir, output_dir)
    print("Fin du défusionnage des factures globales \n")

    print("Défusionnage des factures unitaires...")
    split_unit_bills(data_dir, output_dir)
    print("Fin du défusionnage des factures globales \n")

    print(f"Lecture du fichier Excel 'factures details.xlsx' pour retrouver les regroupement et PDL associés")
    # Lecture des données Excel
    df = pd.read_excel(data_dir / "factures details.xlsx", sheet_name='Sheet1')
    groups = df.groupby("groupement").filter(lambda x: len(x)>=1)["groupement"].unique()

    if "nan" in groups:
        groups = groups.remove("nan")

    print("Tri des fichiers Excel défusionnés \n")
    sort_xls_by_group(df, groups, merge_dir)

    print("Export en PDF des tableurs Excel  \n")
    export_tables_as_pdf(groups, merge_dir)

    print("Tri des fichiers PDF défusionnés \n")
    sort_pdfs_by_group(df, groups, output_dir, merge_dir)

    print("Fusion des PDF par groupement")
    merged_pdf_files = merge_pdfs_by_group(groups, merge_dir)
    print("Fin de la fusion")

    print("Reduce PDF size")
    compress_pdfs(merged_pdf_files, res_dir)

    # Clean folders
