# Avaliação (eval)

Estrutura reservada para a **Fase 1** (ver `constitution/roadmap.md`).

- `golden-set/`: perguntas em pt-BR, respostas esperadas e trechos de referência (versionado).
- `results/`: métricas oficiais por fase (Recall@k, MRR, nDCG, RAGAS), usadas para comparar cada mudança no pipeline.

Princípio da constituição: nenhuma mudança de parsing, chunking, embedding ou recuperação é aceita sem comparar métricas.
