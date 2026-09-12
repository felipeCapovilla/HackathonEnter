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

