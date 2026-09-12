# Comparativo e Reestruturação do Repositório — Proposta `main` vs. Implementação Atual

Este documento analisa as diferenças entre a **estrutura proposta na branch `main` (repositório base do hackathon)** e a **estrutura implementada na branch de desenvolvimento (`HackatonEnter`)**, fornecendo os planos de ação para colocar o projeto em total conformidade.

---

## 1. Mapeamento das Estruturas

### 🏛️ Estrutura Proposta na `main` (Base Original)
A proposta padrão da `main` organiza o código-fonte sob o diretório `src/`:

```text
hackathon-ufmg-2026/
├── src/
│   ├── policy/            # Lógica da política de acordos (regras de decisão, modelo XGBoost, cálculo de faixas)
│   ├── interface/         # Interface de acesso do advogado / servidor Web (ex: Flask ou FastAPI + visualizações)
│   └── utils/             # Extratores de PDF/TXT, validadores e utilitários compartilhados
├── data/                  # Planilhas e dados de entrada
├── docs/                  # Documentação arquitetural e de uso
├── environment.yml / requirements.txt
└── README.md
```

---

### 🚀 Estrutura Implementada Atualmente (`HackatonEnter`)
A implementação atual adotou uma arquitetura moderna Full-Stack desacoplada (`backend` + `frontend`):

```text
HackatonEnter/
├── backend/               # Servidor FastAPI
│   └── app/
│       ├── main.py        # Endpoints da API
│       ├── policy_service.py # Motor de regras e política
│       ├── document_service.py # Processamento de PDFs e OCR
│       └── repository.py  # Persistência SQLite
├── frontend/              # Interface SPA (React + Vite)
│   └── src/               # Componentes visuais e dashboards
├── artefatos/             # Modelo XGBoost (.pkl), features.json e métricas
├── scripts/               # Scripts de preparação de dados e treinamento
├── tests/                 # Testes automatizados (pytest)
├── docs/                  # Planos e documentações arquiteturais
├── Dockerfile & docker-compose.yml
└── README.md
```

---

## 2. Comparativo de Equivalência de Módulos

| Módulo Proposto na `main` (`src/`) | Equivalente Implementado no Projeto (`HackatonEnter`) | Função |
| :--- | :--- | :--- |
| `src/policy/` | `backend/app/policy_service.py` & `artefatos/` | Regras determinísticas de acordo + modelo XGBoost reproduzido |
| `src/interface/` | `frontend/` & `backend/app/main.py` | Dashboard React + Endpoints REST do advogado/banco |
| `src/utils/` | `backend/app/document_service.py` & `document_type_validator.py` | Extração por streaming, OCR e validação de PDFs |

---

## 3. Planos de Ação para Conformidade

Oferecemos duas alternativas para alinhar o repositório à `main`:

### 🔹 Opção 1: Migração Completa para a Estrutura `src/` (Fidelidade Restrita à `main`)
Reorganizar fisicamente as pastas para responder exatamente à arborescência de `main`:

- Mover `backend/app/policy_service.py` e artefatos para `src/policy/`
- Mover a API FastAPI e a aplicação Frontend React para `src/interface/` (`src/interface/backend` e `src/interface/frontend`)
- Mover os serviços de extração e validação de documentos para `src/utils/`

#### Árvore Resultante (Opção 1):
```text
src/
├── policy/
│   ├── engine.py           # policy_service.py refatorado
│   ├── modelo_xgboost.pkl  # artefato do modelo
│   └── features.json
├── interface/
│   ├── backend/            # FastAPI app
│   └── frontend/           # React + Vite app
└── utils/
    ├── document_extractor.py
    └── validator.py
```

---

### 🔹 Opção 2: Compatibilidade via Wrappers & Mapeamento no `src/` (Recomendado)
Manter a separação limpa `backend/` + `frontend/` e adicionar um módulo adaptador dentro de `src/` que reexporta os componentes principais.

No `src/`:
- `src/policy/__init__.py`: importa `policy_service.py` do backend.
- `src/interface/__init__.py`: redireciona para a aplicação backend/frontend.
- `src/utils/__init__.py`: importa `document_service.py`.

Essa abordagem preserva a execução de testes automatizados (`pytest`), contêineres Docker e ferramentas de build do React sem quebrar os caminhos originais do projeto.

---

## 4. Checklist para Mudança da Estrutura

- [ ] Escolha entre a **Opção 1** (Reestruturação física em `src/`) ou **Opção 2** (Mapeamento/Adaptação no `src/`).
- [ ] Atualização dos caminhos de importação nos testes em `tests/`.
- [ ] Atualização dos comandos de execução no `README.md` principal.
- [ ] Execução da suíte de testes (`pytest`) para validar a integridade.
