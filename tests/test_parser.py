import os
import pytest
from scad_parser import parse_customizer_comment, parse_scad

def test_parse_range_comments():
    # Simple range
    res = parse_customizer_comment("[0:100]")
    assert res == {"type": "range", "min": 0, "max": 100}

    # Float range with step
    res = parse_customizer_comment("[0.5:0.1:2.5]")
    assert res == {"type": "range", "min": 0.5, "step": 0.1, "max": 2.5}

    # Negative values
    res = parse_customizer_comment("[-10:10]")
    assert res == {"type": "range", "min": -10, "max": 10}


def test_parse_dropdown_comments():
    # List of options (strings)
    res = parse_customizer_comment("[small, medium, large]")
    assert res == {
        "type": "dropdown",
        "options": [
            {"value": "small", "label": "small"},
            {"value": "medium", "label": "medium"},
            {"value": "large", "label": "large"}
        ]
    }

    # List of option:label mappings (with numbers and strings)
    res = parse_customizer_comment('[10:Ten, 20:Twenty, "30":Thirty]')
    assert res == {
        "type": "dropdown",
        "options": [
            {"value": 10, "label": "Ten"},
            {"value": 20, "label": "Twenty"},
            {"value": 30, "label": "Thirty"}
        ]
    }


def test_parse_non_customizer_comments():
    res = parse_customizer_comment("This is a simple descriptive comment")
    assert res == {"description_extra": "This is a simple descriptive comment"}


def test_parse_scad_fixture():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "test_model.scad")
    with open(fixture_path, "r", encoding="utf-8") as f:
        content = f.read()

    result = parse_scad(content)

    # 1. Check parameters
    params = {p["name"]: p for p in result["parameters"]}
    
    assert "box_height" in params
    assert params["box_height"]["value"] == 50
    assert params["box_height"]["type"] == "range"
    assert params["box_height"]["section"] == "Box Dimensions"
    assert params["box_height"]["min"] == 10
    assert params["box_height"]["max"] == 150
    assert "Height of the main container body" in params["box_height"]["description"]

    assert "wall_thickness" in params
    assert params["wall_thickness"]["value"] == 2.4
    assert params["wall_thickness"]["type"] == "range"
    assert params["wall_thickness"]["min"] == 1
    assert params["wall_thickness"]["step"] == 0.2
    assert params["wall_thickness"]["max"] == 10
    assert "Wall thickness of the box" in params["wall_thickness"]["description"]

    assert "lid_type" in params
    assert params["lid_type"]["value"] == "sliding"
    assert params["lid_type"]["section"] == "Lid Parameters"
    assert params["lid_type"]["type"] == "dropdown"
    assert len(params["lid_type"]["options"]) == 3
    assert params["lid_type"]["options"][0] == {"value": "sliding", "label": "sliding"}

    assert "ventilation" in params
    assert params["ventilation"]["value"] is True
    assert params["ventilation"]["type"] == "boolean"

    assert "vent_grid" in params
    assert params["vent_grid"]["value"] == [10, 10]
    assert params["vent_grid"]["type"] == "vector"

    assert "hidden_internal" in params
    assert params["hidden_internal"]["value"] == 42
    assert params["hidden_internal"]["type"] == "integer"
    assert params["hidden_internal"]["section"] == "Lid Parameters"

    # 2. Check modules
    modules = {m["name"]: m for m in result["modules"]}
    assert "box" in modules
    assert modules["box"]["parameters"] == ["h", "w", "t"]

    # 3. Check functions
    functions = {f["name"]: f for f in result["functions"]}
    assert "calculate_volume" in functions
    assert functions["calculate_volume"]["parameters"] == ["h", "w"]
