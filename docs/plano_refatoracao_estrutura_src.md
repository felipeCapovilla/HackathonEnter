# Plano de Refatoração Física da Estrutura para `src/` — EnterAgree

Este documento especifica detalhadamente o **plano de execução** para refatorar a estrutura física de arquivos do repositório **EnterAgree**, migrando da arquitetura atual (`backend/` + `frontend/`) para a arborescência padronizada sob o diretório `src/` exigida na branch `main`.

> [!IMPORTANT]  
> Este documento é uma especificação técnica e plano de ação. As etapas descritas abaixo devem ser executadas somente após aprovação do time de desenvolvimento.

---

## 1. Mapeamento Geral de Migração (De / Para)

| Arquivo/Pasta Atual | Novo Destino sob `src/` | Responsabilidade |
| :--- | :--- | :--- |
| `backend/app/policy_service.py` | `src/policy/service.py` | Regras de política de acordo, faixas de valor e modelo XGBoost |
| `src/policy/*` (engine, pricing, etc.) | `src/policy/` | Motores determinísticos e constantes numéricas da política |
| `backend/app/document_service.py` | `src/utils/document_service.py` | Extração em streaming de PDFs e integração OCR |
| `backend/app/document_type_validator.py` | `src/utils/document_type_validator.py` | Validação de sinais determinísticos dos documentos |
| `backend/app/rag/` | `src/utils/rag/` | Componente RAG, embeddings e chunking semântico |
| `backend/app/main.py` | `src/interface/backend/main.py` | Servidor Web e rotas da API (FastAPI) |
| `backend/app/database.py` | `src/interface/backend/database.py` | Configuração do banco de dados SQLite e sessão SQLAlchemy |
| `backend/app/repository.py` | `src/interface/backend/repository.py` | Camada de acesso a dados (CRUD de Casos e Análises) |
| `backend/app/schemas.py` | `src/interface/backend/schemas.py` | Esquemas Pydantic de requisição e resposta |
| `backend/app/auth.py` | `src/interface/backend/auth.py` | Autenticação e permissões por perfil (Banco, Advogado, Admin) |
| `backend/app/monitoring.py` | `src/interface/backend/monitoring.py` | Endpoints de métricas gerenciais e aderência |
| `frontend/` | `src/interface/frontend/` | Interface do Usuário (Single Page Application em React + Vite) |
| `src/monitor/` | `src/monitor/` (mantido) | Scripts de análise contrafactual e aderência |

---

## 2. Nova Arborescência Alvo

Após a execução da refatoração, o repositório terá a seguinte estrutura física de arquivos:

```text
HackatonEnter/
├── src/
│   ├── policy/                     # Lógica de Políticas de Acordo & Modelo ML
│   │   ├── __init__.py
│   │   ├── engine.py               # Motor determinístico
│   │   ├── service.py              # policy_service.py refatorado
│   │   ├── pricing.py              # Regras de faixas e valores
│   │   ├── normalization.py        # Normalização de atributos
│   │   └── constants.py            # Limiares e parâmetros
│   │
│   ├── utils/                      # Processamento de Documentos e RAG
│   │   ├── __init__.py
│   │   ├── document_service.py     # Extração de texto e OCR
│   │   ├── document_type_validator.py # Sinais determinísticos
│   │   └── rag/                    # Embeddings, retriever e chunker
│   │
│   ├── interface/                  # Interfaces de Acesso (API & Web)
│   │   ├── backend/                # Servidor FastAPI
│   │   │   ├── main.py             # App FastAPI & Rotas
│   │   │   ├── database.py         # Configuração DB
│   │   │   ├── repository.py       # Data Access Object
│   │   │   ├── schemas.py          # Pydantic Models
│   │   │   ├── auth.py             # Autenticação JWT / Perfis
│   │   │   └── monitoring.py       # API de Monitoramento
│   │   └── frontend/               # Dashboard React SPA
│   │       ├── src/                # Componentes React (JSX, CSS)
│   │       ├── package.json
│   │       └── vite.config.js
│   │
│   └── monitor/                    # Análises e Métricas Offline
│       ├── counterfactual.py
│       ├── baseline.py
│       └── metrics_effectiveness.py
│
├── artefatos/                      # Modelo XGBoost binário (.pkl) e artefatos
├── docs/                           # Documentação arquitetural
├── scripts/                        # Scripts de treinamento e preparação
├── tests/                          # Suíte de testes (pytest)
├── Dockerfile & docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 3. Roteiro Passo a Passo para Execução Futura

Quando for autorizada a execução da refatoração física, siga os passos ordenados abaixo:

### Passo 1: Criar novas pastas com `mkdir`
```powershell
mkdir -p src/interface/backend
mkdir -p src/interface/frontend
mkdir -p src/utils
```

### Passo 2: Mover arquivos preservando o histórico (`git mv`)
```powershell
# 1. Mover backend app para src/interface/backend
git mv backend/app/main.py src/interface/backend/
git mv backend/app/database.py src/interface/backend/
git mv backend/app/repository.py src/interface/backend/
git mv backend/app/schemas.py src/interface/backend/
git mv backend/app/auth.py src/interface/backend/
git mv backend/app/monitoring.py src/interface/backend/
git mv backend/app/config.py src/interface/backend/

# 2. Mover utilitários de documento e RAG para src/utils
git mv backend/app/document_service.py src/utils/
git mv backend/app/document_type_validator.py src/utils/
git mv backend/app/rag src/utils/

# 3. Mover serviço de política para src/policy
git mv backend/app/policy_service.py src/policy/service.py

# 4. Mover frontend para src/interface/frontend
git mv frontend/* src/interface/frontend/

# 5. Remover pasta backend vazia
rmdir backend/app
rmdir backend
```

### Passo 3: Atualizar Referências e Imports Python

Atualizar as declarações de `import` nos seguintes arquivos:

1. Em `src/interface/backend/main.py`:
   ```python
   # Antes:
   from backend.app.policy_service import calcular_politica
   from backend.app.document_service import extrair_documento

   # Depois:
   from src.policy.service import calcular_politica
   from src.utils.document_service import extrair_documento
   ```

2. Em `tests/` (`test_auth.py`, `test_rag.py`, `test_sla_and_ocr.py`, `test_dossie_renaming.py`):
   Ajustar `sys.path` ou os imports para apontar para os módulos em `src.policy`, `src.utils` e `src.interface.backend`.

### Passo 4: Atualizar Arquivos de Configuração e Build

1. **`README.md`**:
   Atualizar os comandos de execução no PowerShell:
   ```powershell
   # Executar Backend:
   python -m uvicorn src.interface.backend.main:app --reload

   # Executar Frontend:
   cd src/interface/frontend
   npm install
   npm run dev
   ```

2. **`Dockerfile` & `docker-compose.yml`**:
   Atualizar os caminhos do `WORKDIR` e `CMD`:
   ```dockerfile
   CMD ["uvicorn", "src.interface.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

3. **`scripts/seed_database.py`**:
   Ajustar a importação de `database.py` e `repository.py` para `src.interface.backend`.

### Passo 5: Validação e Testes Automatizados

Após a refatoração, execute as seguintes verificações para garantir que nenhuma regressão foi introduzida:

```powershell
# 1. Executar testes automatizados
pytest

# 2. Testar inicialização da API Backend
python -m uvicorn src.interface.backend.main:app --port 8000

# 3. Testar build do Frontend
cd src/interface/frontend
npm run build
```

### Passo 6: Commit com Conventional Commits
```powershell
git add .
git commit -m "refactor: restructure project directories into src/policy, src/interface, and src/utils"
```
