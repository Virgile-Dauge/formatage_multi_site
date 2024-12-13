import pandas as pd
from pandas import DataFrame
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

import logging
from rich.logging import RichHandler

# Configuration du logger pour utiliser Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger()

# Supprimer les messages de débogage de font_manager
logging.getLogger('matplotlib').setLevel(logging.WARNING)

def prepare_dataframe(df: DataFrame, exclude=['id', 'pdl'], to_drop=['PRM', 'groupement', 'membre']) -> DataFrame:
    convertible_columns = []

    # Parcourir toutes les colonnes, vérifier si elles sont des floats ou des chaînes (à l'exception de celles à exclure)
    for col in df.columns:
        if col not in exclude and df[col].dtype in ['float64', 'object', 'str']:
            # Vérifier si tous les éléments de la colonne peuvent être convertis en float
            try:
                pd.to_numeric(df[col], errors='raise')
                convertible_columns.append(col)
            except ValueError:
                # Ignorer les colonnes qui ne peuvent pas être converties entièrement
                continue

    # Convertir les colonnes convertibles en float
    df[convertible_columns] = df[convertible_columns].apply(pd.to_numeric, errors='coerce')

    # Arrondir toutes les colonnes de type float à deux décimales
    df[convertible_columns] = df[convertible_columns].round(2)

    for col in to_drop:
        if col in df.columns:
            df = df.drop(columns=[col])

    return df

def export_table_as_pdf(df: DataFrame, pdf_filename):
    # Fixe la police utilisee
    plt.rcParams['font.family'] = 'DejaVu Sans'
    rows_per_page = 40
    # Détermine le nombre de pages nécessaires
    num_pages = len(df) // rows_per_page + int(len(df) % rows_per_page != 0)

    # Modifier le dataframe Pandas
    df = prepare_dataframe(df)

    df_columns = []
    df_columns.append(df.columns[0])
    for col in df.columns[1:]:
        if len(col) > 8:
            col = col.replace(" ", "\n")
        df_columns.append(col)
    df.columns = df_columns
    #colwidths = [0.1 for x in df.columns]
    #colwidths[0] = 0.2
    # Étape 4: Exporter le tableau en PDF
    with PdfPages(pdf_filename) as pdf:
        for i in range(num_pages):
            start_idx = i * rows_per_page
            end_idx = start_idx + rows_per_page
            df_segment = df.iloc[start_idx:end_idx]

            # Créer un tableau avec Matplotlib
            fig, ax = plt.subplots(figsize=(11.69,8.27))  # Ajuster la taille de la figure si nécessaire

            # Masquer les axes
            ax.axis('tight')
            ax.axis('off')

            # Ajouter une table
            table = ax.table(cellText=df_segment.values,
                             colLabels=df_segment.columns,
                             #colWidths=colwidths,
                             cellLoc='center',
                             loc='center',)


            # Style des cellules (contenu)
            table.auto_set_font_size(False)
            table.set_fontsize(8)  # Taille de police pour le contenu
            table.scale(1.2, 1.2)  # Échelle des cellules

            # Style des en-têtes (titres des colonnes)
            for key, cell in table.get_celld().items():
                if key[0] == 0:  # Titre de la colonne
                    cell.set_fontsize(9)  # Taille de police pour les titres

                    #cell.set_facecolor('#40466e')  # Couleur de fond des titres
                    cell.set_facecolor('#F2BC49')
                    cell.set_text_props(color='black')  # Couleur du texte des titres
                    cell.set_height(0.1)
                    cell.set_linewidth(1)
                    cell.set_edgecolor("white")
                    cell.set_text_props(fontweight='extra bold', ha="center")  # Texte en gras
                else:
                    cell.set_edgecolor("white")
                    cell.set_text_props(ha="right")
                    #cell.set_facecolor('#f0f0f0')  # Couleur de fond des cellules



            # Bordures de la table
            table.auto_set_column_width([0, 1, 2, 3])  # Ajuste automatiquement la largeur des colonnes
            # table.auto_set_column_width(range(len(df.columns)))
            pdf.savefig(fig, bbox_inches='tight')

            plt.close(fig)

    logger.debug(f"Le fichier PDF '{pdf_filename}' a été créé avec succès.")


