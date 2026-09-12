from typing import TypedDict

class GraphState(TypedDict):

    caminho_pdf: str          # Entrada: Onde procurar o PDF
    docie_existe: bool        # Gerado pelo Nó 1: Diz se o arquivo estava lá
    parecer_geral: str        # Gerado pelo Nó 1: Conformidade ou não-conformidade
    recomendacao: str