"""Production des documents exportés : classeurs Excel et PDF (relevés, listes, procès-verbaux).

Sécurité :
- injection de formules (CSV/Excel) neutralisée : toute cellule texte commençant par
  = + - @ ou une tabulation est préfixée d'une apostrophe et stockée comme texte ;
- aucun contenu actif dans les PDF (pas de JavaScript ni de formulaire) ;
- les métadonnées ne contiennent que le titre et l'émetteur.
"""
import io
import statistics
from datetime import datetime, timezone
from decimal import Decimal

DEBUTS_DANGEREUX = ("=", "+", "-", "@", "\t", "\r")
BRUN, SABLE, TEXTE, MUET = "#5B4130", "#F1E7DC", "#2A221C", "#7A6C5F"
TRANCHES = ((0, 5), (5, 8), (8, 10), (10, 12), (12, 14), (14, 16), (16, 20.01))


def cellule_sure(valeur):
    if isinstance(valeur, str) and valeur.startswith(DEBUTS_DANGEREUX):
        return "'" + valeur
    return valeur


def statistiques(valeurs: list[Decimal]) -> dict:
    """Indicateurs d'une série de notes sur 20 (F22)."""
    if not valeurs:
        return {"nombre": 0, "moyenne": None, "mediane": None, "minimum": None, "maximum": None,
                "ecart_type": None, "taux_reussite": None, "repartition": [0] * len(TRANCHES)}
    flottants = [float(v) for v in valeurs]
    return {
        "nombre": len(flottants),
        "moyenne": round(statistics.fmean(flottants), 2),
        "mediane": round(statistics.median(flottants), 2),
        "minimum": min(flottants), "maximum": max(flottants),
        "ecart_type": round(statistics.pstdev(flottants), 2),
        "taux_reussite": round(100 * sum(v >= 10 for v in flottants) / len(flottants), 1),
        "repartition": [sum(bas <= v < haut for v in flottants) for bas, haut in TRANCHES],
    }


LIBELLES_TRANCHES = ["0–5", "5–8", "8–10", "10–12", "12–14", "14–16", "16–20"]


# --- Excel ---

def classeur(titre: str, entetes: list[str], lignes: list[list], feuille: str = "Notes") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = feuille[:31]
    ws.append([cellule_sure(titre)])
    ws["A1"].font = Font(bold=True, size=13, color="2A221C")
    ws.append([f"Exporté le {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC – document confidentiel"])
    ws["A2"].font = Font(italic=True, size=9, color="7A6C5F")
    ws.append([])
    ws.append(entetes)
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="5B4130")
        c.alignment = Alignment(horizontal="center")
    for ligne in lignes:
        ws.append([cellule_sure(v) for v in ligne])
        for c in ws[ws.max_row]:
            if isinstance(c.value, str):
                c.data_type = "s"  # jamais interprété comme une formule
    for i, entete in enumerate(entetes, start=1):
        largeur = max([len(str(entete))] + [len(str(l[i - 1])) for l in lignes if i - 1 < len(l)]) + 2
        ws.column_dimensions[ws.cell(row=4, column=i).column_letter].width = min(largeur, 45)
    ws.freeze_panes = "A5"
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


# --- PDF ---

def _styles():
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16,
                                textColor=HexColor(TEXTE), alignment=0, spaceAfter=2),
        "sous": ParagraphStyle("sous", parent=base["Normal"], fontSize=9.5, textColor=HexColor(MUET), spaceAfter=10),
        "normal": ParagraphStyle("normal", parent=base["Normal"], fontSize=9.5, textColor=HexColor(TEXTE), leading=13),
        "petit": ParagraphStyle("petit", parent=base["Normal"], fontSize=8, textColor=HexColor(MUET), leading=10),
    }


def _tableau(entetes, lignes, largeurs=None, alignes_droite=()):
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import Table, TableStyle

    t = Table([entetes] + lignes, colWidths=largeurs, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(BRUN)), ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#FAF7F3")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, HexColor("#E4DACD")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for col in alignes_droite:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _gabarit(titre: str):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4

    def entete_pied(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor(BRUN))
        canvas.rect(0, A4[1] - 14, A4[0], 14, stroke=0, fill=1)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(HexColor(TEXTE))
        canvas.drawString(40, A4[1] - 34, "SCOLARIS")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(HexColor(MUET))
        canvas.drawRightString(A4[0] - 40, A4[1] - 34, "Université – Service de la scolarité")
        canvas.drawString(40, 24, f"{titre} – édité le {datetime.now(timezone.utc):%d/%m/%Y à %H:%M} UTC")
        canvas.drawRightString(A4[0] - 40, 24, f"Page {doc.page}")
        canvas.restoreState()

    return entete_pied


def pdf(titre: str, sous_titre: str, blocs: list, paysage: bool = False) -> bytes:
    """Assemble un PDF ; « blocs » est une liste d'éléments platypus ou de tuples ("tableau", ...)."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    st = _styles()
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=landscape(A4) if paysage else A4, title=titre, author="Scolaris",
                            leftMargin=40, rightMargin=40, topMargin=56, bottomMargin=44)
    elements = [Paragraph(titre, st["titre"]), Paragraph(sous_titre, st["sous"])]
    for b in blocs:
        if isinstance(b, tuple) and b[0] == "tableau":
            elements.append(_tableau(*b[1:]))
        elif isinstance(b, tuple) and b[0] == "texte":
            elements.append(Paragraph(b[1], st[b[2] if len(b) > 2 else "normal"]))
        elif isinstance(b, tuple) and b[0] == "espace":
            elements.append(Spacer(1, b[1]))
        else:
            elements.append(b)
    gabarit = _gabarit(titre)
    doc.build(elements, onFirstPage=gabarit, onLaterPages=gabarit)
    return tampon.getvalue()


def code_qr(contenu: str, taille: float = 92):
    """QR code vectoriel (bibliothèque reportlab, sans dépendance supplémentaire)."""
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    w = QrCodeWidget(contenu)
    x1, y1, x2, y2 = w.getBounds()
    d = Drawing(taille, taille, transform=[taille / (x2 - x1), 0, 0, taille / (y2 - y1), 0, 0])
    d.add(w)
    return d


def bloc_verification(url: str, code: str, empreinte: str):
    """Encadré du relevé : QR code vers la page publique de vérification, code et empreinte."""
    from reportlab.platypus import Paragraph, Table

    texte = Paragraph(
        "<b>Vérification de l'authenticité</b><br/>Scannez ce code ou saisissez-le sur la page de vérification :"
        f"<br/><font face='Courier'>{code}</font><br/>Empreinte : <font face='Courier' size='7'>{empreinte}</font>",
        _styles()["petit"])
    return Table([[code_qr(url), texte]], colWidths=[100, 380])


def echapper(texte) -> str:
    """Les paragraphes reportlab interprètent un balisage simple : les données sont échappées."""
    from xml.sax.saxutils import escape

    return escape(str(texte))
