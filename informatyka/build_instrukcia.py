"""ІНСТРУКЦІЯ.md -> Instrukcia.docx (через pandoc).

Pandoc складає блок коду в один абзац із розривами рядка (Shift+Enter), а для
копіювання тексту в Word кожен рядок має бути окремим абзацом (Enter). Тому після
pandoc кожен рядок блоку стає окремим абзацом того ж стилю.
"""
import os
import re
import subprocess
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "ІНСТРУКЦІЯ.md")
OUT = os.path.join(HERE, "Instrukcia.docx")

CODE_P = re.compile(r'<w:p><w:pPr><w:pStyle w:val="SourceCode" /></w:pPr>(.*?)</w:p>', re.S)
BREAK = "<w:r><w:br /></w:r>"
PPR = '<w:pPr><w:pStyle w:val="SourceCode" /><w:spacing w:before="0" w:after="0" /></w:pPr>'


def split_lines(match):
    return "".join(f"<w:p>{PPR}{runs}</w:p>" for runs in match.group(1).split(BREAK))


def main():
    subprocess.run(["pandoc", SRC, "-o", OUT], check=True)
    with zipfile.ZipFile(OUT) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    doc = parts["word/document.xml"].decode("utf-8")
    parts["word/document.xml"] = CODE_P.sub(split_lines, doc).encode("utf-8")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    print("ok")


if __name__ == "__main__":
    main()
