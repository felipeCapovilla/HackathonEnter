# Plano de refatoração física para src — EnterAgree

> **Nota (12/09):** documento histórico do plano de migração. O `PolicyEngine`, o modelo XGBoost
> e seus artefatos foram removidos depois; a política ativa é `src/policy/engine.decidir`.

A execução deste plano foi solicitada para preparar a integração com main. A escolha é mover fisicamente a implementação para `src/policy`, `src/utils` e `src/interface`, preservando contratos e comportamento. Não basta criar módulos que reexportem a aplicação dos diretórios antigos.

O plano foi revisado contra a implementação documental e `origin/main`, inicialmente em `07de512b` e posteriormente em `1ab771bc`, após atualização do histórico remoto. Ambas as referências foram integradas. A árvore remota contém `contracts/`, `src/policy/`, `src/tools/`, `web/` e testes, mas não exige esta organização de API e React. O alinhamento é uma decisão desta entrega. O roteiro define os critérios; a seção final registra as verificações concluídas.

## Mapeamento

| Origem anterior à migração | Destino | Responsabilidade |
| --- | --- | --- |
| `backend/app/policy_service.py` | `src/policy/service.py` | `PolicyService`: compor documentos, chamar o motor e persistir a análise |
| `src/policy/engine.py` | Mesmo caminho | `PolicyEngine`: regras e XGBoost; preservar também a API `decidir(CaseFeatures)` de main |
| `src/policy/{constants,normalization,pricing}.py` | Mesmos caminhos | Atributos, normalização e cálculo financeiro |
| `backend/app/document_service.py` | `src/utils/document_service.py` | `DocumentService`: streaming e extração PDF/TXT |
| `backend/app/document_type_validator.py` | `src/utils/document_type_validator.py` | `validate_document_type`: sinais determinísticos |
| `backend/app/{main,config,database,repository,schemas,monitoring}.py` | `src/interface/backend/`, mesmos nomes | API, configuração, SQLite via sqlite3, persistência, Pydantic e resumo operacional |
| `backend/app/__init__.py` | `src/interface/backend/__init__.py` | Pacote Python da API |
| `frontend/` | `src/interface/frontend/` | React/Vite, incluindo package-lock e entradas HTML/JSX |
| `src/monitor/` | Mesmo caminho | Análises offline e métricas |
| `artefatos/`, `scripts/`, `tests/` | Mesmos caminhos na raiz | Modelo, treinamento e testes |
| `contracts/`, `src/tools/`, `src/policy/{gate,table,backtest,learning}.py` de main | Mesmos caminhos | Contratos, componentes remotos e ferramentas offline preservados |
| `web/` de main | `src/interface/prototype/` | Demonstrador com dados simulados, documentado e separado do frontend ativo |

`engine.py` não é o destino do serviço: substituir o motor pelo antigo `policy_service.py` apagaria suas responsabilidades. `artefatos/modelo_xgboost.pkl`, `features.json` e métricas permanecem na raiz, sem copiar nem retreinar o modelo.

`PolicyEngine` legado (removido) e `decidir(CaseFeatures)` de main representam contratos e lógicas diferentes. Preservar as duas interfaces e testar cada uma; não declarar que foram unificadas nem mudar silenciosamente a lógica consumida pelo fluxo documental. O serviço documental continua chamando `PolicyEngine`.

Não existem na implementação documental revisada `auth.py`, pacote RAG, Dockerfile, docker-compose ou `seed_database.py`. Login/perfis, RAG e OCR permanecem planejados; sua ausência não é corrigida criando implementações fictícias. Sinalizar páginas com pouco texto não comprova execução de OCR. O banco usa `sqlite3`, sem sessão SQLAlchemy.

## Estrutura de destino

```text
HackatonEnter/
├── contracts/
├── src/
│   ├── __init__.py
│   ├── policy/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── service.py
│   │   ├── constants.py
│   │   ├── normalization.py
│   │   ├── pricing.py
│   │   ├── gate.py
│   │   ├── backtest.py
│   │   ├── learning.py
│   │   └── table.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── document_service.py
│   │   └── document_type_validator.py
│   ├── interface/
│   │   ├── __init__.py
│   │   ├── backend/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── repository.py
│   │   │   ├── schemas.py
│   │   │   └── monitoring.py
│   │   ├── frontend/
│   │   │   ├── src/
│   │   │   ├── index.html
│   │   │   ├── package.json
│   │   │   └── package-lock.json
│   │   └── prototype/
│   ├── monitor/
│   └── tools/
├── artefatos/
├── scripts/
├── tests/
├── docs/
├── requirements.txt
├── pyproject.toml
├── Makefile
└── README.md
```

## Roteiro em seis passos

### 1. Inventariar e preparar

Na raiz, conferir `git status --short`, `git worktree list` e o diff pendente. Preservar as correções de auditoria existentes. Atualizar `origin/main` e comparar `contracts/`, `src/policy/`, `tests/test_smoke.py`, `pyproject.toml`, `Makefile` e `web/` antes de resolver sobreposições. O guia Git descreve a publicação sem reescrita de histórico.

Criar os diretórios Python sem pré-criar a pasta que receberá a aplicação frontend inteira:

```powershell
New-Item -ItemType Directory -Force src/interface/backend, src/utils
```

Esse comando é PowerShell, não Bash. Se os destinos já contiverem arquivos, conferir seu conteúdo antes de mover.

### 2. Mover módulos e preservar pacotes

Movimentações rastreáveis de referência:

```powershell
git mv backend/app/main.py src/interface/backend/main.py
git mv backend/app/config.py src/interface/backend/config.py
git mv backend/app/database.py src/interface/backend/database.py
git mv backend/app/repository.py src/interface/backend/repository.py
git mv backend/app/schemas.py src/interface/backend/schemas.py
git mv backend/app/monitoring.py src/interface/backend/monitoring.py
git mv backend/app/__init__.py src/interface/backend/__init__.py
git mv backend/app/document_service.py src/utils/document_service.py
git mv backend/app/document_type_validator.py src/utils/document_type_validator.py
git mv backend/app/policy_service.py src/policy/service.py
git mv frontend src/interface/frontend
```

Uma edição equivalente que registre adição e remoção dos mesmos arquivos é válida; o Git reconhece renomes pelo conteúdo. Preservar mudanças locais. Criar `src/interface/__init__.py` e `src/utils/__init__.py`, manter `src/__init__.py` e `src/policy/__init__.py`, e remover apenas o antigo `backend/__init__.py` após conferir que não contém lógica.

Após integrar main, mover seu `web/` para `src/interface/prototype/` e documentar que é um demonstrador com dados simulados. Ele não substitui o frontend que usa a API. Não adicionar `node_modules/` ou `dist/` ao índice. Não usar remoção recursiva para limpar diretórios antigos que possam conter arquivos locais.

### 3. Corrigir imports e caminhos

Em `src/interface/backend/main.py`, usar os nomes reais:

```python
from src.policy.service import PolicyService
from src.utils.document_service import DocumentService
from src.utils.document_type_validator import validate_document_type
```

Imports locais da API, como `from .repository import Repository`, continuam relativos. Em `src/policy/service.py`, importar `Repository` e enums por `src.interface.backend.repository` e `src.interface.backend.schemas`. Em `src/utils/document_service.py`, importar `Settings`, `Repository` e schemas por `src.interface.backend`; manter o import relativo do validador. O validador importa enums por `src.interface.backend.schemas`.

A migração preserva dependências existentes do serviço em relação à persistência e aos schemas da API. Isso não representa separação completa entre domínio e infraestrutura. Evitar reexportar `PolicyService` no `src/policy/__init__.py` se causar importação circular ou carregar a API ao importar apenas o motor.

No `config.py` movido, o nome existente é `PROJECT_ROOT`, não `REPO_ROOT`. Ajustar a profundidade:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[3]
```

Isso mantém `.runtime/` e `artefatos/` na raiz. `src/monitor/paths.py` tem sua própria resolução de raiz e não foi movido; não alterar sua profundidade indiscriminadamente. Preservar `ENTERAGREE_RUNTIME_DIR`, `ENTERAGREE_DATABASE_PATH` e `ENTERAGREE_MAX_UPLOAD_BYTES`.

Atualizar imports reais de `tests/test_api.py`, `tests/test_database.py` e `tests/test_monitoring.py` para `src.interface.backend`. Preservar testes do motor e verificar caminhos e entrypoint, sem alterar `sys.path` artificialmente para sustentar o caminho antigo.

### 4. Atualizar configuração, frontend e instruções

Atualizar `.gitignore` para ignorar `src/interface/frontend/node_modules/` e `src/interface/frontend/dist/`. Preservar `package-lock.json` e imports de JSX, CSS e `index.html`.

No README e no alvo `api` do Makefile integrado de main, usar:

```powershell
python -m uvicorn src.interface.backend.main:app --reload --port 8000
```

Para o frontend, a partir da raiz:

```powershell
npm --prefix src/interface/frontend ci
npm --prefix src/interface/frontend run dev
```

Revisar `pyproject.toml` para instalar os pacotes e dependências reais. Ajustar o alvo `schema` do Makefile ao novo destino do protótipo. Atualizar o README do frontend e `docs/arquitetura.md`. Preservar URLs `/api/...`, payloads, status HTTP e configuração do endereço da API; mover arquivos não autoriza alterar rotas.

### 5. Validar comportamento e árvore final

Executar na raiz, com as dependências instaladas:

```powershell
python -m pytest -q
python -m compileall -q src contracts scripts tests
npm --prefix src/interface/frontend run build
git diff --check
rg -n 'backend\.app|backend/app|cd frontend|src\.api\.main' src tests scripts README.md Makefile pyproject.toml
```

Ausência de referências antigas no último comando retorna código 1 do `rg`, o que não é falha de compilação. Documentos de migração podem citar caminhos antigos como origem, mas comandos operacionais devem apontar para os novos destinos.

- [x] API inicia pelo novo entrypoint e sua rota de saúde responde.
- [x] `PROJECT_ROOT`, artefatos e runtime padrão continuam na raiz; overrides funcionam.
- [x] Criação/listagem de processos, upload, consulta documental, solicitação e resposta, análise, decisão e monitoramento mantêm seus contratos.
- [x] Uploads concorrentes/duplicados, vínculo com solicitação e transições preservam as correções existentes.
- [x] Modelo real carrega de `artefatos/`; regras legadas e `decidir(CaseFeatures)` continuam cobertas separadamente.
- [x] Testes de main e testes documentais passam juntos, sem descartar um conjunto para obter sucesso.
- [x] React compila e consome a mesma API; renderização inicial e navegação existente continuam funcionais.
- [x] Protótipo de main está identificado como demonstrador e não aparece como frontend operacional.
- [x] Nenhum módulo depende de `backend.app`; nenhuma árvore dupla `frontend/frontend` foi criada.
- [x] `git status` não inclui runtime, bases locais, ambientes virtuais, dependências instaladas ou builds.

Comparar o inventário de rotas em execução ao anterior: testar somente saúde não comprova os demais fluxos. Não retreinar XGBoost para validar uma movimentação de diretórios.

### 6. Revisar e publicar

Revisar diff, documentação e resultados. Registrar migração e integração com mensagens descritivas, publicar `feat/docs-pipeline` e criar ou atualizar o PR para main, seguindo `guia_conformidade_git.md`. Incluir limitações e verificações executadas. Manter a branch remota antiga enquanto seu PR estiver ativo. Criar o PR não autoriza seu merge.

## Evidências desta execução — 12/09/2026

Os seis passos foram executados. A integração preserva a referência inicial
`07de512b`, a atualização remota `1ab771bc` e os commits da branch de documentação.
As mudanças posteriores de gate, ajuste de UF em log-odds, alertas, backtest e
aprendizado de aceitação foram conciliadas sem substituir o motor ativo legado (removido).
O resultado está publicado em
`feat/docs-pipeline`, no [PR #3](https://github.com/felipeCapovilla/HackatonEnter/pull/3).

| Verificação | Resultado observado |
| --- | --- |
| `python -m pytest -q` | 24 testes passaram, incluindo os oito testes da main atualizada |
| `python -m compileall -q src contracts scripts tests` | Sem erros |
| Importação de módulos | 34 módulos Python de `src`/`contracts` importados; monitor offline carrega o artefato real |
| Instalação editável | `python -m pip install --no-deps --no-build-isolation -e .` passou no ambiente com dependências instaladas |
| Schema | `python -m scripts.export_policy_schema` gerou os contratos do protótipo no destino correto |
| API real | Uvicorn pelo novo entrypoint; saúde 200; processo criado, dois uploads e análise com `policy_source=MODEL` |
| Compatibilidade HTTP | 13 pares método/rota anteriores preservados; OpenAPI publica 12 caminhos |
| Regras da main | AST das quatro funções de decisão idêntico a `1ab771bc`; contratos e testes mantidos |
| Ferramentas offline da main | Backtest e atualização Beta-Binomial importados e exercitados com exemplos isolados; sem reexecutar a base histórica |
| Frontend | Build passou; cinco regressões Playwright no Chrome executaram o bundle de produção com API interceptada apenas nos testes |
| Fluxo integrado real | Chrome + Vite + FastAPI em portas isoladas: criação, solicitação, envio vinculado, dois documentos, XGBoost e decisão persistida; zero erros de página |
| Protótipo | Build separado passou; exemplos estáticos identificados no README |
| Dependências JavaScript | `npm audit --audit-level=high` completo: zero vulnerabilidades nas duas aplicações |
| Diretórios e artefatos | Sem imports do pacote antigo nem arquivos versionados em `backend/`, `frontend/`, `web/` ou `venv/`; artefatos mantidos sem retreino |

Vite foi atualizado para 7.3.6 e requer Node 20.19 (linha 20) ou 22.12+.
As origens locais de desenvolvimento/preview são configuráveis por
`ENTERAGREE_CORS_ORIGINS`. Os comandos do Makefile possuem equivalentes Python/npm
no README; `make` não estava instalado no ambiente Windows desta validação.

A verificação é da refatoração e dos fluxos atuais. Não inclui validação de OCR,
extração semântica, autenticação, desempenho de 600 páginas/s ou eficácia jurídica
em produção, que permanecem fora desta entrega.
O backtest de main simula sinais de dossiê a partir de flags; preservá-lo e
executar exemplos não valida extração por IA nem comprova economia financeira.
