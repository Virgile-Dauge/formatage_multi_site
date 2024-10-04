from pathlib import Path
import io
import pymupdf

from pymupdf import Document
def extraire_polices_pdf(fichier_pdf):
    # Ouvrir le fichier PDF
    doc = pymupdf.open(fichier_pdf)
    polices = set()  # Utilisation d'un set pour éviter les doublons

    # Parcourir chaque page
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        # Extraire le texte avec ses propriétés
        blocs = page.get_text("dict")['blocks']
        
        # Parcourir chaque bloc de texte pour extraire les polices
        for bloc in blocs:
            if "lines" in bloc:
                for ligne in bloc["lines"]:
                    for span in ligne["spans"]:
                        font = span["font"]  # Extraire le nom de la police
                        polices.add(font)

    doc.close()
    return polices

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
def ajouter_ligne_regroupement(fichier_pdf : Path, output_dir: Path, group_name : str, fontname : str="hebo", fontsize : int=11):
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
    
    # pymupdf.Base14_fontdict pour avoir les polices supportées
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
    
    texte_regroupement = f'Regroupement de facturation : ({group_name})'
    lignes = obtenir_lignes_regroupement(texte_regroupement, fontname, fontsize, max_largeur=290)
    # Ouvrir le fichier PDF
    doc = pymupdf.open(fichier_pdf)

    # Charger la première page uniquement
    page = doc.load_page(0)
    texte = page.get_text("text")
    
    # Définir le texte à rechercher
    texte_a_rechercher = "Votre identifiant :"
    
    # Vérifier si le texte est présent dans la page
    if texte_a_rechercher in texte:
        # Rechercher la position du texte
        zones_texte = page.search_for(texte_a_rechercher)
        
        interligne = 10.9
        # Ajouter la ligne spécifique en dessous du texte trouvé
        for rect in zones_texte:
            for i, l in enumerate(lignes):
                page.insert_text((rect.x0, rect.y0 + interligne*(2 + i)), l, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
                    
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
def ajouter_ligne_regroupement_doc(doc, cible:str = 'Votre espace client :', fontname : str="hebo", fontsize : int=11):
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
    
    metadata = get_extended_metadata(doc)
    if not "GroupName" in metadata:
        return
    group = metadata["GroupName"]
    if group == '':
        return
    
    print(group)
    texte_regroupement = f'Regroupement de facturation : ({group})'
    lignes = obtenir_lignes_regroupement(texte_regroupement, fontname, fontsize, max_largeur=290)
    print(lignes)
    # Charger la première page uniquement
    page = doc.load_page(0)
    texte = page.get_text("text")
    
    # Définir le texte à rechercher
    texte_a_rechercher = cible
    
    # Vérifier si le texte est présent dans la page
    if texte_a_rechercher in texte:
        # Rechercher la position du texte
        zones_texte = page.search_for(texte_a_rechercher)
        
        interligne = 12
        # Ajouter la ligne spécifique en dessous du texte trouvé
        for rect in zones_texte:
            for i, l in enumerate(lignes):
                page.insert_text((rect.x0, rect.y0 + interligne*(2 + i)), l, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
                    
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

def apply_pdf_transformations(input_pdf_path, output_pdf_path, transformations):
    """
    Apply a series of transformations to a PDF file.

    Args:
    input_pdf_path (str): Path to the input PDF file.
    output_pdf_path (str): Path where the transformed PDF will be saved.
    transformations (list): A list of transformation functions to apply.

    Each transformation function should take a PyMuPDF document object as its first argument,
    and any additional arguments specific to that transformation.
    """
    # Open the PDF
    doc = pymupdf.open(input_pdf_path)


    # Apply each transformation
    for transform_func, *args in transformations:
        transform_func(doc, *args)

    # Save the transformed PDF
    doc.save(output_pdf_path)
    doc.close()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Remplacer du texte dans un fichier PDF")
    parser.add_argument("pdf_path", type=str, help="Le chemin du fichier PDF à traiter")
    # parser.add_argument("texte_a_remplacer", type=str, help="Le texte à remplacer dans le fichier PDF")
    # parser.add_argument("nouveau_texte", type=str, help="Le nouveau texte à insérer dans le fichier PDF")
    # parser.add_argument("output_path", type=str, help="Le chemin du fichier PDF de sortie")
    args = parser.parse_args()

    input_pdf = Path(args.pdf_path).expanduser()
    output_pdf = input_pdf.parent / f"replaced_{input_pdf.name}"
    print(output_pdf)
    #remplacer_texte_pdf(args.pdf_path, output_pdf, "Votre espace client  : https://client.enargia.eus", "Votre espace client : suiviconso.enargia.eus")
    transformations = [
        (remplacer_texte_doc, "Votre espace client  : https://client.enargia.eus", "Votre espace client : https://suiviconso.enargia.eus"),
        (caviarder_texte_doc, "Votre identifiant :", 290, 45),
        (ajouter_ligne_regroupement_doc,)
        # Add more transformations as needed
    ]

    apply_pdf_transformations(input_pdf, output_pdf, transformations)

    doc = pymupdf.open(output_pdf)
    metadata = get_extended_metadata(doc)
    print(metadata)
    # Exemple d'utilisation
    # polices = extraire_polices_pdf(args.pdf_path)

    # print("Polices utilisées dans le PDF :")
    # for police in polices:
    #     print(police)

    #group = "GROUP - NAME"
    #ajouter_ligne_regroupement(args.pdf_path, f'Regroupement de facturation : ({group})')