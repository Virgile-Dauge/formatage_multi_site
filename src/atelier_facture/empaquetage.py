from pypdf import PdfReader
import pandas as pd
from pathlib import Path
from logger_config import logger

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
                .str.replace(r'\.0+$', '', regex=True))
    
    for pdf_file in pdf_files:
        reader = PdfReader(pdf_file)
        metadata = reader.metadata
        
        group_name = metadata.get('/GroupName', '')
        group_name = str(group_name).strip()
        invoice_id = metadata.get('/InvoiceID', '')
        pdl = str(metadata.get('/Pdl', '')).strip()
        # Cherche d'abord une correspondance dans la colonne 'group'
        mask = (df_copy['group'].astype(str).str.strip() == str(group_name).strip()) & (df_copy['group'].astype(str).str.strip() != '')
        
        # Check if any True values in group_mask
        if not mask.any():
            mask = df_copy['pdl'].fillna('').astype(str).str.strip() == pdl
        
        # def format_id(x, width:int=14) -> str:
        #     return x if x == '' else str(x).zfill(width)

        df_copy.loc[mask, 'BT-1'] = invoice_id
        # df_copy['BT-1'] = df_copy['BT-1'].apply(lambda x: format_id(x))
        df_copy.loc[mask, 'pdf'] = pdf_file

    return df_copy

def process_BT_csv(pdf_dir: Path, csv_dir: Path) -> pd.DataFrame | None:
    """
    Finds the initial CSV file (starting with 'BT') in the given directory,
    loads it, and applies the extract_metadata_and_update_df function to update it with PDF metadata.

    Args:
        directory (Path): The directory to search for the CSV and PDF files.

    Returns:
        pd.DataFrame: The updated DataFrame, or None if no CSV file is found.
    """
    # Find the CSV file
    csv_files = list(csv_dir.glob('BT*.csv'))
    if not csv_files:
        logger.warning(f"No CSV file starting with 'BT' found in {csv_dir}.")
        return None

    # Use the first CSV file found
    csv_file = csv_files[0]
    logger.info(f"Using CSV file: {csv_file}")

    # Load the CSV file
    df = pd.read_csv(csv_file).replace('–', '-', regex=True)

    # Find all PDF files in the directory
    pdf_files = list(pdf_dir.glob('*.pdf'))

    # Apply the extract_metadata_and_update_df function
    updated_df = extract_metadata_and_update_df(pdf_files, df)

    updated_df.to_csv(csv_dir / 'BT_updated.csv', index=False)

    return updated_df