import importlib.util
import sys
from io import BytesIO
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.styles import load_css
load_css()

# Carrega funções do script reutilizável
_spec = importlib.util.spec_from_file_location(
    'extrato_escrituracao',
    Path(__file__).parent.parent / 'scripts' / 'extrato_escrituracao.py',
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

carregar_arquivo = _mod.carregar_arquivo
encontrar_linha_colunas = _mod.encontrar_linha_colunas
gerar_extrato = _mod.gerar_extrato
conciliar_extrato = _mod.conciliar_extrato

# -------------------------------------------------------------------------
# Layout
# -------------------------------------------------------------------------

st.title("Processamento de Extrato e Acompanhamento de Serviços")

st.markdown(
    """
    ### Este sistema foi criado para processamento de arquivos de planilha Excel contendo informações financeiras.

    #### Funcionamento:
    - Permite o upload de dois arquivos Excel: Extrato e Acompanhamento de Serviços
    - Extrai números de notas fiscais dos lançamentos do extrato
    - Relaciona estas notas com os registros do arquivo de serviços
    - Gera um extrato conciliado com informações completas

    #### Dados processados:
    - Data das movimentações
    - Descrição dos lançamentos
    - Valores monetários
    - Documentos fiscais relacionados

    #### Verificações de segurança:
    - Confirma existência de movimentações
    - Identifica arquivos vazios
    - Registra problemas para investigação posterior

    #### Tipos de movimentações tratadas:
    - SISPAG
    - TED
    - PIX

    #### Resultado final:
    - Apresenta relatório na tela
    - Oferece download do arquivo processado em Excel
    - Disponibiliza relatório de erros quando necessário
    """
)

st.divider()

# -------------------------------------------------------------------------
# Upload e processamento dos arquivos
# -------------------------------------------------------------------------

extrato = []
df_servicos_filtrado = None

uploaded_extrato = st.file_uploader("Escolha o arquivo de Extrato", type=['xlsx', 'xls'])
if uploaded_extrato is not None:
    st.info(f"Arquivo de extrato carregado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        df = carregar_arquivo(uploaded_extrato)
        linha_colunas = encontrar_linha_colunas(
            "Extrato", df,
            ["Data", "Lançamento", "Valor (R$)", "Saldo (R$)"]
        )
        st.write(f"A linha {linha_colunas} contém os nomes das colunas no arquivo Extrato.")

        df_extrato = pd.read_excel(uploaded_extrato, header=linha_colunas)
        df_extrato = df_extrato.drop(df_extrato.columns[0], axis=1)
        df_extrato.rename(columns={df_extrato.columns[-1]: 'Notas Fiscais'}, inplace=True)

        extrato, erros_ext = gerar_extrato("Acompanhamento de Serviços", df_extrato)
        st.success(f"Arquivo de extrato processado com sucesso! {len(extrato)} notas fiscais encontradas.")
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")

uploaded_servicos = st.file_uploader(
    "Escolha o arquivo de Acompanhamento de Serviços", type=['xlsx', 'xls']
)
if uploaded_servicos is not None:
    st.info(f"Arquivo de Acompanhamento de Serviços carregado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        df = carregar_arquivo(uploaded_servicos)
        linha_colunas_srv = encontrar_linha_colunas(
            "Acompanhamento de Serviços", df,
            ["Código", "Data", "Nota", "Série", "Espécie", "Código", "Cliente",
             "AC.", "UF", "Valor Contábil", "Tipo", "Base Cálculo", "Alíq.", "Valor", "Isentas", "Outras"]
        )
        st.write(f"A linha {linha_colunas_srv} contém os nomes das colunas no arquivo Acompanhamento de Serviços.")

        df_servicos_filtrado = pd.read_excel(
            uploaded_servicos, header=linha_colunas_srv, usecols=["Nota", "Cliente"]
        )
        df_servicos_filtrado = df_servicos_filtrado.dropna(subset=["Nota"])
        df_servicos_filtrado["Nota"] = df_servicos_filtrado["Nota"].astype(int)
        st.success(
            f"Arquivo de Acompanhamento de Serviços processado com sucesso! "
            f"{len(df_servicos_filtrado)} notas fiscais encontradas."
        )
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")

st.divider()

bt_disabled = (
    uploaded_extrato is None
    or uploaded_servicos is None
    or df_servicos_filtrado is None
    or len(extrato) == 0
)
if st.button("Processar", disabled=bt_disabled):
    try:
        df_conciliado, erros_conc = conciliar_extrato(extrato, df_servicos_filtrado)

        st.dataframe(df_conciliado, use_container_width=True, hide_index=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_conciliado.to_excel(writer, index=False, sheet_name="Resultado")
        output.seek(0)

        st.download_button(
            type="primary",
            label="Baixar Arquivo Processado",
            data=output,
            file_name="Planilha Escrituração Dominio.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/check:",
        )

        todos_erros = (erros_ext if uploaded_extrato else []) + erros_conc
        if todos_erros:
            df_error = pd.DataFrame(todos_erros, columns=["Erro"])
            st.dataframe(df_error, use_container_width=True, hide_index=True)

            output_error = BytesIO()
            with pd.ExcelWriter(output_error, engine="xlsxwriter") as writer:
                df_error.to_excel(writer, index=False, sheet_name="Erros")
            output_error.seek(0)

            st.download_button(
                type="primary",
                label="Baixar Arquivo de Erros",
                data=output_error,
                file_name="erros.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/error:",
            )
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado na aplicação: {str(e)}")
