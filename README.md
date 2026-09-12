# EnterAgree

Implementação enxuta da política híbrida do Grupo 9 para acordos de não reconhecimento de empréstimo. A API compõe regras determinísticas, o artefato XGBoost reproduzido e evidência documental auditável.

## Executar

Requisitos: Python 3.11+ e Node.js 20.19+ (linha 20) ou 22.12+.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn src.interface.backend.main:app --reload
```

Em outro terminal:

```powershell
cd src/interface/frontend
npm ci
npm run dev
```

A API atende em `http://localhost:8000` e a interface usa `http://localhost:5173`.

O primeiro acesso é criado localmente, sem senha padrão no repositório:

```powershell
python -m scripts.create_admin --name "Administrador" --email admin@empresa.com
```

Depois do login, o admin cadastra banco e advogados; o banco abre e atribui processos;
o advogado acessa somente os processos atribuídos, executa a avaliação e registra a decisão.

O fluxo de telas, os limites de acesso e os cuidados para implantação estão em
`docs/fluxo_papeis_frontend.md`.

## Estrutura

- `src/policy/`: motor de política e serviço que relaciona documentos com recomendações.
- `src/interface/backend/`: API FastAPI, contratos HTTP, configuração e persistência SQLite.
- `src/interface/frontend/`: aplicação React/Vite conectada à API.
- `src/utils/`: extração de documentos e verificação determinística de tipo.
- `src/monitor/`: análises históricas e simulações offline.
- `contracts/` e `src/tools/`: contratos e analisador de dossiê com extração estruturada e evidências por página.
- `src/graph.py`: workflow LangGraph opcional para extração e revisão, separado da política ativa da API.
- `src/interface/prototype/`: desenho de tela da `main` com exemplos estáticos, separado da aplicação conectada à API.
- `artefatos/`, `scripts/` e `tests/`: modelo treinado, preparação/treinamento e testes, respectivamente.

O armazenamento continua em `.runtime/` na raiz do repositório. `ENTERAGREE_RUNTIME_DIR`,
`ENTERAGREE_DATABASE_PATH` e `ENTERAGREE_MAX_UPLOAD_BYTES` mantêm os mesmos significados.
O artefato XGBoost permanece em `artefatos/`; a migração de diretórios não exige retreinamento.

`src.policy.engine.PolicyEngine` continua sendo o motor usado pela API documental.
A função `src.policy.engine.decidir` preserva o contrato `CaseFeatures` da `main`
e sua política por segmentos (`DEFENDER`, `ACORDAR`, `RECUPERAR`). As duas APIs
mantêm suas regras e testes; esta migração não troca a política ativa silenciosamente.
Os módulos `src/policy/backtest.py` e `src/policy/learning.py` também são preservados
da `main` como ferramentas offline, sem integração automática ao fluxo documental.
O cenário de extração do backtest assume sinais a partir das flags; não executa IA
nos documentos nem comprova resultados financeiros de produção.

O CORS local permite `localhost` e `127.0.0.1`, nas portas 5173 (desenvolvimento)
e 4173 (preview). Para outras origens, configure `ENTERAGREE_CORS_ORIGINS` com
uma lista separada por vírgulas.

## Verificar

Execute a partir da raiz:

```powershell
python -m pytest -q
python -m compileall -q src scripts tests
npm --prefix src/interface/frontend run build
```

Os comandos `make setup`, `make test`, `make api`, `make frontend` e `make build`
são atalhos opcionais. `make schema` (ou `python -m scripts.export_policy_schema`)
gera `src/interface/prototype/schema.json` a partir dos contratos da política por segmentos.
Esse JSON não substitui os contratos HTTP, disponíveis em `/openapi.json`.

Testes de navegador, executando o bundle de produção:

```powershell
cd src/interface/frontend
npx playwright install chromium
npm run test:e2e
```

Veja o [guia Git](docs/guia_conformidade_git.md), o
[plano de migração](docs/plano_refatoracao_estrutura_src.md) e o
[comparativo de diretórios](docs/comparativo_e_reestruturacao_diretorios.md).

## Fluxo implementado

1. O advogado cria um caso e o banco ou advogado envia um PDF/TXT com o tipo documental declarado.
2. O upload é persistido por streaming, o texto é extraído em lotes de 100 páginas e o tipo declarado é conferido por sinais determinísticos, sem LLM.
3. Tipos confirmados ativam exclusivamente as variáveis do motor de política; incompatibilidades exigem reclassificação, continuação com ressalva ou remoção.
4. A política registra recomendação, faixa de acordo, vetor de atributos, origem de cada atributo, limitações e decisão posterior do advogado.
5. O banco acompanha análises, decisões e aderência em `GET /api/monitoring`.

## Análise auxiliar de dossiê

Instale o extra opcional e configure a chave somente no servidor:

```powershell
python -m pip install -e ".[dossie]"
$env:OPENAI_API_KEY = "sua-chave"
$env:ENTERAGREE_DOSSIE_MODEL = "gpt-4o-mini"
python -m uvicorn src.interface.backend.main:app --reload
```

Após enviar um documento do tipo `DOSSIE` e concluir a extração, use **Analisar
dossiê com IA**. A operação envia texto à OpenAI apenas mediante esse comando.
Mostra parecer do perito, exame da assinatura contratual, índices, contrato
referenciado e citações. Informação ausente permanece desconhecida, não zero.
O resultado é auxiliar: não autentica documentos, não ativa a presença de contrato
e não altera automaticamente a política G9. A falta de chave retorna erro explícito,
sem impedir os demais fluxos da aplicação. Arquivos `.env` não são carregados automaticamente.

Consulte [implementação e auditoria do analisador](docs/dossie_analyser_implementacao.md)
para limites, cache, endpoints, revisão humana e testes.

## Modelo e dados

`artefatos/modelo_xgboost.pkl` foi reproduzido pelos scripts originais do Grupo 9 a partir da base recebida. Para gerar novamente, disponibilize a planilha e execute:

```powershell
python scripts/01_prepare_data.py --input ..\Hackaton_Enter_Base_Candidatos.xlsx --output artefatos
python scripts/02_train_model.py --input artefatos
```

Na reprodução local: AUC de validação cruzada `0.9079 ± 0.0013`, AUC de teste `0.9045` e Brier `0.1027`. Esses números são retrospectivos e não constituem validação de produção.

## Limites e evolução

Esta entrega usa SQLite e tarefas em processo para demonstração. Produção requer armazenamento de objetos, fila de workers, banco transacional, autenticação/autorização, criptografia, antivírus, auditoria imutável e observabilidade. Páginas com pouco texto são sinalizadas; a métrica de qualidade e a etapa de OCR estão explicitamente pendentes. A extração de dossiê já complementa a leitura documental, mas não substitui a política nem a confirmação determinística de tipo. RAG e validação cruzada entre documentos continuam pendentes.

Consulte `docs/arquitetura.md` para contrato, estados e critérios de evolução.

## Feature planejada: acesso por perfil

O [plano de banco, advogado, admin global e login](docs/plano_acesso_banco_advogado_admin.md) define telas, permissões, sessões, migração, contratos e critérios de aceite para a próxima implementação. Nesta entrega, somente o documento foi criado; autenticação e áreas separadas ainda não estão implementadas.
