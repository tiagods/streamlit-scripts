import io
import re
import zipfile
import rarfile


class ZipMerger:
    """Filtra e mescla arquivos ZIP/RAR com base em condições sobre o nome dos arquivos."""

    def __init__(
        self,
        regex_pattern=None,
        start_with=None,
        end_with=None,
        contains=None,
        ignore_case=False,
    ):
        self.regex_pattern = regex_pattern
        self.start_with = start_with
        self.end_with = end_with
        self.contains = contains
        self.ignore_case = ignore_case

    def matches_conditions(self, filename: str) -> bool:
        """Retorna True se o arquivo satisfaz todas as condições configuradas."""
        name = filename.lower() if self.ignore_case else filename

        def fix(val):
            return val.lower() if self.ignore_case and val else val

        if self.regex_pattern and not re.match(self.regex_pattern, fix(name)):
            return False
        if self.start_with and not name.startswith(fix(self.start_with)):
            return False
        if self.end_with and not name.endswith(fix(self.end_with)):
            return False
        if self.contains and fix(self.contains) not in name:
            return False
        return True


def _extrair_de_zip(zip_file, merger: ZipMerger, merged_zip: zipfile.ZipFile):
    with zipfile.ZipFile(zip_file, 'r') as zf:
        for info in zf.infolist():
            if merger.matches_conditions(info.filename):
                merged_zip.writestr(info.filename, zf.read(info.filename))


def _extrair_de_rar(rar_file, merger: ZipMerger, merged_zip: zipfile.ZipFile):
    with rarfile.RarFile(rar_file, 'r') as rf:
        for info in rf.infolist():
            if merger.matches_conditions(info.filename):
                merged_zip.writestr(info.filename, rf.read(info.filename))


def merge_zip_content(zip_files: list, merger: ZipMerger = None) -> bytes:
    """Mescla o conteúdo de múltiplos arquivos ZIP/RAR em um único ZIP.

    Args:
        zip_files: lista de caminhos (str) ou objetos file-like (bytes/BytesIO)
                   para arquivos .zip ou .rar.
        merger: instância de ZipMerger com as condições de filtro. Se None,
                todos os arquivos são incluídos.

    Returns:
        Bytes do ZIP resultante.
    """
    if merger is None:
        merger = ZipMerger()

    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as merged_zip:
            for arquivo in zip_files:
                nome = getattr(arquivo, 'name', str(arquivo)).lower()
                if nome.endswith('.zip'):
                    _extrair_de_zip(arquivo, merger, merged_zip)
                elif nome.endswith('.rar'):
                    _extrair_de_rar(arquivo, merger, merged_zip)
        return buffer.getvalue()
    finally:
        buffer.close()


if __name__ == '__main__':
    import sys
    import argparse

    # -r: regex  -s: starts_with  -e: ends_with  -c: contains  -i: ignore_case
    parser = argparse.ArgumentParser(
        description='Mescla conteúdo de arquivos ZIP/RAR em um único ZIP.'
    )
    parser.add_argument('arquivos', nargs='+', help='Arquivos .zip ou .rar de entrada')
    parser.add_argument('saida', help='Caminho do ZIP de saída')
    parser.add_argument('-r', '--regex', dest='regex_pattern', default=None,
                        help='Padrão regex para filtrar arquivos')
    parser.add_argument('-s', '--start-with', default=None,
                        help='Incluir somente arquivos cujo nome começa com este valor')
    parser.add_argument('-e', '--end-with', default=None,
                        help='Incluir somente arquivos cujo nome termina com este valor')
    parser.add_argument('-c', '--contains', default=None,
                        help='Incluir somente arquivos cujo nome contém este valor')
    parser.add_argument('-i', '--ignore-case', action='store_true',
                        help='Comparações sem distinção de maiúsculas/minúsculas')
    args = parser.parse_args()

    merger = ZipMerger(
        regex_pattern=args.regex_pattern,
        start_with=args.start_with,
        end_with=args.end_with,
        contains=args.contains,
        ignore_case=args.ignore_case,
    )

    try:
        dados = merge_zip_content(args.arquivos, merger)
        with open(args.saida, 'wb') as f:
            f.write(dados)
        print(f"Sucesso! ZIP gerado em: {args.saida} ({len(dados):,} bytes)")
    except Exception as e:
        import traceback
        print(f"Erro: {e}")
        traceback.print_exc()
        sys.exit(1)
