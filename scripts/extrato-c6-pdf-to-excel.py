"""
Extrator de extrato C6 Bank (PDF) para Excel.

Layout: Extrato mensal C6 Bank PJ
Colunas: Data lançamento | Data contábil | Tipo | Descrição | Valor
Datas no formato dd/mm; valores têm R$ como token separado do número.
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
_RE_DATA_FULL = re.compile(r'\d{2}/\d{2}/(\d{4})')   # captura ano de cabeçalhos de mês
_RE_SUFIXO_RS = re.compile(r'\s*(-?R\$)\s*$')         # R$ que caiu na coluna de descrição

_FALLBACK = {
    'data_lanc': (0,    70),
    'data_cont': (70,   135),
    'tipo':      (135,  280),
    'descricao': (280,  545),
    'valor':     (545,  700),
}


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
    """Detecta limites de colunas a partir dos cabeçalhos 'Tipo', 'Valor' e 'Descri'."""
    for pagina in pdf.pages[:3]:
        palavras = pagina.extract_words()
        grupos   = agrupar_linhas(palavras, tolerancia=5)

        pos = {}
        data_items = []

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


def _contar_lancamentos_c6(pdf, limites):
    """Segunda passagem independente: conta lançamentos sem armazenar dados."""
    total = 0
    for pagina in pdf.pages:
        palavras = pagina.extract_words()
        if not palavras:
            continue
        grupos = agrupar_linhas(palavras, tolerancia=3)
        for y in sorted(grupos.keys()):
            linha_bruta = ' '.join(
                p['text'] for p in sorted(grupos[y], key=lambda w: w['x0'])
            )
            if _RE_DATA_FULL.search(linha_bruta):
                continue
            cols      = linha_para_colunas(grupos[y], limites)
            data_lanc = cols.get('data_lanc', '').strip()
            desc_col  = cols.get('descricao', '').strip()
            valor_col = cols.get('valor', '').strip()
            m_rs = _RE_SUFIXO_RS.search(desc_col)
            if m_rs and valor_col and re.match(r'^\d', valor_col):
                valor_col = m_rs.group(1) + ' ' + valor_col
            linha_norm = _norm(linha_bruta)
            if 'saldo' in linha_norm and 'dia' in linha_norm:
                continue
            if REGEX_DATA.match(data_lanc) and valor_col and REGEX_VALOR.match(valor_col):
                total += 1
    return total


def _validar_contagem(pdf, limites, df):
    """Compara total extraído com contagem independente no PDF. Lança ValueError se divergir."""
    esperado = _contar_lancamentos_c6(pdf, limites)
    extraido = len(df)
    if extraido != esperado:
        raise ValueError(
            f"[ERRO] Validacao falhou: PDF contem {esperado} lancamentos, "
            f"mas foram extraidos {extraido} (diferenca: {extraido - esperado:+d}). "
            f"Verifique o arquivo gerado."
        )
    print(f"[OK] Validacao: {extraido} lancamentos extraidos == {esperado} no PDF")


def _parse_valor(v):
    v = v.strip()
    neg = v.startswith('-')
    clean = re.sub(r'[-R$\s]', '', v).replace('.', '').replace(',', '.')
    try:
        return float(clean) * (-1 if neg else 1)
    except ValueError:
        return None


def extrair_extrato_c6(caminho_pdf, senha=None):
    """Extrai lançamentos do extrato C6 Bank.

    Retorna DataFrame com colunas: Data, Data Contábil, Tipo, Descrição, Valor.
    """
    _verificar_pdf_texto(caminho_pdf, senha=senha)

    with pdfplumber.open(caminho_pdf, password=senha or '') as pdf:
        limites = detectar_limites(pdf)

        dados = []
        ano_atual           = None
        desc_pendente       = ''   # descrição de linha anterior à linha de data+valor
        aguarda_continuacao = False  # True após linha de valor sem descrição inline

        for pagina in pdf.pages:
            palavras = pagina.extract_words()
            if not palavras:
                continue
            grupos = agrupar_linhas(palavras, tolerancia=3)

            for y in sorted(grupos.keys()):
                linha_bruta = ' '.join(
                    p['text'] for p in sorted(grupos[y], key=lambda w: w['x0'])
                )

                # Cabeçalhos de mês contêm data completa dd/mm/yyyy: atualiza ano e pula a linha
                m_ano = _RE_DATA_FULL.search(linha_bruta)
                if m_ano:
                    ano_atual           = m_ano.group(1)
                    desc_pendente       = ''
                    aguarda_continuacao = False
                    continue

                cols      = linha_para_colunas(grupos[y], limites)
                data_lanc = cols.get('data_lanc', '').strip()
                data_cont = cols.get('data_cont', '').strip()
                tipo_col  = cols.get('tipo', '').strip()
                desc_col  = cols.get('descricao', '').strip()
                valor_col = cols.get('valor', '').strip()

                # R$ pode cair na coluna de descrição quando o valor é grande e o token
                # fica à esquerda do limite da coluna valor. Resgata para valor_col.
                m_rs = _RE_SUFIXO_RS.search(desc_col)
                if m_rs and valor_col and re.match(r'^\d', valor_col):
                    valor_col = m_rs.group(1) + ' ' + valor_col
                    desc_col  = desc_col[:m_rs.start()].strip()

                # Pula linhas de saldo diário e de cabeçalho de coluna
                linha_norm = _norm(linha_bruta)
                if 'saldo' in linha_norm and 'dia' in linha_norm:
                    aguarda_continuacao = False
                    continue
                if _norm(tipo_col) == 'tipo':
                    continue

                tem_data  = bool(REGEX_DATA.match(data_lanc))
                tem_valor = bool(valor_col and REGEX_VALOR.match(valor_col))

                if tem_data and tem_valor:
                    data = f"{data_lanc}/{ano_atual}" if ano_atual else data_lanc
                    dc   = f"{data_cont}/{ano_atual}" if (data_cont and ano_atual) else data_cont
                    desc = (desc_pendente + ' ' + desc_col).strip()
                    dados.append({
                        'Data':          data,
                        'Data Contábil': dc,
                        'Tipo':          tipo_col,
                        'Descrição':     desc,
                        'Valor':         _parse_valor(valor_col),
                    })
                    desc_pendente       = ''
                    # Aguarda continuação se a linha de valor não trouxe descrição inline
                    aguarda_continuacao = (desc_col == '')

                elif tem_data and not tem_valor:
                    # Linha de data sem valor: guarda como pré-descrição do próximo lançamento
                    desc_pendente       = desc_col
                    aguarda_continuacao = False

                elif not tem_data and desc_col and data_lanc == '':
                    if aguarda_continuacao and dados:
                        dados[-1]['Descrição'] = (
                            dados[-1]['Descrição'] + ' ' + desc_col
                        ).strip()
                        aguarda_continuacao = False
                    elif not aguarda_continuacao:
                        sep = ' ' if desc_pendente else ''
                        desc_pendente += sep + desc_col

        colunas = ['Data', 'Data Contábil', 'Tipo', 'Descrição', 'Valor']
        df = pd.DataFrame(dados, columns=colunas)
        _validar_contagem(pdf, limites, df)

    return df


if __name__ == '__main__':
    import argparse
    import traceback

    parser = argparse.ArgumentParser(
        description='Converte extrato C6 Bank PDF para Excel.'
    )
    parser.add_argument('arquivo', nargs='?', default='extrato-c6.pdf')
    parser.add_argument('saida',   nargs='?', default='extrato_c6.xlsx')
    parser.add_argument('--senha', default=None, help='Senha do PDF (se protegido)')
    args = parser.parse_args()

    try:
        df = extrair_extrato_c6(args.arquivo, senha=args.senha)
        df.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df)} lancamentos -> {args.saida}")
        print()
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Erro: {e}")
        traceback.print_exc()
