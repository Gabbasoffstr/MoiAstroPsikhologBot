
from fpdf import FPDF
import os

pdf = FPDF()
pdf.add_page()

# Добавляем кириллический шрифт
font_path = "DejaVuSans.ttf"
pdf.add_font("DejaVu", "", font_path, uni=True)
pdf.set_font("DejaVu", size=12)

summary = [
    "Солнце в Весах — стремление к гармонии.",
    "Луна в Раке — эмоциональность и забота.",
    "Меркурий в Весах — дипломатичное мышление.",
    "Венера в Деве — перфекционизм в любви.",
    "Марс в Деве — организованность в действиях.",
]

for s in summary:
    pdf.multi_cell(0, 10, s)

pdf.output("test_chart.pdf")
