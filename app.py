# ==========================================================
# SMARTCREDITAI - BACKEND COM INTEGRAÇÃO SUPABASE (app.py)
# ==========================================================

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI(
    title="SmartCreditAI",
    description="Plataforma de Análise de Crédito Empresarial",
    version="1.0.0"
)

# Configuração de CORS para permitir requisições do navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexão com o Supabase através de Variáveis de Ambiente
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Cria o cliente do Supabase apenas se as chaves estiverem configuradas
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Estrutura dos dados recebidos no formulário
class AnaliseCreditoInput(BaseModel):
    receita_liquida_anual: float
    liquidez_corrente: float
    margem_liquida: float
    endividamento_geral: float

@app.get("/api")
@app.get("/api/")
def pagina_inicial():
    return {
        "status": "online",
        "projeto": "SmartCreditAI",
        "mensagem": "O servidor do SmartCreditAI está a funcionar perfeitamente na Vercel!"
    }

@app.post("/api/v1/decisao/analisar")
def analisar_credito(dados: AnaliseCreditoInput):
    score = 500

    # Lógica de cálculo do Score
    if dados.liquidez_corrente >= 1.5:
        score += 150
    elif dados.liquidez_corrente >= 1.0:
        score += 50
    else:
        score -= 100

    if dados.margem_liquida >= 10.0:
        score += 150
    elif dados.margem_liquida > 0:
        score += 50
    else:
        score -= 150

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

    # Gravação no Supabase (se o cliente estiver ativado)
    if supabase:
        try:
            supabase.table("analises_credito").insert({
                "receita_liquida_anual": dados.receita_liquida_anual,
                "liquidez_corrente": dados.liquidez_corrente,
                "margem_liquida": dados.margem_liquida,
                "endividamento_geral": dados.endividamento_geral,
                "score": score,
                "classificacao_risco": risco,
                "status_decisao": decisao,
                "limite_sugerido": round(limite, 2)
            }).execute()
        except Exception as e:
            print(f"Erro ao gravar no Supabase: {e}")

    return {
        "score": score,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": round(limite, 2)
    }
