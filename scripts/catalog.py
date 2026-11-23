"""Sample product catalogue used to generate the demo datasheets.

All manufacturers, model names and figures are FICTIONAL. They are realistic in
range for mobile hydraulics, but do not describe any real product. Replace the
generated PDFs with real public datasheets to use the tool for real work.

Values here are in canonical units (cm3/rev, bar, rpm, L/min, kg). The PDF
generator converts them into each brand's own units and labels.
"""

REFERENCE_BRAND = "Ostwerk"  # stands in for "our own" portfolio

# fmt: off
REFERENCE = [
    # Axial piston pumps, variable displacement
    dict(model="OW-A28",  type="axial_piston_pump", circuit="open",   mounting="SAE B", displacement=28,  max_pressure=350, cont_pressure=280, max_speed=3000, weight=15.0,
         control="Pressure compensator, load-sensing (LS) and electro-proportional displacement control."),
    dict(model="OW-A45",  type="axial_piston_pump", circuit="open",   mounting="SAE B", displacement=45,  max_pressure=350, cont_pressure=280, max_speed=2600, weight=21.0,
         control="Pressure compensator, load-sensing (LS) and electro-proportional displacement control."),
    dict(model="OW-A45C", type="axial_piston_pump", circuit="closed", mounting="SAE B", displacement=45,  max_pressure=450, cont_pressure=400, max_speed=3300, weight=38.0,
         control="Hydrostatic transmission pump with integrated charge pump, electric and hydraulic servo control."),
    dict(model="OW-A71",  type="axial_piston_pump", circuit="open",   mounting="SAE C", displacement=71,  max_pressure=400, cont_pressure=350, max_speed=2400, weight=34.0,
         control="Pressure compensator, load-sensing (LS), power (torque) limiter."),
    dict(model="OW-A100", type="axial_piston_pump", circuit="open",   mounting="SAE C", displacement=100, max_pressure=400, cont_pressure=350, max_speed=2200, weight=47.0,
         control="Pressure compensator, load-sensing (LS), power (torque) limiter."),
    # External gear pumps, fixed displacement
    dict(model="OW-G8",   type="external_gear_pump", circuit="open", mounting="SAE A", displacement=8,    max_pressure=280, cont_pressure=250, max_speed=4000, weight=3.1,
         control="Fixed displacement, aluminium body, optional integrated relief valve."),
    dict(model="OW-G16",  type="external_gear_pump", circuit="open", mounting="SAE A", displacement=16,   max_pressure=280, cont_pressure=250, max_speed=3500, weight=3.9,
         control="Fixed displacement, aluminium body, optional integrated relief valve."),
    dict(model="OW-G22",  type="external_gear_pump", circuit="open", mounting="SAE A", displacement=22.5, max_pressure=250, cont_pressure=220, max_speed=3000, weight=4.6,
         control="Fixed displacement, aluminium body, optional integrated relief valve."),
    dict(model="OW-G32",  type="external_gear_pump", circuit="open", mounting="SAE B", displacement=32,   max_pressure=210, cont_pressure=190, max_speed=3000, weight=5.8,
         control="Fixed displacement, aluminium body, optional integrated relief valve."),
    # Directional spool valves
    dict(model="OW-D6",   type="directional_valve", size="NG6",  max_pressure=350, max_flow=80,  weight=1.5,
         control="Solenoid-operated 4/3 directional spool valve, wet-pin DC solenoids, manual override."),
    dict(model="OW-D6H",  type="directional_valve", size="NG6",  max_pressure=350, max_flow=120, weight=1.7,
         control="High-flow solenoid-operated 4/3 directional spool valve, wet-pin DC solenoids."),
    dict(model="OW-D10",  type="directional_valve", size="NG10", max_pressure=315, max_flow=160, weight=4.3,
         control="Solenoid-operated 4/3 directional spool valve, wet-pin DC solenoids, manual override."),
]

COMPETITORS = {
    # US units and US wording
    "Norhydra": [
        dict(model="NH-P30",  type="axial_piston_pump", circuit="open", mounting="SAE B", displacement=30, max_pressure=345, cont_pressure=276, max_speed=2900, weight=15.0,
             control="Pressure compensated with load sense option and electronic proportional control.", expected="OW-A28"),
        dict(model="NH-P48",  type="axial_piston_pump", circuit="open", mounting="SAE B", displacement=48, max_pressure=345, cont_pressure=276, max_speed=2600, weight=22.0,
             control="Pressure compensated with load sense option and electronic proportional control.", expected="OW-A45"),
        dict(model="NH-P74",  type="axial_piston_pump", circuit="open", mounting="SAE C", displacement=74, max_pressure=400, cont_pressure=345, max_speed=2300, weight=35.0,
             control="Pressure compensated, load sense, horsepower limiter.", expected="OW-A71"),
        dict(model="NH-G16",  type="external_gear_pump", circuit="open", mounting="SAE A", displacement=16.4, max_pressure=248, cont_pressure=207, max_speed=3300, weight=4.1,
             control="Fixed displacement gear pump, cast aluminium housing.", expected="OW-G16"),
        dict(model="NH-V03",  type="directional_valve", size="NG6",  max_pressure=345, max_flow=79.5, weight=1.6,
             control="Solenoid operated directional control valve, 4-way 3-position, wet armature coils.", expected="OW-D6"),
        dict(model="NH-V05",  type="directional_valve", size="NG10", max_pressure=317, max_flow=151, weight=4.5,
             control="Solenoid operated directional control valve, 4-way 3-position, wet armature coils.", expected="OW-D10"),
    ],
    # Metric with MPa and DIN-style symbols
    "Vantek": [
        dict(model="VT-AX45",   type="axial_piston_pump", circuit="open",   mounting="SAE B", displacement=46, max_pressure=350, cont_pressure=280, max_speed=2700, weight=21.5,
             control="Pressure cut-off, LS control, proportional solenoid control.", expected="OW-A45"),
        dict(model="VT-AX45CL", type="axial_piston_pump", circuit="closed", mounting="SAE B", displacement=46, max_pressure=420, cont_pressure=380, max_speed=3200, weight=37.0,
             control="Variable pump for closed loop hydrostatic drives, boost pump included, servo control.", expected="OW-A45C"),
        dict(model="VT-AX100",  type="axial_piston_pump", circuit="open",   mounting="SAE C", displacement=98, max_pressure=380, cont_pressure=330, max_speed=2200, weight=48.0,
             control="Pressure cut-off, LS control, torque limiter.", expected="OW-A100"),
        dict(model="VT-G19",    type="external_gear_pump", circuit="open", mounting="SAE A", displacement=19.5, max_pressure=275, cont_pressure=240, max_speed=3200, weight=4.2,
             control="External gear pump, fixed displacement.", expected="OW-G16"),
        dict(model="VT-G22",    type="external_gear_pump", circuit="open", mounting="SAE A", displacement=22, max_pressure=250, cont_pressure=220, max_speed=2800, weight=4.5,
             control="External gear pump, fixed displacement.", expected="OW-G22"),
        dict(model="VT-D6",     type="directional_valve", size="NG6", max_pressure=315, max_flow=100, weight=1.6,
             control="4/3 directional valve, direct operated, DC solenoid.", expected="OW-D6H"),
    ],
    # Metric bar, long-form wording, CETOP sizes
    "Caldera": [
        dict(model="CF-AP28",  type="axial_piston_pump", circuit="open", mounting="SAE B", displacement=25,  max_pressure=315, cont_pressure=250, max_speed=3100, weight=14.0,
             control="Constant pressure regulator, load sensing regulator, electrohydraulic control.", expected="OW-A28"),
        dict(model="CF-AP71",  type="axial_piston_pump", circuit="open", mounting="SAE C", displacement=71,  max_pressure=380, cont_pressure=320, max_speed=2400, weight=33.0,
             control="Constant pressure regulator, load sensing regulator, power regulator.", expected="OW-A71"),
        dict(model="CF-AP100", type="axial_piston_pump", circuit="open", mounting="SAE C", displacement=105, max_pressure=400, cont_pressure=350, max_speed=2100, weight=49.0,
             control="Constant pressure regulator, load sensing regulator, power regulator.", expected="OW-A100"),
        dict(model="CF-GP8",   type="external_gear_pump", circuit="open", mounting="SAE A", displacement=8.2, max_pressure=270, cont_pressure=240, max_speed=3800, weight=3.0,
             control="Gear pump, fixed displacement, aluminium.", expected="OW-G8"),
        dict(model="CF-GP32",  type="external_gear_pump", circuit="open", mounting="SAE B", displacement=31,  max_pressure=200, cont_pressure=180, max_speed=2800, weight=5.9,
             control="Gear pump, fixed displacement, aluminium.", expected="OW-G32"),
        dict(model="CF-DV10",  type="directional_valve", size="NG10", max_pressure=320, max_flow=150, weight=4.4,
             control="Directional spool valve 4/3, solenoid actuated, emergency manual override.", expected="OW-D10"),
    ],
}
# fmt: on

# Hard cases: the naive "closest size" answer is wrong because an engineering rule fails.
HARD_CASES = {
    "VT-AX45CL": "closed circuit: the open-circuit OW-A45 has the same size but cannot replace it",
    "VT-G19": "closest size OW-G22 is rated 250 bar < 275 bar; OW-G16 is smaller but meets pressure",
    "VT-D6": "OW-D6 has the right interface but only 80 L/min < 100 L/min; OW-D6H is required",
    "CF-AP28": "max speed 3100 rpm is above OW-A28's 3000 rpm, but within the 5 % tolerance",
}
