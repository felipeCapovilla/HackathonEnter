# EnterAgree

Implementação enxuta da política híbrida do Grupo 9 para acordos de não reconhecimento de empréstimo. A API compõe regras determinísticas, o artefato XGBoost reproduzido e evidência documental auditável.

## Executar

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
```

Em outro terminal:

```powershell
cd frontend
npm install
npm run dev
```

A API atende em `http://localhost:8000` e a interface usa `http://localhost:5173`.

## Fluxo implementado

1. O advogado cria um caso e o banco ou advogado envia um PDF/TXT com o tipo documental declarado.
2. O upload é persistido por streaming, o texto é extraído em lotes de 100 páginas e o tipo declarado é conferido por sinais determinísticos, sem LLM.
3. Tipos confirmados ativam exclusivamente as variáveis do motor de política; incompatibilidades exigem reclassificação, continuação com ressalva ou remoção.
4. A política registra recomendação, faixa de acordo, vetor de atributos, origem de cada atributo, limitações e decisão posterior do advogado.
5. O banco acompanha análises, decisões e aderência em `GET /api/monitoring`.

## Modelo e dados

`artefatos/modelo_xgboost.pkl` foi reproduzido pelos scripts originais do Grupo 9 a partir da base recebida. Para gerar novamente, disponibilize a planilha e execute:

```powershell
python scripts/01_prepare_data.py --input ..\Hackaton_Enter_Base_Candidatos.xlsx --output artefatos
python scripts/02_train_model.py --input artefatos
```

Na reprodução local: AUC de validação cruzada `0.9079 ± 0.0013`, AUC de teste `0.9045` e Brier `0.1027`. Esses números são retrospectivos e não constituem validação de produção.

## Limites e evolução

Esta entrega usa SQLite e tarefas em processo para demonstração. Produção requer armazenamento de objetos, fila de workers, banco transacional, autenticação/autorização, criptografia, antivírus, auditoria imutável e observabilidade. Páginas com pouco texto são sinalizadas; a métrica de qualidade e a etapa de OCR estão explicitamente pendentes. A extração semântica/RAG pode complementar, mas não substituir, a política e a confirmação determinística de tipo.

Consulte `docs/arquitetura.md` para contrato, estados e critérios de evolução.

## Feature planejada: acesso por perfil

O [plano de banco, advogado, admin global e login](docs/plano_acesso_banco_advogado_admin.md) define telas, permissões, sessões, migração, contratos e critérios de aceite para a próxima implementação. Nesta entrega, somente o documento foi criado; autenticação e áreas separadas ainda não estão implementadas.
