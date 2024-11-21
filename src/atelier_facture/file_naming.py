import re
from pathlib import Path

def compose_filename(file_dict: dict[str, str], format_type: str, separator: str='-') -> str:
    type_dict = {'group': 'G', 'pdl': 'U'}
    if format_type not in type_dict.keys():
        raise ValueError("Invalid format_type. Use 'group' or 'pdl'.")
    
    _validate_file_dict(file_dict, format_type)
    to_add = [type_dict[format_type], file_dict['date'], file_dict['client_name'], file_dict[format_type], file_dict['id']]
    return separator.join(to_add)

def _validate_file_dict(file_dict: dict[str, str], format_type: str) -> None:
    required_keys = {'date', 'client_name', 'id'}
    if not required_keys.issubset(file_dict.keys()):
        raise ValueError(f"Missing required keys. Required: {required_keys}")
    
    if not re.match(r'^\d{14}$', file_dict['id']):
        raise ValueError("id must be a 14-digit number")
    
    if format_type == 'pdl':
        if 'pdl' not in file_dict or not re.match(r'^\d{14}$', file_dict['pdl']):
            raise ValueError("PDL must be present and be a 14-digit number for 'pdl' format")
    elif format_type == 'group':
        if 'group' not in file_dict:
            raise ValueError("group must be present for 'group' format")
    else:
        raise ValueError("Invalid format_type. Use 'group' or 'pdl'.")

def interpret_filename(filename: str, separator: str='-') -> dict[str, str]:
    # Remove the file extension if present
    filename_without_ext = Path(filename).stem
    
    parts = filename_without_ext.split(separator)
    if len(parts) < 5:
        raise ValueError("Filename format is incorrect, expected at least 5 parts.")
    
    # Extract fixed parts
    type_letter, date, client_name, identifier = parts[0], parts[1], parts[2], parts[-1]
    
    # Determine format type based on type letter
    if type_letter == 'G':
        format_type = 'group'
    elif type_letter == 'U':
        format_type = 'pdl'
    else:
        raise ValueError("Invalid type letter. Use 'G' for group or 'P' for pdl.")
    
    # Extract the 'group' or 'pdl' part, which may contain separators
    group_or_pdl = separator.join(parts[3:-1])
    
    # Construct the resulting dictionary
    file_dict = {
        'date': date,
        'client_name': client_name,
        'id': identifier,
        'type': format_type,
        format_type: group_or_pdl
    }
    
    return file_dict

def main():
    # Test case 1: Valid 'group' format
    group_dict = {
        'date': '20230601',
        'client_name': 'ClientA',
        'group': 'GroupX',
        'id': '12345678901234'
    }
    print("Test 1 (Valid 'group' format):")
    print(compose_filename(group_dict, 'group'))

    group_dict = {
        'date': '20230601',
        'client_name': 'ClientA',
        'pdl': '12345678901234',
        'id': '11111111111111'
    }
    print("Test 1bis (Valid 'pdl' format):")
    print(compose_filename(group_dict, 'pdl'))

    # Test case 2: Valid 'pdl' format
    pdl_dict = {
        'date': '20230602',
        'client_name': 'ClientB',
        'pdl': '98765432109876',
        'id': '56789012345678'
    }
    print("\nTest 2 (Valid 'pdl' format):")
    print(compose_filename(pdl_dict, 'pdl'))

    # Test case 3: Invalid id (not 14 digits)
    invalid_id_dict = {
        'date': '20230603',
        'client_name': 'ClientC',
        'group': 'GroupY',
        'id': '123456'  # Invalid: not 14 digits
    }
    print("\nTest 3 (Invalid id):")
    try:
        print(compose_filename(invalid_id_dict, 'group'))
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