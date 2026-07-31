from app.services.matching import normalize


def test_normalize_cmr_removes_spaces_and_punctuation():
    assert normalize("CMR 2026/001-AB") == "CMR2026001AB"


def test_normalize_handles_czech_diacritics_and_case():
    assert normalize(" řidič-Žluťoučký ") == "RIDICZLUTOUCKY"


def test_normalize_empty_value():
    assert normalize(None) == ""
