import pymupdf4llm
from pathlib import Path

def text_converter(input_path):
    caminho_pdf = Path(input_path)
    caminho_md = caminho_pdf.with_suffix(".md")
    formated_text = pymupdf4llm.to_markdown(str(caminho_pdf))
    
    with open(caminho_md, "w", encoding="utf-8") as f:
        f.write(formated_text)
        

