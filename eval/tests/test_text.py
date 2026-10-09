from ch_eval.text import contains_quote, normalize


def test_normalize_lower_and_collapse_whitespace():
    assert normalize("  Art. 5º\n\tPara   os FINS  ") == "art. 5o para os fins"


def test_normalize_nbsp_and_ordinal_indicator():
    # NFKC maps NBSP to space and the ordinal indicator to "o" on both sides
    assert normalize("art. 5º") == normalize("Art. 5º") == normalize("art. 5o")


def test_contains_quote_across_line_breaks():
    chunk = "I - ultrassecreta: 25 (vinte e cinco) anos;\nII - secreta: 15 (quinze) anos; e"
    assert contains_quote(chunk, "ultrassecreta: 25 (vinte e cinco) anos; II - secreta")
    assert not contains_quote(chunk, "reservada: 5 (cinco) anos")
    assert not contains_quote(chunk, "   ")
