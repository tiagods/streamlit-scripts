# Extrator Bradesco PDF → Excel

## Layout suportado

**Bradesco Net Empresa — Extrato Consolidado / Por Período**

Colunas: Data · Lançamento · Dcto. · Crédito R$ · Débito R$ · Saldo R$

Data no formato `dd/mm/yyyy`; valores de débito com sinal `-` prefixado (e.g. `-581,58`).

---

## Estrutura do PDF — entradas de 1 e 2 linhas

O Bradesco pode renderizar um lançamento em **1 linha** ou **2 linhas** dependendo do comprimento da descrição.

**Entrada de 1 linha** — descrição e valores na mesma linha:
```
y=270.0  APLIC.INVEST FACIL  422132  -581,58  1,00
          ↑ lancamento col   ↑ dcto   ↑ debito ↑ saldo
```

**Entrada de 2 linhas** — o PDF centraliza verticalmente os campos numéricos entre as duas linhas de descrição:
```
y=250.9  TRANSFERENCIA PIX                      ← apenas descrição (linha 1)
y=255.3  01/03/2024  1103425  576,00  582,58    ← apenas data+dcto+valor (linha central)
y=259.7  REM: EDUARDO RODRIGUES DE 01/03        ← apenas descrição (linha 2)
```

Verificação: `(250.9 + 259.7) / 2 = 255.3` — a linha de valores está exatamente centrada.

A coluna `lancamento` fica **vazia** na linha de valores de entradas de 2 linhas.

---

## Problemas identificados e soluções adotadas

### 1. Limites de coluna calculados incorretamente

**Problema**
`detectar_limites()` calculava o limite direito de cada coluna como o ponto médio entre os centros dos cabeçalhos adjacentes, podendo fazer palavras longas transbordarem para a coluna seguinte.

**Solução** (idêntica à adotada nos outros extratores)
O limite direito de cada coluna passa a ser o `x0` do cabeçalho da coluna seguinte:

```python
cols[col] = (p['x0'], (p['x0'] + p['x1']) / 2)   # armazena (x0, centro)

for i, (n, x0, cx) in enumerate(cols_ord):
    x_start = 0 if i == 0 else cols_ord[i][1]
    x_end   = pw if i == len-1 else cols_ord[i+1][1]
```

---

### 2. Descrição complementar de entrada 2 linhas atribuída ao lançamento seguinte

**Problema**
Após fechar um lançamento cujos valores estavam numa linha sem descrição (e.g. `01/03/2024 1103425 576,00`), o código armazenava a linha seguinte (`REM: EDUARDO RODRIGUES DE 01/03`) em `desc_pendente`. Essa descrição pendente era então concatenada à descrição do **próximo** lançamento:

```
Resultado incorreto:
  T1 → "TRANSFERENCIA PIX"                              (incompleto)
  T2 → "REM: EDUARDO RODRIGUES DE 01/03 APLIC.INVEST FACIL"  (misturado)

Resultado correto:
  T1 → "TRANSFERENCIA PIX REM: EDUARDO RODRIGUES DE 01/03"
  T2 → "APLIC.INVEST FACIL"
```

**Diagnóstico**
O critério de distinção estava errado. Uma linha sem data e sem valor pode ser:
- **Descrição pré-valor** — aparece *antes* da linha com valores, vira `desc_pendente` do lançamento seguinte.
- **Descrição complementar** — aparece *depois* da linha com valores, pertence ao lançamento já fechado.

Ambas são visualmente idênticas (apenas texto na coluna `lancamento`), então o código não conseguia distingui-las.

**Solução — flag `aguarda_continuacao`**

O critério definitivo é o conteúdo da **linha de valores**:
- **Entrada de 1 linha**: `desc_col ≠ ''` na linha de valores → não há descrição complementar.
- **Entrada de 2 linhas**: `desc_col = ''` na linha de valores → a linha seguinte é a descrição complementar.

Implementação:

```python
# Ao fechar um lançamento:
aguarda_continuacao = (desc_col == '')
# True  → linha de valor sem descrição: próxima linha é complementar
# False → linha de valor com descrição (1-liner): nenhuma complementar esperada

# Ao processar linha sem data e sem valor:
if aguarda_continuacao and dados and (desc_col or dcto_col):
    # Anexa ao último lançamento fechado
    detalhe = (desc_col + ' ' + dcto_col).strip()
    dados[-1]['Lançamento'] = (dados[-1]['Lançamento'] + ' ' + detalhe).strip()
    aguarda_continuacao = False
elif desc_col and data_atual:
    # Descrição pré-valor de novo lançamento
    desc_pendente += (' ' if desc_pendente else '') + desc_col
    aguarda_continuacao = False
```

`aguarda_continuacao` substitui completamente a variável `ultimo_completo` que existia antes.

**Por que não usar espaçamento Y?**
O espaçamento entre linhas dentro de um mesmo lançamento (~4.4 pt) vs entre lançamentos distintos (~10.3 pt) foi avaliado como alternativa. Essa diferença é consistente no template atual do Bradesco, mas dependeria de um threshold numérico frágil. A solução por `desc_col == ''` usa apenas semântica do conteúdo e não depende de coordenadas.

---

## Condições de parada

A extração encerra ao encontrar linhas cujo texto normalizado contenha qualquer entrada de `_SECOES_FIM`:

```python
_SECOES_FIM = (
    'ultimos lancamentos',
    'resumo do periodo',
)
```

Também encerra quando a coluna `data` contém `"total"` (linha de total do período).
