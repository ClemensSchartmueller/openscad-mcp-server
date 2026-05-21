import re
from typing import Dict, Any, List, Union

def parse_customizer_comment(comment_str: str) -> Dict[str, Any]:
    """Parse customizer annotations inside the double slash comment.
    
    Examples:
        // [0:100] -> Range
        // [0:0.5:10] -> Range with step
        // [small, medium, large] -> Dropdown options
        // [10:Label A, 20:Label B] -> Dropdown option:label pairs
        // Simple descriptive comment -> description_extra
    """
    comment_str = comment_str.strip()
    
    # If it doesn't look like customizer brackets, treat as description suffix
    if not (comment_str.startswith('[') and comment_str.endswith(']')):
        return {"description_extra": comment_str}
        
    inside = comment_str[1:-1].strip()
    
    # Check if it's a numeric range [min:max] or [min:step:max] (no commas but contains colons)
    if ',' not in inside and ':' in inside:
        parts = [p.strip() for p in inside.split(':')]
        if len(parts) == 2:
            return {
                "type": "range",
                "min": _cast_numeric(parts[0]),
                "max": _cast_numeric(parts[1])
            }
        elif len(parts) == 3:
            return {
                "type": "range",
                "min": _cast_numeric(parts[0]),
                "step": _cast_numeric(parts[1]),
                "max": _cast_numeric(parts[2])
            }
            
    # Otherwise, it is a dropdown list of options
    # We split by comma, taking care of colon mappings (value:label)
    options = []
    # Split by comma (assumes option values don't have nested commas)
    raw_items = [item.strip() for item in inside.split(',') if item.strip()]
    
    for item in raw_items:
        if ':' in item:
            # Check for value:label mapping
            val_part, lbl_part = item.split(':', 1)
            val_part = val_part.strip()
            lbl_part = lbl_part.strip()
            
            # Strip quotes if string literal
            if val_part.startswith('"') and val_part.endswith('"'):
                val_part = val_part[1:-1]
            if lbl_part.startswith('"') and lbl_part.endswith('"'):
                lbl_part = lbl_part[1:-1]
                
            options.append({
                "value": _cast_numeric(val_part),
                "label": lbl_part
            })
        else:
            val_part = item
            if val_part.startswith('"') and val_part.endswith('"'):
                val_part = val_part[1:-1]
            
            cast_val = _cast_numeric(val_part)
            options.append({
                "value": cast_val,
                "label": str(cast_val)
            })
            
    if options:
        return {
            "type": "dropdown",
            "options": options
        }
        
    return {}


def _cast_numeric(val: str) -> Union[int, float, str, bool]:
    """Helper to convert string values to numeric types if possible, or boolean."""
    val_stripped = val.strip()
    if val_stripped == "true":
        return True
    if val_stripped == "false":
        return False
        
    try:
        if '.' in val_stripped:
            return float(val_stripped)
        return int(val_stripped)
    except ValueError:
        return val_stripped


def parse_scad(content: str) -> Dict[str, Any]:
    """Parse a .scad file content to extract customizer parameters, modules, and functions.
    
    We track block nesting (brace level) to ensure we only capture global parameters.
    """
    parameters = []
    modules = []
    functions = []
    
    lines = content.splitlines()
    current_section = "Parameters"
    description_acc = []
    
    brace_level = 0
    in_block_comment = False
    
    for line in lines:
        stripped = line.strip()
        
        # 1. Handle Block Comments /* ... */
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
                idx = stripped.find("*/")
                stripped = stripped[idx+2:].strip()
            else:
                continue
                
        if stripped.startswith("/*"):
            # Check for section header customizer syntax: /* [Section Name] */
            section_match = re.match(r'^/\*\s*\[([^\]]+)\]\s*\*/\s*$', stripped)
            if section_match:
                current_section = section_match.group(1).strip()
                description_acc = []
                continue
            elif "*/" in stripped:
                # Inline block comment - strip it out and continue parsing the rest of the line
                stripped = re.sub(r'/\*.*?\*/', '', stripped).strip()
            else:
                in_block_comment = True
                continue
                
        if not stripped:
            # Empty lines reset the accumulated preceding description comments
            description_acc = []
            continue
            
        # Count braces to track lexical scope (very simple parser, ignore braces in strings)
        # Note: We strip strings first to avoid matching braces inside them
        no_strings_line = re.sub(r'"(?:[^"\\]|\\.)*"', '', stripped)
        open_braces = no_strings_line.count('{')
        close_braces = no_strings_line.count('}')
        
        # 2. Check for module and function definitions (only at global level)
        if brace_level == 0:
            module_match = re.match(r'^\s*module\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)', stripped)
            if module_match:
                name = module_match.group(1)
                params_raw = module_match.group(2)
                params = [p.strip() for p in params_raw.split(',') if p.strip()]
                modules.append({
                    "name": name,
                    "parameters": params,
                    "description": "\n".join(description_acc) if description_acc else ""
                })
                description_acc = []
                brace_level += open_braces - close_braces
                continue
                
            func_match = re.match(r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)', stripped)
            if func_match:
                name = func_match.group(1)
                params_raw = func_match.group(2)
                params = [p.strip() for p in params_raw.split(',') if p.strip()]
                functions.append({
                    "name": name,
                    "parameters": params,
                    "description": "\n".join(description_acc) if description_acc else ""
                })
                description_acc = []
                brace_level += open_braces - close_braces
                continue
                
        # If we are currently inside a block (brace_level > 0), update brace level and skip parameters
        if brace_level > 0:
            brace_level += open_braces - close_braces
            if brace_level < 0:
                brace_level = 0
            description_acc = []
            continue
            
        # 3. Accumulated comments preceding a declaration
        if stripped.startswith("//"):
            comment_text = stripped[2:].strip()
            # Ignore separator lines (e.g. // ------)
            if comment_text and not re.match(r'^[-=_*#\s]+$', comment_text):
                description_acc.append(comment_text)
            continue
            
        # 4. Check for variable assignment at global scope
        # Syntax: name = value; // optional comment
        var_match = re.match(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;]+);(?:\s*//\s*(.*))?$', stripped)
        if var_match:
            name = var_match.group(1)
            val_raw = var_match.group(2).strip()
            comment_raw = var_match.group(3)
            
            # Determine type and value
            val = val_raw
            val_type = "expression"
            
            if val_raw == "true":
                val = True
                val_type = "boolean"
            elif val_raw == "false":
                val = False
                val_type = "boolean"
            elif val_raw.startswith('"') and val_raw.endswith('"'):
                val = val_raw[1:-1]
                val_type = "string"
            elif val_raw.startswith('[') and val_raw.endswith(']'):
                val_type = "vector"
                # Parse vector of numbers if possible
                try:
                    inner = val_raw[1:-1].strip()
                    val = [_cast_numeric(x.strip()) for x in inner.split(',') if x.strip()]
                except Exception:
                    val = val_raw # Fallback to raw string representation
            else:
                try:
                    if '.' in val_raw:
                        val = float(val_raw)
                        val_type = "float"
                    else:
                        val = int(val_raw)
                        val_type = "integer"
                except ValueError:
                    val = val_raw # keep expression string
                    
            # Parse customizer directives in the trailing comment
            customizer = {}
            description_extra = ""
            if comment_raw:
                customizer = parse_customizer_comment(comment_raw)
                description_extra = customizer.pop("description_extra", "")
                
            # Construct final description
            desc = "\n".join(description_acc) if description_acc else ""
            if description_extra:
                desc = f"{desc}\n{description_extra}".strip() if desc else description_extra
                
            param = {
                "name": name,
                "value": val,
                "type": val_type,
                "section": current_section,
                "description": desc
            }
            param.update(customizer)
            parameters.append(param)
            
            description_acc = [] # reset description accumulator
        else:
            # If we hit any other non-variable line at global scope, reset description accumulator
            brace_level += open_braces - close_braces
            if brace_level < 0:
                brace_level = 0
            description_acc = []
            
    return {
        "parameters": parameters,
        "modules": modules,
        "functions": functions
    }
