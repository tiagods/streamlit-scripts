import io
import importlib.util
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.styles import load_css
load_css()

# Carrega a função de extração de scripts/extrato-itau-pdf-to-excel.py
_spec = importlib.util.spec_from_file_location(
    'extrato-itau-pdf-to-excel', Path(__file__).parent.parent / 'scripts' / 'extrato-itau-pdf-to-excel.py'
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
extrair_extrato_itau = _mod.extrair_extrato_itau

# -------------------------------------------------------------------------
# Layout
# -------------------------------------------------------------------------

st.markdown("""
    <div class="hero">
        <h1>🏦 Extrato Itaú → Excel</h1>
        <p>Converta seu extrato bancário do Itaú (PDF) em uma planilha Excel organizada, pronta para análise e conciliação financeira.</p>
        <p>O projeto se baseia na mesma estratégia do <a href="https://tabula.technology" target="_blank">Tabula</a>, usando a biblioteca pdfplumber para trabalhar diretamente com as coordenadas de cada palavra no PDF. Detecta automaticamente dois layouts de extrato Itaú (Personalite e Conta corrente) e valida a contagem de lançamentos antes de gerar a planilha.</p>
        <p>Faça upload do seu extrato PDF e baixe a planilha pronta.</p>
    </div>""", unsafe_allow_html=True)

st.divider()

uploaded = st.file_uploader('Selecione o extrato PDF', type='pdf')

st.divider()

if uploaded:
    if st.button('Converter', type='primary', use_container_width=True):
        with st.spinner('Processando…'):
            try:
                df = extrair_extrato_itau(io.BytesIO(uploaded.read()))

                st.metric('Lançamentos', len(df))

                st.dataframe(df, use_container_width=True, hide_index=True)

                buffer = io.BytesIO()
                df.to_excel(buffer, index=False)
                buffer.seek(0)

                nome_saida = Path(uploaded.name).stem + '.xlsx'
                st.download_button(
                    label='⬇  Baixar Excel',
                    data=buffer,
                    file_name=nome_saida,
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True,
                    type='primary',
                )

            except Exception as exc:
                st.error(f'Erro ao processar o arquivo: {exc}')
else:
    st.info('Faça o upload de um PDF para começar.')
