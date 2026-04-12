# Ferramentas

Central de ferramentas internas para colaboradores internos. A plataforma reúne utilitários desenvolvidos para automatizar tarefas do dia a dia, disponíveis em uma única interface web.

---

## Sumário

- [Ferramentas](#ferramentas)
  - [Sumário](#sumário)
  - [Visão Geral](#visão-geral)
  - [Estrutura do Projeto](#estrutura-do-projeto)
  - [Ferramentas Disponíveis](#ferramentas-disponíveis)
    - [🏦 Extrato Itaú para Excel](#-extrato-itaú-para-excel)
      - [Por que `pdfplumber` em vez de `camelot`?](#por-que-pdfplumber-em-vez-de-camelot)
  - [Como Executar](#como-executar)
    - [Com Docker (recomendado)](#com-docker-recomendado)
    - [Localmente (sem Docker)](#localmente-sem-docker)
  - [Como Adicionar uma Nova Ferramenta](#como-adicionar-uma-nova-ferramenta)
    - [1. Criar o script de automação (se houver lógica reutilizável)](#1-criar-o-script-de-automação-se-houver-lógica-reutilizável)
    - [2. Criar a página Streamlit](#2-criar-a-página-streamlit)
    - [3. Registrar na navegação e no hub](#3-registrar-na-navegação-e-no-hub)
  - [Tema e Estilo](#tema-e-estilo)

---

## Visão Geral

A plataforma é construída com [Streamlit](https://streamlit.io/) e containerizada com Docker. Todo o hub é servido por um único container, eliminando a necessidade de hospedar cada ferramenta individualmente.

---

## Estrutura do Projeto

```
ferramentas/
│
├── Home.py                         # Ponto de entrada — define navegação e carrega CSS global
│
├── pages/                          # Páginas da plataforma (uma por ferramenta)
│   ├── 01_Extrato_Itau_para_Excel.py
│   └── 02_Hello_World.py
│
├── scripts/                        # Scripts de automação reutilizáveis
│   └── extrato-itau-pdf-to-excel.py
│
├── styles/
│   └── global.css                  # Estilos CSS globais (compartilhados entre todas as páginas)
│
├── utils/
│   └── styles.py                   # Utilitário para injetar o CSS global nas páginas
│
├── .streamlit/
│   └── config.toml                 # Configuração do tema (Spotify Dark)
│
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── requirements.txt
```

---

## Ferramentas Disponíveis

### 🏦 Extrato Itaú para Excel
Converte extratos bancários do Itaú em formato PDF para planilha Excel.

- Faz o upload do PDF diretamente na interface
- Extrai todos os lançamentos organizados por data
- Opção de incluir o saldo diário
- Gera e disponibiliza o `.xlsx` para download

**Script:** `scripts/extrato-itau-pdf-to-excel.py`
**Página:** `pages/01_Extrato_Itau_para_Excel.py`

#### Por que `pdfplumber` em vez de `camelot`?

O extrato do Itaú não é uma tabela com bordas ou linhas de grade — é um PDF com **texto posicionado por coordenadas X/Y**. O `camelot` foi projetado para PDFs com estrutura tabular explícita e falha nesse tipo de documento.

O `pdfplumber` lê as coordenadas exatas de cada palavra no PDF (`x0`, `x1`, `top`) e permite **reconstruir as colunas manualmente pelos limites de posição X**. Para o layout específico do extrato Itaú, essa abordagem é muito mais precisa e confiável do que tentar inferir estrutura onde ela não existe.

---

## Como Executar

### Com Docker (recomendado)

**Requisitos:** Docker Desktop instalado e em execução.

```bash
# Primeira execução (build + start)
docker compose up --build -d

# Execuções seguintes
docker compose up -d

# Parar
docker compose down
```

Acesse: [http://localhost:8501](http://localhost:8501)

### Localmente (sem Docker)

```bash
pip install -r requirements.txt
streamlit run Home.py
```

---

## Como Adicionar uma Nova Ferramenta

### 1. Criar o script de automação (se houver lógica reutilizável)

Adicione o script em `scripts/`:

```
scripts/
└── meu-novo-script.py
```

### 2. Criar a página Streamlit

Crie o arquivo em `pages/`, seguindo a numeração existente:

```python
# pages/03_Minha_Ferramenta.py
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.styles import load_css
load_css()

# Se usar um script de automação:
import importlib.util
_spec = importlib.util.spec_from_file_location(
    'meu_script', Path(__file__).parent.parent / 'scripts' / 'meu-novo-script.py'
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

st.title('🔧 Minha Ferramenta')
# ... restante da página
```

### 3. Registrar na navegação e no hub

Em `Home.py`, adicione a página em dois lugares:

**Na lista `tools` dentro de `home()`:**
```python
{
    'icon': '🔧',
    'name': 'Minha Ferramenta',
    'description': 'Descrição curta do que a ferramenta faz.',
    'tag': 'Categoria',
},
```

**No `st.navigation()`:**
```python
'Ferramentas': [
    st.Page('pages/01_Extrato_Itau_para_Excel.py', title='Extrato Itaú para Excel', icon='🏦'),
    st.Page('pages/02_Hello_World.py', title='Hello World', icon='👋'),
    st.Page('pages/03_Minha_Ferramenta.py', title='Minha Ferramenta', icon='🔧'),  # ← novo
],
```

---

## Tema e Estilo

O tema é configurado em dois lugares:

| Arquivo | Responsabilidade |
|---|---|
| `.streamlit/config.toml` | Paleta de cores base (Spotify Dark: fundo `#191414`, verde `#1DB954`) |
| `styles/global.css` | Classes CSS customizadas (cards, hero, badges, footer) |

O CSS global é carregado automaticamente em todas as páginas via `utils/styles.py`. Para customizar o visual, edite `styles/global.css` — as mudanças se aplicam a toda a plataforma.
