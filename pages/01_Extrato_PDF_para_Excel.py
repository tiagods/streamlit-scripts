import io
import importlib.util
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.styles import load_css
from utils.pdf_errors import PDFSemTextoError, MENSAGEM_PDF_SEM_TEXTO
load_css()


def _carregar(nome_script, nome_funcao):
    spec = importlib.util.spec_from_file_location(
        nome_script,
        Path(__file__).parent.parent / 'scripts' / f'{nome_script}.py',
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, nome_funcao)


extrair_itau      = _carregar('extrato-itau-pdf-to-excel',      'extrair_extrato_itau')
extrair_santander = _carregar('extrato-santander-pdf-to-excel', 'extrair_extrato_santander')
extrair_bradesco  = _carregar('extrato-bradesco-pdf-to-excel',  'extrair_extrato_bradesco')

# -------------------------------------------------------------------------
# Layout
# -------------------------------------------------------------------------

st.markdown("""
    <div class="hero">
        <h1>🏦 Extrato PDF → Excel</h1>
        <p>Converta extratos bancários em PDF para planilhas Excel organizadas, prontas para análise e conciliação financeira.</p>
        <p>Selecione o banco na aba correspondente, faça upload do extrato e baixe a planilha.</p>
    </div>""", unsafe_allow_html=True)

st.divider()

tab_itau, tab_santander, tab_bradesco = st.tabs([
    '🏦 Itaú',
    '🏦 Santander',
    '🏦 Bradesco',
])


def _render_extrator(label, extractor):
    uploaded = st.file_uploader(
        f'Selecione o extrato {label} (PDF)',
        type='pdf',
        key=f'upload_{label}',
    )
    st.divider()
    if uploaded:
        if st.button('Converter', type='primary', use_container_width=True, key=f'btn_{label}'):
            with st.spinner('Processando…'):
                try:
                    df = extractor(io.BytesIO(uploaded.read()))

                    st.metric('Lançamentos', len(df))
                    st.dataframe(df, use_container_width=True, hide_index=True)

                    buffer = io.BytesIO()
                    df.to_excel(buffer, index=False)
                    buffer.seek(0)

                    st.download_button(
                        label='⬇  Baixar Excel',
                        data=buffer,
                        file_name=Path(uploaded.name).stem + '.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        use_container_width=True,
                        type='primary',
                        key=f'dl_{label}',
                    )
                except PDFSemTextoError:
                    st.warning(MENSAGEM_PDF_SEM_TEXTO)
                except Exception as exc:
                    st.error(f'Erro ao processar o arquivo: {exc}')
    else:
        st.info('Faça o upload de um PDF para começar.')


with tab_itau:
    _render_extrator('Itaú', extrair_itau)

with tab_santander:
    _render_extrator('Santander', extrair_santander)

with tab_bradesco:
    _render_extrator('Bradesco', extrair_bradesco)
