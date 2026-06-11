import io
import pdfplumber


def pdf_requer_senha(pdf_bytes):
    """Retorna True se o PDF está protegido por senha."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)):
            pass
        return False
    except Exception:
        return True


class PDFSemTextoError(ValueError):
    """Levantada quando um PDF não contém texto extraível (PDF de imagem)."""
    pass


MENSAGEM_PDF_SEM_TEXTO = """
**Este PDF não contém texto selecionável.**

O extrator não consegue ler o conteúdo porque o arquivo está em formato de imagem - o texto foi convertido em gráfico e não pode ser lido diretamente.

---

**Causas mais comuns**

- **Escaneamento físico** - o documento foi impresso, escaneado e salvo como PDF. O scanner captura uma foto do papel.
- **Print via navegador (Ctrl+P)** - alguns portais bancários renderizam o extrato com tecnologia de canvas/gráfico. Ao imprimir pelo navegador, o resultado é uma imagem, não texto.
- **Aplicativo mobile do banco** - certos apps geram PDFs onde o texto é armazenado como vetores gráficos em vez de caracteres.
- **Captura de tela convertida em PDF** - print-screen salvo como PDF preserva apenas a imagem.

---

**Como obter o PDF correto**

1. Acesse o **internet banking pelo computador** (não pelo app mobile).
2. Procure a opção **Exportar** ou **Baixar extrato em PDF** - use o botão do próprio portal, não o "Imprimir" do navegador.
3. Abra o PDF gerado e tente **selecionar o texto com o cursor**. Se conseguir, o arquivo está correto para upload.
"""
