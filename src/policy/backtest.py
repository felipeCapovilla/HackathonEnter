"""
Backtest da política sobre as 60.000 sentenças reais.

METODOLOGIA — leia antes de citar qualquer número destes:

  baseline  = o que o banco EFETIVAMENTE pagou (R$ 192.982.862,07 observados)
  política  = custo por caso sob a ação recomendada, onde:
              DEFENDER  -> condenação OBSERVADA (defender foi o que de fato
                           aconteceu, então o desfecho real vale)
              ACORDAR   -> P3 x oferta alvo + (1-P3) x condenação observada
              RECUPERAR -> P4 x custo esperado no segmento melhorado
                           + (1-P4) x melhor alternativa restante

  As duas últimas são MODELADAS, não observadas — não existe contrafactual de
  oferta recusada na base. Por isso todo número sai com curva de sensibilidade.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from contracts.schema import AnaliseDossie, CaseFeatures
from src.policy import constants as K
from src.policy.engine import custo_esperado_defesa, decidir

DATA = Path(__file__).resolve().parents[2] / "data"


def carregar(com_extracao_ia: bool = True) -> list[tuple[CaseFeatures, float]]:
    """Devolve (features, condenação observada). com_extracao_ia liga o sinal
    de recuperabilidade que só existe lendo o PDF do dossiê."""
    subs = {r["Número do processos"]: r for r in csv.DictReader(open(DATA / "subsidios.csv"))}
    out = []
    for r in csv.DictReader(open(DATA / "resultados.csv")):
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
                analise_dossie=(AnaliseDossie(veredito="conforme",
                                              analisou_assinatura_contrato=True)
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


def rodar(casos, p_aceita: float, p_recupera: float, sucumbencia: float) -> Resultado:
    K.P3.__dict__  # premissas são frozen; variação entra por parâmetro
    baseline = total = 0.0
    por_acao: dict[str, int] = {}

    for c, cond_obs in casos:
        baseline += cond_obs
        r = decidir(c)
        por_acao[r.acao] = por_acao.get(r.acao, 0) + 1
        cond_real = cond_obs * (1 + sucumbencia)

        if r.acao == "DEFENDER":
            custo = cond_real
        elif r.acao == "ACORDAR":
            custo = p_aceita * r.acordo.alvo + (1 - p_aceita) * cond_real
        else:  # RECUPERAR
            melhor = custo_esperado_defesa(c.valor_causa, r.recuperacao.p_perda_se_recuperado)
            alternativa = min(cond_real, (r.acordo.alvo if r.acordo else cond_real))
            custo = p_recupera * melhor + (1 - p_recupera) * alternativa
        total += custo

    return Resultado(len(casos), baseline, total, por_acao)


def calibracao(casos) -> list[tuple[str, int, float, float]]:
    """P(derrota) prevista vs observada por segmento — a prova de acurácia."""
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0, 0.0])
    for c, cond in casos:
        r = decidir(c)
        a = agg[r.segmento]
        a[0] += 1
        a[1] += 1 if cond > 0 else 0
        a[2] += r.p_perda
    return sorted((seg, n, prev / n, perdas / n) for seg, (n, perdas, prev) in agg.items())


if __name__ == "__main__":
    for rotulo, ia in (("COM extração de IA (lê o dossiê)", True), ("SEM extração (só as flags)", False)):
        casos = carregar(com_extracao_ia=ia)
        print(f"\n{'='*78}\n{rotulo}\n{'='*78}")
        base = rodar(casos, K.P3.valor, K.P4.valor, 0.0)
        print(f"  baseline observado : R$ {base.baseline:,.2f}")
        print(f"  distribuição       : {base.por_acao}")
        print(f"\n  {'P(aceita)':>10s} {'P(recupera)':>12s} {'custo política':>18s} {'economia':>16s} {'%':>7s}")
        for pa in (0.30, 0.40, 0.60):
            for pr in (0.50, 0.70):
                x = rodar(casos, pa, pr, 0.0)
                marca = "  <- premissas atuais" if (pa == 0.40 and pr == 0.70) else ""
                print(f"  {pa:10.0%} {pr:12.0%} {x.custo_politica:18,.0f} {x.economia:16,.0f} {x.pct:6.1%}{marca}")
        if ia:
            print("\n  CALIBRAÇÃO (prevista vs observada):")
            pior = 0.0
            for seg, n, prev, obs in calibracao(casos):
                pior = max(pior, abs(prev - obs))
                print(f"    {seg:24s} n={n:6d}  prevista {prev:6.1%}  observada {obs:6.1%}  erro {prev-obs:+6.2%}")
            print(f"    -> erro absoluto máximo: {pior:.2%}")
