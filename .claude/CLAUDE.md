# Ferramentas Internas — Streamlit

Plataforma de utilitários internos para colaboradores, construída com Streamlit e containerizada com Docker. Todo o hub é servido por um único container com nginx + SSL.

---

## Estrutura do projeto

```
Home.py                        # Entrada: define st.navigation() e carrega CSS global
pages/                         # Uma página por ferramenta
    01_Extrato_PDF_para_Excel.py
    02_Extrato_Arquivo_Escrituracao.py
    03_Zip_Merger.py
scripts/                       # Lógica de negócio reutilizável (ver scripts/CLAUDE.md)
    extrato-itau-pdf-to-excel.py
    extrato-santander-pdf-to-excel.py
    extrato-bradesco-pdf-to-excel.py
    extrato-c6-pdf-to-excel.py
    extrato_escrituracao.py
    zip_merger_content.py
utils/
    styles.py                  # load_css() — injeta global.css em todas as páginas
    pdf_errors.py              # PDFSemTextoError + mensagem amigável ao usuário
styles/
    global.css                 # Tema Spotify Dark (bg #191414, verde #1DB954)
.streamlit/
    config.toml                # Paleta de cores base
docs/                          # PDFs de teste para os extratores
tmp/                           # Saídas temporárias geradas durante testes
```

---

## Convenções

### Idioma
Todo o código orientado ao usuário (UI, mensagens, nomes de função de negócio) está em **português brasileiro**. Nomes de função nos scripts seguem snake_case em português (e.g. `extrair_extrato_itau`, `carregar_arquivo`).

### Carregamento de scripts nas páginas
Scripts têm hífens no nome (`extrato-itau-pdf-to-excel.py`), o que impede `import` direto. O carregamento é feito via `importlib.util`:

```python
def _carregar(nome_script, nome_funcao):
    spec = importlib.util.spec_from_file_location(
        nome_script,
        Path(__file__).parent.parent / 'scripts' / f'{nome_script}.py',
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, nome_funcao)
```

### CSS global
Toda página deve chamar `load_css()` de `utils/styles.py` logo após os imports. Nunca copiar o CSS diretamente na página — ele é compartilhado.

### Dependências
`requirements.txt`: `streamlit`, `pandas`, `xlrd`, `openpyxl`, `xlsxwriter`, `pdfplumber`, `fpdf2`, `rarfile`, `patool`.

Não adicionar dependências sem atualizar `requirements.txt` e verificar que o `Dockerfile` continua funcional.

---

## Adicionando uma nova ferramenta

1. **Script** (se houver lógica reutilizável): criar em `scripts/` e documentar em `scripts/CLAUDE.md`.
2. **Página**: criar `pages/NN_Nome_Da_Ferramenta.py` com `sys.path.insert` + `load_css()` no topo.
3. **Navegação**: registrar em dois lugares em `Home.py`:
   - Lista `tools` dentro de `home()` (card na página inicial).
   - `st.navigation()` (item no menu lateral).

---

## Extratores bancários

Documentação detalhada em `scripts/CLAUDE.md`.

Resumo dos comportamentos não óbvios que já foram tratados:

| Banco | Problema | Solução |
|-------|----------|---------|
| Todos | Limite de coluna calculado como ponto médio entre centros de cabeçalhos → transbordamento de texto | Limite direito = `x0` do cabeçalho da coluna seguinte |
| Itaú Layout A | Descrições longas invadiam coluna de valor | Corrigido pelo fix de limite acima |
| Itaú Layout B | `data_atual` reiniciada por página cortava lançamentos que continuavam na próxima | `data_atual` persiste entre páginas |
| Itaú Layout B | Tabelas de resumo do final do extrato eram extraídas como lançamentos | Para em `"Saldo final"` / `"Saldo em C/C"` |
| Bradesco | Linha de descrição complementar (2ª linha de entrada multi-linha) era atribuída ao lançamento seguinte | Flag `aguarda_continuacao`: linha de valor com `desc_col == ''` sinaliza que a linha seguinte é complementar |
| Santander | Cabeçalho de tabela ocupa 2 linhas — `detectar_limites()` nunca satisfazia condição de 1 linha | Detecção em duas linhas: mescla linha de Créditos/Débitos com linha adjacente (≤20pt) que tem Saldo |
| Santander | Valores monetários alinhados à direita: `x0` variável impede classificação por centro | `linha_para_colunas()` usa `x1` (borda direita fixa) para tokens que casam com `REGEX_VALOR` |
| Santander | Linhas de continuação pós-valor prefixadas ao próximo lançamento | `aguarda_continuacao = True` após todo fechamento; desc-only é sempre continuação no Santander |
| Santander | Rodapé `Extrato_PJ_A4_Inteligente1.0` appendado como continuação | `_RODAPE_TOKENS` filtra linhas de marca d'água pelo `desc_col` |
| Santander | `SALDOEM31/01` não filtrado pelo check `'saldo em'` (palavra sem espaço no PDF) | Adiciona `'saldoem' in linha_norm` |

Detalhes com diagnóstico e raciocínio em:
- `scripts/extrato-itau-pdf-to-excel.md`
- `scripts/extrato-bradesco-pdf-to-excel.md`
- `scripts/extrato-santander-pdf-to-excel.md`

---

## Execução local

```bash
# Com Docker (recomendado)
docker compose up --build -d

# Sem Docker
pip install -r requirements.txt
streamlit run pages/Home.py
```

PDFs de teste ficam em `docs/`. Saídas temporárias em `tmp/` (não versionado).
