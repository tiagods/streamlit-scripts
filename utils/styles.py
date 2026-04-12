import streamlit as st
from pathlib import Path

def load_css():
    css = (Path(__file__).parent.parent / 'styles' / 'global.css').read_text(encoding='utf-8')
    st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
