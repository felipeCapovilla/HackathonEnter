/*
 * Mock com a MESMA forma de contracts/schema.py (Recomendacao + CaseFeatures).
 * Trocar por fetch('/api/casos') não deve exigir mudar nenhum componente.
 * Números vindos do motor real (src/policy/engine.py) sobre os casos-exemplo.
 */
export const CASOS = [
  {
    numero_processo: '0654321-09.2024.8.04.0001',
    autor: 'José Raimundo Oliveira Costa', uf: 'AM', sub_assunto: 'Golpe',
    valor_causa: 15000,
    subsidios: { contrato: false, extrato: false, comprovante_credito: true,
                 dossie: true, demonstrativo: true, laudo: true },
    analise_dossie: { veredito: 'conforme', analisou_assinatura_contrato: true },
    recomendacao: {
      acao: 'RECUPERAR', gate_defesa_disponivel: false,
      gate_motivo: 'Sem contrato e sem extrato o banco não satisfaz o ônus probatório do art. 373, II do CPC. Segmento com 2,7% de êxito histórico.',
      segmento: 'C0 E0 CC1 Golpe', p_perda: 0.99, custo_esperado_defesa: 12295.8,
      acordo: { abertura: 4650, alvo: 5250, maximo_aceitavel: 5250, teto_absoluto: 6000 },
      recuperacao: { documento: 'contrato', confianca: 'alta',
        fundamento: 'O dossiê periciou a assinatura aposta no instrumento contratual: o contrato existe e não foi juntado.',
        ganho_estimado: 3373.05, p_perda_se_recuperado: 0.602 },
      justificativa: [
        'Gate fechado: sem contrato e sem extrato o ônus do art. 373, II do CPC não é satisfeito.',
        'Segmento C0 E0 CC1 Golpe: P(derrota) 99,0% em 2.158 casos observados.',
        'O dossiê referencia perícia de assinatura no contrato nº 603827451 — o documento existiu.',
        'Autos alegam crédito depositado em conta da Caixa que o autor declara não possuir; o banco não juntou extrato que contradiga.',
      ],
      premissas_usadas: ['P1', 'P3', 'P4', 'P6'],
    },
  },
  {
    numero_processo: '0801234-56.2024.8.10.0001',
    autor: 'Maria das Graças Silva Pereira', uf: 'MA', sub_assunto: 'Generico',
    valor_causa: 15000,
    subsidios: { contrato: true, extrato: true, comprovante_credito: true,
                 dossie: true, demonstrativo: true, laudo: true },
    analise_dossie: { veredito: 'conforme', analisou_assinatura_contrato: true },
    recomendacao: {
      acao: 'DEFENDER', gate_defesa_disponivel: true, gate_motivo: 'Prova mínima presente.',
      segmento: 'C1 E1 CC1 Generico', p_perda: 0.018, custo_esperado_defesa: 224.86,
      acordo: null, recuperacao: null,
      justificativa: [
        'Prova mínima presente: contrato, extrato e comprovante BACEN.',
        'Segmento C1 E1 CC1 Genérico: P(derrota) 1,8% em 9.351 casos observados.',
        'Extrato mostra o crédito de R$ 5.000 em 12/05/2022, TED para conta de titularidade da autora em 13/05 e PIX a familiar em 15/05 — contradiz a alegação de que jamais recebeu os valores.',
        'Defesa é o caminho mais barato: R$ 224,86 de custo esperado.',
      ],
      premissas_usadas: ['P1', 'P3', 'P6'],
    },
  },
]

export const ROTULO_SUBSIDIO = {
  contrato: 'Contrato', extrato: 'Extrato', comprovante_credito: 'Comprovante BACEN',
  dossie: 'Dossiê', demonstrativo: 'Evolução da dívida', laudo: 'Laudo referenciado',
}
/* Dossiê e Laudo não movem o resultado (Δ +0,03pp e +0,19pp em 60k casos).
   A tela diz isso em vez de fingir que todo documento pesa igual. */
export const SEM_PESO = new Set(['dossie', 'laudo'])
export const brl = (v) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
