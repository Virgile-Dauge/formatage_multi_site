from pypdf import PdfReader, PdfWriter
from pathlib import Path
import io
import fitz  # PyMuPDF
def extraire_polices_pdf(fichier_pdf):
    # Ouvrir le fichier PDF
    doc = fitz.open(fichier_pdf)
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

def ajouter_ligne_regroupement(fichier_pdf : Path, texte_regroupement : str, fontname : str="hebo", fontsize : int=11):
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
        if fitz.get_text_length(texte_regroupement, fontname=fontname, fontsize=fontsize) > max_largeur:
            # Diviser le texte en plusieurs lignes
            mots = texte_regroupement.split()
            ligne = ""
            for mot in mots:
                if fitz.get_text_length(ligne + " " + mot, fontname=fontname, fontsize=fontsize) <= max_largeur:
                    ligne += " " + mot
                else:
                    lignes.append(ligne.strip())
                    ligne = mot
            lignes.append(ligne.strip())
        else:
            lignes.append(texte_regroupement)
        return lignes
    
    lignes = obtenir_lignes_regroupement(texte_regroupement, fontname, fontsize, max_largeur=290)
    # Ouvrir le fichier PDF
    doc = fitz.open(fichier_pdf)

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
                    
    
    # Sauvegarder le fichier PDF modifié dans un nouveau dossier depuis le même dossier que le dossier d'entrée
    dossier_entree = Path(fichier_pdf).parent
    nouveau_dossier = dossier_entree / "groupement_facture_unique"
    nouveau_dossier.mkdir(parents=True, exist_ok=True)
    nouveau_fichier_pdf = nouveau_dossier / Path(fichier_pdf).name
    doc.save(nouveau_fichier_pdf)
    doc.close()


def remplacer_texte_pdf(fichier_entree, fichier_sortie, ancien_texte, nouveau_texte):
    # Ouvrir le fichier PDF
    doc = fitz.open(fichier_entree)

    # Parcourir chaque page
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        texte = page.get_text("text")
        
        # Vérifier si l'ancien texte est présent dans la page
        if ancien_texte in texte:
            # Rechercher toutes les instances du texte à remplacer
            zones_texte = page.search_for(ancien_texte)
            
            # Pour chaque zone où le texte est trouvé
            for rect in zones_texte:
                # Ajouter une annotation de caviardage (redaction) pour masquer le texte original
                page.add_redact_annot(rect)
                
            # Appliquer le caviardage (supprimer le texte original)
            page.apply_redactions()
            
            # Insérer le nouveau texte légèrement décalé de la position d'origine
            for rect in zones_texte:
                # Insérer le nouveau texte légèrement décalé de l'ancien avec une option de choix de police et détection de l'ancienne police
                for rect in zones_texte:
                    fontname = "helv"
                    fontsize = 11
                    page.insert_text((rect.x0, rect.y0 + 9.5), nouveau_texte, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
    
    # Sauvegarder le fichier PDF modifié
    doc.save(fichier_sortie)
    doc.close()
    
def remplacer_texte_pdf_pypdf(pdf_path, texte_a_remplacer, nouveau_texte, output_path):
    try:
        # Vérifier si le fichier PDF existe
        if not Path(pdf_path).is_file():
            raise FileNotFoundError(f"Le fichier PDF '{pdf_path}' n'existe pas.")
        # Ouvrir le document PDF
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # Parcourir chaque page du document
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text = page.extract_text()
            
            # Remplacer le texte
            if texte_a_remplacer in text:
                text = text.replace(texte_a_remplacer, nouveau_texte)
                
                # Créer une nouvelle page avec le texte modifié
                writer.add_page(page)
                writer.pages[page_num].merge_page(PdfReader(io.BytesIO(text.encode('utf-8'))))
            else:
                writer.add_page(page)
        
        # Sauvegarder le document modifié
        with open(output_path, "wb") as output_pdf:
            writer.write(output_pdf)
        
        print(f"Le texte '{texte_a_remplacer}' a été remplacé par '{nouveau_texte}' dans le fichier '{output_path}'")
    except Exception as e:
        print(f"Erreur lors du traitement du fichier PDF: {e}")

# Exemple d'utilisation
# remplacer_texte_pdf("chemin/vers/votre_fichier.pdf", "texte_a_remplacer", "nouveau_texte", "chemin/vers/fichier_modifie.pdf")

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
    remplacer_texte_pdf(args.pdf_path, output_pdf, "Référence PDL : 16423878312360", "Gagné")

    # Exemple d'utilisation
    polices = extraire_polices_pdf(args.pdf_path)

    print("Polices utilisées dans le PDF :")
    for police in polices:
        print(police)

    group = "GROUP - NAME"
    ajouter_ligne_regroupement(args.pdf_path, f'Regroupement de facturation : ({group})')