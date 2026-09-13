# Painel do banco

Visão de quem contratou os escritórios: o que a política entregou, onde o banco perde dinheiro e quem executa bem.
Rota do front: `/banco/monitoramento` (abas por `?aba=`). Código: `src/interface/frontend/src/banco/` e
`src/interface/backend/bank_insights.py`.

## Princípios

- **Tudo é ajustado ao risco.** O número principal de banco, escritório e advogado é o **índice** =
  economia realizada ÷ economia esperada pela política para *aqueles* processos. Taxa de vitória crua não entra:
  ela mede a carteira recebida (sem contrato o banco perde 75%; com contrato, 13%), não o trabalho.
- **Documento é a alavanca do banco.** Contrato e extrato mudam o resultado e quem entrega é o banco. O painel mostra
  o valor em jogo = (P(derrota) sem o documento − com ele) × condenação média × chance de recuperar (70%).
- **Benchmark anônimo.** Escritório × mercado só aparece com ao menos 2 outros clientes e 50 decisões fora do banco.
  Nenhum outro cliente é identificado; nome de advogado nunca sai do banco.
- **Gestão por exceção.** Acordo acima do walk-away, divergência com custo esperado ≥ R$ 1.000 e decisão registrada
  sem abrir documento quando o motor pediu conferência.
- **IA com propósito.** Os valores são determinísticos. A OpenAI só classifica o texto livre de "documento indisponível"
  num motivo (sem chave, cai para regra de palavras-chave).

## Abas

| Aba | O que responde |
|---|---|
| Visão geral | Economia realizada × esperada, aceitação (premissa 40% → aprendida, Beta-Binomial), aderência, custo das divergências, pago acima do alvo, condenação realizada × projetada |
| Documentos | Valor em jogo por documento na carteira, fila de recuperação ordenada por R$, motivos de indisponibilidade, leitura da base de 60 mil sentenças |
| Recomendações | Um card por (documento, motivo) com área responsável, ação, indicador e valor em jogo; mais os achados da base |
| Escritórios | Índice com você × no mercado (anônimo) e a leitura do gap |
| Advogados | Ranking pelo índice (mínimo 20 decisões), aceitação, acima do alvo, divergências, tempo ativo, % sem abrir documento |
| Engajamento | Tempo ativo por caso, com e sem ressalva do motor, por tipo de caso (mínimo 10 processos) |
| Exceções | Lista priorizada com link para o processo |
| Contrato | Gestor edita o contrato do banco ou de um escritório; só salva depois de simular e com justificativa |

## API (para as telas do advogado e do admin)

Advogado (`ADVOGADO_EXTERNO`):

| Método | Rota | Corpo |
|---|---|---|
| POST | `/api/cases/{id}/negotiation-outcomes` | `{status: ACEITO\|RECUSADO\|CONTRAPROPOSTA\|SEM_RESPOSTA, offered_value?, counter_value?, closed_value?}` — exige decisão de ACORDO antes (409); ACEITO exige `closed_value`, CONTRAPROPOSTA exige `counter_value` |
| POST | `/api/cases/{id}/judicial-outcomes` | `{result: EXITO\|NAO_EXITO, condemnation_value}` |
| POST | `/api/cases/{id}/engagement` | `{event_type: ACTIVE_TIME, active_seconds ≤ 300}` ou `{event_type: DOCUMENT_OPENED, document_id}` — o hook `useActiveTime` já envia o tempo ativo |

Gravados automaticamente pelo backend: abertura do caso (`GET /api/cases/{id}`), abertura de documento
(`/file` e página 1), análise rodada, decisão e resultado registrados. `GET /api/cases/{id}` agora devolve
`negotiation_outcomes` e `judicial_outcomes`.

Banco (`BANCO`; escrita de contrato exige `is_manager`):

| Método | Rota | Observação |
|---|---|---|
| GET | `/api/bank/insights` | Tudo o que o painel mostra |
| GET | `/api/bank/law-firms` | Escritórios com advogado ativo no banco |
| GET | `/api/bank/contract?law_firm_id=` | Sem escritório: padrão do banco; escritório sem contrato próprio vem com `inherited_from_bank` |
| POST | `/api/bank/contract/preview?law_firm_id=` | Corpo: `ParametrosContrato` |
| POST | `/api/bank/contract?law_firm_id=` | Corpo: `{parametros, justificativa (≥ 10)}` |
| POST | `/api/document-requests/{id}/response` | Agora aceita `unavailability_reason` |

Admin (`ADMIN_GLOBAL`): `GET/POST /api/admin/law-firms`; `POST /api/admin/users` aceita `law_firm_id` (advogado) e
`is_manager` (banco); as rotas de contrato do admin aceitam `?law_firm_id=`.

O contrato de um processo é o do escritório do advogado atribuído; sem contrato próprio, vale o padrão do banco.

## Operação simulada

`python -m scripts.seed_operacao_simulada --confirm-demo [--reset]` cria em `.runtime/demo`: 3 bancos (Unicamp + 2
fictícios), 5 escritórios, 13 advogados sem login e 1.160 processos.

- **Real:** processos sorteados da base (UF, valor, subsídios), recomendação do motor de produção e, para processo
  defendido, o desfecho e a condenação verdadeiros.
- **Simulado:** comportamento dos advogados (perfis), resposta da parte autora ao acordo, motivos de indisponibilidade
  e tempo de tela. O painel mostra o selo "Operação simulada".

`banco@demo.local` vira gestor e `advogada@demo.local` entra no escritório Almeida & Rocha. As senhas demo não mudam.
Precisa de `data/resultados.csv` e `data/subsidios.csv` (`python -m scripts.exportar_base_csv --xlsx ...`).
`python -m scripts.gerar_insights_base` regenera `artefatos/insights_base_historica.json`.
