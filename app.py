# ==========================================================
# SMARTCREDITAI - BACKEND PRINCIPAL (app.py)
# ==========================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Inicializamos a aplicação
app = FastAPI(
    title="SmartCreditAI",
    description="Plataforma de Análise de Crédito Empresarial",
    version="1.0.0"
)

# Permite que o frontend (index.html) converse com este backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estrutura dos dados enviados para análise
class AnaliseCreditoInput(BaseModel):
    receita_liquida_anual: float
    liquidez_corrente: float
    margem_liquida: float
    endividamento_geral: float

# Rota Inicial
@app.get("/")
def pagina_inicial():
    return {
        "status": "online",
        "projeto": "SmartCreditAI",
        "mensagem": "O servidor do SmartCreditAI está a funcionar perfeitamente!"
    }

# Rota de Cálculo de Decisão de Crédito
@app.post("/api/v1/decisao/analisar")
def analisar_credito(dados: AnaliseCreditoInput):
    score = 500

    # Validação de Liquidez
    if dados.liquidez_corrente >= 1.5:
        score += 150
    elif dados.liquidez_corrente >= 1.0:
        score += 50
    else:
        score -= 100

    # Validação de Margem Líquida
    if dados.margem_liquida >= 10.0:
        score += 150
    elif dados.margem_liquida > 0:
        score += 50
    else:
        score -= 150

    # Validação de Endividamento
    if dados.endividamento_geral <= 50.0:
        score += 150
    elif dados.endividamento_geral <= 70.0:
        score += 50
    else:
        score -= 100

    # Limita o score entre 0 e 1000
    score = max(0, min(1000, score))

    # Definição do Limite e Decisão
    if score >= 700:
        decisao = "APROVADO"
        percentual = 0.15
        risco = "BAIXO"
    elif score >= 450:
        decisao = "APROVADO COM RESTRICAO"
        percentual = 0.05
        risco = "MEDIO"
    else:
        decisao = "REPROVADO"
        percentual = 0.0
        risco = "ALTO"

    limite = dados.receita_liquida_anual * percentual

    return {
        "score": score,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": round(limite, 2)
    }