# Extrator Santander PDF → Excel

## Layout suportado

**Santander Empresas PJ — Extrato Consolidado Inteligente**

Colunas: Data · Descrição · N° Documento · Movimentos(R$) [Créditos / Débitos] · Saldo(R$)

Data no formato `dd/mm`; o ano é extraído do cabeçalho da primeira ou segunda página.
Valores de débito com sinal `-` no sufixo (e.g. `165,00-`); créditos sem sinal (e.g. `2.500,00`).

---

## Estrutura do PDF — cabeçalho de duas linhas

O Santander usa um cabeçalho de tabela que ocupa **duas linhas**:

```
Linha 1:  Data | Descrição   N°Documento | Movimentos(R$) | Saldo(R$)
Linha 2:                                 | Créditos | Débitos |
```

A função `detectar_limites()` lida com isso mesclando duas linhas adjacentes (dentro de 20pt):
quando encontra `credito` e `debito` numa linha mas não `saldo`, procura `saldo` em linhas próximas
e mescla os resultados antes de calcular os limites.

**Posições reais medidas no PDF (página width ≈ 595):**

| Coluna    | x0   | Limite direito (x0 da próxima) |
|-----------|------|-------------------------------|
| Data      | 34   | 65 (x0 de Descrição)          |
| Descrição | 65   | 296 (x0 de N°Documento)       |
| N°Doc     | 296  | 384 (x0 de Créditos)          |
| Créditos  | 384  | 435 (x0 de Débitos)           |
| Débitos   | 435  | 508 (x0 de Saldo)             |
| Saldo(R$) | 508  | 650 (fim da página)           |

Esses valores são usados no `_FALLBACK` quando a detecção dinâmica falha.

---

## Alinhamento à direita dos valores monetários

Os valores (Créditos, Débitos, Saldo) são **alinhados à direita** no PDF. Isso significa:
- `x1` (borda direita) é fixo por coluna: Créditos≈405, Débitos≈456, Saldo≈540
- `x0` varia com o tamanho do número: `15.000,00` tem x0≈376, enquanto `72,50` tem x0≈397

**Problema:** classificar pelo centro `cx = (x0 + x1) / 2` funciona para valores pequenos, mas
para valores grandes `cx` pode cair à esquerda do limite da coluna.

**Solução:** em `linha_para_colunas()`, tokens que correspondem a `REGEX_VALOR` são classificados
pelo `x1` (borda direita), não pelo centro:

```python
ref = p['x1'] if (regex_valor and regex_valor.match(p['text'])) else (p['x0'] + p['x1']) / 2
```

Outros tokens (descrição, N°Doc) continuam usando o centro.

---

## Problemas identificados e soluções adotadas

### 1. Cabeçalho de duas linhas não detectado

**Problema**
`detectar_limites()` exigia encontrar `credito`, `debito` e `saldo` na **mesma** linha. O Santander
coloca "Créditos" e "Débitos" em uma sub-linha e "Saldo(R$)" na linha acima, fazendo a detecção
cair sempre no `_FALLBACK`.

**Solução**
Adicionar detecção em duas linhas: quando `credito` e `debito` são encontrados numa linha mas não
`saldo`, varre linhas adjacentes (|Δy| ≤ 20pt) em busca de `saldo`, mescla e calcula os limites:

```python
if 'credito' in cols and 'debito' in cols:
    for y2 in ys_sorted:
        if y2 == y or abs(y2 - y) > 20:
            continue
        cols2  = _extrair_cols_linha(grupos[y2])
        merged = {**cols2, **cols}   # cols tem prioridade (credito/debito)
        if 'saldo' in merged:
            return _calcular_limites(merged, pw)
```

---

### 2. Palavras compostas não mapeadas no `_HEADER_MAP`

**Problema**
`pdfplumber` extrai palavras únicas sem separar por símbolos especiais:
- `"N°Documento"` → normalizado como `"ndocumento"` — não casava com `"no"` ou `"documento"`
- `"Saldo(R$)"` → normalizado como `"saldo(r$)"` — não casava com `"saldo"`

**Solução**
Adicionar as variantes ao `_HEADER_MAP`:

```python
'ndocumento':   'ndoc',
'saldo(r$)':    'saldo',
'saldo(r':      'saldo',   # variante por truncamento de codificação
```

---

### 3. Descrições complementares concatenadas ao lançamento seguinte

**Problema**
Lançamentos com descrição longa têm o restante em uma **linha seguinte** (sem data, sem valor).
O código armazenava essa linha em `desc_pendente`, que era então prefixada ao **próximo** lançamento.

```
Resultado incorreto:
  T1 → "IOFIMPOSTOOPERACOESFINANCEIRAS -"                    (incompleto)
  T2 → "PERIODO:01/12A31/12/24 IOFADICIONAL-AUTOMATICO -"    (misturado)

Resultado correto:
  T1 → "IOFIMPOSTOOPERACOESFINANCEIRAS - PERIODO:01/12A31/12/24"
  T2 → "IOFADICIONAL-AUTOMATICO - PERIODO:01/12A31/12/24"
```

**Diagnóstico**
Diferente do Bradesco, no Santander o valor **sempre** está na mesma linha que a primeira parte
da descrição. Linhas com apenas descrição (sem data, sem valor) são **sempre** continuações do
lançamento anterior, nunca pré-descrições do próximo.

**Solução — flag `aguarda_continuacao`**

Após fechar qualquer lançamento (`dados.append`), seta `aguarda_continuacao = True`. Ao encontrar
uma linha só-descrição:

```python
# Após fechar um lançamento:
aguarda_continuacao = True

# Ao processar linha sem data e sem valor:
if aguarda_continuacao and dados:
    dados[-1]['Descrição'] = (dados[-1]['Descrição'] + ' ' + desc_col).strip()
else:
    sep = ' ' if desc_pendente else ''
    desc_pendente += sep + desc_col
```

O flag é resetado para `False` quando:
- Linha de cabeçalho de tabela (`data_col == 'data'`)
- Linha de `saldo em`
- Linha de DATA sem VALOR (aguardando o VALOR desta nova data)

---

### 4. Rodapé do PDF concatenado como continuação

**Problema**
Cada página do PDF contém linhas de rodapé/marca d'água:
- `Extrato_PJ_A4_Inteligente1.0(EficienciaePagueDireto)-2/4/2024`
- `BALP_UY_M3AM4231_MXDD0125.PIM-`

Com `aguarda_continuacao = True` após o último lançamento da página, essas linhas eram appendadas
à descrição do lançamento anterior.

**Solução**
Filtrar linhas cujo `desc_col` contém tokens de rodapé:

```python
_RODAPE_TOKENS = ('extrato_pj_a4', 'balp_')
if any(t in _norm(desc_col) for t in _RODAPE_TOKENS):
    continue
```

---

### 5. Linha "SALDO EM dd/mm" não filtrada

**Problema**
O filtro existente usava `'saldo em' in linha_txt` (com espaço). No PDF, "SALDO" e "EM" são
renderizados como uma palavra única ("SALDOEM31/01"), então o filtro falhava.

**Solução**
Adicionar verificação alternativa:

```python
if 'saldo em' in linha_txt or 'saldoem' in linha_norm:
    data_atual = None
    desc_pendente = ''
    aguarda_continuacao = False
    continue
```

---

## Condições de parada

A extração encerra ao encontrar qualquer entrada de `_SECOES_FIM`:

```python
_SECOES_FIM = (
    'saldos por periodo',
    'investimentos',
    'debito automatico em conta corrente',
    'pacote de servicos',
    'indices economicos',
    'taxa de juros',
)
```

---

## Notas

- O Saldo é extraído apenas nas linhas onde o PDF o apresenta (não em todas as linhas de lançamento).
- O N° Documento é mesclado na coluna `Descrição`. Quando o campo contém apenas `-` (sem número real),
  o traço aparece no final da descrição — comportamento esperado refletindo o dado real do PDF.
