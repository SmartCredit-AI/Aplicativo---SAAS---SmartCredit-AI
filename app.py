# ==========================================================
# SMARTCREDITAI - MOTOR DE CRÉDITO E ANÁLISE CONTÁBIL (app.py)
# ==========================================================

import os
import json
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Carrega variáveis do arquivo .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Inicialização da aplicação FastAPI
app = FastAPI(
    title="SmartCreditAI",
    description="Motor Inteligente de Análise Contábil e Concessão de Crédito Empresarial",
    version="1.2.0"
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

# Cache em memória para histórico de análises (disponível mesmo sem Supabase)
local_analises_cache: List[Dict[str, Any]] = []


# ==========================================================
# MODELOS DE DADOS
# ==========================================================

class ContasBalanco(BaseModel):
    ativo_total: float = 0.0
    ativo_circulante: float = 0.0
    disponibilidades: float = 0.0
    contas_a_receber: float = 0.0
    estoques: float = 0.0
    ativo_nao_circulante: float = 0.0
    realizavel_longo_prazo: float = 0.0
    imobilizado: float = 0.0
    passivo_circulante: float = 0.0
    fornecedores: float = 0.0
    emprestimos_curto_prazo: float = 0.0
    passivo_nao_circulante: float = 0.0
    financiamentos_longo_prazo: float = 0.0
    patrimonio_liquido: float = 0.0
    capital_social: float = 0.0


class ContasDre(BaseModel):
    receita_bruta: float = 0.0
    deducoes: float = 0.0
    receita_liquida: float = 0.0
    custos_vendas: float = 0.0
    lucro_bruto: float = 0.0
    despesas_operacionais: float = 0.0
    ebitda: float = 0.0
    depreciacao_amortizacao: float = 0.0
    resultado_financeiro: float = 0.0
    impostos: float = 0.0
    lucro_liquido: float = 0.0


class AnaliseCreditoInput(BaseModel):
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    
    # Contas Contábeis (Opcionais com defaults calculados ou preenchidos)
    balanco: Optional[ContasBalanco] = None
    dre: Optional[ContasDre] = None
    
    # Campos diretos / legados para retrocompatibilidade
    receita_liquida_anual: Optional[float] = None
    liquidez_corrente: Optional[float] = None
    margem_liquida: Optional[float] = None
    endividamento_geral: Optional[float] = None
    liquidez_seca: Optional[float] = None
    margem_ebitda: Optional[float] = None
    roe: Optional[float] = None


class ExtracaoTextoInput(BaseModel):
    texto: str


# ==========================================================
# PARSER E EXTRATOR INTELIGENTE DE TEXTO / PLANILHAS
# ==========================================================

def limpar_numero(val_str: str) -> float:
    """Converte strings numéricas em float tratando formatos brasileiros (1.000,00) e internacionais."""
    if not val_str:
        return 0.0
    v = val_str.strip().replace("R$", "").replace(" ", "")
    # Se contém ponto e vírgula, ex: 1.250.000,50
    if "." in v and "," in v:
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(re.findall(r"[-+]?\d*\.?\d+", v)[0])
    except (IndexError, ValueError):
        return 0.0


def extrair_contas_contabeis(conteudo_texto: str) -> Dict[str, Any]:
    """
    Analisa o texto do Balanço Patrimonial e DRE para identificar as contas
    mais comuns conforme o padrão contábil brasileiro (CPC / IFRS).
    """
    linhas = conteudo_texto.splitlines()
    balanco = ContasBalanco().model_dump()
    dre = ContasDre().model_dump()
    contas_encontradas = []

    # Dicionário de padrões regex para identificação das contas
    padroes_balanco = {
        "ativo_circulante": r"(?:ativo\s+circulante|circulante\s+ativo)",
        "disponibilidades": r"(?:disponibilidades|caixa\s+e\s+equivalentes|caixa\s+e\s+bancos|bancos\s+conta)",
        "contas_a_receber": r"(?:contas\s+a\s+receber|clientes|duplicatas\s+a\s+receber)",
        "estoques": r"(?:estoques?|mercadorias\s+para\s+revenda)",
        "ativo_nao_circulante": r"(?:ativo\s+n[aã]o\s+circulante|realiz[aá]vel\s+a\s+longo\s+prazo|imobilizado|ativo\s+permanente)",
        "realizavel_longo_prazo": r"(?:realiz[aá]vel\s+a\s+longo\s+prazo|ativo\s+rlp)",
        "imobilizado": r"(?:imobilizado|ativo\s+imobilizado|bens\s+e\s+equipamentos)",
        "ativo_total": r"(?:ativo\s+total|total\s+do\s+ativo)",
        "passivo_circulante": r"(?:passivo\s+circulante|circulante\s+passivo)",
        "fornecedores": r"(?:fornecedores|contas\s+a\s+pagar\s+fornecedores)",
        "emprestimos_curto_prazo": r"(?:empr[eé]stimos\s+(?:cp|curto\s+prazo)|financiamentos\s+cp)",
        "passivo_nao_circulante": r"(?:passivo\s+n[aã]o\s+circulante|exig[ií]vel\s+a\s+longo\s+prazo)",
        "financiamentos_longo_prazo": r"(?:empr[eé]stimos\s+lp|financiamentos\s+lp|d[ií]vidas\s+lp)",
        "patrimonio_liquido": r"(?:patrim[oô]nio\s+l[ií]quido|pl\s+total|total\s+do\s+patrim[oô]nio)",
        "capital_social": r"(?:capital\s+social|capital\s+subscrito|capital\s+integralizado)"
    }

    padroes_dre = {
        "receita_bruta": r"(?:receita\s+operacional\s+bruta|receita\s+bruta\s+de\s+vendas|vendas\s+brutas)",
        "deducoes": r"(?:dedu[cç][oõ]es\s+da\s+receita|impostos\s+sobre\s+vendas|devolu[cç][oõ]es)",
        "receita_liquida": r"(?:receita\s+operacional\s+l[ií]quida|receita\s+l[ií]quida|vendas\s+l[ií]quidas)",
        "custos_vendas": r"(?:custo\s+(?:das\s+vendas|dos\s+produtos|dos\s+servi[cç]os)|cmv|cpv|csp)",
        "lucro_bruto": r"(?:lucro\s+bruto|resultado\s+bruto)",
        "despesas_operacionais": r"(?:despesas\s+operacionais|despesas\s+administrativas|despesas\s+comerciais)",
        "ebitda": r"(?:ebitda|lajida|resultado\s+operacional\s+antes)",
        "depreciacao_amortizacao": r"(?:deprecia[cç][aã]o|amortiza[cç][aã]o)",
        "resultado_financeiro": r"(?:resultado\s+financeiro|despesas\s+financeiras\s+l[ií]quidas)",
        "impostos": r"(?:irpj|csll|provis[aã]o\s+para\s+imposto)",
        "lucro_liquido": r"(?:lucro\s+l[ií]quido|lucro\/preju[ií]zo\s+do\s+exerc[ií]cio|resultado\s+l[ií]quido)"
    }

    for linha in linhas:
        linha_limpa = linha.strip()
        if not linha_limpa or len(linha_limpa) < 3:
            continue

        # Procura números na linha (valores monetários)
        numeros = re.findall(r"[-+]?\s*R?\$?\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?", linha_limpa)
        if not numeros:
            continue
        ultimo_valor = limpar_numero(numeros[-1])
        if ultimo_valor == 0:
            continue

        # Testa com padrões de Balanço
        for chave, padrao in padroes_balanco.items():
            if re.search(padrao, linha_limpa, re.IGNORECASE) and balanco[chave] == 0:
                balanco[chave] = abs(ultimo_valor)
                contas_encontradas.append({"tipo": "balanco", "conta": chave, "valor": abs(ultimo_valor), "linha": linha_limpa})
                break

        # Testa com padrões de DRE
        for chave, padrao in padroes_dre.items():
            if re.search(padrao, linha_limpa, re.IGNORECASE) and dre[chave] == 0:
                # Lucro Líquido e Resultado Financeiro podem ser negativos
                valor_final = ultimo_valor if "-" not in numeros[-1] else -abs(ultimo_valor)
                dre[chave] = valor_final
                contas_encontradas.append({"tipo": "dre", "conta": chave, "valor": valor_final, "linha": linha_limpa})
                break

    # Racionalização / Consistência Contábil de Fechamento
    # Se ativo total estiver zerado, tenta compor ativo circulante + não circulante
    if balanco["ativo_total"] == 0:
        balanco["ativo_total"] = balanco["ativo_circulante"] + balanco["ativo_nao_circulante"]
    if balanco["ativo_circulante"] == 0 and (balanco["disponibilidades"] or balanco["contas_a_receber"] or balanco["estoques"]):
        balanco["ativo_circulante"] = balanco["disponibilidades"] + balanco["contas_a_receber"] + balanco["estoques"]
    if balanco["passivo_circulante"] == 0 and (balanco["fornecedores"] or balanco["emprestimos_curto_prazo"]):
        balanco["passivo_circulante"] = balanco["fornecedores"] + balanco["emprestimos_curto_prazo"]
    if balanco["patrimonio_liquido"] == 0 and balanco["ativo_total"] > 0:
        exigivel = balanco["passivo_circulante"] + balanco["passivo_nao_circulante"]
        if balanco["ativo_total"] >= exigivel:
            balanco["patrimonio_liquido"] = balanco["ativo_total"] - exigivel

    # Consistência da DRE
    if dre["receita_liquida"] == 0 and dre["receita_bruta"] > 0:
        dre["receita_liquida"] = dre["receita_bruta"] - dre["deducoes"]
    if dre["lucro_bruto"] == 0 and dre["receita_liquida"] > 0 and dre["custos_vendas"] > 0:
        dre["lucro_bruto"] = dre["receita_liquida"] - dre["custos_vendas"]
    if dre["ebitda"] == 0 and dre["lucro_bruto"] > 0:
        dre["ebitda"] = dre["lucro_bruto"] - dre["despesas_operacionais"]
    if dre["lucro_liquido"] == 0 and dre["ebitda"] > 0:
        dre["lucro_liquido"] = dre["ebitda"] - dre["depreciacao_amortizacao"] + dre["resultado_financeiro"] - dre["impostos"]

    return {
        "sucesso": True,
        "balanco": balanco,
        "dre": dre,
        "total_contas_detectadas": len(contas_encontradas),
        "contas_encontradas": contas_encontradas
    }


# ==========================================================
# ROTAS DO SISTEMA
# ==========================================================

@app.get("/", response_class=HTMLResponse)
def carregar_dashboard():
    caminho_html = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(caminho_html):
        with open(caminho_html, "r", encoding="utf-8") as file:
            return file.read()
    return "<h1>Erro: Ficheiro index.html não foi encontrado.</h1>"


def consultar_cnpj_externo(cnpj: str):
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) != 14:
        return None

    request = Request(
        f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}",
        headers={"User-Agent": "SmartCreditAI/1.2"}
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


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


# Rota para extração de contas contábeis de texto / relatório
@app.post("/api/v1/documentos/extrair")
def extrair_documentos(dados: ExtracaoTextoInput):
    resultado = extrair_contas_contabeis(dados.texto)
    return resultado


# Rota para upload direto de arquivos de Balanço e DRE
@app.post("/api/v1/documentos/upload")
async def upload_documentos(
    arquivo_balanco: Optional[UploadFile] = File(None),
    arquivo_dre: Optional[UploadFile] = File(None)
):
    texto_combinado = ""
    nomes_arquivos = []

    for arq in [arquivo_balanco, arquivo_dre]:
        if arq and arq.filename:
            nomes_arquivos.append(arq.filename)
            conteudo_bytes = await arq.read()
            # Decodificação flexível (UTF-8, Latin-1, ASCII)
            try:
                texto_combinado += "\n" + conteudo_bytes.decode("utf-8", errors="ignore")
            except Exception:
                texto_combinado += "\n" + conteudo_bytes.decode("latin-1", errors="ignore")

    resultado = extrair_contas_contabeis(texto_combinado)
    resultado["arquivos_processados"] = nomes_arquivos
    return resultado


# ==========================================================
# MOTOR DE DECISÃO E ANÁLISE DE CRÉDITO
# ==========================================================

@app.post("/api/v1/decisao/analisar")
def analisar_credito(dados: AnaliseCreditoInput):
    # Consolida as contas contábeis
    b = dados.balanco.model_dump() if dados.balanco else {}
    d = dados.dre.model_dump() if dados.dre else {}

    # Resgata ou deduz grandezas fundamentais
    receita_liquida = d.get("receita_liquida") or dados.receita_liquida_anual or 1200000.0
    ativo_total = b.get("ativo_total") or (receita_liquida * 0.8)
    ativo_circulante = b.get("ativo_circulante") or (ativo_total * 0.55)
    passivo_circulante = b.get("passivo_circulante") or (ativo_circulante / (dados.liquidez_corrente or 1.5))
    estoques = b.get("estoques") or (ativo_circulante * 0.25)
    passivo_nao_circulante = b.get("passivo_nao_circulante") or (ativo_total * 0.15)
    patrimonio_liquido = b.get("patrimonio_liquido") or max(1000.0, ativo_total - passivo_circulante - passivo_nao_circulante)
    
    lucro_bruto = d.get("lucro_bruto") or (receita_liquida * 0.35)
    ebitda = d.get("ebitda") or (receita_liquida * 0.18)
    lucro_liquido = d.get("lucro_liquido") or (receita_liquida * (dados.margem_liquida or 10.0) / 100.0)

    # 1. Cruzamento de Índices Contábeis Rigorosos
    # Liquidez Corrente
    if passivo_circulante > 0:
        liq_corrente = round(ativo_circulante / passivo_circulante, 2)
        liq_seca = round(max(0.0, ativo_circulante - estoques) / passivo_circulante, 2)
    else:
        liq_corrente = round(dados.liquidez_corrente or 2.0, 2)
        liq_seca = round(dados.liquidez_seca or 1.5, 2)

    # Liquidez Geral
    exigivel_total = passivo_circulante + passivo_nao_circulante
    rlp = b.get("realizavel_longo_prazo", 0.0)
    liq_geral = round((ativo_circulante + rlp) / exigivel_total, 2) if exigivel_total > 0 else liq_corrente

    # Endividamento Geral (%)
    if ativo_total > 0:
        endiv_geral = round((exigivel_total / ativo_total) * 100.0, 1)
    else:
        endiv_geral = round(dados.endividamento_geral or 45.0, 1)

    # Perfil da Dívida (% Curto Prazo)
    perfil_divida = round((passivo_circulante / exigivel_total) * 100.0, 1) if exigivel_total > 0 else 50.0

    # Margens (%)
    margem_bruta = round((lucro_bruto / receita_liquida) * 100.0, 1) if receita_liquida > 0 else 30.0
    margem_ebitda = round((ebitda / receita_liquida) * 100.0, 1) if receita_liquida > 0 else 15.0
    margem_liquida = round((lucro_liquido / receita_liquida) * 100.0, 1) if receita_liquida > 0 else round(dados.margem_liquida or 10.0, 1)

    # Retornos (%)
    roe = round((lucro_liquido / patrimonio_liquido) * 100.0, 1) if patrimonio_liquido > 0 else 0.0
    roa = round((lucro_liquido / ativo_total) * 100.0, 1) if ativo_total > 0 else 0.0

    # 2. Motor de Pontuação e Score IA (0 a 1000)
    score = 500
    pontos_fortes = []
    pontos_atencao = []

    # Pilar 1: Liquidez (Peso: 250 pts)
    if liq_corrente >= 1.6 and liq_seca >= 1.1:
        score += 150
        pontos_fortes.append(f"Excelente índice de liquidez corrente ({liq_corrente}x) e seca ({liq_seca}x).")
    elif liq_corrente >= 1.2:
        score += 60
        pontos_fortes.append(f"Liquidez operacional saudável ({liq_corrente}x).")
    elif liq_corrente >= 1.0:
        score += 10
        pontos_atencao.append(f"Liquidez no limiar de equilíbrio ({liq_corrente}x).")
    else:
        score -= 120
        pontos_atencao.append(f"Alerta de liquidez crítica: passivo de curto prazo supera os ativos circulantes ({liq_corrente}x).")

    # Pilar 2: Endividamento e Estrutura de Capital (Peso: 250 pts)
    if endiv_geral <= 45.0:
        score += 140
        pontos_fortes.append(f"Baixo endividamento geral ({endiv_geral}% do ativo total).")
    elif endiv_geral <= 65.0:
        score += 50
        pontos_fortes.append(f"Endividamento moderado e controlado ({endiv_geral}%).")
    elif endiv_geral <= 80.0:
        score -= 50
        pontos_atencao.append(f"Endividamento geral elevado ({endiv_geral}%). Recomenda-se cautela.")
    else:
        score -= 150
        pontos_atencao.append(f"Alavancagem excessiva: endividamento atinge {endiv_geral}% do ativo total.")

    if perfil_divida > 75.0 and exigivel_total > 0:
        score -= 30
        pontos_atencao.append("Concentração desproporcional da dívida no curto prazo (>75%).")

    # Pilar 3: Margens e Geração de Caixa (Peso: 250 pts)
    if margem_liquida >= 12.0 and margem_ebitda >= 15.0:
        score += 130
        pontos_fortes.append(f"Alta rentabilidade operacional: margem líquida de {margem_liquida}% e EBITDA de {margem_ebitda}%.")
    elif margem_liquida >= 5.0:
        score += 60
        pontos_fortes.append(f"Margem de lucro consistente ({margem_liquida}%).")
    elif margem_liquida > 0:
        score += 10
        pontos_atencao.append(f"Margem líquida estreita ({margem_liquida}%). Sensível a oscilações de custos.")
    else:
        score -= 140
        pontos_atencao.append(f"Resultado em prejuízo no exercício ({margem_liquida}%).")

    # Pilar 4: Retorno e Robustez Patrimonial (Peso: 150 pts)
    if roe >= 15.0:
        score += 80
        pontos_fortes.append(f"Forte retorno sobre o patrimônio líquido (ROE: {roe}%).")
    elif roe > 0:
        score += 30
    else:
        score -= 50

    if patrimonio_liquido < 0:
        score -= 200
        pontos_atencao.append("Passivo a descoberto: Patrimônio Líquido negativo.")

    # Limita o score entre 0 e 1000
    score = max(50, min(1000, score))

    # 3. Rating e Classificação de Risco
    if score >= 850:
        rating = "AAA"
        risco = "MÍNIMO"
        decisao = "APROVADO"
        fator_limite = 0.20
    elif score >= 750:
        rating = "AA"
        risco = "MUITO BAIXO"
        decisao = "APROVADO"
        fator_limite = 0.16
    elif score >= 650:
        rating = "A"
        risco = "BAIXO"
        decisao = "APROVADO"
        fator_limite = 0.12
    elif score >= 550:
        rating = "BBB"
        risco = "MODERADO BAIXO"
        decisao = "APROVADO"
        fator_limite = 0.08
    elif score >= 450:
        rating = "BB"
        risco = "MODERADO"
        decisao = "APROVADO COM RESTRICAO"
        fator_limite = 0.05
    elif score >= 350:
        rating = "B"
        risco = "MODERADO ALTO"
        decisao = "APROVADO COM RESTRICAO"
        fator_limite = 0.025
    elif score >= 250:
        rating = "CCC"
        risco = "ALTO"
        decisao = "REPROVADO"
        fator_limite = 0.0
    else:
        rating = "D"
        risco = "CRÍTICO"
        decisao = "REPROVADO"
        fator_limite = 0.0

    # 4. Cálculo dos KPIs de Crédito
    # Capacidade mensal de pagamento (serviço da dívida estimado com base no EBITDA)
    capacidade_mensal = round(max(0.0, (ebitda * 0.40) / 12.0), 2)
    
    # Limite sugerido com travas prudenciais de PL e Receita
    limite_bruto = receita_liquida * fator_limite
    # O limite não deve exceder 50% do PL positivo nem 6x a capacidade mensal
    teto_pl = patrimonio_liquido * 0.50 if patrimonio_liquido > 0 else 0.0
    teto_mensal = capacidade_mensal * 6.0 if capacidade_mensal > 0 else 0.0
    
    if decisao != "REPROVADO" and teto_pl > 0 and teto_mensal > 0:
        limite_sugerido = round(min(limite_bruto, max(limite_bruto * 0.5, teto_pl), max(limite_bruto * 0.5, teto_mensal)), 2)
    else:
        limite_sugerido = round(limite_bruto, 2) if decisao != "REPROVADO" else 0.0

    agora_iso = datetime.now(timezone.utc).isoformat()

    dados_contabeis_salvar = {
        "balanco": {
            "ativo_total": ativo_total,
            "ativo_circulante": ativo_circulante,
            "passivo_circulante": passivo_circulante,
            "passivo_nao_circulante": passivo_nao_circulante,
            "patrimonio_liquido": patrimonio_liquido,
            "estoques": estoques
        },
        "dre": {
            "receita_liquida": receita_liquida,
            "lucro_bruto": lucro_bruto,
            "ebitda": ebitda,
            "lucro_liquido": lucro_liquido
        },
        "indices": {
            "liquidez_corrente": liq_corrente,
            "liquidez_seca": liq_seca,
            "liquidez_geral": liq_geral,
            "endividamento_geral": endiv_geral,
            "perfil_divida": perfil_divida,
            "margem_bruta": margem_bruta,
            "margem_ebitda": margem_ebitda,
            "margem_liquida": margem_liquida,
            "roe": roe,
            "roa": roa
        },
        "pontos_fortes": pontos_fortes,
        "pontos_atencao": pontos_atencao
    }

    registro = {
        "cnpj": dados.cnpj,
        "razao_social": dados.razao_social or "Empresa Não Informada",
        "receita_liquida_anual": receita_liquida,
        "liquidez_corrente": liq_corrente,
        "margem_liquida": margem_liquida,
        "endividamento_geral": endiv_geral,
        "score": score,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": limite_sugerido,
        "ativo_total": ativo_total,
        "ativo_circulante": ativo_circulante,
        "passivo_circulante": passivo_circulante,
        "patrimonio_liquido": patrimonio_liquido,
        "lucro_liquido": lucro_liquido,
        "ebitda": ebitda,
        "liquidez_seca": liq_seca,
        "margem_ebitda": margem_ebitda,
        "roe": roe,
        "capacidade_pagamento_mensal": capacidade_mensal,
        "rating": rating,
        "dados_contabeis": dados_contabeis_salvar,
        "created_at": agora_iso
    }

    # 5. Gravação no Supabase (se configurado)
    gravou_supabase = False
    if supabase:
        try:
            supabase.table("analises_credito").insert({
                "cnpj": dados.cnpj,
                "razao_social": dados.razao_social,
                "receita_liquida_anual": receita_liquida,
                "liquidez_corrente": liq_corrente,
                "margem_liquida": margem_liquida,
                "endividamento_geral": endiv_geral,
                "score": score,
                "classificacao_risco": risco,
                "status_decisao": decisao,
                "limite_sugerido": limite_sugerido,
                "ativo_total": ativo_total,
                "ativo_circulante": ativo_circulante,
                "passivo_circulante": passivo_circulante,
                "patrimonio_liquido": patrimonio_liquido,
                "lucro_liquido": lucro_liquido,
                "ebitda": ebitda,
                "liquidez_seca": liq_seca,
                "margem_ebitda": margem_ebitda,
                "roe": roe,
                "capacidade_pagamento_mensal": capacidade_mensal,
                "rating": rating,
                "dados_contabeis": dados_contabeis_salvar
            }).execute()
            gravou_supabase = True
        except Exception as e:
            print(f"Aviso ao gravar no Supabase: {e}")

    # Mantém no cache em memória para disponibilidade imediata
    local_analises_cache.insert(0, registro)

    return {
        "score": score,
        "rating": rating,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": limite_sugerido,
        "capacidade_pagamento_mensal": capacidade_mensal,
        "indices": dados_contabeis_salvar["indices"],
        "contas": {
            "ativo_total": ativo_total,
            "ativo_circulante": ativo_circulante,
            "passivo_circulante": passivo_circulante,
            "passivo_nao_circulante": passivo_nao_circulante,
            "patrimonio_liquido": patrimonio_liquido,
            "receita_liquida": receita_liquida,
            "lucro_bruto": lucro_bruto,
            "ebitda": ebitda,
            "lucro_liquido": lucro_liquido
        },
        "pontos_fortes": pontos_fortes,
        "pontos_atencao": pontos_atencao,
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
            resposta = supabase.table("analises_credito").select("score,classificacao_risco,status_decisao,limite_sugerido,rating").execute()
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
            "volume_credito_total": 0.0,
            "rating_predominante": "N/A"
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