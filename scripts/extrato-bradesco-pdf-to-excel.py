"""
Extrator de extrato Bradesco Net Empresa (PDF) para Excel.

Layout: Extrato Consolidado / Por Período
Colunas: Data | Lançamento | Dcto. | Crédito R$ | Débito R$ | Saldo R$
Data no formato dd/mm/yyyy; créditos sem sinal, débitos com '-' no prefixo.
"""

import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.pdf_errors import PDFSemTextoError

REGEX_DATA  = re.compile(r'^\d{2}/\d{2}/\d{4}$')
REGEX_VALOR = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')

_HEADER_MAP = {
    'data':       'data',
    'lancamento': 'lancamento',
    'dcto':       'dcto',
    'dcto.':      'dcto',
    'credito':    'credito',
    'debito':     'debito',
    'saldo':      'saldo',
}

_FALLBACK = {
    'data':       (0,    90),
    'lancamento': (90,   340),
    'dcto':       (340,  400),
    'credito':    (400,  470),
    'debito':     (470,  540),
    'saldo':      (540,  650),
}

# Cabeçalhos de seções que encerram a tabela principal de lançamentos
_SECOES_FIM = (
    'ultimos lancamentos',
    'resumo do periodo',
)


def _norm(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()


def _verificar_pdf_texto(caminho_pdf, senha=None):
    """Lança PDFSemTextoError se o PDF não contiver texto extraível."""
    with pdfplumber.open(caminho_pdf, password=senha or '') as pdf:
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
    for pagina in pdf.pages[:3]:
        palavras = pagina.extract_words()
        grupos   = agrupar_linhas(palavras, tolerancia=4)
        for y in sorted(grupos.keys()):
            linha = sorted(grupos[y], key=lambda w: w['x0'])
            cols = {}
            for p in linha:
                k = _norm(p['text'])
                col = _HEADER_MAP.get(k)
                if col and col not in cols:
                    cols[col] = (p['x0'], (p['x0'] + p['x1']) / 2)
            if 'credito' in cols and 'debito' in cols and 'saldo' in cols:
                ordem = ['data', 'lancamento', 'dcto', 'credito', 'debito', 'saldo']
                cols_ord = sorted(
                    [(n, cols[n][0], cols[n][1]) for n in ordem if n in cols],
                    key=lambda t: t[2],
                )
                pw = pagina.width + 50
                lim = {}
                for i, (n, x0, cx) in enumerate(cols_ord):
                    x_start = 0 if i == 0 else cols_ord[i][1]
                    x_end   = pw if i == len(cols_ord) - 1 else cols_ord[i + 1][1]
                    lim[n] = (x_start, x_end)
                return lim
    return _FALLBACK


def _to_float(v):
    if not v or not REGEX_VALOR.match(v):
        return None
    neg = v.startswith('-')
    num = float(v.lstrip('-').replace('.', '').replace(',', '.'))
    return -num if neg else num


def extrair_extrato_bradesco(caminho_pdf, senha=None):
    """Extrai lançamentos do extrato Bradesco Net Empresa.

    Retorna DataFrame com colunas: Data, Lançamento, Dcto., Crédito, Débito, Saldo.
    """
    _verificar_pdf_texto(caminho_pdf, senha=senha)

    with pdfplumber.open(caminho_pdf, password=senha or '') as pdf:
        limites = detectar_limites(pdf)

        dados = []
        data_atual           = None
        desc_pendente        = ''
        dcto_pendente        = ''
        aguarda_continuacao  = False  # True quando valor fechou uma entrada sem desc na linha
        fim_transacoes       = False

        for pagina in pdf.pages:
            if fim_transacoes:
                break
            palavras = pagina.extract_words()
            if not palavras:
                continue
            grupos = agrupar_linhas(palavras, tolerancia=3)

            for y in sorted(grupos.keys()):
                cols      = linha_para_colunas(grupos[y], limites)
                data_col  = cols.get('data', '')
                desc_col  = cols.get('lancamento', '')
                dcto_col  = cols.get('dcto', '')
                cred_col  = cols.get('credito', '')
                deb_col   = cols.get('debito', '')
                saldo_col = cols.get('saldo', '')

                linha_norm = _norm(' '.join(cols.values()))
                if any(s in linha_norm for s in _SECOES_FIM):
                    fim_transacoes = True
                    break

                if _norm(data_col) == 'total':
                    fim_transacoes = True
                    break

                desc_norm = _norm(desc_col)
                if desc_norm == 'saldo anterior':
                    if REGEX_DATA.match(data_col):
                        data_atual = data_col
                    desc_pendente        = ''
                    dcto_pendente        = ''
                    aguarda_continuacao  = False
                    continue
                # Pula linhas de cabeçalho e totais (checa todas as colunas)
                if any(_norm(v) in ('lancamento', 'credito', 'debito', 'saldo', 'total')
                       for v in cols.values()):
                    continue

                tem_cred  = bool(cred_col and REGEX_VALOR.match(cred_col))
                tem_deb   = bool(deb_col  and REGEX_VALOR.match(deb_col))
                tem_valor = tem_cred or tem_deb

                if tem_valor:
                    if REGEX_DATA.match(data_col):
                        data_atual = data_col
                    if data_atual:
                        desc = (desc_pendente + ' ' + desc_col).strip()
                        dcto = dcto_pendente or dcto_col
                        dados.append({
                            'Data':       data_atual,
                            'Lançamento': desc,
                            'Dcto.':      dcto,
                            'Crédito':    _to_float(cred_col) if tem_cred else None,
                            'Débito':     _to_float(deb_col)  if tem_deb  else None,
                            'Saldo':      saldo_col,
                        })
                        desc_pendente  = ''
                        dcto_pendente  = ''
                        # Linha de valor sem descrição indica entrada de 2 linhas:
                        # a descrição complementar vem na linha imediatamente seguinte
                        aguarda_continuacao = (desc_col == '')
                elif REGEX_DATA.match(data_col):
                    # Linha só com data (sem valor) — início de novo bloco
                    data_atual          = data_col
                    desc_pendente       = desc_col
                    dcto_pendente       = dcto_col
                    aguarda_continuacao = False
                else:
                    # Linha sem data e sem valor
                    if aguarda_continuacao and dados and (desc_col or dcto_col):
                        # Descrição complementar da entrada de 2 linhas (vinha após o valor)
                        detalhe = (desc_col + ' ' + dcto_col).strip()
                        dados[-1]['Lançamento'] = (dados[-1]['Lançamento'] + ' ' + detalhe).strip()
                        aguarda_continuacao = False
                    elif desc_col and data_atual:
                        # Descrição pré-valor de novo lançamento
                        sep = ' ' if desc_pendente else ''
                        desc_pendente += sep + desc_col
                        aguarda_continuacao = False

    return pd.DataFrame(dados, columns=['Data', 'Lançamento', 'Dcto.', 'Crédito', 'Débito', 'Saldo'])


if __name__ == '__main__':
    import argparse
    import traceback

    parser = argparse.ArgumentParser(
        description='Converte extrato Bradesco Net Empresa PDF para Excel.'
    )
    parser.add_argument('arquivo', nargs='?', default='extrato-bradesco.pdf')
    parser.add_argument('saida',   nargs='?', default='extrato_bradesco.xlsx')
    args = parser.parse_args()

    try:
        df = extrair_extrato_bradesco(args.arquivo)
        df.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df)} lançamentos → {args.saida}")
        print()
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Erro: {e}")
        traceback.print_exc()
