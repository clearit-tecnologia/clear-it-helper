from ch_eval.htmltext import decode_html, html_to_text

PAGE = """<html><head><title>L1</title><style>p{color:red}</style>
<script>alert('x')</script></head><body>
<p>Menu do portal</p>
<p>LEI Nº 1, DE 2020</p>
<p><strike>Art. 1º Texto
revogado.</strike></p>
<p>Art. 1º Texto vigente&nbsp;com
quebra. <a href="#">(Redação dada pela Lei nº 2, de 2021)</a></p>
<p><span style="color:black; text-decoration: line-through">II - inciso antigo;</span></p>
<p>II - inciso novo;<p>III - sem fechar p
<table><tr><td>a</td><td>b</td></tr></table>
</body></html>"""


def test_html_to_text_drops_struck_and_scripts():
    text = html_to_text(PAGE, start_pattern=r"^LEI N")
    assert text.splitlines() == [
        "LEI Nº 1, DE 2020",
        "Art. 1º Texto vigente com quebra. (Redação dada pela Lei nº 2, de 2021)",
        "II - inciso novo;",
        "III - sem fechar p",
        "a b",
    ]


def test_html_to_text_can_keep_struck():
    text = html_to_text(PAGE, drop_struck=False)
    assert "Texto revogado." in text
    assert "inciso antigo" in text
    assert "alert" not in text and "color:red" not in text


def test_decode_windows_1252_without_charset():
    raw = "Art. 5º Informação – “pública”".encode("cp1252")
    assert decode_html(raw) == "Art. 5º Informação – “pública”"
    assert decode_html("já é utf-8".encode()) == "já é utf-8"
    assert decode_html(b"\x81undefined") == "\x81undefined"
