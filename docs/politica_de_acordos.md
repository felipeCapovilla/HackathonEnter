# Política de acordos — versão final do motor

Versão `politica-2026.09.12-v3`. Casos em que a pessoa não reconhece a contratação de um empréstimo.

## A pergunta que o motor responde

Para cada processo, qual caminho custa menos ao banco:

- **Defender** no judiciário;
- **Acordar**, com uma faixa de negociação;
- **Recuperar** um documento que falta e que muda a melhor opção.

A decisão é determinística e reproduzível. A IA não decide: ela lê o dossiê e extrai o veredito do perito.

## Como a decisão é tomada

**1. A defesa é possível?** Sem contrato válido e sem extrato, o banco não cumpre o ônus da prova do art. 373, II do CPC. Nesses casos ele vence 2,7% das vezes. A defesa sai do menu padrão e só pode ser escolhida com justificativa registrada.

**2. Qual a chance de perder?** Vem de uma tabela gerada da base histórica de 60 mil sentenças (`scripts/gerar_tabela_politica.py`). Combina contrato, extrato, comprovante de crédito e golpe/genérico, ajustada pelo grupo de risco da UF. O risco vai de 2% a 99% conforme os documentos presentes. Dossiê e laudo não mudam a chance de perder.

**3. Quanto custa defender?** Chance de perder × condenação média (71% do valor da causa) × custo do tempo (1% ao mês por 24 meses), mais os honorários do contrato que dependem do desfecho.

**4. Quanto oferecer?**
- **Abertura:** 29% do valor da causa, a mediana dos acordos reais da base.
- **Walk-away:** o custo esperado da defesa daquele caso, limitado pela alçada do banco. Acima dele é defesa.
- **Alvo:** a abertura. Nos acordos reais o valor fechado não sobe com o risco. O contrato pode definir uma concessão, que sobe o alvo em direção ao walk-away.
- **Valor único:** quando o espaço entre abertura e walk-away é menor que 5% da abertura, o advogado recebe um valor só.
- **Regra:** se o walk-away fica abaixo da abertura, defender é mais barato.

**5. Vale recuperar um documento?** O dossiê que periciou a assinatura do contrato prova que o contrato existe. O motor recomenda recuperar só quando o documento muda a melhor opção disponível. O ganho é a chance de recuperá-lo × a diferença de custo.

**O dossiê na decisão:**
- Parecer **não conforme** desconsidera o contrato como prova, e o caso é recalculado.
- Parecer **conforme** não muda o risco.
- A análise roda automaticamente ao fim da extração, quando a chave da OpenAI está configurada.

## O que cada banco configura (contrato com o escritório)

| Parâmetro | Padrão |
|---|---|
| Honorário se a defesa ganhar, se perder e por acordo (R$ ou %) | 0 |
| Custo mensal do tempo | 1% |
| Duração esperada | 24 meses |
| Teto de alçada do acordo | sem teto |
| Concessão na negociação | 0% |

Mensalidade e valor fixo por caso novo não entram, porque não mudam a decisão. Cada gravação cria uma versão, e cada análise registra a versão usada.

## Premissas

| Medido na base | Assumido |
|---|---|
| Chance de perder por segmento e UF | Aceitação do acordo: 40% (não muda nenhuma decisão, só o tamanho da economia) |
| Condenação média: 71% da causa | Recuperação do documento: 70% com prova interna de que ele existe, 25% sem |
| Faixa dos acordos: P25 25%, mediana 29%, P90 39% | Custo do tempo: 1% ao mês por 24 meses (decisão igual entre 12 e 36 meses) |

## Resultados retrospectivos

- **Calibração:** erro máximo de 0,62 ponto entre risco previsto e observado.
- **Economia sobre os R$ 193M pagos:** 15,3% só com a presença dos documentos; 27,7% no teto em que todo dossiê presente periciou o contrato.
- **Tabela contra LightGBM, fora da amostra (5 folds):** AUC 0,9199 contra 0,9215, e economia R$ 68 mil maior com a tabela. Empate prático; a tabela ficou por não exigir dependência nem treino.

## Limitações

- A aceitação dos acordos é suposta até o desfecho das negociações ser registrado.
- A base tem apenas a presença dos documentos; o conteúdo lido hoje é só o do dossiê.
- A estrutura dos segmentos é fixa. Para outro banco, a tabela é regenerada com a base dele, mas os documentos considerados são os mesmos.
