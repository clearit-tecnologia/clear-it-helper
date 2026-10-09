# Fase 1: Status

> Atualizado em 2026-10-09. Critério de pronto: `constitution/roadmap.md`, Fase 1.

## Concluído

- Upload de documentos, ingestão assíncrona (`baseline-v1`) e status na UI, com deploy no cluster k3d via Argo CD.
- Telas de documentos, chat com streaming e citações, e status.
- Golden set v1 com 60 perguntas (42 factuais, 12 multi-hop e 6 sem resposta), validado contra o corpus.
- **Baseline de recuperação registrada** em [`eval/results/2026-10-09-baseline-v1.md`](../../eval/results/2026-10-09-baseline-v1.md):

| Subconjunto | n | MRR | Recall@1 | Recall@5 | Recall@10 | nDCG@10 |
|---|---|---|---|---|---|---|
| todas | 54 | 0,714 | 0,485 | 0,769 | 0,864 | 0,630 |
| factual | 42 | 0,750 | 0,563 | 0,833 | 0,909 | 0,661 |
| multi_hop | 12 | 0,586 | 0,208 | 0,542 | 0,708 | 0,522 |

Corpus: LGPD (100 chunks), Lei 14.133 (336 chunks) e LAI (52 chunks). Chunking fixo de 1000/200 caracteres, `bge-m3` dense, top_k=10 e `min_score` 0,35.

## Pendente (bloqueia o "pronto" da Fase 1)

1. **Avaliação do chat** (resposta citada, recusa correta e indevida, latência p50/p95 e RAGAS opcional): adiada até haver uma VM com memória suficiente.
   No notebook de dev (WSL com cerca de 7,8 GB), o cluster junto com `qwen3.5:2b` e `bge-m3` esgota a memória e derruba os pods.
   - Comando para rodar depois: `uv run python run_eval.py --skip-upload --chat-timeout 900` (em `eval/`).
2. **Orçamento de latência** para a Fase 4: depende do item 1, medido no hardware da VM.
3. **Revisão humana do golden set**: as 60 perguntas ainda estão com `reviewed: false` (checklist em `eval/README.md`).
4. **Traces no Langfuse** (roadmap da Fase 1): o Langfuse está desligado no dev, e a instrumentação do backend ainda não foi feita.

## Melhorias identificadas

- `run_eval.py` deveria abortar quando a API fica inacessível, em vez de registrar erro em todas as perguntas e sobrescrever o arquivo de resultados do dia.
- Imagens com a tag mutável `:dev`: avaliar tag por commit para eliminar a corrida entre o sync do Argo CD e o build (hoje contornada no `dev-up.sh`).
- Logs do worker em nível DEBUG no dev são muito ruidosos.
