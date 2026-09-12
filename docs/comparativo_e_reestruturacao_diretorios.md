# Comparativo e decisão de reestruturação — EnterAgree

A decisão desta entrega é migrar fisicamente API, frontend e serviços documentais para `src/`, mantendo motor e artefatos nos locais apropriados. Este documento compara fontes verificadas; a organização proposta não é uma imposição presumida de main.

## 1. Fontes e estado observado

A revisão usa a implementação documental originada em `(feat)_docs_pipeline`, com correções locais, e `origin/main`, inicialmente em `07de512b` e depois em `1ab771bc`. A atualização do histórico remoto foi integrada preservando as novas correções do motor. Não existe `README.md` nessas referências; portanto, não há ali uma árvore publicada que exija `src/interface/` ou `src/utils/`.

Árvore resumida da referência remota:

```text
main/
├── contracts/
├── src/
│   ├── policy/
│   └── tools/
├── tests/
├── web/
├── .env.example
├── pyproject.toml
└── Makefile
```

Implementação documental antes da migração:

```text
HackatonEnter/
├── backend/app/
├── frontend/
├── src/
│   ├── policy/
│   └── monitor/
├── artefatos/
├── scripts/
├── tests/
├── docs/
├── requirements.txt
└── README.md
```

`src/policy/` já existe na implementação documental. Não é correto reduzir sua equivalência a `policy_service.py` e aos artefatos: motor, normalização e cálculo financeiro têm módulos próprios. A API não implementa login ou áreas isoladas para Banco, Advogado e Admin; isso permanece no plano de acesso.

## 2. Matriz de responsabilidades

| Responsabilidade | Origem documental | Destino escolhido | Integração com main |
| --- | --- | --- | --- |
| Decisão por regras e modelo | `src/policy/engine.py` | Mesmo caminho | Preservar `PolicyEngine` e a API remota `decidir(CaseFeatures)` |
| Composição e persistência da análise | `backend/app/policy_service.py` | `src/policy/service.py` | Serviço separado do motor, consumindo `PolicyEngine` |
| Atributos, normalização e valores | `src/policy/{constants,normalization,pricing}.py` | Mesmos caminhos | Conciliar sobreposições e preservar `gate.py` e `table.py` |
| Backtest e aprendizado de aceitação remotos | Ausentes antes da atualização de main | `src/policy/{backtest,learning}.py` | Ferramentas offline preservadas; não conectadas automaticamente à API documental |
| Upload e extração PDF/TXT | `backend/app/document_service.py` | `src/utils/document_service.py` | Preservar streaming e lotes |
| Conferência de tipo | `backend/app/document_type_validator.py` | `src/utils/document_type_validator.py` | Preservar confirmação e incompatibilidades determinísticas |
| API e persistência | `backend/app/{main,config,database,repository,schemas,monitoring}.py` | `src/interface/backend/` | Preservar schemas e integrar contratos sem regressão |
| Interface operacional React/Vite | `frontend/` | `src/interface/frontend/` | Continua consumindo a API real |
| Protótipo remoto | `web/` de main | `src/interface/prototype/` | Demonstrador com dados simulados, identificado como tal |
| Modelo e metadados | `artefatos/` | Mesmo caminho na raiz | Não mover binários para o pacote nem retreinar |
| Monitoramento offline | `src/monitor/` | Mesmo caminho | Preservar consumidores e caminhos |
| Contratos e ferramentas remotos | Ausentes ou distintos antes do merge | `contracts/`, `src/tools/` | Preservar módulos, dependências e testes |
| Treinamento e testes | `scripts/`, `tests/` | Mesmos caminhos na raiz | Atualizar imports e executar testes das duas origens |

## 3. Migração escolhida

Utilizar a migração física de `plano_refatoracao_estrutura_src.md`. Manter `backend/` e `frontend/` e acrescentar wrappers não atende à escolha de alinhar os diretórios.

1. `PolicyService` vai para `service.py`; `engine.py` continua motor. `PolicyEngine` e `decidir(CaseFeatures)` possuem contratos e regras diferentes: preservar e testar ambos, sem declarar uma unificação silenciosa.
2. `artefatos/`, `scripts/`, `tests/` e `src/monitor/` permanecem. `contracts/`, `src/tools/` e componentes úteis de main são preservados. O protótipo remoto fica explicitamente separado da aplicação operacional.
3. Pacotes Python recebem os `__init__.py` necessários; imports apontam para destinos reais.
4. `src/interface/backend/config.py` usa `PROJECT_ROOT = Path(__file__).resolve().parents[3]`, mantendo runtime e artefatos na raiz.
5. Rotas, payloads e fluxos documentais mantêm compatibilidade. Mover React não muda o endereço da API.
6. Login/perfis, RAG e OCR permanecem planejados. A refatoração não cria autenticação, embeddings, Docker ou seed inexistentes para corresponder a uma árvore imaginada.

## 4. Evidências de conclusão

Os documentos são complementares: este registra a decisão e as equivalências; o plano contém seis passos e validações; o guia Git define publicação e preservação do histórico.

- [x] API em `src/interface/backend`, React em `src/interface/frontend`, serviços em `src/utils` e orquestração em `src/policy/service.py`.
- [x] Imports, raiz de configuração, Makefile, dependências e comandos correspondem à árvore real.
- [x] Contratos e testes de main foram integrados aos fluxos documentais existentes.
- [x] Artefatos e dados locais permanecem preservados.
- [x] Testes automatizados, inicialização da API e build React verificados pelos novos caminhos.
- [x] Protótipo remoto identificado como demonstrador; frontend operacional continua sem dados simulados.
- [x] Publicação em `feat/docs-pipeline` e PR para main descrevem o resultado sem declarar funcionalidades planejadas como prontas.

Mover arquivos não basta para comprovar a reestruturação: verificar os novos entrypoints, fluxos e contratos é parte da entrega.

## Resultado

Migração física executada e integrada à main de referência. As evidências e
os comandos verificados estão no
[plano de refatoração](plano_refatoracao_estrutura_src.md#evidências-desta-execução--12092026).
Código e documentos publicados em `origin/feat/docs-pipeline`, com revisão no
[PR #3 para main](https://github.com/felipeCapovilla/HackatonEnter/pull/3).
