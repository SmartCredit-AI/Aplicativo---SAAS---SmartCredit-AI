# ==========================================================
# SMARTCREDITAI - BACKEND E SERVIDOR VISUAL (app.py)
# ==========================================================

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(
    title="SmartCreditAI",
    description="Plataforma de Análise de Crédito Empresarial",
    version="1.0.0"
)

# Configuração de CORS para permitir requisições no navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estrutura dos dados enviados para análise de crédito
class AnaliseCreditoInput(BaseModel):
    receita_liquida_anual: float
    liquidez_corrente: float
    margem_liquida: float
    endividamento_geral: float

# Rota principal: Entrega o ficheiro index.html para o navegador
@app.get("/", response_class=HTMLResponse)
def carregar_dashboard():
    caminho_html = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(caminho_html):
        with open(caminho_html, "r", encoding="utf-8") as file:
            return file.read()
    return "<h1>Erro: Ficheiro index.html não foi encontrado.</h1>"

# Rota de Cálculo da Decisão de Crédito
@app.post("/api/v1/decisao/analisar")
def analisar_credito(dados: AnaliseCreditoInput):
    score = 500

    # Regras de Liquidez Corrente
    if dados.liquidez_corrente >= 1.5:
        score += 150
    elif dados.liquidez_corrente >= 1.0:
        score += 50
    else:
        score -= 100

    # Regras de Margem Líquida
    if dados.margem_liquida >= 10.0:
        score += 150
    elif dados.margem_liquida > 0:
        score += 50
    else:
        score -= 150

    # Regras de Endividamento
    if dados.endividamento_geral <= 50.0:
        score += 150
    elif dados.endividamento_geral <= 70.0:
        score += 50
    else:
        score -= 100

    score = max(0, min(1000, score))

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
