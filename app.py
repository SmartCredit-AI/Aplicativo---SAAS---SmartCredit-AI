# ==========================================================
# SMARTCREDITAI - MOTOR DE CRÉDITO E AUDITORIA CONTÁBIL (app.py)
# ==========================================================

import os
import io
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
    description="Motor Inteligente de Análise Contábil, Auditoria por IA e Decisão de Crédito Empresarial",
    version="1.3.0"
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


class AuditoriaInput(BaseModel):
    balanco: ContasBalanco
    dre: ContasDre


class AnaliseCreditoInput(BaseModel):
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    capital_social_cadastral: Optional[float] = None
    
    # Contas Contábeis
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
    capital_social_cadastral: Optional[float] = 0.0


# ==========================================================
# PARSER REAL DE ARQUIVOS (PDF, EXCEL, CSV, TXT)
# ==========================================================

def extrair_texto_de_arquivo(nome_arquivo: str, conteudo_bytes: bytes) -> str:
    """Extrai texto legível e estruturado de arquivos PDF, planilhas Excel (.xlsx/.xls) ou arquivos de texto/CSV."""
    nome_lower = (nome_arquivo or "").lower()

    # 1. Arquivo PDF real (usando pypdf)
    if nome_lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            leitor = PdfReader(io.BytesIO(conteudo_bytes))
            textos = []
            for num, pagina in enumerate(leitor.pages):
                txt = pagina.extract_text()
                if txt:
                    textos.append(txt)
            if textos:
                return "\n".join(textos)
        except Exception as e:
            print(f"Aviso ao ler PDF '{nome_arquivo}' com pypdf: {e}")

    # 2. Planilha Excel real moderna (usando openpyxl com leitura de todas as abas e colunas)
    elif nome_lower.endswith((".xlsx", ".xlsm", ".xltx")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), data_only=True)
            linhas_planilha = []
            for sheetname in wb.sheetnames:
                ws = wb[sheetname]
                linhas_planilha.append(f"\n--- PLANILHA: {sheetname} ---")
                for row in ws.iter_rows(values_only=True):
                    celulas = []
                    for c in row:
                        if c is None:
                            continue
                        # Formata tipos do Excel (datetime, float, int, str)
                        if hasattr(c, "strftime"):
                            celulas.append(c.strftime("%d/%m/%Y"))
                        else:
                            s = str(c).strip()
                            if s:
                                celulas.append(s)
                    if celulas:
                        linhas_planilha.append(" | ".join(celulas))
            if linhas_planilha:
                return "\n".join(linhas_planilha)
        except Exception as e:
            print(f"Aviso ao ler Excel '{nome_arquivo}' com openpyxl: {e}")

    # 3. Tratamento para arquivos legados .xls (Excel 97-2003)
    elif nome_lower.endswith(".xls"):
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=conteudo_bytes)
            linhas_xls = []
            for s_idx in range(book.nsheets):
                sh = book.sheet_by_index(s_idx)
                linhas_xls.append(f"\n--- PLANILHA: {sh.name} ---")
                for rx in range(sh.nrows):
                    row_vals = [str(sh.cell_value(rx, cx)).strip() for cx in range(sh.ncols) if str(sh.cell_value(rx, cx)).strip()]
                    if row_vals:
                        linhas_xls.append(" | ".join(row_vals))
            if linhas_xls:
                return "\n".join(linhas_xls)
        except Exception:
            # Se xlrd não estiver disponível, avisa para salvar como .xlsx
            return (
                "Aviso: O arquivo enviado está no formato legado .xls (Excel 97-2003). "
                "Para leitura contábil automática com máxima precisão, converta e salve o arquivo como .xlsx ou .csv."
            )

    # 4. Arquivo de Texto, CSV ou fallback com detecção de encoding (com suporte a utf-8-sig com BOM)
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            return conteudo_bytes.decode(enc)
        except UnicodeDecodeError:
            continue

    return conteudo_bytes.decode("utf-8", errors="ignore")


def detectar_escala(conteudo_texto: str):
    """
    Identifica se as demonstrações contábeis estão expressas em Milhares (R$ Mil), Milhões ou Unidades simples.
    Padrão amplamente utilizado por companhias de capital aberto (CVM, B3 e IFRS).
    """
    t = (conteudo_texto or "").lower()
    
    # 1. Padrões de Milhões
    padroes_milhoes = [
        r"r\$\s*mi\b",
        r"r\$\s*milh[oõ]es\b",
        r"valores\s+em\s+milh[oõ]es",
        r"valores\s+expressos\s+em\s+milh[oõ]es",
        r"expressos\s+em\s+milh[oõ]es",
        r"em\s+milh[oõ]es(?:\s+de\s+reais|\s+de\s+r\$|\s+reais)?",
        r"cifras\s+em\s+milh[oõ]es",
        r"milh[oõ]es\s+de\s+reais",
        r"r\$\s*em\s+milh[oõ]es",
        r"\(?\s*r\$\s*[\'\"]?000\.000\s*\)?",
        r"\(?\s*em\s+milh[oõ]es\s*\)?",
        r"escala:\s*milh[oõ]es",
        r"unidade:\s*milh[oõ]es"
    ]
    for p in padroes_milhoes:
        if re.search(p, t):
            return "milhoes", 1000000.0, "Em milhões de Reais (x1.000.000)"

    # 2. Padrões de Milhares (Padrão CVM / B3 / IFRS Brasil: 'R$ Mil', 'Valores em milhares', etc.)
    padroes_milhares = [
        r"r\$\s*mil\b",
        r"\(?\s*em\s+r\$\s*mil\s*\)?",
        r"valores\s+em\s+milhares",
        r"valores\s+expressos\s+em\s+milhares",
        r"expressos\s+em\s+milhares",
        r"em\s+milhares(?:\s+de\s+reais|\s+de\s+r\$|\s+reais)?",
        r"cifras\s+em\s+milhares",
        r"milhares\s+de\s+reais",
        r"r\$\s*em\s+milhares",
        r"\(?\s*r\$\s*[\'\"]?000\s*\)?",
        r"\(?\s*em\s+milhares\s*\)?",
        r"escala:\s*milhares",
        r"unidade:\s*milhares",
        r"r\$\s*1\.000\b",
        r"\(?\s*em\s+r\$\s*1\.000\s*\)?"
    ]
    for p in padroes_milhares:
        if re.search(p, t):
            return "milhares", 1000.0, "Em milhares de Reais (x1.000)"

    return "unidades", 1.0, "Em Reais (x1)"


def limpar_numero(val_str: str) -> float:
    """
    Converte strings numéricas em float tratando padrões brasileiros (1.000,00 e 35.240.112)
    e internacionais sem truncamento de dígitos.
    """
    if not val_str:
        return 0.0
    v = str(val_str).strip().replace("R$", "").replace(" ", "")
    negativo = False
    if (v.startswith("(") and v.endswith(")")) or v.startswith("-"):
        negativo = True
        v = v.strip("()-")
    
    # Caso 1: tem ponto e vírgula -> Ex: 35.240.112,50 ou 35,240,112.50
    if "." in v and "," in v:
        # Se a vírgula vem depois do ponto: padrão brasileiro 1.000,50
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    elif "," in v:
        # Apenas vírgula: se tem mais de uma vírgula (ex: 35,240,112)
        if v.count(",") > 1:
            v = v.replace(",", "")
        else:
            # Uma vírgula: se tiver exatamente 2 dígitos no fim, é decimal (1250,50)
            partes = v.split(",")
            if len(partes[1]) == 2:
                v = v.replace(",", ".")
            else:
                v = v.replace(",", "")
    elif "." in v:
        # Apenas ponto: se tem mais de um ponto (ex: 35.240.112)
        if v.count(".") > 1:
            v = v.replace(".", "")
        else:
            # Um ponto: se tiver 3 dígitos após o ponto (ex: 1.250 ou 500.000), é milhar!
            partes = v.split(".")
            if len(partes[1]) == 3:
                v = v.replace(".", "")
            else:
                pass # decimal como 1250.50
    
    try:
        num = float(v)
        return -num if negativo else num
    except ValueError:
        nums = re.findall(r"\d+(?:\.\d+)?", v)
        if nums:
            num = float(nums[0])
            return -num if negativo else num
        return 0.0


def extrair_valor_de_linha_contabil(linha: str) -> float:
    """
    Extrai com precisão contábil o valor financeiro do período recente (exercício corrente)
    em planilhas com múltiplas colunas (Código | Descrição | Nota | Período Atual | Período Anterior)
    e relatórios de texto / PDF, descartando colunas de notas explicativas e anos.
    """
    # 1. Quebra de colunas estruturadas ou delimitadas por múltiplos espaços
    if "|" in linha or ";" in linha or "\t" in linha:
        delim = "|" if "|" in linha else (";" if ";" in linha else "\t")
        colunas = [c.strip() for c in linha.split(delim) if c.strip()]
    else:
        colunas = [c.strip() for c in re.split(r"\s{2,}", linha.strip()) if c.strip()]

    if len(colunas) <= 1:
        padrao = r"[-+]?\s*\(?\s*R?\$?\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?\s*\)?"
        numeros = re.findall(padrao, linha)
        if numeros:
            for n in reversed(numeros):
                v = limpar_numero(n)
                if abs(v) > 0:
                    return v
        return 0.0

    valores_candidatos = []
    for i, col in enumerate(colunas):
        # Despreza datas completas (ex: 31/12/2023 ou 2023-12-31)
        if re.search(r"^\d{2}/\d{2}/\d{4}$", col) or re.search(r"^\d{4}-\d{2}-\d{2}", col):
            continue
        # Despreza colunas que são puramente texto sem dígito
        if not re.search(r"\d", col):
            continue
        # Despreza notas explicativas textuais explícitas (ex: 'Nota 4', 'NE 12', 'N.E. 3')
        if re.search(r"^(?:nota|ne|n\.e\.)\s*\d+$", col, re.I):
            continue
        # Despreza código da conta contábil na primeira coluna (ex: 1, 1.01, 1.01.01, 2.01, 3.01)
        if i == 0 and re.match(r"^[1-9](?:\.\d{2})*(?:\.\d{2})*$", col):
            continue

        val = limpar_numero(col)
        # Despreza ano isolado no cabeçalho ou linha (ex: 1990..2099) quando houver valores financeiros
        if 1990 <= val <= 2099 and ("." not in col and "," not in col) and len(col) == 4:
            if any(limpar_numero(c) > 2100 for c in colunas[i+1:]):
                continue

        # Despreza coluna de nota explicativa numérica isolada (ex: 4, 12, 58) quando a próxima coluna for valor financeiro maior
        if 0 < val < 100 and ("." not in col and "," not in col):
            if any(abs(limpar_numero(c)) >= 100 for c in colunas[i+1:]):
                continue

        if abs(val) > 0:
            valores_candidatos.append(val)

    if valores_candidatos:
        # Retorna o valor do período mais recente (primeira coluna financeira contábil da linha)
        return valores_candidatos[0]

    return 0.0


def extrair_contas_contabeis(conteudo_texto: str, capital_social_cadastral: float = 0.0) -> Dict[str, Any]:
    """
    Analisa o texto do Balanço Patrimonial e DRE para identificar as contas
    mais comuns conforme o padrão contábil brasileiro (CPC / IFRS / CVM)
    e aplica a escala de grandeza monetária detectada (Milhares / Milhões / Unidades).
    """
    tipo_escala, fator_escala, desc_escala = detectar_escala(conteudo_texto)
    linhas = conteudo_texto.splitlines()
    balanco = ContasBalanco().model_dump()
    dre = ContasDre().model_dump()
    contas_encontradas = []

    # Padrões regex para contas do Balanço Patrimonial (Textuais e Códigos CVM)
    padroes_balanco = {
        "ativo_total": r"(?:^\s*1(?:\.00)?\s*\||ativo\s+total|total\s+do\s+ativo|total\s+geral\s+do\s+ativo)",
        "ativo_circulante": r"(?:^\s*1\.01\s*\||ativo\s+circulante|total\s+do\s+ativo\s+circulante|circulante\s+ativo)",
        "disponibilidades": r"(?:^\s*1\.01\.01\s*\||caixa\s+e\s+equivalentes|caixa\s+e\s+bancos|disponibilidades|bancos\s+conta\s+movimento|dispon[ií]vel)",
        "contas_a_receber": r"(?:^\s*1\.01\.02\s*\||^\s*1\.01\.03\s*\||contas\s+a\s+receber|duplicatas\s+a\s+receber|clientes\s+a\s+receber|clientes\b|cr[eé]ditos\s+operacionais)",
        "estoques": r"(?:^\s*1\.01\.04\s*\||estoques?|mercadorias\s+para\s+revenda|produtos\s+acabados|mat[eé]rias\s+primas)",
        "realizavel_longo_prazo": r"(?:^\s*1\.02\.01\s*\||realiz[aá]vel\s+a\s+longo\s+prazo|ativo\s+rlp|cr[eé]ditos\s+de\s+longo\s+prazo)",
        "imobilizado": r"(?:^\s*1\.02\.03\s*\||^\s*1\.02\.02\s*\||imobilizado|ativo\s+imobilizado|intang[ií]vel|investimentos\s+e\s+imobilizado|bens\s+e\s+direitos)",
        "ativo_nao_circulante": r"(?:^\s*1\.02\s*\||ativo\s+n[aã]o\s+circulante|total\s+do\s+ativo\s+n[aã]o\s+circulante|permanente)",
        "passivo_circulante": r"(?:^\s*2\.01\s*\||passivo\s+circulante|total\s+do\s+passivo\s+circulante|circulante\s+passivo)",
        "fornecedores": r"(?:^\s*2\.01\.01\s*\||^\s*2\.01\.02\s*\||fornecedores|contas\s+a\s+pagar\s+fornecedores|fornecedores\s+nacionais)",
        "emprestimos_curto_prazo": r"(?:^\s*2\.01\.04\s*\||^\s*2\.01\.03\s*\||empr[eé]stimos\s+e\s+financiamentos\s+cp|empr[eé]stimos\s+(?:cp|curto\s+prazo)|financiamentos\s+cp|d[ií]vidas\s+cp)",
        "passivo_nao_circulante": r"(?:^\s*2\.02\s*\||passivo\s+n[aã]o\s+circulante|total\s+do\s+passivo\s+n[aã]o\s+circulante|exig[ií]vel\s+a\s+longo\s+prazo)",
        "financiamentos_longo_prazo": r"(?:^\s*2\.02\.01\s*\||empr[eé]stimos\s+lp|financiamentos\s+lp|d[ií]vidas\s+lp|financiamentos\s+a\s+longo\s+prazo)",
        "capital_social": r"(?:^\s*2\.03\.01\s*\||capital\s+social|capital\s+subscrito|capital\s+integralizado|capital\s+realizado)",
        "patrimonio_liquido": r"(?:^\s*2\.03\s*\||patrim[oô]nio\s+l[ií]quido|total\s+do\s+patrim[oô]nio\s+l[ií]quido|pl\s+total)"
    }

    # Padrões regex para contas da DRE (Textuais e Códigos CVM)
    padroes_dre = {
        "receita_bruta": r"(?:^\s*3\.01\s*\||receita\s+de\s+venda|receita\s+operacional\s+bruta|receita\s+bruta\s+de\s+vendas|vendas\s+brutas|faturamento\s+bruto)",
        "deducoes": r"(?:^\s*3\.02\s*\||dedu[cç][oõ]es\s+da\s+receita|impostos\s+incidentes\s+sobre\s+vendas|devolu[cç][oõ]es\s+e\s+abatimentos)",
        "receita_liquida": r"(?:^\s*3\.03\s*\||receita\s+operacional\s+l[ií]quida|receita\s+l[ií]quida|vendas\s+l[ií]quidas|total\s+da\s+receita\s+l[ií]quida)",
        "custos_vendas": r"(?:^\s*3\.04\s*\||custo\s+(?:das\s+vendas|dos\s+produtos|dos\s+servi[cç]os|dos\s+bens)|custo\s+das\s+mercadorias|cmv|cpv|csp)",
        "lucro_bruto": r"(?:^\s*3\.05\s*\||lucro\s+bruto|resultado\s+bruto|resultado\s+operacional\s+bruto)",
        "despesas_operacionais": r"(?:^\s*3\.06\s*\||despesas\s+operacionais|despesas\s+com\s+vendas|despesas\s+administrativas|despesas\s+gerais)",
        "ebitda": r"(?:ebitda|lajida|resultado\s+operacional\s+antes\s+dos\s+efeitos|lucro\s+operacional)",
        "depreciacao_amortizacao": r"(?:deprecia[cç][aã]o|amortiza[cç][aã]o|deprecia[cç][aã]o\s+e\s+amortiza[cç][aã]o)",
        "resultado_financeiro": r"(?:^\s*3\.07\s*\||^\s*3\.08\s*\||resultado\s+financeiro\s+l[ií]quido|despesas\s+financeiras\s+l[ií]quidas|receitas\s+e\s+despesas\s+financeiras)",
        "impostos": r"(?:irpj\s+e\s+csll|imposto\s+de\s+renda\s+e\s+contribui[cç][aã]o|provis[aã]o\s+para\s+irpj)",
        "lucro_liquido": r"(?:^\s*3\.11\s*\||lucro\s+l[ií]quido\s+do\s+exerc[ií]cio|lucro\s+l[ií]quido|resultado\s+l[ií]quido\s+do\s+exerc[ií]cio|lucro\/preju[ií]zo\s+l[ií]quido|resultado\s+do\s+per[ií]odo)"
    }

    for linha in linhas:
        linha_limpa = linha.strip()
        if not linha_limpa or len(linha_limpa) < 3:
            continue

        valor_bruto = extrair_valor_de_linha_contabil(linha_limpa)
        if valor_bruto == 0:
            continue

        valor_escalado = valor_bruto * fator_escala

        # Testa com padrões de Balanço
        for chave, padrao in padroes_balanco.items():
            if re.search(padrao, linha_limpa, re.IGNORECASE) and balanco[chave] == 0:
                balanco[chave] = abs(valor_escalado)
                contas_encontradas.append({
                    "tipo": "balanco",
                    "conta": chave,
                    "valor_bruto": abs(valor_bruto),
                    "valor": abs(valor_escalado),
                    "fator_escala": fator_escala,
                    "linha": linha_limpa
                })
                break

        # Testa com padrões de DRE
        for chave, padrao in padroes_dre.items():
            if re.search(padrao, linha_limpa, re.IGNORECASE) and dre[chave] == 0:
                valor_final = valor_escalado
                dre[chave] = valor_final
                contas_encontradas.append({
                    "tipo": "dre",
                    "conta": chave,
                    "valor_bruto": valor_bruto,
                    "valor": valor_final,
                    "fator_escala": fator_escala,
                    "linha": linha_limpa
                })
                break

    return {
        "sucesso": True,
        "escala_detectada": tipo_escala,
        "fator_escala": fator_escala,
        "descricao_escala": desc_escala,
        "balanco": balanco,
        "dre": dre,
        "total_contas_detectadas": len(contas_encontradas),
        "contas_encontradas": contas_encontradas
    }


# ==========================================================
# MOTOR DE AUDITORIA CONTÁBIL POR INTELIGÊNCIA ARTIFICIAL
# ==========================================================

def formatar_moeda(val: float) -> str:
    """Formata valor em formato de moeda brasileira R$ 1.234.567,89."""
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def auditar_demonstrativos_contabeis(balanco: Dict[str, Any], dre: Dict[str, Any], capital_social_cadastral: float = 0.0) -> Dict[str, Any]:
    """
    Executa a auditoria inteligente dos demonstrativos contábeis carregados.
    Verifica a Equação Patrimonial Fundamental, a coerência interna da DRE,
    a compatibilidade entre o Balanço e a DRE e a consistência cruzada com o Capital Social Cadastral.
    """
    erros_criticos: List[str] = []
    alertas: List[str] = []

    # Extração das grandezas informadas
    ativo_total = float(balanco.get("ativo_total") or 0.0)
    ativo_circulante = float(balanco.get("ativo_circulante") or 0.0)
    disponibilidades = float(balanco.get("disponibilidades") or 0.0)
    contas_a_receber = float(balanco.get("contas_a_receber") or 0.0)
    estoques = float(balanco.get("estoques") or 0.0)
    ativo_nao_circulante = float(balanco.get("ativo_nao_circulante") or 0.0)

    passivo_circulante = float(balanco.get("passivo_circulante") or 0.0)
    passivo_nao_circulante = float(balanco.get("passivo_nao_circulante") or 0.0)
    patrimonio_liquido = float(balanco.get("patrimonio_liquido") or 0.0)

    receita_bruta = float(dre.get("receita_bruta") or 0.0)
    deducoes = float(dre.get("deducoes") or 0.0)
    receita_liquida = float(dre.get("receita_liquida") or 0.0)
    lucro_bruto = float(dre.get("lucro_bruto") or 0.0)
    ebitda = float(dre.get("ebitda") or 0.0)
    lucro_liquido = float(dre.get("lucro_liquido") or 0.0)

    # 1. VALIDAÇÃO CRUZADA DE CONSISTÊNCIA: ATIVO TOTAL vs. CAPITAL SOCIAL CADASTRAL
    # Regra de Negócio: Trava a aprovação se Ativo Total lido < Capital Social Cadastral
    if capital_social_cadastral > 0 and ativo_total > 0:
        if ativo_total < (capital_social_cadastral * 0.90):
            erros_criticos.append(
                f"Incompatibilidade de Escala / Arquivo Inválido: O Ativo Total lido ({formatar_moeda(ativo_total)}) "
                f"é inferior ao Capital Social Cadastral na Receita Federal ({formatar_moeda(capital_social_cadastral)}). "
                f"Demonstrativos contábeis de companhias de médio/grande porte são expressos em R$ Mil ou R$ Milhões. "
                f"A aprovação automática foi travada para mitigar risco cadastral e distorção de escala."
            )
            # Dica orientativa de correção de escala
            if (ativo_total * 1000.0) >= (capital_social_cadastral * 0.5):
                alertas.append(
                    f"Sugestão de Escala Contábil: Ao multiplicar os valores por 1.000 (R$ Mil), o Ativo Total passará para "
                    f"{formatar_moeda(ativo_total * 1000.0)}, condizente com o porte cadastral da entidade. "
                    f"Selecione o botão 'Em milhares (x1.000)' no topo das tabelas."
                )

    # 2. TESTE DA EQUAÇÃO PATRIMONIAL FUNDAMENTAL (Ativo = Passivo + PL)
    soma_passivo_pl = passivo_circulante + passivo_nao_circulante + patrimonio_liquido
    diferenca_balanco = abs(ativo_total - soma_passivo_pl)

    # Se ambos os lados possuem valores preenchidos (> 0)
    if ativo_total > 0 and soma_passivo_pl > 0:
        perc_dif = (diferenca_balanco / ativo_total) * 100.0
        # Tolerância de até 3% para pequenas variações de arredondamento em balanços
        if perc_dif > 3.0 and diferenca_balanco > 10000.0:
            erros_criticos.append(
                f"Desequilíbrio Patrimonial Severo: O Ativo Total ({formatar_moeda(ativo_total)}) "
                f"diverge do Passivo Total + PL ({formatar_moeda(soma_passivo_pl)}) "
                f"em {formatar_moeda(diferenca_balanco)} ({perc_dif:.1f}% de diferença). "
                f"A Equação Fundamental do Balanço (Ativo = Passivo + PL) foi violada."
            )
    elif ativo_total > 0 and soma_passivo_pl == 0:
        erros_criticos.append(
            f"Passivo e Patrimônio Líquido não informados ou zerados para um Ativo Total de {formatar_moeda(ativo_total)}."
        )

    # 3. TESTE DE SINAIS E INTEGRIDADE DE ATIVO
    if disponibilidades < 0:
        erros_criticos.append("Disponibilidades / Caixa não pode apresentar saldo negativo no Balanço.")
    if contas_a_receber < 0 or estoques < 0:
        erros_criticos.append("Contas de Ativo Circulante (Clientes e Estoques) com saldo negativo inválido.")
    if ativo_total < 0 or ativo_circulante < 0:
        erros_criticos.append("Total do Ativo ou Ativo Circulante não pode ser negativo.")

    # 4. TESTE DE CONSISTÊNCIA INTERNA DA DRE
    if receita_bruta > 0 and receita_liquida > (receita_bruta * 1.01):
        erros_criticos.append(
            f"Inconsistência na DRE: A Receita Líquida ({formatar_moeda(receita_liquida)}) "
            f"é maior do que a Receita Bruta ({formatar_moeda(receita_bruta)})."
        )

    if receita_liquida > 0 and lucro_bruto > (receita_liquida * 1.02):
        erros_criticos.append(
            f"Inconsistência na DRE: O Lucro Bruto ({formatar_moeda(lucro_bruto)}) "
            f"ultrapassa a Receita Líquida ({formatar_moeda(receita_liquida)})."
        )

    if receita_liquida > 0 and lucro_liquido > (receita_liquida * 1.05):
        erros_criticos.append(
            f"Inconsistência Crítica na DRE: O Lucro Líquido ({formatar_moeda(lucro_liquido)}) "
            f"é superior à própria Receita Operacional Líquida ({formatar_moeda(receita_liquida)})."
        )

    # 5. CRUZAMENTO ANALÍTICO: DRE vs. BALANÇO PATRIMONIAL
    if receita_liquida > 0 and contas_a_receber > (receita_liquida * 2.0) and contas_a_receber > 100000.0:
        alertas.append(
            f"Divergência entre DRE e Balanço: O saldo de Contas a Receber ({formatar_moeda(contas_a_receber)}) "
            f"representa mais de 200% do Faturamento Anual ({formatar_moeda(receita_liquida)}). "
            f"Indica possível acúmulo de créditos vencidos ou exercício contábil incompatível."
        )

    if patrimonio_liquido > 0 and patrimonio_liquido < 20000.0 and lucro_liquido > 1000000.0:
        alertas.append(
            f"Incompatibilidade de Porte: Lucro Líquido de {formatar_moeda(lucro_liquido)} "
            f"declarado para um Patrimônio Líquido de apenas {formatar_moeda(patrimonio_liquido)}."
        )

    soma_componentes_ac = disponibilidades + contas_a_receber + estoques
    if ativo_circulante > 0 and soma_componentes_ac > (ativo_circulante * 1.25):
        alertas.append(
            f"A soma de Caixa, Clientes e Estoques ({formatar_moeda(soma_componentes_ac)}) "
            f"ultrapassa o Ativo Circulante total informado ({formatar_moeda(ativo_circulante)})."
        )

    # DECISÃO DA AUDITORIA POR IA
    aprovado = len(erros_criticos) == 0

    if not aprovado:
        status_auditoria = "REJEITADO_INCONSISTENTE"
        diagnostico = (
            "Os demonstrativos contábeis foram REJEITADOS pela Auditoria Inteligente. "
            "Foram detectadas incongruências matemáticas, cadastrais ou de escala que invalidam o parecer favorável."
        )
    elif len(alertas) > 0:
        status_auditoria = "APROVADO_COM_RESSALVAS"
        diagnostico = (
            "Demonstrativos contábeis APROVADOS com ressalvas. A estrutura básica fecha, "
            "mas foram identificados pontos atípicos de atenção analítica."
        )
    else:
        status_auditoria = "APROVADO"
        diagnostico = (
            "Auditoria Contábil por IA APROVADA: Balanço Patrimonial e DRE em plena conformidade contábil "
            "e perfeitamente conciliados."
        )

    return {
        "aprovado": aprovado,
        "status_auditoria": status_auditoria,
        "erros_criticos": erros_criticos,
        "alertas": alertas,
        "diferenca_balanco": round(diferenca_balanco, 2),
        "diagnostico_ia": diagnostico
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
        headers={"User-Agent": "SmartCreditAI/1.3"}
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
    resultado = extrair_contas_contabeis(dados.texto, capital_social_cadastral=float(dados.capital_social_cadastral or 0.0))
    auditoria = auditar_demonstrativos_contabeis(
        resultado["balanco"],
        resultado["dre"],
        capital_social_cadastral=float(dados.capital_social_cadastral or 0.0)
    )
    resultado["auditoria"] = auditoria
    return resultado


# Rota para upload direto de arquivos de Balanço e DRE (PDF, Excel, CSV, TXT)
@app.post("/api/v1/documentos/upload")
async def upload_documentos(
    arquivo_balanco: Optional[UploadFile] = File(None),
    arquivo_dre: Optional[UploadFile] = File(None),
    capital_social_cadastral: Optional[float] = Form(0.0)
):
    texto_combinado = ""
    nomes_arquivos = []

    for arq in [arquivo_balanco, arquivo_dre]:
        if arq and arq.filename:
            nomes_arquivos.append(arq.filename)
            conteudo_bytes = await arq.read()
            texto_extraido = extrair_texto_de_arquivo(arq.filename, conteudo_bytes)
            texto_combinado += f"\n--- INICIO ARQUIVO {arq.filename} ---\n" + texto_extraido

    cap_cadastral = float(capital_social_cadastral or 0.0)
    resultado = extrair_contas_contabeis(texto_combinado, capital_social_cadastral=cap_cadastral)
    auditoria = auditar_demonstrativos_contabeis(resultado["balanco"], resultado["dre"], capital_social_cadastral=cap_cadastral)
    resultado["auditoria"] = auditoria
    resultado["arquivos_processados"] = nomes_arquivos
    return resultado


# Rota para validação e auditoria contábil isolada das contas preenchidas
@app.post("/api/v1/auditoria/validar")
def validar_auditoria_contabil(dados: AuditoriaInput):
    resultado_auditoria = auditar_demonstrativos_contabeis(
        dados.balanco.model_dump(),
        dados.dre.model_dump()
    )
    return resultado_auditoria


# ==========================================================
# MOTOR DE DECISÃO E ANÁLISE DE CRÉDITO
# ==========================================================

@app.post("/api/v1/decisao/analisar")
def analisar_credito(dados: AnaliseCreditoInput):
    b = dados.balanco.model_dump() if dados.balanco else {}
    d = dados.dre.model_dump() if dados.dre else {}
    cap_cadastral = float(dados.capital_social_cadastral or 0.0)

    # 1. EXECUTAR AUDITORIA CONTÁBIL PRIMEIRO (com validação cruzada com capital cadastral)
    auditoria = auditar_demonstrativos_contabeis(b, d, capital_social_cadastral=cap_cadastral)

    # Se a auditoria for rejeitada por inconsistência severa, bloqueia a concessão imediatamente
    if not auditoria["aprovado"]:
        return {
            "score": 50,
            "rating": "D",
            "classificacao_risco": "CRÍTICO - INCONSISTÊNCIA CONTÁBIL",
            "status_decisao": "REPROVADO",
            "limite_sugerido": 0.0,
            "capacidade_pagamento_mensal": 0.0,
            "auditoria": auditoria,
            "motivo_rejeicao": auditoria["erros_criticos"],
            "pontos_fortes": [],
            "pontos_atencao": auditoria["erros_criticos"] + auditoria["alertas"],
            "indices": {},
            "contas": {},
            "gravado_supabase": False,
            "cnpj": dados.cnpj,
            "razao_social": dados.razao_social
        }

    # Grandezas contábeis estritamente extraídas ou informadas (SEM valores fictícios de mockup)
    receita_liquida = float(d.get("receita_liquida") or dados.receita_liquida_anual or 0.0)
    ativo_total = float(b.get("ativo_total") or 0.0)
    ativo_circulante = float(b.get("ativo_circulante") or 0.0)
    passivo_circulante = float(b.get("passivo_circulante") or 0.0)
    estoques = float(b.get("estoques") or 0.0)
    passivo_nao_circulante = float(b.get("passivo_nao_circulante") or 0.0)
    patrimonio_liquido = float(b.get("patrimonio_liquido") or 0.0)
    
    lucro_bruto = float(d.get("lucro_bruto") or 0.0)
    ebitda = float(d.get("ebitda") or 0.0)
    lucro_liquido = float(d.get("lucro_liquido") or 0.0)

    # Se ambas as grandezas vitais estiverem ausentes, rejeita por ausência de dados reais
    if ativo_total <= 0 or receita_liquida <= 0:
        return {
            "score": 0,
            "rating": "D",
            "classificacao_risco": "DADOS_INSUFICIENTES",
            "status_decisao": "REPROVADO",
            "limite_sugerido": 0.0,
            "capacidade_pagamento_mensal": 0.0,
            "auditoria": {
                "aprovado": False,
                "status_auditoria": "REJEITADO_SEM_DADOS",
                "erros_criticos": ["Ativo Total ou Receita Líquida ausentes ou zerados no demonstrativo contábil."],
                "alertas": []
            },
            "motivo_rejeicao": ["Ativo Total ou Receita Líquida ausentes ou zerados."],
            "pontos_fortes": [],
            "pontos_atencao": ["Demonstrativo sem valores contábeis reconhecidos."],
            "indices": {},
            "contas": {},
            "gravado_supabase": False,
            "cnpj": dados.cnpj,
            "razao_social": dados.razao_social
        }

    # Cruzamento de Índices Contábeis
    liq_corrente = round(ativo_circulante / passivo_circulante, 2) if passivo_circulante > 0 else 1.5
    liq_seca = round(max(0.0, ativo_circulante - estoques) / passivo_circulante, 2) if passivo_circulante > 0 else 1.0

    exigivel_total = passivo_circulante + passivo_nao_circulante
    rlp = b.get("realizavel_longo_prazo", 0.0)
    liq_geral = round((ativo_circulante + rlp) / exigivel_total, 2) if exigivel_total > 0 else liq_corrente

    endiv_geral = round((exigivel_total / ativo_total) * 100.0, 1) if ativo_total > 0 else 45.0
    perfil_divida = round((passivo_circulante / exigivel_total) * 100.0, 1) if exigivel_total > 0 else 50.0

    margem_bruta = round((lucro_bruto / receita_liquida) * 100.0, 1) if receita_liquida > 0 else 30.0
    margem_ebitda = round((ebitda / receita_liquida) * 100.0, 1) if receita_liquida > 0 else 15.0
    margem_liquida = round((lucro_liquido / receita_liquida) * 100.0, 1) if receita_liquida > 0 else 10.0

    roe = round((lucro_liquido / patrimonio_liquido) * 100.0, 1) if patrimonio_liquido > 0 else 0.0
    roa = round((lucro_liquido / ativo_total) * 100.0, 1) if ativo_total > 0 else 0.0

    # Motor de Score IA (0 a 1000)
    score = 500
    pontos_fortes = []
    pontos_atencao = []

    # Pilar 1: Liquidez
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
        pontos_atencao.append(f"Alerta de liquidez crítica: passivo de curto prazo supera o ativo circulante ({liq_corrente}x).")

    # Pilar 2: Endividamento
    if endiv_geral <= 45.0:
        score += 140
        pontos_fortes.append(f"Baixo endividamento geral ({endiv_geral}% do ativo total).")
    elif endiv_geral <= 65.0:
        score += 50
        pontos_fortes.append(f"Endividamento moderado e controlado ({endiv_geral}%).")
    elif endiv_geral <= 80.0:
        score -= 50
        pontos_atencao.append(f"Endividamento geral elevado ({endiv_geral}%).")
    else:
        score -= 150
        pontos_atencao.append(f"Alavancagem excessiva: endividamento atinge {endiv_geral}% do ativo total.")

    if perfil_divida > 75.0 and exigivel_total > 0:
        score -= 30
        pontos_atencao.append("Concentração desproporcional da dívida no curto prazo (>75%).")

    # Pilar 3: Margens e Geração de Caixa
    if margem_liquida >= 12.0 and margem_ebitda >= 15.0:
        score += 130
        pontos_fortes.append(f"Alta rentabilidade operacional: margem líquida de {margem_liquida}% e EBITDA de {margem_ebitda}%.")
    elif margem_liquida >= 5.0:
        score += 60
        pontos_fortes.append(f"Margem de lucro consistente ({margem_liquida}%).")
    elif margem_liquida > 0:
        score += 10
        pontos_atencao.append(f"Margem líquida estreita ({margem_liquida}%).")
    else:
        score -= 140
        pontos_atencao.append(f"Resultado em prejuízo no exercício ({margem_liquida}%).")

    # Pilar 4: Retorno e Patrimônio Líquido
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

    # Incorpora eventuais alertas da auditoria nos pontos de atenção
    if auditoria.get("alertas"):
        pontos_atencao.extend(auditoria["alertas"])

    score = max(50, min(1000, score))

    # Rating e Decisão
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

    capacidade_mensal = round(max(0.0, (ebitda * 0.40) / 12.0), 2)
    limite_bruto = receita_liquida * fator_limite
    teto_pl = patrimonio_liquido * 0.50 if patrimonio_liquido > 0 else 0.0
    teto_mensal = capacidade_mensal * 6.0 if capacidade_mensal > 0 else 0.0
    
    if decisao != "REPROVADO" and teto_pl > 0 and teto_mensal > 0:
        limite_sugerido = round(min(limite_bruto, max(limite_bruto * 0.5, teto_pl), max(limite_bruto * 0.5, teto_mensal)), 2)
    else:
        limite_sugerido = round(limite_bruto, 2) if decisao != "REPROVADO" else 0.0

    agora_iso = datetime.now(timezone.utc).isoformat()

    dados_contabeis_salvar = {
        "balanco": b,
        "dre": d,
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
        "auditoria": auditoria,
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

    local_analises_cache.insert(0, registro)

    return {
        "score": score,
        "rating": rating,
        "classificacao_risco": risco,
        "status_decisao": decisao,
        "limite_sugerido": limite_sugerido,
        "capacidade_pagamento_mensal": capacidade_mensal,
        "auditoria": auditoria,
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