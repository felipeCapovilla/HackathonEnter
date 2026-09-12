"""State exchanged by the optional dossier workflow."""

from typing import Literal, TypedDict

from contracts.dossie import DossieReport
from contracts.schema import AnaliseDossie, CaseFeatures, Recomendacao


class GraphState(TypedDict, total=False):
    caminho_pdf: str
    dossie_texto: str
    features: CaseFeatures
    analise_revisada: bool
    dossie_resultado: DossieReport
    analise_dossie: AnaliseDossie
    recomendacao: Recomendacao | None
    encaminhamento: Literal["AUSENTE", "REVISAO_MANUAL", "POLITICA_CALCULADA", "POLITICA_COM_RESSALVA"]
