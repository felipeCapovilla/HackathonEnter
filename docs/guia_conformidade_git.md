# Guia de branches, commits e publicação — EnterAgree

Este guia registra a convenção adotada para publicar a reorganização em `feat/docs-pipeline` e abrir um PR para `main`. Não estabelece uma exigência histórica que o repositório não possui.

## 1. Evidência e convenção escolhida

Na revisão, `origin/main` aponta para `07de512b`. Sua raiz contém `contracts/`, `src/`, `tests/`, `web/`, `pyproject.toml` e `Makefile`. Não existe `README.md` nessa referência; `git show origin/main:README.md` não fornece uma regra de contribuição. O histórico contém mensagens como `Estrutura inicial: contrato de tipos, motor de política e teste de fumaça`, sem Conventional Commits. Não foi identificada uma exigência de Git Flow ou Conventional Commits em main.

`(feat)_docs_pipeline` é um nome aceito pelo Git. Caracteres especiais exigem cuidado com aspas em comandos, mas não tornam o nome inválido. Para esta entrega, a convenção escolhida é `tipo/descricao-kebab-case`, usando `feat/docs-pipeline`.

| Tipo | Uso | Exemplo |
| --- | --- | --- |
| `feat/` | Funcionalidade | `feat/docs-pipeline` |
| `fix/` | Correção | `fix/upload-concorrente` |
| `refactor/` | Reorganização | `refactor/estrutura-src` |
| `docs/` | Documentação | `docs/plano-acesso` |
| `test/` | Testes | `test/contratos-api` |

Para novos commits da entrega, utilizar `tipo(escopo opcional): descrição`, por exemplo `refactor: reorganize application under src`. A descrição deve explicar a mudança; caixa baixa ou idioma específico não são condições de validade. Não reescrever commits já publicados para adequar seu formato.

## 2. Preparar e preservar o trabalho

Executar na raiz de `HackatonEnter`, conferindo o resultado de cada etapa:

```powershell
git status --short
git branch --show-current
git worktree list
git fetch origin
git log -5 --oneline origin/main
git diff --stat
```

Se a branch atual ainda for `(feat)_docs_pipeline` e `feat/docs-pipeline` não existir, criar a nova branch a partir do trabalho atual:

```powershell
git switch -c feat/docs-pipeline
```

Se já estiver na branch de destino, não repetir a criação. Se ela estiver em outro worktree, continuar naquele diretório. Alterações não commitadas devem ser preservadas e revisadas; não descartar arquivos para limpar a árvore.

## 3. Integrar main sem reescrever o histórico

Registrar as correções e a migração em commits revisados antes de integrar main. Selecionar somente os caminhos inspecionados com `git add -- <caminhos>`, incluindo a remoção dos caminhos antigos após a migração, e conferir o índice:

```powershell
git diff --cached --stat
git diff --cached --check
git commit -m "refactor: reorganize application under src"
git merge origin/main
```

O commit pressupõe que os arquivos pretendidos já estão no índice. Não adicionar dados privados, `.runtime/`, `.env`, ambientes virtuais, `node_modules/` ou `dist/`.

O merge preserva o histórico publicado. Resolver conflitos comparando responsabilidades e contratos: main também contém um motor, tipos em `contracts/`, testes e configurações. Não selecionar uma versão inteira sem verificar o comportamento da outra. Após resolver, adicionar somente os arquivos resolvidos e concluir `git merge --continue`. Não é necessário rebase, force push ou reescrita de commits anteriores.

## 4. Publicar e abrir o PR

Após validar o plano de refatoração e revisar o diff:

```powershell
git push -u origin feat/docs-pipeline
gh pr list --head feat/docs-pipeline --base main
```

Se ainda não houver PR dessa branch, criar um PR com base main, descrevendo a estrutura final, a compatibilidade dos contratos, as correções e os testes. Preparar um arquivo com a descrição revisada e usar:

```powershell
gh pr create --base main --head feat/docs-pipeline --title "refactor: align application structure under src" --body-file pr-description.md
```

`pr-description.md` é um exemplo de arquivo temporário de publicação: deve existir com o texto revisado e não precisa integrar o commit. Se o PR já existir, atualizar sua descrição em vez de criar outro.

A branch remota `(feat)_docs_pipeline` deve permanecer enquanto houver PR ativo ou dependentes. Não remover a branch antiga, fechar seu PR ou fazer merge do novo PR automaticamente como parte da padronização. Registrar no novo PR a relação com o anterior, se aplicável.

## 5. Worktree de documentação

Os documentos foram preparados em `worktree-docs`, associado a `docs/padronizacao-branches-e-fluxo`. Conferir o estado antes de integrar o conteúdo à branch de implementação:

```powershell
git -C ../worktree-docs status --short
git -C ../worktree-docs log -3 --oneline
```

Integrar somente os documentos revisados, preservando alterações existentes. Não remover o worktree enquanto contiver trabalho não integrado. Seu caminho não é parte da estrutura de execução do aplicativo.

## 6. Checklist de publicação

- [x] Branch de trabalho e destino conferidos; publicação em `feat/docs-pipeline`.
- [x] Correções existentes preservadas e novos commits com mensagens descritivas.
- [x] `origin/main` atualizado e integrado sem perda de contratos ou testes.
- [x] Refatoração e validações de `plano_refatoracao_estrutura_src.md` concluídas.
- [x] Diff revisado, sem dados locais, dependências instaladas ou segredos.
- [x] PR para main criado ou atualizado com evidências de validação.
- [x] Branch remota e PR anteriores preservados; nenhum merge de PR automático.

## Registro desta publicação

Executado em 12/09/2026: os commits da migração e do worktree de documentação
foram integrados sem rebase e publicados em `origin/feat/docs-pipeline`.
O [PR #3 para main](https://github.com/felipeCapovilla/HackatonEnter/pull/3)
foi aberto pela API do GitHub autenticada, equivalente aos comandos `gh` acima
(o GitHub CLI não estava instalado neste ambiente). O PR #1 já estava encerrado;
a branch antiga foi preservada. Nenhum PR foi mesclado nesta execução.
