"""The A4 poster of the school link: the name, a short call, the QR code and the address in text.

Drawn with reportlab (the same library as the reports; the standard fonts embed nothing). The QR
code is drawn as vectors, so it prints sharp at any size. The same link gives the same bytes."""

from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.reports.format import printable

INK = colors.HexColor("#101a3f")
MUTED = colors.HexColor("#4a5578")
QR_SIZE = 120 * mm
MAX_NAME_WIDTH = A4[0] - 30 * mm


def _fit(text: str, font: str, size: float, pdf: canvas.Canvas) -> float:
    """The largest font size (not above `size`) at which the text fits the width of the page."""
    while size > 14 and pdf.stringWidth(text, font, size) > MAX_NAME_WIDTH:
        size -= 1
    return size


def render_poster(*, school_name: str, url: str) -> bytes:
    width, height = A4
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=True)
    pdf.setTitle(printable(f"Cartaz da {school_name}"))
    pdf.setAuthor("APM Digital")

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 18)
    pdf.drawCentredString(width / 2, height - 35 * mm, "Contribua com a APM da")

    name = printable(school_name)
    size = _fit(name, "Helvetica-Bold", 40, pdf)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawCentredString(width / 2, height - 55 * mm, name)

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(width / 2, height - 72 * mm, "Aponte a câmera do celular para o QR Code")

    widget = QrCodeWidget(url, barLevel="M", barFillColor=INK)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(
        QR_SIZE, QR_SIZE, transform=[QR_SIZE / (x1 - x0), 0, 0, QR_SIZE / (y1 - y0), 0, 0]
    )
    drawing.add(widget)
    renderPDF.draw(drawing, pdf, (width - QR_SIZE) / 2, height - 80 * mm - QR_SIZE)

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width / 2, 60 * mm, "Ou digite o endereço:")
    address = printable(url.removeprefix("https://").removeprefix("http://"))
    size = _fit(address, "Helvetica", 22, pdf)
    pdf.setFont("Helvetica", size)
    pdf.drawCentredString(width / 2, 50 * mm, address)

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(
        width / 2, 22 * mm, "Pagamento por Pix. O valor é conferido na página, antes de você pagar."
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
