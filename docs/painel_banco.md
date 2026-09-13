# Painel da empresa

Na tela o cliente aparece como **empresa** (a política serve para qualquer grande empresa); no código o papel continua `BANCO`.

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

## Ajustes da rodada de avaliação

| Pedido | O que mudou |
|---|---|
| Banco → Empresa; sem EnterOS/EnterAgree | Textos das telas; a barra superior mostra só o nome da empresa |
| Cor da bolinha | O contador das abas do painel passou ao âmbar da marca e deixou de vazar para as abas de processos |
| Leitura por IA ao subir documento | `src/tools/leitor_documentos.py`: tipo, resumo, nº do contrato, valores, parte autora e pontos de atenção. PDF escaneado vai como arquivo. Sem `OPENAI_API_KEY`, o envio segue normal. `POST /api/documents/{id}/leitura` refaz; `ENTERAGREE_LEITURA_IA=false` desliga |
| Excluir e reenviar documento | A trava "mesmo arquivo no mesmo processo" só olha documentos não excluídos (índice parcial, com migração de bancos antigos) |
| Textos da indicação de ação | O motor explica em frequência ("em 10 casos parecidos, a empresa perde 6"), sem walk-away, segmento ou P(derrota) |
| Quanto se perdeu na sentença desfavorável | O desfecho aceita `value`; o processo mostra a condenação e compara com o acordo recomendado; a lista marca a condenação |
| Busca por contrato | `GET /api/bank/search?q=` procura no número do processo, na leitura por IA (contrato, parte) e no texto de cada página |

## Métricas observadas (rodada com a organização)

O painel mostra **só valor observado**: o que foi pago de fato e quanto processos parecidos custaram na base de
60 mil sentenças. Estimativas do modelo decidem a recomendação, mas não medem o próprio resultado.

**Economia.** No pitch, o backtest: aplicar a política aos 60 mil processos e comparar com o que a empresa pagou
nesses mesmos processos (R$ 193,0 mi pagos; R$ 163,5 mi com a política e 40% de aceitação; entre R$ 22 mi e
R$ 44 mi conforme a aceitação fique entre 30% e 60%). No painel ao vivo, a soma, nos processos encerrados, de
**custo médio real de processos parecidos − custo real do processo** (mesmos documentos, alegação e região; sem a
região quando há menos de 30 casos). Nunca por processo isolado. A economia aparece dividida entre quem seguiu a
recomendação e quem divergiu.

**Pior caso e gasto real** lado a lado (soma do valor da causa × acordos e condenações pagos), sem número de diferença.

**Ticket médio dos acordos**, em reais e em % da causa, contra os 280 acordos da base (R$ 4.540; 29,8% da causa).

**Score de advogado e escritório (0 a 100).** Cada processo vira notas de 0 a 1 que não dependem do valor da causa:

| Componente | Nota por processo | Peso |
|---|---|---|
| Resultado | (custo de parecidos − custo real) ÷ custo de parecidos, limitado a ±1 e levado para 0 a 1 | 50% |
| Preço do acordo | 1 − posição do valor fechado (% da causa) entre os acordos da base | 20% |
| Aderência | 1 seguiu a recomendação; 0,5 divergiu com motivo; 0 sem motivo | 20% |
| Aceitação | 1 acordo proposto aceito; 0 recusado ou sem resposta | 10% |

Componente sem dado sai da conta e os pesos se redistribuem. Com poucos processos encerrados o score é puxado para
a média da empresa: (n × nota + 10 × média) ÷ (n + 10). Posição no ranking a partir de 20 encerrados. O mercado dos
escritórios usa o mesmo score, com ao menos 2 outros clientes e 50 processos encerrados fora da empresa.

**Exceções sem valor estimado:** acordo acima do limite, decisão diferente da recomendação (com o motivo) e decisão
sem abrir documento. **Saiu do painel:** índice, custo das divergências, pago acima do alvo, economia esperada,
condenação projetada, valor em jogo estimado e a aba de tempo (o tempo de tela deixou de ser coletado).

**Saldo estimado das divergências** (`divergencias.py`, tabela `divergence_balances`): caminho recomendado em valor
esperado − custo real, guardado por decisão encerrada que divergiu. Não aparece em tela; é a entrada do human in the loop.

## Valor recomendado ao advogado

- **Ofereça R$ X:** dentro da faixa de mercado (25% a 35% da causa, onde os acordos da base fecharam), a oferta que
  maximiza chance de aceite × economia até o limite. A chance de aceite é a curva dos 280 acordos, corrigida pela
  aceitação observada na operação a partir de 10 respostas.
- **Faixa de mercado:** onde acordos parecidos fecham.
- **Limite, explícito:** "Acima de R$ Y, acordo não compensa: defender sai mais barato." Y é o custo esperado de
  defender (chance de perder × condenação média × custo do tempo), por isso chega perto de 85% da causa quando a
  empresa quase sempre perde.
- **Argumentos calculados:** chance de perder, faixa dos acordos parecidos, chance de aceite da oferta e economia
  sobre o custo médio de processos parecidos.
