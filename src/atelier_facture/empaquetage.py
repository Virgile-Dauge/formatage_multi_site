from pypdf import PdfReader
import pandas as pd
from pathlib import Path

def extract_metadata_and_update_df(pdf_files: list[Path], df: pd.DataFrame) -> pd.DataFrame:
    """
    Extrait les métadonnées des fichiers PDF et met à jour une copie du DataFrame existant.

    Pour chaque PDF, cette fonction crée ou met à jour une colonne 'BT-1' avec le numéro de facture.
    Elle recherche d'abord une correspondance dans la colonne 'group', puis dans la colonne 'pdl'.

    Args:
        pdf_files (List[str]): Une liste de chemins vers les fichiers PDF.
        df (pd.DataFrame): Le DataFrame existant à mettre à jour.

    Returns:
        pd.DataFrame: Une copie du DataFrame mise à jour avec la nouvelle colonne 'BT-1'.
    """
    df_copy = df.copy()

    if 'BT-1' not in df_copy.columns:
        df_copy['BT-1'] = ''
    if 'pdl' not in df_copy.columns and 'PRM' in df_copy.columns:
        df_copy = df_copy.rename(columns={'PRM': 'pdl'})
    if 'pdl' not in df_copy.columns:
        df_copy['pdl'] = ''
    if 'group' not in df_copy.columns and 'facture' in df_copy.columns:
        df_copy = df_copy.rename(columns={'facture': 'group'})
    
    if 'group' not in df_copy.columns:
        df_copy['group'] = ''
    df_copy['group'] = df_copy['group'].fillna('').astype(str).str.strip()
    df_copy['pdl'] = df_copy['pdl'].fillna('').astype(str).str.strip()

    id_columns = ['BT-1', 'BT-13']
    for col in id_columns:
        if col in df_copy.columns:
            df_copy[col] = (df_copy[col]
                .apply(lambda x: '' if pd.isna(x) else str(x))
                .str.rstrip('.0'))
    
    for pdf_file in pdf_files:
        reader = PdfReader(pdf_file)
        metadata = reader.metadata
        
        group_name = metadata.get('/GroupName', '')
        group_name = str(group_name).strip()
        invoice_id = metadata.get('/InvoiceID', '')
        pdl = str(metadata.get('/Pdl', '')).strip()
        # Cherche d'abord une correspondance dans la colonne 'group'
        mask = df_copy['group'].astype(str).str.strip() == str(group_name).strip()

        # Check if any True values in group_mask
        if not mask.any():
            mask = df_copy['pdl'].fillna('').astype(str).str.strip() == pdl
        
        def format_id(x, width:int=14) -> str:
            return x if x == '' else str(x).rstrip('.0').zfill(width)

        df_copy.loc[mask, 'BT-1'] = invoice_id
        df_copy['BT-1'] = df_copy['BT-1'].apply(lambda x: format_id(x))
        df_copy.loc[mask, 'pdf'] = pdf_file

    return df_copy
