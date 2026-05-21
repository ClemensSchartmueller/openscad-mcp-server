/* [Box Dimensions] */

// Height of the main container body
box_height = 50; // [10:150]

// Wall thickness of the box
wall_thickness = 2.4; // [1:0.2:10]

/* [Lid Parameters] */

// Type of cover lid
lid_type = "sliding"; // [sliding, snap-on, screw-on]

// Whether the lid has ventilation slots
ventilation = true;

// Grid size for venting holes (width, height)
vent_grid = [10, 10];

// Description for non-customizer variable (should be ignored by customizer but parsed)
hidden_internal = 42; 

module box(h, w, t) {
    difference() {
        cube([w, w, h], center = true);
        cube([w - t*2, w - t*2, h - t*2], center = true);
    }
}

function calculate_volume(h, w) = h * w * w;
