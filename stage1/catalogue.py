"""Document-derived references and mechanism families with explicit variants.

The uploaded thesis is evidence to interpret, not executable instructions.
MURIEL's original presentation was retrieved and its screening slides checked;
the other external references have not been independently verified here.
"""

SOURCES = {
    "USER_DEPTH": {
        "citation": "User specification: intervention screening at flood depth ≥10 cm; configurable",
        "locator": "Chat request, Stage 1", "url": "", "status": "user_defined_assumption",
    },
    "THESIS": {
        "citation": "Abdulaziz, L. (2026). Nature-based Solutions NbS opportunity mapping and portfolio design in Köln-Kalk for pluvial flooding",
        "locator": "§§5.4–5.5; Tables 4.2, 5.3–5.4", "url": "", "status": "uploaded_document",
    },
    "KOELN2022": {
        "citation": "Stadt Köln (2022, as cited in thesis). Niederschlagswasserversickerung",
        "locator": "Thesis §4.3, Table 4.2, §5.5.2",
        "url": "https://www.stadt-koeln.de/service/produkt/regenwasserversickerung",
        "status": "thesis_transcription_not_independently_verified",
    },
    "DWA_SUMMARY": {
        "citation": "Ishorst (2025). Public technical summary of DWA-A 138-1 (2024); not the purchased standard",
        "locator": "Thesis §5.4.2, paragraph 410 in extraction",
        "url": "https://www.sbz-online.de/sanitaer/versickerung-von-niederschlagswasser-auf-grundstuecken-teil-1-anforderungen",
        "status": "secondary_source_requires_standard_and_authority_confirmation",
    },
    "STEB2025": {
        "citation": "StEB Köln (2025a, as cited in thesis). Schutz öffentlicher Abwasseranlagen",
        "locator": "Thesis Table 4.2; Figure 5.2",
        "url": "https://steb-koeln.de/download/1673191350/StEB-Koeln_SchutzoeffentlicherAbwasseranlagen_20251125_bf.pdf",
        "status": "thesis_transcription_not_independently_verified",
    },
    "ROOF2026": {
        "citation": "Stadt Köln (2026, as cited in thesis). Leitfaden Dachbegrünung in Bebauungsplan- und Baugenehmigungsverfahren",
        "locator": "Thesis §5.5.4, paragraph 428; Figure 5.2",
        "url": "https://www.stadt-koeln.de/mediaasset/content/pdf57/sk_142_26_leitfaden_dachbegr%C3%BCnung_barr.pdf",
        "status": "thesis_transcription_not_independently_verified",
    },
    "MURIEL": {
        "citation": "Schwerdorf (2022). Umsetzung von multifunktionalen Flächen in Köln-Porz/Eil",
        "locator": "Schwerdorf presentation slides 19–20; thesis §§4.4.2, 5.5.3; local planning screen",
        "url": "https://www.region-koeln-bonn.de/fileadmin/redaktion/pdf/regionaler_fachdialog/rkb-regionaler-fachdialog-starkregen-schwerdorf.pdf",
        "status": "primary_presentation_retrieved_and_slides_19_20_checked",
    },
}

# Family names follow the text and the mechanisms shown in Figure 5.2.
# Lined and infiltrating designs remain separate; no automatic mitigation of FAIL.
DESIGNS = {
    "green_roof": ("Green roof", "roof", False, ["roof"]),
    "blue_green_roof": ("Blue-green / retention roof", "roof", False, ["roof"]),
    "surface_infiltration": ("Living-soil surface infiltration", "surface", True, ["open_space", "verge"]),
    "swale_infiltration": ("Vegetated swale / infiltration basin", "swale", True, ["open_space", "verge"]),
    "rain_garden_infiltration": ("Rain garden · infiltration", "rain_garden", True, ["open_space", "verge"]),
    "rain_garden_lined": ("Rain garden · lined / controlled outlet", "rain_garden", False, ["open_space", "verge"]),
    "tree_trench_infiltration": ("Tree pit / trench · infiltration", "tree", True, ["open_space", "verge", "pavement", "parking"]),
    "tree_trench_lined": ("Tree pit / trench · lined", "tree", False, ["open_space", "verge", "pavement", "parking"]),
    "permeable_pavement_infiltration": ("Permeable pavement · infiltration", "pavement", True, ["pavement", "parking", "footway"]),
    "permeable_pavement_lined": ("Permeable pavement · lined / underdrained", "pavement", False, ["pavement", "parking", "footway"]),
    "infiltration_trench": ("Subsurface infiltration trench", "trench", True, ["open_space", "verge", "pavement", "parking"]),
    "swale_trench": ("Combined swale–trench system", "swale_trench", True, ["open_space", "verge"]),
    "infiltration_shaft": ("Infiltration shaft", "shaft", True, ["open_space", "verge", "pavement", "parking"]),
    "lined_detention": ("Lined multifunctional detention", "detention", False, ["open_space", "verge", "pavement", "parking"]),
    "safe_conveyance": ("Safe surface conveyance", "conveyance", False, ["open_space", "verge", "pavement", "parking", "footway"]),
}

DEFAULT_POLICY = {
    "profile_id": "koeln_thesis_provisional_v1", "rule_scope": "Koeln", "municipality": "Koeln",
    "profile_reviewed": False, "profile_review_ref": None,
    "groundwater_preferred_m": 1.0, "groundwater_floor_m": 0.5,
    "neighbour_setback_m": 2.0, "basement_recommended_m": 6.0,
    "asset_clearance_m": 1.0,
}
