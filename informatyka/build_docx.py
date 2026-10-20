"""Генерує два .docx: Варіант 1 (с. 13) і Варіант 2 (с. 14) з методички «Інформатика».

Запуск: python3 build_docx.py  -> Variant_1.docx, Variant_2.docx поруч зі скриптом.
Документ збирається з «сирого» OOXML, щоб були доступні межі-малюнки сторінки,
тінь у межах абзацу, межі навколо окремих слів, буквиця тощо.
"""
import os
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))

TNR = "Times New Roman"
ARIAL = "Arial"
ARIAL_BLACK = "Arial Black"
COURIER = "Courier New"
BOOKMAN = "Bookman Old Style"
CORSIVA = "Monotype Corsiva"

# ---------------------------------------------------------------- run / paragraph helpers


def rpr(font=None, sz=None, b=False, i=False, u=None, caps=False, small_caps=False,
        strike=False, color=None, spacing=None, position=None, shd=None, bdr=None,
        va=None):
    """sz — у пунктах; spacing/position — у пунктах (розріджений інтервал / зміщення)."""
    x = []
    if font:
        x.append(f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>')
    if b:
        x.append("<w:b/><w:bCs/>")
    if i:
        x.append("<w:i/><w:iCs/>")
    if caps:
        x.append("<w:caps/>")
    if small_caps:
        x.append("<w:smallCaps/>")
    if strike:
        x.append("<w:strike/>")
    if color:
        x.append(f'<w:color w:val="{color}"/>')
    if spacing:
        x.append(f'<w:spacing w:val="{int(spacing * 20)}"/>')
    if position:
        x.append(f'<w:position w:val="{int(position * 2)}"/>')
    if sz:
        x.append(f'<w:sz w:val="{int(sz * 2)}"/><w:szCs w:val="{int(sz * 2)}"/>')
    if u:
        x.append(f'<w:u w:val="{u}"/>')
    if bdr:
        x.append(bdr)
    if shd:
        x.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shd}"/>')
    if va:
        x.append(f'<w:vertAlign w:val="{va}"/>')
    return "<w:rPr>" + "".join(x) + "</w:rPr>" if x else ""


def r(text, **kw):
    return f'<w:r>{rpr(**kw)}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def tab(**kw):
    return f"<w:r>{rpr(**kw)}<w:tab/></w:r>"


def sym(font, code, **kw):
    """Символ зі шрифту Wingdings/Symbol (Вставлення → Символ, код знака)."""
    return f'<w:r>{rpr(**kw)}<w:sym w:font="{font}" w:char="F0{code}"/></w:r>'


def border(side, val="single", sz=1.0, color="000000", space=4, shadow=False):
    """sz — товщина лінії в пунктах."""
    sh = ' w:shadow="1"' if shadow else ""
    return (f'<w:{side} w:val="{val}" w:sz="{int(sz * 8)}" w:space="{space}" '
            f'w:color="{color}"{sh}/>')


def box(sz=1.0, color="000000", shadow=True, val="single", space=4):
    return "".join(border(s, val, sz, color, space, shadow)
                   for s in ("top", "left", "bottom", "right"))


def cm(v):
    return int(round(v * 567))


def p(runs, jc=None, left=0, right=0, first=0, hanging=0, before=0, after=0,
      line=None, pbdr=None, shd=None, tabs=None, frame=None, keep_next=False,
      run_default=None):
    """Відступи — у см; before/after — у пунктах; line — множник (1.0, 1.5)."""
    x = []
    if keep_next:
        x.append("<w:keepNext/>")
    if frame:
        x.append(frame)
    if pbdr:
        x.append(f"<w:pBdr>{pbdr}</w:pBdr>")
    if shd:
        x.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shd}"/>')
    if tabs:
        x.append("<w:tabs>" + "".join(
            f'<w:tab w:val="{a}" w:pos="{cm(pos)}"/>' for a, pos in tabs) + "</w:tabs>")
    sp = f'w:before="{int(before * 20)}" w:after="{int(after * 20)}"'
    if isinstance(line, tuple):  # ("exact", twips)
        sp += f' w:line="{line[1]}" w:lineRule="exact"'
    elif line:
        sp += f' w:line="{int(line * 240)}" w:lineRule="auto"'
    x.append(f"<w:spacing {sp}/>")
    ind = f'w:left="{cm(left)}" w:right="{cm(right)}"'
    if hanging:
        ind += f' w:hanging="{cm(hanging)}"'
    elif first:
        ind += f' w:firstLine="{cm(first)}"'
    x.append(f"<w:ind {ind}/>")
    if jc:
        x.append(f'<w:jc w:val="{jc}"/>')
    if run_default:
        x.append(run_default)
    return "<w:p><w:pPr>" + "".join(x) + "</w:pPr>" + "".join(runs) + "</w:p>"


def drop_cap(letter, font, sz, line_twips, color, position=0):
    """Буквиця «У тексті» на 3 рядки (Вставлення → Буквиця)."""
    frame = ('<w:framePr w:dropCap="drop" w:lines="3" w:hSpace="113" w:wrap="around" '
             'w:vAnchor="text" w:hAnchor="text"/>')
    return p([r(letter, font=font, sz=sz, color=color, position=position)],
             frame=frame, line=("exact", line_twips), keep_next=True)


def heading_box(text, font, sz, spacing, fill, line_color, jc="left", b=True, i=False,
                before=8, after=6, left=0, right=0):
    """Заголовок у рамці з тінню та заливкою (Межі та заливка → Тінь)."""
    return p([r(text, font=font, sz=sz, b=b, i=i, spacing=spacing)], jc=jc,
             pbdr=box(1.0, line_color, shadow=True), shd=fill, before=before, after=after,
             left=left, right=right, keep_next=True)


def table(rows, widths, fill_col=None, fill=None, color="000000"):
    """Таблиця без зовнішніх меж, лише внутрішні вертикальні лінії."""
    tw = sum(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="{tw}" w:type="dxa"/><w:jc w:val="center"/>'
           f'<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/>'
           f'<w:right w:val="nil"/><w:insideH w:val="nil"/>'
           f'<w:insideV w:val="single" w:sz="8" w:space="0" w:color="{color}"/></w:tblBorders>'
           f'<w:tblLayout w:type="fixed"/>'
           f'<w:tblCellMar><w:left w:w="60" w:type="dxa"/><w:right w:w="60" w:type="dxa"/></w:tblCellMar>'
           f'<w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
    for row in rows:
        out.append("<w:tr>")
        for ci, (cell, w) in enumerate(zip(row, widths)):
            shd = (f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
                   if ci == fill_col else "")
            out.append(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}'
                       f'<w:vAlign w:val="center"/></w:tcPr>{cell}</w:tc>')
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


# ---------------------------------------------------------------- package


NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def styles_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {NS}>
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="{TNR}" w:hAnsi="{TNR}" w:eastAsia="{TNR}" w:cs="{TNR}"/>
<w:sz w:val="26"/><w:szCs w:val="26"/><w:lang w:val="uk-UA" w:eastAsia="uk-UA" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/>
<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/>
<w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>
</w:tblCellMar></w:tblPr></w:style>
</w:styles>'''


def footer_xml(page_no):
    body = p([tab(), r("ХПК НУ «ЛП»", b=True, sz=12), tab(), r(f"- {page_no} -", sz=12)],
             tabs=[("center", 8.25), ("right", 16.5)])
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}>{body}</w:ftr>'


def write_docx(path, body, page_border, footer_page):
    sect = (
        '<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        f'<w:pgMar w:top="{cm(1.5)}" w:right="{cm(2.0)}" w:bottom="{cm(1.5)}" w:left="{cm(2.5)}" '
        f'w:header="{cm(1.0)}" w:footer="{cm(0.7)}" w:gutter="0"/>'
        f'{page_border}<w:cols w:space="708"/></w:sectPr>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {NS}><w:body>{body}{sect}</w:body></w:document>')
    files = {
        "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''',
        "word/_rels/document.xml.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>''',
        "word/settings.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings {NS}><w:defaultTabStop w:val="708"/><w:characterSpacingControl w:val="doNotCompress"/>
<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>
</w:settings>''',
        "word/styles.xml": styles_xml(),
        "word/footer1.xml": footer_xml(footer_page),
        "word/document.xml": document,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)


def page_border(art, width_pt, color):
    sides = "".join(f'<w:{s} w:val="{art}" w:sz="{width_pt}" w:space="24" w:color="{color}"/>'
                    for s in ("top", "left", "bottom", "right"))
    return f'<w:pgBorders w:offsetFrom="page">{sides}</w:pgBorders>'


# ---------------------------------------------------------------- Варіант 1 (синя гама)

V1_DARK = "1F4E79"   # темно-синій: рамки, тінь, буквиця
V1_FILL = "DEEAF6"   # світло-блакитна заливка заголовків
V1_BAR = "BDD7EE"    # заливка смуги «Варіант 1»


def variant1():
    b = []
    b.append(p([r("Варіант 1", font=ARIAL, sz=16, b=True)], jc="center", shd=V1_BAR,
               right=2.5))
    b.append(p([r("Білет № 14", font=ARIAL, sz=14, b=True)], jc="right", after=6))
    b.append(p([r("Системи опрацювання текстів. Призначення, основні функції "
                  "текстових редакторів. Система команд.", font=ARIAL, sz=13, b=True,
                  small_caps=True)], jc="center", left=1, right=1, after=6))
    hl = dict(font=BOOKMAN, color="FFFFFF", shd=V1_DARK)
    b.append(p([
        r("Текстові редактори", **hl),
        r(" (ТР) - програми для підготовки "), r("текстових", i=True),
        r(" документів. ТР застосовуються: у діловодстві, редакційно-видавничій діяльності, "
          "у побуті тощо. "),
        r("Текстові процесори", **hl),
        r(" (ТП) - потужні ТР, що мають "), r("розширені", i=True, u="single"),
        r(" можливості."),
    ], jc="both"))
    b.append(heading_box("Основні функції текстових процесорів", COURIER, 12, 3,
                         V1_FILL, V1_DARK))
    bar = border("left", "single", 4.5, "000000", 12)
    for t in ["Введення тексту.",
              "Редагування тексту (переміщення, виділення, копіювання, перенесення).",
              "Форматування тексту (зміна параметрів сторінки, абзаців, шрифтів, таблиць).",
              "Робота з таблицями та використання графіки.",
              "Робота з декількома документами одночасно.",
              "Друкування тексту з заданою щільністю, якістю тощо."]:
        b.append(p([r(t)], jc="both", left=5.0, hanging=2.0, pbdr=bar))
    b.append(p([], after=0, line=("exact", 120)))
    # буквиця «О» + абзац Arial
    b.append(drop_cap("О", ARIAL, 54, 920, V1_DARK, position=-4))
    b.append(p([
        r("днією з найпоширеніших операцій при роботі з документами є ", font=ARIAL, sz=13),
        r("форматування", font=ARIAL, sz=13, b=True, i=True, u="single"),
        r(" - зовнішнє виділення текстів із застосуванням параметрів ", font=ARIAL, sz=13),
        r("шрифту, абзацу, сторінки", font=ARIAL, sz=13, spacing=5),
    ], jc="both"))
    b.append(p([
        r("Процедура форматування символів", b=True, i=True, u="single"),
        r(" включає вибір "), r("ТИПУ", font=ARIAL_BLACK, sz=12), r(", "),
        r("накреслення", i=True),
        r(", розміру і кольору шрифту; встановлення "),
        r("інтервалів", font=BOOKMAN, b=True, spacing=1),
        r(" між символами, вибір "),
        r("засобу", bdr=border("bdr", "single", 0.75, "000000", 0)),
        r(": "),
        r("анімації", bdr=border("bdr", "dotted", 1.0, V1_DARK, 0)),
        r(" (обрамлення, виділення) окремих слів та фрагментів тексту, введення в текст "
          "спеціальних символів"),
        sym("Wingdings", "4A"),
        r(" тощо."),
    ], jc="both", before=6, pbdr=border("bottom", "dashed", 1.0, "000000", 4)))
    b.append(p([r("Форматування абзаців передбачає їх вирівнювання, задавання відступів, "
                  "установлення інтервалів між рядками, контроль \"висячих\" рядків, "
                  "форматування табуляцією тощо.")], jc="both", first=2.5, before=6))
    b.append(heading_box("Пересування курсору по документу за допомогою:", COURIER, 12, 2,
                         V1_FILL, V1_DARK))
    b.append(p([r("Спосіб 1", u="single"), r(" - курсору миші"), sym("Wingdings", "38")]))
    b.append(p([r("Спосіб 2", u="single"), r(" - лінійок прокрутки"), sym("Wingdings", "49")],
               jc="center"))
    b.append(p([r("Спосіб 3", u="single"), r(" - клавіш"), sym("Wingdings", "37")],
               jc="right"))
    b.append(heading_box("Робота з файлами", COURIER, 12, 6, V1_FILL, V1_DARK, jc="center"))
    cf = dict(font=CORSIVA, sz=13)
    for label, icon, action in [("Створення нового документа:", "32", "Створити"),
                                ("Відкриття документа:", "31", "Відкрити."),
                                ("Збереження документа:", "3C", "Зберегти (Зберегти як...)")]:
        b.append(p([
            r(label, u="single", **cf), r(" кнопка ", **cf), sym("Wingdings", icon, sz=13),
            r(" ", **cf), r("на", position=-3, **cf),
            r(" панелі швидкого доступу або Файл ", **cf),
            sym("Symbol", "DE", sz=13), r(" " + action, **cf),
        ], after=4))
    b.append(p([r("Хмельницький політехнічний коледж. Навчальна дисципліна "
                  "\"Інформатика\"", font=ARIAL, sz=12, b=True, i=True, spacing=-0.5)], jc="center",
               pbdr=box(1.0, V1_DARK, shadow=True), shd=V1_FILL, before=10))
    return "".join(b)


# ---------------------------------------------------------------- Варіант 2 (зелена гама)

V2_DARK = "385723"   # темно-зелений
V2_FILL = "E2EFDA"   # світло-зелена заливка
V2_BAR = "C5E0B3"    # смуга «Варіант 2» / рядки структури


def variant2():
    b = []
    b.append(p([r("Варіант 2", font=ARIAL, sz=16, b=True)], jc="center", shd=V2_BAR,
               after=6))
    b.append(p([sym("Symbol", "A7", sz=14, color=V2_DARK),
                r(" Основні теги мови HTML для створення гіпертекстового документа ",
                  font=ARIAL, sz=13, b=True, spacing=2),
                sym("Symbol", "A7", sz=14, color=V2_DARK)],
               jc="center", pbdr=box(1.0, V2_DARK, shadow=True), shd=V2_FILL,
               left=0.5, right=0.5, after=4))
    b.append(drop_cap("Д", TNR, 48, 900, V2_DARK))
    b.append(p([
        r("ля створення Web-сторінок використовуються спеціальні "),
        r("мови розмітки", b=True, spacing=3),
        r(", що дозволяють керувати форматуванням, розташуванням і функціональністю "
          "елементів, які містяться на сторінках. Найбільш поширеною у Web є мова  ("),
        r("HYPER TEXT Markup Language-", font=ARIAL, small_caps=True),
        r("мова гіпертекстової розмітки)."),
    ], jc="both"))
    b.append(p([
        r("Документи HTML", b=True, i=True, sz=13),
        r(" являють собою текст, у якому містяться спеціальні команди (або ТЕГИ), що "
          "визначають форматування сторінок і дозволяють розташовувати на ній ", sz=13),
        r("гіперпосилання", u="single", sz=13),
        r(", зображення, спеціальні елементи форматування і певну службову інформацію.",
          sz=13),
    ], jc="both", left=4.2, hanging=2.3, right=0.5, before=4))
    b.append(p([r("Тег завжди міститься між дужками < > і має такий вигляд:", font=COURIER,
                  sz=12, spacing=2)], jc="both", first=2.0, before=4, after=4))
    b.append(p([r("<ТЕГ атрибуті = ЗНАЧЕННЯ ... атрибут N = ЗНАЧЕННЯ >")], jc="center",
               pbdr=box(2.25, V2_DARK, shadow=True), left=0.3, right=0.3, after=6))
    b.append(p([r("Теги бувають "),
                r("поодинокими і контейнерними", font=COURIER, b=True, spacing=1),
                r(". Контейнером називається пара відкриваючий <Тег> і закриваючий </ТЕГ>.")],
               jc="both", line=1.3, shd=V2_FILL,
               pbdr=border("left", "thickThinSmallGap", 4.5, V2_DARK, 8)))
    b.append(p([sym("Symbol", "A9", sz=14, color="C00000"),
                r(" Структура простого HTML-документа ", font=ARIAL, sz=13, b=True, spacing=3),
                sym("Symbol", "A9", sz=14, color="C00000")],
               jc="center", pbdr=box(1.0, V2_DARK, shadow=True), shd=V2_FILL,
               before=8, after=4, keep_next=True))
    lines = ["<HTML> - Початок документа", "<HEAD>", "ЗАГОЛОВОК ДОКУМЕНТА", "</HEAD>",
             "<BODY>", "ТІЛО ДОКУМЕНТА", "</BODY>", "</HTML>"]
    for k, t in enumerate(lines):
        b.append(p([r(t, sz=12)], left=2.2, right=8.0, shd=V2_BAR if k % 2 else None))
    b.append(p([sym("Symbol", "A8", sz=14, color=V2_DARK),
                r(" Теги стилістичного виділення тексту ", b=True, i=True, sz=13, spacing=3),
                sym("Symbol", "A8", sz=14, color=V2_DARK)],
               jc="center", pbdr=box(1.0, V2_DARK, shadow=True), shd=V2_FILL,
               before=8, after=4, keep_next=True))
    s = dict(sz=12)
    b.append(p([r("<STRIKE>...</STRIKE> - Виділення перекреслюванням (", **s),
                r("Помилка", strike=True, **s), r(")", **s)]))
    b.append(p([r("<B>...</B> Виділення напівжирним шрифтом (", **s),
                r("Інформатика", b=True, **s), r(")", **s)]))
    b.append(p([r("<I>...</I> Виділення курсивом (", **s), r("Програмування", i=True, **s),
                r(")", **s)]))
    b.append(p([r("<U>...</U> Виділення підкреслюванням (", **s),
                r("Бази даних", u="single", **s), r(")", **s)]))
    b.append(p([r("<SUP>...</SUP> Шрифт у верхньому індексі (x", **s),
                r("y", va="superscript", **s), r(")", **s)]))
    b.append(p([r("<SUB>...</SUB> Шрифту нижньому індексі (Температура", **s),
                r("січнева", va="subscript", **s), r(")", **s)]))
    a = dict(font=ARIAL, sz=12)
    n = dict(font=ARIAL, sz=11)
    b.append(p([sym("Symbol", "AA", sz=11), r(" ", **n), r("НУМЕРОВАНИЙ", b=True, **n),
                r(" список починається з тега ", **n), r("<OL>", b=True, **n),
                r(" і закривається тегом ", **n), r("</OL>", b=True, **n), r(". ", **n),
                sym("Symbol", "AA", sz=11)],
               jc="center", pbdr=box(1.0, V2_DARK, shadow=True), left=0.5, before=6,
               after=6))
    side = border("left", "single", 4.5, V2_DARK, 6) + border("right", "single", 4.5, V2_DARK, 6)
    b.append(p([r("Тег <OL> може мати такі параметри:", **a)], left=0.6, right=7.0,
               pbdr=side, after=4))
    b.append(p([r("TYPE", b=True, **a), r(" - вид лічильника:", **a)], left=1.2))
    cells = [("A", "великі латинські літери"), ("a", "маленькі латинські літери"),
             ("I", "великі римські літери"), ("i", "маленькі римські літери"),
             ("1", "звичайні цифри")]
    t = dict(font=ARIAL, sz=11)
    row = [p([r(k, b=True, **t), r(" - " + v, **t)], jc="center") for k, v in cells]
    b.append(table([row], [1890, 1890, 1890, 1890, 1795], fill_col=2, fill=V2_BAR))
    b.append(p([r("START", b=True, **a),
                r(" - встановлює число,  яким буде починатися список.", **a)], left=1.2))
    b.append(p([r("Хмельницький політехнічний коледж. Навчальна дисципліна "
                  "\"Інформатика\"", sz=12, b=True, i=True)], jc="center", shd=V2_FILL,
               pbdr=border("bottom", "single", 2.25, V2_DARK, 1), before=8))
    return "".join(b)


if __name__ == "__main__":
    write_docx(os.path.join(HERE, "Variant_1.docx"), variant1(),
               page_border("musicNotes", 20, V1_DARK), 13)
    write_docx(os.path.join(HERE, "Variant_2.docx"), variant2(),
               page_border("quadrants", 16, V2_DARK), 14)
    print("ok")
