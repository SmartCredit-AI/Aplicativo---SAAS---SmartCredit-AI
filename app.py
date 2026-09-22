# ==========================================================
# SMARTCREDITAI - BACKEND COM INTEGRAÇÃO SUPABASE (app.py)
# ==========================================================

import os
import json
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Carrega variáveis do arquivo .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Inicialização da aplicação FastAPI
app = FastAPI(
    title="SmartCreditAI",
    description="Plataforma Inteligente de Análise de Crédito Empresarial",
    version="1.1.0"
)

# Permite requisições do navegador sem bloqueios de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexão com o Supabase através de Variáveis de Ambiente
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

supabase = None
if SUPABASE_URL and SUPABASE_KEY and not SUPABASE_URL.startswith("https://your-project-ref"):
    try:
        from supabase import create_client, Client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Conectado ao Supabase com sucesso.")
    except Exception as err:
        print(f"Aviso: Não foi possível inicializar o cliente Supabase: {err}")

# Cache em memória para histórico de análises (útil quando Supabase não estiver configurado)
local_analises_cache: List[Dict[str, Any]] = []

# Estrutura dos dados recebidos no formulário
class AnaliseCreditoInput(BaseModel):
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
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
        headers={"User-Agent": "SmartCreditAI/1.1"}
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


# Consulta dados cadastrais na BrasilAPI
@app.get("/api/v1/empresa/{cnpj}")
def consultar_empresa(cnpj: str):
    dados = consultar_cnpj_externo(cnpj)
    if not dados:
        return {"encontrada": False, "mensagem": "CNPJ não encontrado ou serviço de consulta indisponível."}

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
        "funcionarios": dados.get("quantidade_funcionarios"),
        "porte": dados.get("porte") or dados.get("descricao_porte") or "Não informado",
        "natureza_juridica": dados.get("natureza_juridica") or "Não informada",
        "data_inicio_atividade": dados.get("data_inicio_atividade") or "Não informada",
        "qsa": dados.get("qsa") or []
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
    limite_arredondado = round(limite, 2)
    agora_iso = datetime.now(timezone.utc).isoformat()

    registro = {
        "cnpj": dados.cnpj,
        "razao_social": dados.razao_social or "Empresa Não Informada",
        "receita_liquida_anual": dados.receita_liquida_anual,
        "liquidez_corrente": dados.liquidez_corrente,
        "margem_liquida": dados.margem_liquida,
        "endividamento_geral": dados.endividamento_geral,
        "score": score,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": limite_arredondado,
        "created_at": agora_iso
    }

    # Gravação no Supabase (se configurado)
    gravou_supabase = False
    if supabase:
        try:
            # Envia apenas as colunas que constam na migração oficial do Supabase
            supabase.table("analises_credito").insert({
                "cnpj": dados.cnpj,
                "receita_liquida_anual": dados.receita_liquida_anual,
                "liquidez_corrente": dados.liquidez_corrente,
                "margem_liquida": dados.margem_liquida,
                "endividamento_geral": dados.endividamento_geral,
                "score": score,
                "classificacao_risco": risco,
                "status_decisao": decisao,
                "limite_sugerido": limite_arredondado
            }).execute()
            gravou_supabase = True
        except Exception as e:
            print(f"Aviso ao gravar no Supabase: {e}")

    # Mantém no cache em memória para disponibilidade imediata
    local_analises_cache.insert(0, registro)

    return {
        "score": score,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": limite_arredondado,
        "gravado_supabase": gravou_supabase,
        "cnpj": dados.cnpj,
        "razao_social": dados.razao_social
    }


# Rota para obter a lista de análises (Carteira)
@app.get("/api/v1/analises")
def listar_analises():
    if supabase:
        try:
            resposta = supabase.table("analises_credito").select("*").order("created_at", desc=True).limit(100).execute()
            if resposta.data:
                return {"analises": resposta.data, "origem": "supabase"}
        except Exception as e:
            print(f"Aviso ao buscar do Supabase: {e}")

    return {"analises": local_analises_cache, "origem": "local"}


# Rota para métricas agregadas da carteira (Dashboard / Relatórios)
@app.get("/api/v1/metricas")
def obter_metricas():
    lista = []
    if supabase:
        try:
            resposta = supabase.table("analises_credito").select("score,classificacao_risco,status_decisao,limite_sugerido").execute()
            if resposta.data:
                lista = resposta.data
        except Exception as e:
            print(f"Aviso ao buscar métricas do Supabase: {e}")

    if not lista:
        lista = local_analises_cache

    total = len(lista)
    if total == 0:
        return {
            "total_analises": 0,
            "aprovados": 0,
            "restricoes": 0,
            "reprovados": 0,
            "taxa_aprovacao": 0.0,
            "score_medio": 0,
            "volume_credito_total": 0.0
        }

    aprovados = sum(1 for item in lista if item.get("status_decisao") == "APROVADO")
    restricoes = sum(1 for item in lista if item.get("status_decisao") == "APROVADO COM RESTRICAO")
    reprovados = sum(1 for item in lista if item.get("status_decisao") == "REPROVADO")
    score_medio = round(sum(item.get("score", 0) for item in lista) / total)
    volume_credito = sum(float(item.get("limite_sugerido", 0)) for item in lista)

    return {
        "total_analises": total,
        "aprovados": aprovados,
        "restricoes": restricoes,
        "reprovados": reprovados,
        "taxa_aprovacao": round(((aprovados + restricoes) / total) * 100, 1),
        "score_medio": score_medio,
        "volume_credito_total": round(volume_credito, 2)
    }