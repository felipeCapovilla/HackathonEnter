import { expect, test } from "@playwright/test";

const documents = [
  { id: "doc-1", original_filename: "01_Contrato_emprestimo.txt", declared_type: "CONTRATO", page_count: 1, status: "COMPLETED" },
  { id: "doc-2", original_filename: "02_Comprovante_de_credito_operacao_bancaria_123456789.txt", declared_type: "COMPROVANTE_CREDITO", page_count: 1, status: "COMPLETED" },
];

async function setup(page, respond, sourceDocuments = documents, overrides = {}) {
  const filters = [];
  const requests = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: { id: "lawyer-1", name: "Ana Advogada", role: "ADVOGADO_EXTERNO", bank_name: "Banco Unicamp" } });
    if (path.endsWith("/conversations")) {
      filters.push(route.request().postDataJSON());
      return route.fulfill({ status: 201, json: { id: `conversation-${filters.length}` } });
    }
    if (path.endsWith("/messages")) {
      requests.push(route.request().postDataJSON());
      if (respond) return respond(route, requests.length);
      return route.fulfill({ status: 201, json: { id: `answer-${requests.length}`, role: "ASSISTANT", content: "O comprovante registra a liberação do crédito. Confira a data e o valor na fonte.",
        citations: [{ chunk_id: "c1", document_id: "doc-2", filename: documents[1].original_filename, page_start: 1, page_end: 1, quote: "Crédito liberado." }] } });
    }
    if (path === "/api/cases/case-1") return route.fulfill({ json: {
      case: { id: "case-1", case_number: "0801234-56.2024.8.10.0001", uf: "SP", value_of_claim: 10000 },
      documents: sourceDocuments, document_readings: [], analyses: [], lawyer_decisions: [], document_requests: [],
      fase: { codigo: "AGUARDANDO_AVALIACAO", rotulo: "Aguardando avaliação", proxima_acao: "Avaliar o processo" },
      ...overrides,
    } });
    if (path.includes("/pages/")) return route.fulfill({ json: { page_number: Number(path.split("/").at(-1)), text_content: `Contrato de empréstimo. Conteúdo da página ${path.split("/").at(-1)}.` } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/advogado/casos/case-1");
  await expect(page.getByRole("button", { name: "Perguntar à IA" })).toBeVisible();
  return { filters, requests };
}

test("chat no topo do leitor preserva conversa, rascunho e seleção ao reabrir, com fontes e foco", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const { filters } = await setup(page);
  const chat = page.locator(".document-chat");
  const viewerBox = await page.locator(".visualizador-quadro").boundingBox();
  const launcherBox = await page.locator(".dc-launcher").boundingBox();
  expect(launcherBox.y + launcherBox.height).toBeLessThanOrEqual(viewerBox.y);
  await page.screenshot({ path: testInfo.outputPath("chat-acesso.png") });
  await page.getByRole("button", { name: "Perguntar à IA" }).click();
  await page.getByRole("button", { name: "Conferir o crédito", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Pergunta sobre os documentos" });
  await expect(input).toHaveValue(/Há comprovante/);
  await page.getByRole("button", { name: "Enviar pergunta" }).click();
  await expect(chat.locator(".is-assistant")).toContainText("O comprovante registra");
  await expect(chat.getByRole("link")).toHaveAttribute("href", /doc-2\/file\?inline=1#page=1$/);
  expect(filters).toEqual([{ document_ids: [] }]);
  await page.getByRole("button", { name: "Selecionar", exact: true }).click();
  await page.getByRole("checkbox", { name: /Todos os documentos/ }).uncheck();
  await page.getByRole("checkbox", { name: /^Contrato/ }).check();
  await page.getByRole("button", { name: "Concluir", exact: true }).click();
  await input.fill("Qual é a data do contrato?");
  await page.getByRole("button", { name: "Fechar chat" }).click();
  await expect(page.getByRole("button", { name: "Continuar conversa" })).toBeFocused();
  await page.getByRole("button", { name: "Continuar conversa" }).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(input).toHaveValue("Qual é a data do contrato?");
  await expect(input).toBeFocused();
  await expect(modal).toContainText("O comprovante registra");
  await expect(modal.locator(".dc-selected-tags")).toContainText(documents[0].original_filename);
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
  await modal.screenshot({ path: testInfo.outputPath("chat-modal.png") });
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    expect(await modal.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(modal).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Continuar conversa" })).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");
  await page.getByRole("button", { name: "Continuar conversa" }).click();
  await expect(input).toHaveValue("Qual é a data do contrato?");
});

test("mensagem aparece durante a espera; falha permite retry sem duplicar balão e mantém próximo rascunho", async ({ page }) => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const { requests } = await setup(page, async (route, attempt) => {
    if (attempt === 1) {
      await gate;
      return route.fulfill({ status: 503, json: { detail: "Serviço indisponível agora." } });
    }
    return route.fulfill({ status: 201, json: { id: "answer-retry", role: "ASSISTANT", content: "Resposta após nova tentativa.", citations: [] } });
  });
  const input = page.getByRole("textbox", { name: "Pergunta sobre os documentos" });
  await page.getByRole("button", { name: "Perguntar à IA" }).click();
  await input.fill("Qual é o valor?");
  await input.press("Enter");
  await expect(page.locator(".dc-message.is-user")).toContainText("Qual é o valor?");
  await expect(page.getByRole("status")).toContainText("Consultando os documentos");
  await page.getByRole("button", { name: "Fechar chat" }).click();
  await page.getByRole("button", { name: "Continuar conversa" }).click();
  await expect(page.getByRole("button", { name: "Selecionar", exact: true })).toBeDisabled();
  await input.fill("Próxima pergunta");
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("Próxima pergunta\n");
  release();
  await expect(page.getByRole("alert")).toContainText("Serviço indisponível");
  await page.getByRole("button", { name: "Tentar novamente" }).click();
  await expect(page.locator(".dc-message.is-assistant")).toContainText("Resposta após");
  await expect(page.locator(".dc-message.is-user")).toHaveCount(1);
  await expect(input).toHaveValue("Próxima pergunta\n");
  expect(requests).toEqual([{ question: "Qual é o valor?" }, { question: "Qual é o valor?" }]);
  await page.getByRole("button", { name: "Fechar chat" }).click();
  await expect(page.getByRole("button", { name: "Continuar conversa" })).toBeVisible();
});

test("modal móvel mantém seleção e composição visíveis sem exceder a tela", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { filters } = await setup(page);
  await page.getByRole("button", { name: "Perguntar à IA" }).click();
  await page.getByRole("button", { name: "Selecionar", exact: true }).click();
  await page.getByRole("checkbox", { name: /Todos os documentos/ }).uncheck();
  const input = page.getByRole("textbox", { name: "Pergunta sobre os documentos" });
  await expect(input).toBeDisabled();
  await page.getByRole("checkbox", { name: /^Contrato/ }).check();
  await page.getByRole("button", { name: "Concluir", exact: true }).click();
  await input.fill("O contrato tem assinatura?");
  await page.getByRole("button", { name: "Enviar pergunta" }).click();
  await expect(page.locator(".dc-message.is-assistant")).toBeVisible();
  expect(filters).toEqual([{ document_ids: ["doc-1"] }]);
  const modal = page.getByRole("dialog");
  expect(await modal.evaluate((element) => element.scrollWidth <= window.innerWidth)).toBe(true);
  const footer = await page.locator(".dc-footer").boundingBox();
  expect(footer.y + footer.height).toBeLessThanOrEqual(845);
  await modal.screenshot({ path: testInfo.outputPath("chat-mobile.png") });
  await page.getByRole("button", { name: "Fechar chat" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("sem documentos mantém estado vazio e envio desabilitado também no modal", async ({ page }) => {
  await setup(page, null, []);
  await page.getByRole("button", { name: "Perguntar à IA" }).click();
  await expect(page.getByText("Os documentos chegam primeiro")).toBeVisible();
  await expect(page.getByRole("button", { name: "Enviar pergunta" })).toBeDisabled();
  await expect(page.getByRole("textbox")).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("todos os cards recolhem com resumo e preservam formulário; IA permanece acessível", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await setup(page, null, documents, {
    analyses: [{ id: "analysis-1", recommendation: "ACORDO", reasons: [], created_at: "2026-09-12T12:00:00Z", pricing: { opening_value: 100, target_value: 200, walk_away_value: 300, expected_defense_cost: 300 } }],
    fase: { codigo: "PRONTO_PARA_DECIDIR", rotulo: "Pronto para decidir", proxima_acao: "Registrar a decisão" },
  });
  const amount = page.getByRole("spinbutton", { name: "Valor da proposta" });
  await amount.fill("150");
  await page.getByRole("button", { name: "Recolher Decisão", exact: true }).click();
  await expect(amount).toBeHidden();
  await page.getByRole("button", { name: "Expandir Decisão", exact: true }).click();
  await expect(amount).toHaveValue("150");
  await page.getByRole("button", { name: "Recolher todos", exact: true }).click();
  await expect(page.locator(".case-panel")).toHaveCount(4);
  await expect(page.locator(".case-panel-body:visible")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Perguntar à IA" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("cards-recolhidos.png") });
  await page.getByRole("button", { name: "Perguntar à IA" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Fechar chat" }).click();
  await page.getByRole("button", { name: "Expandir todos", exact: true }).click();
  await expect(page.locator(".case-panel-body:visible")).toHaveCount(2);
  await expect(amount).toHaveValue("150");
});

const readyCase = {
  case: { id: "case-1", case_number: "0801234-56.2024.8.10.0001", uf: "MA", value_of_claim: 20000, sub_subject: "Não reconhecimento de empréstimo" },
  analyses: [{ id: "analysis-1", recommendation: "ACORDO", created_at: "2026-09-12T12:00:00Z", reasons: ["O custo esperado de defesa supera a proposta de acordo."],
    pricing: { opening_value: 2500, target_value: 3900, walk_away_value: 5100, expected_defense_cost: 5100 },
    policy_output: { p_perda: .65, p_estrela: .4 } }],
  fase: { codigo: "PRONTO_PARA_DECIDIR", rotulo: "Pronto para decidir", proxima_acao: "Registrar a decisão" },
};

test("áreas de avaliação, decisão e histórico preservam rascunhos e navegam pelo teclado", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const sameTypeDocs = [...documents, { ...documents[0], id: "doc-3", original_filename: "03_Contrato_aditivo_renegociacao.txt" }];
  await setup(page, null, sameTypeDocs, { ...readyCase, document_readings: [{ document_id: "doc-1", status: "COMPLETED", result: { resumo: "Contrato da operação de crédito questionada no processo.", pontos_de_atencao: ["Conferir a assinatura e a data de contratação."] } }] });
  await expect(page.getByRole("tab", { name: "Próximo passo" })).toHaveAttribute("aria-selected", "true");
  const amount = page.getByRole("spinbutton", { name: "Valor da proposta" });
  await amount.fill("2800");
  await page.getByRole("tab", { name: "Avaliação" }).click();
  await expect(amount).toBeHidden();
  await expect(page.getByRole("heading", { name: "Propor acordo", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("workspace-desktop.png") });
  await page.getByRole("button", { name: "Continuar para a decisão" }).click();
  await expect(amount).toHaveValue("2800");
  await page.getByRole("tab", { name: "Histórico" }).click();
  await expect(page.locator(".linha-do-tempo")).toContainText("Avaliação: Propor acordo");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tab", { name: "Avaliação" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(amount).toHaveValue("2800");
  const documentTabs = page.getByRole("tablist", { name: "Documentos do processo" });
  await expect(documentTabs.getByRole("tab")).toHaveCount(3);
  await expect(page.getByRole("combobox", { name: "Arquivo em leitura" })).toHaveCount(0);
  await documentTabs.getByTitle("03_Contrato_aditivo_renegociacao.txt").click();
  await expect(documentTabs.getByTitle("03_Contrato_aditivo_renegociacao.txt")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".visualizador-rodape")).toContainText("03_Contrato_aditivo");
  await page.keyboard.press("ArrowRight");
  await expect(documentTabs.getByRole("tab", { name: "Comprovante de crédito" })).toBeFocused();
  await expect(documentTabs.getByRole("tab", { name: "Comprovante de crédito" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".visualizador-rodape")).toContainText(documents[1].original_filename);
  await page.getByRole("button", { name: "Recolher todos", exact: true }).click();
  await page.getByRole("button", { name: "Ir para decisão", exact: true }).click();
  await expect(amount).toBeVisible();
  await expect(amount).toHaveValue("2800");
  await expect(page.locator(".visualizador")).toBeHidden();
});

test("no celular a próxima ação leva direto à decisão e permite voltar ao mesmo documento", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, null, documents, readyCase);
  await page.getByRole("tab", { name: "Comprovante de crédito" }).click();
  await page.getByRole("button", { name: "Ir para decisão", exact: true }).click();
  await expect(page.locator(".caso-documentos-coluna")).toBeHidden();
  const amount = page.getByRole("spinbutton", { name: "Valor da proposta" });
  await amount.fill("2600");
  await page.getByRole("button", { name: "Documentos", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Comprovante de crédito" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Perguntar à IA" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Análise e decisão", exact: true }).click();
  await expect(amount).toHaveValue("2600");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("workspace-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("leitor distingue falha de processamento e permite ler todas as páginas de texto", async ({ page }) => {
  await setup(page, null, [{ ...documents[0], page_count: 24 }, { ...documents[1], status: "FAILED" }]);
  await expect(page.getByRole("button", { name: "Página anterior" })).toBeDisabled();
  for (let index = 1; index < 24; index++) await page.getByRole("button", { name: "Próxima página" }).click();
  await expect(page.getByText("Página 24 de 24", { exact: true })).toBeVisible();
  await expect(page.locator(".texto-extraido")).toContainText("Conteúdo da página 24");
  await expect(page.getByRole("button", { name: "Próxima página" })).toBeDisabled();
  await page.getByRole("tab", { name: "Comprovante de crédito" }).click();
  await expect(page.getByRole("heading", { name: "Não foi possível extrair este documento" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Preparando a leitura" })).toHaveCount(0);
});
