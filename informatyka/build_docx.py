"""Генерує два .docx: Варіант 1 (с. 13) і Варіант 2 (с. 14) з методички «Інформатика».

Запуск: python3 build_docx.py  -> Variant_1.docx, Variant_2.docx поруч зі скриптом.
Документ збирається з «сирого» OOXML, щоб були доступні межі-малюнки сторінки,
точкові рамки з тінню, межі навколо окремих слів, буквиця тощо.
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

# «Студентська» мішана палітра (HEX = RGB з інструкції)
RED = "C00000"        # темно-червоний
ORANGE = "C55A11"     # темно-помаранчевий
PURPLE = "7030A0"     # фіолетовий
BLUE = "0070C0"       # синій
DGREEN = "548235"     # темно-зелений
L_YELLOW = "FFF2CC"   # світло-жовтий
L_GREEN = "E2EFDA"    # світло-зелений
L_BLUE = "DEEBF7"     # світло-блакитний
L_PEACH = "FBE5D6"    # світло-персиковий
PEACH = "F8CBAD"      # персиковий
GOLD = "FFE699"       # жовтий
BLACK = "000000"

# ---------------------------------------------------------------- run / paragraph helpers


def rpr(font=None, sz=None, b=False, i=False, u=None, caps=False, small_caps=False,
        strike=False, color=None, spacing=None, scale=None, position=None, shd=None,
        bdr=None, va=None):
    """sz, spacing, position — у пунктах; scale — масштаб у % (Ctrl+D → Додатково → Масштаб)."""
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
    if scale:
        x.append(f'<w:w w:val="{scale}"/>')
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


def sym(font, code, **kw):
    """Символ зі шрифту Wingdings/Symbol (Вставлення → Символ, код знака)."""
    return f'<w:r>{rpr(**kw)}<w:sym w:font="{font}" w:char="F0{code}"/></w:r>'


def border(side, val="single", sz=1.0, color=BLACK, space=4, shadow=False):
    """sz — товщина лінії в пунктах."""
    sh = ' w:shadow="1"' if shadow else ""
    return (f'<w:{side} w:val="{val}" w:sz="{int(sz * 8)}" w:space="{space}" '
            f'w:color="{color}"{sh}/>')


def box(sz=1.0, color=BLACK, shadow=True, val="single", space=4):
    return "".join(border(s, val, sz, color, space, shadow)
                   for s in ("top", "left", "bottom", "right"))


def cm(v):
    return int(round(v * 567))


def p(runs, jc=None, left=0, right=0, first=0, hanging=0, before=0, after=0,
      line=None, pbdr=None, shd=None, frame=None, keep_next=False):
    """Відступи — у см; before/after — у пунктах; line — множник або ("exact", twips)."""
    x = []
    if keep_next:
        x.append("<w:keepNext/>")
    if frame:
        x.append(frame)
    if pbdr:
        x.append(f"<w:pBdr>{pbdr}</w:pBdr>")
    if shd:
        x.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shd}"/>')
    sp = f'w:before="{int(before * 20)}" w:after="{int(after * 20)}"'
    if isinstance(line, tuple):
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
    return "<w:p><w:pPr>" + "".join(x) + "</w:pPr>" + "".join(runs) + "</w:p>"


def drop_cap(letter, font, sz, line_twips, color, position=0):
    """Буквиця «У тексті» на 3 рядки (Вставлення → Буквиця)."""
    frame = ('<w:framePr w:dropCap="drop" w:lines="3" w:hSpace="113" w:wrap="around" '
             'w:vAnchor="text" w:hAnchor="text"/>')
    return p([r(letter, font=font, sz=sz, color=color, position=position)],
             frame=frame, line=("exact", line_twips), keep_next=True)


def heading_box(text, font, sz, spacing, fill, line_color, jc="left",
                before=8, after=6):
    """Заголовок у рамці з тінню та заливкою (Межі та заливка → Тінь)."""
    return p([r(text, font=font, sz=sz, b=True, spacing=spacing)], jc=jc,
             pbdr=box(1.5, line_color, shadow=True), shd=fill, before=before, after=after,
             keep_next=True)


def table(rows, widths, borders, fills=None, jc="center", cell_mar=(60, 60, 0, 0),
          height=None):
    """rows — список рядків (кожна клітинка — XML абзаців); fills — заливка по стовпцях."""
    tw = sum(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    l, rr, t, bt = cell_mar
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="{tw}" w:type="dxa"/><w:jc w:val="{jc}"/>'
           f'<w:tblBorders>{borders}</w:tblBorders><w:tblLayout w:type="fixed"/>'
           f'<w:tblCellMar><w:top w:w="{t}" w:type="dxa"/><w:left w:w="{l}" w:type="dxa"/>'
           f'<w:bottom w:w="{bt}" w:type="dxa"/><w:right w:w="{rr}" w:type="dxa"/></w:tblCellMar>'
           f'<w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
    for row in rows:
        trpr = (f'<w:trPr><w:trHeight w:val="{height}" w:hRule="exact"/></w:trPr>'
                if height else "")
        out.append(f"<w:tr>{trpr}")
        for ci, (cell, w) in enumerate(zip(row, widths)):
            fill = fills[ci] if fills else None
            shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
            out.append(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}'
                       f'<w:vAlign w:val="center"/></w:tcPr>{cell}</w:tc>')
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


NO_BORDERS = ('<w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/>'
              '<w:right w:val="nil"/><w:insideH w:val="nil"/><w:insideV w:val="nil"/>')
TEXT_WIDTH = 9354  # 21 − 2,5 − 2 = 16,5 см


def dotted_heading(runs, fill, dot_color, before=5, after=3):
    """Штрихова (точкова) рамка + товста «тінь» справа і знизу, як на аркуші Варіанта 2.

    Таблиця 1×1: у клітинки лише права і нижня межі (товста лінія 3 пт),
    а всередині — абзац із точковою рамкою 1½ пт і заливкою.
    """
    inner = p(runs, jc="center", pbdr=box(1.5, dot_color, shadow=False, val="dotted",
                                          space=2), shd=fill, keep_next=True)
    borders = ('<w:top w:val="nil"/><w:left w:val="nil"/>'
               '<w:bottom w:val="single" w:sz="24" w:space="0" w:color="000000"/>'
               '<w:right w:val="single" w:sz="24" w:space="0" w:color="000000"/>'
               '<w:insideH w:val="nil"/><w:insideV w:val="nil"/>')
    gap_before = p([], line=("exact", int(before * 20)), keep_next=True)
    gap_after = p([], line=("exact", int(after * 20)) if after else ("exact", 20))
    return (gap_before + table([[inner]], [TEXT_WIDTH], borders, cell_mar=(40, 60, 40, 60))
            + gap_after)


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
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/>
<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/>
<w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>
</w:tblCellMar></w:tblPr></w:style>
</w:styles>'''


def write_docx(path, body, page_border):
    sect = (
        f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        f'<w:pgMar w:top="{cm(1.5)}" w:right="{cm(2.0)}" w:bottom="{cm(1.5)}" w:left="{cm(2.5)}" '
        f'w:header="{cm(1.0)}" w:footer="{cm(0.7)}" w:gutter="0"/>'
        f'{page_border}<w:cols w:space="708"/></w:sectPr>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {NS}><w:body>{body}{sect}</w:body></w:document>')
    rels = ('<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>')
    files = {}
    files.update({
        "[Content_Types].xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''',
        "word/_rels/document.xml.rels": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>''',
        "word/settings.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings {NS}><w:defaultTabStop w:val="708"/><w:characterSpacingControl w:val="doNotCompress"/>
<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>
</w:settings>''',
        "word/styles.xml": styles_xml(),
        "word/document.xml": document,
    })
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)


def page_border(art, width_pt, color, space=20):
    sides = "".join(f'<w:{s} w:val="{art}" w:sz="{width_pt}" w:space="{space}" w:color="{color}"/>'
                    for s in ("top", "left", "bottom", "right"))
    return f'<w:pgBorders w:offsetFrom="page">{sides}</w:pgBorders>'


# ---------------------------------------------------------------- Варіант 1
# Текст чорний, як на аркуші; кольорові лише заливки, рамки й лінії.


def variant1():
    b = []
    b.append(p([r("Варіант 1", font=ARIAL, sz=16, b=True)], jc="center", shd=PEACH,
               right=3.0))
    b.append(p([r("Білет № 14", font=ARIAL, sz=14, b=True)], jc="right", after=4))
    b.append(p([r("Системи опрацювання текстів. Призначення, основні функції "
                  "текстових редакторів. Система команд.", font=ARIAL, sz=13, b=True,
                  small_caps=True)], jc="center", left=1, right=1, after=6))
    b.append(p([
        r("Текстові редактори", font=BOOKMAN, color="FFFFFF", shd=PURPLE),
        r(" (ТР) - програми для підготовки "), r("текстових", i=True),
        r(" документів. ТР застосовуються: у діловодстві, редакційно-видавничій діяльності, "
          "у побуті тощо. "),
        r("Текстові процесори", font=BOOKMAN, color="FFFFFF", shd=DGREEN),
        r(" (ТП) - потужні ТР, що мають "), r("розширені", i=True, u="single"),
        r(" можливості."),
    ], jc="both"))
    b.append(heading_box("Основні функції текстових процесорів", COURIER, 12, 3,
                         L_YELLOW, ORANGE))
    bar = border("left", "single", 4.5, PURPLE, 12)
    for t in ["Введення тексту.",
              "Редагування тексту (переміщення, виділення, копіювання, перенесення).",
              "Форматування тексту (зміна параметрів сторінки, абзаців, шрифтів, таблиць).",
              "Робота з таблицями та використання графіки.",
              "Робота з декількома документами одночасно.",
              "Друкування тексту з заданою щільністю, якістю тощо."]:
        b.append(p([r(t)], jc="both", left=5.0, hanging=2.0, pbdr=bar))
    b.append(p([], line=("exact", 120)))
    b.append(drop_cap("О", ARIAL, 54, 920, BLACK, position=-4))
    b.append(p([
        r("днією з найпоширеніших операцій при роботі з документами є ", font=ARIAL, sz=13),
        r("форматування", font=ARIAL, sz=13, b=True, i=True, u="dotted"),
        r(" - зовнішнє виділення текстів із застосуванням параметрів ", font=ARIAL, sz=13),
        r("шрифту, абзацу, сторінки", font=ARIAL, sz=13, i=True, spacing=5),
    ], jc="both"))
    b.append(p([
        r("Процедура форматування символів", b=True, i=True),
        r(" включає вибір "), r("ТИПУ", font=ARIAL_BLACK, sz=12), r(", "),
        r("накреслення", i=True),
        r(", розміру і кольору шрифту; встановлення "),
        r("інтервалів", font=BOOKMAN, b=True, scale=150, spacing=1),
        r(" між символами, вибір "),
        r("засобу", bdr=border("bdr", "single", 0.75, BLACK, 0)),
        r(": "),
        r("анімації", bdr=border("bdr", "dotted", 1.0, BLACK, 0)),
        r(" (обрамлення, виділення) окремих слів та фрагментів тексту, введення в текст "
          "спеціальних символів"),
        sym("Wingdings", "4A"),
        r(" тощо."),
    ], jc="both", before=6, pbdr=border("bottom", "dashed", 1.0, PURPLE, 4)))
    b.append(p([r("Форматування абзаців передбачає їх вирівнювання, задавання відступів, "
                  "установлення інтервалів між рядками, контроль \"висячих\" рядків, "
                  "форматування табуляцією тощо.")], jc="both", first=2.5, before=6))
    b.append(heading_box("Пересування курсору по документу за допомогою:", COURIER, 12, 2,
                         L_GREEN, DGREEN))
    b.append(p([r("Спосіб 1", u="single"), r(" - курсору миші"), sym("Wingdings", "38")]))
    b.append(p([r("Спосіб 2", u="single"), r(" - лінійок прокрутки"), sym("Wingdings", "49")],
               jc="center"))
    b.append(p([r("Спосіб 3", u="single"), r(" - клавіш"), sym("Wingdings", "37")], jc="right"))
    b.append(heading_box("Робота з файлами", COURIER, 12, 6, L_BLUE, BLUE, jc="center"))
    cf = dict(font=CORSIVA, sz=12)
    for label, ic, action in [("Створення нового документа:", "32", "Створити"),
                              ("Відкриття документа:", "31", "Відкрити."),
                              ("Збереження документа:", "3C", "Зберегти (Зберегти як...)")]:
        b.append(p([
            r(label, u="single", **cf), r(" кнопка ", **cf), sym("Wingdings", ic, sz=12),
            r(" ", **cf), r("на", position=-3, **cf),
            r(" панелі швидкого доступу або Файл ", **cf),
            sym("Symbol", "DE", sz=12), r(" " + action, **cf),
        ], after=4))
    b.append(p([r("Хмельницький політехнічний коледж. Навчальна дисципліна "
                  "\"Інформатика\"", font=ARIAL, sz=12, b=True, spacing=-0.3)],
               jc="center", pbdr=box(1.5, RED, shadow=True), shd=L_PEACH, before=10))
    return "".join(b)


# ---------------------------------------------------------------- Варіант 2


def variant2():
    b = []
    b.append(p([r("Варіант 2", font=ARIAL, sz=16, b=True)], jc="center", shd=L_BLUE))
    b.append(dotted_heading([
        sym("Symbol", "A7", sz=13),
        r(" Основні теги мови HTML для створення гіпертекстового документа ",
          font=ARIAL, sz=13, b=True, spacing=2),
        sym("Symbol", "A7", sz=13)], L_YELLOW, ORANGE, before=4, after=4))
    b.append(drop_cap("Д", TNR, 48, 900, BLACK))
    b.append(p([
        r("ля створення Web-сторінок використовуються спеціальні "),
        r("мови розмітки", b=True, spacing=3),
        r(", що дозволяють керувати форматуванням, розташуванням і функціональністю "
          "елементів, які містяться на сторінках. Найбільш поширеною у Web є мова  ("),
        r("HYPER TEXT Markup Language-", font=ARIAL, small_caps=True),
        r("мова гіпертекстової розмітки)."),
    ], jc="both"))
    b.append(p([
        r("Документи HTML", b=True, i=True),
        r(" являють собою текст, у якому містяться спеціальні команди (або ТЕГИ), що "
          "визначають форматування сторінок і дозволяють розташовувати на ній "),
        r("гіперпосилання", u="single"),
        r(", зображення, спеціальні елементи форматування і певну службову інформацію."),
    ], jc="both", left=4.2, hanging=2.3, right=0.5, before=4))
    b.append(p([r("Тег завжди міститься між дужками < > і має такий вигляд:", font=COURIER,
                  sz=12, spacing=2)], jc="both", first=2.0, before=4, after=4))
    b.append(p([r("<ТЕГ атрибуті = ЗНАЧЕННЯ ... атрибут N = ЗНАЧЕННЯ >")], jc="center",
               pbdr=box(3.0, PURPLE, shadow=False, val="thickThinSmallGap"), left=0.3,
               right=0.3, after=6))
    b.append(p([r("Теги бувають "),
                r("поодинокими і контейнерними", font=COURIER, b=True, spacing=1),
                r(". Контейнером називається пара відкриваючий <Тег> і закриваючий </ТЕГ>.")],
               jc="both", line=1.3, shd=L_GREEN,
               pbdr=border("left", "thickThinSmallGap", 4.5, DGREEN, 8)))
    b.append(dotted_heading([
        sym("Symbol", "A9", sz=13),
        r(" Структура простого HTML-документа ", font=ARIAL, sz=13, b=True, spacing=3),
        sym("Symbol", "A9", sz=13)],
        L_BLUE, BLUE))
    lines = ["<HTML> - Початок документа", "<HEAD>", "ЗАГОЛОВОК ДОКУМЕНТА", "</HEAD>",
             "<BODY>", "ТІЛО ДОКУМЕНТА", "</BODY>", "</HTML>"]
    for k, t in enumerate(lines):
        b.append(p([r(t, sz=12)], left=2.2, right=8.0, shd=GOLD if k % 2 else None))
    b.append(dotted_heading([
        sym("Symbol", "A8", sz=13),
        r(" Теги стилістичного виділення тексту ", b=True, i=True, sz=13, spacing=3),
        sym("Symbol", "A8", sz=13)],
        L_PEACH, RED))
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
               jc="center", pbdr=box(0.75, BLUE, shadow=False), left=0.5, before=4, after=6))
    side = (border("left", "double", 2.25, PURPLE, 6)
            + border("right", "double", 2.25, PURPLE, 6))
    b.append(p([r("Тег <OL> може мати такі параметри:", **a)], left=0.6, right=7.0,
               pbdr=side, after=4))
    b.append(p([r("TYPE", b=True, **a), r(" - вид лічильника:", **a)], left=1.2))
    cells = [("A", "великі латинські літери"), ("a", "маленькі латинські літери"),
             ("I", "великі римські літери"), ("i", "маленькі римські літери"),
             ("1", "звичайні цифри")]
    t = dict(font=ARIAL, sz=11)
    row = [p([r(k, b=True, **t), r(" - " + v, **t)], jc="center") for k, v in cells]
    inside_v = ('<w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/>'
                '<w:right w:val="nil"/><w:insideH w:val="nil"/>'
                f'<w:insideV w:val="single" w:sz="8" w:space="0" w:color="{PURPLE}"/>')
    b.append(table([row], [1890, 1890, 1890, 1890, 1794], inside_v,
                   fills=[None, None, GOLD, None, None]))
    b.append(p([r("START", b=True, **a),
                r(" - встановлює число,  яким буде починатися список.", **a)], left=1.2))
    b.append(p([r("Хмельницький політехнічний коледж. Навчальна дисципліна "
                  "\"Інформатика\"", font=CORSIVA, sz=14, b=True)],
               jc="center", shd=L_GREEN, before=6))
    return "".join(b)


# ---------------------------------------------------------------- каталог рамок-малюнків

BORDER_CANDIDATES = [
    "swirligig", "hypnotic", "circlesLines", "circlesRectangles", "compass", "fans",
    "triangleCircle1", "triangleCircle2", "rings", "moons", "ovals", "sun", "quadrants",
    "eclipsingSquares1", "eclipsingSquares2", "shapes1", "shapes2", "gems", "xIllusions",
    "cakeSlice", "mosaic", "doubleD", "earth1", "earth2",
]


def border_catalog():
    """По одній сторінці на кожну рамку: розділ з власною межею сторінки і підписом."""
    out = []
    last = len(BORDER_CANDIDATES) - 1
    for k, art in enumerate(BORDER_CANDIDATES):
        out.append(p([r(f"№ {k + 1}", font=ARIAL, sz=40, b=True)], jc="center", before=200))
        label = p([r(f"рамка «{art}»", font=ARIAL, sz=20)], jc="center")
        if k == last:
            out.append(label)
            continue
        sect = (f'<w:sectPr><w:type w:val="nextPage"/><w:pgSz w:w="11906" w:h="16838"/>'
                f'<w:pgMar w:top="{cm(1.5)}" w:right="{cm(2.0)}" w:bottom="{cm(1.5)}" '
                f'w:left="{cm(2.5)}" w:header="{cm(1.0)}" w:footer="{cm(0.7)}" w:gutter="0"/>'
                f'{page_border(art, 16, BLACK)}<w:cols w:space="708"/></w:sectPr>')
        out.append(label.replace("</w:pPr>", f"{sect}</w:pPr>", 1))
    return "".join(out), page_border(BORDER_CANDIDATES[last], 16, BLACK)


if __name__ == "__main__":
    # обидві рамки — вбудовані «Рисунки» Word (Разметка страницы → Границы страниц → Рисунок)
    write_docx(os.path.join(HERE, "Variant_1.docx"), variant1(),
               page_border("musicNotes", 18, PURPLE))
    write_docx(os.path.join(HERE, "Variant_2.docx"), variant2(),
               page_border("swirligig", 16, RED))
    catalog, last_border = border_catalog()
    write_docx(os.path.join(HERE, "Ramky_vybir.docx"), catalog, last_border)
    print("ok")
