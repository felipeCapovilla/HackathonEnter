"""
Backtest da política sobre as 60.000 sentenças reais.

METODOLOGIA — leia antes de citar qualquer número destes:

  baseline  = o que o banco EFETIVAMENTE pagou (R$ 192.982.862,07 observados),
              mais os honorários do desfecho quando um contrato é informado
  política  = custo por caso sob a ação recomendada, onde:
              DEFENDER  -> condenação OBSERVADA (defender foi o que de fato
                           aconteceu, então o desfecho real vale)
              ACORDAR   -> aceitação x alvo + (1 - aceitação) x condenação observada
              RECUPERAR -> recuperabilidade x melhor opção no segmento melhorado
                           + (1 - recuperabilidade) x o acordo/defesa de hoje

  ACORDAR e RECUPERAR são MODELADOS, não observados: não existe contrafactual
  de oferta recusada na base. Os valores não levam juros (a base registra a
  condenação na sentença); o custo do tempo afeta a decisão, não o baseline.

  "com_extracao_ia" ASSUME que todo dossiê presente periciou a assinatura do
  contrato. É um teto para a terceira via, não um resultado observado.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from contracts.schema import AnaliseDossie, CaseFeatures, ParametrosContrato
from src.policy import constants as K
from src.policy.engine import decidir

DATA = Path(__file__).resolve().parents[2] / "data"


def carregar(com_extracao_ia: bool = True) -> list[tuple[CaseFeatures, float]]:
    """Devolve (features, condenação observada)."""
    with open(DATA / "subsidios.csv", encoding="utf-8") as arquivo:
        subs = {r["Número do processos"]: r for r in csv.DictReader(arquivo)}
    out = []
    with open(DATA / "resultados.csv", encoding="utf-8") as arquivo:
        for r in csv.DictReader(arquivo):
            s = subs[r["Número do processo"]]
            b = lambda k: bool(int(float(s[k])))
            tem_dossie = b("Dossiê")
            out.append((
                CaseFeatures(
                    numero_processo=r["Número do processo"], uf=r["UF"],
                    sub_assunto="Golpe" if r["Sub-assunto"] == "Golpe" else "Generico",
                    valor_causa=float(r["Valor da causa"]),
                    contrato=b("Contrato"), extrato=b("Extrato"),
                    comprovante_credito=b("Comprovante de crédito"), dossie=tem_dossie,
                    demonstrativo=b("Demonstrativo de evolução da dívida"),
                    laudo=b("Laudo referenciado"),
                    analise_dossie=(AnaliseDossie(veredito="conforme", analisou_assinatura_contrato=True)
                                    if (tem_dossie and com_extracao_ia) else None),
                ),
                float(r["Valor da condenação/indenização"]),
            ))
    return out


@dataclass
class Resultado:
    n: int
    baseline: float
    custo_politica: float
    por_acao: dict[str, int]

    @property
    def economia(self) -> float:
        return self.baseline - self.custo_politica

    @property
    def pct(self) -> float:
        return self.economia / self.baseline if self.baseline else 0.0


def _honorario_do_desfecho(c: CaseFeatures, condenacao: float, contrato: ParametrosContrato | None) -> float:
    if contrato is None:
        return 0.0
    if condenacao > 0:
        return contrato.honorario_defesa_perdida.em_reais(c.valor_causa, condenacao)
    return contrato.honorario_defesa_ganha.em_reais(c.valor_causa, K.P1.valor * c.valor_causa)


def custo_sem_politica(c: CaseFeatures, condenacao: float, contrato: ParametrosContrato | None = None) -> float:
    """Status quo: o caso é defendido e o banco paga a condenação e o honorário do desfecho."""
    return condenacao + _honorario_do_desfecho(c, condenacao, contrato)


def custo_realizado(c: CaseFeatures, condenacao: float, r, p_aceita: float, p_recupera: float,
                    contrato: ParametrosContrato | None = None) -> float:
    """Custo de um caso sob a recomendação `r`, com os honorários do contrato."""
    defesa = custo_sem_politica(c, condenacao, contrato)
    honorario_acordo = (contrato.honorario_acordo.em_reais(c.valor_causa, K.P1.valor * c.valor_causa)
                        if contrato else 0.0)
    acordo_hoje = (p_aceita * (r.acordo.alvo + honorario_acordo) + (1 - p_aceita) * defesa) if r.acordo else defesa
    if r.acao == "DEFENDER":
        return defesa
    if r.acao == "ACORDAR":
        return acordo_hoje
    esperado_recuperado = r.recuperacao.p_perda_se_recuperado * K.P1.valor * c.valor_causa
    recuperado = (min(esperado_recuperado, r.acordo.abertura + honorario_acordo)
                  if r.acordo else esperado_recuperado)
    return p_recupera * recuperado + (1 - p_recupera) * acordo_hoje


def rodar(casos, p_aceita: float, p_recupera: float, contrato: ParametrosContrato | None = None) -> Resultado:
    baseline = total = 0.0
    por_acao: dict[str, int] = defaultdict(int)
    for c, condenacao in casos:
        baseline += custo_sem_politica(c, condenacao, contrato)
        r = decidir(c, contrato)
        por_acao[r.acao] += 1
        total += custo_realizado(c, condenacao, r, p_aceita, p_recupera, contrato)
    return Resultado(len(casos), baseline, total, dict(por_acao))


def calibracao(casos) -> list[tuple[str, int, float, float]]:
    """P(derrota) prevista vs observada por segmento — a prova de acurácia."""
    agg = defaultdict(lambda: [0, 0, 0.0])
    for c, condenacao in casos:
        r = decidir(c)
        a = agg[r.segmento]
        a[0] += 1
        a[1] += 1 if condenacao > 0 else 0
        a[2] += r.p_perda
    return sorted((seg, n, prev / n, perdas / n) for seg, (n, perdas, prev) in agg.items())


if __name__ == "__main__":
    for rotulo, ia in (("COM leitura do dossiê (teto: todo dossiê periciou o contrato)", True),
                       ("SEM leitura do dossiê (só as flags)", False)):
        casos = carregar(com_extracao_ia=ia)
        print(f"\n{'=' * 78}\n{rotulo}\n{'=' * 78}")
        base = rodar(casos, K.P3.valor, K.P4.valor)
        print(f"  baseline observado : R$ {base.baseline:,.2f}")
        print(f"  distribuição       : {base.por_acao}")
        print(f"\n  {'aceitação':>10s} {'recuperação':>12s} {'custo política':>18s} {'economia':>16s} {'%':>7s}")
        for pa in (0.30, 0.40, 0.60):
            for pr in (0.50, 0.70):
                x = rodar(casos, pa, pr)
                marca = "  <- premissas atuais" if (pa == K.P3.valor and pr == K.P4.valor) else ""
                print(f"  {pa:10.0%} {pr:12.0%} {x.custo_politica:18,.0f} {x.economia:16,.0f} {x.pct:6.1%}{marca}")
