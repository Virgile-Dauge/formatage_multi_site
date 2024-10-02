import os
from pypdf import PdfReader
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

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
    if 'pdl' not in df_copy.columns:
        df_copy['pdl'] = ''
    if 'group' not in df_copy.columns and 'facture' in df_copy.columns:
        df_copy = df_copy.rename(columns={'facture': 'group'})
    
    df_copy['group'] = df_copy['group'].astype(str).str.strip()

    for pdf_file in pdf_files:
        reader = PdfReader(pdf_file)
        metadata = reader.metadata
        
        group_name = metadata.get('/GroupName', '')
        group_name = str(group_name).strip()
        invoice_id = metadata.get('/InvoiceID', '')
        pdl = metadata.get('/Pdl', '')
        # Cherche d'abord une correspondance dans la colonne 'group'
        mask = df_copy['group'].str.lower() == group_name.lower()

        mask = mask if mask.any() else df_copy['pdl'] == pdl

        # First, convert the entire 'BT-1' column to string type
        df_copy['BT-1'] = df_copy['BT-1'].astype(str).apply(lambda x: x.rstrip('.0'))
        df_copy.loc[mask, 'BT-1'] = str(int(invoice_id))
        df_copy.loc[mask, 'pdf'] = pdf_file
        #print(group_name, pdl, mask.any())

    return df_copy
