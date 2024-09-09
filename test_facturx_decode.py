import facturx
from facturx import get_facturx_xml_from_pdf
from io import BytesIO
from xml.etree import ElementTree as ET
from rich.console import Console
from rich.tree import Tree
from rich.syntax import Syntax
import rich
# Chemin du fichier PDF/A-3 avec Factur-X intégré
facturx_pdf_path = 'FSO1117A_EN16931_P01.pdf' # issu de la doc Chorus
facturx_pdf_path = 'Facture_FR_MINIMUM.pdf' # Issu de la doc FeRD
facturx_pdf_path = 'facture_facturx.pdf' # Généré par moi
# Lecture du fichier PDF en mode binaire
try:
    with open(facturx_pdf_path, 'rb') as f:
        pdf_data = f.read()

    # Utilisation de BytesIO pour manipuler le fichier en mémoire
    pdf_io = BytesIO(pdf_data)
    
    # Extraire le fichier XML du PDF en mémoire
    facturx_xml = get_facturx_xml_from_pdf(pdf_io)
    #print(facturx_xml[-1])


    # Initialiser la console rich
    console = Console()

    # Décoder les bytes en chaîne de caractères
    xml_str = facturx_xml[-1].decode('utf-8')

    # Charger le contenu XML en tant qu'élément XML
    tree = ET.ElementTree(ET.fromstring(xml_str))
    root = tree.getroot()
    root = tree.getroot()

    # Fonction récursive pour construire un arbre à partir de l'arbre XML
    def add_xml_to_tree(element, tree_node):
        # Ajouter l'élément actuel à l'arbre Rich
        node_text = f"<{element.tag}>"
        if element.text and element.text.strip():
            node_text += f" {element.text.strip()}"
        node = tree_node.add(node_text)
        
        # Ajouter les enfants récursivement
        for child in element:
            add_xml_to_tree(child, node)

    # Créer l'arbre pour l'affichage
    rich_tree = Tree(f"XML: {root.tag}")
    add_xml_to_tree(root, rich_tree)

    # Afficher l'arbre dans la console
    console.print(rich_tree)
    
    # Définir le chemin du fichier XML de sortie
    output_xml_path = 'extracted_facturx.xml'

    # Sauvegarder le contenu XML dans un fichier
    with open(output_xml_path, 'w', encoding='utf-8') as xml_file:
        xml_file.write(xml_str)

    print(f"Le fichier XML a été sauvegardé avec succès dans {output_xml_path}")
except Exception as e:
    print(f"Erreur lors de l'extraction du XML : {str(e)}")