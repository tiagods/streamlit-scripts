# Extrator Itaú PDF → Excel

## Layouts suportados

| Layout | Identificação | Formato de data | Colunas |
|--------|--------------|-----------------|---------|
| A — Personalite / conta premium | datas `dd/mm/yyyy`, largura ~612pt | `dd/mm/yyyy` | Data · Lançamento · Valor · Saldo |
| B — Conta corrente mensal | datas `dd/mm`, largura ~595pt | `dd/mm` | Data · Descrição · Entradas R$ · Saídas R$ · Saldo R$ |

O layout é detectado automaticamente em `detectar_layout()` pela presença das colunas `entradas`/`saidas` (B) ou `valor`/`lancamento` (A) no cabeçalho.

---

## Problemas identificados e soluções adotadas

### 1. Limites de coluna calculados incorretamente (afeta ambos os layouts)

**Problema**
`detectar_layout()` calculava o limite direito de cada coluna como o ponto médio entre os centros dos cabeçalhos adjacentes:

```
limite lancamento|valor = (cx_lancamento + cx_valor) / 2
```

O cabeçalho do Personalite é a linha `"data lançamentos futuros valor (R$) saldo (R$)"`, onde `"lançamentos"` tem centro em x≈128 e `"valor"` em x≈423. O ponto médio resultante era **x=275**, mas descrições longas chegavam a x≈340 (e.g., `"PAG BOLETO PORTOSEG SA C FINANC E INVEST"`), fazendo as últimas palavras transbordarem para a coluna de valor.

**Solução**
Cada coluna armazena também o `x0` da palavra do cabeçalho. O limite direito de uma coluna passa a ser o `x0` do cabeçalho da coluna seguinte — ou seja, uma coluna nunca ultrapassa onde a próxima começa:

```python
cols[nome] = (p['x0'], (p['x0'] + p['x1']) / 2)   # (x0, centro)

for i, (nome, x0, cx) in enumerate(cols_ord):
    x_start = 0 if i == 0 else cols_ord[i][1]       # x0 desta coluna
    x_end   = pw if i == len-1   else cols_ord[i+1][1]  # x0 da próxima
```

---

### 2. Expressão regular de valor não cobria sinal prefixado (Layout A)

**Problema**
`REGEX_VALOR_BR` (`^\d{1,3}(?:\.\d{3})*,\d{2}[-+]?$`) exige que o sinal seja sufixo (`154,80-`). O Layout A do Personalite usa sinal prefixado (`-154,80`), então o regex não reconhecia os valores como válidos.

**Solução**
Essa inconsistência era mascarada pelo transbordamento descrito no item 1. Após corrigir os limites de coluna os valores passaram a cair corretamente na coluna `valor` e foram tratados como texto bruto (não convertidos a `float`), o que é suficiente para o Layout A.

> O `REGEX_VALOR_BR` continua inalterado porque é usado apenas no Layout B para distinguir entradas/saídas de linhas de texto comum.

---

### 3. `data_atual` reiniciada a cada página (Layout B)

**Problema**
No início do loop de cada página havia `data_atual = None`. Quando um grupo de lançamentos do mesmo dia continuava na página seguinte sem repetir a data na coluna `data`, todos esses lançamentos eram descartados (`if not data_atual: continue`).

Exemplo: `extrato-itau-2.pdf` encerrava na página 7 com `PIX TRANSF EBONY H30/01`, ignorando todos os lançamentos de `30/01` que continuavam na página 8.

**Solução**
`data_atual` é inicializado **fora** do loop de páginas e persiste durante toda a extração:

```python
data_atual = None   # fora do for pagina in pdf.pages

for pagina in pdf.pages:
    ...             # data_atual NÃO é reiniciado aqui
```

A mesma correção foi aplicada em `_contar_lancamentos_b()` para manter a validação de contagem consistente.

---

### 4. Ausência de condição de parada no Layout B

**Problema**
Após o último lançamento, o extrato Itaú conta corrente apresenta seções de resumo (`"Saldo em C/C"`, `"Saldo final"`, tabelas de aplicações) com valores numéricos que eram incorretamente extraídos como lançamentos.

**Solução**
Verificação antecipada do texto normalizado de cada linha:

```python
linha_norm = _norm(' '.join(cols.values()))
if 'saldo final' in linha_norm or 'saldo em c' in linha_norm:
    fim = True
    break
```

`"saldo em c"` captura `"Saldo em C/C"` sem falsos positivos em linhas como `"SALDO APLIC AUT MAIS"` (que não contém a sequência `"saldo em c"`).

---

## Validação de contagem

Após cada extração, `_validar_contagem()` realiza uma segunda passagem independente no PDF contando lançamentos pelo mesmo critério. Se os totais divergirem, `ValueError` é lançado. Ambas as funções (`extrair_layout_b` e `_contar_lancamentos_b`) devem sempre receber as mesmas correções.
