# Auditoria do frontend e identidade visual

## Correções verificadas

| Fluxo | Falha encontrada | Correção |
| --- | --- | --- |
| Abrir processo | O caso era salvo, mas `event.currentTarget.reset()` falhava após o `await` e impedia a navegação. | Navegação direta para o caso salvo; valores preservados quando o salvamento falha. |
| Cadastros e decisão | O mesmo acesso tardio ao evento impedia limpar o formulário e atualizar a lista. | Referência ao formulário capturada antes de aguardar a API. |
| Sair | A resposta FastAPI retornada não tinha status definido; o Uvicorn falhava ao enviá-la. | HTTP 204 explícito, revogação de sessão e exclusão do cookie; interface trata falhas e permite nova tentativa. |
| Envios repetidos | Botões permitiam mais de uma submissão durante o salvamento. | Controles desabilitados e trava de execução enquanto a operação está pendente. |
| Sessão expirada | Área autenticada permanecia visível depois de respostas 401. | Retorno ao login com aviso de expiração. |
| Falhas de carregamento | Monitoramento ficava carregando indefinidamente; erros de ações ocultavam o detalhe do caso. | Estados de erro e repetição de consultas; detalhe preservado quando uma ação falha. |
| Cadastros de usuários | Banco padrão não era selecionado após a carga assíncrona; admin global enviava banco. | Seleção controlada; `bank_id: null` para administradores globais. |
| Valores monetários | Campos aceitavam somente passos inteiros na validação HTML. | Campos monetários aceitam centavos. |
| Validações da API | Erros estruturados podiam aparecer como `[object Object]`; duplicidades geravam HTTP 500. | Mensagens legíveis; duplicidades retornam HTTP 409 e atribuição inválida retorna HTTP 422. |
| Navegação e análise | Rota desconhecida ficava vazia; resposta tardia podia atualizar tela abandonada; nova análise mantinha seleção anterior. | Rota de retorno por perfil, cancelamento de consultas e formulário associado à análise atual. |

## Identidade visual

- Logo fornecido em `src/assets/logo.png`, preservado; versões recortadas e otimizadas em WebP para wordmark e símbolo.
- Paleta baseada na referência: azul escuro `#0B0F1A`, azul `#4F7BFF`, lilás `#B7C6FF` e cinza `#F4F5F7`.
- Fonte Inter servida localmente, navegação lateral por perfil, login em duas colunas e adaptação para celular.
- Listas, contagens, recomendações e valores continuam usando a API. A interface não contém dados demonstrativos fixos.

## Validação desta revisão

- 91 testes Python aprovados, incluindo status HTTP do logout, revogação do token, duplicidades e atribuição inválida.
- Build de produção e 17 testes Playwright aprovados. Esses testes usam respostas controladas para simular também falhas, sessão expirada e requisições pendentes.
- Jornada adicional com Playwright na aplicação local e API real: admin cadastra banco e usuários; banco cria processo com centavos e atribui advogado; advogado avalia e registra decisão; banco vê resultado e monitoramento. Login, recarga e logout foram exercitados, sem erros no console.
- Capturas de desktop e celular inspecionadas. Os registros temporários da jornada real foram removidos após a verificação.

Para repetir a suíte automatizada:

```powershell
python -m pytest -q
cd src/interface/frontend
$env:PLAYWRIGHT_CHROMIUM_CHANNEL = 'chrome'
npm run test:e2e
```

O escopo permanece nas telas de login, casos, decisão, monitoramento e administração. Os limites de implantação e as funcionalidades documentais ainda pendentes estão descritos em `fluxo_papeis_frontend.md`.
