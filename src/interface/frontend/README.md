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
- `POST /documents/{document_id}/dossie-analysis`
- `GET /documents/{document_id}/dossie-analysis` (carregamento sob demanda das evidências)
- `GET /documents/{document_id}/pages/{page_number}` (texto da página referenciada em evidência)
- `POST /cases/{case_id}/analyses`
- `POST /cases/{case_id}/lawyer-decisions?analysis_id={analysis_id}`
- `POST /cases/{case_id}/document-requests`
- `POST /document-requests/{request_id}/response`
- `GET /monitoring`

Os payloads seguem `src/interface/backend/schemas.py`. Não há dados simulados nem persistência no navegador: se a API estiver indisponível, a tela apresenta o erro retornado. Após cada mutação, ela recarrega o detalhe do caso e o monitoramento. Documentos em `UPLOADED` ou `EXTRACTING` são consultados novamente a cada dois segundos até atingirem um estado terminal. Ao trocar de caso, respostas pendentes do caso anterior não substituem o caso selecionado. Pedidos de documentos permanecem abertos como `REQUESTED`, sem vencimento; ao vincular o upload a um pedido, o tipo declarado acompanha o documento solicitado.

## Análise auxiliar de dossiês

Cada documento declarado como `DOSSIE`, com extração concluída e sem divergência de tipo pendente, oferece o botão **Analisar dossiê com IA**. O aviso anterior ao botão informa o envio do texto à OpenAI; nenhuma análise LLM é iniciada automaticamente. A presença e a classificação documental continuam determinísticas. O detalhe do caso inclui `dossie_analyses`, permitindo recuperar resultados persistidos ao voltar ao processo; o backend também disponibiliza `GET /documents/{document_id}/dossie-analysis` para consulta direta.

O detalhe do caso transporta somente o resumo mais recente por documento, com `evidencias_total` e `evidencias_carregadas: false`, sem os trechos. **Carregar evidências** consulta o resultado completo sob demanda, sem repetir a análise LLM. Atualizações periódicas do mesmo registro preservam as evidências já carregadas e atualizam avisos e cobertura; uma nova análise invalida a cópia anterior. Falhas de carregamento preservam o resumo e permitem tentar novamente.

A tela mostra veredito, assinatura examinada, contrato referenciado, índices reportados em percentuais, cobertura, avisos e trechos com links para suas páginas. O campo `assinatura_contrato_status` distingue afirmação, negação explícita, desconhecimento e conflito: a ausência de confirmação não prova que a assinatura não foi periciada. Confiança de extração não representa confiança jurídica. Extração incompleta e falhas são explicitadas; durante a chamada o botão fica desabilitado e respostas de processos que já não estão selecionados são descartadas. Documentos removidos ou reclassificados para outro tipo não exibem análise de dossiê ativa. O resultado auxilia a revisão humana, sem autenticar documentos ou modificar automaticamente a recomendação G9/XGBoost.

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
