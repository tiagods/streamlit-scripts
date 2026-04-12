import re
import pdfplumber
import pandas as pd

# Limites de colunas calibrados para o extrato Itaú
# Baseados nos centros (x0+x1)/2 das palavras encontradas no PDF
LIMITES_COLUNAS = [
    (0, 80),     # Data: datas ficam em x0=30.6, x1=87, centro ~58
    (80, 395),   # Lançamento: descrições iniciam em x0=95.8, centro ~130-270
    (395, 490),  # Valor: alinhado à direita em x1=459.4, centro ~435-450
    (490, 600),  # Saldo: somente em linhas "SALDO TOTAL", centro ~542
]

REGEX_DATA = re.compile(r'^\d{2}/\d{2}')


def agrupar_linhas(palavras, tolerancia=3):
    """Agrupa palavras por linha usando tolerância de pixels no eixo Y.

    O pdfplumber pode reportar palavras da mesma linha física com valores
    de 'top' ligeiramente diferentes. Uma tolerância de 3 pontos resolve
    esse problema sem fundir linhas distintas (espaçamento ~18pt no extrato).
    """
    grupos = {}
    for p in palavras:
        y = p['top']
        chave = next((y_ref for y_ref in grupos if abs(y - y_ref) <= tolerancia), None)
        if chave is None:
            chave = y
            grupos[chave] = []
        grupos[chave].append(p)
    return grupos


def linha_para_colunas(palavras_linha):
    """Distribui as palavras de uma linha nas 4 colunas pelo centro X."""
    colunas = ["", "", "", ""]
    for p in sorted(palavras_linha, key=lambda w: w['x0']):
        x_centro = (p['x0'] + p['x1']) / 2
        for i, (inicio, fim) in enumerate(LIMITES_COLUNAS):
            if inicio <= x_centro < fim:
                sep = " " if colunas[i] else ""
                colunas[i] += sep + p['text']
                break
    return [c.strip() for c in colunas]


def extrair_extrato_itau(caminho_pdf, incluir_saldo_diario=False):
    """Extrai lançamentos do extrato Itaú em PDF.

    Retorna um DataFrame com as colunas: Data, Lançamento, Valor, Saldo.
    Cada lançamento ocupa exatamente uma linha.

    Args:
        caminho_pdf: caminho para o arquivo PDF do extrato.
        incluir_saldo_diario: se True, inclui as linhas "SALDO TOTAL DISPONÍVEL DIA"
            com o valor do saldo na coluna Saldo. Útil para balanços e conferência
            de fechamento diário. Por padrão False (apenas lançamentos).
    """
    dados = []

    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            palavras = pagina.extract_words()
            if not palavras:
                continue

            grupos = agrupar_linhas(palavras, tolerancia=3)

            for y in sorted(grupos.keys()):
                data, lancamento, valor, saldo = linha_para_colunas(grupos[y])

                # Ignora linhas sem data válida no início
                # (cabeçalhos, texto legal, separadores de seção, etc.)
                if not REGEX_DATA.match(data):
                    continue

                # Linhas de saldo diário ("SALDO TOTAL DISPONÍVEL DIA")
                if lancamento.upper().startswith('SALDO'):
                    if incluir_saldo_diario:
                        dados.append({
                            'Data': data,
                            'Lançamento': lancamento,
                            'Valor': valor,
                            'Saldo': saldo,
                        })
                    continue

                # Ignora cabeçalhos de seção ("data lançamentos futuros valor saldo")
                if lancamento.lower() in ('lançamentos futuros', 'lancamentos futuros'):
                    continue

                dados.append({
                    'Data': data,
                    'Lançamento': lancamento,
                    'Valor': valor,
                    'Saldo': saldo,
                })

    df = pd.DataFrame(dados, columns=['Data', 'Lançamento', 'Valor', 'Saldo'])
    df = df.drop_duplicates()
    return df


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Converte extrato Itaú PDF para Excel.')
    parser.add_argument('arquivo', nargs='?', default='extrato-itau.pdf',
                        help='Caminho do PDF (padrão: extrato-itau.pdf)')
    parser.add_argument('saida', nargs='?', default='extrato_itau_v2.xlsx',
                        help='Caminho do Excel de saída (padrão: extrato_itau_v2.xlsx)')
    parser.add_argument('-s', '--saldo', action='store_true',
                        help='Inclui linhas "SALDO TOTAL DISPONÍVEL DIA" com o saldo diário')
    args = parser.parse_args()

    try:
        df = extrair_extrato_itau(args.arquivo, incluir_saldo_diario=args.saldo)
        df.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df)} lancamentos extraidos -> {args.saida}")
        print()
        print(df.to_string(index=False))
    except Exception as e:
        import traceback
        print(f"Erro: {e}")
        traceback.print_exc()
