import os
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import calculos as C
from informe import generar_pdf

ICONO = "logo.png" if os.path.exists("logo.png") else None
st.set_page_config(page_title="ENERSMART", page_icon=ICONO, layout="centered")

# ---------------------------------------------------------------------------
# Configuración y seguridad
# ---------------------------------------------------------------------------

def secreto(nombre, defecto=None):
    try:
        return st.secrets.get(nombre, defecto)
    except Exception:  
        return defecto


MODELO_IA = secreto("GEMINI_MODEL", "gemini-3.8-flash")
MAX_IA_POR_SESION = int(secreto("MAX_IA_POR_SESION", 3))   
MAX_IA_POR_DIA = int(secreto("MAX_IA_POR_DIA", 150))      
URL_ENCUESTA = secreto("URL_ENCUESTA", "")                 


class CupoAgotado(Exception):
    pass


@st.cache_resource
def _cupo_global():
    return {"fecha": None, "usos": 0, "lock": threading.Lock()}


def _gastar_cupo_global():
    cupo = _cupo_global()
    with cupo["lock"]:
        hoy = date.today()
        if cupo["fecha"] != hoy:
            cupo["fecha"], cupo["usos"] = hoy, 0
        if cupo["usos"] >= MAX_IA_POR_DIA:
            raise CupoAgotado()
        cupo["usos"] += 1


@st.cache_data(ttl=3600, show_spinner=False)
def _consejo_gemini(consumo, costo, equipo, pct, modelo):
    """Solo se envían números y el nombre de un equipo de una lista fija: nunca el nombre del negocio."""
    from google import genai
    from google.genai import types

    _gastar_cupo_global()
    cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"],
                           http_options=types.HttpOptions(timeout=60000))
    pregunta = (
        "Eres un asesor experto en eficiencia energética para pequeños negocios en Colombia. "
        f"Un cliente tiene un consumo total de {consumo} kWh al mes, con un costo aproximado de ${costo} al mes. "
        f"El equipo que más consume es: {equipo}, representando el {pct}% del total. "
        "Escribe un consejo breve, cálido y fácil de entender (máximo 4 líneas) para ayudarle a ahorrar energía, "
        "dirigido al dueño de una cafetería pequeña, sin tecnicismos."
    )
    # Revisar por si el modelo cambia...
    respaldo = secreto("GEMINI_MODEL_RESPALDO", "gemini-3.6-flash")
    modelos = [modelo] + ([respaldo] if respaldo and respaldo != modelo else [])
    ultimo = None
    for m in modelos:
        for intento in range(2):
            try:
                respuesta = cliente.models.generate_content(model=m, contents=pregunta)
                texto = (respuesta.text or "").strip()
                if texto:
                    return texto
                ultimo = RuntimeError("Respuesta vacía")
            except Exception as e:
                ultimo = e
                codigo = getattr(e, "code", None)
                if codigo in (500, 502, 503, 504) or "ServerError" in type(e).__name__:
                    time.sleep(2)      
                    continue
                if codigo == 404:
                    break             
                raise                  
    raise ultimo or RuntimeError("Sin respuesta")


# ---------------------------------------------------------------------------
# Estado: los valores escritos no se pierden al cambiar de sección
# ---------------------------------------------------------------------------
EQUIPOS = [  # clave, nombre, ayuda de potencia, potencia, horas por defecto
    ("nevera", "Nevera", "Una nevera pequeña ronda los 100 a 250 W.", 150, 24.0),
    ("cafetera", "Cafetera", "Las cafeteras eléctricas van de 800 a 1.500 W.", 1000, 3.0),
    ("ac", "Aire acondicionado o ventilador", "Un ventilador usa 40 a 80 W; un aire mini-split, 800 a 1.500 W.", 800, 6.0),
    ("luces", "Iluminación", "Suma la potencia de todas tus luces (cantidad × vatios de cada una).", 200, 10.0),
]
NOMBRES_EQUIPO = {"nevera": "Nevera", "cafetera": "Cafetera", "ac": "Aire/Ventilador", "luces": "Iluminación"}
SECCIONES = ["Diagnóstico energético", "Luminarias (RETILAP)", "Auditoría energética", "Informe en PDF"]
ICONOS_MENU = {SECCIONES[0]: ":material/bolt:", SECCIONES[1]: ":material/lightbulb:",
               SECCIONES[2]: ":material/fact_check:", SECCIONES[3]: ":material/description:"}
MAX_TIPOS = 5

DEFAULTS = {"w_negocio": "", "w_seccion": SECCIONES[0], "w_precio": 850, "w_area": 40.0, "w_lum_n": 2}
for clave, _, _, pot, horas in EQUIPOS:
    DEFAULTS.update({f"w_pot_{clave}": pot, f"w_h_{clave}": horas, f"w_no_{clave}": False})
for i in range(MAX_TIPOS):
    DEFAULTS.update({f"w_lum_nombre_{i}": "", f"w_lum_preset_{i}": "Escribir mis propios datos",
                     f"w_lum_cant_{i}": 4, f"w_lum_pot_{i}": 15, f"w_lum_flujo_{i}": 1500})
for c, _, _ in C.PREGUNTAS_AUDITORIA:
    DEFAULTS[f"w_aud_{c}"] = False

for k, v in st.session_state.get("_guardado", {}).items():   # recupera lo escrito antes
    if k not in st.session_state:
        st.session_state[k] = v
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)
for k in ("calc_diag", "calc_lum", "calc_aud"):
    st.session_state.setdefault(k, False)

ss = st.session_state

# ---------------------------------------------------------------------------
# Menú lateral
# ---------------------------------------------------------------------------
def reiniciar():
    """Borra todo lo escrito y calculado para atender a otra cafetería (conserva el contador de IA)."""
    usos = ss.get("ia_usos", 0)
    ss.clear()
    ss["ia_usos"] = usos


st.sidebar.title("ENERSMART")
st.sidebar.text_input("Nombre de tu local o empresa", max_chars=60, key="w_negocio",
                      placeholder="Ej. Café La Esquina",
                      help="Aparece en tus resultados y en el informe en PDF.")
st.sidebar.radio("Menú", SECCIONES, key="w_seccion", format_func=lambda x: f"{ICONOS_MENU[x]} {x}")
with st.sidebar.expander("Atender otra cafetería"):
    st.caption("Borra todos los datos y resultados de esta pantalla. Descarga antes el informe en PDF si lo necesitas.")
    st.button("Empezar de cero", on_click=reiniciar, key="btn_reiniciar", icon=":material/restart_alt:")
st.sidebar.divider()
st.sidebar.caption("No guardamos tus datos: todo se queda en tu sesión y se borra al cerrar la página.")
st.sidebar.info("Próximamente: plan de seguimiento trimestral con histórico de consumos y alertas de picos de energía.")
if URL_ENCUESTA:
    st.sidebar.link_button("Cuéntanos qué te pareció", URL_ENCUESTA, icon=":material/rate_review:")

negocio = (ss.w_negocio or "").strip()
seccion = ss.w_seccion

st.title("ENERSMART")
st.write(f"Diagnóstico energético digital para **{negocio}**" if negocio else "Diagnóstico energético digital para tu negocio")


# ---------------------------------------------------------------------------
# Componentes reutilizables
# ---------------------------------------------------------------------------
def imagen_ayuda(nombre, pie=None):
    """Muestra una imagen de la carpeta imagenes/. Si el archivo no existe, no muestra nada (la app no se rompe)."""
    ruta = os.path.join("imagenes", nombre)
    if os.path.exists(ruta):
        st.image(ruta, caption=pie)


def paso(n, total=3):
    """Indicador «Paso n de total» con barra de avance."""
    st.progress(n / total, text=f"Paso {n} de {total}")


def ayuda_potencia():
    with st.expander(":material/search: ¿No sabes cuántos vatios (W) tiene tu equipo?"):
        st.markdown(
            "- Busca la **etiqueta** pegada atrás o a un lado del equipo: dice **W** o **Watts**.\n"
            "- Si solo ves **voltios (V)** y **amperios (A)**, multiplícalos: **W = V × A** "
            "(en Colombia casi siempre son 110 a 120 V).\n"
            "- Si no encuentras nada, usa el valor típico que aparece en la ayuda (el signo **?**) de cada casilla."
        )
        imagen_ayuda("etiqueta_potencia.jpg", "Así se ve una etiqueta: busca la línea marcada con «W».")
        imagen_ayuda("esquema_vatios.png")


def ayuda_horas():
    with st.expander(":material/schedule: ¿Cómo calculo las horas de uso al día?"):
        st.markdown(
            "Cuenta **cuántas horas al día** está encendido el equipo. Por ejemplo:\n"
            "- Abres de 8 a.m. a 8 p.m. y las luces están prendidas todo ese tiempo: **12 horas**.\n"
            "- La cafetera la usas de 7 a 10 a.m.: **3 horas**.\n"
            "- La nevera está conectada todo el día: **24 horas**."
        )


def bloque_equipo(clave, nombre, ayuda):
    st.subheader(nombre)
    if st.checkbox("No tengo o no uso este equipo", key=f"w_no_{clave}"):
        st.caption("Este equipo no suma a tu cuenta de energía.")
        return 0, 0.0
    c1, c2 = st.columns(2)
    pot = c1.number_input("Potencia (vatios)", min_value=0, max_value=20000, step=10, key=f"w_pot_{clave}", help=ayuda)
    horas = c2.number_input("Horas encendido al día", min_value=0.0, max_value=24.0, step=0.5, key=f"w_h_{clave}",
                            help="Ej.: abierto de 8 a.m. a 8 p.m. = 12 horas.")
    return pot or 0, horas or 0.0


def mensaje_error_ia(detalle):
    d = detalle.upper()
    if "429" in d or "RESOURCE_EXHAUSTED" in d or "QUOTA" in d:
        return "Se alcanzó el límite gratuito de la IA por ahora. Espera un minuto y vuelve a intentar; tu diagnóstico sigue siendo válido."
    if "503" in d or "UNAVAILABLE" in d or "OVERLOADED" in d:
        return "El servicio de IA está saturado en este momento. Intenta de nuevo en unos minutos; tu diagnóstico sigue siendo válido."
    if "404" in d or "NOT_FOUND" in d:
        return "El modelo de IA configurado no está disponible. Avisa a quien administra la app; tu diagnóstico sigue siendo válido."
    if "API_KEY" in d or "401" in d or "403" in d or "PERMISSION_DENIED" in d or "400" in d:
        return "La IA no está bien configurada (clave o permisos). Avisa a quien administra la app; tu diagnóstico sigue siendo válido."
    return "No pude generar la recomendación con IA en este momento. Intenta de nuevo más tarde; tu diagnóstico sigue siendo válido."


def mostrar_ia(res):
    st.subheader(":material/auto_awesome: Recomendación con inteligencia artificial")
    usos = ss.get("ia_usos", 0)
    if not secreto("GEMINI_API_KEY"):
        st.info("La recomendación con IA no está disponible por ahora. El resto del diagnóstico funciona normal.")
        return
    firma = (round(res["total_kwh"], 1), round(res["total_costo"]), res["equipo_mayor"], round(res["pct_mayor"], 1))
    if st.button("Generar recomendación con IA", disabled=usos >= MAX_IA_POR_SESION, icon=":material/auto_awesome:"):
        ss["ia_usos"] = usos + 1
        try:
            with st.spinner("Pensando un consejo para tu negocio..."):
                texto = _consejo_gemini(firma[0], firma[1], firma[2], firma[3], MODELO_IA)
            ss["res_ia"] = {"texto": texto, "firma": firma} if texto else None
            if not texto:
                st.warning("La IA no devolvió respuesta esta vez. Intenta de nuevo en un momento.")
        except CupoAgotado:
            st.info("Hoy ya se usó todo el cupo gratuito de la IA. Vuelve mañana; tu diagnóstico completo sigue disponible.")
        except Exception as e:  
            clave = str(secreto("GEMINI_API_KEY", "") or "")
            detalle = f"{type(e).__name__}: {str(e)}"
            if clave:
                detalle = detalle.replace(clave, "***")
            print("Error al llamar a Gemini:", detalle[:500])
            st.warning(mensaje_error_ia(detalle))
            if secreto("DEBUG_IA", False):   
                st.code(detalle[:500])
    if usos >= MAX_IA_POR_SESION:
        st.caption(f"Ya usaste las {MAX_IA_POR_SESION} recomendaciones con IA de esta visita.")
    ia = ss.get("res_ia")
    if ia:
        st.write(ia["texto"])
        if ia["firma"] != firma:
            st.caption("Esta recomendación se generó con datos anteriores. Genera una nueva para que coincida con tus cambios.")
        st.caption("Generada con IA: revísala antes de aplicarla.")


def pie():
    st.caption("Los resultados son estimaciones orientativas: no reemplazan una auditoría profesional ni garantizan un ahorro.")


# ---------------------------------------------------------------------------
# 1) DIAGNÓSTICO ENERGÉTICO
# ---------------------------------------------------------------------------
if seccion == SECCIONES[0]:
    paso(1)
    st.header(":material/bolt: Diagnóstico energético")
    st.write("Llena los datos de tus equipos principales; con eso calculo cuánta energía gastas y cuánto te cuesta.")
    ayuda_potencia()
    ayuda_horas()

    st.header(":material/payments: Tarifa de energía")
    st.number_input("Precio del kWh según tu factura (en pesos)", min_value=0, max_value=5000, step=10, key="w_precio",
                    help="Lo encuentras en tu factura de energía, como «costo unitario» o «valor kWh».")
    with st.expander(":material/receipt_long: ¿Dónde encuentro el precio del kWh en mi factura?"):
        st.markdown("Busca en tu factura de energía la línea que dice **«valor kWh»**, **«costo unitario»** o **«tarifa»**. "
                    "Es un número en pesos por cada kWh consumido.")
        imagen_ayuda("factura_kwh.jpg", "Ejemplo de factura (con nombre y dirección tapados): la flecha señala el valor del kWh.")

    equipos = {}
    for clave, nombre, ayuda, _, _ in EQUIPOS:
        pot, horas = bloque_equipo(clave, nombre, ayuda)
        equipos[NOMBRES_EQUIPO[clave]] = (pot, horas)
        kwh = C.calcular_consumo(pot, horas)
        st.write(f"Consumo aproximado: **{C.fmt_num(kwh)} kWh al mes**")

    st.header(":material/analytics: Resumen de tu diagnóstico")
    if st.button("Calcular mi diagnóstico energético", icon=":material/calculate:"):
        ss.calc_diag = True

    if ss.calc_diag:
        res = C.diagnostico(ss.w_precio, equipos)
        ss["res_diag"] = res
        if res["vacio"]:
            st.warning("Todavía no hay consumo para calcular. Ingresa la potencia y las horas de al menos un equipo.")
        else:
            c1, c2 = st.columns(2)
            c1.metric("Consumo total estimado", f"{C.fmt_num(res['total_kwh'])} kWh/mes")
            c2.metric("Costo aproximado en tu factura", f"{C.fmt_cop(res['total_costo'])}/mes")

            st.write(f"Tu refrigeración (nevera + aire/ventilador) representa el **{C.fmt_num(res['pct_refrig'])} %** de tu consumo total.")
            if res["supera_refrig"]:
                st.warning(f"Tu refrigeración está por encima del {C.UMBRAL_REFRIGERACION}%, que es el máximo esperado en el sector comercial "
                           "según la UPME. Aquí hay una oportunidad clara de ahorro.")
            else:
                st.success("Tu refrigeración está dentro del rango esperado para el sector comercial.")

            st.subheader(":material/manage_search: ¿En qué se te va más la energía?")
            st.write(f"El equipo que más consume en tu negocio es: **{res['equipo_mayor']}**, "
                     f"con el **{C.fmt_num(res['pct_mayor'])} %** de tu consumo total.")
            st.info("Recomendación: " + res["recomendacion"])
            st.write(f"Si logras reducir un {int(C.AHORRO_REFRIGERACION * 100)} % el consumo de tu refrigeración (supuesto conservador), "
                     f"ahorrarías cerca de **{C.fmt_cop(res['ahorro_mes'])} al mes** (unos {C.fmt_cop(res['ahorro_anio'])} al año).")

            grafico = pd.DataFrame({"Consumo (kWh/mes)": {f["equipo"]: f["kwh"] for f in res["filas"]}})
            st.bar_chart(grafico)
            mostrar_ia(res)
            st.success("Listo. Cuando quieras, ve a «Informe en PDF» en el menú para descargar tus resultados.")
    pie()

# ---------------------------------------------------------------------------
# 2) LUMINARIAS (RETILAP)
# ---------------------------------------------------------------------------
elif seccion == SECCIONES[1]:
    paso(2)
    st.header(":material/lightbulb: Luminarias (según RETILAP)")
    st.write("Cuéntame qué luces tienes y verifico si tu local está bien iluminado para atender clientes.")
    with st.expander(":material/search: ¿Qué es el flujo luminoso (lúmenes)?"):
        st.markdown(
            "Los **lúmenes (lm)** miden cuánta luz da un bombillo; los **vatios (W)**, cuánta energía gasta. "
            "Casi siempre vienen impresos en la **caja** o en el **cuerpo del bombillo** (por ejemplo «9 W – 800 lm»). "
            "Si no los encuentras, elige abajo el tipo de bombillo que más se parezca y usaré valores típicos."
        )
        imagen_ayuda("caja_bombillo.jpg", "En la caja: «W» son los vatios y «lm» son los lúmenes.")

    st.number_input("Área del local (m²)", min_value=1.0, max_value=2000.0, step=1.0, key="w_area",
                    help="Largo × ancho del espacio donde atiendes a los clientes.")
    with st.expander(":material/straighten: ¿Cómo calculo el área?"):
        st.markdown("Mide el **largo** y el **ancho** de la zona donde atiendes y multiplícalos. "
                    "Si el local no es un rectángulo, divídelo en rectángulos y suma las áreas.")
        imagen_ayuda("area_local.png")
    st.number_input("¿Cuántos tipos distintos de luminaria tienes?", min_value=1, max_value=MAX_TIPOS, step=1, key="w_lum_n")

    tipos = []
    for i in range(int(ss.w_lum_n)):
        st.subheader(f"Tipo de luminaria {i + 1}")
        st.text_input("Nombre o ubicación (ej. «LED mesas», «Fluorescente cocina»)", key=f"w_lum_nombre_{i}", max_chars=40)
        eleccion = st.selectbox("¿Qué bombillo es?", list(C.PRESETS_LUMINARIA), key=f"w_lum_preset_{i}")
        st.number_input("Número de luminarias de este tipo", min_value=0, max_value=500, step=1, key=f"w_lum_cant_{i}")
        preset = C.PRESETS_LUMINARIA[eleccion]
        if preset:
            pot, flujo = preset
            st.caption(f"Uso valores típicos aproximados: {pot} W y {C.fmt_num(flujo, 0)} lm por luminaria.")
        else:
            c1, c2 = st.columns(2)
            pot = c1.number_input("Potencia por luminaria (W)", min_value=0, max_value=2000, step=1, key=f"w_lum_pot_{i}")
            flujo = c2.number_input("Flujo luminoso por luminaria (lúmenes)", min_value=0, max_value=100000, step=50, key=f"w_lum_flujo_{i}")
        tipos.append({"nombre": ss[f"w_lum_nombre_{i}"], "cantidad": ss[f"w_lum_cant_{i}"], "potencia": pot or 0, "flujo": flujo or 0})

    if st.button("Calcular iluminación", icon=":material/calculate:"):
        ss.calc_lum = True

    if ss.calc_lum:
        res = C.iluminacion(ss.w_area, tipos)
        ss["res_lum"] = res
        if res["estado"] == "vacio":
            st.warning(C.MENSAJES_LUZ["vacio"])
        else:
            c1, c2 = st.columns(2)
            c1.metric("Potencia instalada", f"{C.fmt_num(res['potencia_total'], 0)} W")
            c2.metric("Flujo luminoso total", f"{C.fmt_num(res['flujo_total'], 0)} lm")
            c3, c4 = st.columns(2)
            c3.metric("Eficacia luminosa promedio", f"{C.fmt_num(res['eficacia'])} lm/W")
            c4.metric("Iluminancia media estimada", f"{C.fmt_num(res['lux'])} lux")
            mensaje = C.MENSAJES_LUZ[res["estado"]]
            if res["estado"] == "bajo":
                st.warning("" + mensaje)
            elif res["estado"] == "alto":
                st.info("" + mensaje)
            else:
                st.success("" + mensaje)
            grafico = pd.DataFrame({"Potencia (W)": {f["nombre"]: f["potencia_total"] for f in res["filas"]}})
            st.bar_chart(grafico)
    pie()

# ---------------------------------------------------------------------------
# 3) AUDITORÍA ENERGÉTICA
# ---------------------------------------------------------------------------
elif seccion == SECCIONES[2]:
    paso(3)
    st.header(":material/fact_check: Auditoría energética básica")
    st.write("Marca las prácticas que **ya** aplicas en tu negocio:")
    respuestas = {c: st.checkbox(p, key=f"w_aud_{c}") for c, p, _ in C.PREGUNTAS_AUDITORIA}

    if st.button("Calcular resultado de la auditoría", icon=":material/calculate:"):
        ss.calc_aud = True

    if ss.calc_aud:
        res = C.auditoria(respuestas)
        ss["res_aud"] = res
        st.metric("Puntaje obtenido", f"{res['puntos']} de {res['total']}")
        st.progress(res["pct"] / 100)
        if res["nivel"] == "verde":
            st.success("" + res["mensaje"])
        elif res["nivel"] == "amarillo":
            st.warning("" + res["mensaje"])
        else:
            st.error("" + res["mensaje"])
        if res["pendientes"]:
            st.subheader("Por dónde empezar")
            for d in res["pendientes"]:
                st.write("• " + d["consejo"])
    pie()

# ---------------------------------------------------------------------------
# 4) INFORME EN PDF
# ---------------------------------------------------------------------------
else:
    st.caption("Último paso: descarga tu informe.")
    st.header(":material/description: Informe en PDF")
    st.write("Aquí reúno en un solo documento los resultados que ya calculaste.")
    diag, lum, aud = ss.get("res_diag"), ss.get("res_lum"), ss.get("res_aud")
    st.write(("Listo: " if diag else "Pendiente: ") + "Diagnóstico energético")
    st.write(("Listo: " if lum else "Pendiente: ") + "Luminarias (RETILAP)")
    st.write(("Listo: " if aud else "Pendiente: ") + "Auditoría energética")
    ia = ss.get("res_ia")
    st.write(("Listo: " if ia else "Pendiente: ") + "Recomendación con IA (opcional)")

    if not negocio:
        st.info("Escribe el nombre de tu local o empresa en el menú lateral para que aparezca en el informe.")
    if not (diag or lum or aud):
        st.warning("Primero calcula al menos un módulo y vuelve aquí.")
    if negocio and (diag or lum or aud):
        fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y")
        try:
            pdf = generar_pdf(negocio, fecha, diag, lum, aud, ia["texto"] if ia else None)
            nombre_archivo = "".join(ch if ch.isalnum() else "_" for ch in negocio)[:40] or "negocio"
            st.download_button("Descargar informe en PDF", icon=":material/download:", data=pdf, file_name=f"ENERSMART_{nombre_archivo}.pdf",
                               mime="application/pdf")
        except Exception as e:
            print("Error al generar el PDF:", type(e).__name__)
            st.error("No pude armar el PDF en este momento. Intenta de nuevo; tus resultados no se perdieron.")
    pie()


ss["_guardado"] = {k: v for k, v in ss.items() if k.startswith("w_")}
