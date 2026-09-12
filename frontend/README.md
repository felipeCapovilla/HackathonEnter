# Frontend EnterAgree

Interface React/Vite para o fluxo do advogado: criar caso, enviar subsídios, acompanhar o processamento, executar a análise da política, registrar a decisão e visualizar indicadores básicos de aderência.

## Executar

```powershell
cd frontend
npm install
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
- `POST /cases/{case_id}/documents` (multipart: `file`, `declared_type`, `source_party`)
- `POST /documents/{document_id}/type-confirmation`
- `POST /cases/{case_id}/analyses`
- `POST /cases/{case_id}/lawyer-decisions?analysis_id={analysis_id}`
- `POST /cases/{case_id}/document-requests`
- `POST /document-requests/{request_id}/response`
- `GET /monitoring`

Os payloads seguem `backend/app/schemas.py`. Não há dados simulados nem persistência no navegador: se a API estiver indisponível, a tela apresenta o erro retornado e não altera o estado exibido. Após cada mutação, ela recarrega o detalhe do caso e o monitoramento. Documentos em `UPLOADED` ou `EXTRACTING` são consultados novamente a cada dois segundos até atingirem um estado terminal.

## Validar produção estática

```powershell
npm run build
npm run preview
```
