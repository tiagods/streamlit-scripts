import patoolib
import zipfile
import rarfile
import os
import shutil
from fpdf import FPDF

#if shutil.which("rar") is None:
   #raise EnvironmentError("O executável 'rar' não foi encontrado. Verifique a instalação")

if not os.path.exists('input'):
    os.makedirs('input')
        
if not os.path.exists('output'):
    os.makedirs('output')

def _create_pdf(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.cell(0, 10, text)
    return bytes(pdf.output())


#generate example zip files for testing
def create_example_zip_files():
    with zipfile.ZipFile('input/archive1.zip', 'w') as zf:
        zf.writestr('file1.txt', 'This is file 1 in archive 1.')
        zf.writestr('file2.txt', 'This is file 2 in archive 1.')
        zf.writestr('image.png', 'This is an image file in archive 1.')

    with zipfile.ZipFile('input/archive2.zip', 'w') as zf:
        zf.writestr('file3.txt', 'This is file 3 in archive 2.')
        zf.writestr('file4.txt', 'This is file 4 in archive 2.')
        zf.writestr('document.pdf', _create_pdf('This is a PDF file in archive 2.'))
    
    os.system('echo "This is file 5 in archive 3." > file5.txt')
    os.system('echo "This is file 6 in archive 3." > file6.txt')
    os.system('echo "This is a PowerPoint file in archive 3." > presentation.pptx')
    
    patoolib.create_archive('input/archive3.rar', ['file5.txt', 'file6.txt', 'presentation.pptx'])
    
    with zipfile.ZipFile('input/archive4.zip', 'w') as zf:
        zf.writestr('file7.txt', 'This is file 7 in archive 4.')
        zf.writestr('file8.txt', 'This is file 8 in archive 4.')
        zf.writestr('spreadsheet.xlsx', 'This is an Excel file in archive 4.')

create_example_zip_files()

if __name__ == "__main__":
    zip_files = ['input/archive1.zip', 'input/archive2.zip', 'input/archive3.rar', 'input/archive4.zip']
    output_zip = 'tmp/merged_archive.zip'
    # merge_zip_content(zip_files, output_zip)