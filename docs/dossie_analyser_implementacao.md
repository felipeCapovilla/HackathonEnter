# Analisador de dossiê — auditoria e implementação

## Referências e escopo

Implementado na branch `feat/dossie-analyser-integration`, criada diretamente de
`origin/main`, inicialmente em `2efb31eb`. Durante a implementação, o remoto
reescreveu essa referência para `4fbe6ea7`, com árvore de arquivos idêntica;
a base da branch ainda não publicada foi atualizada, preservando todas as alterações.
Referência avaliada: `origin/feat/docie-analyser`,
commit `d2573e35`; essa branch não foi sobrescrita ou mesclada integralmente.

A referência contém `src/tools/dossie_analyzer.py`, `text_converter.py`, `graph.py`,
`state.py` e o exemplo fictício `docs/05_Dossie_Veritas.{md,pdf}`. O exemplo relata
conformidade, perícia da assinatura no contrato, compatibilidade de 91%, match
facial de 97,3% e validação de identidade/residência. São declarações do laudo,
não medidas calculadas pelo nosso sistema nem comprovação independente de autoria.

### O que já existia e foi corrigido

| Referência | Implementação integrada |
| --- | --- |
| Cliente OpenAI criado no import; ausência de chave quebra importação | SDK/cliente carregados somente ao solicitar extração; API comum funciona sem chave |
| PDF inteiro convertido em `.md` ao lado do original e enviado em uma chamada | Reutiliza páginas persistidas; trechos limitados, números de página preservados, nenhum arquivo lateral |
| Campos ausentes viram `0`/`False` | Índice `null`, item `inconclusivo`, exame contratual `desconhecido` |
| Parecer livre, sem evidência ou normalização de índice | Schema tipado, índices 0–1, citações literais verificadas e conflitos explícitos |
| Grafo considera qualquer texto diferente de “não-conformidade” como sucesso | Inconclusivo/ausente/falha nunca implica conformidade |
| Não conformidade força acordo | Extração não decide ação; eventual revisão usa o motor vigente da main |
| `ResumoDocie` não implementa `AnaliseDossie` da main | Saída `DossieReport.analise` usa o contrato real, incluindo perícia no instrumento contratual |
| Caminhos absolutos Linux, imports locais e venv/bytecode versionados | Imports de pacotes, CLI portátil, dependências opcionais declaradas; nenhum venv/bytecode copiado |

## Fluxo operacional

1. Usuário envia PDF/TXT manualmente, declarado como `DOSSIE`.
2. O processamento existente extrai texto e verifica tipo por regras, sem LLM.
3. Ao clicar em **Analisar dossiê com IA**, o texto é enviado à OpenAI; o aviso
   de envio aparece antes do botão. Não há análise paga automática no upload.
4. O extrator coleta parecer, exame de assinatura contratual, número de contrato,
   itens de validação e índices. Cada afirmação utilizada exige trecho e página.
5. A consolidação compara os trechos. Informações conflitantes, páginas ilegíveis
   ou evidências rejeitadas tornam o relatório inconclusivo/com ressalvas.
6. Resultado e metadados são persistidos separadamente da análise de política.
   A interface apresenta os achados e permite abrir a página extraída.

A mera existência de arquivo não prova seu conteúdo. `docie_existe` é obtido
localmente, não pelo LLM. Um dossiê que menciona um contrato não torna a feature
`contrato` verdadeira. Exame de RG/selfie tampouco prova perícia da assinatura
contratual. Só o documento de contrato submetido e confirmado ativa essa presença.

## Contratos e limites de confiança

- `contracts/dossie.py`: `DossieChunkExtraction`, `DossieEvidence`, `DossieReport`.
- `contracts/schema.py`: `AnaliseDossie`, `ItemDossie`, índices finitos entre 0 e 1.
- Parecer: `conforme`, `nao_conforme`, `inconclusivo`.
- Exame contratual: `assinatura_contrato_status` distingue `sim`, `nao`,
  `desconhecido` e `conflitante`. O bool legado é conservador e não substitui essa distinção.
- Falta de índice não vira zero. Percentuais são normalizados e confrontados com
  o percentual na citação. Citações vazias, inventadas ou em outra página são rejeitadas.
- `completo` informa se o processamento terminou sem problemas detectados de
  cobertura/consistência; não significa que todos os campos foram encontrados.
- `confianca_extracao=0` significa **não calibrada**, não probabilidade jurídica de 0%.

O extrator não verifica biometria/grafotecnia por conta própria. Citação literal
não comprova a interpretação do LLM. Checagens locais de polaridade e perícia são
conservadoras e podem rejeitar formulações legítimas; revisão humana é obrigatória
antes de transportar achados para uma decisão automatizada.

O prompt trata documentos como dados não confiáveis e não oferece ferramentas
ao modelo. Essa separação reduz exposição, mas não constitui prova de resistência
a toda injeção de prompt. São necessários evals adversariais com documentos reais.

## API e persistência

| Operação | Comportamento |
| --- | --- |
| `POST /api/documents/{id}/dossie-analysis` | Executa ou reutiliza extração; retorna 201 com relatório completo |
| `GET /api/documents/{id}/dossie-analysis` | Consulta última análise, priorizando sucesso; 404 se inexistente |
| `GET /api/cases/{id}` | Acrescenta resumo do último resultado por documento; não repete todas as citações no polling |

Resumos informam `evidencias_total` e `evidencias_carregadas=false`. O botão
**Carregar evidências** busca o relatório completo pelo GET dedicado. O POST/GET
dedicado retorna `evidencias_carregadas=true`. Omissão de evidências no resumo é
explícita, não truncagem silenciosa. As rotas existentes são preservadas.

404: documento/relatório ausente. 409: tipo incompatível/removido, extração não
concluída, alteração durante a análise ou processamento concorrente. 503:
configuração, provedor/recusa/saída inválida ou limite de entrada; registra código
sanitizado, sem chave, texto jurídico ou mensagem bruta do provedor.

`UNCONFIRMED` não impede a análise auxiliar: há ressalva. `MISMATCH` exige resolução
prévia pelo fluxo existente; `USER_CONFIRMED` permite continuar com aviso.

Tabelas `dossie_analyses` e `dossie_analysis_claims` são criadas idempotentemente,
sem apagar casos existentes. Cache usa documento, hash, modelo e versão do extrator.
Falhas são registradas e podem ser tentadas novamente; não substituem silenciosamente
sucesso anterior. Ressalvas de status/cobertura são reaplicadas ao consultar o cache.
Uma reserva SQLite atômica evita chamadas simultâneas duplicadas. A conexão fecha
antes da rede; a reserva é liberada ao terminar. Após crash, expira em
`max_chunks * 100 + 300` segundos. O histórico é mantido; não há endpoint de exclusão
ou reanálise forçada de sucesso nesta entrega.

O acesso atual ainda não autentica banco/advogado. Não expor essa API na internet
antes de implementar autorização e segregação de clientes.

## Documentos extensos e configuração

```powershell
python -m pip install -e ".[dossie]"
$env:OPENAI_API_KEY = "sua-chave"
$env:ENTERAGREE_DOSSIE_MODEL = "gpt-4o-mini"
$env:ENTERAGREE_DOSSIE_MAX_CHUNKS = "128"
$env:ENTERAGREE_DOSSIE_MAX_CHUNK_CHARS = "12000"
python -m uvicorn src.interface.backend.main:app --reload
```

Não versionar chaves. `.env.example` é apenas exemplo; não há carregamento
automático de `.env`. O SDK usa Structured Outputs e `store=False` na requisição,
sem afirmar ausência de toda retenção pelo provedor.

Paginação SQLite em lotes de 32; chamadas agrupam até 12.000 caracteres de texto,
preservando páginas e sobreposição nas quebras. O limite é de caracteres, não de
tokens. Limites configuráveis: 512–48.000 caracteres/trecho, 1–4.096 trechos.
Exceder o orçamento resulta em falha explícita, nunca em aprovação do prefixo.
Timeout do SDK de 45 segundos e uma retentativa por chamada. O POST é síncrono,
executado no pool de threads do FastAPI: documentos grandes podem levar minutos.

O suporte foi exercitado com 1.200 páginas sintéticas e extrator controlado,
inclusive evidência na última página. Isso valida paginação/cobertura, **não**
throughput do LLM. Não há promessa de 600 páginas/s. Produção exige fila de workers,
progresso persistido, retomada de trechos e orçamento/cancelamento. Um relatório
completo ainda pode ser grande; a UI evita retransmiti-lo durante polling.

Extração PDF/texto é local e usa CPU. Nenhum embedding remoto foi introduzido.
GPU/embeddings locais, OCR e métrica de qualidade continuam TODO, fora deste incremento.

## Workflow LangGraph opcional

```powershell
python -m src.graph --document "C:\caminho\dossie.pdf"
```

O grafo começa sem aprovação; cada nova extração reseta `analise_revisada` e
qualquer recomendação anterior. Documento ausente termina em `AUSENTE`; relatório
existente segue a `REVISAO_MANUAL`. Não há acordo/defesa inferido por substring.

Para consumidores Python, `node_verificar_parecer` aceita o estado **após** revisão
do resultado, com `analise_revisada=True` e `CaseFeatures` completos. Só então chama
`decidir` da main, preservando as flags originais. Inconclusivo/cobertura incompleta
ou ausência de dossiê nas features não avança para a política. Esse passo é um
contrato programático, não uma nova tela de aprovação nem autenticação do revisor.

A main atual invalida o contrato probatoriamente diante de parecer negativo e
recalcula custos; não força sempre acordo. A API documental continua utilizando
`PolicyEngine` do Grupo 9. Nenhum dos dois motores foi retreinado ou substituído.

## Validação e próximos passos

Testes cobrem contrato/citações/índices, dados ausentes, arquivo vazio/protegido,
conflitos, orçamento, páginas finais, adapter real do SDK com transporte HTTP de
teste, recusa/falha, cache/concorrência, migração SQLite, grafo e navegação React.
Fakes são exclusivos dos testes; execução normal usa o provedor configurado.

```powershell
python -m pytest -q
python -m compileall -q src contracts scripts tests
python -m scripts.export_policy_schema
$env:PLAYWRIGHT_CHROMIUM_CHANNEL = "chrome"
npm --prefix src/interface/frontend run test:e2e
```

O comando de navegador usa Chrome instalado. Como alternativa, instalar o Chromium
do Playwright e omitir a variável. Não confundir ausência do executável de navegador
com falha da aplicação. A inferência real contra OpenAI não foi executada nesta
entrega: `OPENAI_API_KEY` não estava configurada. Não há métrica de acurácia ou
validação financeira nova. Antes de produção, executar evals rotulados, inclusive
ambos os casos exemplo, contraditórios, documentos adversariais e PDFs escaneados.

Referências técnicas consultadas: [Structured Outputs da OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs)
e [Graph API do LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api).
