"""
Extrator de extrato Santander Empresas PJ (PDF) para Excel.

Layout: Extrato Consolidado Inteligente
Colunas: Data | Descrição | Nº Documento | Créditos R$ | Débitos R$ | Saldo R$
Data no formato dd/mm; créditos sem sinal, débitos com '-' no sufixo.
"""

import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.pdf_errors import PDFSemTextoError

REGEX_DATA  = re.compile(r'^\d{2}/\d{2}$')
REGEX_VALOR = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}-?$')
_RE_ANO     = re.compile(r'\b(20\d{2})\b')

_HEADER_MAP = {
    'data':         'data',
    'descricao':    'descricao',
    'descri':       'descricao',
    'no':           'ndoc',
    'documento':    'ndoc',
    'ndocumento':   'ndoc',    # "N°Documento" extraído como palavra única
    'nodocumento':  'ndoc',    # idem, quando a fonte decodifica "°" como "o"
    'creditos':     'credito',
    'debitos':      'debito',
    'saldo':        'saldo',
    'saldo(r$)':    'saldo',   # "Saldo(R$)" extraído como palavra única
    'saldo(r':      'saldo',   # variante por truncamento de codificação
}

# Posições reais medidas no PDF (página width ≈ 595):
#   Data x0=34, Descrição x0=65, N°Documento x0=296,
#   Créditos x0=384, Débitos x0=435, Saldo x0=508
# Os valores monetários são alinhados à DIREITA (x1 fixo por coluna):
#   Créditos x1≈405, Débitos x1≈456, Saldo x1≈540
_FALLBACK = {
    'data':      (0,    65),
    'descricao': (65,   296),
    'ndoc':      (296,  384),
    'credito':   (384,  435),
    'debito':    (435,  508),
    'saldo':     (508,  650),
}

# Cabeçalhos de seções não-transacionais que encerram a tabela de lançamentos
_SECOES_FIM = (
    'saldos por periodo',
    'investimentos',
    'debito automatico em conta corrente',
    'pacote de servicos',
    'indices economicos',
    'taxa de juros',
)

# Tokens que identificam linhas de rodapé/marca d'água do PDF (não são lançamentos)
_RODAPE_TOKENS = (
    'extrato_pj_a4',
    'balp_',
)


def _norm(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()


def _extrair_palavras(pagina, tolerancia_y=3):
    """Extrai palavras a partir de chars, inserindo quebras onde o PDF usa avanço
    de caráter para criar espaço visual sem espaço real no stream de texto.

    O Santander renderiza "IOF IMPOSTO OPERACOES FINANCEIRAS" como uma sequência
    contínua de chars com gaps de ~1-3pt entre as palavras. extract_words() com
    x_tolerance=3 une tudo numa só string. Aqui usamos a largura média dos chars
    da linha para estimar um limiar dinâmico.
    """
    chars = [c for c in (pagina.chars or []) if c.get('text', '').strip()]
    if not chars:
        return pagina.extract_words()

    grupos_y = {}
    for ch in chars:
        y = ch['top']
        chave = next((k for k in grupos_y if abs(y - k) <= tolerancia_y), None)
        if chave is None:
            chave = y
            grupos_y[chave] = []
        grupos_y[chave].append(ch)

    resultado = []
    for y_key in sorted(grupos_y.keys()):
        linha = sorted(grupos_y[y_key], key=lambda c: c['x0'])
        if not linha:
            continue

        larguras = [c['width'] for c in linha if c.get('width', 0) > 0]
        larg_media = (sum(larguras) / len(larguras)) if larguras else 5.0
        # Gap > 30% da largura média = nova palavra
        threshold = max(larg_media * 0.30, 1.0)

        grupo = [linha[0]]
        for ch in linha[1:]:
            gap = ch['x0'] - grupo[-1]['x1']
            if gap >= threshold:
                texto = ''.join(c['text'] for c in grupo)
                resultado.append({
                    'text':   texto,
                    'x0':     grupo[0]['x0'],
                    'x1':     grupo[-1]['x1'],
                    'top':    y_key,
                    'bottom': max(c.get('bottom', y_key + 10) for c in grupo),
                })
                grupo = [ch]
            else:
                grupo.append(ch)

        if grupo:
            texto = ''.join(c['text'] for c in grupo)
            resultado.append({
                'text':   texto,
                'x0':     grupo[0]['x0'],
                'x1':     grupo[-1]['x1'],
                'top':    y_key,
                'bottom': max(c.get('bottom', y_key + 10) for c in grupo),
            })

    return resultado


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


def linha_para_colunas(palavras_linha, limites, regex_valor=None):
    """Classifica palavras por coluna.

    Tokens que correspondem a regex_valor (valores monetários) são classificados
    pelo x1 (borda direita), pois o Santander alinha valores à direita.
    Demais tokens usam o centro (cx).
    """
    colunas = {n: '' for n in limites}
    for p in sorted(palavras_linha, key=lambda w: w['x0']):
        ref = p['x1'] if (regex_valor and regex_valor.match(p['text'])) else (p['x0'] + p['x1']) / 2
        for nome, (ini, fim) in limites.items():
            if ini <= ref < fim:
                sep = ' ' if colunas[nome] else ''
                colunas[nome] += sep + p['text']
                break
    return {n: v.strip() for n, v in colunas.items()}


def detectar_limites(pdf):
    """Detecta os limites de coluna a partir do cabeçalho do PDF.

    O Santander usa um cabeçalho de DUAS linhas:
      Linha 1: Data | Descrição | N°Documento | Movimentos(R$) | Saldo(R$)
      Linha 2:                                 | Créditos | Débitos

    A detecção tenta primeiro uma linha única; caso não encontre saldo na mesma
    linha que Créditos/Débitos, procura saldo em linhas adjacentes (até 20pt).
    """
    ordem = ['data', 'descricao', 'ndoc', 'credito', 'debito', 'saldo']

    def _extrair_cols_linha(linha):
        cols = {}
        for p in linha:
            k = _norm(p['text'])
            col = _HEADER_MAP.get(k)
            if col and col not in cols:
                cols[col] = (p['x0'], (p['x0'] + p['x1']) / 2)
        return cols

    def _calcular_limites(cols, pw):
        cols_ord = sorted(
            [(n, cols[n][0], cols[n][1]) for n in ordem if n in cols],
            key=lambda t: t[2],
        )
        lim = {}
        for i, (n, x0, cx) in enumerate(cols_ord):
            x_start = 0 if i == 0 else cols_ord[i][1]
            x_end   = pw if i == len(cols_ord) - 1 else cols_ord[i + 1][1]
            lim[n] = (x_start, x_end)
        return lim

    for pagina in pdf.pages[:5]:
        palavras  = pagina.extract_words()
        grupos    = agrupar_linhas(palavras, tolerancia=4)
        ys_sorted = sorted(grupos.keys())
        pw        = pagina.width + 50

        for y in ys_sorted:
            linha = sorted(grupos[y], key=lambda w: w['x0'])
            cols  = _extrair_cols_linha(linha)

            # Detecção em linha única (bancos com cabeçalho simples)
            if 'credito' in cols and 'debito' in cols and 'saldo' in cols:
                return _calcular_limites(cols, pw)

            # Detecção em duas linhas (Santander): Créditos/Débitos numa linha,
            # Saldo numa linha adjacente (tipicamente 12pt acima)
            if 'credito' in cols and 'debito' in cols:
                for y2 in ys_sorted:
                    if y2 == y or abs(y2 - y) > 20:
                        continue
                    linha2 = sorted(grupos[y2], key=lambda w: w['x0'])
                    cols2  = _extrair_cols_linha(linha2)
                    merged = {**cols2, **cols}  # cols tem prioridade (credito/debito)
                    if 'saldo' in merged:
                        return _calcular_limites(merged, pw)

    return _FALLBACK


def _to_float(v):
    if not v or not REGEX_VALOR.match(v):
        return None
    neg = v.endswith('-')
    num = float(v.rstrip('-').replace('.', '').replace(',', '.'))
    return -num if neg else num


def extrair_extrato_santander(caminho_pdf, senha=None):
    """Extrai lançamentos do extrato Santander PJ.

    Retorna DataFrame com colunas: Data, Descrição, Crédito, Débito, Saldo.

    Usa duas passagens sobre o PDF (dentro do mesmo contexto pdfplumber):
      Passagem 1 — extract_words(): classificação de colunas e extração de valores;
                   cada lançamento acumula as posições (pag, y) das linhas que
                   formam sua descrição.
      Passagem 2 — _extrair_palavras(): lê os chars do PDF para reconstruir os
                   textos da coluna Descrição com os espaços visuais corretos.
    """
    _verificar_pdf_texto(caminho_pdf, senha=senha)

    with pdfplumber.open(caminho_pdf, password=senha or '') as pdf:
        limites = detectar_limites(pdf)

        ano = None
        for pagina in pdf.pages[:2]:
            texto = ' '.join(p['text'] for p in (pagina.extract_words() or [])[:80])
            m = _RE_ANO.search(texto)
            if m:
                ano = m.group(1)
                break

        # ── Passagem 1: valores e posições ───────────────────────────────────
        dados = []
        data_atual           = None
        desc_pendente        = ''
        desc_pendente_linhas = []   # posições (pag_idx, round(y)) de desc_pendente
        aguarda_continuacao  = False
        fim_transacoes       = False

        for pag_idx, pagina in enumerate(pdf.pages):
            if fim_transacoes:
                break
            palavras = pagina.extract_words()
            if not palavras:
                continue
            grupos = agrupar_linhas(palavras, tolerancia=3)

            for y in sorted(grupos.keys()):
                cols      = linha_para_colunas(grupos[y], limites, regex_valor=REGEX_VALOR)
                data_col  = cols.get('data', '')
                desc_col  = cols.get('descricao', '')
                ndoc_col  = cols.get('ndoc', '')
                cred_col  = cols.get('credito', '')
                deb_col   = cols.get('debito', '')
                saldo_col = cols.get('saldo', '')

                # N°Doc: descarta placeholders ('-') e valores monetários
                ndoc_doc = (
                    ndoc_col.strip()
                    if ndoc_col and ndoc_col.strip() not in ('', '-')
                       and not REGEX_VALOR.match(ndoc_col)
                    else None
                )

                linha_txt  = ' '.join(cols.values()).lower()
                linha_norm = _norm(linha_txt)

                if any(s in linha_norm for s in _SECOES_FIM):
                    fim_transacoes = True
                    break

                if 'saldo em' in linha_txt or 'saldoem' in linha_norm:
                    data_atual           = None
                    desc_pendente        = ''
                    desc_pendente_linhas = []
                    aguarda_continuacao  = False
                    continue

                if _norm(data_col) == 'data':
                    aguarda_continuacao = False
                    continue
                if any(t in _norm(desc_col) for t in _RODAPE_TOKENS):
                    continue

                tem_cred  = bool(cred_col and REGEX_VALOR.match(cred_col))
                tem_deb   = bool(deb_col  and REGEX_VALOR.match(deb_col))
                tem_valor = tem_cred or tem_deb

                saldo_efetivo = _to_float(saldo_col) if (saldo_col and REGEX_VALOR.match(saldo_col)) else None
                pos_atual     = (pag_idx, round(y))

                if REGEX_DATA.match(data_col):
                    data_atual = f"{data_col}/{ano}" if ano else data_col
                    if tem_valor:
                        dados.append({
                            'Data':      data_atual,
                            'Descrição': desc_col,
                            'N°Doc':     ndoc_doc,
                            'Crédito':   _to_float(cred_col) if tem_cred else None,
                            'Débito':    _to_float(deb_col)  if tem_deb  else None,
                            'Saldo':     saldo_efetivo,
                            '_linhas':   desc_pendente_linhas + [pos_atual],
                        })
                        desc_pendente        = ''
                        desc_pendente_linhas = []
                        aguarda_continuacao  = True
                    else:
                        desc_pendente        = desc_col
                        desc_pendente_linhas = [pos_atual]
                        aguarda_continuacao  = False
                else:
                    if tem_valor and data_atual:
                        desc = (desc_pendente + ' ' + desc_col).strip()
                        dados.append({
                            'Data':      data_atual,
                            'Descrição': desc,
                            'N°Doc':     ndoc_doc,
                            'Crédito':   _to_float(cred_col) if tem_cred else None,
                            'Débito':    _to_float(deb_col)  if tem_deb  else None,
                            'Saldo':     saldo_efetivo,
                            '_linhas':   desc_pendente_linhas + [pos_atual],
                        })
                        desc_pendente        = ''
                        desc_pendente_linhas = []
                        aguarda_continuacao  = True
                    elif desc_col and data_atual:
                        if aguarda_continuacao and dados:
                            dados[-1]['Descrição'] = (dados[-1]['Descrição'] + ' ' + desc_col).strip()
                            dados[-1]['_linhas'].append(pos_atual)
                        else:
                            sep = ' ' if desc_pendente else ''
                            desc_pendente += sep + desc_col
                            desc_pendente_linhas.append(pos_atual)

        # ── Passagem 2: reconstrói descrições com espaços corretos ───────────
        desc_map = {}   # {(pag_idx, round(y)): texto_espaçado}
        for pag_idx, pagina in enumerate(pdf.pages):
            for y_key, ws in agrupar_linhas(_extrair_palavras(pagina), tolerancia=3).items():
                cols_e = linha_para_colunas(ws, limites, regex_valor=REGEX_VALOR)
                desc   = cols_e.get('descricao', '')
                if desc:
                    desc_map[(pag_idx, round(y_key))] = desc

        for row in dados:
            linhas = row.pop('_linhas')
            partes = [desc_map.get(pos, '') for pos in linhas]
            desc_e = ' '.join(p for p in partes if p).strip()
            if desc_e:
                row['Descrição'] = desc_e

    return pd.DataFrame(dados, columns=['Data', 'Descrição', 'N°Doc', 'Crédito', 'Débito', 'Saldo'])


if __name__ == '__main__':
    import argparse
    import traceback

    parser = argparse.ArgumentParser(
        description='Converte extrato Santander PJ PDF para Excel.'
    )
    parser.add_argument('arquivo', nargs='?', default='extrato-santander.pdf')
    parser.add_argument('saida',   nargs='?', default='extrato_santander.xlsx')
    args = parser.parse_args()

    try:
        df = extrair_extrato_santander(args.arquivo)
        df.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df)} lancamentos -> {args.saida}")
        print()
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Erro: {e}")
        traceback.print_exc()
