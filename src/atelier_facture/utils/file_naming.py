import re
from pathlib import Path

def compose_filename(file_dict: dict[str, str], format_type: str, separator: str='-') -> str:
    """
    Compose un nom de fichier en utilisant les informations fournies dans `file_dict` et le type de format.

    :param file_dict: Dictionnaire contenant des clés telles que 'date', 'client_name', 'id', et éventuellement 'group' ou 'pdl'.
                      - 'date': La date associée au fichier (par exemple, date de la facture).
                      - 'client_name': Le nom du client.
                      - 'id': Un identifiant de 14 chiffres pour le fichier.
                      - 'groupement': (optionnel) Le nom du groupe, requis si `format_type` est 'group'.
                      - 'pdl': (optionnel) Le nom du PDL, requis si `format_type` est 'pdl'.
    :param format_type: Le type de format à utiliser, soit 'group' soit 'pdl'. Détermine si 'group' ou 'pdl' est utilisé dans le nom de fichier.
    :param separator: Le caractère utilisé pour séparer les différentes parties du nom de fichier. Par défaut, '-'.
    :return: Une chaîne représentant le nom de fichier composé.
    :raises ValueError: Si `format_type` n'est pas 'group' ou 'pdl', ou si des clés requises sont manquantes dans `file_dict`.
    """
    type_dict = {'groupement': 'G', 'pdl': 'U', 'table': 'T'}
    if format_type not in type_dict.keys():
        raise ValueError("Invalid format_type. Use 'groupement','pdl' or 'table'.")
    
    _validate_file_dict(file_dict, format_type)
    to_add = [type_dict[format_type], 
              file_dict['date'], 
              file_dict['membre'], 
              file_dict['pdl' if format_type == 'pdl' else 'groupement'], 
              file_dict['id']]
    return separator.join(to_add)

def _validate_file_dict(file_dict: dict[str, str], format_type: str) -> None:
    """
    Validate the `file_dict` to ensure it contains the necessary keys and follows the required format based on `format_type`.

    :param file_dict: Dictionary containing file-related information.
                      - 'date': The date associated with the file (e.g., invoice date).
                      - 'client_name': The name of the client.
                      - 'id': A 14-digit identifier for the file.
                      - 'groupement': (optional) The group name, required if `format_type` is 'group'.
                      - 'pdl': (optional) The PDL name, required if `format_type` is 'pdl'.
    :param format_type: The type of format to use, either 'group' or 'pdl'. Determines the validation logic.
    :raises ValueError: If required keys are missing, or if the values do not match the expected patterns.
    """
    required_keys = {'date', 'membre', 'id'}
    if not required_keys.issubset(file_dict.keys()):
        raise ValueError(f"Missing required keys. Required: {required_keys}")
    
    if not re.match(r'^\d{14}$', file_dict['id']):
        raise ValueError(f"id must be a 14-digit number. Found instead :{file_dict['id']}")
    
    if format_type == 'pdl':
        if 'pdl' not in file_dict or not re.match(r'^\d{14}$', file_dict['pdl']):
            raise ValueError("PDL must be present and be a 14-digit number for 'pdl' format")
    elif format_type == 'groupement' or format_type == 'table':
        if 'groupement' not in file_dict:
            raise ValueError("groupement must be present for 'group' or 'table' format")
    else:
        raise ValueError("Invalid format_type. Use 'groupement' or 'pdl'.")

def interpret_filename(filename: str, separator: str='-') -> dict[str, str]:
    """
    Valide le `file_dict` pour s'assurer qu'il contient les clés nécessaires et respecte le format requis selon `format_type`.

    :param file_dict: Dictionnaire contenant les informations liées au fichier.
                      - 'date': La date associée au fichier (par exemple, date de la facture).
                      - 'client_name': Le nom du client.
                      - 'id': Un identifiant de 14 chiffres pour le fichier.
                      - 'group': (optionnel) Le nom du groupe, requis si `format_type` est 'group'.
                      - 'pdl': (optionnel) Le nom du PDL, requis si `format_type` est 'pdl'.
    :param format_type: Le type de format à utiliser, soit 'group' soit 'pdl'. Détermine la logique de validation.
    :raises ValueError: Si des clés requises sont manquantes ou si les valeurs ne correspondent pas aux motifs attendus.
    """
    # Remove the file extension if present
    filename_without_ext = Path(filename).stem
    
    parts = filename_without_ext.split(separator)
    if len(parts) < 5:
        raise ValueError("Filename format is incorrect, expected at least 5 parts.")
    
    # Extract fixed parts
    type_letter, date, client_name, identifier = parts[0], parts[1], parts[2], parts[-1]
    
    # Determine format type based on type letter
    if type_letter == 'G':
        format_type = 'groupement'
    elif type_letter == 'U':
        format_type = 'pdl'
    elif type_letter == 'T':
        format_type = 'table'
    else:
        raise ValueError("Invalid type letter. Use 'G' for groupement or 'U' for pdl or 'T' for table")
    
    # Extract the 'group' or 'pdl' part, which may contain separators
    group_or_pdl = separator.join(parts[3:-1])
    
    # Construct the resulting dictionary
    file_dict = {
        'date': date,
        'membre': client_name,
        'id': identifier,
        'type': format_type,
        format_type: group_or_pdl
    }
    
    return file_dict

def abbreviate_long_text_to_acronym(text: str, max_length: int=20, max_word_length: int=8) -> str:
    """
    Crée un acronyme pour un texte s'il dépasse une longueur maximale spécifiée et qu'au moins un mot a une longueur supérieure ou égale à 10.

    :param text: Le texte à vérifier.
    :param max_length: La longueur maximale du texte.
    :return: L'acronyme si une condition est remplie, ou le texte original.
    """
    words = text.split()
    if len(text) > max_length and any(len(word) >= max_word_length for word in words):
        acronym = ''.join(word[0].upper() for word in words if word)
        return acronym
    return text

def main():
    # Test case 1: Valid 'group' format
    group_dict = {
        'date': '20230601',
        'membre': 'ClientA',
        'groupement': 'GroupX',
        'id': '12345678901234'
    }
    print("Test 1 (Valid 'groupement' format):")
    print(compose_filename(group_dict, 'groupement'))

    group_dict = {
        'date': '20230601',
        'membre': 'ClientA',
        'pdl': '12345678901234',
        'id': '11111111111111'
    }
    print("Test 1bis (Valid 'pdl' format):")
    print(compose_filename(group_dict, 'pdl'))

    # Test case 2: Valid 'pdl' format
    pdl_dict = {
        'date': '20230602',
        'membre': 'ClientB',
        'pdl': '98765432109876',
        'id': '56789012345678'
    }
    print("\nTest 2 (Valid 'pdl' format):")
    print(compose_filename(pdl_dict, 'pdl'))

    # Test case 3: Invalid id (not 14 digits)
    invalid_id_dict = {
        'date': '20230603',
        'membre': 'ClientC',
        'groupement': 'GroupY',
        'id': '123456'  # Invalid: not 14 digits
    }
    print("\nTest 3 (Invalid id):")
    try:
        print(compose_filename(invalid_id_dict, 'groupement'))
    except ValueError as e:
        print(f"Error: {e}")

    # Test case 4: Interpret filename group
    filename = "G-20230604-ClientD-GroupZ-11223344556677.pdf"
    print("\nTest 4 (Interpret filename):")
    print(interpret_filename(filename))

    # Test case 5: Interpret filename pdl
    filename = "U-20230604-ClientD-11223344556677-11223344556677.pdf"
    print("\nTest 5 (Interpret filename):")
    print(interpret_filename(filename))
    
    # Test case 6: Interpret filename group
    filename = "G-20230604-ClientD-11qwr-34q45-566e77-11223344556677.pdf"
    print("\nTest 6 (Interpret filename):")
    print(interpret_filename(filename))
if __name__ == "__main__":
    main()