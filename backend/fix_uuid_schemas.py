"""
Script to fix UUID serialization in Pydantic v2 schemas.

Strategy:
1. For RESPONSE schemas (output schemas): Change UUID fields to str type
2. For REQUEST schemas (input schemas): Keep UUID type but remove json_encoders
   (Pydantic v2 handles UUID serialization automatically)
3. Remove all json_encoders={UUID: str} lines
"""
import re
from collections import defaultdict
from pathlib import Path

schema_dir = Path('presentation/schemas')

# Keywords that indicate a response/output schema
RESPONSE_INDICATORS = [
    'Response', 'Out', 'ListResponse', 'DetailResponse',
    'Item', 'PublicItem', 'Child', 'Group', 'Option'
]

# Keywords that indicate a request/input schema
REQUEST_INDICATORS = [
    'Request', 'Create', 'Update', 'Body', 'Params', 'Filter',
    'Query', 'In'
]

def is_response_schema(class_name: str) -> bool:
    """Determine if a class is a response schema based on naming conventions."""
    lower = class_name.lower()
    return any(ind.lower() in lower for ind in RESPONSE_INDICATORS)

def is_request_schema(class_name: str) -> bool:
    """Determine if a class is a request schema based on naming conventions."""
    lower = class_name.lower()
    return any(ind.lower() in lower for ind in REQUEST_INDICATORS)

def process_file(filepath: Path) -> dict[str, int | str]:  # noqa: PLR0912
    """Process a single schema file."""
    content = filepath.read_text()
    original = content

    changes: dict[str, int | str] = {
        'file': filepath.name,
        'json_encoders_removed': 0,
        'uuid_to_str_converted': 0,
        'json_encoders_lines_removed': 0,
    }

    # Find all model_config = ConfigDict(json_encoders={UUID: str}) occurrences
    # Pattern matches the line with optional preceding whitespace

    # We need to process class by class to know which fields to convert
    # First, let's find all class definitions and their json_encoders lines
    lines = content.split('\n')
    current_class = None

    # Simple approach: find and replace json_encoders lines, then convert UUID fields in response classes
    json_encoders_lines = []
    for i, line in enumerate(lines):
        class_match = re.match(r'^[ \t]*class\s+(\w+)\(BaseModel\):', line)
        if class_match:
            current_class = class_match.group(1)

        if 'json_encoders={UUID: str}' in line or 'json_encoders= {UUID: str}' in line:
            json_encoders_lines.append((i, current_class, line))

    # Build a set of response class names that have json_encoders
    response_classes = set()
    request_classes = set()
    for _idx, class_name, _line in json_encoders_lines:
        if class_name is None:
            continue
        if is_response_schema(class_name):
            response_classes.add(class_name)
        elif is_request_schema(class_name):
            request_classes.add(class_name)
        else:
            # Ambiguous - treat as response if it has UUID fields
            response_classes.add(class_name)

    # Now process line by line
    result_lines = []
    current_class = None

    for _i, original_line in enumerate(lines):
        class_match = re.match(r'^(\s*)class\s+(\w+)\(BaseModel\):', original_line)
        if class_match:
            current_class = class_match.group(2)

        # Skip json_encoders lines
        if 'json_encoders={UUID: str}' in original_line or 'json_encoders= {UUID: str}' in original_line:
            changes['json_encoders_lines_removed'] = int(
                changes['json_encoders_lines_removed']
            ) + 1
            # Also check if there was a duplicate model_config line right after
            continue

        # Convert UUID fields to str in response classes
        line = original_line
        if current_class in response_classes:
            # Match UUID field declarations (not in comments, not inside strings)
            # Pattern: field_name: UUID | None = ... or field_name: UUID
            uuid_pattern = r'^(\s*)(\w+)(\s*:\s*)UUID(\s*(?:\|.*)?)$'
            match = re.match(uuid_pattern, line)
            if match:
                indent = match.group(1)
                field_name = match.group(2)
                colon = match.group(3)
                rest = match.group(4)
                line = f'{indent}{field_name}{colon}str{rest}'
                changes['uuid_to_str_converted'] = int(
                    changes['uuid_to_str_converted']
                ) + 1

        result_lines.append(line)

    new_content = '\n'.join(result_lines)

    # Write if changed
    if new_content != original:
        filepath.write_text(new_content)
        return changes

    return changes


# Process all files
total_changes: defaultdict[str, int] = defaultdict(int)
files_changed = 0

for pyfile in sorted(schema_dir.glob('*.py')):
    content = pyfile.read_text()
    if 'json_encoders={UUID: str}' not in content:
        continue

    changes = process_file(pyfile)
    removed_lines = int(changes['json_encoders_lines_removed'])
    if removed_lines > 0:
        files_changed += 1
        for k, v in changes.items():
            if k != 'file':
                total_changes[k] += int(v)
