import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title='Ferramentas Internas',
    page_icon='🔧',
    layout='centered',
)

# CSS global — carregado em todas as páginas
_css = (Path(__file__).parent.parent / 'styles' / 'global.css').read_text(encoding='utf-8')
st.markdown(f'<style>{_css}</style>', unsafe_allow_html=True)

def home():
    st.markdown("""
    <div class="hero">
        <div class="badge">Acesso interno exclusivo</div>
        <h1>Central de Ferramentas</h1>
        <p>Utilitários internos desenvolvidos para colaboradores.
        Automatize tarefas repetitivas, reduza erros e ganhe tempo no dia a dia.</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    tools = [
        {
            'icon': '🏦',
            'name': 'Extrato Itaú para Excel',
            'description': 'Faça upload do extrato bancário em PDF e baixe uma planilha Excel pronta, com todos os lançamentos organizados por data. Ideal para conciliação financeira.',
            'tag': 'Financeiro',
        },
        {
            'icon': '👋',
            'name': 'Extrato XLS para Escrituração Contábil',
            'description': 'Processamento de arquivos de planilha Excel contendo informações financeiras para escrituração contábil.',
            'tag': 'Contabilidade',
        },
        {
            'icon': '🗜',
            'name': 'Zip Merger',
            'description': 'Una o conteúdo de múltiplos arquivos ZIP e RAR em um único ZIP. Filtre os arquivos internos por nome, prefixo, sufixo, substring ou expressão regular.',
            'tag': 'Geral',
        },
    ]

    cols = st.columns(len(tools), gap='medium')
    for i, tool in enumerate(tools):
        with cols[i]:
            st.markdown(f"""
            <div class="tool-card">
                <div class="tool-icon">{tool['icon']}</div>
                <div class="tool-name">{tool['name']}</div>
                <div class="tool-desc">{tool['description']}</div>
                <div class="tool-tag">{tool['tag']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("""
    <div class="footer">
        Plataforma interna · Sugestões? Fale com o time de Desenvolvimento.
    </div>
    """, unsafe_allow_html=True)

pg = st.navigation({
    'Home': [
        st.Page(home, title='Home', icon='🏠', default=True),
    ],
    'Ferramentas': [
        st.Page('01_Extrato_Itau_para_Excel.py', title='Extrato Itaú para Excel', icon='🏦'),
        st.Page('02_Extrato_Arquivo_Escrituracao.py', title='Extrato XLS para Escrituração Contábil', icon='👋'),
        st.Page('03_Zip_Merger.py', title='Zip Merger', icon='🗜'),
    ],
})

pg.run()
