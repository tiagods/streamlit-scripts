import re
import pandas as pd
from io import BytesIO
from datetime import datetime


def carregar_arquivo(file):
    """Carrega um arquivo Excel sem cabeçalho."""
    df = pd.read_excel(file, header=None)
    return df


def encontrar_linha_colunas(nome, df, nome_colunas):
    """Encontra o índice da linha que contém todos os nomes de colunas esperados.

    Args:
        nome: nome do arquivo (para mensagens de erro).
        df: DataFrame sem cabeçalho.
        nome_colunas: lista de strings que devem aparecer na linha de cabeçalho.

    Returns:
        Índice (int) da linha de cabeçalho.

    Raises:
        ValueError: se o arquivo estiver vazio ou a linha não for encontrada.
    """
    if df.empty:
        raise ValueError(f"O arquivo {nome} está vazio.")

    for i, linha in df.iterrows():
        if all(col in linha.values for col in nome_colunas):
            return i

    raise ValueError(
        f"Nenhuma linha contendo os nomes das colunas foi encontrada no arquivo {nome}."
    )


def gerar_extrato(nome, df_modificado):
    """Extrai lançamentos com notas fiscais do DataFrame do extrato.

    Args:
        nome: nome do arquivo (para mensagens de erro).
        df_modificado: DataFrame com colunas Data, Lançamento, Valor (R$), Notas Fiscais.

    Returns:
        Tupla (extrato, erros):
            extrato: lista de dicts com os lançamentos encontrados.
            erros: lista de strings descrevendo os lançamentos ignorados.
    """
    extrato = []
    erros = []

    for index, row in df_modificado.iterrows():
        texto = row['Notas Fiscais']
        data = row['Data']
        valor = row['Valor (R$)']

        texto_limpo = re.sub(r"\s*(\d)\s+(\d)\s*", r"\1\2", texto, flags=re.IGNORECASE)
        texto_limpo = re.sub(r"NFS-?e(\d+)", r"NFS-e \1", texto_limpo, flags=re.IGNORECASE)
        texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()

        padrao = r"nfs-?e\s+?(\d+)"
        numeros_notas = re.findall(padrao, texto_limpo, flags=re.IGNORECASE)
        lista_inteiros = [int(x) for x in numeros_notas if x is not None]

        if data == '':
            erros.append(f"{nome}: Nenhuma data encontrada para o lançamento {index}")
            continue

        dataStr = datetime.strftime(data, '%m/%d/%Y')

        if valor == '':
            erros.append(f"{nome}: Nenhuma valor encontrado para o lançamento {index}")
            continue

        if len(lista_inteiros) == 0:
            erros.append(
                f"{nome}: Nenhuma nota fiscal encontrada para o lançamento {index}, {texto}, {texto_limpo}"
            )
            continue

        extrato.append({
            'index': index,
            'data': dataStr,
            'lançamento': row['Lançamento'],
            'valor': valor,
            'notas': lista_inteiros,
            'nfs': "NF N " + str(lista_inteiros[0]) + "".join(
                [", " + str(num) for num in lista_inteiros[1:]]
            ),
        })

    return extrato, erros


def conciliar_extrato(extrato, df_servicos):
    """Concilia o extrato com o arquivo de acompanhamento de serviços.

    Args:
        extrato: lista de dicts gerada por gerar_extrato().
        df_servicos: DataFrame com colunas Nota e Cliente.

    Returns:
        Tupla (df_conciliado, erros):
            df_conciliado: DataFrame com as colunas do arquivo de escrituração.
            erros: lista de strings descrevendo lançamentos sem correspondência.
    """
    colunas = [
        "Data",
        "Cód. Conta Debito",
        "Cód. Conta Credito",
        "Valor",
        "Cód. Histórico",
        "Complemento Histórico",
        "Inicia Lote",
        "Código Matriz/Filial",
        "Centro de Custo Débito",
        "Centro de Custo Crédito",
    ]
    df_conciliado = pd.DataFrame(columns=colunas)
    erros = []

    for ext in extrato:
        df_result = df_servicos[df_servicos["Nota"].isin(ext["notas"])]
        if df_result.empty:
            erros.append(
                f"Nenhuma nota no arquivo Acompanhamentos de Serviços foi encontrada. "
                f"Dados do extrato: data={ext['data']}, notas={ext['notas']}, "
                f"valor={ext['valor']}, nfs={ext['nfs']}, "
                f"lancamento={ext['lançamento']}, linha={ext['index']}"
            )
        else:
            cliente = df_result['Cliente'].values[0]
            df_conciliado.loc[len(df_conciliado)] = [
                ext["data"], "10008", "31577", ext["valor"], "132",
                ext["nfs"] + " " + cliente, "", 2194, "", "",
            ]

    return df_conciliado, erros


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Concilia extrato bancário com acompanhamento de serviços.'
    )
    parser.add_argument('extrato', help='Caminho do Excel de extrato')
    parser.add_argument('servicos', help='Caminho do Excel de acompanhamento de serviços')
    parser.add_argument('saida', nargs='?', default='escrituracao.xlsx',
                        help='Caminho do Excel de saída (padrão: escrituracao.xlsx)')
    args = parser.parse_args()

    try:
        df_ext = carregar_arquivo(args.extrato)
        linha_ext = encontrar_linha_colunas(
            'Extrato', df_ext,
            ["Data", "Lançamento", "Valor (R$)", "Saldo (R$)"]
        )
        df_ext_cab = pd.read_excel(args.extrato, header=linha_ext)
        df_ext_cab = df_ext_cab.drop(df_ext_cab.columns[0], axis=1)
        df_ext_cab.rename(columns={df_ext_cab.columns[-1]: 'Notas Fiscais'}, inplace=True)

        extrato, erros_ext = gerar_extrato('Extrato', df_ext_cab)
        print(f"{len(extrato)} lançamentos extraídos. {len(erros_ext)} ignorados.")

        df_srv = carregar_arquivo(args.servicos)
        linha_srv = encontrar_linha_colunas(
            'Acompanhamento de Serviços', df_srv,
            ["Código", "Data", "Nota", "Série", "Espécie", "Cliente"]
        )
        df_srv_cab = pd.read_excel(args.servicos, header=linha_srv, usecols=["Nota", "Cliente"])
        df_srv_cab = df_srv_cab.dropna(subset=["Nota"])
        df_srv_cab["Nota"] = df_srv_cab["Nota"].astype(int)

        df_result, erros_conc = conciliar_extrato(extrato, df_srv_cab)
        df_result.to_excel(args.saida, index=False)
        print(f"Sucesso! {len(df_result)} linhas -> {args.saida}")
        if erros_conc:
            print(f"{len(erros_conc)} erros de conciliação.")
    except Exception as e:
        import traceback
        print(f"Erro: {e}")
        traceback.print_exc()
