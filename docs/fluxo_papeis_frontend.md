# Fluxo de papéis e telas

## Objetivo

Esta entrega substitui a tela única e sem autenticação por um fluxo operacional
mínimo para o Banco Unicamp, advogados externos e administração global. A política
continua a ser calculada pelo mesmo motor; a mudança limita quem pode consultar,
executar e registrar cada etapa.

## Papéis

| Papel | Tela inicial | Permissões principais |
| --- | --- | --- |
| `BANCO` | `/banco` | Abre processos do próprio banco, atribui advogado, envia documentos, consulta análises, decisões e monitoramento. |
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
   um advogado no detalhe do caso. Na seção **Documentos do processo**, seleciona
   o tipo, escolhe um PDF ou TXT e clica em **Enviar documento**.
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
| `/banco/casos/:caseId` | Atribuição, envio de documentos e leitura da recomendação. |
| `/banco/monitoramento` | Aderência e efetividade do banco. |
| `/advogado` | Processos atribuídos ao advogado autenticado. |
| `/advogado/casos/:caseId` | Consulta e download dos documentos, execução da avaliação e registro de decisão. |
| `/admin` | Cadastro simples de bancos e usuários. |

## Verificação

- Testes de API: autenticação, isolamento entre advogados, administração,
  revogação de sessão e fluxos documentais.
- Testes de navegador: jornada de banco e de advogado com APIs simuladas.
- Build Vite: garante rotas React e bundles de produção.

As correções de formulários, logout, carregamento e identidade visual, incluindo
a validação com API real, estão registradas em `auditoria_frontend.md`.

## Envio de documentos pelo banco

- O formulário fica no detalhe do processo, exclusivamente no perfil banco.
  Envia um arquivo por vez pela API existente, sem conversão para Base64 e sem
  carregar o arquivo inteiro em memória JavaScript. O limite de tamanho é
  controlado pelo servidor (`ENTERAGREE_MAX_UPLOAD_BYTES`, padrão 512 MiB).
- O tipo declarado é obrigatório. A API determina a origem pelo usuário
  autenticado, independentemente do valor de `source_party` enviado pelo cliente.
- Durante o envio, os controles ficam desabilitados. Falhas preservam os campos;
  o formulário é limpo somente após a confirmação do servidor.
- A lista é atualizada após o envio e consultada a cada dois segundos enquanto
  houver documentos aguardando processamento ou em extração. O acompanhamento
  para ao concluir, sair da tela ou falhar a consulta; nesse último caso, a tela
  permite tentar novamente.
- Banco e advogado responsável podem baixar o original pelo endpoint autenticado.
  O link não transfere o arquivo para o estado React nem expõe o caminho em disco.
- A tela mostra falhas, divergências de tipo, tipo não confirmado e texto
  insuficiente. A validação de tipo continua determinística; não é chamada de LLM.
  OCR não está implementado. Documentos sem tipo confirmado não ativam evidências
  na política apenas por terem sido enviados.

## Limites conhecidos e próximos passos

- O cadastro inicial é propositalmente por CLI; não há endpoint público de
  bootstrap.
- Para produção, configurar HTTPS e endurecer o cookie como `Secure`; adicionar
  proteção CSRF para mutações autenticadas e limitação de tentativas no login.
- Envio pelo banco, acompanhamento e download estão disponíveis. Telas de
  solicitações documentais, reclassificação, remoção e confirmação com ressalva
  ainda precisam ser reincorporadas, preservando as APIs protegidas por papel.
- Auditoria de ações de usuário, redefinição de senha e gestão avançada de
  usuários permanecem próximos incrementos.
