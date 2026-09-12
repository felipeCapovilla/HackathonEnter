# Protótipo visual da main

Esta aplicação preserva a tela de caso adicionada à `main` em `83c80b5b`.
Os dados em `src/data/mock.js` são exemplos estáticos; o botão de decisão muda
apenas o estado local e não persiste decisões na API.

A aplicação funcional conectada ao backend fica em `../frontend/`.
Este demonstrador não é iniciado pelos comandos `make frontend` ou `make api`.

Para inspecionar o desenho separadamente, execute nesta pasta:

```powershell
npm ci
npm run dev
```

O contrato ilustrado vem de `contracts/schema.py` e `src.policy.engine.decidir`.
A API documental usa `src.policy.engine.PolicyEngine`; esta reorganização
preserva ambos os contratos sem alterar a política escolhida pela API.
