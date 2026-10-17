"""EFG Training · caminatas registradas desde capturas de Apple Fitness.

No hay conexión con Apple Watch. Estos registros se guardan y consultan
separados de los entrenamientos de fuerza.
"""
from __future__ import annotations

from datetime import date
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


CYAN = "#22D3EE"
PURPLE = "#A855F7"
PINK = "#F472B6"
MINT = "#4ADE80"
MUTED = "#B9ABCD"


def duration_label(seconds: int | float) -> str:
    value = max(0, int(seconds or 0))
    hours, rem = divmod(value, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"


def pace_label(seconds_per_km: int | float) -> str:
    value = max(0, int(seconds_per_km or 0))
    return f"{value // 60}:{value % 60:02d} min/km"


def walk_rows(walks: list[dict]) -> list[dict]:
    """Sanitize data loaded from GitHub without inventing missing values."""
    rows = []
    for walk in walks:
        if not isinstance(walk, dict):
            continue
        try:
            recorded = date.fromisoformat(str(walk["date"]))
            km = float(walk["distance_km"])
            duration = int(walk["moving_duration_seconds"])
            elapsed = int(walk["elapsed_seconds"])
            kcal = int(walk["active_kcal"])
            total = int(walk["total_kcal"])
            heart = int(walk["average_hr_bpm"])
            pace = int(walk["pace_seconds_per_km"])
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        if not (math.isfinite(km) and 0 < km <= 150 and 0 < duration <= 86400
                and duration <= elapsed <= 172800 and 0 <= kcal <= total <= 10000
                and 30 <= heart <= 240 and 60 <= pace <= 3600):
            continue
        rows.append({
            "date": recorded, "distance_km": km, "duration": duration,
            "elapsed": elapsed, "active_kcal": kcal, "total_kcal": total,
            "hr": heart, "pace": pace, "raw": walk,
        })
    rows.sort(key=lambda row: (row["date"], str(row["raw"].get("start_time", ""))))
    return rows


def _chart_style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        height=325, title=dict(text=title, font=dict(color="#F3EDFF", size=15)),
        margin=dict(l=6, r=12, t=60, b=35),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F3EDFF", size=12),
        xaxis=dict(showgrid=False, tickformat="%d/%m", tickfont=dict(color=MUTED)),
        yaxis=dict(gridcolor="rgba(174,128,229,.15)", tickfont=dict(color=MUTED)),
    )
    return fig


def render_walks_dashboard(walks: list[dict], offline: bool = False) -> None:
    st.markdown("### 🚶 Caminatas · actividad al aire libre")
    st.caption(
        "Entrenamientos de caminata cargados manualmente desde tus capturas "
        "de Apple Fitness. No hay sincronización con Apple Watch ni con Salud. "
        "Las caminatas no se contabilizan como sesiones de gimnasio."
    )
    if offline:
        st.warning("No se pudo actualizar el historial de caminatas desde GitHub; se muestra la copia local.")
    rows = walk_rows(walks)
    if not rows:
        st.info("Todavía no hay caminatas registradas.")
        return

    last = rows[-1]
    total_distance = sum(row["distance_km"] for row in rows)
    total_duration = sum(row["duration"] for row in rows)
    total_active = sum(row["active_kcal"] for row in rows)
    a, b = st.columns(2)
    a.metric("Caminatas registradas", len(rows))
    b.metric("Distancia acumulada", f"{total_distance:.2f} km".replace(".", ","))
    c, d = st.columns(2)
    c.metric("Tiempo de entrenamiento", duration_label(total_duration))
    d.metric("Kcal activas estimadas", f"{total_active:,}".replace(",", "."))

    if len(rows) > 1:
        st.markdown("#### 📈 Evolución de las caminatas")
        selection = st.radio(
            "Indicador", ["Distancia", "Ritmo", "Frecuencia cardíaca"],
            horizontal=True, key="efg_walks_metric",
        )
        metric = {
            "Distancia": ("distance_km", "Distancia (km)", CYAN),
            "Ritmo": ("pace", "Ritmo (min/km)", PURPLE),
            "Frecuencia cardíaca": ("hr", "FC media (lpm)", PINK),
        }[selection]
        key, axis_title, color = metric
        fig = go.Figure(go.Scatter(
            x=[row["date"] for row in rows],
            y=[row[key] / 60 if key == "pace" else row[key] for row in rows],
            mode="lines+markers",
            line=dict(color=color, width=3),
            marker=dict(color=color, size=11, line=dict(color="#FFFFFF", width=1)),
        ))
        fig.update_layout(yaxis_title=axis_title)
        st.plotly_chart(_chart_style(fig, "Progreso por fecha"), use_container_width=True,
                        config={"displayModeBar": False})
        if selection == "Ritmo":
            st.caption("En el ritmo, un valor menor significa más velocidad; compará recorridos similares.")
    else:
        st.caption("Con la próxima caminata podremos comparar distancias, ritmos y frecuencia cardíaca.")

    st.markdown("#### 🗓️ Detalle del entrenamiento")
    choices = list(range(len(rows) - 1, -1, -1))
    chosen = st.selectbox(
        "Fecha de la caminata", choices,
        format_func=lambda idx: (
            f"{rows[idx]['date'].strftime('%d/%m/%Y')} · "
            f"{rows[idx]['distance_km']:.2f} km".replace(".", ",")
        ), key="efg_walks_select",
    )
    row = rows[chosen]
    source = row["raw"]
    hours = str(source.get("start_time", ""))
    end = str(source.get("end_time", ""))
    st.caption(
        f"{row['date'].strftime('%d/%m/%Y')} · "
        f"{hours}{'–' + end if end else ''} · {source.get('activity', 'Caminata')}"
    )

    a, b = st.columns(2)
    a.metric("Distancia", f"{row['distance_km']:.2f} km".replace(".", ","))
    b.metric("Ritmo medio", pace_label(row["pace"]))
    c, d = st.columns(2)
    c.metric("Duración del ejercicio", duration_label(row["duration"]))
    d.metric("Tiempo transcurrido", duration_label(row["elapsed"]))
    e, f = st.columns(2)
    e.metric("Kcal activas (estimadas)", row["active_kcal"])
    f.metric("Kcal totales (estimadas)", row["total_kcal"])
    g, h = st.columns(2)
    g.metric("FC promedio", f"{row['hr']} lpm")
    h.metric("Desnivel positivo", f"{source.get('elevation_gain_m', '—')} m")

    zones = source.get("hr_zones_seconds")
    if isinstance(zones, dict):
        z1 = max(0, int(zones.get("z1", 0)))
        st.markdown("#### ❤️ Tiempo en zonas cardíacas")
        st.caption(
            f"Zona 1 (<131 lpm): {duration_label(z1)} · "
            + " · ".join(
                f"Zona {index}: {duration_label(zones.get(f'z{index}', 0))}"
                for index in range(2, 6)
            )
        )
        if sum(int(zones.get(f"z{index}", 0)) for index in range(1, 6)) < row["duration"]:
            st.caption("Las lecturas por zona no cubren toda la duración. No se completaron los intervalos faltantes.")
    recovery = source.get("post_workout_hr_bpm")
    if isinstance(recovery, dict) and recovery.get("at_end") is not None:
        st.caption(
            f"FC tras finalizar: {recovery['at_end']} lpm. "
            "No hay lectura informada al minuto ni a los dos minutos."
        )
    hr_range = source.get("hr_range_bpm")
    if isinstance(hr_range, dict):
        st.caption(f"Frecuencia cardíaca observada: {hr_range.get('min', '—')}–{hr_range.get('max', '—')} lpm.")
    st.caption(
        "Los datos se transcriben de imágenes de Apple Fitness; las calorías son estimaciones. "
        "La duración del ejercicio y el tiempo transcurrido son indicadores distintos. "
        "No se almacena el trazado GPS de la caminata."
    )

    st.markdown("#### 📚 Historial de caminatas")
    history = pd.DataFrame([
        {"Fecha": item["date"], "Distancia (km)": item["distance_km"],
         "Duración": duration_label(item["duration"]),
         "Ritmo": pace_label(item["pace"]),
         "Kcal activas": item["active_kcal"],
         "FC media (lpm)": item["hr"]}
        for item in reversed(rows)
    ])
    st.dataframe(history, hide_index=True, use_container_width=True,
                 column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
