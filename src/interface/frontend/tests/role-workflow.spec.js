import { expect, test } from "@playwright/test";

const bank = { id: "bank-user", name: "Operação Banco", email: "banco@unicamp.br", role: "BANCO", bank_id: "banco-unicamp", bank_name: "Banco Unicamp", is_active: true, csrf_token: "csrf" };
const lawyer = { id: "lawyer-user", name: "Ana Advogada", email: "ana@unicamp.br", role: "ADVOGADO_EXTERNO", bank_id: "banco-unicamp", bank_name: "Banco Unicamp", is_active: true, csrf_token: "csrf" };

async function api(page, user, cases = []) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/auth/me") return route.fulfill({ json: user });
    if (url === "/api/auth/logout") return route.fulfill({ status: 204 });
    if (url === "/api/cases") {
      if (route.request().method() === "GET") return route.fulfill({ json: cases });
      return route.fulfill({ status: 201, json: { id: "new-case", case_number: "novo-1", uf: "SP", value_of_claim: 1000 } });
    }
    if (url === "/api/bank/lawyers") return route.fulfill({ json: [lawyer] });
    if (url.startsWith("/api/cases/")) return route.fulfill({ json: { case: cases[0] || { id: "case-1", case_number: "001", uf: "SP", value_of_claim: 1000 }, documents: [], analyses: [{ id: "analysis-1", recommendation: "ACORDO", reasons: ["Subsídios insuficientes."], pricing: { target_value: 300 } }], lawyer_decisions: [] } });
    if (url === "/api/monitoring") return route.fulfill({ json: { total_analyses: 1, total_lawyer_decisions: 0, adherence_rate: null } });
    return route.fulfill({ json: {} });
  });
}

test("banco abre processo e enxerga a recomendação, sem registrar decisão jurídica", async ({ page }) => {
  await api(page, bank, [{ id: "case-1", case_number: "001", uf: "SP", value_of_claim: 1000, assigned_lawyer_id: lawyer.id }]);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Abrir novo processo" })).toBeVisible();
  await page.getByRole("link", { name: /001/ }).click();
  await expect(page.getByRole("heading", { name: "Saída da ferramenta" })).toBeVisible();
  await expect(page.getByText("Propor acordo")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Registrar decisão" })).toHaveCount(0);
});

test("advogado vê apenas seus processos e pode executar a avaliação", async ({ page }) => {
  await api(page, lawyer, [{ id: "case-1", case_number: "001", uf: "SP", value_of_claim: 1000, assigned_lawyer_id: lawyer.id }]);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Meus processos" })).toBeVisible();
  await page.getByRole("link", { name: /001/ }).click();
  await expect(page.getByRole("button", { name: "Avaliar risco e recomendação" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Registrar decisão" })).toBeVisible();
});

test("criação de processo navega para o detalhe após salvar", async ({ page }) => {
  await api(page, bank);
  const created = { id: "new-case", case_number: "novo-1", uf: "SP", value_of_claim: 1000 };
  await page.route("**/api/cases/new-case", (route) => route.fulfill({ json: {
    case: created, documents: [], analyses: [], lawyer_decisions: [],
  } }));
  await page.goto("/banco");
  await page.getByLabel("Número do processo").fill(created.case_number);
  await page.getByLabel("Valor da causa").fill("1000");
  const saved = page.waitForResponse((response) => response.url().endsWith("/api/cases") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Abrir processo", exact: true }).click();
  expect((await saved).status()).toBe(201);
  await expect(page).toHaveURL(/\/banco\/casos\/new-case$/);
  await expect(page.getByRole("heading", { name: created.case_number, exact: true })).toBeVisible();
  await expect(page.locator(".warning")).toHaveCount(0);
});

test("falha ao salvar preserva os campos do processo", async ({ page }) => {
  await api(page, bank);
  await page.route("**/api/cases", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    return route.fulfill({ status: 422, json: { detail: "Número de processo já cadastrado." } });
  });
  await page.goto("/banco");
  await page.getByLabel("Número do processo").fill("duplicado-1");
  await page.getByLabel("Valor da causa").fill("1000");
  await page.getByRole("button", { name: "Abrir processo", exact: true }).click();
  await expect(page.getByText("Número de processo já cadastrado.")).toBeVisible();
  await expect(page.getByLabel("Número do processo")).toHaveValue("duplicado-1");
  await expect(page.getByLabel("Valor da causa")).toHaveValue("1000");
  await expect(page).toHaveURL(/\/banco$/);
});

for (const entity of ["banco", "usuário"]) {
  test(`cadastro de ${entity} limpa formulário e atualiza lista após salvar`, async ({ page }) => {
    await api(page, { ...bank, role: "ADMIN_GLOBAL", bank_id: null });
    const banks = [{ id: "banco-unicamp", name: "Banco Unicamp" }];
    const users = [];
    for (const [resource, records] of [["banks", banks], ["users", users]]) {
      await page.route(`**/api/admin/${resource}`, (route) => {
        if (route.request().method() === "GET") return route.fulfill({ json: records });
        const created = { ...route.request().postDataJSON(), id: "new-record", is_active: true };
        records.push(created);
        return route.fulfill({ status: 201, json: created });
      });
    }
    await page.goto("/admin");
    const button = page.getByRole("button", { name: `Cadastrar ${entity}`, exact: true });
    const form = page.locator("form").filter({ has: button });
    const name = entity === "banco" ? "Banco de teste" : "Advogada de teste";
    await form.getByLabel("Nome", { exact: true }).fill(name);
    if (entity === "usuário") {
      await form.getByLabel("E-mail").fill("nova@example.test");
      await form.getByLabel("Senha inicial (15+ caracteres)").fill("senha-para-teste-123");
    }
    await button.click();
    await expect(form.getByLabel("Nome", { exact: true })).toHaveValue("");
    await expect(page.getByRole("listitem").filter({ hasText: name })).toBeVisible();
    await expect(page.locator(".warning")).toHaveCount(0);
  });
}

test("registro de decisão limpa formulário e exibe decisão salva", async ({ page }) => {
  await api(page, lawyer);
  const detail = {
    case: { id: "case-1", case_number: "001", uf: "SP", value_of_claim: 1000 },
    documents: [],
    analyses: [{ id: "analysis-1", recommendation: "ACORDO", reasons: ["Subsídios insuficientes."] }],
    lawyer_decisions: [],
  };
  await page.route("**/api/cases/case-1", (route) => route.fulfill({ json: detail }));
  await page.route("**/api/cases/case-1/lawyer-decisions?*", (route) => {
    const decision = { ...route.request().postDataJSON(), id: "decision-1" };
    detail.lawyer_decisions.unshift(decision);
    return route.fulfill({ status: 201, json: decision });
  });
  await page.goto("/advogado/casos/case-1");
  await page.getByLabel("Valor proposto").fill("300");
  await page.getByLabel("Justificativa").fill("Proposta conforme política.");
  await page.getByRole("button", { name: "Registrar decisão", exact: true }).click();
  await expect(page.getByText("Decisão registrada pelo advogado: Acordo")).toBeVisible();
  await expect(page.getByLabel("Justificativa")).toHaveValue("");
  await expect(page.getByLabel("Valor proposto")).toHaveValue("");
  await expect(page.locator(".warning")).toHaveCount(0);
});

test("sair volta ao login e permanece deslogado após recarregar", async ({ page }) => {
  await api(page, bank);
  let loggedOut = false;
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: loggedOut ? null : bank }));
  await page.route("**/api/auth/logout", (route) => {
    loggedOut = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/banco");
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("E-mail")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("E-mail")).toBeVisible();
  await page.goto("/banco");
  await expect(page).toHaveURL(/\/login$/);
});

test("falha no logout informa o erro e permite sair novamente", async ({ page }) => {
  await api(page, bank);
  let attempts = 0;
  await page.route("**/api/auth/logout", (route) => {
    attempts += 1;
    return attempts === 1
      ? route.fulfill({ status: 503, json: { detail: "Serviço temporariamente indisponível." } })
      : route.fulfill({ status: 204 });
  });
  await page.goto("/banco");
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Serviço temporariamente indisponível.");
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(attempts).toBe(2);
});

test("sessão expirada redireciona ao login sem manter a área autenticada", async ({ page }) => {
  await api(page, bank);
  await page.route("**/api/cases", (route) => route.fulfill({ status: 401, json: { detail: "Sessão expirada." } }));
  await page.goto("/banco");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Sua sessão expirou. Entre novamente.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Abrir novo processo" })).toHaveCount(0);
});

test("monitoramento permite repetir carregamento que falhou", async ({ page }) => {
  await api(page, bank);
  let attempts = 0;
  await page.route("**/api/monitoring", (route) => {
    attempts += 1;
    return attempts === 1
      ? route.fulfill({ status: 503, json: { detail: "Monitoramento indisponível." } })
      : route.fulfill({ json: { total_analyses: 12, total_lawyer_decisions: 4, adherence_rate: 0.75 } });
  });
  await page.goto("/banco/monitoramento");
  await expect(page.getByRole("alert")).toContainText("Monitoramento indisponível.");
  await page.getByRole("button", { name: "Tentar novamente" }).click();
  await expect(page.getByText("75.0%", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("validação estruturada da API aparece como texto e preserva valores com centavos", async ({ page }) => {
  await api(page, bank);
  let submitted;
  await page.route("**/api/cases", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 422, json: { detail: [{ loc: ["body", "value_of_claim"], msg: "Valor não permitido para este caso." }] } });
  });
  await page.goto("/banco");
  await page.getByLabel("Número do processo").fill("centavos-1");
  await page.getByLabel("Valor da causa").fill("1000.50");
  await page.getByRole("button", { name: "Abrir processo", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Valor não permitido para este caso.");
  expect(submitted.value_of_claim).toBe(1000.5);
  await expect(page.getByLabel("Valor da causa")).toHaveValue("1000.50");
});

test("submissão pendente impede criação duplicada", async ({ page }) => {
  await api(page, bank);
  let pendingRoute;
  let submissions = 0;
  await page.route("**/api/cases", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    submissions += 1;
    pendingRoute = route;
  });
  await page.goto("/banco");
  await page.getByLabel("Número do processo").fill("unico-1");
  await page.getByLabel("Valor da causa").fill("1000");
  await page.getByRole("button", { name: "Abrir processo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Salvando…" })).toBeDisabled();
  await page.locator("form").dispatchEvent("submit");
  await expect.poll(() => submissions).toBe(1);
  await pendingRoute.fulfill({ status: 201, json: { id: "new-case" } });
  await expect(page).toHaveURL(/\/banco\/casos\/new-case$/);
  expect(submissions).toBe(1);
});

test("admin global é cadastrado sem associação com banco", async ({ page }) => {
  await api(page, { ...bank, role: "ADMIN_GLOBAL", bank_id: null });
  await page.route("**/api/admin/banks", (route) => route.fulfill({ json: [{ id: "banco-unicamp", name: "Banco Unicamp" }] }));
  let submitted;
  await page.route("**/api/admin/users", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 201, json: { ...submitted, id: "new-admin" } });
  });
  await page.goto("/admin");
  const form = page.locator("form").filter({ has: page.getByRole("button", { name: "Cadastrar usuário" }) });
  await form.getByLabel("Nome", { exact: true }).fill("Novo Admin");
  await form.getByLabel("E-mail").fill("admin@example.test");
  await form.getByLabel("Senha inicial (15+ caracteres)").fill("senha-para-teste-123");
  await form.getByLabel("Perfil").selectOption("ADMIN_GLOBAL");
  await expect(form.getByLabel("Banco", { exact: true })).toBeDisabled();
  await form.getByRole("button", { name: "Cadastrar usuário" }).click();
  await expect(form.getByLabel("Nome", { exact: true })).toHaveValue("");
  expect(submitted.bank_id).toBeNull();
  expect(submitted.role).toBe("ADMIN_GLOBAL");
});

test("nova análise atualiza a ação padrão e permite recuperar de erro", async ({ page }) => {
  await api(page, lawyer);
  const detail = {
    case: { id: "case-1", case_number: "001", uf: "SP", value_of_claim: 1000 }, documents: [], lawyer_decisions: [],
    analyses: [{ id: "old-analysis", recommendation: "ACORDO", reasons: ["Provas insuficientes."] }],
  };
  let attempts = 0;
  await page.route("**/api/cases/case-1", (route) => route.fulfill({ json: detail }));
  await page.route("**/api/cases/case-1/analyses", (route) => {
    attempts += 1;
    if (attempts === 1) return route.fulfill({ status: 503, json: { detail: "Análise indisponível." } });
    detail.analyses = [{ id: "new-analysis", recommendation: "DEFESA", reasons: ["Provas suficientes."] }];
    return route.fulfill({ status: 201, json: detail.analyses[0] });
  });
  await page.goto("/advogado/casos/case-1");
  await expect(page.getByLabel("Ação", { exact: true })).toHaveValue("ACORDO");
  await page.getByRole("button", { name: "Avaliar risco e recomendação" }).click();
  await expect(page.getByRole("alert")).toContainText("Análise indisponível.");
  await expect(page.getByRole("heading", { name: "001", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Avaliar risco e recomendação" }).click();
  await expect(page.getByLabel("Ação", { exact: true })).toHaveValue("DEFESA");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("rotas desconhecidas voltam à página inicial do perfil", async ({ page }) => {
  await api(page, bank);
  await page.goto("/rota-inexistente");
  await expect(page).toHaveURL(/\/banco$/);
  await expect(page.getByRole("heading", { name: "Abrir novo processo" })).toBeVisible();
});

test("tela do banco cabe em uma janela móvel", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await api(page, bank, [{ id: "case-1", case_number: "1234567890".repeat(7), uf: "SP", value_of_claim: 1000 }]);
  await page.goto("/banco");
  await expect(page.getByRole("heading", { name: "Abrir novo processo" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByRole("button", { name: "Sair", exact: true })).toBeVisible();
});

