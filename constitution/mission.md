# Missão

## Propósito

Construir um chatbot baseado em RAG (Retrieval-Augmented Generation) que responde perguntas a partir dos documentos enviados pelo próprio usuário, com respostas **fundamentadas, citadas e verificáveis**.

O diferencial do projeto é o **embedding inteligente**: em vez de quebrar documentos em pedaços de tamanho fixo, o pipeline entende a estrutura e o sentido de cada documento antes de indexá-lo. Isso aumenta a precisão da recuperação e reduz alucinações.

## Problema

Organizações, especialmente do setor público, guardam conhecimento crítico em PDFs, documentos escaneados, planilhas e normativos. Os chatbots RAG convencionais costumam:

- perder tabelas, títulos e hierarquia ao extrair o texto;
- cortar informações no meio ao dividir os documentos em chunks;
- recuperar trechos parecidos, mas irrelevantes;
- exigir envio de dados sensíveis para APIs externas, o que é incompatível com a LGPD e com exigências de soberania de dados.

## Público-alvo

- **Usuários finais:** servidores públicos e colaboradores corporativos que precisam consultar grandes acervos documentais.
- **Clientes:** órgãos governamentais e empresas atendidos pela ClearIT que exigem execução 100% on-premises.

## Princípios inegociáveis

1. **Soberania de dados (100% on-premises).** Nenhum documento, embedding, prompt ou resposta sai da infraestrutura do cliente. Todos os modelos são open-source e servidos localmente.
2. **Fundamentação e citação.** Toda resposta cita os trechos e documentos de origem. Se a resposta não está nos documentos, o sistema diz isso em vez de inventar.
3. **Qualidade medida, não presumida.** Desde a Fase 1 existe um golden set de perguntas em pt-BR. Nenhuma mudança no pipeline de parsing, chunking, embedding ou recuperação é aceita sem comparação de métricas antes e depois.
4. **Isolamento por tenant desde o início.** Todo dado (documento, chunk, vetor, conversa) carrega `tenant_id`, e toda consulta é filtrada por ele. A autenticação evolui ao longo das fases, mas o modelo de dados não muda.
5. **Estrutura antes de vetores.** A qualidade do embedding depende da qualidade do parsing. O documento é compreendido estruturalmente antes de ser fragmentado.
6. **pt-BR em primeiro lugar.** Modelos, prompts e avaliações são escolhidos e validados para o português brasileiro.
7. **Simplicidade evolutiva.** O MVP é um núcleo enxuto da arquitetura-alvo da ClearIT AI Platform. Componentes como orquestradores, guardrails e gateways entram quando houver necessidade comprovada, e cada um deles precisa ser substituível.
8. **Observabilidade.** Cada etapa da ingestão e cada resposta é rastreável: qual chunk foi recuperado, com qual score, por qual modelo e com qual latência.

## Os 4 pilares do embedding inteligente

Em ordem de prioridade, por dependência:

| # | Pilar | O que entrega |
|---|-------|---------------|
| 1 | **Parsing estrutural** | Extração com layout preservado (títulos, seções, tabelas, listas) e OCR para documentos escaneados. |
| 2 | **Chunking semântico + contextual retrieval** | Chunks delimitados por estrutura e sentido, cada um enriquecido com um contexto do documento de origem antes de gerar o embedding. |
| 3 | **Busca híbrida + rerank** | Recuperação densa e esparsa combinada, seguida de reranking com cross-encoder. |
| 4 | **Enriquecimento por LLM** | Metadados automáticos por chunk: resumo, palavras-chave, perguntas hipotéticas e classificação. |

## Critérios de sucesso

- Respostas com citação verificável em 100% dos casos em que há resposta.
- Ganho mensurável de recuperação (Recall@k, MRR) e de qualidade da resposta (faithfulness, answer relevancy) a cada pilar entregue, em comparação com uma baseline de chunking fixo.
- Nenhum tráfego de dados para fora do ambiente on-premises.
- Ingestão de PDFs nativos, escaneados, DOCX e planilhas sem perda de tabelas.

## Fora de escopo (por enquanto)

- Canais além da web, como WhatsApp, plugins de IDE e integrações via MCP com ERPs ou CRMs.
- Agentes autônomos multi-etapa.
- Uso de APIs de LLM em nuvem, em qualquer ambiente com dados reais.
