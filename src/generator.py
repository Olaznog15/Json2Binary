"""Json2Class generator module

This module inspects a JSON structure and generates equivalent Python
dataclasses that mirror the JSON schema. The generator:

- Infers Python types for JSON values (primitives, lists, nested objects).
- Creates nested dataclasses for JSON objects and reuses types when
    structures match (deduplication based on keys+value types).
- Emits dataclasses with a `to_dict()` helper, `from_dict()` classmethod, and a `__post_init__`
    that converts nested dicts/lists into the corresponding dataclass
    instances at runtime.
- Converts JSON fields to valid Python identifiers correctly, and maps them in the dict processing paths.
- Processes special ENUM nodes to produce Python Enums instead of generic dataclasses.

Usage (from project root):

        python src/generator.py path/to/input.json

The generated file is written to `src/generated_class.py` by default.
"""

import json
import os
import sys
import hashlib
import re
import keyword
from typing import Any, Dict, List, Union, Optional

def clean_class_name(name: str) -> str:
    """
    Cleans a JSON key into a valid PascalCase Python identifier for classes.
    """
    if not name:
        return "GeneratedClass"
    name = re.sub(r'[^a-zA-Z0-9_\s-]', ' ', name)
    name = re.sub(r'[-\s_]+', '_', name).strip('_')
    
    if '_' in name:
        name = ''.join(x.title() for x in name.split('_') if x)
    else:
        name = name[0].upper() + name[1:] if name else "GeneratedClass"
    
    if name and name[0].isdigit():
        name = f"Class{name}"
    
    if not name:
        return "GeneratedClass"
    return name

def clean_field_name(name: str) -> str:
    """
    Cleans a JSON key into a valid snake_case or standard valid Python identifier for variables.
    """
    # Replace anything not a letter, number, or underscore with underscore
    name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Remove consecutive underscores
    name_clean = re.sub(r'_+', '_', name_clean).strip('_')
    
    if not name_clean:
        name_clean = "field"
        
    if name_clean[0].isdigit():
        name_clean = f"_{name_clean}"
        
    if keyword.iskeyword(name_clean):
        name_clean = f"{name_clean}_"
        
    return name_clean

def get_singular_name(name: str) -> str:
    """
    Simple heuristic to singularize a word.
    
    Currently just removes the trailing 's' if present.
    """
    if name.endswith('s'):
        return name[:-1]
    return name

def infer_type(value: Any, classes: Dict[str, str], structure_map: Dict[str, str], name_counts: Dict[str, int], field_name: str = None) -> str:
    """
    Infers the Python type string for a given JSON value and handles nested class generation.

    This function recursively determines the type of a value. If the value is a dictionary,
    it generates a new class (or reuses an existing one) and returns the class name.
    """
    # Primitive types
    if isinstance(value, bool):
        return 'bool'
    elif isinstance(value, int):
        return 'int'
    elif isinstance(value, float):
        return 'float'
    elif isinstance(value, str):
        return 'str'
    elif value is None:
        return 'Optional[Any]'
    elif isinstance(value, list):
        if not value:
            return 'List[Any]'
        
        # Determine singular name for items (used for naming item classes)
        item_name = None
        if field_name:
            item_name = get_singular_name(field_name)
            
        # Collect all unique types in the list
        types = set()
        for item in value:
            types.add(infer_type(item, classes, structure_map, name_counts, field_name=item_name))
        
        if len(types) == 1:
            return f'List[{list(types)[0]}]'
        else:
            union_types = ' | '.join(sorted(types))
            return f'List[{union_types}]'
    elif isinstance(value, dict):
        # We don't hash ENUM structures as standard structure, they are skipped in generate_class,
        # but if we somehow arrive here for a dict that we want to turn into a dataclass:
        
        structure_sig = json.dumps(
            {k: type(v).__name__ for k, v in sorted(value.items())},
            sort_keys=True,
        )
        dict_hash = hashlib.md5(structure_sig.encode()).hexdigest()[:8]

        # Reuse class name if this structural signature was already seen
        if dict_hash in structure_map:
            return structure_map[dict_hash]

        # Derive a human-friendly base name from the field name if present
        base_name = "GeneratedClass"
        if field_name:
            base_name = clean_class_name(field_name)

        # Ensure uniqueness against already used class names
        class_name = base_name
        counter = 0
        original_base = base_name
        while class_name in classes or class_name in name_counts:
            counter += 1
            class_name = f"{original_base}{counter}"

        # Register the structural signature before generating the body to
        # correctly handle recursive structures.
        structure_map[dict_hash] = class_name
        if class_name not in name_counts:
            name_counts[class_name] = 0

        classes[class_name] = generate_class(value, class_name, classes, structure_map, name_counts)
        return class_name
    else:
        return 'Any'

def generate_class(json_data: Dict[str, Any], class_name: str, classes: Dict[str, str], structure_map: Dict[str, str], name_counts: Dict[str, int]) -> str:
    """
    Generates the Python code for a dataclass based on a JSON dictionary.

    Iterates through the dictionary keys to define fields and their types.
    Adds a `to_dict` and `from_dict` method to handle potential JSON key transformations.
    Includes __post_init__ to convert nested dicts to class instances correctly.
    Supports converting "ENUM" key's children into Enum classes.
    """
    fields = []
    post_init_conversions = []
    key_map = {}
    inverse_key_map = {}
    
    for key, value in json_data.items():
        if key == "ENUM" and isinstance(value, dict):
            # Special logic for ENUM: Process its children to generate Enum classes
            for enum_name, enum_values in value.items():
                if isinstance(enum_values, dict):
                    safe_enum_name = clean_class_name(enum_name)
                    # Deduplicate name
                    counter = 0
                    original_enum_base = safe_enum_name
                    while safe_enum_name in classes or safe_enum_name in name_counts:
                        counter += 1
                        safe_enum_name = f"{original_enum_base}{counter}"
                    if safe_enum_name not in name_counts:
                        name_counts[safe_enum_name] = 0
                    
                    enum_lines = [f'class {safe_enum_name}(Enum):']
                    for k, val in enum_values.items():
                        # Using Option B: Keys are the numeric strings, and values are the Name of the enum representation
                        # E.g. {"1": "CRITICAL"}
                        safe_val = clean_field_name(str(val)).upper()
                        if safe_val == "_":
                            safe_val = f"ENUM_{k}"
                        try:
                            int_k = int(k)
                        except ValueError:
                            int_k = repr(k)
                        enum_lines.append(f'    {safe_val} = {int_k}')
                    
                    classes[safe_enum_name] = '\n'.join(enum_lines) + '\n'
            
            # The ENUM block itself doesn't need to be represented as strongly typed dataclasses in parent,
            # but we keep it functionally equivalent for JSON read/write compatibility
            safe_key = clean_field_name(key)
            if safe_key != key:
                key_map[safe_key] = key
                inverse_key_map[key] = safe_key
            fields.append(f'    {safe_key}: Dict[str, Any] = field(default_factory=lambda: {repr(value)})')
            continue

        safe_key = clean_field_name(key)
        if safe_key != key:
            key_map[safe_key] = key
            inverse_key_map[key] = safe_key

        typ = infer_type(value, classes, structure_map, name_counts, field_name=key)
        default_str = ""
        if isinstance(value, (str, int, float, bool)):
            default_str = f" = {repr(value)}"
        elif isinstance(value, list):
            if value:
                # For lists, store raw data as default and convert in __post_init__
                default_str = f" = field(default_factory=lambda: {repr(value)})"
                # Extract item class name from List[ClassName]
                if isinstance(value[0], dict):
                    item_type = typ[5:-1] if typ.startswith('List[') else 'dict'
                    post_init_conversions.append((safe_key, item_type, True))  # True = is_list
            else:
                default_str = " = field(default_factory=list)"
        elif isinstance(value, dict):
            # For nested objects, store raw data as default and convert in __post_init__
            sub_class_name = infer_type(value, classes, structure_map, name_counts, field_name=key)
            default_str = f" = field(default_factory=lambda: {repr(value)})"
            post_init_conversions.append((safe_key, sub_class_name, False))  # False = not is_list
        elif value is None:
            default_str = " = None"
        
        if 'Optional' in typ or typ == 'Any':
            typ = f'Optional[{typ}]'
        fields.append(f'    {safe_key}: {typ}{default_str}')
    
    # Build __post_init__ method if needed
    post_init_code = ""
    if post_init_conversions:
        post_init_lines = ["    def __post_init__(self) -> None:"]
        for field_name, nested_class_name, is_list in post_init_conversions:
            if is_list:
                post_init_lines.append(f"        if isinstance(self.{field_name}, list) and self.{field_name} and isinstance(self.{field_name}[0], dict):")
                post_init_lines.append(f"            self.{field_name} = [{nested_class_name}.from_dict(item) for item in self.{field_name}]")
            else:
                post_init_lines.append(f"        if isinstance(self.{field_name}, dict):")
                post_init_lines.append(f"            self.{field_name} = {nested_class_name}.from_dict(self.{field_name})")
        post_init_code = "\n" + "\n".join(post_init_lines)
    
    to_dict_local_map = f"        key_map = {repr(key_map)}\n" if key_map else "        key_map = {{}}\n"
    from_dict_local_map = f"        inverse_key_map = {repr(inverse_key_map)}\n" if inverse_key_map else "        inverse_key_map = {{}}\n"

    class_code = f'''@dataclass(slots=True)
class {class_name}:
{chr(10).join(fields)}{post_init_code}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> '{class_name}':
{from_dict_local_map}        init_kwargs = dict()
        for json_key, val in data.items():
            safe_key = inverse_key_map.get(json_key, json_key)
            if safe_key in cls.__dataclass_fields__:
                init_kwargs[safe_key] = val
        return cls(**init_kwargs)

    def to_dict(self) -> Dict[str, Any]:
        result = dict()
{to_dict_local_map}        for field_name in self.__dataclass_fields__:
            json_key = key_map.get(field_name, field_name)
            val = getattr(self, field_name)
            if isinstance(val, list):
                result[json_key] = [item.to_dict() if hasattr(item, 'to_dict') else item for item in val]
            elif hasattr(val, 'to_dict'):
                result[json_key] = val.to_dict()
            else:
                result[json_key] = val
        return result
'''
    return class_code

def main(input_json_path: str = None):
    """
    Main execution entry point.

    1. Determines input JSON path (arg or default).
    2. Loads JSON data.
    3. Generates the 'Root' class and all dependency classes.
    4. Writes the result to 'generated_class.py'.
    """
    if input_json_path is None:
        if len(sys.argv) > 1:
            input_json_path = sys.argv[1]
        else:
            input_json_path = os.path.join(os.path.dirname(__file__), '..', 'default.json')
    
    output_path = os.path.join(os.path.dirname(__file__), 'generated_class.py')
    
    try:
        with open(input_json_path, 'r') as f:
            json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found at {input_json_path}")
        return

    classes = {}
    structure_map = {} # Maps dict_key -> class_name
    name_counts = {}   # Maps base_name -> count
    
    # Generate root class
    # Derive class name from filename
    filename = os.path.basename(input_json_path)
    filename_no_ext = os.path.splitext(filename)[0]
    main_class_name = clean_class_name(filename_no_ext)
    
    main_class = generate_class(json_data, main_class_name, classes, structure_map, name_counts)
    
    # Combine all classes
    all_code = 'from __future__ import annotations\n\nfrom dataclasses import dataclass, field\nfrom enum import Enum\nfrom typing import Any, Dict, List, Optional\n\n'
    
    for class_name, class_code in classes.items():
        all_code += class_code + '\n'
    all_code += main_class
    
    with open(output_path, 'w') as f:
        f.write(all_code)
    
    print(f'Class generated successfully at {output_path}!')

if __name__ == '__main__':
    main()