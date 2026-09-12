import { expect, test } from "@playwright/test";

function caseDetail(caseId, overrides = {}) {
  return {
    case: { id: caseId, case_number: `processo-${caseId}`, uf: "SP", value_of_claim: 1000 },
    documents: [{
      id: `dossie-${caseId}`, original_filename: `dossie-${caseId}.pdf`, declared_type: "DOSSIE",
      status: "COMPLETED", type_status: "CONFIRMED", pages_extracted: 2, page_count: 2,
      ...overrides,
    }],
    analyses: [], lawyer_decisions: [], document_requests: [], dossie_analyses: [],
  };
}

function analysisRecord(caseId) {
  return {
    id: `analysis-${caseId}`, document_id: `dossie-${caseId}`, status: "COMPLETED",
    error_code: null, model: "test-model", created_at: "2026-09-12T12:00:00Z",
    evidencias_total: 1, evidencias_carregadas: true,
    result: {
      docie_existe: true,
      analise: {
        veredito: "conforme", analisou_assinatura_contrato: true,
        numero_contrato_referenciado: "12345", confianca_extracao: 0.9,
        itens: [{ tipo: "assinatura", resultado: "ok", indice: 0.95 }],
      },
      evidencias: [{ campo: "assinatura", valor: "ok", pagina: 2, trecho: "A assinatura analisada corresponde ao titular." }],
      avisos: ["Verificar a página ilegível."], paginas_processadas: 2, trechos_processados: 1, completo: false,
    },
  };
}

function summaryRecord(record) {
  return { ...record, evidencias_carregadas: false, result: { ...record.result, evidencias: [] } };
}

function addProcessingDocument(detail) {
  detail.documents.push({
    id: "pending-document", original_filename: "autos.pdf", declared_type: "AUTOS",
    status: "EXTRACTING", type_status: "PENDING", pages_extracted: 0, page_count: 2,
  });
}

async function serveApi(page, details, intercept = async () => false) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (await intercept(route, pathname, request)) return;
    if (pathname === "/api/cases") {
      await route.fulfill({ json: Object.values(details).map((detail) => detail.case) });
    } else if (pathname === "/api/monitoring") {
      await route.fulfill({ json: { total_analyses: 0, total_lawyer_decisions: 0, recommendations: {} } });
    } else {
      const detail = details[pathname.replace("/api/cases/", "")];
      if (!detail) throw new Error(`Unexpected API request: ${request.method()} ${pathname}`);
      await route.fulfill({ json: detail });
    }
  });
}

test("dossie analysis is explicit and shows persisted evidence without changing policy", async ({ page }) => {
  const details = { first: caseDetail("first"), second: caseDetail("second") };
  let analysisCalls = 0;
  await serveApi(page, details, async (route, pathname, request) => {
    if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
    expect(request.method()).toBe("POST");
    analysisCalls += 1;
    const record = analysisRecord("first");
    details.first.dossie_analyses = [record];
    await route.fulfill({ status: 201, json: record });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  const panel = page.getByRole("region", { name: "Análise de dossiê: dossie-first.pdf" });
  await expect(panel).toContainText("será enviado à OpenAI");
  expect(analysisCalls).toBe(0);
  await panel.getByRole("button", { name: "Analisar dossiê com IA" }).click();
  await expect(panel).toContainText("Veredito do dossiê: Conforme");
  await expect(panel).toContainText("O dossiê examinou a assinatura do contrato: Sim");
  await expect(panel).toContainText("Contrato referenciado: 12345");
  await expect(panel).toContainText("Índice reportado: 95%");
  await expect(panel).toContainText("Confiança da extração: 90%");
  await expect(panel).toContainText("Não é confiança jurídica");
  await expect(panel).toContainText("Análise incompleta");
  await expect(panel).toContainText("Verificar a página ilegível");
  await expect(panel).toContainText("A assinatura analisada corresponde ao titular.");
  await expect(panel.getByRole("link", { name: "Página 2 (texto extraído)" }))
    .toHaveAttribute("href", /\/api\/documents\/dossie-first\/pages\/2$/);
  await expect(page.locator(".analysis")).toContainText("A análise aparecerá aqui após a execução");
  await page.getByRole("button", { name: /processo-second/ }).click();
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await expect(panel).toContainText("Veredito do dossiê: Conforme");
  expect(analysisCalls).toBe(1);
});

for (const failed of [false, true]) {
  test(`late dossie ${failed ? "failure" : "success"} cannot contaminate another case`, async ({ page }) => {
    const details = { first: caseDetail("first"), second: caseDetail("second") };
    let releaseAnalysis;
    const ready = new Promise((resolve) => { releaseAnalysis = resolve; });
    await serveApi(page, details, async (route, pathname) => {
      if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
      await ready;
      await route.fulfill(failed
        ? { status: 503, json: { detail: "Serviço indisponível no caso anterior" } }
        : { status: 201, json: analysisRecord("first") });
      return true;
    });
    await page.goto("/");
    await page.getByRole("button", { name: /processo-first/ }).click();
    const firstRequest = page.waitForRequest("**/api/documents/dossie-first/dossie-analysis");
    await page.getByRole("button", { name: "Analisar dossiê com IA" }).click();
    await firstRequest;
    await expect(page.getByRole("button", { name: "Analisando dossiê…" })).toBeDisabled();
    await page.getByRole("button", { name: /processo-second/ }).click();
    await expect(page.locator(".case-title h2")).toHaveText("processo-second");
    const firstResponse = page.waitForResponse("**/api/documents/dossie-first/dossie-analysis");
    releaseAnalysis();
    await firstResponse;
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator(".case-title h2")).toHaveText("processo-second");
    await expect(page.getByRole("button", { name: "Analisar dossiê com IA" })).toBeEnabled();
    await expect(page.getByText("Veredito do dossiê:")).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
}

test("dossie service failures are actionable and allow retry", async ({ page }) => {
  const details = { first: caseDetail("first") };
  await serveApi(page, details, async (route, pathname) => {
    if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
    await route.fulfill({ status: 503, json: { detail: "Configure o serviço de análise na API." } });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await page.getByRole("button", { name: "Analisar dossiê com IA" }).click();
  await expect(page.getByRole("alert")).toContainText("Configure o serviço de análise na API");
  await expect(page.getByRole("button", { name: "Analisar dossiê com IA" })).toBeEnabled();
  await expect(page.getByText("Veredito do dossiê:")).toHaveCount(0);
});

test("dossie analysis waits for extraction and type mismatch confirmation", async ({ page }) => {
  const details = {
    extracting: caseDetail("extracting", { status: "EXTRACTING" }),
    mismatch: caseDetail("mismatch", { type_status: "MISMATCH", detected_type: "CONTRATO" }),
  };
  await serveApi(page, details);
  await page.goto("/");
  await page.getByRole("button", { name: /processo-extracting/ }).click();
  await expect(page.getByRole("button", { name: "Analisar dossiê com IA" })).toBeDisabled();
  await expect(page.getByText(/A análise requer a extração documental concluída/)).toBeVisible();
  await page.getByRole("button", { name: /processo-mismatch/ }).click();
  await expect(page.getByRole("button", { name: "Analisar dossiê com IA" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Confirmar tratamento" })).toBeVisible();
});

test("unknown and conflicting signature findings are not presented as a negative examination", async ({ page }) => {
  const details = { unknown: caseDetail("unknown"), conflicting: caseDetail("conflicting") };
  const unknownRecord = analysisRecord("unknown");
  unknownRecord.result.analise.analisou_assinatura_contrato = false;
  unknownRecord.result.assinatura_contrato_status = "desconhecido";
  details.unknown.dossie_analyses = [unknownRecord];
  const conflictingRecord = analysisRecord("conflicting");
  conflictingRecord.result.analise.analisou_assinatura_contrato = false;
  conflictingRecord.result.assinatura_contrato_status = "conflitante";
  details.conflicting.dossie_analyses = [conflictingRecord];
  await serveApi(page, details);
  await page.goto("/");
  await page.getByRole("button", { name: /processo-unknown/ }).click();
  await expect(page.getByRole("region", { name: "Análise de dossiê: dossie-unknown.pdf" }))
    .toContainText("O dossiê examinou a assinatura do contrato: Não identificado");
  await page.getByRole("button", { name: /processo-conflicting/ }).click();
  await expect(page.getByRole("region", { name: "Análise de dossiê: dossie-conflicting.pdf" }))
    .toContainText("O dossiê examinou a assinatura do contrato: Conflitante");
});

test("removed and reclassified documents do not show an active dossie result", async ({ page }) => {
  const details = {
    removed: caseDetail("removed", { type_status: "REMOVED" }),
    reclassified: caseDetail("reclassified", { declared_type: "CONTRATO" }),
  };
  details.removed.dossie_analyses = [analysisRecord("removed")];
  details.reclassified.dossie_analyses = [analysisRecord("reclassified")];
  await serveApi(page, details);
  await page.goto("/");
  for (const caseId of ["removed", "reclassified"]) {
    await page.getByRole("button", { name: new RegExp(`processo-${caseId}`) }).click();
    await expect(page.locator(".case-title h2")).toHaveText(`processo-${caseId}`);
    await expect(page.getByRole("button", { name: "Analisar dossiê com IA" })).toHaveCount(0);
    await expect(page.getByText("Veredito do dossiê:")).toHaveCount(0);
  }
});

test("summary evidence loads only on demand and remains visible after polling", async ({ page }) => {
  const details = { first: caseDetail("first") };
  const fullRecord = analysisRecord("first");
  details.first.dossie_analyses = [summaryRecord(fullRecord)];
  addProcessingDocument(details.first);
  let evidenceCalls = 0;
  await serveApi(page, details, async (route, pathname, request) => {
    if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
    expect(request.method()).toBe("GET");
    evidenceCalls += 1;
    await route.fulfill({ json: fullRecord });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  const panel = page.getByRole("region", { name: "Análise de dossiê: dossie-first.pdf" });
  await expect(panel).toContainText("Veredito do dossiê: Conforme");
  await expect(panel).toContainText("1 evidências disponíveis");
  await expect(panel).not.toContainText("Nenhuma evidência referenciada");
  expect(evidenceCalls).toBe(0);
  await panel.getByRole("button", { name: "Carregar evidências" }).click();
  await expect(panel).toContainText("A assinatura analisada corresponde ao titular.");
  details.first.dossie_analyses[0].result.avisos = ["Contexto documental atualizado."];
  details.first.dossie_analyses[0].result.completo = true;
  await page.waitForResponse("**/api/cases/first");
  await expect(panel).toContainText("A assinatura analisada corresponde ao titular.");
  await expect(panel).toContainText("Contexto documental atualizado.");
  await expect(panel).not.toContainText("Análise incompleta");
  await expect(panel.getByRole("button", { name: "Carregar evidências" })).toHaveCount(0);
  expect(evidenceCalls).toBe(1);
});

test("evidence load failure preserves the summary and permits retry", async ({ page }) => {
  const details = { first: caseDetail("first") };
  const fullRecord = analysisRecord("first");
  details.first.dossie_analyses = [summaryRecord(fullRecord)];
  let evidenceCalls = 0;
  await serveApi(page, details, async (route, pathname) => {
    if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
    evidenceCalls += 1;
    await route.fulfill(evidenceCalls === 1
      ? { status: 503, json: { detail: "Consulta temporariamente indisponível" } }
      : { json: fullRecord });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await page.getByRole("button", { name: "Carregar evidências" }).click();
  await expect(page.getByRole("alert")).toContainText("Consulta temporariamente indisponível");
  await expect(page.locator(".dossie-result")).toContainText("Veredito do dossiê: Conforme");
  await expect(page.getByRole("button", { name: "Carregar evidências" })).toBeEnabled();
  await page.getByRole("button", { name: "Carregar evidências" }).click();
  await expect(page.locator(".dossie-result")).toContainText("A assinatura analisada corresponde ao titular.");
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(evidenceCalls).toBe(2);
});

test("a newer analysis discards evidence arriving from the previous record", async ({ page }) => {
  const details = { first: caseDetail("first") };
  const previousRecord = analysisRecord("first");
  details.first.dossie_analyses = [summaryRecord(previousRecord)];
  addProcessingDocument(details.first);
  let releaseEvidence;
  const ready = new Promise((resolve) => { releaseEvidence = resolve; });
  await serveApi(page, details, async (route, pathname) => {
    if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
    await ready;
    await route.fulfill({ json: previousRecord });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  const evidenceRequest = page.waitForRequest("**/api/documents/dossie-first/dossie-analysis");
  await page.getByRole("button", { name: "Carregar evidências" }).click();
  await evidenceRequest;
  await expect(page.getByRole("button", { name: "Carregando evidências…" })).toBeDisabled();
  const latestRecord = analysisRecord("first");
  latestRecord.id = "new-analysis";
  latestRecord.result.analise.numero_contrato_referenciado = "67890";
  details.first.dossie_analyses = [summaryRecord(latestRecord)];
  await page.waitForResponse("**/api/cases/first");
  await expect(page.locator(".dossie-result")).toContainText("Contrato referenciado: 67890");
  const evidenceResponse = page.waitForResponse("**/api/documents/dossie-first/dossie-analysis");
  releaseEvidence();
  await evidenceResponse;
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator(".dossie-result")).toContainText("Contrato referenciado: 67890");
  await expect(page.locator(".dossie-result")).not.toContainText("A assinatura analisada corresponde ao titular.");
  await expect(page.getByRole("button", { name: "Carregar evidências" })).toBeEnabled();
});

test("late evidence failures cannot add an error to another case", async ({ page }) => {
  const details = { first: caseDetail("first"), second: caseDetail("second") };
  details.first.dossie_analyses = [summaryRecord(analysisRecord("first"))];
  let releaseEvidence;
  const ready = new Promise((resolve) => { releaseEvidence = resolve; });
  await serveApi(page, details, async (route, pathname) => {
    if (pathname !== "/api/documents/dossie-first/dossie-analysis") return false;
    await ready;
    await route.fulfill({ status: 503, json: { detail: "Falha no processo anterior" } });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  const evidenceRequest = page.waitForRequest("**/api/documents/dossie-first/dossie-analysis");
  await page.getByRole("button", { name: "Carregar evidências" }).click();
  await evidenceRequest;
  await page.getByRole("button", { name: /processo-second/ }).click();
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
  const evidenceResponse = page.waitForResponse("**/api/documents/dossie-first/dossie-analysis");
  releaseEvidence();
  await evidenceResponse;
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
});
