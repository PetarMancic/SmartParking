"""
Generise Seminarski_rad_Smart_Parking.docx na osnovu teksta definisanog u ovoj
skripti (python-docx). Struktura prati postojeci seminarski rad
(C:\\FAX\\MASTER\\SIR1\\Seminarski rad.docx) kao uzor: naslovna strana, TOC polje,
7 poglavlja, numerisane slike/tabele.

Pokretanje:
    python docs/seminarski-rad/generate_seminarski_rad.py
"""

import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
OUTPUT_PATH = os.path.join(BASE_DIR, "Seminarski_rad_Smart_Parking.docx")

BODY_FONT = "Times New Roman"
CODE_FONT = "Consolas"

ACCENT = RGBColor(0x1F, 0x3B, 0x73)

fig_counter = [0]
table_counter = [0]


# --------------------------------------------------------------------------
# Osnovni helperi za formatiranje
# --------------------------------------------------------------------------

def setup_styles(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), BODY_FONT)

    for level, size in ((1, 16), (2, 14), (3, 12.5)):
        style = doc.styles[f"Heading {level}"]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = ACCENT
        style.paragraph_format.space_before = Pt(18 if level == 1 else 12)
        style.paragraph_format.space_after = Pt(10)
        style.paragraph_format.line_spacing = 1.15
        style.paragraph_format.keep_with_next = True


def h1(doc, text, page_break_before=True):
    if page_break_before:
        doc.add_page_break()
    return doc.add_heading(text, level=1)


def h2(doc, text):
    return doc.add_heading(text, level=2)


def h3(doc, text):
    return doc.add_heading(text, level=3)


def p(doc, text, *, italic=False, bold=False, align=None, space_after=8):
    para = doc.add_paragraph()
    if align is not None:
        para.alignment = align
    para.paragraph_format.space_after = Pt(space_after)
    run = para.add_run(text)
    run.italic = italic
    run.bold = bold
    return para


def bullets(doc, items):
    for item in items:
        para = doc.add_paragraph(style="List Bullet")
        para.paragraph_format.space_after = Pt(4)
        run = para.add_run(item)
        run.font.name = BODY_FONT


def formula(doc, text):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(6)
    para.paragraph_format.space_after = Pt(6)
    run = para.add_run(text)
    run.italic = True
    run.font.size = Pt(12.5)
    return para


def code_block(doc, code_text):
    para = doc.add_paragraph()
    para.paragraph_format.line_spacing = 1.0
    para.paragraph_format.space_before = Pt(4)
    para.paragraph_format.space_after = Pt(10)
    para.paragraph_format.left_indent = Cm(0.4)

    pPr = para._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F2F2F2")
    pPr.append(shd)

    lines = code_text.strip("\n").split("\n")
    for i, line in enumerate(lines):
        run = para.add_run(line if line.strip() else "\u00a0")
        run.font.name = CODE_FONT
        run.font.size = Pt(9)
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:ascii"), CODE_FONT)
        rfonts.set(qn("w:hAnsi"), CODE_FONT)
        if i < len(lines) - 1:
            run.add_break(WD_BREAK.LINE)
    return para


def figure(doc, filename, caption, width_cm=14.5):
    fig_counter[0] += 1
    doc.add_picture(os.path.join(ASSETS_DIR, filename), width=Cm(width_cm))
    last_para = doc.paragraphs[-1]
    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(12)
    run = cap.add_run(f"Slika {fig_counter[0]}. {caption}")
    run.italic = True
    run.font.size = Pt(10.5)
    return fig_counter[0]


def table_grid(doc, headers, rows, caption=None):
    table_counter[0] += 1
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr_cells = table.rows[0].cells
    for i, htext in enumerate(headers):
        hdr_cells[i].text = ""
        run = hdr_cells[i].paragraphs[0].add_run(htext)
        run.bold = True
        run.font.size = Pt(10)
        run.font.name = BODY_FONT
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "DCE6F1")
        hdr_cells[i]._tc.get_or_add_tcPr().append(shd)

    for row_data in rows:
        row_cells = table.add_row().cells
        for i, value in enumerate(row_data):
            row_cells[i].text = ""
            run = row_cells[i].paragraphs[0].add_run(str(value))
            run.font.size = Pt(10)
            run.font.name = BODY_FONT

    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_before = Pt(4)
        cap.paragraph_format.space_after = Pt(14)
        run = cap.add_run(f"Tabela {table_counter[0]}. {caption}")
        run.italic = True
        run.font.size = Pt(10.5)
    else:
        doc.add_paragraph().paragraph_format.space_after = Pt(10)

    return table_counter[0]


def add_field(paragraph, instr_text, placeholder_text):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    run._r.append(fld_begin)

    run2 = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instr_text
    run2._r.append(instr)

    run3 = paragraph.add_run()
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    run3._r.append(fld_sep)

    run4 = paragraph.add_run(placeholder_text)

    run5 = paragraph.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run5._r.append(fld_end)


# --------------------------------------------------------------------------
# Naslovna strana i sadrzaj
# --------------------------------------------------------------------------

def build_title_page(doc):
    def center(text, size, bold=False, space_before=0, space_after=0, italic=False):
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.space_before = Pt(space_before)
        para.paragraph_format.space_after = Pt(space_after)
        run = para.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.size = Pt(size)
        run.font.name = BODY_FONT
        return para

    center("UNIVERZITET U NIŠU", 15, bold=True, space_before=10, space_after=2)
    center("ELEKTRONSKI FAKULTET", 15, bold=True, space_after=60)

    center("Preporuka parking mesta u pametnim gradovima", 18, bold=True, space_after=2)
    center("primenom analize podataka u realnom vremenu", 18, bold=True, space_after=10)
    center("(Smart Parking Recommendation)", 12, italic=True, space_after=30)
    center("Seminarski rad", 14, bold=True, space_after=6)
    center("Studijski program: Računarstvo i informatika", 12, space_after=2)
    center("Modul: Softversko inženjerstvo", 12, space_after=100)

    info_table = doc.add_table(rows=2, cols=2)
    info_table.autofit = True
    widths = (Cm(6), Cm(6))
    for row in info_table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = w

    c00 = info_table.rows[0].cells[0].paragraphs[0]
    c00.add_run("Student:").bold = True
    c01 = info_table.rows[0].cells[1].paragraphs[0]
    c01.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    c01.add_run("Mentor:").bold = True

    c10 = info_table.rows[1].cells[0].paragraphs[0]
    c10.add_run("Petar Mančić, 1906")
    c11 = info_table.rows[1].cells[1].paragraphs[0]
    c11.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    c11.add_run("Prof. Petar Rajković")

    for row in info_table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.name = BODY_FONT
                    run.font.size = Pt(12)

    center("", 12, space_after=120)
    center("Niš, avgust 2026. godina", 12, space_before=140)


def build_toc(doc):
    doc.add_page_break()
    heading = doc.add_heading("Sadržaj", level=1)
    heading.paragraph_format.space_after = Pt(10)

    para = doc.add_paragraph()
    add_field(para, 'TOC \\o "1-3" \\h \\z \\u', "Klikom desnim tasterom na ovo polje i izborom "
              "\"Update Field\" (ili tasterom F9) učitaće se stvarni sadržaj sa brojevima strana.")
    note = doc.add_paragraph()
    run = note.add_run(
        "Napomena: sadržaj je generisan kao Word TOC polje na osnovu naslova (Heading 1-3). "
        "Brojevi strana se izračunavaju tek kada se dokument otvori u Microsoft Word-u i polje "
        "osveži (desni klik → Update Field, ili F9)."
    )
    run.italic = True
    run.font.size = Pt(9.5)


# --------------------------------------------------------------------------
# Poglavlje 1 - Definisanje problema
# --------------------------------------------------------------------------

def build_chapter1(doc):
    h1(doc, "1. Definisanje problema")

    p(doc, (
        "Savremeni gradovi suočavaju se sa stalnim rastom broja motornih vozila, dok kapacitet "
        "parking prostora u centralnim gradskim zonama ostaje praktično nepromenjen. Posledica "
        "ovog neslaganja je pojava poznata u literaturi kao „cruising for parking” — vožnja u "
        "potrazi za slobodnim parking mestom — koja značajno doprinosi saobraćajnim gužvama, "
        "potrošnji goriva i zagađenju vazduha u urbanim sredinama. Istraživanja pokazuju da "
        "vozila koja traže parking mesto mogu činiti između 8% i 74% ukupnog saobraćaja u "
        "zagušenim gradskim jezgrima, a prosečno vreme potrebno da se pronađe slobodno mesto "
        "kretalo se, u analiziranim studijama, od 3,5 do čak 14 minuta [1]."
    ))

    p(doc, (
        "Sa stanovišta gradske uprave, problem nije ograničen samo na neudobnost pojedinačnog "
        "vozača. Saobraćaj koji nastaje traženjem parkinga povećava prosečno vreme putovanja za "
        "sve učesnike u saobraćaju, ne samo za vozila koja traže mesto, i doprinosi lokalnom "
        "zagađenju vazduha u već gusto naseljenim gradskim jezgrima. Zbog toga se rešavanje ovog "
        "problema sve češće posmatra kao deo šire strategije pametnih gradova — zajedno sa "
        "pametnom rasvetom, upravljanjem semaforima i sistemima javnog prevoza — u kojoj se "
        "postojeća infrastruktura koristi efikasnije zahvaljujući analizi podataka, umesto da se "
        "problem rešava isključivo izgradnjom novih parking kapaciteta."
    ))

    p(doc, (
        "Razvoj koncepta pametnih gradova (smart cities) i sve veća dostupnost senzorskih i "
        "istorijskih podataka o zauzetosti parkinga otvaraju mogućnost da se ovaj problem reši "
        "algoritamski — predviđanjem buduće zauzetosti parkinga na osnovu istorijskih obrazaca "
        "ponašanja, i preporukom optimalne lokacije korisniku pre nego što uopšte krene ka centru "
        "grada. Umesto da vozač nasumično kruži ulicama oslanjajući se na trenutno stanje, sistem "
        "može unapred da proceni koji je parking najverovatnije slobodan u trenutku njegovog "
        "dolaska i da ga predloži u odnosu na destinaciju kojoj vozač teži."
    ))

    p(doc, (
        "Jednostavnija, klasična rešenja ovog problema oslanjaju se na prikaz trenutne (a ne "
        "buduće) zauzetosti, ili na prosto sortiranje parkinga po udaljenosti, bez ikakvog uvida "
        "u to da li će parking uopšte imati slobodnih mesta u trenutku dolaska korisnika. Ovakav "
        "pristup ne koristi punu vrednost dostupnih istorijskih podataka i može korisnika uputiti "
        "ka parkingu koji će, do njegovog dolaska, već biti pun."
    ))

    p(doc, (
        "Više radova je pokazalo da modeli mašinskog učenja — regresioni i klasifikacioni — daju "
        "znatno preciznije predikcije zauzetosti parkinga u odnosu na naivne statističke pristupe "
        "(npr. prost istorijski prosek), koristeći pritom isključivo lako dostupne podatke o "
        "vremenu merenja i identitetu parkinga [2], [3]. Sličan zaključak potvrđuju i istraživanja "
        "sprovedena direktno nad podacima o gradu Birmingemu — istom skupu podataka koji se "
        "koristi i u ovom radu — koja pokazuju jasnu, predvidivu vremensku pravilnost u obrascima "
        "punjenja parkinga tokom dana i nedelje [4]."
    ))

    p(doc, (
        "Ove studije se razlikuju po pristupu, ali dele zajednički zaključak. Stolfi, Alba i Yao "
        "[4] testirali su nad istim Birmingham datasetom više klasičnih tehnika predviđanja "
        "(polinomijalno fitovanje, Furijeove redove, k-means klasterovanje vremenskih serija) i "
        "pokazali da se u podacima može prepoznati stabilan, ponovljiv dnevni obrazac po "
        "parkingu. Awan i saradnici [2], poredeći više modela mašinskog i dubokog učenja "
        "(K-najbližih suseda, stabla odlučivanja, slučajne šume, višeslojni perceptron) nad "
        "drugim gradskim datasetom, pokazuju da jednostavniji modeli zasnovani na stablima često "
        "nadmašuju kompleksnije neuronske arhitekture upravo na ovakvim, relativno malim "
        "tabelarnim skupovima podataka — nalaz koji direktno motiviše izbor XGBoost-a u ovom "
        "radu (Poglavlje 3.2, 4). Dahiya i saradnici [3] dodatno pokazuju da se tačnost predikcije "
        "značajno poboljšava kada se pored vremenskih obeležja uključi i identitet same lokacije "
        "parkinga, što je pristup usvojen i u ovom radu kroz enkodovanje identifikatora parkinga "
        "kao zasebnog feature-a (Poglavlje 3.2, 5.3)."
    ))

    p(doc, (
        "Problem koji se rešava u okviru ovog rada može se formulisati na sledeći način:"
    ))

    formula(doc, (
        "Kako, na osnovu istorijskih podataka o zauzetosti parkinga, predvideti buduću "
        "dostupnost parking mesta za zadati trenutak (sat, dan), i kako na osnovu te predikcije, "
        "u kombinaciji sa udaljenošću od željene destinacije, rangirati i preporučiti korisniku "
        "optimalnu lokaciju za parkiranje?"
    ))

    p(doc, (
        "Vredi napomenuti i da problem, iako formulisan nad jednim konkretnim datasetom "
        "(Poglavlje 2), nije specifičan samo za grad Birmingem. Isti obrazac — merljiva, "
        "vremenski predvidiva zauzetost parking prostora, uz nedostatak koordinata i podataka o "
        "saobraćaju u sirovim senzorskim podacima — sreće se i u drugim gradovima i skupovima "
        "podataka korišćenim u srodnim istraživanjima (npr. Santander [2]), što sugeriše da bi se "
        "pristup opisan u ovom radu, uz odgovarajuće ponovno treniranje modela, mogao primeniti i "
        "van konteksta jednog konkretnog grada."
    ))

    p(doc, (
        "Rešavanje ovog problema zahteva dva odvojena, ali povezana zadatka: (1) predikciju — "
        "procenu buduće zauzetosti pojedinačnog parkinga u zadatom trenutku, što predstavlja "
        "klasičan zadatak mašinskog učenja nad tabelarnim podacima, i (2) preporuku — rangiranje "
        "svih dostupnih parkinga na osnovu kombinacije predviđene dostupnosti i drugih relevantnih "
        "faktora (udaljenosti, saobraćaja), što predstavlja zadatak odlučivanja, a ne učenja. Ova "
        "podela je namerna i predstavlja ključni arhitekturni princip celog sistema, detaljnije "
        "obrazložen u poglavljima 2 i 3."
    ))


# --------------------------------------------------------------------------
# Poglavlje 2 - Opis problema
# --------------------------------------------------------------------------

def build_chapter2(doc):
    h1(doc, "2. Opis problema")

    p(doc, (
        "Za potrebe ovog rada korišćen je realan skup senzorskih podataka o zauzetosti parkinga "
        "u gradu Birmingemu (Ujedinjeno Kraljevstvo), poznat kao Parking Birmingham Data Set, "
        "dostupan u UCI Machine Learning Repository-ju [5]. Podaci su prikupljeni od strane "
        "kompanije NCP (National Car Parks) i obuhvataju stvarna merenja zauzetosti nad 29 "
        "parkinga u gradu, a ranije su korišćeni i u akademskim istraživanjima predikcije "
        "zauzetosti parkinga [4]."
    ))

    p(doc, "Osnovne karakteristike skupa podataka (`data/parking.csv`), utvrđene analizom (Poglavlje 5.2):")

    table_grid(
        doc,
        headers=["Veličina", "Vrednost"],
        rows=[
            ["Broj merenja (redova)", "3.352"],
            ["Broj različitih parkinga", "29"],
            ["Period merenja", "13.12.2016 – 19.12.2016 (7 dana)"],
            ["Učestalost merenja", "~30 minuta, u intervalu ~08:00–16:30"],
            ["Prosečna popunjenost (OccupancyRate)", "53,14 % (std 26,02 %, opseg 0,69–100 %)"],
            ["Kapacitet parkinga (Capacity)", "220 – 4.675 mesta (prosek ~1.361)"],
        ],
        caption="Osnovne karakteristike Parking Birmingham dataset-a.",
    )

    p(doc, "Kolone u datasetu, tačno onakve kakve dolaze iz izvornog fajla:")

    table_grid(
        doc,
        headers=["Kolona", "Opis"],
        rows=[
            ["SystemCodeNumber", "Identifikator parkinga (npr. BHMBCCMKT01, Broad Street) — 29 lokacija"],
            ["Capacity", "Ukupan kapacitet parkinga (broj mesta)"],
            ["Occupancy", "Broj trenutno zauzetih mesta"],
            ["LastUpdated", "Vremenska oznaka merenja (npr. 2016-12-13 08:02:51)"],
            ["OccupancyRate", "Stepen popunjenosti u procentima (0–100) — ciljna promenljiva"],
            ["Date, Time, DayOfWeek", "Već izdvojeni delovi vremenske oznake"],
        ],
        caption="Kolone dataset-a data/parking.csv.",
    )

    p(doc, "Nekoliko stvarnih redova iz `data/parking.csv`, radi konkretizacije:")

    table_grid(
        doc,
        headers=["SystemCodeNumber", "Capacity", "Occupancy", "LastUpdated", "OccupancyRate"],
        rows=[
            ["BHMBCCMKT01", "577", "14", "2016-12-13 08:02:51", "2,43"],
            ["BHMBCCMKT01", "577", "20", "2016-12-13 08:29:53", "3,47"],
            ["BHMBCCMKT01", "577", "33", "2016-12-13 09:02:55", "5,72"],
            ["BHMBCCMKT01", "577", "59", "2016-12-13 09:29:54", "10,23"],
            ["BHMBCCMKT01", "577", "91", "2016-12-13 09:55:56", "15,77"],
        ],
        caption="Prvih pet redova dataset-a za parking BHMBCCMKT01 — vidljiv je rast popunjenosti tokom jutra.",
    )

    p(doc, (
        "Tokom pripreme podataka uočena je i jedna sitna, ali vredna napomene, osobina samog "
        "izvornog fajla: kolone `Date` i `Time`, iako su prema opisu dataseta trebale da sadrže "
        "samo izdvojen datum, odnosno samo vreme, u stvarnosti sadrže potpunu vremensku oznaku, "
        "identičnu koloni `LastUpdated`. Zbog toga se u ovom radu, i u pripremi podataka (Poglavlje "
        "5.2) i u treniranju modela (Poglavlje 5.3), sve vremenske komponente (sat, minut, dan u "
        "nedelji) računaju isključivo iz `LastUpdated`, dok se kolone `Date` i `Time` ne koriste — "
        "čime se izbegava oslanjanje na redundantne, potencijalno zbunjujuće kolone."
    ))

    p(doc, (
        "Kapacitet parkinga u datasetu varira gotovo dvadesetostruko — od najmanjeg do najvećeg "
        "parkinga u skupu podataka:"
    ))

    table_grid(
        doc,
        headers=["Kategorija", "Parking", "Kapacitet"],
        rows=[
            ["Najveći", "Others-CCCPS133", "4.675 mesta"],
            ["Najveći (2.)", "Others-CCCPS135a", "3.883 mesta"],
            ["Najmanji", "BHMEURBRD02", "220 mesta"],
            ["Najmanji (2.)", "BHMBCCPST01", "317 mesta"],
        ],
        caption="Raspon kapaciteta u datasetu — od najmanjeg do najvećeg parkinga.",
    )

    p(doc, (
        "Ova razlika u veličini je jedan od razloga zašto je kapacitet uključen kao zaseban "
        "feature u modelu za predikciju (Poglavlje 3.2, 5.3), a ne samo koordinate ili "
        "identifikator parkinga — veći parkinzi se, očekivano, sporije pune i prazne u relativnom "
        "smislu (procenat popunjenosti), pa kapacitet modelu daje dodatni, koristan kontekst uz "
        "identitet parkinga."
    ))

    p(doc, (
        "Dataset ima i dva bitna ograničenja koja direktno oblikuju rešenje. Prvo, ne sadrži "
        "geografske koordinate parkinga — samo identifikator lokacije (SystemCodeNumber) — pa je "
        "za potrebe mape i računanja udaljenosti bilo potrebno dodati približne koordinate ručno "
        "(vidi `backend/parks.py`, Poglavlje 5.4), jasno dokumentovane kao fiktivne. Drugo, dataset "
        "ne sadrži nikakav podatak o trenutnom stanju saobraćaja, pa se taj faktor u modulu za "
        "preporuku (Poglavlje 3.3 i 5.5) tretira kao pojednostavljena, simulirana vrednost, uz "
        "eksplicitnu napomenu da bi se u budućem radu (npr. master radu) zamenio realnim podacima "
        "o saobraćaju."
    ))

    p(doc, (
        "Treće ograničenje, manje očigledno ali važno za interpretaciju rezultata, jeste da su "
        "merenja dostupna samo u prozoru od otprilike 08:00 do 16:30 — dataset ne sadrži noćna "
        "merenja. Model treniran nad ovim podacima je, samim tim, pouzdan isključivo u tom "
        "vremenskom opsegu; predikcije van njega predstavljaju ekstrapolaciju i treba ih tumačiti "
        "sa oprezom."
    ))

    p(doc, "Rad se oslanja na uvide iz srodnih istraživanja, ali se od njih razlikuje po obimu i po tome što eksplicitno dodaje modul za preporuku lokacije, a ne samo predikciju zauzetosti:")

    table_grid(
        doc,
        headers=["Rad", "Dataset / fokus", "Model", "Izlaz sistema"],
        rows=[
            ["Stolfi, Alba, Yao [4]", "Birmingham (isti dataset)", "Polinomi, Furijeovi redovi, k-means", "Samo predikcija zauzetosti"],
            ["Awan i dr. [2]", "Santander (Španija)", "KNN, stabla, RF, MLP (poređenje)", "Samo predikcija zauzetosti"],
            ["Tekouabou i dr. [6]", "Birmingham (isti dataset)", "Ansambl modeli (ensemble)", "Samo predikcija zauzetosti"],
            ["Ovaj rad", "Birmingham (isti dataset)", "XGBoost regresija", "Predikcija + rangirana preporuka lokacije"],
        ],
        caption="Poređenje ovog rada sa srodnim istraživanjima nad istim ili sličnim datasetom.",
    )

    p(doc, (
        "Kao što tabela pokazuje, veći deo pregledane literature zaustavlja se na predikciji "
        "zauzetosti kao krajnjem cilju. Ovaj rad ide korak dalje — predikcija je samo ulaz u "
        "drugi, jednako važan modul (preporuku), koji krajnjem korisniku direktno odgovara na "
        "pitanje „gde da parkiram”, a ne samo „koliko će ovaj konkretan parking biti pun”."
    ))

    p(doc, (
        "Ključna arhitekturna odluka u rešavanju problema jeste striktno razdvajanje predikcije "
        "od preporuke, na dva nezavisna softverska modula:"
    ))

    bullets(doc, [
        "Predikcija (backend/predictor.py, ml/train.py) — koliko će konkretan parking biti "
        "zauzet u zadatom trenutku. Ovo je zadatak mašinskog učenja: model uči nelinearne "
        "obrasce iz istorijskih podataka i generalizuje ih na nove kombinacije (sat, dan, "
        "parking).",
        "Preporuka (backend/recommender.py) — koji parking predložiti korisniku, kombinovanjem "
        "predikcije sa udaljenošću i (simuliranim) saobraćajem. Ovo NIJE zadatak učenja, već "
        "zadatak odlučivanja — obično ponderisano rangiranje sa tri lako razumljiva i lako "
        "izmenljiva faktora.",
    ])

    p(doc, (
        "Ovo razdvajanje nije samo organizaciono, već i namerno arhitektonsko opredeljenje: "
        "preporuka koja kombinuje samo dva do tri interpretabilna faktora ne zahteva „crnu kutiju” "
        "poput neuronske mreže — dovoljna je transparentna, objašnjiva formula čiji ponderi mogu "
        "biti prikazani korisniku (Poglavlje 5.5, 5.7). Kompleksnost učenja obrasca zauzetosti "
        "ostaje izolovana u predikcionom modelu, dok modul za preporuku ostaje jednostavan, brz i "
        "lako proverljiv."
    ))


# --------------------------------------------------------------------------
# Poglavlje 3 - Nacin resavanja problema
# --------------------------------------------------------------------------

def build_chapter3(doc):
    h1(doc, "3. Način rešavanja problema")

    p(doc, (
        "Problem je rešen razvojem sistema koji povezuje tri međusobno nezavisne, ali "
        "komplementarne celine: pripremu i analizu podataka, model za predikciju zauzetosti "
        "zasnovan na mašinskom učenju, i modul za preporuku zasnovan na ponderisanom rangiranju. "
        "Ceo lanac (podaci → predikcija → preporuka → prikaz) implementiran je i testiran "
        "end-to-end, u pet faza koje odgovaraju potpoglavljima 3.1–3.3 i poglavlju 5."
    ))

    h2(doc, "3.1. Priprema i obrada podataka")

    p(doc, (
        "U prvoj fazi učitan je dataset `data/parking.csv`, vremenska oznaka `LastUpdated` "
        "parsirana je u tip datetime, i iz nje su izvučeni dodatni vremenski feature-i: sat "
        "(Hour), minut (Minute), redni broj dana u nedelji (DayOfWeekNum, 0 = ponedeljak) i "
        "binarna oznaka radni dan/vikend (IsWeekend). Nad ovako obogaćenim podacima izračunata je "
        "osnovna deskriptivna statistika, a zatim je nacrtana dnevna kriva punjenja — prosečna "
        "popunjenost po satu — za nekoliko reprezentativnih parkinga."
    ))

    p(doc, (
        "Ova analiza (detaljno opisana u Poglavlju 5.2) potvrdila je jasnu, ponovljivu dnevnu "
        "pravilnost u zauzetosti: popunjenost je niska u ranim jutarnjim satima i raste ka "
        "sredini dana. Ova pravilnost je ključna — ona opravdava izbor pristupa u kojem se "
        "popunjenost predviđa isključivo na osnovu vremenskih obeležja i identiteta parkinga, bez "
        "potrebe za spoljašnjim, teže dostupnim podacima (npr. vremenskim prognozama ili "
        "podacima o događajima u gradu)."
    ))

    h2(doc, "3.2. Predviđanje dostupnosti")

    p(doc, (
        "Za predikciju budućeg stepena popunjenosti (OccupancyRate) korišćena je XGBoost regresija "
        "— model zasnovan na gradijentnom pojačavanju (gradient boosting) stabala odlučivanja "
        "[6]. Kao ulazni feature-i korišćeni su: sat, minut, redni broj dana u nedelji, "
        "identifikator parkinga (enkodovan pomoću LabelEncoder-a u celobrojnu vrednost) i "
        "kapacitet parkinga."
    ))

    p(doc, (
        "Podela na trening i test skup urađena je hronološki, a ne nasumično: poslednjih 20% "
        "vremenske ose izdvojeno je za test, dok je model treniran isključivo na ranijem periodu. "
        "Ovakva podela sprečava „curenje” informacija iz budućnosti u trening skup — model se u "
        "praksi nikada neće trenirati na podacima koji hronološki dolaze posle trenutka za koji "
        "predviđa, pa evaluacija na hronološkom test skupu realističnije odražava stvarne uslove "
        "korišćenja modela u produkciji."
    ))

    p(doc, (
        "Uspešnost modela evaluirana je metrikama RMSE (koren srednjekvadratne greške) i MAE "
        "(srednja apsolutna greška), poređenjem sa jednostavnim baseline modelom koji uvek "
        "predviđa prosečnu popunjenost iz trening skupa. Rezultati (detaljno u Poglavlju 5.3) "
        "pokazuju da XGBoost model gotovo prepolovljuje grešku u odnosu na baseline, što potvrđuje "
        "da model stvarno uči vremenski obrazac, a ne samo reprodukuje prosek."
    ))

    p(doc, "Iz predviđenog stepena popunjenosti direktno se izvodi predviđena dostupnost:")

    formula(doc, "dostupnost = 1 − (predviđeni OccupancyRate / 100)")

    p(doc, (
        "Pri definisanju zadatka razmatrana je i alternativa da se problem postavi kao "
        "klasifikacija (npr. „slobodno” / „skoro puno” / „puno”, u tri ili više kategorija) "
        "umesto regresije nad kontinualnom vrednošću OccupancyRate. Regresija je zadržana kao "
        "konačan izbor iz dva razloga: prvo, ne gubi informaciju — kontinualna predikcija "
        "popunjenosti se u svakom trenutku može naknadno pretvoriti u proizvoljan broj "
        "kategorija (npr. pragovima), dok obrnuto nije moguće; drugo, modul za preporuku "
        "(Poglavlje 3.3) direktno koristi kontinualnu vrednost dostupnosti kao brojčanu "
        "komponentu ponderisanog skora, pa bi kategorička predikcija zahtevala dodatnu, veštačku "
        "konverziju nazad u broj."
    ))

    h2(doc, "3.3. Preporuka lokacije")

    p(doc, (
        "Preporuka lokacije realizovana je kao ponderisano rangiranje svih parkinga, bez upotrebe "
        "neuronske mreže ili bilo kog drugog modela učenja — u skladu sa principom iz Poglavlja 2. "
        "Osnovna formula skora je:"
    ))

    formula(doc, "skor = w1 · dostupnost + w2 · blizina − w3 · saobraćaj")

    p(doc, "gde su komponente definisane na sledeći način:")

    bullets(doc, [
        "dostupnost — predviđena raspoloživost parkinga, direktno iz ML modela (1 − OccupancyRate/100).",
        "blizina — normalizovana blizina parkinga u odnosu na polaznu tačku korisnika (rastojanje "
        "izračunato haversine formulom, normalizovano u odnosu na najudaljenijeg kandidata), "
        "tako da parkinzi bliži polaznoj tački dobijaju veći doprinos skoru.",
        "saobraćaj — pojednostavljena, simulirana procena zagušenja u okolini destinacije, "
        "zasnovana na dobu dana (jutarnji/popodnevni špic) i blizini destinaciji. Dataset ne "
        "sadrži stvarne podatke o saobraćaju — ovo je eksplicitno obeleženo kao mesto za "
        "proširenje u budućem (master) radu, gde bi ova komponenta bila zamenjena stvarnim "
        "podacima ili spoljašnjim API-jem za saobraćaj.",
    ])

    p(doc, (
        "Ponderi w1, w2 i w3 definisani su kao konstante na vrhu `backend/recommender.py` "
        "(trenutno 0,55 / 0,30 / 0,15), lako izmenljive radi eksperimentisanja bez ikakvog "
        "ponovnog treniranja modela — što je još jedna praktična posledica odvajanja predikcije "
        "od preporuke. Dodatno, API podržava i opcioni parametar radijusa pretrage (u metrima) "
        "oko destinacije — ako je zadat, parkinzi van tog radijusa se potpuno isključuju iz "
        "razmatranja pre samog rangiranja, što korisniku omogućava da ograniči preporuke npr. na "
        "parkinge do 500 m od cilja pešačenja. Sistem vraća top N (podrazumevano 5) parkinga sortiranih po skoru, uz "
        "razložene komponente skora, tako da je svaka preporuka objašnjiva, a ne „crna kutija” "
        "(detaljno u Poglavlju 5.5)."
    ))


# --------------------------------------------------------------------------
# Poglavlje 4 - Koriscene tehnologije i alati
# --------------------------------------------------------------------------

def build_chapter4(doc):
    h1(doc, "4. Korišćene tehnologije i alati")

    p(doc, (
        "Struktura projekta prati podelu na tri sloja opisanu u nastavku poglavlja — svaki sloj "
        "živi u svom direktorijumu, sa jasno odvojenom odgovornošću:"
    ))

    code_block(doc, '''
smart-parking/
|-- data/
|   `-- parking.csv          # dataset (Parking Birmingham, UCI)
|-- ml/
|   |-- explore.py           # Faza 1 - EDA
|   |-- train.py             # Faza 2 - trening XGBoost modela
|   `-- model.joblib         # sacuvan istreniran model
|-- backend/
|   |-- main.py              # FastAPI app, endpointi (Faza 3)
|   |-- predictor.py         # ucitava model.joblib, daje predikciju
|   |-- recommender.py       # ponderisano rangiranje parkinga (Faza 4)
|   `-- parks.py             # koordinate i kapacitet parkinga
`-- frontend/                # Next.js app (Faza 5)
    `-- app/
        |-- page.tsx         # glavna stranica, poziva API
        `-- ParkingMap.tsx   # Leaflet mapa
'''.strip("\n"))

    p(doc, "Ceo sistem se pokreće u dva paralelna procesa — backend i frontend rade nezavisno i komuniciraju isključivo preko REST API-ja:")

    code_block(doc, '''
# Terminal 1 - backend (iz smart-parking/)
uvicorn backend.main:app --reload

# Terminal 2 - frontend (iz smart-parking/frontend/)
npm run dev
'''.strip("\n"))

    p(doc, (
        "Nakon pokretanja oba procesa, aplikacija je dostupna na `http://localhost:3000`, dok je "
        "interaktivna API dokumentacija dostupna na `http://127.0.0.1:8000/docs`. Ovakva podela "
        "na dva nezavisna procesa odražava i podelu odgovornosti opisanu ranije: frontend se može "
        "razvijati i menjati bez ikakvog uticaja na model ili backend logiku, sve dok se poštuje "
        "ugovoreni format REST odgovora (Poglavlje 5.4)."
    ))

    p(doc, (
        "Sistem je implementiran kroz tri sloja — pripremu podataka i mašinsko učenje, backend "
        "REST servis, i frontend aplikaciju — od kojih svaki koristi tehnologije prilagođene "
        "prirodi zadatka."
    ))

    table_grid(
        doc,
        headers=["Sloj", "Tehnologija", "Uloga u sistemu"],
        rows=[
            ["Podaci i ML", "Python 3.12", "Osnovni jezik za obradu podataka i treniranje modela"],
            ["Podaci i ML", "pandas", "Učitavanje, filtriranje i agregacija tabelarnih podataka"],
            ["Podaci i ML", "scikit-learn", "LabelEncoder za identifikator parkinga, metrike (RMSE, MAE)"],
            ["Podaci i ML", "XGBoost", "Regresioni model za predikciju OccupancyRate"],
            ["Podaci i ML", "joblib", "Serijalizacija istreniranog modela i enkodera na disk"],
            ["Podaci i ML", "matplotlib", "Vizuelizacija dnevne krive punjenja i rezultata"],
            ["Backend", "FastAPI", "REST API — endpointi /parks, /predict, /recommend"],
            ["Backend", "uvicorn", "ASGI server za pokretanje FastAPI aplikacije"],
            ["Frontend", "Next.js (App Router)", "React aplikacija, klijentska komponenta karte"],
            ["Frontend", "Leaflet / react-leaflet", "Interaktivna mapa sa markerima parkinga"],
        ],
        caption="Tehnološki stack po slojevima sistema.",
    )

    h2(doc, "Zašto XGBoost")

    p(doc, (
        "Podaci o zauzetosti parkinga su strukturirani, tabelarni podaci sa mešavinom "
        "kategoričkih (identifikator parkinga) i numeričkih (sat, minut, kapacitet) obeležja. Za "
        "ovakve podatke, modeli zasnovani na stablima odlučivanja i gradijentnom pojačavanju — "
        "poput XGBoost-a — dosledno nadmašuju duboke neuronske mreže po tačnosti, brzini treniranja "
        "i jednostavnosti podešavanja [6]. Konvolutivne neuronske mreže (CNN), koje su prirodno "
        "rešenje za slikovne podatke sa prostornom strukturom, nisu odgovarajući alat za ovaj tip "
        "tabelarnih podataka i namerno nisu korišćene — u skladu sa projektnim smernicama, gde je "
        "za poređenje sekvencijalnih modela (LSTM/GRU) predviđen prostor za budući, master rad."
    ))

    table_grid(
        doc,
        headers=["Porodica modela", "Prikladnost za tabelarne podatke", "Modeluje vremenski sled?", "Korišćeno u radu"],
        rows=[
            ["Linearni modeli", "Ograničena — ne hvata nelinearne interakcije", "Ne", "Da (kao dodatni baseline, Poglavlje 5.3)"],
            ["Stabla / ansambli (RF, XGBoost)", "Vrlo dobra", "Ne direktno (svaki red nezavisan)", "Da — XGBoost je glavni model"],
            ["CNN", "Loša — namenjena prostornim (slikovnim) podacima", "Ne", "Ne — namerno isključeno"],
            ["LSTM / GRU", "Dobra, uz dodatnu složenost", "Da — eksplicitno", "Ne — planirano za master rad"],
        ],
        caption="Uporedni pregled porodica modela razmatranih za zadatak predikcije popunjenosti.",
    )

    h2(doc, "Zašto FastAPI")

    p(doc, (
        "FastAPI omogućava deklarativno definisanje endpointa uz automatsku validaciju tipova "
        "upitnih parametara i automatski generisanu interaktivnu dokumentaciju (Swagger UI na "
        "`/docs`), što značajno ubrzava razvoj i testiranje API-ja tokom izrade proof-of-concept "
        "sistema [10]. Kombinacija sa uvicorn ASGI serverom obezbeđuje nisku latenciju odgovora, "
        "što je bitno jer frontend poziva `/recommend` endpoint pri svakom kliku korisnika na "
        "mapu."
    ))

    h2(doc, "Zašto Next.js i Leaflet")

    p(doc, (
        "Next.js (App Router) korišćen je kao moderan React framework koji olakšava organizaciju "
        "klijentske aplikacije i integraciju sa spoljnim bibliotekama [11]. Leaflet, kroz "
        "react-leaflet omotač, predstavlja lagan i široko korišćen alat za interaktivne mape "
        "zasnovane na OpenStreetMap podlozi, sa jednostavnim API-jem za markere, popup prozore i "
        "rukovanje klik-događajima na mapi [12] — što je tačno funkcionalnost potrebna za prikaz "
        "parkinga i biranje destinacije klikom."
    ))

    p(doc, (
        "Tokom razvoja frontenda, funkcionalnost je proširena i van originalno planiranog obima "
        "(Poglavlje 5.6): dodata je integracija sa javnim OSRM (Open Source Routing Machine) "
        "servisom za računanje stvarne vozne rute između polazne tačke i destinacije, kao i sa "
        "Nominatim (OpenStreetMap) servisom za reverzno geokodiranje — pretvaranje koordinata u "
        "čitljivu adresu koja se prikazuje korisniku."
    ))

    h2(doc, "Razmatrane alternative")

    p(doc, (
        "Pri izboru tehnologija razmatrane su i uobičajene alternative za svaki sloj sistema. Za "
        "backend, Flask je razmatran kao lakša, minimalnija alternativa FastAPI-ju; FastAPI je "
        "ipak izabran zbog ugrađene validacije tipova nad upitnim parametrima (npr. `hour: int`) "
        "i automatski generisane Swagger dokumentacije, što je posebno korisno u fazi razvoja i "
        "ručnog testiranja endpointa opisanih u Poglavlju 5.4, bez pisanja dodatnog koda za "
        "validaciju ili dokumentaciju. Za frontend, React aplikacija bez frameworka ili Vue/"
        "Angular predstavljali su alternativu; Next.js je izabran zbog spremne projektne "
        "strukture (App Router), ugrađenog razvojnog servera sa automatskim osvežavanjem i "
        "lakoće integracije sa react-leaflet paketom, bez potrebe za ručnim podešavanjem build "
        "alata. Za bazu podataka razmatrano je čuvanje istorijskih upita korisnika radi analize, "
        "ali je ta ideja odbačena u skladu sa opsegom proof-of-concept rada (Poglavlje 2, "
        "CLAUDE.md smernice projekta) — sistem je bez stanja (stateless): svaki zahtev nosi sve "
        "podatke potrebne za predikciju i preporuku, a jedini izvor istine je `parking.csv` i "
        "istrenirani model."
    ))


def main():
    doc = Document()
    setup_styles(doc)

    build_title_page(doc)
    build_toc(doc)
    build_chapter1(doc)
    build_chapter2(doc)
    build_chapter3(doc)
    build_chapter4(doc)

    from chapter5 import build_chapter5
    from chapter67 import build_chapter6, build_chapter7

    build_chapter5(doc, {
        "h1": h1, "h2": h2, "h3": h3, "p": p, "bullets": bullets,
        "formula": formula, "code_block": code_block, "figure": figure,
        "table_grid": table_grid, "BODY_FONT": BODY_FONT,
    })
    build_chapter6(doc, {"h1": h1, "p": p, "bullets": bullets})
    build_chapter7(doc, {"h1": h1, "p": p})

    doc.save(OUTPUT_PATH)
    print(f"Sacuvano: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
