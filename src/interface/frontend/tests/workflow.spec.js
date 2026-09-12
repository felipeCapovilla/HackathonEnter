import { expect, test } from "@playwright/test";

function caseDetail(caseId) {
  return {
    case: { id: caseId, case_number: `processo-${caseId}`, uf: "SP", value_of_claim: 1000 },
    documents: [], analyses: [], lawyer_decisions: [], document_requests: [],
  };
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

test("production bundle renders and formats API validation errors", async ({ page }) => {
  const runtimeErrors = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await serveApi(page, {}, async (route, pathname, request) => {
    if (pathname !== "/api/cases" || request.method() !== "POST") return false;
    await route.fulfill({ status: 422, json: { detail: [{ msg: "UF inválida" }] } });
    return true;
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "EnterAgree", exact: true })).toBeVisible();
  await page.getByLabel("Número do processo").fill("processo-teste");
  await page.getByLabel("UF", { exact: true }).fill("ZZ");
  await page.getByRole("button", { name: "Criar caso", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("UF inválida");
  expect(runtimeErrors).toEqual([]);
});

test("late case response cannot replace the selected case", async ({ page }) => {
  const details = { first: caseDetail("first"), second: caseDetail("second") };
  let releaseFirst;
  const firstReady = new Promise((resolve) => { releaseFirst = resolve; });
  await serveApi(page, details, async (route, pathname) => {
    if (pathname !== "/api/cases/first") return false;
    await firstReady;
    await route.fulfill({ json: details.first });
    return true;
  });
  await page.goto("/");
  const firstRequest = page.waitForRequest("**/api/cases/first");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await firstRequest;
  await page.getByRole("button", { name: /processo-second/ }).click();
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
  const firstResponse = page.waitForResponse("**/api/cases/first");
  releaseFirst();
  await firstResponse;
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
});

test("finishing a mutation in another case preserves current selection", async ({ page }) => {
  const details = { first: caseDetail("first"), second: caseDetail("second") };
  let releaseAnalysis;
  const analysisReady = new Promise((resolve) => { releaseAnalysis = resolve; });
  await serveApi(page, details, async (route, pathname) => {
    if (pathname !== "/api/cases/first/analyses") return false;
    await analysisReady;
    await route.fulfill({ json: {} });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await page.getByRole("button", { name: "Executar análise" }).click();
  await page.getByRole("button", { name: /processo-second/ }).click();
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
  releaseAnalysis();
  await expect(page.getByRole("button", { name: "Executar análise" })).toBeEnabled();
  await expect(page.locator(".case-title h2")).toHaveText("processo-second");
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("request upload submits its document type and clears the completed selection", async ({ page }) => {
  const details = { first: caseDetail("first") };
  details.first.document_requests.push({
    id: "request-extrato", document_type: "EXTRATO", status: "REQUESTED", reason: "Conferir crédito",
  });
  let uploadBody;
  await serveApi(page, details, async (route, pathname, request) => {
    if (pathname !== "/api/cases/first/documents") return false;
    uploadBody = request.postData();
    details.first.document_requests[0].status = "SUBMITTED";
    await route.fulfill({ status: 201, json: { id: "document-extrato" } });
    return true;
  });
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await page.getByLabel("Pedido vinculado").selectOption("request-extrato");
  await expect(page.getByLabel("Tipo declarado")).toHaveValue("EXTRATO");
  await expect(page.getByLabel("Tipo declarado")).toBeDisabled();
  await page.getByLabel("Arquivo", { exact: true }).setInputFiles({
    name: "extrato.txt", mimeType: "text/plain", buffer: Buffer.from("Extrato bancário e saldo"),
  });
  await page.getByRole("button", { name: "Enviar documento" }).click();
  await expect(page.getByRole("status")).toContainText("Documento enviado");
  expect(uploadBody).toMatch(/name="request_id"\r\n\r\nrequest-extrato/);
  expect(uploadBody).toMatch(/name="declared_type"\r\n\r\nEXTRATO/);
  await expect(page.getByLabel("Pedido vinculado")).toHaveValue("");
  await expect(page.getByLabel("Tipo declarado")).toBeEnabled();
  await expect(page.getByLabel("Arquivo", { exact: true })).toHaveValue("");
});

test("processing refresh preserves a request being written", async ({ page }) => {
  const details = { first: caseDetail("first") };
  details.first.documents.push({
    id: "document-first", original_filename: "contrato.txt", declared_type: "CONTRATO",
    status: "EXTRACTING", pages_extracted: 0, page_count: 2,
  });
  await serveApi(page, details);
  await page.goto("/");
  await page.getByRole("button", { name: /processo-first/ }).click();
  await page.getByLabel("Hipótese", { exact: true }).fill("credito_na_conta");
  const refreshResponse = page.waitForResponse("**/api/cases/first");
  await refreshResponse;
  await expect(page.getByLabel("Hipótese", { exact: true })).toHaveValue("credito_na_conta");
});
