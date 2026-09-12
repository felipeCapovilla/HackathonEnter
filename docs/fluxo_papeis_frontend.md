# Fluxo de papéis e telas

## Objetivo

Esta entrega substitui a tela única e sem autenticação por um fluxo operacional
mínimo para o Banco Unicamp, advogados externos e administração global. A política
continua a ser calculada pelo mesmo motor; a mudança limita quem pode consultar,
executar e registrar cada etapa.

## Papéis

| Papel | Tela inicial | Permissões principais |
| --- | --- | --- |
| `BANCO` | `/banco` | Abre processos do próprio banco, atribui advogado, consulta documentos, análises, decisões e monitoramento. |
| `ADVOGADO_EXTERNO` | `/advogado` | Vê somente processos a ele atribuídos, executa a análise e registra defesa ou acordo. |
| `ADMIN_GLOBAL` | `/admin` | Cadastra bancos e usuários. Não acessa processos operacionais. |

O backend aplica o escopo do banco em todas as rotas de processo. Um advogado
recebe `404` para processo de outro responsável, evitando a enumeração de casos.

## Jornada operacional

1. Um administrador é provisionado fora da interface, sem senha padrão:
   `python -m scripts.create_admin --name "Administrador" --email admin@empresa.com`.
2. O administrador entra em `/login`, cadastra o banco e os usuários, incluindo
   advogados externos.
3. Um usuário do banco entra em `/login`, abre o processo em `/banco` e atribui
   um advogado no detalhe do caso.
4. O advogado vê o caso atribuído em `/advogado`, abre-o e executa **Avaliar risco
   e recomendação**.
5. Banco e advogado visualizam a mesma saída auditável: recomendação de acordo ou
   defesa, razões e valor sugerido quando aplicável. Somente o advogado registra a
   decisão operacional.

## Autenticação

- Senhas são derivadas com `scrypt`, usando sal aleatório por senha.
- O login cria uma sessão opaca, persistida no SQLite apenas como hash SHA-256 do
  token e expirada em oito horas.
- A sessão é enviada em cookie `HttpOnly`, `SameSite=Lax`; o frontend usa
  `credentials: "include"`.
- Desativar um usuário revoga suas sessões abertas.
- `ENTERAGREE_AUTH_REQUIRED` é verdadeiro por padrão. Os testes que exercitam
  componentes antigos desativam a autenticação explicitamente na configuração de
  teste; isto não deve ser usado em ambientes implantados.

## Rotas de interface

| Rota | Uso |
| --- | --- |
| `/login` | Identificação por e-mail e senha. |
| `/banco` | Abertura e lista de processos do banco. |
| `/banco/casos/:caseId` | Atribuição e leitura da recomendação. |
| `/banco/monitoramento` | Aderência e efetividade do banco. |
| `/advogado` | Processos atribuídos ao advogado autenticado. |
| `/advogado/casos/:caseId` | Execução da avaliação e registro de decisão. |
| `/admin` | Cadastro simples de bancos e usuários. |

## Verificação

- Testes de API: autenticação, isolamento entre advogados, administração,
  revogação de sessão e fluxos documentais.
- Testes de navegador: jornada de banco e de advogado com APIs simuladas.
- Build Vite: garante rotas React e bundles de produção.

## Limites conhecidos e próximos passos

- O cadastro inicial é propositalmente por CLI; não há endpoint público de
  bootstrap.
- Para produção, configurar HTTPS e endurecer o cookie como `Secure`; adicionar
  proteção CSRF para mutações autenticadas e limitação de tentativas no login.
- A tela atual prioriza abertura, atribuição e decisão. A experiência completa de
  envio de documentos e solicitações documentais deve ser reincorporada em uma
  iteração específica, preservando as APIs já protegidas por papel.
- Auditoria de ações de usuário, redefinição de senha e gestão avançada de
  usuários permanecem próximos incrementos.
