import pandas as pd
from pathlib import Path
def compare_excel_sheets(file1: str, file2: str, sheet_name=0):
    # Lire les deux fichiers Excel
    df1 = pd.read_excel(file1, sheet_name=sheet_name)
    df2 = pd.read_excel(file2, sheet_name=sheet_name)

    # Comparer les DataFrames
    comparison = df1.compare(df2, keep_equal=False)

    # Afficher les lignes qui ont changé
    if not comparison.empty:
        print("Lignes qui ont changé:")
        print(comparison)
    else:
        print("Aucune différence trouvée.")
        
old = Path('~/data/enargia/batch_1/input/lien.xlsx').expanduser()
old = Path('~/data/enargia/batch_2/input/lien.xlsx').expanduser()
old = Path('~/data/enargia/batch_3/input/lien.xlsx').expanduser()
old = Path('~/data/enargia/batch_4/input/lien.xlsx').expanduser()
val = Path('~/data/enargia/details 86.xlsx').expanduser()

compare_excel_sheets(old, val)