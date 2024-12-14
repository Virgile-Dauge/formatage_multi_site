from pathlib import Path

import os
import shutil
import tempfile
import pymupdf

from atelier_facture.utils import logger
# ====================== Utilitaires =======================

def human_readable_size(size_in_bytes: int) -> str:
    """Convert a size in bytes to a human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

def compress_pdf_inplace(input_path: Path):
    """
    Compress a PDF file in place using PyMuPDF.

    :param input_path: Path to the input PDF file, which will be modified in place.
    """
    original_size = input_path.stat().st_size
    try:
        # Ouvrir le document avec PyMuPDF
        doc = pymupdf.open(str(input_path))

        # Créer un fichier temporaire pour sauvegarder le PDF compressé
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_output_path = temp_file.name
        temp_file.close()  # Fermer le fichier temporaire pour l'utiliser avec PyMuPDF

        # Sauvegarder le document compressé dans le fichier temporaire
        doc.save(temp_output_path,
                 garbage=4,  # clean up unreferenced objects
                 deflate=True,  # compress streams
                 deflate_images=True,
                 clean=True,  # clean up redundant objects
                 pretty=True,  # make PDF human-readable
                 linear=True)  # optimize for web viewing
        doc.close()

        # Remplacer le fichier d'origine par le fichier compressé
        shutil.move(temp_output_path, input_path)

        # Calculer la taille de compression
        compressed_size = input_path.stat().st_size
        compression_ratio = (1 - (compressed_size / original_size)) * 100

        logger.debug(f"Compressed {input_path.name} ({compression_ratio:.2f}%).")

    except Exception as e:
        logger.error(f"Error compressing {input_path.name}: {str(e)}")

    finally:
        # S'assurer que le fichier temporaire est supprimé s'il existe encore
        if Path(temp_output_path).exists():
            Path(temp_output_path).unlink()

def compress_pdf(input_path: Path, output_path: Path):
    """
    Compress a PDF file using PyMuPDF.

    :param input_path: Path to the input PDF file
    :param output_path: Path to save the compressed PDF file
    """
    try:
        doc = pymupdf.open(input_path)
        doc.save(output_path, 
                 garbage=4,  # clean up unreferenced objects
                 deflate=True,  # compress streams
                 deflate_images=True,
                 clean=True,  # clean up redundant objects
                 pretty=True,  # make PDF human-readable
                 linear=True  # optimize for web viewing
                 )
        doc.close()

        original_size = input_path.stat().st_size
        compressed_size = output_path.stat().st_size
        size_gained = original_size - compressed_size
        compression_ratio = (1 - (compressed_size / original_size)) * 100

        logger.debug(f"Compressed {input_path.name} ({compression_ratio:.2f}%).")

    except Exception as e:
        logger.error(f"Error compressing {input_path.name}: {str(e)}")

def compress_pdfs(pdf_files: list[Path], output_dir: Path):
    """
    Compresse une liste de fichiers PDF en compressant les streams.

    Paramètres:
    pdf_files (list[Path]): Liste des chemins des fichiers PDF à compresser.
    output_dir (Path): Chemin du répertoire où les fichiers PDF compressés seront enregistrés.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for pdf_file in pdf_files:
        output_file = output_dir / pdf_file.name
        compress_pdf(pdf_file, output_file)

def get_extended_metadata(doc) -> dict[str, str]:
    """
    Extracts extended metadata from a PDF document.
    """
    metadata = {}  # make my own metadata dict
    what, value = doc.xref_get_key(-1, "Info")  # /Info key in the trailer
    if what != "xref":
        pass  # PDF has no metadata
    else:
        xref = int(value.replace("0 R", ""))  # extract the metadata xref
        for key in doc.xref_get_keys(xref):
            metadata[key] = doc.xref_get_key(xref, key)[1]
    return metadata

def store_extended_metadata(doc, metadata: dict[str, str]):
    """
    Stores extended metadata in a PDF document.
    """
    what, value = doc.xref_get_key(-1, "Info")  # /Info key in the trailer
    if what != "xref":
        raise ValueError("PDF has no metadata")
    
    xref = int(value.replace("0 R", ""))  # extract the metadata xref
    for key, value in metadata.items():
        # add some private information
        doc.xref_set_key(xref, key, pymupdf.get_pdf_str(value))

def obtenir_lignes_regroupement(texte_regroupement: str, fontname: str, fontsize: int, max_largeur: int=500) -> list[str]:
    """
    Divise le texte de regroupement en plusieurs lignes si nécessaire pour s'adapter à la largeur maximale spécifiée.

    Paramètres:
    texte_regroupement (str): Le texte de regroupement à ajouter.
    fontname (str): Le nom de la police à utiliser pour le texte ajouté.
    fontsize (int): La taille de la police à utiliser pour le texte ajouté.
    max_largeur (int): La largeur maximale autorisée pour une ligne de texte. Par défaut 500.

    Retourne:
    list[str]: Une liste de lignes de texte adaptées à la largeur maximale spécifiée.
    """
    
    lignes = []
    # Vérifier si le texte de regroupement est trop long pour une seule ligne
    if pymupdf.get_text_length(texte_regroupement, fontname=fontname, fontsize=fontsize) > max_largeur:
        # Diviser le texte en plusieurs lignes
        mots = texte_regroupement.split()
        ligne = ""
        for mot in mots:
            if pymupdf.get_text_length(ligne + " " + mot, fontname=fontname, fontsize=fontsize) <= max_largeur:
                ligne += " " + mot
            else:
                lignes.append(ligne.strip())
                ligne = mot
        lignes.append(ligne.strip())
    else:
        lignes.append(texte_regroupement)
    return lignes

def partial_pdf_copy(doc: pymupdf.Document, start_page: int, end_page: int, output_path: Path, metadata: dict|None=None) -> None:
    """
    Crée un nouveau fichier PDF à partir des pages spécifiées d'un document source,
    et ajoute les métadonnées spécifiées.

    :param doc: Document source PyMuPDF.
    :param start_page: Index de la page de début (inclus).
    :param end_page: Index de la page de fin (exclus).
    :param output_path: Chemin de sauvegarde du nouveau fichier PDF.
    :param metadata: Dictionnaire contenant les métadonnées à ajouter.
    """
    with pymupdf.open() as new_doc:
        # Insérer les pages du document source dans le nouveau document
        for page_number in range(start_page, end_page):
            new_doc.insert_pdf(doc, from_page=page_number, to_page=page_number)

        if metadata is not None:
            new_doc.set_metadata(metadata)
        # Sauvegarder le nouveau fichier PDF
        new_doc.save(output_path)

def concat_pdfs(paths: list[Path], output_path: Path, metadata: dict|None=None) -> None:
    """
    Concatène une liste de fichiers PDF en un seul fichier.

    Arguments :
    :paths list[Path]: liste de chemins vers les fichiers PDF à concaténer (type : list[Path])
    :output_path Path:chemin vers le fichier de sortie (type : Path)
    """
    # Créer un nouveau document PDF vide
    with pymupdf.Document() as pdf_final:
        for chemin_pdf in paths:
            with pymupdf.Document(str(chemin_pdf)) as pdf_a_ajouter:
                # Ajouter chaque page du document actuel au PDF final
                for page_index in range(len(pdf_a_ajouter)):
                    pdf_final.insert_pdf(pdf_a_ajouter, from_page=page_index, to_page=page_index)
        if metadata is not None:
            pdf_final.set_metadata(metadata)
        # Enregistrer le PDF final
        pdf_final.save(str(output_path))

# ============== Opérations modification uniques ========================
def ajouter_ligne_regroupement(fichier_pdf : Path, output_dir: Path, group_name : str, cible:str='Votre espace client :', fontname : str="hebo", fontsize : int=11):
    """
    Ajoute une ligne de regroupement à un fichier PDF existant.

    Paramètres:
    fichier_pdf (Path): Le chemin vers le fichier PDF à modifier.
    texte_regroupement (str): Le texte de regroupement à ajouter.
    fontname (str): Le nom de la police à utiliser pour le texte ajouté. Par défaut "hebo".
    fontsize (int): La taille de la police à utiliser pour le texte ajouté. Par défaut 11.

    Cette fonction ouvre le fichier PDF spécifié, recherche une position spécifique
    où ajouter le texte de regroupement, et sauvegarde le fichier modifié dans un
    nouveau dossier nommé "groupement_facture_unique" situé dans le même répertoire
    que le fichier d'entrée.
    """
    texte_regroupement = f'Regroupement de facturation : ({group_name})'
    lignes = obtenir_lignes_regroupement(texte_regroupement, fontname, fontsize, max_largeur=290)
    # Ouvrir le fichier PDF
    doc = pymupdf.open(fichier_pdf)

    # Charger la première page uniquement
    page = doc.load_page(0)
    texte = page.get_text("text")
    
    # Vérifier si le texte est présent dans la page
    if cible in texte:
        # Rechercher la position du texte
        zones_texte = page.search_for(cible)
        
        interligne = 10.9
        # Ajouter la ligne spécifique en dessous du texte trouvé
        for rect in zones_texte:
            for i, l in enumerate(lignes):
                page.insert_text((rect.x0, rect.y0 + interligne*(3 + i)), l, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
                    
    # Read metadata
    metadata = get_extended_metadata(doc)
    
    metadata['GroupName'] = str(group_name)

    store_extended_metadata(doc, metadata)
    metadata = get_extended_metadata(doc)

    date = metadata['CreationDate']
    client_name = metadata['ClientName']
    # Sauvegarder le fichier PDF modifié dans un nouveau dossier depuis le même dossier que le dossier d'entrée
    output_pdf_path = output_dir / f"{date}-{client_name} - {group_name}.pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    doc.save(output_pdf_path)
    doc.close()

# ============== Opérations modification chainables =====================
# TODO: Check if legacy not impacted
def ajouter_ligne_regroupement_doc(doc, group: str|None=None, cible:str = 'Votre espace client :', fontname : str="hebo", fontsize : int=11):
    """
    Ajoute une ligne de regroupement à un fichier PDF existant.

    Paramètres:
    fichier_pdf (Path): Le chemin vers le fichier PDF à modifier.
    texte_regroupement (str): Le texte de regroupement à ajouter.
    fontname (str): Le nom de la police à utiliser pour le texte ajouté. Par défaut "hebo".
    fontsize (int): La taille de la police à utiliser pour le texte ajouté. Par défaut 11.

    Cette fonction ouvre le fichier PDF spécifié, recherche une position spécifique
    où ajouter le texte de regroupement, et sauvegarde le fichier modifié dans un
    nouveau dossier nommé "groupement_facture_unique" situé dans le même répertoire
    que le fichier d'entrée.
    """
    if group is None:
        
        metadata = get_extended_metadata(doc)
        if not "GroupName" in metadata:
            return
        group = metadata.get('GroupName', '')
    
    if group == '':
        return
    texte_regroupement = f'Regroupement de facturation : ({group})'
    lignes = obtenir_lignes_regroupement(texte_regroupement, fontname, fontsize, max_largeur=290)
    
    # Charger la première page uniquement
    page = doc.load_page(0)
    texte = page.get_text("text")

    # Vérifier si le texte est présent dans la page
    if cible in texte:
        # Rechercher la position du texte
        zones_texte = page.search_for(cible)
        interligne = 12
        # Ajouter la ligne spécifique en dessous du texte trouvé
        for rect in zones_texte:
            for i, l in enumerate(lignes):
                page.insert_text((rect.x0, rect.y0 + interligne*(3 + i)), l, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
                    
def remplacer_texte_doc(doc, ancien_texte, nouveau_texte, fontname="hebo", fontsize=11):
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        texte = page.get_text("text")
        if ancien_texte in texte:
            zones_texte = page.search_for(ancien_texte)
            for rect in zones_texte:
                page.add_redact_annot(rect)
            page.apply_redactions()
            for rect in zones_texte:
                page.insert_text((rect.x0, rect.y0 + 9.5), nouveau_texte, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
  
def caviarder_texte_doc(doc, cible, x=None, y=None):
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        texte = page.get_text("text")
        if cible in texte:
            zones_texte = page.search_for(cible)
            for rect in zones_texte:
                if x is not None and y is not None:
                    rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + x, rect.y0 + y)
                    #page.add_rect_annot(rect)
                page.add_redact_annot(rect)
            page.apply_redactions()

# ============== Chainage des Opérations ===================
def apply_pdf_transformations(input_pdf_path, output_pdf_path, transformations):
    """
    Apply a series of transformations to a PDF file.
    """
    # Open the PDF
    doc = pymupdf.open(input_pdf_path)

    # Apply each transformation
    for transform_func, *args in transformations:
        transform_func(doc, *args)

    # If input and output paths are the same, use a temporary file
    if input_pdf_path == output_pdf_path:
        # Create a temporary file in the same directory as the input file
        with tempfile.NamedTemporaryFile(delete=False, dir=os.path.dirname(input_pdf_path), suffix='.pdf') as tmp_file:
            temp_output_path = tmp_file.name

        # Save to the temporary file
        doc.save(temp_output_path)
        doc.close()
        
        # Replace the original file with the temp file
        os.replace(temp_output_path, input_pdf_path)
    else:
        # Save directly to the output path if it's different from the input
        doc.save(output_pdf_path)
        doc.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Remplacer du texte dans un fichier PDF")
    parser.add_argument("pdf_path", type=str, help="Le chemin du fichier PDF à traiter")
    args = parser.parse_args()

    input_pdf = Path(args.pdf_path).expanduser()
    output_pdf = input_pdf.parent / f"replaced_{input_pdf.name}"
    
    transformations = [
        (remplacer_texte_doc, "Votre espace client  : https://client.eqwasd.fr", "Votre espace client : https://qwedda.adssad.fr"),
        (caviarder_texte_doc, "Votre identifiant :", 290, 45),
        (ajouter_ligne_regroupement_doc,)
        # Add more transformations as needed
    ]

    # apply_pdf_transformations(input_pdf, output_pdf, transformations)

    # doc = pymupdf.open(output_pdf)
    doc = pymupdf.open(input_pdf)
    metadata = get_extended_metadata(doc)

    from rich import print
    print(metadata)
    group = "GROUP - NAME"
    # ajouter_ligne_regroupement(input_pdf, input_pdf.parent, 'COUCOU')
    original_filename = input_pdf.stem
    compressed_file = input_pdf.parent / f"{original_filename}_compressed.pdf"
    # compress_pdf(input_pdf, compressed_file)