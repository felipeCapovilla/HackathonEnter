# Plano de implementação: banco, advogado, admin global e login

Status: planejado; nenhuma funcionalidade deste documento está implementada por esta entrega.

Data: 12/09/2026. Base inspecionada: commit `2907436`, branch `(feat)_docs_pipeline`.

## 1. Objetivo e recorte

Entregar uma próxima versão utilizável por três tipos de usuário, com responsabilidades claras, contas reais e dados persistidos. Manter FastAPI, SQLite, React e Vite. A implementação deverá acontecer depois da publicação deste plano.

No enunciado, o banco é o cliente corporativo da plataforma e o advogado externo opera os processos. Neste documento, “cliente” significa banco; a pessoa que processa o banco não receberá uma área de acesso. Os três perfis definidos são usuários humanos, não agentes de IA.

Decisões para manter o MVP pequeno:

- Exatamente três papéis fixos: `BANCO`, `ADVOGADO_EXTERNO` e `ADMIN_GLOBAL`.
- Cada usuário operacional pertence a um único banco. Começar com Banco Unicamp; permitir cadastrar outro banco pela mesma tela simples de administração.
- Cada caso pertence a um banco e tem, no máximo, um advogado responsável. Um advogado pode receber vários casos do seu banco.
- O perfil `BANCO` reúne operação documental e acompanhamento jurídico. Não criar um quarto perfil de gestor.
- Uma aplicação frontend, com três áreas protegidas e componentes compartilhados.
- Login por e-mail e senha, com sessão persistida no servidor e cookie no navegador.
- Administração pequena: cadastrar bancos, criar usuários, ativar/desativar acessos e redefinir senha.
- Manter motor de política, treinamento, regras financeiras e processamento documental existentes. Não inserir alterações de modelo nesta feature.

SSO, MFA, convite por e-mail, recuperação automática de senha, organizações de escritórios, usuários vinculados a vários bancos, permissões configuráveis e impersonação ficam fora desta versão.

## 2. Situação atual e mudanças necessárias

| Evidência no código atual | Consequência | Mudança planejada |
| --- | --- | --- |
| `src/interface/frontend/src/main.jsx` reúne todas as operações em `App` | A mesma pessoa pode solicitar e responder como banco | Separar layouts e ações por perfil autenticado |
| O formulário de upload envia `source_party` escolhido pelo usuário | A origem declarada não comprova quem enviou | Derivar origem e autoria a partir da sessão |
| `src/interface/backend/main.py` expõe as rotas sem dependência de autenticação | Qualquer cliente HTTP pode executar as ações | Proteger cada rota e verificar o caso relacionado |
| `src/interface/backend/database.py` não tem usuários, sessões nem banco do caso | Não existe isolamento ou atribuição | Acrescentar tabelas e vínculos mínimos |
| `src/interface/backend/monitoring.py` agrega todas as análises e decisões | O painel não está limitado ao banco | Aplicar filtro de banco na consulta e em todos os agregados |
| Download e páginas recebem apenas o UUID do documento | Conhecer o identificador basta para acessar | Resolver documento → caso → permissão antes de retornar conteúdo |
| Upload já aceita `request_id`, mas a interface não o seleciona | Um anexo não encerra necessariamente o pedido correspondente | Adicionar ação “Enviar documento solicitado” com vínculo automático |
| `TypeConfirmation.reason` é recebido, mas não persistido | Falta autoria e justificativa da confirmação | Registrar evento com usuário, ação e motivo |
| O frontend acessa `event.currentTarget` após `await` e não cancela buscas antigas | Erro no reset do formulário e risco de exibir o caso anterior | Capturar formulário antes de aguardar; cancelar ou descartar respostas antigas |

A existência de `BANCO` e `ADVOGADO_EXTERNO` em `SourceParty` não equivale a um sistema de permissões. O novo papel do usuário será uma informação separada, mantida no servidor.

## 3. Papéis e regras de acesso

### 3.1 Regras fundamentais

1. Usuário sem sessão válida recebe `401` nas APIs protegidas.
2. Usuário autenticado só acessa os recursos do seu escopo. Identificador inexistente ou fora do escopo recebe `404`.
3. Ação proibida pelo papel recebe `403`; o erro não deve incluir dados de outro banco.
4. O backend aplica as regras a cada chamada. Menus e botões refletem essas permissões, mas não são a proteção.
5. `bank_id`, identidade do ator e origem do upload são derivados da sessão. O navegador não escolhe o banco em operações comuns.
6. Advogado precisa estar ativo, pertencer ao banco do caso e ser seu responsável atual. A reatribuição retira o acesso do advogado anterior imediatamente.
7. Admin global administra a plataforma. Não assume identidade de banco nem registra decisões jurídicas.

### 3.2 Matriz de permissões

| Operação | Banco | Advogado externo | Admin global |
| --- | --- | --- | --- |
| Entrar, sair e trocar a própria senha | Sim | Sim | Sim |
| Listar e abrir casos | Do próprio banco | Apenas atribuídos a ele | Sem acesso operacional nesta versão |
| Criar caso | Sim, no seu banco | Não | Não |
| Atribuir ou reatribuir responsável | Advogado ativo do seu banco | Não | Não |
| Ler documentos, páginas, recomendações e histórico | Casos do seu banco | Casos atribuídos | Não |
| Enviar autos ou subsídios | Casos do seu banco | Casos atribuídos | Não |
| Corrigir tipo ou remover documento | Somente uploads de origem `BANCO` do seu banco | Documentos do caso atribuído | Não |
| Continuar com ressalva após divergência de tipo | Não | Sim, com justificativa | Não |
| Executar análise da política | Não | Sim | Não |
| Solicitar documento ao banco | Não | Sim | Não |
| Enviar documento em resposta a um pedido | Sim | Não; pode fazer upload avulso | Não |
| Declarar documento indisponível | Sim | Não | Não |
| Cancelar pedido ainda aberto | Não | Sim, no caso atribuído | Não |
| Registrar acordo/defesa e valor proposto | Não | Sim | Não |
| Consultar monitoramento de aderência | Somente seu banco | Não | Apenas contagens administrativas globais |
| Cadastrar bancos e usuários | Não | Não | Sim |
| Ativar/desativar usuário e redefinir senha | Não | Não | Sim |

Para o MVP, todos os usuários `BANCO` da mesma instituição compartilham a fila de documentos recebidos e enviados. A autoria individual permanece no histórico.

“Remover documento” significa marcar `REMOVED`, excluindo-o das próximas análises; nunca apagar fisicamente o original nem reescrever análises anteriores. A permissão do advogado sobre documentos do caso é deliberada: ele pode corrigir a classificação ou desconsiderar um subsídio na avaliação jurídica, mesmo quando enviado pelo banco. Toda alteração exige motivo e evento de autoria, visíveis ao banco. Usuários banco podem corrigir/remover qualquer documento de origem `BANCO` da sua instituição, não apenas os enviados pela mesma pessoa.

Os campos que definem papel e banco do usuário são imutáveis após o cadastro nesta versão. Uma mudança estrutural exige novo cadastro e reatribuição dos casos; evita-se uma interface de permissões e transferência entre organizações. O admin poderá editar nome, ativação e senha.

## 4. Telas e navegação

Adotar `react-router-dom` com `BrowserRouter`, em versão compatível com o React utilizado no momento da implementação. Manter um único ponto de entrada e um layout por área. A API conserva o prefixo `/api`.

| URL do frontend | Conteúdo | Público permitido |
| --- | --- | --- |
| `/login` | E-mail, senha, entrar e mensagens de erro | Anônimo |
| `/` | Encaminhamento à área do usuário ou ao login | Todos |
| `/banco` | Lista de processos, criação e atalhos de gestão | Banco |
| `/banco/casos/:caseId` | Detalhe, responsável, documentos e histórico | Banco |
| `/banco/pedidos` | Pedidos abertos e respondidos | Banco |
| `/banco/monitoramento` | Agregados reais do seu banco | Banco |
| `/advogado` | “Meus processos”, com pendências | Advogado |
| `/advogado/casos/:caseId` | Documentos, pedidos, análise e decisão | Advogado responsável |
| `/admin` | Tela única com bancos e usuários | Admin global |
| `/conta` | Nome/perfil e formulário de troca de senha | Usuário autenticado |
| `/acesso-negado` | Explicação curta e volta à própria área | Usuário autenticado |
| Qualquer outra URL | Página não encontrada | Todos |

### 4.1 Banco

O banco começa por uma lista de casos reais, com número, advogado responsável e indicação “Sem responsável” quando aplicável. Pode cadastrar um caso e selecionar o responsável imediatamente ou depois. Casos sem responsável continuam visíveis ao banco, mas não aparecem para nenhum advogado.

No detalhe, o banco envia documentos, acompanha a validação de tipo e lê a recomendação e a decisão do advogado. Não há formulário de decisão jurídica nessa área. Quando um upload de origem `BANCO` da sua instituição estiver classificado como divergente, pode corrigir o tipo ou removê-lo logicamente; a continuação com ressalva cabe ao advogado.

Na fila de pedidos, cada item mostra processo, tipo solicitado, motivo, solicitante, estado e resposta. “Enviar documento solicitado” preenche `request_id` e o tipo solicitado. “Não temos o documento” exige motivo. A fila deve continuar permitindo upload avulso no detalhe do caso. Pedidos sem resposta ficam abertos nesta fase, sem prazo, alerta ou escalonamento automático.

O painel de monitoramento usa os campos atuais da API, filtrados pelo banco. Não inventar aceitação, economia ou desfecho judicial: esses dados ainda não são coletados pelo fluxo atual e ficam para outra feature.

### 4.2 Advogado

O advogado entra diretamente em “Meus processos”. Abre apenas os casos atribuídos, lê ou baixa os arquivos e pode consultar texto extraído por página. Vê a origem e o estado dos documentos sem poder se declarar banco.

No detalhe, pode solicitar subsídios, acompanhar respostas, cancelar pedidos abertos, executar análise e registrar a decisão. A recomendação deve exibir justificativas, faixa financeira e limitações documentais já retornadas. Se escolher ação diferente da recomendação, a justificativa será obrigatória no frontend e na API.

Se houver divergência documental, pode reclassificar, remover ou continuar com ressalva com motivo registrado. Documentos não confirmados continuam informativos e não bloqueiam a navegação; manter a semântica atual das features. O TODO de qualidade de OCR continua separado.

O envio de novos documentos não altera silenciosamente análises antigas. A interface avisa que houve atualização e oferece nova análise; cada decisão fica vinculada ao `analysis_id` usado pelo advogado.

### 4.3 Admin global

Uma tela com duas seções simples:

- **Bancos:** lista e formulário de criação com nome. Banco Unicamp é o registro inicial. Sem exclusão ou suspensão de banco nesta versão.
- **Usuários:** lista com nome, e-mail, papel, banco e situação; formulário de cadastro; ações de ativar/desativar, editar nome e redefinir senha.

Ao cadastrar `BANCO` ou `ADVOGADO_EXTERNO`, o admin escolhe um banco existente. Para `ADMIN_GLOBAL`, `bank_id` é nulo. A interface pode mostrar contagens de bancos, usuários e casos por banco, sem expor documentos ou permitir operações jurídicas.

Não permitir desativar o último admin ativo. Desativar um advogado preserva seu histórico e vínculos; o banco vê a pendência e pode reatribuir os casos. Um usuário desativado perde acesso mesmo com cookie ainda presente.

## 5. Login e sessão

### 5.1 Comportamento esperado

1. A aplicação inicia no estado “Verificando sessão” e chama `GET /api/auth/me`.
2. Se receber `401`, mostra `/login`. Não carregar casos ou monitoramento antes de identificar o usuário.
3. O formulário envia `{email, password}` para `POST /api/auth/login`, sem seletor de papel.
4. O backend normaliza o e-mail, valida a senha, verifica ativação e cria uma sessão nova.
5. A resposta define cookie e devolve os dados públicos do usuário e o token CSRF. Papel e banco vêm do cadastro.
6. O frontend encaminha o usuário a `/banco`, `/advogado` ou `/admin` conforme o papel.
7. Recarregar a página mantém o login enquanto a sessão for válida. Acessar diretamente uma URL protegida também passa por essa verificação.
8. `POST /api/auth/logout` revoga a sessão no servidor, remove o cookie e limpa dados e requisições em andamento no frontend.

Uma resposta `401` durante o uso encerra o estado autenticado e volta ao login. `403` mostra acesso negado; `404` mostra recurso não encontrado. Falha de rede ou `5xx` mostra erro e tentativa novamente, sem simular sucesso ou considerar a pessoa automaticamente deslogada.

### 5.2 Escolha técnica

Usar sessão opaca armazenada em SQLite: token aleatório de pelo menos 32 bytes, com apenas seu hash SHA-256 persistido. Não há necessidade de JWT ou refresh token para esta versão. A sessão tem duração absoluta de oito horas, é revogável e deve consultar usuário ativo e permissões atuais a cada chamada. O cookie será `enteragree_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`, sem `Domain` e `Secure` em HTTPS. O token de sessão não será exposto ao JavaScript. Essas propriedades seguem as orientações de [gerenciamento de sessões da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Armazenar senhas com Argon2 por `pwdlib[argon2]`, usando a biblioteca para gerar e verificar hashes. O guia de [hash de senhas do FastAPI](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#password-hashing) documenta essa integração; seu exemplo de JWT não faz parte desta escolha. Para o MVP, aceitar senhas de 15 a 128 caracteres, sem regras artificiais de composição; nunca truncar, registrar ou devolver senha/hash.

Manter o frontend e a API na mesma origem: cliente usa `/api`; Vite encaminha esse prefixo para FastAPI em desenvolvimento; a publicação serve frontend e API no mesmo domínio. `Secure=false` fica restrito ao desenvolvimento local HTTP. Evitar combinações de `localhost` e `127.0.0.1` no mesmo fluxo de teste. Usar `credentials: "include"` no cliente. Se houver execução entre origens, permitir apenas a origem configurada com `allow_credentials=True`, sem curinga.

Para alterações autenticadas (`POST`, `PATCH`, `PUT` e `DELETE`), usar token CSRF aleatório vinculado à sessão, entregue em login e `/auth/me`, mantido em memória e enviado em `X-CSRF-Token`. Isso inclui logout, senha e upload. Validar também `Origin` contra a origem configurada; o login, que ainda não possui token de sessão, exige a origem esperada. Clientes de teste também devem enviar esse cabeçalho; origem ausente ou diferente é rejeitada nas operações mutáveis. Cookies `SameSite` complementam esse controle. Referência: [prevenção de CSRF da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Respostas de autenticação usam `Cache-Control: no-store`. Senha inválida, e-mail inexistente e conta inativa produzem a mesma mensagem “E-mail ou senha inválidos”. Prever limite simples por IP e e-mail normalizado: cinco falhas em quinze minutos geram `429` com `Retry-After`. Para o MVP de um único processo, manter os contadores em memória; limitação deve constar na documentação operacional, sem introduzir Redis.

### 5.3 Provisionamento e manutenção

- O primeiro admin é criado por comando local idempotente, a implementar em `scripts/create_admin.py`, com senha solicitada por entrada oculta. Não expor endpoint público de bootstrap.
- Criar Banco Unicamp na migração inicial; criar usuários operacionais pela tela de admin.
- O admin informa uma senha inicial no cadastro e pode redefini-la por formulário. A entrega da senha ocorre fora da plataforma, sem serviço de e-mail nesta versão.
- Usuário troca sua própria senha em `/conta`, informando senha atual e nova. Após troca ou redefinição, revogar todas as sessões desse usuário e exigir novo login.
- Desativação também revoga todas as sessões. Reativação exige login novo.
- Não inserir senhas padrão, contas simuladas, tokens ou dados jurídicos de exemplo no commit.

## 6. Modelo mínimo de dados e migração

| Entidade | Campos a acrescentar ou criar |
| --- | --- |
| `banks` | `id`, `name`, `created_at` |
| `users` | `id`, `name`, `email` único normalizado, `password_hash`, `role`, `bank_id` opcional, `is_active`, `created_at` |
| `sessions` | `token_hash` único, `user_id`, `csrf_token`, `created_at`, `expires_at`, `revoked_at` opcional |
| `cases` | `bank_id`, `assigned_lawyer_id` opcional, `created_by_user_id` opcional para legado |
| `documents` | `uploaded_by_user_id` opcional para legado; manter `source_party` e `request_id` |
| `analyses` | `created_by_user_id` opcional para legado |
| `document_requests` | `requested_by_user_id`, `responded_by_user_id` opcionais para legado; manter resposta e datas existentes |
| `lawyer_decisions` | `decided_by_user_id` opcional para legado |
| `audit_events` | `id`, `actor_user_id`, `action`, `entity_type`, `entity_id`, `case_id` opcional, `reason` opcional, `created_at` |
| `schema_migrations` | `version` única, `applied_at` |

Não criar uma tabela de atribuições: `cases.assigned_lawyer_id` representa o único responsável, e o histórico das mudanças fica em `audit_events`. Não duplicar `bank_id` em todos os filhos: documentos, análises e pedidos derivam seu escopo do caso.

Restrições: papéis limitados aos três valores; `bank_id` obrigatório para usuário operacional e nulo para admin; advogado atribuído deve ser ativo, ter papel correto e pertencer ao banco do caso. Ativar chaves estrangeiras em cada conexão SQLite, não apenas durante a criação do schema. Toda criação nova registra ator; dados anteriores à feature mantêm autoria nula, exibida como “Registro anterior ao login”.

Migração sequencial e versionada, executada antes de abrir a API:

1. Criar cópia de segurança local do SQLite por comando operacional antes da atualização. Implementar funções ordenadas de migração, cada uma transacional; não criar backups a cada inicialização.
2. Criar `banks`, `users`, `sessions` e `audit_events`; obter ou criar o banco inicial de forma idempotente.
3. Associar os casos legados ao banco inicial explicitamente. Esta regra vale para a base atual do hackathon, que tem uma única instituição; abortar se houver indicação de dados misturados sem mapeamento.
4. Deixar casos sem advogado até atribuição pelo banco. Não selecionar automaticamente o primeiro usuário cadastrado.
5. Preservar IDs, arquivos, análises, decisões, pedidos e numeração de casos. Manter a unicidade atual do número de processo nesta versão.
6. Validar preenchimento de `cases.bank_id`, FKs, índices e contagens. Se for necessário reconstruir tabela SQLite para aplicar `NOT NULL`, preservar os vínculos e verificar `foreign_key_check` antes de concluir.
7. Registrar a versão da migração, para que novo startup não faça backfill novamente. Não criar usuários públicos automaticamente.

Eventos de atribuição, confirmações documentais, criação de usuário, ativação e redefinição de senha precisam registrar quem agiu. Registrar a alteração e seu evento na mesma transação; nunca guardar a senha no evento. A tabela de eventos oferece rastreabilidade local, não garantia de armazenamento imutável.

A validação de advogado ativo, papel e banco deve ocorrer na mesma transação da atribuição; uma chave estrangeira isolada não garante essas condições.

## 7. Contratos da API

### 7.1 Rotas novas

| Método e rota | Entrada/saída principal | Permissão |
| --- | --- | --- |
| `POST /api/auth/login` | Entrada `{email, password}`; saída `{user, csrf_token}` e cookie | Pública, limitada por tentativas |
| `GET /api/auth/me` | `{user, csrf_token}` | Sessão válida |
| `POST /api/auth/logout` | Sem corpo; `204` | Sessão válida |
| `POST /api/auth/change-password` | `{current_password, new_password}`; `204`, revoga sessões | Sessão válida |
| `GET /api/lawyers` | Lista `{id, name}` de advogados ativos do banco | Banco |
| `PATCH /api/cases/{case_id}/assignment` | `{lawyer_user_id: id ou null}`; caso atualizado | Banco proprietário |
| `GET /api/document-requests` | Fila com processo, solicitante, resposta e estado | Banco; filtro obrigatório por sessão |
| `GET /api/admin/summary` | Contagens de bancos, usuários e casos por banco | Admin global |
| `GET /api/admin/banks` | Lista de bancos | Admin global |
| `POST /api/admin/banks` | `{name}`; banco criado, `201` | Admin global |
| `GET /api/admin/users` | Lista pública de usuários, sem hashes/sessões | Admin global |
| `POST /api/admin/users` | `{name, email, password, role, bank_id}`; usuário criado, `201` | Admin global |
| `PATCH /api/admin/users/{user_id}` | `{name?, is_active?}`; usuário atualizado | Admin global |
| `POST /api/admin/users/{user_id}/reset-password` | `{new_password}`; `204`, revoga sessões | Admin global |

Representação pública `user`: `{id, name, email, role, bank_id, bank_name, is_active}`. Para admin, banco e nome do banco são nulos. O backend rejeita campos adicionais em operações de administração, atribuição e autenticação.

O logout é idempotente: sem sessão válida, pode retornar `204` removendo o cookie, sem acessar dados. Requisições autenticadas de logout seguem a proteção CSRF; a validação de origem vale nos dois casos. Redefinição de senha não devolve nem armazena texto de senha nos registros de auditoria.

`/api/admin/summary` devolve apenas contagens administrativas, sem identificador de caso, partes, documentos, decisões ou valores financeiros. `ADMIN_GLOBAL` recebe `403` em `/api/cases` e `/api/monitoring`; não deve usar essas rotas para montar o resumo.

### 7.2 Rotas existentes que serão preservadas

| Rota atual | Ajuste previsto |
| --- | --- |
| `POST /api/cases` | Apenas banco; definir `bank_id` e autor pela sessão |
| `GET /api/cases` | Banco filtra sua instituição; advogado filtra atribuição |
| `GET /api/cases/{case_id}` | Manter `{case, documents, document_requests, analyses, lawyer_decisions}` e verificar escopo |
| `POST /api/cases/{case_id}/documents` | Manter multipart e upload manual; inferir `source_party`, registrar autor e validar vínculo com pedido |
| `GET /api/documents/{document_id}/file` | Verificar acesso ao caso antes de abrir o arquivo |
| `GET /api/documents/{document_id}/pages/{page_number}` | Mesma autorização do original |
| `POST /api/documents/{document_id}/type-confirmation` | Aplicar matriz de ações e persistir motivo/ator |
| `POST /api/cases/{case_id}/analyses` | Apenas advogado responsável; registrar ator |
| `POST /api/cases/{case_id}/document-requests` | Apenas advogado responsável; registrar solicitante |
| `POST /api/document-requests/{request_id}/response` | `DECLARED_UNAVAILABLE` só banco; `CANCELLED` só advogado responsável |
| `POST /api/cases/{case_id}/lawyer-decisions?analysis_id=...` | Advogado responsável; análise do mesmo caso; autor e justificativa de divergência |
| `GET /api/monitoring` | Apenas banco, com todos os agregados filtrados pela instituição |
| `GET /health` | Continua público sem dados de usuários ou processos |

No upload, o frontend deixa de enviar `source_party`. Para facilitar transição, o backend pode recebê-lo opcionalmente, mas somente aceita valor igual ao derivado da sessão; divergência retorna `422`. O campo permanece na resposta. Se `request_id` estiver preenchido, exigir papel `BANCO`: advogado não pode encerrar o próprio pedido por upload. Não aceitar `bank_id` ou autoria fornecidos pelo cliente em operações comuns.

Adicionar à resposta do caso seu banco e responsável. Expor `request_id` nos documentos e autoria pública nos históricos para que a UI mostre qual upload atende qual pedido. `response_reason` já existe no SQLite, mas precisa entrar no contrato de resposta do pedido. Não expor caminhos locais de arquivos.

Listas grandes: acrescentar `limit` e `offset`, com padrão de 50 e limite máximo de 100, preservando a resposta como array nas rotas atuais; frontend usa “Carregar mais”. Usar ordenação estável por data e ID; avançar o offset pela quantidade recebida e encerrar ao receber menos que o limite. Não apresentar total de registros calculado a partir de uma página. A fila de pedidos aceita `status` e `case_id` como filtros, sempre dentro do banco autenticado. Monitoramento considera todo o banco, não apenas a página visível.

Não há `GET /api/analyses/{analysis_id}` na implementação inspecionada. Nesta feature, continuar lendo a análise pelo detalhe do caso. Se a rota for criada futuramente, deve aplicar a mesma verificação de escopo.

### 7.3 Ciclo dos pedidos de documentos

| Situação | Estado persistido | Quem age |
| --- | --- | --- |
| Advogado pede documento | `REQUESTED` | Advogado responsável |
| Banco envia arquivo vinculado ao pedido | `SUBMITTED` | Banco |
| Banco informa não ter o documento | `DECLARED_UNAVAILABLE` | Banco, com motivo |
| Advogado retira o pedido | `CANCELLED` | Advogado responsável, com motivo |
| Ninguém responde | Manter `REQUESTED`, sem prazo ou alerta automático nesta fase | Nenhum |

Não calcular nem persistir `PENDING`, `OVERDUE` ou `is_overdue` nesta fase. A interface mostra o pedido como aberto enquanto estiver `REQUESTED`; silêncio não significa documento indisponível.

Upload de resposta deve ter pedido aberto do mesmo caso e tipo declarado correspondente. Inserção do registro do documento, atualização condicional para `SUBMITTED` e autoria devem ocorrer na mesma transação SQLite. Persistir o arquivo antes da transação e, em caso de falha, limpar somente o arquivo criado pela tentativa. Esse estado significa que o banco enviou um arquivo; não significa que tipo, OCR ou conteúdo foram validados. Mostrar também o estado de processamento do documento vinculado.

Upload malsucedido mantém o pedido aberto. Se a extração falhar depois do recebimento, o advogado pode abrir novo pedido; não haverá reabertura automática nesta versão. Cancelar ou responder um pedido terminal retorna `409`. Registrar transição condicional no banco para impedir duas respostas simultâneas sobrescrevendo o histórico.

Não criar novos registros persistidos `PENDING` ou `OVERDUE`. A rota de resposta recebe `{status: "DECLARED_UNAVAILABLE" ou "CANCELLED", reason}` e autoriza a transição individualmente, conforme a matriz; não conceder uma permissão genérica de “responder” aos dois papéis.

## 8. Organização de implementação

### 8.1 Backend

Acrescentar `auth.py` para hash e sessão, `permissions.py` para as verificações compartilhadas e routers pequenos de autenticação/admin. Manter as rotas de negócio e o motor de política atuais. A autorização de documento, página, pedido e análise deve resolver o caso proprietário por uma função comum.

`repository.py` recebe operações de usuários, sessões e atribuições, ou as delega a um módulo de persistência de acesso se ficar extenso. As consultas devem filtrar antes de carregar dados; não buscar todos os bancos para depois escondê-los em Python ou na interface.

`database.py` recebe migração e índices de banco, advogado, usuário e expiração de sessão. A consulta de monitoramento recebe escopo explícito de banco em todos os cálculos. Não chamar `src/monitor` legado para contornar essa filtragem.

O serviço de upload usa temporário com identificador único e armazenamento separado por caso. Corrigir o fluxo atual que pode apagar o arquivo original ao receber upload duplicado: a limpeza só pode remover o arquivo criado por aquela tentativa. Essa correção acompanha a atribuição e autoria para não haver interferência entre bancos enviando arquivos iguais.

### 8.2 Frontend

Divisão sugerida, sem introduzir uma biblioteca global de estado:

```text
src/
  main.jsx
  app/App.jsx
  app/router.jsx
  api/client.js
  auth/AuthProvider.jsx
  auth/ProtectedRoute.jsx
  layouts/BankLayout.jsx
  layouts/LawyerLayout.jsx
  layouts/AdminLayout.jsx
  pages/LoginPage.jsx
  pages/AccountPage.jsx
  pages/BankCasesPage.jsx
  pages/BankCasePage.jsx
  pages/BankRequestsPage.jsx
  pages/BankMonitoringPage.jsx
  pages/LawyerCasesPage.jsx
  pages/LawyerCasePage.jsx
  pages/AdminPage.jsx
  components/DocumentList.jsx
  components/DocumentUploadForm.jsx
  components/DocumentRequestList.jsx
  components/AnalysisPanel.jsx
  components/LawyerDecisionForm.jsx
```

`AuthProvider` controla apenas identificação e estado de autenticação. `api/client.js` concentra base URL, cookie, CSRF e tratamento de erros. Componentes de domínio recebem dados e ações explicitamente; cada página busca apenas o que seu perfil pode acessar.

Adicionar as duas dependências necessárias (`react-router-dom` no frontend e `pwdlib[argon2]` no backend), configurar explicitamente o proxy `/api` em `src/interface/frontend/vite.config.js` e manter a base de requisições relativa. Na publicação, o servidor HTTP que entrega `src/interface/frontend/dist` deve encaminhar `/api/*` para FastAPI e retornar `index.html` nas rotas de páginas; documentar essa configuração junto ao setup. O Vite de desenvolvimento já atende à navegação de páginas, mas não substitui essa configuração de publicação.

Cuidados para preservar o fluxo:

- Links de casos usam URL real; atualizar ou abrir uma aba direta deve funcionar. Configurar fallback da SPA apenas para URLs do frontend, nunca transformar `404` de API em HTML.
- Resposta atrasada de um caso não pode sobrescrever outro. Usar `AbortController` ou identificação da requisição; limpar dados na troca de caso e logout.
- Capturar o elemento do formulário antes de um `await`; após sucesso, resetar o elemento capturado se ainda estiver montado. Manter formulário e dados em caso de falha.
- Ler o corpo de erro uma única vez e traduzir erros Pydantic para mensagem legível; não tentar `response.text()` depois de consumir `response.json()`.
- Polling atualiza os documentos enquanto estiverem em processamento sem desmontar toda a página nem apagar formulário preenchido. Parar ao sair do caso ou perder sessão.
- Mostrar estados carregando, vazio, falha e sucesso. Não usar mocks, contas locais fictícias ou `localStorage` para autorizações.
- Downloads usam as rotas autenticadas de arquivo; o PDF não deve ficar disponível por um diretório estático público.
- O menu vem do perfil retornado em `/auth/me`. Navegar manualmente a outra área mostra acesso negado; escolher outro perfil exige sair e autenticar outra conta.

## 9. Sequência de execução futura

| Etapa | Entrega verificável |
| --- | --- |
| 1. Dados | Migração idempotente; casos legados preservados; banco e atribuição definidos |
| 2. Acesso | Bootstrap de admin, login, sessão, logout, troca/redefinição de senha e ativação |
| 3. Permissões | Todas as rotas atuais protegidas, isolamento de documentos e monitoramento testado |
| 4. Contratos | Rotas administrativas, atribuição, fila do banco e autoria funcionando |
| 5. Interface | Login, três áreas, conta, navegação direta e formulários reais |
| 6. Validação | Fluxo completo com dois bancos e advogados distintos; documentação de execução atualizada |

Não publicar uma versão intermediária em que a API exija sessão, mas o frontend ainda não consiga fazer login. A divisão em commits pode seguir as etapas; a disponibilização funcional exige o conjunto validado.

## 10. Critérios de aceite e testes

O aceite exige a matriz de permissões funcionando por HTTP, além da separação visual. Testes automatizados devem criar usuários e casos em banco temporário, com sessões reais; não substituir as dependências de autorização por um usuário administrador.

### 10.1 Casos essenciais de backend

- Anônimo não acessa listagens, documentos, páginas, análises, decisões nem monitoramento.
- Login válido, inválido, sessão expirada, logout, usuário desativado, troca de senha e redefinição revogam ou mantêm acesso conforme o contrato.
- Cookie com propriedades esperadas, CSRF ausente/inválido rejeitado e tentativas excessivas limitadas.
- Banco A não lista ou acessa conteúdo do Banco B nem por UUID direto. Contagens de monitoramento também não vazam dados de B.
- Advogado não atribuído não lê o caso; reatribuição retira acesso do responsável anterior, inclusive a arquivos e pedidos.
- Banco não registra decisão ou se apresenta como advogado; advogado não responde em nome do banco; admin não opera processos.
- Autoria, banco e origem forjados são rejeitados ou derivados da sessão conforme os contratos.
- Último admin ativo não pode ser desativado. Usuários operacionais não podem chamar endpoints de admin.
- Pedido pode receber documento vinculado, indisponibilidade ou cancelamento; estados terminais e concorrência não sobrescrevem respostas.
- Enviar arquivo duplicado não apaga o original; o mesmo arquivo em dois casos não provoca exclusão cruzada.
- Migração executada duas vezes preserva IDs, contagens, arquivos e autoria desconhecida do legado.
- Testes atuais de upload, tipagem, política e monitoramento continuam passando com usuários autorizados.

### 10.2 Roteiro funcional de demonstração

1. Criar primeiro admin por comando local e entrar em `/admin`.
2. Cadastrar um usuário banco e dois advogados do Banco Unicamp, com senhas reais definidas para a demonstração.
3. Entrar como banco, criar um caso, atribuir ao primeiro advogado e enviar um contrato.
4. Entrar como primeiro advogado, abrir o arquivo, solicitar extrato e sair.
5. Entrar como banco, responder o pedido com upload vinculado; criar outro pedido no fluxo de advogado para demonstrar “Não temos o documento”.
6. Manter um pedido sem resposta e verificar que permanece aberto, sem ser tratado como indisponível.
7. Entrar como responsável, executar análise, registrar decisão e consultar a recomendação com suas limitações.
8. Entrar como banco e verificar que a decisão aparece no monitoramento real.
9. Entrar como segundo advogado e confirmar que o primeiro caso não aparece. Atribuí-lo pelo banco e verificar a troca de acesso.
10. Criar segundo banco pela administração e verificar isolamento. Testar acesso direto a URLs, recarregamento, sair e voltar do navegador.

Na implementação, executar suíte Python e build do frontend, além de teste de navegação em navegador real ou Playwright para login, três áreas e URLs diretas. Build isolado não comprova funcionamento dos formulários ou das rotas.

## 11. Resultado desta entrega de planejamento

Publicar este documento na branch remota `(feat)_docs_pipeline`, com referência no README. O login, as áreas por papel e o admin global permanecem como trabalho futuro descrito aqui; não anunciar sua disponibilidade no produto até os critérios de aceite serem cumpridos.
