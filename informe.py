"""Genera el informe en PDF de ENERSMART con fpdf2 (solo fuentes estándar, sin dependencias pesadas)."""
import re
from fpdf import FPDF
from fpdf.fonts import FontFace

import calculos as C

VERDE = (0, 82, 204) 
VERDE_CLARO = (232, 244, 237)
GRIS = (90, 90, 90)

_REEMPLAZOS = {"≥": ">=", "≤": "<=", "–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
               "…": "...", "•": "-", "→": "->", "✓": "Si", "✗": "No"}

AVISO = ("Este informe es una estimación orientativa hecha con la información que ingresó el usuario. "
         "No incluye mediciones eléctricas ni fotométricas en sitio, no reemplaza una auditoría energética "
         "profesional, no certifica cumplimiento normativo y no garantiza un ahorro. Las recomendaciones "
         "generadas con inteligencia artificial deben ser revisadas por el usuario antes de aplicarse.")


def _t(texto):
    """Deja el texto compatible con las fuentes estándar del PDF (latin-1) y quita emojis."""
    s = str(texto)
    for a, b in _REEMPLAZOS.items():
        s = s.replace(a, b)
    return re.sub(r"[^\x00-\xff]", "", s).strip()


class _Informe(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _t(f"ENERSMART - Diagnóstico energético digital - Página {self.page_no()}/{{nb}}"), align="C")


def _titulo(pdf, texto):
    if pdf.get_y() > 245:
        pdf.add_page()
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*VERDE)
    pdf.cell(0, 8, _t(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*VERDE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)


def _parrafo(pdf, texto, negrita=False, tam=10, color=(0, 0, 0)):
    pdf.set_font("Helvetica", "B" if negrita else "", tam)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, 5.5, _t(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def _tabla(pdf, encabezados, filas, anchos, alineacion):
    estilo = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=VERDE)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(255, 255, 255)
    with pdf.table(col_widths=anchos, text_align=alineacion, line_height=6,
                   headings_style=estilo, borders_layout="HORIZONTAL_LINES",
                   cell_fill_color=(238, 243, 252), cell_fill_mode="ROWS") as tabla:
        fila = tabla.row()
        for e in encabezados:
            fila.cell(_t(e))
        for f in filas:
            fila = tabla.row()
            for c in f:
                fila.cell(_t(c))
    pdf.ln(2)


def _barras(pdf, datos, unidad):
    """datos: lista de (etiqueta, valor). Barras horizontales dibujadas a mano."""
    maximo = max((v for _, v in datos), default=0)
    if maximo <= 0:
        return
    ancho_max = 95
    pdf.set_font("Helvetica", "", 9)
    for etiqueta, valor in datos:
        if pdf.get_y() > 270:
            pdf.add_page()
        y = pdf.get_y()
        pdf.set_xy(pdf.l_margin, y)
        pdf.cell(38, 6, _t(etiqueta))
        pdf.set_fill_color(*VERDE)
        pdf.rect(pdf.l_margin + 40, y + 1, max(ancho_max * valor / maximo, 0.5), 4, style="F")
        pdf.set_xy(pdf.l_margin + 40 + ancho_max + 3, y)
        pdf.cell(40, 6, _t(f"{C.fmt_num(valor)} {unidad}"))
        pdf.set_xy(pdf.l_margin, y + 7)
    pdf.ln(2)


def generar_pdf(negocio, fecha, diag=None, lum=None, aud=None, ia_texto=None):
    pdf = _Informe(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Portada compacta
    pdf.set_fill_color(64,64,64)
    pdf.rect(0, 0, 210, 34, style="F")
    pdf.set_xy(15, 9)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.image("logo_enersmart.png", x=160, y=6, h=22)
    pdf.cell(0, 9, "ENERSMART", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _t("Informe de diagnóstico energético digital"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(40)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _t(negocio or "Mi negocio"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 6, _t(f"Fecha del informe: {fecha}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    hecho = [x is not None for x in (diag, lum, aud)]
    if not any(hecho):
        _titulo(pdf, "Sin resultados todavía")
        _parrafo(pdf, "Aún no se ha calculado ningún módulo. Vuelve a la aplicación, completa al menos uno y genera el informe de nuevo.")

    # 1. Diagnóstico
    if diag is not None:
        _titulo(pdf, "1. Diagnóstico energético")
        if diag["vacio"]:
            _parrafo(pdf, "No se ingresaron equipos con consumo, por eso no hay resultados para este módulo.")
        else:
            filas = [[f["equipo"], C.fmt_num(f["potencia"], 0), C.fmt_num(f["horas"], 1),
                      C.fmt_num(f["kwh"]), C.fmt_cop(f["costo"]), C.fmt_num(f["pct"], 1) + " %"]
                     for f in diag["filas"]]
            _tabla(pdf, ["Equipo", "Potencia (W)", "Horas/día", "kWh/mes", "Costo/mes", "% del total"],
                   filas, (38, 28, 24, 28, 36, 26), ("LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"))
            _parrafo(pdf, f"Consumo total estimado: {C.fmt_num(diag['total_kwh'])} kWh al mes "
                          f"(con un precio de {C.fmt_cop(diag['precio_kwh'])} por kWh, unos {C.fmt_cop(diag['total_costo'])} al mes en la factura).",
                     negrita=True)
            estado = ("por encima" if diag["supera_refrig"] else "dentro")
            _parrafo(pdf, f"La refrigeración (nevera + aire/ventilador) representa el {C.fmt_num(diag['pct_refrig'])} % del consumo, "
                          f"{estado} del máximo de referencia de {C.UMBRAL_REFRIGERACION} % para el sector comercial (UPME). "
                          + ("Aquí hay una oportunidad clara de ahorro." if diag["supera_refrig"] else ""))
            _parrafo(pdf, f"El equipo que más consume es: {diag['equipo_mayor']} ({C.fmt_num(diag['pct_mayor'])} % del total).")
            _parrafo(pdf, "Recomendación: " + diag["recomendacion"])
            _parrafo(pdf, f"Ahorro potencial (supuesto conservador de {int(C.AHORRO_REFRIGERACION * 100)} % menos en refrigeración): "
                          f"cerca de {C.fmt_cop(diag['ahorro_mes'])} al mes, unos {C.fmt_cop(diag['ahorro_anio'])} al año. "
                          "Es una estimación sujeta a validación con datos reales.")
            _barras(pdf, [(f["equipo"], f["kwh"]) for f in diag["filas"]], "kWh/mes")

    # 2. Luminarias
    if lum is not None:
        _titulo(pdf, "2. Iluminación (RETILAP)")
        filas = [[f["nombre"], C.fmt_num(f["cantidad"], 0), C.fmt_num(f["potencia"], 0),
                  C.fmt_num(f["flujo"], 0), C.fmt_num(f["potencia_total"], 0)] for f in lum["filas"]]
        _tabla(pdf, ["Tipo de luminaria", "Cantidad", "Potencia (W)", "Flujo (lm)", "Potencia total (W)"],
               filas, (58, 24, 30, 30, 38), ("LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"))
        _parrafo(pdf, f"Área del local: {C.fmt_num(lum['area'])} m2. Potencia instalada: {C.fmt_num(lum['potencia_total'], 0)} W. "
                      f"Flujo luminoso total: {C.fmt_num(lum['flujo_total'], 0)} lm. "
                      f"Eficacia promedio: {C.fmt_num(lum['eficacia'])} lm/W.")
        _parrafo(pdf, f"Iluminancia media estimada: {C.fmt_num(lum['lux'])} lux.", negrita=True)
        _parrafo(pdf, C.MENSAJES_LUZ[lum["estado"]])

    # 3. Auditoría
    if aud is not None:
        _titulo(pdf, "3. Auditoría energética básica")
        _parrafo(pdf, f"Puntaje obtenido: {aud['puntos']} de {aud['total']} ({C.fmt_num(aud['pct'], 0)} %).", negrita=True, tam=11)
        _parrafo(pdf, aud["mensaje"])
        filas = [[d["pregunta"], "Sí" if d["cumple"] else "No"] for d in aud["detalle"]]
        _tabla(pdf, ["Práctica", "¿La aplica?"], filas, (150, 30), ("LEFT", "CENTER"))
        if aud["pendientes"]:
            _parrafo(pdf, "Para mejorar:", negrita=True)
            for d in aud["pendientes"]:
                _parrafo(pdf, "- " + d["consejo"])

    # 4. IA
    if ia_texto:
        _titulo(pdf, "4. Recomendación generada con inteligencia artificial")
        _parrafo(pdf, ia_texto)

    _titulo(pdf, "Alcance de este informe")
    _parrafo(pdf, AVISO, tam=9, color=GRIS)
    return bytes(pdf.output())
