# Frontend EnterAgree

Interface React/Vite para o fluxo do advogado: criar caso, enviar subsídios, acompanhar o processamento, executar a análise da política, registrar a decisão e visualizar indicadores básicos de aderência. Requer Node.js 20.19+ na linha 20 ou Node.js 22.12+.

## Executar

```powershell
cd src/interface/frontend
npm ci
npm run dev
```

O Vite exibirá a URL local, normalmente `http://localhost:5173`.

## API esperada

Por padrão, o cliente consome `http://localhost:8000/api`. Altere com uma variável de ambiente antes de iniciar:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000/api"
npm run dev
```

Rotas utilizadas:

- `GET /cases`
- `POST /cases`
- `GET /cases/{case_id}`
- `POST /cases/{case_id}/documents` (multipart: `file`, `declared_type`, `source_party`, `request_id` opcional)
- `POST /documents/{document_id}/type-confirmation`
- `POST /cases/{case_id}/analyses`
- `POST /cases/{case_id}/lawyer-decisions?analysis_id={analysis_id}`
- `POST /cases/{case_id}/document-requests`
- `POST /document-requests/{request_id}/response`
- `GET /monitoring`

Os payloads seguem `src/interface/backend/schemas.py`. Não há dados simulados nem persistência no navegador: se a API estiver indisponível, a tela apresenta o erro retornado. Após cada mutação, ela recarrega o detalhe do caso e o monitoramento. Documentos em `UPLOADED` ou `EXTRACTING` são consultados novamente a cada dois segundos até atingirem um estado terminal. Ao trocar de caso, respostas pendentes do caso anterior não substituem o caso selecionado. Pedidos de documentos permanecem abertos como `REQUESTED`, sem vencimento; ao vincular o upload a um pedido, o tipo declarado acompanha o documento solicitado.

## Validar produção estática

```powershell
npm run build
npm run preview
```

## Regressões no navegador

```powershell
npx playwright install chromium
npm run test:e2e
```

Para usar Chrome já instalado, defina `$env:PLAYWRIGHT_CHROMIUM_CHANNEL = "chrome"` antes do comando de teste. A suíte compila a aplicação e executa o bundle de produção na porta 4173. As respostas HTTP são controladas somente nos testes para reproduzir validação de entrada, respostas atrasadas, upload vinculado a pedido e atualização de processamento durante o preenchimento de formulários. O teste de integração com o backend deve ser executado separadamente, com a API configurada em `VITE_API_BASE_URL`.
