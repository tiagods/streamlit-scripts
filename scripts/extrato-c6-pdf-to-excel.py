"""
Extrator de extrato C6 Bank (PDF) para Excel.

Layout: Extrato mensal C6 Bank PJ
Colunas: Data lançamento | Data contábil | Tipo | Descrição | Valor
Data no formato dd/mm; valores prefixados com R$ ou -R$.
"""

import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.pdf_errors import PDFSemTextoError

REGEX_DATA    = re.compile(r'^\d{2}/\d{2}$')
REGEX_VALOR   = re.compile(r'^-?R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}$')
_RE_ANO       = re.compile(r'\b(20\d{2})\b')

_FALLBACK = {
    'data_lanc': (0,    70),
    'data_cont': (70,   135),
    'tipo':      (135,  280),
    'descricao': (280,  545),
    'valor':     (545,  700),
}


def _norm(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()


def _verificar_pdf_texto(caminho_pdf):
    """Lança PDFSemTextoError se o PDF não contiver texto extraível."""
    with pdfplumber.open(caminho_pdf) as pdf:
        tem_texto = all(pagina.extract_words() for pagina in pdf.pages)
    if hasattr(caminho_pdf, 'seek'):
        caminho_pdf.seek(0)
    if not tem_texto:
        raise PDFSemTextoError()


def agrupar_linhas(palavras, tolerancia=3):
    grupos = {}
    for p in palavras:
        y = p['top']
        chave = next((k for k in grupos if abs(y - k) <= tolerancia), None)
        if chave is None:
            chave = y
            grupos[chave] = []
        grupos[chave].append(p)
    return grupos


def linha_para_colunas(palavras_linha, limites):
    colunas = {n: '' for n in limites}
    for p in sorted(palavras_linha, key=lambda w: w['x0']):
        cx = (p['x0'] + p['x1']) / 2
        for nome, (ini, fim) in limites.items():
            if ini <= cx < fim:
                sep = ' ' if colunas[nome] else ''
                colunas[nome] += sep + p['text']
                break
    return {n: v.strip() for n, v in colunas.items()}


def detectar_limites(pdf):
    """Detecta limites de colunas a partir dos cabeçalhos 'Tipo', 'Valor' e 'Descri'."""
    for pagina in pdf.pages[:3]:
        palavras = pagina.extract_words()
        grupos   = agrupar_linhas(palavras, tolerancia=5)

        pos = {}
        data_items = []  # lista de (x0, cx) para cada ocorrência da palavra "data"

        for y in sorted(grupos.keys()):
            for p in sorted(grupos[y], key=lambda w: w['x0']):
                k  = _norm(p['text'])
                x0 = p['x0']
                cx = (p['x0'] + p['x1']) / 2
                if k == 'data':
                    data_items.append((x0, cx))
                elif k == 'tipo' and 'tipo' not in pos:
                    pos['tipo'] = (x0, cx)
                elif k.startswith('descri') and 'descricao' not in pos:
                    pos['descricao'] = (x0, cx)
                elif k == 'valor' and 'valor' not in pos:
                    pos['valor'] = (x0, cx)
                elif k == 'lancamento' and data_items and 'data_lanc' not in pos:
                    pos['data_lanc'] = data_items[0]
                elif k == 'contabil' and len(data_items) > 1 and 'data_cont' not in pos:
                    pos['data_cont'] = data_items[1]

        if 'tipo' in pos and 'valor' in pos:
            if 'data_lanc' not in pos and data_items:
                pos['data_lanc'] = data_items[0]
            if 'data_cont' not in pos and len(data_items) > 1:
                pos['data_cont'] = data_items[1]
            if 'descricao' not in pos:
                mid = (pos['tipo'][1] + pos['valor'][1]) / 2
                pos['descricao'] = (mid, mid)

            ordem = ['data_lanc', 'data_cont', 'tipo', 'descricao', 'valor']
            cols_ord = sorted(
                [(n, pos[n][0], pos[n][1]) for n in ordem if n in pos],
                key=lambda t: t[2],
            )
            if len(cols_ord) >= 3:
                pw = pagina.width + 50
                lim = {}
                for i, (n, x0, cx) in enumerate(cols_ord):
                    x_start = 0 if i == 0 else cols_ord[i][1]
                    x_end   = pw if i == len(cols_ord) - 1 else cols_ord[i + 1][1]
                    lim[n] = (x_start, x_end)
                return lim

    return _FALLBACK


def _parse_valor(v):
    v = v.strip()
    neg = v.startswith('-')
    clean = re.sub(r'[-R$\s]', '', v).replace('.', '').replace(',', '.')
    try:
        return float(clean) * (-1 if neg else 1)
    except ValueError:
        return None


def extrair_extrato_c6(caminho_pdf):
    """Extrai lançamentos do extrato C6 Bank.

    Retorna DataFrame com colunas: Data, Tipo, Descrição, Valor.
    """
    _verificar_pdf_texto(caminho_pdf)

    with pdfplumber.open(caminho_pdf) as pdf:
        limites = detectar_limites(pdf)

        # Extrai o menor ano do cabeçalho (período, não data de exportação)
        ano = None
        for pagina in pdf.pages[:2]:
            palavras = pagina.extract_words() or []
            texto    = ' '.join(p['text'] for p in palavras[:120])
            anos     = _RE_ANO.findall(texto)
            if anos:
                ano = min(anos, key=int)
                break

        dados = []

        for pagina in pdf.pages:
            palavras = pagina.extract_words()
            if not palavras:
                continue
            grupos = agrupar_linhas(palavras, tolerancia=3)

            for y in sorted(grupos.keys()):
                cols       = linha_para_colunas(grupos[y], limites)
                data_lanc  = cols.get('data_lanc', '').strip()
                tipo_col   = cols.get('tipo', '').strip()
                desc_col   = cols.get('descricao', '').strip()
                valor_col  = cols.get('valor', '').strip()

                # Pula linhas de saldo diário e cabeçalho
                linha_txt = ' '.join(cols.values()).lower()
                if 'saldo' in linha_txt and 'dia' in linha_txt:
                    continue
                if _norm(tipo_col) == 'tipo':
                    continue

                if not REGEX_DATA.match(data_lanc):
                    continue
                if not valor_col or not REGEX_VALOR.match(valor_col):
                    continue

                data = f"{data_lanc}/{ano}" if ano else data_lanc
                valor = _parse_valor(valor_col)

                dados.append({
                    'Data': data,
                    'Tipo': tipo_col,
                    'Descrição': desc_col,
                    'Valor': valor,
                })

    return pd.DataFrame(dados, columns=['Data', 'Tipo', 'Descrição', 'Valor'])


if __name__ == '__main__':
    import argparse
    import traceback

    parser = argparse.ArgumentParser(
        description='Converte extrato C6 Bank PDF para Excel.'
    )
    parser.add_argument('arquivo', nargs='?', default='extrato-c6.pdf')
    parser.add_argument('saida',   nargs='?', default='extrato_c6.xlsx')
    args = parser.parse_args()

    try:
        df = extrair_extrato_c6(args.arquivo)
        df.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df)} lançamentos → {args.saida}")
        print()
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Erro: {e}")
        traceback.print_exc()
