# Extrator C6 Bank PDF → Excel

## Layout suportado

**C6 Bank — Extrato Mensal PJ**

Colunas: Data · Data Contábil · Tipo · Descrição · Valor

Datas no formato `dd/mm/yyyy` (compostas internamente de `dd/mm` + ano extraído do cabeçalho de seção). Valores prefixados com `R$` ou `-R$` como token separado do número.

PDFs são protegidos por senha (padrão: CPF ou CNPJ do titular).

---

## Estrutura do PDF

O documento agrupa lançamentos por mês. Cada mês começa com um cabeçalho de seção e termina com um separador de saldo diário antes do próximo mês. Meses sem lançamentos exibem apenas "Sem lançamentos no mês".

```
Julho 2025 ( 01/07/2025 - 31/07/2025 )   Entradas: R$ 10.450,00   Saídas: R$ 10.235,91
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  Data      Data        Tipo              Descrição                           Valor  │
│ lançamento contábil                                                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  10/07     10/07       Entrada PIX       Pix recebido de VITARA CONSULTORIA  R$ ... │
│  10/07     10/07       Saída PIX         Pix enviado para KAROLYNE SUSAN...  -R$ ...│
│ ...                                                                                 │
│  Saldo do dia 10/07/25                                                      R$ ...  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Problemas identificados e soluções adotadas

### 1. Cabeçalho de tabela em 3 linhas

**Problema**
O cabeçalho da tabela de lançamentos ocupa 3 linhas no PDF:

```
y=215  Data        Data
y=219  Tipo        Descrição       Valor
y=222  lançamento  contábil
```

`detectar_limites()` usa `agrupar_linhas(tolerancia=5)`. As linhas y=215 e y=219 distam 4 pt (≤5) e são mescladas no mesmo grupo; y=222 dista 7 pt de y=215 mas apenas 3 pt de y=219, formando um segundo grupo.

**Solução**
O código processa os dois grupos em sequência:
- Grupo 1 (y≈215): registra os dois tokens `"data"` em `data_items` e os outros cabeçalhos (`tipo`, `descricao`, `valor`).
- Grupo 2 (y≈222): encontra `"lancamento"` e `"contabil"` → associa ao 1° e 2° item de `data_items`, resultando em `data_lanc` e `data_cont` com posições corretas.

---

### 2. Token `R$` cai fora da coluna `valor`

**Problema**
Os valores monetários no C6 são dois tokens separados: `R$` (ou `-R$`) e o número (e.g. `4.950,00`). O cabeçalho `"Valor"` está em x0=541, então a coluna `valor` começa em 541. Para valores grandes, o token `R$` fica à esquerda desse limite (cx≈529) e cai na coluna `descricao`. Resultado: `valor_col = "4.950,00"` (sem o `R$`) não bate em `REGEX_VALOR = r'^-?R\$\s*...'` e o lançamento é descartado.

Apenas lançamentos pequenos (e.g. `-R$ 9,99`) eram extraídos porque para valores de 1 dígito o token `-R$` caía exatamente sobre o limite 541.

**Diagnóstico**
```
10/07@36 | 10/07@95 | Entrada@154 | PIX@178 | Pix@235 | ... | R$@526 | 4.950,00@535
                                                               cx≈529       cx≈542
                                                              (descricao)  (valor)
```

**Solução — `_RE_SUFIXO_RS`**
Após `linha_para_colunas()`, verifica se `desc_col` termina com `(-?R\$)` e `valor_col` começa com dígito. Se sim, move o prefixo para `valor_col`:

```python
_RE_SUFIXO_RS = re.compile(r'\s*(-?R\$)\s*$')

m_rs = _RE_SUFIXO_RS.search(desc_col)
if m_rs and valor_col and re.match(r'^\d', valor_col):
    valor_col = m_rs.group(1) + ' ' + valor_col
    desc_col  = desc_col[:m_rs.start()].strip()
```

Após o rescue: `valor_col = "R$ 4.950,00"` → bate em `REGEX_VALOR` ✓.

---

### 3. Ano incorreto em documentos multi-ano

**Problema**
A lógica original extraía o menor ano encontrado no topo do PDF (`min(anos, key=int)`). Um documento de junho/2025 a fevereiro/2026 retornava sempre 2025, produzindo datas erradas para os meses de 2026.

**Solução — `_RE_DATA_FULL` por seção de mês**
Os cabeçalhos de seção contêm a data completa em formato `dd/mm/yyyy`:

```
Julho 2025 ( 01/07/2025 - 31/07/2025 ) ...
Janeiro 2026 ( 01/01/2026 - 31/01/2026 ) ...
```

`_RE_DATA_FULL = re.compile(r'\d{2}/\d{2}/(\d{4})')` detecta essas linhas durante o loop principal, atualiza `ano_atual` e pula a linha (não é lançamento). Todos os lançamentos seguintes usam esse ano até o próximo cabeçalho.

Efeito colateral positivo: a linha de cabeçalho também redefine `desc_pendente = ''`, impedindo que texto dessas linhas vaze para a descrição do primeiro lançamento do mês.

---

### 4. Texto de cabeçalho contaminando descrições

**Problema**
Linhas como a de período do documento ou cabeçalhos de seção tinham texto em posições que caíam na coluna `descricao`. Esse texto era acumulado em `desc_pendente` e prefixado ao primeiro lançamento do mês seguinte:

```
Resultado incorreto:
  T1 → "Periodo - 1 de junho de 2025 Entradas: R$ 10.450,00 Saidas: Pix recebido de VITARA..."
```

**Solução — condição `data_lanc == ''`**
Linhas que devem acumular `desc_pendente` (pré-descrição de lançamento multi-linha) têm todos os seus tokens na coluna `descricao` — `data_lanc` fica vazio. Linhas de cabeçalho sempre têm algum token no início da página (nome do mês, "Extrato", "Saldo" etc.) que cai em `data_lanc`.

```python
elif not tem_data and desc_col and data_lanc == '':
    # Só acumula pré-descrição quando data_lanc está vazio
```

---

### 5. Lançamentos com descrição em múltiplas linhas

**Problema**
Alguns lançamentos têm a descrição dividida em 3 linhas: pré-descrição → linha de data+valor → pós-descrição. Exemplo (SABESP):

```
y=433  Pix enviado para COMPANHIA DE SANEAMENTO BASICO DO ESTADO DE SAO PAULO -
y=439  15/07  15/07  Saída PIX  (sem desc inline)  -R$  124,62
y=445  SABESP
```

**Solução — `desc_pendente` + `aguarda_continuacao`**

| Flag | Quando ativa | O que faz |
|------|-------------|-----------|
| `desc_pendente` | Linha desc-only com `data_lanc == ''` antes de data+valor | Acumula e prepende à descrição do próximo lançamento |
| `aguarda_continuacao` | Linha de data+valor onde `desc_col == ''` (sem desc inline) | A linha desc-only seguinte é sufixada ao último lançamento fechado |

```python
# Ao fechar lançamento:
aguarda_continuacao = (desc_col == '')

# Ao encontrar linha desc-only com data_lanc == '':
if aguarda_continuacao and dados:
    dados[-1]['Descrição'] = (dados[-1]['Descrição'] + ' ' + desc_col).strip()
    aguarda_continuacao = False
elif not aguarda_continuacao:
    desc_pendente += (' ' if desc_pendente else '') + desc_col
```

---

## Validação de contagem

`_contar_lancamentos_c6(pdf, limites)` faz uma segunda passagem independente no PDF aplicando as mesmas regras de detecção (rescue de R$, skip de saldo e cabeçalhos), contando apenas linhas onde `REGEX_DATA.match(data_lanc)` e `REGEX_VALOR.match(valor_col)` ambos passam.

`_validar_contagem` compara esse total com `len(df)` e lança `ValueError` em caso de divergência.

---

## Condições de filtro (linhas descartadas)

| Condição | Motivo |
|----------|--------|
| `_RE_DATA_FULL` bate na linha bruta | Cabeçalho de seção de mês |
| `'saldo' in linha_norm and 'dia' in linha_norm` | Linha de saldo diário |
| `_norm(tipo_col) == 'tipo'` | Linha de cabeçalho de coluna |
| `data_lanc != ''` e sem data válida | Cabeçalho de documento, linha de conta |

## CLI

```bash
python extrato-c6-pdf-to-excel.py extrato.pdf saida.xlsx --senha 61474280000164
```
