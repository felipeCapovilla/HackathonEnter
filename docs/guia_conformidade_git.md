# Guia de Conformidade de Branches e Commits — EnterAgree

Este documento estabelece as diretrizes de padronização para branches, mensagens de commit e fluxo de trabalho Git no repositório **EnterAgree**, garantindo a conformidade entre branches de funcionalidade (`feature`) e a branch principal (`main`).

---

## 1. Diagnóstico do Estado Atual

Na análise realizada no repositório:
- **Branch Atual Anterior**: `(feat)_docs_pipeline`
- **Branch Principal**: `main`

### Inconformidades Identificadas:
1. **Formato do Nome da Branch**:
   - O uso de parênteses e sublinhados `(feat)_docs_pipeline` não segue a convenção Git nem do repositório.
   - Parênteses no nome da branch exigem aspas para navegação em terminais (Bash/Zsh/PowerShell) e podem quebrar pipelines de CI/CD ou integrações automatizadas.
2. **Padrão Exigido por `main`**:
   - Padrão **Git Flow / Conventional Branches**: Categoria minúscula com barra `/` e separação por hífens `-` (ex: `feat/docs-pipeline` ou `docs/pipeline`).
   - Padrão **Conventional Commits**: Commits estruturados no formato `<tipo>: <descrição imperativa em minúsculas>`.

---

## 2. Padrões Exigidos no Repositório

### 2.1 Nomenclatura de Branches
As branches devem seguir o formato `<tipo>/<descricao-kebab-case>`:

| Tipo | Descrição | Exemplo |
| :--- | :--- | :--- |
| `feat/` | Novas funcionalidades | `feat/autenticacao-jwt` |
| `docs/` | Alterações puras de documentação | `docs/pipeline-documentacao` |
| `fix/` | Correção de bugs | `fix/validacao-ocr` |
| `refactor/` | Refatoração de código sem alterar regra de negócio | `refactor/politicas-servico` |
| `test/` | Adição ou alteração de testes | `test/cobertura-rag` |

### 2.2 Formato de Commits (Conventional Commits)
Todas as mensagens de commit em conformidade com a `main` devem seguir:
```text
<tipo>: <descrição curta e clara>

[corpo opcional detalhando o motivo da mudança]
```
Exemplos válidos observados no projeto:
- `docs: plan bank lawyer and global admin access`
- `feat: add evidence-backed agreement pipeline`
- `test: add unit tests for document type validation`

---

## 3. Passo a Passo: Como Colocar a Branch Atual em Conformidade

Se você possui uma branch no formato incorreto (como `(feat)_docs_pipeline`), siga os passos abaixo para deixá-la em conformidade total com a `main`:

### Passo 1: Renomear a Branch Localmente
Renomeie a branch atual para o nome padronizado usando hífen e barra:
```bash
git branch -m "(feat)_docs_pipeline" feat/docs-pipeline
```

### Passo 2: Commitar ou Organizar Mudanças Pendentes
Verifique o estado das suas alterações (`git status`). Commite as alterações pendentes respeitando o Conventional Commits:
```bash
git add backend/ frontend/ tests/
git commit -m "feat: implement document pipeline and interface components"
```

### Passo 3: Sincronizar e Aplicar Rebase sobre a `main`
Garanta que sua branch esteja atualizada a partir do topo da `main`:
```bash
git fetch origin
git rebase origin/main
```
> **Nota**: Se houver conflitos durante o rebase, resolva os arquivos, execute `git add <arquivo-resolvido>` e continue com `git rebase --continue`.

### Passo 4: Publicar a Nova Branch no Remoto
Envie a branch renomeada e ajustada para o repositório remoto:
```bash
git push -u origin feat/docs-pipeline
```

### Passo 5: Remover a Branch com Nome Antigo do Remoto (se aplicável)
Se a branch antiga `(feat)_docs_pipeline` já havia sido enviada ao GitHub/GitLab:
```bash
git push origin --delete "(feat)_docs_pipeline"
```

---

## 4. Uso de Git Worktree (Árvores de Trabalho Isoladas)

Para trabalhar em novas tarefas ou documentações sem sujar o diretório atual nem precisar alternar (`git checkout`) constantemente, utiliza-se o **Git Worktree**.

### O que foi executado para este trabalho:
Criamos um worktree isolado na pasta paralela `worktree-docs`:
```bash
git worktree add ..\worktree-docs -b docs/padronizacao-branches-e-fluxo main
```

### Comandos Úteis do Git Worktree:
- **Listar worktrees ativos**:
  ```bash
  git worktree list
  ```
- **Remover um worktree após concluir o trabalho**:
  ```bash
  git worktree remove ..\worktree-docs
  ```

---

## 5. Checklist de Verificação Antes do Pull Request (PR)

Antes de abrir um Pull Request para a branch `main`:
- [ ] Branch renomeada sem parênteses e no padrão `tipo/nome-da-feature`.
- [ ] Commits no padrão Conventional Commits (`feat:`, `docs:`, `fix:`, etc.).
- [ ] Rebase executado com sucesso sobre a `main` mais recente.
- [ ] Suíte de testes automatizados executada e aprovada (`pytest`).
- [ ] Documentação atualizada na pasta `docs/`.
