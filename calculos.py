"""Cálculos de ENERSMART (sin Streamlit, para poder probarlos aparte)."""

UMBRAL_REFRIGERACION = 48      
LUX_MIN = 300                 
LUX_MAX = 500
FACTOR_UTILIZACION = 0.6
FACTOR_MANTENIMIENTO = 0.8
AHORRO_REFRIGERACION = 0.15    

RECOMENDACIONES = {
    "Nevera": "Revisa que las empaquetaduras de la puerta cierren bien y que no esté cerca de fuentes de calor; esto puede aumentar su consumo hasta un 20%.",
    "Cafetera": "Apágala manualmente en horas de bajo tráfico; muchas cafeteras siguen consumiendo energía incluso en modo de espera.",
    "Aire/Ventilador": "Verifica que puertas y ventanas estén cerradas mientras está encendido, y hazle mantenimiento periódico a los filtros.",
    "Iluminación": "Cambia las luces convencionales por bombillos LED; consumen hasta 80% menos energía para la misma cantidad de luz.",
}

REFRIGERACION = ("Nevera", "Aire/Ventilador")

# (clave, pregunta, consejo si la respuesta es "no")
PREGUNTAS_AUDITORIA = [
    ("mant", "¿Realizas mantenimiento periódico a tus equipos de refrigeración (nevera, aire/ventilador)?",
     "Programa una limpieza de filtros y de la parte trasera de la nevera cada 3 a 6 meses."),
    ("led", "¿Usas bombillos LED en la mayoría de tu iluminación?",
     "Cambia poco a poco los bombillos viejos por LED, empezando por los que más horas pasan encendidos."),
    ("apagar", "¿Apagas los equipos que no estás usando en horas de bajo tráfico?",
     "Define una rutina de apagado para cafetera, luces y ventiladores en las horas más flojas."),
    ("fugas", "¿Las puertas y ventanas de tu local cierran bien, sin fugas de aire?",
     "Revisa empaques y rendijas: cada fuga de aire obliga al aire o a la nevera a trabajar más."),
    ("factura", "¿Has revisado tu factura de energía en el último año para detectar aumentos raros?",
     "Compara los kWh de los últimos meses en tu factura; un salto sin explicación merece revisión."),
    ("monitoreo", "¿Cuentas con algún sistema para monitorear tu consumo de energía?",
     "Anota el consumo de cada factura en una tabla sencilla; así ves si tus acciones funcionan."),
    ("antiguedad", "¿Tus equipos eléctricos tienen menos de 5 años de antigüedad?",
     "Si un equipo es muy viejo, cotiza uno eficiente cuando toque cambiarlo (etiqueta CONOCE o clase A)."),
    ("luz_natural", "¿Tu local recibe suficiente luz natural durante el día?",
     "Aprovecha mejor la luz del día: mueve mesas cerca de ventanas y apaga luces donde no hagan falta."),
]

# Valores típicos aproximados de bombillos (potencia W, flujo lm)
PRESETS_LUMINARIA = {
    "Escribir mis propios datos": None,
    "Bombillo LED de 9 W (unos 800 lm)": (9, 800),
    "Bombillo LED de 12 W (unos 1.100 lm)": (12, 1100),
    "Tubo LED de 18 W (unos 1.800 lm)": (18, 1800),
    "Panel LED de 40 W (unos 4.000 lm)": (40, 4000),
    "Bombillo ahorrador de 15 W (unos 900 lm)": (15, 900),
    "Tubo fluorescente de 36 W (unos 2.800 lm)": (36, 2800),
    "Bombillo incandescente de 60 W (unos 700 lm)": (60, 700),
}


def calcular_consumo(potencia, horas):
    """kWh al mes = (W x horas al día x 30) / 1000"""
    return ((potencia or 0) * (horas or 0) * 30) / 1000


def fmt_num(x, dec=1):
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_cop(x):
    return "$" + fmt_num(round(x), 0)


def diagnostico(precio_kwh, equipos):
    """equipos: dict nombre -> (potencia W, horas al día). Devuelve un dict con todo calculado."""
    precio_kwh = precio_kwh or 0
    filas = []
    for nombre, (pot, horas) in equipos.items():
        kwh = calcular_consumo(pot, horas)
        filas.append({"equipo": nombre, "potencia": pot or 0, "horas": horas or 0,
                      "kwh": kwh, "costo": kwh * precio_kwh})
    total = sum(f["kwh"] for f in filas)
    res = {"filas": filas, "precio_kwh": precio_kwh, "total_kwh": total,
           "total_costo": total * precio_kwh, "vacio": total <= 0}
    if res["vacio"]:
        return res
    for f in filas:
        f["pct"] = f["kwh"] / total * 100
    kwh_ref = sum(f["kwh"] for f in filas if f["equipo"] in REFRIGERACION)
    res["kwh_refrig"] = kwh_ref
    res["pct_refrig"] = kwh_ref / total * 100
    res["supera_refrig"] = res["pct_refrig"] > UMBRAL_REFRIGERACION
    mayor = max(filas, key=lambda f: f["kwh"])
    res["equipo_mayor"] = mayor["equipo"]
    res["kwh_mayor"] = mayor["kwh"]
    res["pct_mayor"] = mayor["pct"]
    res["recomendacion"] = RECOMENDACIONES.get(mayor["equipo"], "")
    res["ahorro_mes"] = kwh_ref * AHORRO_REFRIGERACION * precio_kwh
    res["ahorro_anio"] = res["ahorro_mes"] * 12
    return res


def iluminacion(area, tipos):
    """tipos: lista de dicts {nombre, cantidad, potencia, flujo}."""
    area = max(area or 0, 0.1)
    filas = []
    usados = set()
    for i, t in enumerate(tipos):
        nombre = (t.get("nombre") or "").strip() or f"Tipo {i + 1}"
        base, n = nombre, 2
        while nombre in usados:
            nombre = f"{base} ({n})"
            n += 1
        usados.add(nombre)
        cant, pot, flujo = t.get("cantidad") or 0, t.get("potencia") or 0, t.get("flujo") or 0
        filas.append({"nombre": nombre, "cantidad": cant, "potencia": pot, "flujo": flujo,
                      "potencia_total": cant * pot, "flujo_total": cant * flujo})
    pot_total = sum(f["potencia_total"] for f in filas)
    flujo_total = sum(f["flujo_total"] for f in filas)
    eficacia = flujo_total / pot_total if pot_total > 0 else 0
    lux = (flujo_total * FACTOR_UTILIZACION * FACTOR_MANTENIMIENTO) / area
    if flujo_total <= 0:
        estado = "vacio"
    elif lux < LUX_MIN:
        estado = "bajo"
    elif lux > LUX_MAX:
        estado = "alto"
    else:
        estado = "ok"
    return {"area": area, "filas": filas, "potencia_total": pot_total, "flujo_total": flujo_total,
            "eficacia": eficacia, "lux": lux, "estado": estado}


MENSAJES_LUZ = {
    "bajo": "Está por debajo de los 300 lux de referencia (RETILAP, Tabla 440.1 / UNE-EN 12464-1) para zonas de atención al cliente en cafeterías. Riesgo de incumplimiento normativo.",
    "alto": "Está muy por encima de lo necesario. Puede ser un desperdicio energético: considera reducir potencia o cantidad de luminarias.",
    "ok": "Cumple con el nivel de iluminancia recomendado para tu tipo de negocio.",
    "vacio": "No ingresaste luminarias con flujo luminoso, así que no se pudo calcular la iluminancia.",
}

MENSAJES_AUDITORIA = {
    "verde": "Excelente gestión energética. Tu negocio ya aplica la mayoría de las buenas prácticas.",
    "amarillo": "Buena gestión, pero hay oportunidades claras de mejora en tu consumo energético.",
    "rojo": "Gestión energética deficiente. Te recomendamos solicitar un Diagnóstico Energético Digital completo con ENERSMART.",
}


def auditoria(respuestas):
    """respuestas: dict clave -> bool."""
    total = len(PREGUNTAS_AUDITORIA)
    detalle = [{"clave": c, "pregunta": p, "cumple": bool(respuestas.get(c)), "consejo": cs}
               for c, p, cs in PREGUNTAS_AUDITORIA]
    puntos = sum(d["cumple"] for d in detalle)
    pct = puntos / total * 100
    nivel = "verde" if pct >= 80 else ("amarillo" if pct >= 50 else "rojo")
    return {"puntos": puntos, "total": total, "pct": pct, "nivel": nivel,
            "mensaje": MENSAJES_AUDITORIA[nivel], "detalle": detalle,
            "pendientes": [d for d in detalle if not d["cumple"]]}
