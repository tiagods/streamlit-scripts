"""
Extrator universal de extratos Itaú em PDF para Excel.

Suporta dois layouts:
- Layout A (Personalite / conta premium): datas no formato dd/mm/yyyy, largura ~612pt.
  Colunas: Data | Lançamento | Valor | Saldo
- Layout B (Conta corrente / extrato mensal): datas no formato dd/mm, largura ~595pt.
  Colunas: Data | Descrição | Entradas R$ | Saídas R$ | Saldo R$
"""

import re
import unicodedata
import pdfplumber
import pandas as pd


# ---------------------------------------------------------------------------
# Padrões
# ---------------------------------------------------------------------------
REGEX_DATA_LONGA = re.compile(r'^\d{2}/\d{2}/\d{4}$')
REGEX_DATA_CURTA = re.compile(r'^\d{2}/\d{2}$')
REGEX_VALOR_BR   = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}[-+]?$')
_RE_ANO          = re.compile(r'\b(20\d{2})\b')


# ---------------------------------------------------------------------------
# Mapeamento cabeçalho → nome canônico de coluna
# ---------------------------------------------------------------------------
_HEADER_MAP = {
    'data':        'data',
    'saldo':       'saldo',
    'lancamento':  'lancamento',
    'lancamentos': 'lancamento',
    'valor':       'valor',
    'descricao':   'descricao',
    'descri':      'descricao',
    'entradas':    'entradas',
    'saidas':      'saidas',
}

_FALLBACK_A = {
    'data':       (0,   80),
    'lancamento': (80,  395),
    'valor':      (395, 490),
    'saldo':      (490, 700),
}
_FALLBACK_B = {
    'data':       (0,   180),
    'descricao':  (180, 360),
    'entradas':   (360, 420),
    'saidas':     (420, 510),
    'saldo':      (510, 700),
}


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _norm(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()


def agrupar_linhas(palavras, tolerancia=3):
    """Agrupa palavras por linha usando tolerância de pixels no eixo Y."""
    grupos = {}
    for p in palavras:
        y = p['top']
        chave = next((y_ref for y_ref in grupos if abs(y - y_ref) <= tolerancia), None)
        if chave is None:
            chave = y
            grupos[chave] = []
        grupos[chave].append(p)
    return grupos


def linha_para_colunas(palavras_linha, limites: dict) -> dict:
    """Distribui palavras de uma linha nas colunas definidas por limites (dict nome→(x0,x1))."""
    colunas = {nome: '' for nome in limites}
    for p in sorted(palavras_linha, key=lambda w: w['x0']):
        x_centro = (p['x0'] + p['x1']) / 2
        for nome, (inicio, fim) in limites.items():
            if inicio <= x_centro < fim:
                sep = ' ' if colunas[nome] else ''
                colunas[nome] += sep + p['text']
                break
    return {nome: v.strip() for nome, v in colunas.items()}


def detectar_layout(pdf):
    """Detecta o layout e calcula limites de colunas dinamicamente a partir do cabeçalho.

    Retorna (layout, limites) onde:
    - layout: 'A' (Personalite) ou 'B' (Conta corrente)
    - limites: dict {nome_coluna: (x_inicio, x_fim)}
    """
    for pagina in pdf.pages[:5]:
        palavras = pagina.extract_words()
        grupos = agrupar_linhas(palavras, tolerancia=3)

        for y in sorted(grupos.keys()):
            linha = sorted(grupos[y], key=lambda w: w['x0'])

            cols_cx = {}
            for p in linha:
                chave = _norm(p['text'])
                if chave in _HEADER_MAP and _HEADER_MAP[chave] not in cols_cx:
                    cols_cx[_HEADER_MAP[chave]] = (p['x0'] + p['x1']) / 2

            if 'data' not in cols_cx or 'saldo' not in cols_cx:
                continue

            if 'entradas' in cols_cx and 'saidas' in cols_cx:
                layout = 'B'
                ordem = ['data', 'descricao', 'entradas', 'saidas', 'saldo']
            elif 'valor' in cols_cx or 'lancamento' in cols_cx:
                layout = 'A'
                ordem = ['data', 'lancamento', 'valor', 'saldo']
            else:
                continue

            cols_ord = [(n, cols_cx[n]) for n in ordem if n in cols_cx]
            cols_ord.sort(key=lambda t: t[1])

            page_w = pagina.width + 50
            limites = {}
            for i, (nome, cx) in enumerate(cols_ord):
                x_start = 0 if i == 0 else (cols_ord[i - 1][1] + cx) / 2
                x_end   = page_w if i == len(cols_ord) - 1 else (cx + cols_ord[i + 1][1]) / 2
                limites[nome] = (x_start, x_end)

            return layout, limites

    return 'A', _FALLBACK_A


# ---------------------------------------------------------------------------
# Extração — Layout A (Personalite)
# ---------------------------------------------------------------------------

def extrair_layout_a(pdf, limites):
    """Extrai lançamentos do Layout A (Personalite, data dd/mm/yyyy)."""
    dados = []

    for pagina in pdf.pages:
        palavras = pagina.extract_words()
        if not palavras:
            continue

        grupos = agrupar_linhas(palavras, tolerancia=3)

        for y in sorted(grupos.keys()):
            cols = linha_para_colunas(grupos[y], limites)
            data       = cols.get('data', '')
            lancamento = cols.get('lancamento', '')
            valor      = cols.get('valor', '')
            saldo      = cols.get('saldo', '')

            if not REGEX_DATA_LONGA.match(data):
                continue

            if lancamento.lower() in ('lançamentos futuros', 'lancamentos futuros'):
                continue

            dados.append({'Data': data, 'Lançamento': lancamento, 'Valor': valor, 'Saldo': saldo})

    return dados


# ---------------------------------------------------------------------------
# Extração — Layout B (Conta corrente mensal)
# ---------------------------------------------------------------------------

def extrair_layout_b(pdf, limites):
    """Extrai lançamentos do Layout B (Conta corrente, data dd/mm).

    Cada linha com valor válido é um lançamento independente.
    Linhas sem data herdam data_atual. Texto de rodapé na coluna saldo é
    descartado via REGEX_VALOR_BR.
    """
    dados = []
    ano_corrente = None

    for pagina in pdf.pages:
        palavras = pagina.extract_words()
        if not palavras:
            continue

        texto_pagina = ' '.join(p['text'] for p in palavras[:30])
        m_ano = _RE_ANO.search(texto_pagina)
        if m_ano:
            ano_corrente = m_ano.group(1)

        grupos = agrupar_linhas(palavras, tolerancia=3)
        data_atual = None

        for y in sorted(grupos.keys()):
            cols = linha_para_colunas(grupos[y], limites)
            data_col  = cols.get('data', '')
            descricao = cols.get('descricao', '')
            entradas  = cols.get('entradas', '')
            saidas    = cols.get('saidas', '')
            saldo_raw = cols.get('saldo', '')

            if REGEX_DATA_CURTA.match(data_col):
                data_atual = f"{data_col}/{ano_corrente}" if ano_corrente else data_col

            if not data_atual:
                continue

            # Determina valor; linhas sem valor válido são informativas → ignora
            if saidas and REGEX_VALOR_BR.match(saidas):
                valor = '-' + saidas.rstrip('-')
            elif entradas and REGEX_VALOR_BR.match(entradas):
                valor = entradas.rstrip('+')
            else:
                continue

            # Descarta texto de rodapé que cai na coluna saldo
            saldo = saldo_raw if saldo_raw and REGEX_VALOR_BR.match(saldo_raw) else ''

            dados.append({'Data': data_atual, 'Lançamento': descricao, 'Valor': valor, 'Saldo': saldo})

    return dados


# ---------------------------------------------------------------------------
# Validação — contagem independente de lançamentos no PDF
# ---------------------------------------------------------------------------

def _contar_lancamentos_a(pdf, limites):
    """Segunda passagem no PDF contando lançamentos do Layout A sem armazenar."""
    total = 0
    for pagina in pdf.pages:
        palavras = pagina.extract_words()
        if not palavras:
            continue
        grupos = agrupar_linhas(palavras, tolerancia=3)
        for y in sorted(grupos.keys()):
            cols = linha_para_colunas(grupos[y], limites)
            data       = cols.get('data', '')
            lancamento = cols.get('lancamento', '')
            if not REGEX_DATA_LONGA.match(data):
                continue
            if lancamento.lower() in ('lançamentos futuros', 'lancamentos futuros'):
                continue
            total += 1
    return total


def _contar_lancamentos_b(pdf, limites):
    """Segunda passagem no PDF contando lançamentos do Layout B sem armazenar."""
    total = 0
    ano = None
    for pagina in pdf.pages:
        palavras = pagina.extract_words()
        if not palavras:
            continue
        texto = ' '.join(p['text'] for p in palavras[:30])
        m = _RE_ANO.search(texto)
        if m:
            ano = m.group(1)
        grupos = agrupar_linhas(palavras, tolerancia=3)
        data_atual = None
        for y in sorted(grupos.keys()):
            cols = linha_para_colunas(grupos[y], limites)
            dc  = cols.get('data', '')
            ent = cols.get('entradas', '')
            sai = cols.get('saidas', '')
            if REGEX_DATA_CURTA.match(dc):
                data_atual = f"{dc}/{ano}" if ano else dc
            if not data_atual:
                continue
            if not (sai and REGEX_VALOR_BR.match(sai)) and not (ent and REGEX_VALOR_BR.match(ent)):
                continue
            total += 1
    return total


def _validar_contagem(pdf, layout, limites, df):
    """Compara total extraído com contagem independente no PDF.

    Lança ValueError se os números divergirem.
    """
    if layout == 'A':
        esperado = _contar_lancamentos_a(pdf, limites)
    else:
        esperado = _contar_lancamentos_b(pdf, limites)

    extraido = len(df)
    if extraido != esperado:
        raise ValueError(
            f"[ERRO] Validacao falhou: PDF contem {esperado} lancamentos, "
            f"mas foram extraidos {extraido} (diferenca: {extraido - esperado:+d}). "
            f"Verifique o arquivo gerado."
        )
    print(f"[OK] Validacao: {extraido} lancamentos extraidos == {esperado} no PDF")


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------

def extrair_extrato_itau(caminho_pdf):
    """Extrai lançamentos de qualquer extrato Itaú em PDF.

    Detecta automaticamente o layout (A = Personalite; B = Conta corrente),
    calcula limites de colunas dinamicamente e valida a contagem extraída
    contra uma segunda passagem independente no PDF.

    Retorna um DataFrame com colunas: Data, Lançamento, Valor, Saldo.
    Lança ValueError se a contagem não conferir.
    """
    with pdfplumber.open(caminho_pdf) as pdf:
        layout, limites = detectar_layout(pdf)
        print(f"[INFO] Layout detectado: {layout!r} ({'Personalite' if layout == 'A' else 'Conta corrente'})")

        if layout == 'A':
            dados = extrair_layout_a(pdf, limites)
        else:
            dados = extrair_layout_b(pdf, limites)

        df = pd.DataFrame(dados, columns=['Data', 'Lançamento', 'Valor', 'Saldo'])
        _validar_contagem(pdf, layout, limites, df)

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Converte extrato Itaú PDF para Excel (suporta múltiplos modelos).'
    )
    parser.add_argument('arquivo', nargs='?', default='extrato-itau.pdf',
                        help='Caminho do PDF (padrão: extrato-itau.pdf)')
    parser.add_argument('saida', nargs='?', default='extrato_itau.xlsx',
                        help='Caminho do Excel de saída (padrão: extrato_itau.xlsx)')
    args = parser.parse_args()

    try:
        df = extrair_extrato_itau(args.arquivo)
        df.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df)} lancamentos extraidos -> {args.saida}")
        print()
        print(df.to_string(index=False))
    except Exception as e:
        import traceback
        print(f"Erro: {e}")
        traceback.print_exc()
