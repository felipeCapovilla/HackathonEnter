"""
Gera artefatos/insights_base_historica.json: quanto custa, na base real, cada documento que falta.

Duas leituras por documento:
  - bruta: taxa de derrota e valor pago nos casos sem o documento (correlação, contexto);
  - valor em jogo: (P(derrota) sem o doc - P(derrota) com o doc) x condenação média x chance de recuperar,
    pela tabela de segmentos. Só existe para contrato, extrato e comprovante, os que entram na política.

Uso: python -m scripts.gerar_insights_base
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.policy import table
from src.policy.artefato import carregar
from src.policy.constants import P4, RATIO_CONDENACAO

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SAIDA = ROOT / "artefatos" / "insights_base_historica.json"

DOCUMENTOS = (
    ("CONTRATO", "Contrato", "contrato"),
    ("EXTRATO", "Extrato", "extrato"),
    ("COMPROVANTE_CREDITO", "Comprovante de crédito", "comprovante"),
    ("DEMONSTRATIVO_DIVIDA", "Demonstrativo de evolução da dívida", None),
    ("DOSSIE", "Dossiê", None),
    ("LAUDO_REFERENCIADO", "Laudo referenciado", None),
)
CRITICOS = ("contrato", "extrato", "comprovante")


def _linhas() -> list[dict]:
    with open(DATA / "subsidios.csv", encoding="utf-8") as arquivo:
        subsidios = {r["Número do processos"]: r for r in csv.DictReader(arquivo)}
    linhas = []
    with open(DATA / "resultados.csv", encoding="utf-8") as arquivo:
        for r in csv.DictReader(arquivo):
            s = subsidios[r["Número do processo"]]
            flag = lambda coluna: bool(int(float(s[coluna])))
            linhas.append({
                "uf": r["UF"], "sub_assunto": "Golpe" if r["Sub-assunto"] == "Golpe" else "Generico",
                "causa": float(r["Valor da causa"]), "pago": float(r["Valor da condenação/indenização"] or 0),
                "perdeu": r["Resultado macro"] != "Êxito",
                "Contrato": flag("Contrato"), "Extrato": flag("Extrato"),
                "Comprovante de crédito": flag("Comprovante de crédito"), "Dossiê": flag("Dossiê"),
                "Demonstrativo de evolução da dívida": flag("Demonstrativo de evolução da dívida"),
                "Laudo referenciado": flag("Laudo referenciado"),
            })
    return linhas


def valor_em_jogo(flags: dict[str, bool], documento: str, sub_assunto: str, uf: str, causa: float) -> float:
    """Ganho esperado de recuperar `documento` num caso em que ele falta."""
    if flags[documento]:
        return 0.0
    com = {**flags, documento: True}
    delta = (table.p_perda(flags["contrato"], flags["extrato"], flags["comprovante"], sub_assunto, uf)
             - table.p_perda(com["contrato"], com["extrato"], com["comprovante"], sub_assunto, uf))
    return max(0.0, delta) * RATIO_CONDENACAO.valor * causa * P4.valor


def gerar() -> dict:
    linhas = _linhas()
    n = len(linhas)
    documentos = []
    for tipo, nome, critico in DOCUMENTOS:
        com = [x for x in linhas if x[nome]]
        sem = [x for x in linhas if not x[nome]]
        derrota = lambda grupo: sum(x["perdeu"] for x in grupo) / len(grupo) if grupo else 0.0
        jogo = None
        if critico:
            jogo = sum(valor_em_jogo({"contrato": x["Contrato"], "extrato": x["Extrato"],
                                      "comprovante": x["Comprovante de crédito"]},
                                     critico, x["sub_assunto"], x["uf"], x["causa"]) for x in sem)
        documentos.append({
            "tipo": tipo, "nome": nome, "casos_sem": len(sem), "ausente_pct": round(len(sem) / n, 4),
            "derrota_com": round(derrota(com), 4), "derrota_sem": round(derrota(sem), 4),
            "pago_nos_casos_sem": round(sum(x["pago"] for x in sem), 2),
            "muda_resultado": abs(derrota(sem) - derrota(com)) >= 0.05,
            "valor_em_jogo": round(jogo, 2) if jogo is not None else None,
        })
    nenhum = [x for x in linhas if not x["Contrato"] and not x["Extrato"]]
    return {
        "versao": carregar()["versao"],
        "casos": n,
        "pago_total": round(sum(x["pago"] for x in linhas), 2),
        "documentos": documentos,
        "sem_contrato_e_extrato": {
            "casos": len(nenhum), "pct": round(len(nenhum) / n, 4),
            "derrota": round(sum(x["perdeu"] for x in nenhum) / len(nenhum), 4),
            "pago": round(sum(x["pago"] for x in nenhum), 2),
        },
        "premissas": (f"Valor em jogo = (P(derrota) sem o documento − com ele) pela tabela de segmentos × "
                      f"condenação média ({RATIO_CONDENACAO.valor:.2%} da causa) × chance de recuperar ({P4.valor:.0%}). "
                      "O valor pago nos casos sem o documento é correlação: parte deles é golpe real, sem documento que exista."),
    }


def main() -> None:
    resultado = gerar()
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{SAIDA.relative_to(ROOT)}: {resultado['casos']} casos")
    for d in resultado["documentos"]:
        print(f"  {d['nome']:38s} falta {d['ausente_pct']:.1%}  em jogo {d['valor_em_jogo']}")


if __name__ == "__main__":
    main()
