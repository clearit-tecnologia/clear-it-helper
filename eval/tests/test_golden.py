import json

from ch_eval.golden import (
    ambiguous_quotes,
    copied_ngrams,
    find_missing_quotes,
    load_golden,
    type_distribution,
    validate_schema,
)

CORPUS = {"lai.txt": "Art. 11. O órgão deverá, em prazo não superior a 20 (vinte) dias, responder."}


def item(**over):
    base = {
        "id": "lai-001",
        "question": "Qual o prazo de resposta do órgão?",
        "type": "factual",
        "reference_answer": "20 dias.",
        "evidence": [
            {
                "document": "lai.txt",
                "quote": "em prazo não superior a 20 (vinte) dias",
                "locator": "Lei 12.527/2011, art. 11",
            }
        ],
        "reviewed": False,
    }
    base.update(over)
    return base


def test_valid_item():
    assert validate_schema(item(), set(CORPUS)) == []
    assert find_missing_quotes(item(), CORPUS) == []


def test_schema_errors():
    errs = validate_schema(item(type="opinion", reviewed="no", extra=1), set(CORPUS))
    assert any("type inválido" in e for e in errs)
    assert any("reviewed" in e for e in errs)
    assert any("não previstos" in e for e in errs)
    short = item(evidence=[{"document": "lai.txt", "quote": "curto", "locator": "x"}])
    assert any("caracteres" in e for e in validate_schema(short))
    unknown = item(evidence=[{"document": "x.txt", "quote": "q" * 40, "locator": "x"}])
    assert any("desconhecido" in e for e in validate_schema(unknown, set(CORPUS)))
    assert any("multi_hop exige" in e for e in validate_schema(item(type="multi_hop")))
    assert validate_schema(item(type="unanswerable", evidence=[])) == []


def test_missing_quote_detected():
    bad = item(
        evidence=[
            {
                "document": "lai.txt",
                "quote": "em prazo não superior a 30 (trinta) dias",
                "locator": "x",
            }
        ]
    )
    assert find_missing_quotes(bad, CORPUS) == ["em prazo não superior a 30 (trinta) dias"]
    wrong_doc = item(
        evidence=[
            {
                "document": "lgpd.txt",
                "quote": "em prazo não superior a 20 (vinte) dias",
                "locator": "x",
            }
        ]
    )
    assert find_missing_quotes(wrong_doc, CORPUS) != []


def test_ambiguous_and_copied():
    corpus = {"a.txt": "frase repetida de teste. frase repetida de teste."}
    it = item(evidence=[{"document": "a.txt", "quote": "frase repetida de teste", "locator": "x"}])
    assert ambiguous_quotes(it, corpus) == ["frase repetida de teste"]
    assert copied_ngrams(
        "o órgão deverá em prazo não superior a 20 (vinte) dias responder?",
        ["em prazo não superior a 20 (vinte) dias, responder"],
    )
    assert not copied_ngrams("Qual o prazo de resposta?", ["em prazo não superior a 20 dias"])


def test_distribution_and_loader(tmp_path):
    p = tmp_path / "g.jsonl"
    rows = (
        [item(id=f"q{i}") for i in range(7)]
        + [item(id="m1", type="multi_hop")] * 2
        + [item(id="u1", type="unanswerable", evidence=[])]
    )
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n\n", "utf-8")
    loaded = load_golden(p)
    assert len(loaded) == 10
    dist = type_distribution(loaded)
    assert dist == {"factual": 0.7, "multi_hop": 0.2, "unanswerable": 0.1}
