# Scripts

Scripts de automação reutilizáveis carregados pelas páginas Streamlit via `importlib.util`.

> Os nomes de arquivo usam hífens (e.g. `extrato-itau-pdf-to-excel.py`) porque foram pensados para uso em linha de comando também. Por isso o carregamento nas páginas usa `importlib` em vez de `import` direto.

---

## Inventário

| Arquivo | Função exportada | Página que consome |
|---------|-----------------|-------------------|
| `extrato-itau-pdf-to-excel.py` | `extrair_extrato_itau(caminho_pdf, senha=None)` | `extrato_pdf_excel.py` |
| `extrato-santander-pdf-to-excel.py` | `extrair_extrato_santander(caminho_pdf, senha=None)` | `extrato_pdf_excel.py` |
| `extrato-bradesco-pdf-to-excel.py` | `extrair_extrato_bradesco(caminho_pdf, senha=None)` | `extrato_pdf_excel.py` |
| `extrato-c6-pdf-to-excel.py` | `extrair_extrato_c6(caminho_pdf, senha=None)` | `extrato_pdf_excel.py` |
| `extrato_escrituracao.py` | `carregar_arquivo`, `encontrar_linha_colunas`, `gerar_extrato`, `conciliar_extrato` | `escrituracao.py` |
| `zip_merger_content.py` | `ZipMerger` | `zip_merger.py` |

---

## Extratores bancários — padrão comum

Todos os extratores PDF seguem o mesmo fluxo:

```
1. _verificar_pdf_texto()   → lança PDFSemTextoError se o PDF for imagem/escaneado
2. detectar_limites()        → lê o cabeçalho do PDF e calcula os limites de coluna
3. agrupar_linhas()          → agrupa palavras por linha usando tolerância de Y
4. linha_para_colunas()      → distribui palavras de uma linha nos campos pelo centro X
5. loop de extração          → processa linha a linha acumulando lançamentos
```

### Suporte a senha

Todos os extratores aceitam `senha=None`. Quando fornecida, é passada para `pdfplumber.open(password=senha or '')`. A detecção de se o PDF requer senha é feita pela página via `pdf_requer_senha()` em `utils/pdf_errors.py` — o extrator nunca precisa saber disso antecipadamente.

```python
# CLI
python extrato-c6-pdf-to-excel.py extrato.pdf saida.xlsx --senha 12345

# Programático
df = extrair_extrato_c6(caminho_pdf, senha='12345')
```

### Cálculo de limites de coluna

**Regra:** o limite direito de cada coluna é o `x0` da palavra de cabeçalho da coluna seguinte, não o ponto médio entre centros. Isso garante que o conteúdo de uma coluna nunca ultrapasse onde a próxima começa.

```python
cols[nome] = (p['x0'], (p['x0'] + p['x1']) / 2)   # (x0, centro)

for i, (nome, x0, cx) in enumerate(cols_ord):
    x_start = 0 if i == 0 else cols_ord[i][1]        # x0 desta coluna
    x_end   = pw if i == len-1 else cols_ord[i+1][1] # x0 da próxima
```

Todos os `detectar_limites()` / `detectar_layout()` implementam esta lógica. Cada script mantém também um `_FALLBACK` com limites fixos usados quando o cabeçalho não é encontrado.

### Erros de PDF sem texto

`utils/pdf_errors.py` define `PDFSemTextoError`, `MENSAGEM_PDF_SEM_TEXTO` e `pdf_requer_senha()`. Todo extrator verifica o PDF antes de processar e relança esse erro para a página Streamlit exibir a mensagem amigável ao usuário.

---

## Particularidades por banco

### Itaú — `extrato-itau-pdf-to-excel.py`

Detecta automaticamente dois layouts. Decisões não óbvias documentadas em `extrato-itau-pdf-to-excel.md`:

- **Layout A (Personalite):** limite de coluna calculado com ponto médio gerava transbordamento de descrições longas para a coluna de valor. Corrigido para usar `x0` do cabeçalho seguinte.
- **Layout B (Conta corrente):** `data_atual` era reiniciada a cada página, cortando lançamentos que continuavam na página seguinte sem repetir a data. Corrigido para persistir entre páginas. Adicionada parada em `"Saldo final"` / `"Saldo em C/C"` para não extrair as tabelas de resumo do final do extrato.
- Validação de contagem (`_validar_contagem`) faz segunda passagem independente no PDF; qualquer divergência lança `ValueError`.

### Bradesco — `extrato-bradesco-pdf-to-excel.py`

Decisões não óbvias documentadas em `extrato-bradesco-pdf-to-excel.md`:

- Lançamentos podem ocupar **2 linhas**. Nesse caso o PDF centraliza os campos numéricos (Dcto, Crédito, Débito, Saldo) verticalmente entre as duas linhas de descrição, deixando a coluna `lancamento` **vazia** na linha de valores.
- O flag `aguarda_continuacao` detecta isso: quando uma linha fecha um lançamento com `desc_col == ''`, a linha imediatamente seguinte é a descrição complementar desse lançamento (não o início do próximo).

### Santander — `extrato-santander-pdf-to-excel.py`

Decisões não óbvias documentadas em `extrato-santander-pdf-to-excel.md`:

- Cabeçalho da tabela ocupa **2 linhas** (`detectar_limites()` nunca satisfaz a condição de linha única → cai no `_FALLBACK`).
- O `_FALLBACK` está intencionalmente desalinhado em relação aos nomes: o intervalo `ndoc` (370–435) captura **Créditos**, o `credito` (435–510) captura **Débitos**, e o `debito` (510–575) captura o **Saldo corrente**. O `ndoc_col` com padrão `REGEX_VALOR` é promovido a `cred_col` antes de computar `tem_cred`.
- `deb_col` é o saldo corrente (nunca um movimento): `tem_deb = False` sempre; `deb_col` alimenta a coluna `Saldo` do DataFrame.
- Flag `aguarda_continuacao = True` após **todo** fechamento de lançamento: no Santander, linhas só-descrição são sempre continuações do lançamento anterior, nunca pré-descrições do próximo.
- Rodapé do PDF (`extrato_pj_a4`, `balp_`) filtrado via `_RODAPE_TOKENS` para não ser appendado como continuação.
- Linha "SALDOEM31/01" filtrada por `'saldoem' in linha_norm` (a palavra não tem espaço no PDF).

### C6 Bank — `extrato-c6-pdf-to-excel.py`

- Extrato mensal com múltiplos meses por documento. Colunas: `Data`, `Data Contábil`, `Tipo`, `Descrição`, `Valor`.
- **Cabeçalho em 3 linhas:** `Data / Data` (y≈215), `Tipo / Descricao / Valor` (y≈219), `lancamento / contabil` (y≈222). `detectar_limites()` agrupa as duas primeiras (tolerância 5pt) e processa a terceira separado; associa cada `"data"` a `data_lanc` ou `data_cont` pela palavra adjacente.
- **R$ como token separado do número:** quando o valor é grande (e.g. `R$ 4.950,00`), o token `R$` cai na coluna `descricao` (cx < 541) e o número na coluna `valor`. `_RE_SUFIXO_RS` detecta `R$` ou `-R$` no final de `desc_col` e resgata para `valor_col` antes da validação com `REGEX_VALOR`.
- **Ano por seção de mês:** cabeçalhos de período contêm data completa `dd/mm/yyyy` (ex: `01/07/2025`). `_RE_DATA_FULL` extrai o ano e atualiza `ano_atual` a cada seção; a linha é descartada para extração. Resolve documentos que cruzam virada de ano.
- **Lançamentos multi-linha:** descrição pode preceder a linha de data+valor (`desc_pendente`) ou sucedê-la (`aguarda_continuacao`). Linhas de pré-descrição só são acumuladas quando `data_lanc == ''` — evita que cabeçalhos de documento com texto na coluna de data contaminem a descrição.
- **Validação de contagem:** `_contar_lancamentos_c6` faz segunda passagem independente; `_validar_contagem` lança `ValueError` se divergir do DataFrame extraído.
- PDFs protegidos por senha (padrão C6: CPF/CNPJ do titular): passar `senha=` ao extrator.

---

## Adicionando suporte a um novo banco

1. Criar `extrato-<banco>-pdf-to-excel.py` seguindo o padrão:
   - `_verificar_pdf_texto(caminho_pdf, senha=None)` no início
   - `detectar_limites()` com a lógica de `x0` do cabeçalho seguinte
   - Função principal `extrair_extrato_<banco>(caminho_pdf, senha=None) → DataFrame`
   - `_contar_lancamentos_<banco>` + `_validar_contagem` para segunda passagem de validação
   - Bloco `if __name__ == '__main__':` com argumento `--senha` para uso em linha de comando
2. Registrar a função em `pages/extrato_pdf_excel.py` via `_carregar()` e adicionar uma aba `st.tabs`.
3. Criar `extrato-<banco>-pdf-to-excel.md` documentando o layout e qualquer decisão não óbvia.
