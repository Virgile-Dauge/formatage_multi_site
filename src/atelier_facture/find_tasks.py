import pandas as pd
from pandas import DataFrame
from pathlib import Path

from file_naming import compose_filename
from mpl import export_table_as_pdf
from pdf_utils import concat_pdfs

def fusion_groupes(df: DataFrame, output_dir: Path):
    # Grouper par 'groupement'
    grouped = df.groupby('groupement')
    
    # Dictionnaire pour stocker le résultat
    group_prm_dict = {}
    
    # Parcourir chaque groupement
    for group_name, group_data in grouped:
        # TODO: Gestion des groupements mono-pdl...
        # Extraire les métadonnées du groupement (seule ligne sans pdl)
        group_mask = (group_data['pdl'].isna() | (group_data['pdl'] == ''))
        no_prm_rows = group_data[group_mask]
        group_meta = no_prm_rows.to_dict(orient='records')[0]

        to_concat = [group_meta['fichier']]
        
        # Extraction des lignes pdl 
        pdl = group_data[~group_mask]

        # On crée le pdf tableau
        table_name = output_dir / f"{compose_filename(group_meta, format_type='table')}.pdf"
        export_table_as_pdf(pdl, table_name)

        # On ajoute le tableau crée  
        to_concat += [table_name]
        # Liste des PRM pour ce groupement (exclure les valeurs manquantes)
        to_concat += pdl['fichier'].tolist()
        print(to_concat)
        # Fichier de groupement enrichi 
        enhanced_pdf = output_dir / f"{compose_filename(group_meta, format_type='groupement')}.pdf"
        print(enhanced_pdf)
        
        # Créer la facture groupement enrichie avec le tableau et les PRM
        #concat_pdfs(to_concat, output_dir / f"{compose_filename(group_meta, format_type='group')}.pdf")
    
    return group_prm_dict

if __name__ == "__main__":
    # Exemple d'utilisation
    data = {
        'id': ['12345678910111', '12345678910112', '12345678910113', '12345678910114', '12345678910115', '12345678910116'],
        'membre': ['A', 'B', 'C', 'D', 'E', 'F'],
        'site': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
        'pdl': ['', 'PRM1', '', 'PRM2', 'PRM3', ''],
        'groupement': ['G1', 'G1', 'G2', 'G2', 'G2', 'G3'],
        'date': ['20230101', '20230102', '20230103', '20230104', '20230105', '20230106'],
        'fichier': ['fichier1', 'fichier2', 'fichier3', 'fichier4', 'fichier5', 'fichier6']
    }

    df = pd.DataFrame(data)

    op = Path("~/data/enargia/tests/").expanduser()
    result = fusion_groupes(df, op)
    print(df)
    print(result)