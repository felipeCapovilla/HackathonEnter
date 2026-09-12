from langgraph.graph import StateGraph, START, END
from state import GraphState

from tools.dossie_analyzer import analyze


def node_processar_arquivo(state: GraphState):
    print("-> Nó 1: Tentando ler e processar o arquivo PDF...")
    
    resultado = analyze(state["caminho_pdf"])
    
    return {
        "docie_existe": resultado.docie_existe,
        "parecer_geral": resultado.parecer_geral
    }

def node_verificar_parecer(state: GraphState):
    print("-> Nó 2: Arquivo encontrado! Verificando o parecer geral...")
    
    parecer = state["parecer_geral"]
    recomendacao_final = ""
    
    # Atualiza a recomendação com base no parecer
    if "não-conformidade" in parecer.lower():
         print("   [!] AÇÃO: O Dossiê apresentou NÃO-CONFORMIDADE. Recomendação: acordo.")
         recomendacao_final = "acordo"
    else:
         print("   [+] Tudo certo: Dossiê em CONFORMIDADE. Recomendação: prosseguir.")
         recomendacao_final = "prosseguir"
         
    # Retorna o dict atualizando a variável recomendacao no estado do grafo
    return {"recomendacao": recomendacao_final} 


def roteador_existe_dossie(state: GraphState):
    """Decide o caminho baseado na existência do dossiê"""
    if state.get("docie_existe") == True:
        return "caminho_existe"
    else:
        return "caminho_nao_existe"


workflow = StateGraph(GraphState)

# Adiciona os Nós
workflow.add_node("processar_arquivo", node_processar_arquivo)
workflow.add_node("verificar_parecer", node_verificar_parecer)

# Início -> Processar
workflow.add_edge(START, "processar_arquivo")

# Roteamento Condicional após tentar processar
workflow.add_conditional_edges(
    "processar_arquivo",
    roteador_existe_dossie,
    {
        "caminho_existe": "verificar_parecer",
        "caminho_nao_existe": END 
    }
)

# Verifica parecer -> Fim
workflow.add_edge("verificar_parecer", END)

# Compila o grafo
app = workflow.compile()

# ==========================================
# 4. TESTE
# ==========================================
if __name__ == "__main__":
    estado_inicial = {
        "caminho_pdf": "/home/felipe-capovilla/Documents/HackatonEnter/docs/dossie.pdf",
        "docie_existe": False,
        "parecer_geral": "",
        "recomendacao": ""  # Inicializamos a recomendação exigida pelo state.py[cite: 3]
    }
    
    print("--- INICIANDO LANGGRAPH ---")
    estado_final = app.invoke(estado_inicial)
    
    print("\n--- ESTADO FINAL ---")
    print(f"Existia? {estado_final.get('docie_existe')}")
    print(f"Parecer Final: {estado_final.get('parecer_geral')}")
    print(f"Recomendação: {estado_final.get('recomendacao')}")