# Arquitetura e critérios

## Fonte única de decisão

`src/policy` preserva o motor Grupo 9: regras para casos claros e XGBoost apenas na zona intermediária. `backend/app/policy_service.py` é o único adaptador entre documentos e motor. Um documento só torna uma feature verdadeira quando está com extração concluída e `CONFIRMED` ou `USER_CONFIRMED`; nome de arquivo e declaração do usuário não bastam.

## Documentos extensos

O upload é gravado em blocos de 1 MiB. PDFs são extraídos página a página e persistidos em lotes de 100, sem formar uma lista de todas as páginas na etapa de processamento. A validação de tipo usa no máximo 100 mil caracteres extraídos. O servidor deve mover esse trabalho para workers com fila e armazenamento de objetos antes de aceitar documentos de milhares de páginas em produção.

## Estados e intervenção humana

- `CONFIRMED`: sinais determinísticos confirmam o tipo declarado.
- `UNCONFIRMED`: não há evidência suficiente; não ativa feature.
- `MISMATCH`: há evidência forte de outro tipo; o advogado deve reclassificar, remover ou continuar com ressalva.
- `USER_CONFIRMED`: continuação registrada pelo advogado; ativa feature com rastreabilidade.
- `REMOVED`: preserva a trilha de auditoria, mas não participa da política.

O advogado pode criar pedido de documento; o banco pode anexar a resposta, declarar indisponibilidade ou cancelar. Silêncio permanece rastreável como pedido aberto.

## Limites atuais

Não há OCR, classificação semântica, RAG, LLM nem autenticação nesta entrega. A avaliação de conteúdo além da identificação de tipo é deliberadamente futura: deverá retornar fatos estruturados com citação de página, confiança, validação cruzada entre documentos e revisão humana. Nunca deverá aceitar instruções presentes nos autos como instruções do sistema.

## Critérios para produção

1. Testes de contrato API e auditoria de cada feature até o documento/página de origem.
2. Evals separados para OCR, tipagem, extração factual, política e aderência.
3. Política e modelo versionados, com dados de treinamento, hash, métricas, aprovação jurídica e rollback.
4. Observabilidade de fila, latência por página, erros de extração, taxa de confirmação e divergência advogado-política.
5. Segurança de dados jurídicos: RBAC, segregação por cliente, criptografia, retenção, exclusão e logs imutáveis.
