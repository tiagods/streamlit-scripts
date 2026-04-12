import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.styles import load_css
load_css()

# Carrega funções do script reutilizável
_spec = importlib.util.spec_from_file_location(
    'zip_merger_content',
    Path(__file__).parent.parent / 'scripts' / 'zip_merger_content.py',
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ZipMerger = _mod.ZipMerger
merge_zip_content = _mod.merge_zip_content

# -------------------------------------------------------------------------
# Layout
# -------------------------------------------------------------------------

st.markdown("""
    <div class="hero">
        <h1>🗜 Zip Merger</h1>
        <p>Mescle o conteúdo de múltiplos arquivos ZIP e RAR em um único arquivo ZIP.</p>
        <p>Filtre os arquivos internos por nome usando expressão regular, prefixo, sufixo ou substring.</p>
    </div>""", unsafe_allow_html=True)

st.divider()

uploaded_files = st.file_uploader(
    'Selecione os arquivos ZIP / RAR',
    type=['zip', 'rar'],
    accept_multiple_files=True,
)

st.markdown('#### Filtros (opcionais)')

col1, col2 = st.columns(2)
with col1:
    filtro_comeca = st.text_input('Nome começa com', placeholder='ex: relatorio_')
    filtro_termina = st.text_input('Nome termina com', placeholder='ex: .pdf')
with col2:
    filtro_contem = st.text_input('Nome contém', placeholder='ex: 2024')

outros_preenchidos = bool(filtro_comeca or filtro_termina or filtro_contem)
filtro_regex = st.text_input(
    'Regex',
    placeholder='ex: ^NF_\\d+\\.xml$',
    disabled=outros_preenchidos,
    help='Não pode ser usado junto com os filtros acima.' if outros_preenchidos else None,
)
regex_preenchido = bool(filtro_regex)

if regex_preenchido and outros_preenchidos:
    st.error('O campo Regex não pode ser usado junto com os outros filtros. Limpe um dos dois.')

ignorar_maiusculas = st.toggle('Ignorar maiúsculas/minúsculas nos filtros', value=True)


st.divider()

if uploaded_files:
    if st.button('Mesclar', type='primary', use_container_width=True, disabled=regex_preenchido and outros_preenchidos):
        with st.spinner('Mesclando…'):
            try:
                merger = ZipMerger(
                    regex_pattern=filtro_regex or None,
                    start_with=filtro_comeca or None,
                    end_with=filtro_termina or None,
                    contains=filtro_contem or None,
                    ignore_case=ignorar_maiusculas,
                )

                dados = merge_zip_content(uploaded_files, merger)

                nome_arquivo = f'merged_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'

                st.success(f'ZIP gerado com sucesso! ({len(dados):,} bytes)')
                st.download_button(
                    label='⬇  Baixar ZIP',
                    data=dados,
                    file_name=nome_arquivo,
                    mime='application/zip',
                    use_container_width=True,
                    type='primary',
                )

            except Exception as exc:
                st.error(f'Erro ao mesclar os arquivos: {exc}')
else:
    st.info('Faça o upload de um ou mais arquivos ZIP/RAR para começar.')
