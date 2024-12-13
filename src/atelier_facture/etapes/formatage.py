import pandas as pd
from pandas import DataFrame
from pathlib import Path

from facturix import process_invoices
def vers_facturx(consignes: DataFrame, facturx: DataFrame, output_dir: Path):
    
    # Fusionner bt_df avec df en utilisant 'BT-1' et 'id' comme clés
    merged_df = pd.merge(facturx, consignes[['id', 'pdf']], on='id', how='left')
    merged_df = merged_df.rename(columns={'id': 'BT-1'})
    # Supprimer la colonne 'id', elle n'est pas nécessaire après la fusion
    #merged_df = merged_df.drop('id', axis=1)
    print(merged_df)
    errors = process_invoices(merged_df, output_dir, output_dir, conform_pdf=False)
    return errors