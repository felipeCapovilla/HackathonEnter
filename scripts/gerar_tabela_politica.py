"""
Gera artefatos/politica_segmentos.json a partir da base histórica de sentenças.

É a fonte única dos números da política: probabilidade de derrota por
segmento, ajuste por UF, quanto se paga ao perder e a faixa observada nos
acordos. Rodar de novo com a base de outro cliente recalibra os números sem
mudar código. A ESTRUTURA dos segmentos (contrato x extrato x comprovante x
golpe/genérico) continua fixa; descobrir outra estrutura é outro projeto.

Uso:
    python scripts/gerar_tabela_politica.py
    python scripts/gerar_tabela_politica.py --xlsx data/Hackaton_Enter_Base_Candidatos.xlsx
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAIDA_PADRAO = ROOT / "artefatos" / "politica_segmentos.json"

# UFs agrupadas pela taxa histórica de derrota: as 6 maiores formam "alto",
# as 8 menores "baixo". Cruzar as 26 UFs com os 16 segmentos daria células
# pequenas demais para uma taxa estável.
N_UF_ALTO, N_UF_BAIXO = 6, 8
PERDAS_COM_CONDENACAO = ("Parcial procedência", "Procedência")


def linhas_csv(resultados: Path, subsidios: Path) -> Iterator[tuple[dict, dict]]:
    with open(subsidios, encoding="utf-8") as arquivo:
        subs = {r["Número do processos"]: r for r in csv.DictReader(arquivo)}
    with open(resultados, encoding="utf-8") as arquivo:
        for r in csv.DictReader(arquivo):
            yield r, subs[r["Número do processo"]]


def linhas_xlsx(caminho: Path) -> Iterator[tuple[dict, dict]]:
    import openpyxl

    planilha = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    sub_linhas = list(planilha["Subsídios disponibilizados"].iter_rows(values_only=True))
    cabecalho_sub = sub_linhas[1]  # a primeira linha da aba é uma legenda
    subs = {str(linha[0]): dict(zip(cabecalho_sub, linha)) for linha in sub_linhas[2:]}
    resultados = planilha["Resultados dos processos"].iter_rows(values_only=True)
    cabecalho = next(resultados)
    for linha in resultados:
        r = dict(zip(cabecalho, linha))
        yield r, subs[str(r["Número do processo"])]


def _quantil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return round(ordenados[min(len(ordenados) - 1, int(p * len(ordenados)))], 4)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def gerar(linhas: Iterable[tuple[dict, dict]]) -> dict:
    segmentos: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    por_uf: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    razao_perda: dict[str, list[float]] = defaultdict(list)
    razao_acordo: list[float] = []
    total = perdas = 0

    for r, s in linhas:
        flag = lambda coluna: int(float(s[coluna]))
        valor_causa = float(r["Valor da causa"])
        condenacao = float(r["Valor da condenação/indenização"])
        perdeu = int(r["Resultado macro"] == "Não Êxito")
        sub = "Golpe" if r["Sub-assunto"] == "Golpe" else "Generico"
        chave = (flag("Contrato"), flag("Extrato"), flag("Comprovante de crédito"), sub)

        segmentos[chave][0] += 1
        segmentos[chave][1] += perdeu
        por_uf[str(r["UF"])][0] += 1
        por_uf[str(r["UF"])][1] += perdeu
        total += 1
        perdas += perdeu
        if valor_causa > 0 and r["Resultado micro"] in PERDAS_COM_CONDENACAO:
            razao_perda[r["Resultado micro"]].append(condenacao / valor_causa)
        if valor_causa > 0 and r["Resultado micro"] == "Acordo":
            razao_acordo.append(condenacao / valor_causa)

    taxa_uf = {uf: p / n for uf, (n, p) in por_uf.items()}
    ordem = sorted(taxa_uf, key=lambda uf: (-taxa_uf[uf], uf))
    alto, baixo = set(ordem[:N_UF_ALTO]), set(ordem[-N_UF_BAIXO:])
    clusters = {uf: "alto" if uf in alto else "baixo" if uf in baixo else "medio" for uf in sorted(ordem)}
    global_ = perdas / total
    offsets = {}
    for grupo in ("alto", "medio", "baixo"):
        n = sum(por_uf[uf][0] for uf, c in clusters.items() if c == grupo)
        p = sum(por_uf[uf][1] for uf, c in clusters.items() if c == grupo)
        offsets[grupo] = round(_logit(p / n) - _logit(global_), 4)

    todas_perdas = [v for lista in razao_perda.values() for v in lista]
    dados = {
        "n_processos": total,
        "p_perda_global": round(global_, 4),
        "segmentos": [
            {"contrato": k[0], "extrato": k[1], "comprovante": k[2], "sub_assunto": k[3],
             "n": n, "p_perda": round(p / n, 4)}
            for k, (n, p) in sorted(segmentos.items())
        ],
        "uf": {
            "regra": f"{N_UF_ALTO} maiores taxas de derrota = alto; {N_UF_BAIXO} menores = baixo; demais = medio",
            "clusters": clusters,
            "offset_logit": offsets,
        },
        "condenacao_sobre_causa_se_perde": {
            "n": len(todas_perdas),
            "media": round(sum(todas_perdas) / len(todas_perdas), 4),
            "procedencia": round(sum(razao_perda["Procedência"]) / len(razao_perda["Procedência"]), 4),
            "parcial_procedencia": round(
                sum(razao_perda["Parcial procedência"]) / len(razao_perda["Parcial procedência"]), 4),
        },
        "acordo_sobre_causa": {
            "n": len(razao_acordo),
            "media": round(sum(razao_acordo) / len(razao_acordo), 4),
            "p25": _quantil(razao_acordo, 0.25),
            "mediana": _quantil(razao_acordo, 0.50),
            "p75": _quantil(razao_acordo, 0.75),
            "p90": _quantil(razao_acordo, 0.90),
        },
    }
    assinatura = hashlib.sha256(json.dumps(dados, sort_keys=True).encode()).hexdigest()[:10]
    return {"versao": f"base-{total}-{assinatura}", **dados}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resultados", type=Path, default=ROOT / "data" / "resultados.csv")
    parser.add_argument("--subsidios", type=Path, default=ROOT / "data" / "subsidios.csv")
    parser.add_argument("--xlsx", type=Path, default=None)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args()

    linhas = linhas_xlsx(args.xlsx) if args.xlsx else linhas_csv(args.resultados, args.subsidios)
    artefato = gerar(linhas)
    artefato["gerado_em"] = datetime.now(UTC).isoformat(timespec="seconds")
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(artefato, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.saida.relative_to(ROOT)}: {artefato['versao']}, {len(artefato['segmentos'])} segmentos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
