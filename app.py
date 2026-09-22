# ==========================================================
# SMARTCREDITAI - BACKEND COM INTEGRAÇÃO SUPABASE (app.py)
# ==========================================================

import os
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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

# Permite requisições do navegador sem bloqueios
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


def consultar_cnpj_externo(cnpj: str):
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) != 14:
        return None

    request = Request(
        f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}",
        headers={"User-Agent": "SmartCreditAI/1.0"}
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

# Rota principal que carrega a interface gráfica
@app.get("/", response_class=HTMLResponse)
def carregar_dashboard():
    caminho_html = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(caminho_html):
        with open(caminho_html, "r", encoding="utf-8") as file:
            return file.read()
    return "<h1>Erro: Ficheiro index.html não foi encontrado.</h1>"


@app.get("/api/v1/empresa/{cnpj}")
def consultar_empresa(cnpj: str):
    dados = consultar_cnpj_externo(cnpj)
    if not dados:
        return {"encontrada": False, "mensagem": "CNPJ não encontrado ou serviço indisponível."}

    return {
        "encontrada": True,
        "cnpj": dados.get("cnpj"),
        "razao_social": dados.get("razao_social"),
        "nome_fantasia": dados.get("nome_fantasia"),
        "situacao": dados.get("descricao_situacao_cadastral"),
        "endereco": "{0}, {1} - {2}, {3}/{4}".format(
            dados.get("logradouro") or "",
            dados.get("numero") or "s/n",
            dados.get("municipio") or "",
            dados.get("uf") or "",
            dados.get("cep") or ""
        ).strip(" ,-/"),
        "telefone": dados.get("ddd_telefone_1") or dados.get("ddd_telefone_2"),
        "email": dados.get("email"),
        "cnae": dados.get("cnae_fiscal_descricao") or "Não informado",
        "capital_social": dados.get("capital_social"),
        "funcionarios": dados.get("quantidade_funcionarios")
    }

# Rota de análise e gravação na base de dados
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