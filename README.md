# ENTER | Política de acordos

EnterAgree é a aplicação de política de acordos para casos de não reconhecimento
de empréstimo. Combina a política híbrida do Grupo 9, regras determinísticas,
XGBoost e evidência documental auditável. Banco, advogado e administrador têm
áreas separadas, com autenticação e controle de acesso no backend.

## Executar a demonstração local

Requisitos: Python 3.11+ e Node.js 20.19+ (linha 20) ou 22.12+. Os comandos abaixo
usam PowerShell, a partir da raiz do repositório. Não dependem de Docker.

```powershell
python -m pip install -r requirements.txt
python -m scripts.seed_demo --confirm-demo
$env:ENTERAGREE_RUNTIME_DIR = Join-Path (Get-Location) '.runtime/demo'
$env:ENTERAGREE_DATABASE_PATH = Join-Path $env:ENTERAGREE_RUNTIME_DIR 'enteragree.db'
$env:ENTERAGREE_AUTH_REQUIRED = 'true'
python -m uvicorn src.interface.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Em outro terminal:

```powershell
cd src/interface/frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Acesse **http://127.0.0.1:5173**. A API atende em `http://127.0.0.1:8000` e expõe
documentação em `/docs`. O frontend escolhe o mesmo hostname da página para a API.
Não misture `localhost` e `127.0.0.1` ao configurar `VITE_API_BASE_URL`, pois a
sessão usa cookie. As variáveis de configuração são lidas do ambiente; arquivos
`.env` não são carregados automaticamente pelo backend.

### Usuários e logins do seeder

Senha comum das **três contas de demonstração**: `teste123`.

| Usuário | E-mail / login | Perfil | Tela inicial |
| --- | --- | --- | --- |
| Admin Demo | `admin@demo.local` | Admin global | `/admin` |
| Banco Unicamp | `banco@demo.local` | Banco | `/banco` |
| Ana Advogada | `advogada@demo.local` | Advogado externo | `/advogado` |

O banco e a advogada pertencem ao Banco Unicamp. O admin global não possui banco
e não acessa os processos operacionais.

**Essas credenciais são públicas e exclusivas para desenvolvimento local. Nunca
use o seed ou seu banco de dados em produção.** O comando exige `--confirm-demo`,
grava somente em `.runtime/demo/enteragree.db` e não segue um
`ENTERAGREE_DATABASE_PATH` diferente. Configure a API para usar o mesmo arquivo,
como no comando acima. O seed pode ser repetido: não apaga processos, não altera
senhas nem revoga sessões existentes; recusa contas que já tenham configuração
incompatível. Em uma base nova, cria somente banco e usuários, sem processos falsos.

Para atualizar as contas demo de uma instalação anterior para `teste123`:

```powershell
python -m scripts.seed_demo --confirm-demo --reset-passwords
```

Esse comando altera somente as senhas das três contas listadas e revoga suas
sessões anteriores. Faça login novamente. A senha curta é uma exceção isolada
no seed; usuários criados pela interface ou pelo CLI de administrador continuam
exigindo pelo menos 15 caracteres.

### Primeiro acesso sem contas de demonstração

Para uma base própria, em outro terminal na raiz do repositório:

```powershell
$env:ENTERAGREE_RUNTIME_DIR = Join-Path (Get-Location) '.runtime/local'
$env:ENTERAGREE_DATABASE_PATH = Join-Path $env:ENTERAGREE_RUNTIME_DIR 'enteragree.db'
$env:ENTERAGREE_AUTH_REQUIRED = 'true'
python -m scripts.create_admin --name "Administrador" --email admin@empresa.com
python -m uvicorn src.interface.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

A senha é solicitada no terminal e deve ter pelo menos 15 caracteres. Não há
cadastro público nem seed automático no startup. Pare a outra instância da API
antes de iniciar esta na mesma porta.

Depois do login, o admin cadastra banco e usuários; o banco abre e atribui
processos e envia documentos; o advogado acessa somente os processos atribuídos,
consulta os arquivos, executa a avaliação e registra a decisão. Banco e advogado
visualizam a recomendação. A sessão persiste na recarga; **Sair** revoga a sessão.

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

Se já houver Google Chrome instalado, pode usar
`$env:PLAYWRIGHT_CHROMIUM_CHANNEL = 'chrome'` antes de `npm run test:e2e`, sem
instalar o Chromium do Playwright. A suíte usa a porta 4173 para o preview.

Veja o [guia Git](docs/guia_conformidade_git.md), o
[plano de migração](docs/plano_refatoracao_estrutura_src.md) e o
[comparativo de diretórios](docs/comparativo_e_reestruturacao_diretorios.md).

## Fluxo implementado

1. O banco abre o processo, atribui um advogado e envia um PDF/TXT na seção **Documentos do processo**, escolhendo o tipo documental. Cada envio aceita um arquivo; o formulário preserva a seleção em caso de erro.
2. O upload é persistido por streaming, o texto é extraído em lotes de 100 páginas e o tipo declarado é conferido por sinais determinísticos, sem LLM.
3. A lista acompanha o processamento automaticamente e permite baixar o original. Tipos confirmados ativam as variáveis correspondentes do motor; incompatibilidades e texto insuficiente são sinalizados. As operações de reclassificação, continuação com ressalva e remoção existem na API, mas ainda não têm controles nesta interface.
4. A política registra recomendação, faixa de acordo, vetor de atributos, origem de cada atributo, limitações e decisão posterior do advogado.
5. O banco acompanha análises, decisões e aderência na tela **Monitoramento**, via `GET /api/monitoring`. A interface não apresenta estimativas fictícias de economia ou aceitação.

A interface usa o logo monocromático atual da [Enter](https://www.getenter.ai/),
armazenado localmente, e destaque `#ffae35`. O título da aba é
**ENTER | Política de acordos**; o favicon usa o novo símbolo da marca.

## Análise auxiliar de dossiê

Instale o extra opcional e configure a chave somente no servidor:

```powershell
python -m pip install -e ".[dossie]"
$env:OPENAI_API_KEY = "sua-chave"
$env:ENTERAGREE_DOSSIE_MODEL = "gpt-4o-mini"
python -m uvicorn src.interface.backend.main:app --reload
```

Após enviar um documento do tipo `DOSSIE` e concluir a extração, a análise pode
ser solicitada na API autenticada por `POST /api/documents/{document_id}/dossie-analysis`
e consultada por `GET` na mesma rota. Esse comando envia texto à OpenAI. Os
controles de análise auxiliar de dossiê ainda não foram reincorporados nas telas
por perfil. A resposta contém parecer do perito, exame da assinatura contratual,
índices, contrato referenciado e citações. Informação ausente permanece
desconhecida, não zero.
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

Esta entrega usa SQLite e tarefas em processo para demonstração. Autenticação,
sessões e escopo por perfil estão implementados, mas produção ainda requer
endurecimento: HTTPS, cookie `Secure`, proteção CSRF, limitação de tentativas,
armazenamento de objetos, fila de workers, banco transacional, criptografia,
antivírus, auditoria imutável e observabilidade. Páginas com pouco texto são
sinalizadas; a métrica de qualidade e a etapa de OCR estão explicitamente
pendentes. A extração de dossiê complementa a leitura documental via API, mas não
substitui a política nem a confirmação determinística de tipo. RAG, validação
cruzada entre documentos e telas de solicitações documentais continuam pendentes.

Consulte `docs/arquitetura.md` para contrato, estados e critérios de evolução.

## Documentação de acesso por perfil

O [plano original de banco, advogado, admin global e login](docs/plano_acesso_banco_advogado_admin.md)
registra a proposta. O [fluxo implementado](docs/fluxo_papeis_frontend.md) descreve
as telas e permissões atuais, e a [auditoria do frontend](docs/auditoria_frontend.md)
registra correções, testes e limitações.
