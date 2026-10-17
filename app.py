"""EFG Training · seguimiento público de fuerza, edición protegida por PIN.

Datos del plan: data/plan.json, migrados de la planilla original.
Entrenamientos: data/history.json, persistidos mediante GitHub Contents API.
Credenciales: Streamlit Community Cloud > App settings > Secrets.
"""
from __future__ import annotations

import base64
import csv
import hmac
from html import escape as html_escape
import io
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import requests
from visuals import render_plan_charts, render_calendar, render_weight_chart
from timer import render_rest_timer
from new_blocks import (ACTIVE_BLOCK_ID, LEGACY_BLOCK_ID, ACTIVE_TITLE, DAY_FOCUS, DAY_TIME, canonical_name, block_of, view_sessions, scope_key, last_and_best, format_load)
from block_views import render_summary, render_archive, render_exercise_progress, render_legacy_reports
# Módulo propio para evitar conflictos de importación en Streamlit Cloud.
# Las métricas proceden de CAPTURAS transcritas manualmente: no existe una
# conexión directa ni sincronización automática con Apple Watch.
try:
    from efg_watch_dashboard import render_watch_dashboard, render_day_watch_summary
except ImportError:
    def render_watch_dashboard(*args, **kwargs):
        st.warning(
            "Los registros de Apple Fitness cargados desde capturas "
            "no están disponibles temporalmente. El resto de la app sigue operativo."
        )

    def render_day_watch_summary(*args, **kwargs):
        return None
from session_detail import render_session_detail
# Módulo aislado: si falla la presentación de caminatas no debe
# impedir que se abran las rutinas y el historial de fuerza.
try:
    from efg_walks_dashboard import render_walks_dashboard
except ImportError:
    def render_walks_dashboard(*args, **kwargs):
        st.warning("La sección de caminatas no está disponible temporalmente.")


st.set_page_config(
    page_title="EFG Training | Strength & Progress",
    page_icon="💜",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REPO = "floresgrancelli/EFG-Training"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}/contents"
PURPLE = "#A855F7"
VIOLET = "#7C3AED"
PINK = "#F472B6"
CYAN = "#22D3EE"
MINT = "#4ADE80"
TEXT = "#F3EDFF"
MUTED = "#AA9FBF"
BG = "#080714"
CARD = "#171328"
DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&display=swap');
    html, body, [data-testid="stApp"], p, label, button, input {font-family:'Outfit',sans-serif}
    [data-testid="stAppViewContainer"] {
       background: radial-gradient(ellipse 50% 24% at 84% 3%,rgba(124,58,237,.20),transparent),
                   radial-gradient(ellipse 42% 25% at 10% 32%,rgba(219,39,119,.075),transparent),
                   #080714;
    }
    [data-testid="stHeader"] {background:transparent}
    .block-container {max-width:1180px; padding-top:1.35rem; padding-bottom:3rem}
    h1,h2,h3,h4 {color:#F5F1FF; letter-spacing:-.045em}
    h2 {padding-top:1rem}
    [data-testid="stMetric"] {
        background:linear-gradient(140deg,rgba(88,37,156,.24),rgba(29,24,53,.90));
        border:1px solid rgba(181,126,255,.22);
        border-radius:18px; padding:18px 18px 14px; min-height:100px;
    }
    [data-testid="stMetricLabel"] {color:#B4A8C6}
    [data-testid="stMetricValue"] {color:#F5ECFF; font-size:1.62rem}
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] {line-height:1.5}
    div[data-testid="stExpander"] {border:1px solid rgba(164,101,249,.27);
      background:rgba(22,17,40,.73); border-radius:15px; margin-bottom:.32rem}
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:5px; background:rgba(13,9,26,.7);
      border:1px solid rgba(164,101,249,.16); border-radius:18px; padding:6px}
    div[data-testid="stTabs"] button {border-radius:12px; font-weight:700; color:#C3B4DC}
    div[data-testid="stTabs"] button[aria-selected="true"] {
       color:#F8F3FF; background:linear-gradient(105deg,#5A189A,#7C3AED);
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {display:none}
    button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
      background:linear-gradient(110deg,#7C3AED,#C026D3)!important;
      border:1px solid rgba(250,180,255,.35)!important;
      color:white!important; font-weight:750!important;
      border-radius:12px!important;
    }
    button[kind="secondary"] {border-radius:12px!important}
    .hero {border:1px solid rgba(187,121,255,.34); border-radius:25px;
       padding:35px 39px 31px; margin-bottom:22px;
       background:radial-gradient(circle at 93% 7%,rgba(242,73,195,.24),transparent 31%),
              linear-gradient(110deg,rgba(74,29,118,.75),rgba(20,13,40,.98) 67%);
       box-shadow:0 17px 55px rgba(4,1,16,.22)}
    .hero-kicker {font-size:.72rem; letter-spacing:.23em; color:#E7BAFF;
        font-weight:850; margin-bottom:10px}
    .hero h1 {font-size:clamp(2.3rem,6vw,4.5rem)!important; margin:0!important;
       line-height:1.05; font-weight:900;
       background:linear-gradient(92deg,#FFF 2%,#E7C4FF 46%,#D99AFF 78%,#FF9EDB);
       -webkit-background-clip:text; -webkit-text-fill-color:transparent}
    .hero-signature {font-size:.76rem;color:#BBA6D2;letter-spacing:.045em;margin-top:7px;font-weight:500}
    .hero-sub {font-size:1.07rem;color:#D8CAE9;margin:13px 0 0}
    /* Se conservan todos los fondos oscuros originales. Solo se destaca la tipografía. */
    [class*="st-key-efg_triserie_"] div[data-testid="stExpander"],
    [class*="st-key-efg_superserie_"] div[data-testid="stExpander"] {
      background:rgba(22,17,40,.73)!important;
      border:1px solid rgba(164,101,249,.27)!important;
      box-shadow:none!important;
    }
    [class*="st-key-efg_triserie_"] div[data-testid="stExpander"] summary p,
    [class*="st-key-efg_triserie_"] div[data-testid="stExpander"] summary span {
      color:#53EFFF!important;font-weight:850!important;
      text-shadow:0 0 13px rgba(34,211,238,.28);
    }
    [class*="st-key-efg_superserie_"] div[data-testid="stExpander"] summary p,
    [class*="st-key-efg_superserie_"] div[data-testid="stExpander"] summary span {
      color:#FF85F4!important;font-weight:850!important;
      text-shadow:0 0 13px rgba(236,72,227,.28);
    }
    .efg-legend {display:flex;flex-wrap:wrap;gap:9px;margin:2px 0 17px;}
    .efg-legend-item {padding:7px 11px;border:1px solid rgba(190,169,218,.22);
       border-radius:100px;font-size:.79rem;font-weight:850;background:rgba(22,17,40,.73)}
    .efg-legend-tri {color:#53EFFF;border-color:rgba(34,211,238,.48)}
    .efg-legend-ss {color:#FF85F4;border-color:rgba(217,70,239,.48)}
    .efg-legend-uni {color:#F2E9FF}
    /* Vista compacta de rutina, optimizada para consultar en el gimnasio */
    .quick-group {margin:0 0 13px;padding:11px 12px 9px;border-radius:16px;
        border:1px solid rgba(192,165,231,.22);background:rgba(22,17,40,.76)}
    .quick-group.triserie, .quick-group.superserie {
        background:rgba(22,17,40,.76);border-color:rgba(192,165,231,.22)}
    .quick-group-title {font-size:.80rem;font-weight:900;letter-spacing:.11em;
        text-transform:uppercase;color:#F4E6FF;padding:0 8px 7px}
    .quick-group.triserie .quick-group-title {color:#53EFFF;
        text-shadow:0 0 12px rgba(34,211,238,.30)}
    .quick-group.superserie .quick-group-title {color:#FF85F4;
        text-shadow:0 0 12px rgba(236,72,227,.30)}
    .quick-group.triserie .quick-ex {color:#53EFFF;font-weight:900}
    .quick-group.superserie .quick-ex {color:#FF85F4;font-weight:900}
    .quick-group.triserie .quick-num {color:#53EFFF}
    .quick-group.superserie .quick-num {color:#FF85F4}
    .quick-cols {display:grid;grid-template-columns:minmax(0,2.3fr) minmax(70px,.65fr) minmax(95px,1fr);
        gap:10px;align-items:center;padding:5px 9px;color:#B4A8C6;
        font-size:.72rem;font-weight:700;letter-spacing:.04em}
    .quick-row {display:grid;grid-template-columns:minmax(0,2.3fr) minmax(70px,.65fr) minmax(95px,1fr);
        align-items:center;gap:10px;padding:10px 9px;border-radius:9px;
        background:rgba(11,10,27,.32);margin-bottom:4px}
    .quick-ex {min-width:0;font-size:.93rem;line-height:1.23;font-weight:800;color:#FCF8FF;overflow-wrap:anywhere}
    .quick-num {color:#BDA0DD;padding-right:6px;font-size:.77rem}
    .quick-note {font-size:.73rem;font-weight:500;color:#BAACCD;margin-top:4px;line-height:1.35}
    .quick-count {font-size:.99rem;font-weight:850;color:#F5E7FF;white-space:normal}
    .quick-plan {font-size:.80rem;color:#BEAAD9;font-weight:650;line-height:1.35}
    .quick-actual {font-size:.86rem;color:#B4FAEB;font-weight:850;line-height:1.3;
      margin-top:5px;overflow-wrap:anywhere}
    .quick-actual-date {font-size:.69rem;color:#A8D7CC;font-weight:500}
    .quick-load {font-size:.87rem;font-weight:800;color:#B4FAEB;overflow-wrap:anywhere}
    .quick-muted {color:#B6A6CA;font-weight:600}
    .quick-loading-note {color:#BAACCD;font-size:.71rem;line-height:1.35;font-weight:500;margin-top:4px}
    @media(max-width:640px) {
      .quick-row {grid-template-columns:minmax(62px,.68fr) minmax(110px,1fr);gap:5px 8px}
      .quick-ex {grid-column:1/-1;font-size:.93rem}
      .quick-cols {grid-template-columns:1fr 1fr}
      .quick-cols span:first-child {display:none}
      .quick-count {font-size:.95rem}
      .quick-load {font-size:.85rem}
      .quick-group {padding:9px 8px}
    }
    .pill {display:inline-block;background:rgba(124,58,237,.22);
       color:#D8B6FF; border:1px solid rgba(186,114,253,.32);
       font-size:.72rem;font-weight:800;letter-spacing:.04em;
       padding:5px 10px;border-radius:100px;margin-right:7px}
    .muted {color:#AA9FBF; font-size:.91rem}
    .status {border-radius:15px; padding:13px 16px; background:rgba(65,35,94,.24);
       border:1px solid rgba(175,119,245,.22); font-size:.87rem;color:#D6C7E8}
    .mini-title {font-size:.72rem;letter-spacing:.15em;text-transform:uppercase;
      color:#E6B3FF;font-weight:850}
    .finish {background:linear-gradient(115deg,rgba(79,46,141,.38),rgba(15,16,35,.8));
      border:1px solid rgba(184,125,254,.24);padding:19px 23px;border-radius:17px}
    @media(max-width:640px) {
      .block-container {padding:1rem .85rem 2.5rem}
      .hero {padding:24px 22px;border-radius:19px}
      .hero-sub {font-size:.92rem}
      [data-testid="stMetricValue"] {font-size:1.37rem}
      div[data-testid="stTabs"] button {font-size:.79rem;padding:0 7px}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError, AttributeError, RuntimeError):
        return ""


def fetch_remote(path: str, token: str = "") -> tuple[dict, str]:
    token = token or secret("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        f"{API}/{path}",
        headers=headers,
        params={"ref": BRANCH},
        timeout=13,
    )
    response.raise_for_status()
    body = response.json()
    raw = base64.b64decode(body["content"]).decode("utf-8")
    return json.loads(raw), body["sha"]


@st.cache_data(ttl=45, show_spinner=False)
def public_history() -> dict:
    try:
        result, _ = fetch_remote("data/history.json")
        return result if isinstance(result.get("sessions"), list) else {"sessions": []}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        # La copia publicada contiene registros reales; nunca se reemplazan por datos inventados.
        cached = json.loads((Path(__file__).resolve().parent / "data" / "history.json").read_text(encoding="utf-8"))
        return dict(cached, _offline=True, _snapshot=True)


@st.cache_data(ttl=45, show_spinner=False)
def public_apple_watch() -> dict:
    try:
        data, _ = fetch_remote("data/apple_watch.json")
        return data if isinstance(data.get("workouts"), list) else {"workouts": [], "_offline": True}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {"workouts": [], "_offline": True}


@st.cache_data(ttl=45, show_spinner=False)
def public_walks() -> dict:
    """Caminatas de capturas, sin conexión con Apple Watch ni datos de fuerza."""
    try:
        data, _ = fetch_remote("data/walks.json")
        if isinstance(data.get("walks"), list):
            return data
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    # Copia local: la web sigue mostrando los registros ya publicados.
    try:
        path = Path(__file__).resolve().parent / "data" / "walks.json"
        cached = json.loads(path.read_text(encoding="utf-8"))
        return dict(cached, _offline=True)
    except (OSError, ValueError, KeyError, TypeError):
        return {"walks": [], "_offline": True}


@st.cache_data(ttl=45, show_spinner=False)
def public_weight() -> dict:
    try:
        data, _ = fetch_remote("data/weight.json")
        if isinstance(data.get("measurements"), list):
            return data
        return {"measurements": [], "_offline": True}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {"measurements": [], "_offline": True}


def persist_remote(path: str, payload: dict, token: str, message: str) -> None:
    if not token:
        raise ValueError("Falta configurar GITHUB_TOKEN en los Secrets de Streamlit.")
    _, sha = fetch_remote(path, token)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    response = requests.put(
        f"{API}/{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "sha": sha,
            "branch": BRANCH,
        },
        timeout=18,
    )
    if response.status_code not in (200, 201):
        if response.status_code in (401, 403):
            raise ValueError("El token no autoriza la escritura. Revisá permisos de Contents.")
        if response.status_code in (409, 422):
            raise ValueError("Hubo otro cambio en el repositorio. Actualizá y volvé a guardar.")
        raise ValueError(f"GitHub no guardó el cambio (HTTP {response.status_code}).")


@st.cache_data
def load_plan_local() -> list[dict]:
    path = Path(__file__).resolve().parent / "data" / "plan.json"
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


@st.cache_data(ttl=45, show_spinner=False)
def public_legacy_plan() -> list[dict]:
    """Mostrar el plan publicado en GitHub sin esperar a un redepliegue.

    Ante fallas de red, usar la última versión empaquetada con la app.
    """
    try:
        data, _ = fetch_remote("data/plan.json")
        if isinstance(data.get("entries"), list) and data["entries"]:
            return data["entries"]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return load_plan_local()


@st.cache_data(ttl=45, show_spinner=False)
def public_plan() -> list[dict]:
    try:
        data, _ = fetch_remote("data/active_plan.json")
        if isinstance(data.get("entries"), list) and data["entries"]:
            return data["entries"]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return json.loads((Path(__file__).resolve().parent / "data" / "active_plan.json").read_text(encoding="utf-8"))["entries"]


def parse_count(value: str, fallback: int = 3) -> int:
    found = re.search(r"\d+", str(value))
    return max(1, min(12, int(found.group()) if found else fallback))


def suggested_reps(value: str, n: int) -> list[int]:
    # "12-10-8-8" = valores por serie; "10/12" = rango, no dos series.
    raw = str(value)
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if len(nums) == n and "-" in raw:
        return nums
    return [nums[0] if nums else 8] * n


def fmt(v, decimal: int = 2) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.{decimal}f}".replace(",", "·").replace(".", ",").replace("·", ".")


def weekly_report_weight(exercise: dict, unit: str = "lb") -> tuple[str, str] | None:
    """Carga declarada en el seguimiento de ESA semana, sin heredar otra semana."""
    report = exercise.get("weekly_report")
    if not isinstance(report, dict):
        return None
    factor = 1.0 if unit == "lb" else 0.45359237
    sequence = report.get("series_lb")
    try:
        if isinstance(sequence, list) and sequence:
            values = [float(v) for v in sequence]
        elif report.get("lb") is not None:
            values = [float(report["lb"])]
        else:
            return None
        if not values or any(not math.isfinite(v) or v < 0 for v in values):
            return None
    except (TypeError, ValueError):
        return None
    amounts = " / ".join(fmt(v * factor, 1).removesuffix(",0") for v in values)
    scope = str(report.get("scope", "")).strip()
    label = f"{amounts} {unit}" + (f" · {scope}" if scope else "")
    raw_date = str(report.get("date", ""))
    try:
        shown_date = date.fromisoformat(raw_date).strftime("%d/%m/%Y")
    except ValueError:
        shown_date = "fecha no indicada"
    context = f"Seguimiento registrado · {shown_date}"
    if len(values) > 1:
        context += f" · máximo {fmt(max(values) * factor, 1).removesuffix(',0')} {unit}"
    return label, context


def planned_load_text(exercise: dict, unit: str = "lb") -> str | None:
    """Carga de REFERENCIA, no máximo real ni sesión efectivamente realizada."""
    load = exercise.get("planned_load")
    if not isinstance(load, dict):
        return None
    if load.get("kind") == "bodyweight":
        return "Peso corporal"
    try:
        pounds = float(load["lb"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(pounds) or pounds < 0:
        return None
    value = pounds if unit == "lb" else pounds * 0.45359237
    text = f"{fmt(value, 1).removesuffix(',0')} {unit}"
    scope = load.get("scope")
    if scope == "por_lado_y_barra":
        return f"{text}/lado + barra"
    if scope == "por_mancuerna":
        return f"{text}/mancuerna"
    if scope == "mancuernas_sin_desglosar":
        return f"{text} · mancuernas*"
    return text


def monthly_maximum_weights(
    plan: list[dict], sessions: list[dict], as_of: date | None = None
) -> dict[str, dict]:
    """Máximo móvil con cargas comparables, incluyendo reportes parciales.

    '180 lb por lado + barra' se conserva como 180 lb/lado: nunca se
    convierte en la carga total ni se suma una barra de peso desconocido.
    Una serie con carga ausente no aporta kg ficticios.
    """
    # Local para que la verificación CI pueda aislar y ejecutar la función
    # sin importar Streamlit ni depender de otros símbolos de app.py.
    def normalize_scope(scope: str) -> str:
        value = str(scope or "").casefold()
        if "por lado" in value:
            return "por_lado_y_barra"
        if "mancuerna" in value:
            return "mancuernas_sin_desglosar"
        if "peso corporal" in value:
            return "peso_corporal"
        if "disco" in value:
            return "disco"
        if "polea" in value:
            return "polea"
        if "máquina" in value or "maquina" in value:
            return "maquina"
        return "carga_externa"

    current = as_of or date.today()
    window_start = current - timedelta(days=29)
    recent: dict[str, list[dict]] = {}
    historical: dict[str, list[dict]] = {}

    def add(target, exercise, raw_kg, scope, source, when):
        name = " ".join(str(exercise).strip().casefold().split())
        try:
            amount = float(raw_kg)
        except (TypeError, ValueError):
            return
        if not name or not math.isfinite(amount) or amount < 0 or amount > 1500:
            return
        target.setdefault(name, []).append({
            "kg": amount, "scope": normalize_scope(scope),
            "source": source, "date": when,
        })

    for ex in plan:
        name = ex.get("exercise", "")
        if int(ex.get("week", 0)) == 1:
            # Referencia sin fecha: solo se utilizará si no hay carga fechada reciente.
            initial_series = ex.get("reference_series_kg")
            if isinstance(initial_series, list) and initial_series:
                for value in initial_series:
                    add(historical, name, value, "", "excel_inicial", None)
            elif ex.get("reference_weight_kg") is not None:
                add(historical, name, ex.get("reference_weight_kg"), "", "excel_inicial", None)
        report = ex.get("weekly_report")
        if not isinstance(report, dict):
            continue
        try:
            reported_day = date.fromisoformat(str(report.get("date", "")))
        except (TypeError, ValueError):
            continue
        if not window_start <= reported_day <= current:
            continue
        pounds = report.get("series_lb")
        if not isinstance(pounds, list) or not pounds:
            pounds = [report.get("lb")]
        for value in pounds:
            try:
                converted = float(value) * 0.45359237
            except (TypeError, ValueError):
                continue
            add(recent, name, converted, report.get("scope"), "seguimiento", reported_day)

    for session in sessions:
        if not isinstance(session, dict):
            continue
        try:
            recorded_day = date.fromisoformat(str(session.get("date", "")))
        except (TypeError, ValueError):
            continue
        if not window_start <= recorded_day <= current:
            continue
        name = session.get("exercise", "")
        reported_lb = session.get("reported_load_lb")
        if reported_lb is not None:
            try:
                kg = float(reported_lb) * 0.45359237
            except (TypeError, ValueError):
                continue
            add(recent, name, kg, session.get("load_scope"), "app", recorded_day)
        else:
            for series in session.get("sets", []):
                if isinstance(series, dict):
                    add(recent, name, series.get("kg"), series.get("load_scope"),
                        "app", recorded_day)

    result: dict[str, dict] = {}
    for name in set(historical) | set(recent):
        if recent.get(name):
            records = recent[name]
            # Si cambia la modalidad registrada, no comparar kg por lado con
            # kilogramos totales: elegimos la modalidad más reciente.
            newest = max(
                enumerate(records),
                key=lambda item: (item[1]["date"], item[1]["source"] == "app", item[0]),
            )[1]
            comparable = [item for item in records if item["scope"] == newest["scope"]]
            result[name] = max(comparable, key=lambda item: item["kg"])
        elif historical.get(name):
            result[name] = max(historical[name], key=lambda item: item["kg"])
    return result

def plot_layout(fig, height=370):
    fig.update_layout(
        height=height,
        margin=dict(l=5, r=10, t=24, b=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial", color=TEXT, size=13),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(color=MUTED)),
        yaxis=dict(gridcolor="rgba(180,140,233,.12)", zeroline=False,
                   tickfont=dict(color=MUTED)),
        hoverlabel=dict(bgcolor="#25163F", font_color="#FFFFFF"),
        showlegend=False,
    )
    return fig


def series_rows(sessions):
    all_rows = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        try:
            event_date = date.fromisoformat(str(session.get("date", "")))
        except ValueError:
            continue
        for pos, item in enumerate(session.get("sets", []), start=1):
            if scope_key(item.get("load_scope") or session.get("load_scope", "")) not in ("Carga total externa", "Máquina o polea", "Disco"):
                continue
            if session.get("duration_unit") == "seconds" or session.get("exercise") == "Plancha común":
                continue
            try:
                weight = float(item.get("kg", 0))
                reps = int(item.get("reps", 0))
            except (ValueError, TypeError):
                continue
            if not math.isfinite(weight) or weight < 0 or weight > 1500 or reps < 0 or reps > 10000:
                continue
            all_rows.append({
                "Fecha": event_date,
                "Bloque": block_of(session),
                "Semana del plan": int(session.get("week", 0)),
                "Día": DAY_NAMES[max(0, min(4, int(session.get("day", 1))-1))],
                "Ejercicio": str(session.get("exercise", "Sin nombre")),
                "Serie": pos,
                "Carga (kg)": round(weight, 3),
                "Repeticiones": reps,
                "Volumen": round(weight * reps, 2),
                "RIR": session.get("rir"),
                "Notas": session.get("notes", ""),
            })
    return pd.DataFrame(all_rows)


def announce(kicker, title, sub):
    st.markdown(
        f'<div class="hero"><div class="hero-kicker">{kicker}</div>'
        f'<h1>{title}</h1><div class="hero-signature">by EFG</div>'
        f'<div class="hero-sub">{sub}</div>'
        f'<div style="margin-top:18px"><span class="pill">5 DÍAS</span>'
        f'<span class="pill">12 SEMANAS</span>'
        f'<span class="pill">FUERZA + DATOS</span></div></div>',
        unsafe_allow_html=True,
    )


LEGACY_PLAN = public_legacy_plan()
PLAN = public_plan()
ALL_PLAN = LEGACY_PLAN + PLAN
PLAN_WEEKS = sorted({int(row['week']) for row in PLAN})
HISTORY = public_history()
WEIGHT = public_weight()
WATCH = public_apple_watch()
WATCH_WORKOUTS = WATCH.get("workouts", [])
WALKS = public_walks()
WALK_SESSIONS = WALKS.get("walks", [])
MEASUREMENTS = WEIGHT.get("measurements", [])
SESSIONS = HISTORY.get("sessions", [])
MONTHLY_MAX = monthly_maximum_weights(ALL_PLAN, SESSIONS)
DF = series_rows(view_sessions(SESSIONS))
TOKEN = secret("GITHUB_TOKEN")
ADMIN_PIN = secret("ADMIN_PIN")

announce(
    "EFG TRAINING  /  PERFORMANCE LAB  ·  V2.0",
    "LA CIENCIA<br>TAMBIÉN ENTRENA.",
    "Fuerza, método y datos para medir cada avance.",
)

tabs = st.tabs(["⚡ MI RUTINA", "📋 RUTINA RESUMEN", "⏱️ TEMPORIZADOR", "📊 PROGRESO", "⌚ APPLE WATCH", "🚶 CAMINATAS", "📚 HISTORIAL", "⚖️ PESO", "🔐 ADMIN", "🗃️ RUTINAS ANTIGUAS"])

with tabs[0]:
    st.markdown("### ⚡ Plan de entrenamiento")
    st.caption(ACTIVE_TITLE + " · Nuevo bloque · Semana 1 independiente del plan anterior")
    a, b = st.columns(2)
    a.metric("Días de entrenamiento", "05")
    b.metric("Semanas planificadas", f"{len(PLAN_WEEKS):02d}")
    st.markdown("")
    left, right = st.columns([1, 1])
    with left:
        week = st.selectbox("SEMANA", PLAN_WEEKS, format_func=lambda x: f"Semana {x}")
    with right:
        day = st.selectbox("DÍA", [1, 2, 3, 4, 5],
                          format_func=lambda x: f"Día {x} · {DAY_NAMES[x-1]}")
    chosen = [r for r in PLAN if int(r["week"]) == week and int(r["day"]) == day]
    st.caption(DAY_FOCUS[day] + " · Duración estimada: " + DAY_TIME[day])
    st.markdown(
        f'<div class="finish"><div class="mini-title">TU SESIÓN</div>'
        f'<h3 style="margin:3px 0 4px">SEMANA {week} · {DAY_NAMES[day-1].upper()}</h3>'
        f'<div class="muted">{len(chosen)} ejercicios · desplegá cualquiera para ver sus indicaciones</div></div>',
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(
        '<div class="efg-legend" aria-label="Código visual de los bloques">'
        '<span class="efg-legend-item efg-legend-tri">AZUL · Triserie</span>'
        '<span class="efg-legend-item efg-legend-ss">VIOLETA · Superserie</span>'
        '<span class="efg-legend-item efg-legend-uni">OSCURO · Individual</span>'
        '</div>', unsafe_allow_html=True,
    )
    st.caption("Core y movilidad: 2 vueltas, 10–15 s entre ejercicios y 30 s entre vueltas. Después, aproximaciones progresivas. Principal: 3 × 8–12 a RIR 2.")
    for index, ex in enumerate(chosen, 1):
        kind = ex.get("set_type", "individual")
        if kind not in ("individual", "superserie", "triserie"):
            kind = "individual"
        group = ex.get("set_group", "")
        type_label = "TRISERIE" if kind == "triserie" else "SUPERSERIE"
        group_tag = f"  ·  {type_label} {group}" if kind != "individual" else ""
        display_label = f"{index:02}. {ex['exercise']}  ·  {ex['series']} × {ex['repetitions']}{group_tag}"
        with st.container(key=f"efg_{kind}_{ex['id']}"):
            with st.expander(display_label):
                x, y, z = st.columns(3)
                x.metric("Series", ex["series"] or "—")
                y.metric("Repeticiones", ex["repetitions"] or "—")
                z.metric("Esfuerzo", ex["intensity"] or "—")
                st.caption("**Descanso:** " + ex.get("rest", "No indicado"))
                last_load, best_load = last_and_best(SESSIONS, ex["exercise"])
                if last_load:
                    st.caption("**Última sesión:** " + format_load(last_load) + " · " + last_load["date"].strftime("%d/%m/%Y"))
                    st.caption("**Mejor carga comparable:** " + format_load(best_load))
                if ex.get("pattern"):
                    st.caption(f"**Grupo / patrón:** {ex['pattern']}")
                if ex.get("block"):
                    st.caption(f"**Bloque:** {ex['block']}")
                if ex.get("notes"):
                    st.write(f"**Indicaciones:** {ex['notes']}")
                planned_load = planned_load_text(ex, "lb")
                report_load = weekly_report_weight(ex, "lb")
                if planned_load is not None:
                    st.info(
                        f"**Carga de referencia:** {planned_load}. "
                        "No corresponde a un registro de entrenamiento realizado."
                    )
                elif report_load:
                    load_text, load_context = report_load
                    st.info(f"**Carga de semana {week}:** {load_text}. {load_context}.")
                elif week == 1 and ex.get("reference_series_kg"):
                    string = " · ".join(f"{fmt(w, 1)} kg" for w in ex["reference_series_kg"])
                    st.info(f"Referencia inicial del Excel (semana 1): {string}.")
                elif week == 1 and ex.get("reference_weight_lb") is not None:
                    st.info(
                        f"Referencia inicial del Excel (semana 1): "
                        f"{fmt(ex.get('reference_weight_lb'), 1)} lb "
                        f"≈ {fmt(ex.get('reference_weight_kg'), 1)} kg."
                    )
                else:
                    st.caption("Carga de esta semana: todavía no confirmada en el seguimiento.")
                recorded = [
                    r for r in SESSIONS if r.get("exercise_id") == ex["id"]
                ]
                if recorded:
                    newest = sorted(recorded, key=lambda d: d.get("date", ""), reverse=True)[0]
                    st.caption(
                        "Última sesión real cargada: "
                        f"{newest.get('date')} · "
                        f"{len(newest.get('sets', []))} series"
                    )
    
    st.markdown("")
    st.caption("Doce semanas del nuevo bloque con la misma estructura inicial, sin cargas futuras inventadas. Al completar 12–12–12 a RIR 2, subí el menor salto disponible. Las referencias anteriores no se asignan automáticamente.")

with tabs[1]:
    st.markdown("### 📋 Rutina resumen")
    render_summary(PLAN, SESSIONS, LEGACY_PLAN, prefix="quick")
    if HISTORY.get("_offline"):
        st.warning("No se pudo actualizar el historial online. Se muestra la copia real incluida en la última publicación; pueden faltar registros posteriores.")


with tabs[2]:
    render_rest_timer()


with tabs[3]:
    st.markdown("### 📊 Tu evolución, en números")
    render_plan_charts(PLAN)
    st.divider()
    st.markdown("### 📈 Rendimiento registrado")
    if HISTORY.get("_offline"):
        st.warning("No se pudo consultar el historial online. Los registros pueden no estar actualizados.")
    if DF.empty:
        st.markdown(
            '<div class="status">Todavía no hay sesiones reales guardadas. '
            'Los gráficos de progreso aparecerán al cargar los primeros entrenamientos. '
            'Mientras tanto, estas son las referencias originales de la rutina.</div>',
            unsafe_allow_html=True,
        )
        render_exercise_progress(SESSIONS, ALL_PLAN, plot_layout, prefix="progress_empty")
        x, y, z = st.columns(3)
        x.metric("Sesiones registradas", len(SESSIONS))
        y.metric("Series realizadas", 0)
        z.metric("Volumen acumulado", "—")
        refs = [
            r for r in PLAN if r["week"] == 1 and
            isinstance(r.get("reference_weight_kg"), (int, float)) and
            r["reference_weight_kg"] > 0
        ]
        if refs:
            refs = sorted(refs, key=lambda r: r["reference_weight_kg"], reverse=True)[:12]
            fig = go.Figure(go.Bar(
                x=[x["reference_weight_kg"] for x in refs],
                y=[x["exercise"] for x in refs],
                orientation="h",
                marker=dict(color=[PURPLE if i % 2 == 0 else PINK for i in range(len(refs))],
                            line=dict(color="#D9B9FF", width=.35)),
                text=[f"{fmt(x['reference_weight_kg'])} kg" for x in refs],
                textposition="outside",
            ))
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="kg")
            st.markdown("#### Cargas de referencia de tu Excel · Semana 1")
            st.plotly_chart(plot_layout(fig, max(450, 30 * len(refs))), use_container_width=True,
                            config={"displayModeBar": False})
            st.caption("Estos pesos NO son estadísticas de entrenamientos realizados.")
    else:
        dates = pd.to_datetime(DF["Fecha"])
        week_start = (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.date
        DF["Semana calendario"] = week_start.astype(str)
        sessions_count = len({r.get("date") for r in SESSIONS})
        confirmed_sets = sum(
            1 for session in SESSIONS if isinstance(session, dict)
            for item in session.get("sets", [])
            if isinstance(item, dict) and isinstance(item.get("reps"), int)
        )
        confirmed_exercises = len({
            str(session.get("exercise", "")).strip()
            for session in SESSIONS if isinstance(session, dict)
            and any(isinstance(item, dict) and isinstance(item.get("reps"), int)
                    for item in session.get("sets", []))
        })
        vol = DF["Volumen"].sum()
        a, b, c, d = st.columns(4)
        a.metric("Días entrenados", sessions_count)
        b.metric("Series confirmadas", confirmed_sets)
        c.metric("Volumen calculable", f"{fmt(vol, 0)} kg·rep")
        d.metric("Ejercicios con repeticiones", confirmed_exercises)
        st.caption(
            "El volumen es parcial: solo incluye series con carga total cuantificada y "
            "repeticiones confirmadas. El detalle completo, incluso cargas por lado "
            "y datos incompletos, está en HISTORIAL."
        )

        by_week = DF.groupby("Semana calendario").agg(
            Volumen=("Volumen", "sum"),
            Series=("Serie", "count"),
            Reps=("Repeticiones", "sum"),
        ).reset_index().sort_values("Semana calendario")
        st.markdown("#### 📈 Volumen por semana")
        fig = go.Figure(go.Bar(
            x=by_week["Semana calendario"],
            y=by_week["Volumen"],
            marker=dict(color=[PURPLE, PINK, CYAN, VIOLET] * (len(by_week)//4+1),
                        line=dict(width=0)),
            text=[fmt(v,0) for v in by_week["Volumen"]],
            textposition="outside",
        ))
        fig.update_layout(yaxis_title="kg × repeticiones")
        st.plotly_chart(plot_layout(fig), use_container_width=True, config={"displayModeBar":False})

        st.markdown("#### 💪 Evolución por ejercicio")
        render_exercise_progress(SESSIONS, ALL_PLAN, plot_layout, prefix="progress")
        st.markdown("#### Resumen semanal")
        show = by_week.rename(columns={
            "Semana calendario":"Semana (lunes)", "Volumen":"Volumen (kg·rep)"
        })
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(
            "Volumen = carga externa × repeticiones. No representa fuerza máxima ni incorpora "
            "peso corporal, cargas bilaterales/unilaterales equivalentes o isométricos. "
            "Compará el mismo ejercicio y condiciones."
        )
        render_calendar(SESSIONS)

with tabs[4]:
    render_watch_dashboard(
        WATCH_WORKOUTS, offline=bool(WATCH.get("_offline")),
        plot_layout=plot_layout,
    )


with tabs[5]:
    render_walks_dashboard(WALK_SESSIONS, offline=bool(WALKS.get("_offline")))


with tabs[6]:
    st.markdown("### 📚 Historial y evolución de fuerza")
    render_session_detail(SESSIONS)
    st.divider()
    st.markdown("#### Evolución con registros de ambos bloques")
    render_exercise_progress(SESSIONS, ALL_PLAN, plot_layout, prefix="history")
    st.download_button("Descargar historial completo sin modificar", json.dumps(HISTORY, ensure_ascii=False, indent=2), "efg_historial_completo.json", "application/json", key="history_json")
    if not DF.empty:
        st.download_button("Descargar series con carga total cuantificada", DF.to_csv(index=False).encode("utf-8-sig"), "efg_series_cuantificadas.csv", "text/csv", key="history_csv")
    with st.expander("Reportes y referencias de la rutina anterior"):
        rows = []
        for e in LEGACY_PLAN:
            report = e.get("weekly_report")
            if isinstance(report, dict):
                rows.append({"Semana":e["week"], "Día":e["day_label"], "Ejercicio":e["exercise"], "Fecha":report.get("date"), "Carga lb":report.get("lb"), "Cargas por serie lb":str(report.get("series_lb", "")), "Condición":report.get("scope", "")})
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption("Las referencias sin fecha y el resumen completo están en Rutinas antiguas. Ninguna referencia se convierte en sesión realizada.")
    st.download_button("Descargar nuevo plan de 12 semanas", pd.DataFrame(PLAN).to_csv(index=False).encode("utf-8-sig"), "efg_nuevo_plan_12_semanas.csv", "text/csv", key="new_plan_csv")


with tabs[7]:
    st.markdown("### ⚖️ Evolución del peso corporal")
    st.caption("Mediciones reales, registradas por fecha y visibles para todos.")
    if WEIGHT.get("_offline"):
        st.warning("No se pudieron actualizar las mediciones desde GitHub.")
    render_weight_chart(MEASUREMENTS)


with tabs[8]:
    st.markdown("### 🔐 Panel de administración")
    st.caption("La aplicación es pública. Este panel requiere tu PIN para guardar o modificar.")

    if not (TOKEN and ADMIN_PIN):
        st.warning(
            "El acceso de edición todavía no está habilitado. Falta configurar "
            "ADMIN_PIN y GITHUB_TOKEN en los Secrets de Streamlit Cloud. "
            "Hasta entonces, toda la aplicación es de solo lectura."
        )
    else:
        st.session_state.setdefault("efg_admin_ok", False)
        st.session_state.setdefault("efg_failed", 0)
        st.session_state.setdefault("efg_locked_until", 0.0)
        if not st.session_state["efg_admin_ok"]:
            now = time.time()
            if now < st.session_state["efg_locked_until"]:
                st.error("Demasiados intentos. Volvé a intentar dentro de unos minutos.")
            else:
                entered = st.text_input("PIN de administrador", type="password",
                                        max_chars=40, key="efg_pin_input")
                if st.button("🔓 Desbloquear edición", type="primary"):
                    if hmac.compare_digest(entered, ADMIN_PIN):
                        st.session_state["efg_admin_ok"] = True
                        st.session_state["efg_failed"] = 0
                        st.rerun()
                    else:
                        st.session_state["efg_failed"] += 1
                        if st.session_state["efg_failed"] >= 5:
                            st.session_state["efg_locked_until"] = time.time() + 300
                            st.session_state["efg_failed"] = 0
                            st.error("Cinco intentos fallidos. Acceso bloqueado 5 minutos en esta sesión.")
                        else:
                            st.error("PIN incorrecto.")
        else:
            left, right = st.columns([3, 1])
            left.success("Acceso de administrador activo en esta sesión.")
            with right:
                if st.button("Cerrar sesión", use_container_width=True):
                    st.session_state["efg_admin_ok"] = False
                    st.rerun()

            edit_tabs = st.tabs(["🏋️ Cargar entrenamiento", "✏️ Editar rutina", "⚖️ Peso corporal"])
            with edit_tabs[0]:
                col1, col2, col3 = st.columns(3)
                with col1:
                    edit_week = st.selectbox("Semana del plan", PLAN_WEEKS,
                                             key="edit_week")
                with col2:
                    edit_day = st.selectbox("Día", [1,2,3,4,5],
                                            format_func=lambda x:DAY_NAMES[x-1],
                                            key="edit_day")
                with col3:
                    edit_date = st.date_input("Fecha", date.today(),
                                              format="DD/MM/YYYY", key="edit_date")
                choices = [
                    x for x in PLAN if x["week"]==edit_week and x["day"]==edit_day
                ]
                selected = st.selectbox(
                    "Ejercicio a registrar", range(len(choices)),
                    format_func=lambda i:f"{i+1:02}. {choices[i]['exercise']}",
                    key="register_exercise",
                )
                ex = choices[selected]
                st.caption("Registro del bloque nuevo. Las cargas previas son solo referencia y no se precargan.")
                ident = f"{edit_date.isoformat()}|{ex['id']}"
                previous = next((s for s in SESSIONS if s.get("id")==ident), None)
                previous_sets = previous.get("sets", []) if isinstance(previous, dict) else []
                if not isinstance(previous_sets, list):
                    previous_sets = []
                recorded_count = len(previous_sets)
                planned_count = parse_count(ex["series"])
                # La rutina es una referencia; las series ejecutadas pueden diferir.
                # Esta selección se hace fuera del formulario para crear o quitar
                # inmediatamente los campos de las series reales.
                series_count = st.number_input(
                    "Cantidad de series REALIZADAS",
                    min_value=1, max_value=12,
                    value=max(1, min(12, recorded_count or planned_count)),
                    step=1,
                    key=f"register_sets_{ex['id']}_{edit_date.isoformat()}",
                    help="Podés registrar más o menos series que las programadas "
                         "sin modificar la rutina original.",
                )
                # Mantener el esquema previsto (p. ej., 12-10-8-8)
                # aunque el registro tenga más o menos series.
                reps_plan = suggested_reps(ex["repetitions"], planned_count)
                if series_count > len(reps_plan):
                    reps_plan.extend([reps_plan[-1]] * (series_count - len(reps_plan)))
                reps_plan = reps_plan[:series_count]
                st.caption(
                    f"Plan: {ex['series']} series · {ex['repetitions']} repeticiones "
                    f"· {ex['intensity'] or 'sin RIR indicado'} "
                    f"| Registro: {series_count} series efectivamente realizadas."
                )
                if recorded_count and series_count < recorded_count:
                    st.warning(
                        f"Esta sesión ya tiene {recorded_count} series guardadas. "
                        f"Si ahora guardás {series_count}, las últimas "
                        f"{recorded_count - series_count} se eliminarán del registro. "
                        "Confirmá este cambio abajo para continuar."
                    )
                units = st.radio("Unidad de carga", ["kg", "lb"], horizontal=True, key="register_units")
                scope_options = ["Carga total externa", "Máquina o polea", "Disco", "Por mancuerna", "Por lado · barra o plataforma aparte", "Lastre externo", "Peso corporal", "Alcance sin confirmar"]
                initial_scope = scope_key(previous.get("load_scope", "") if previous else ex.get("load_scope", ""))
                load_condition = st.selectbox("Condición de la carga registrada", scope_options, index=scope_options.index(initial_scope), key=f"register_scope_{ex['id']}_{edit_date.isoformat()}", help="Si anotás peso por lado o por mancuerna, no lo sumamos como carga total. Las condiciones tienen curvas separadas.")
                with st.form("register_session_form", clear_on_submit=False):
                    new_sets = []
                    for i in range(series_count):
                        prior_sets = previous.get("sets") if previous else None
                        oldset = (prior_sets[i] if isinstance(prior_sets, list)
                                  and i < len(prior_sets) and isinstance(prior_sets[i], dict)
                                  else None)
                        # Una carga total desconocida se almacena como None,
                        # no como cero. Ej.: peso por lado conocido, barra sin pesar.
                        raw_kg = (oldset.get("kg") if oldset.get("kg") is not None else (oldset.get("load_lb") * 0.45359237 if oldset.get("load_lb") is not None else None)) if oldset else None
                        try:
                            stored_kg = float(raw_kg) if raw_kg is not None else None
                            if stored_kg is not None and (
                                not math.isfinite(stored_kg) or stored_kg < 0
                            ):
                                stored_kg = None
                        except (TypeError, ValueError):
                            stored_kg = None
                        weight = stored_kg if stored_kg is not None else 0.0
                        if units == "lb":
                            weight /= 0.45359237
                        try:
                            old_reps = int(oldset.get("reps_per_side", oldset.get("reps"))) if oldset else reps_plan[i]
                        except (TypeError, ValueError):
                            old_reps = reps_plan[i]
                        a, b, c = st.columns([.5,1.35,1.35])
                        a.markdown(f"**S{i+1}**")
                        with b:
                            missing_load = st.checkbox(
                                f"Carga no informada · S{i+1}",
                                value=oldset is not None and stored_kg is None,
                                key=f"pending_{ex['id']}_{edit_date.isoformat()}_{i}",
                                help="Usá esta opción si no se conoce la carga de la serie. No se guarda un cero ficticio.",
                            )
                            loaded = st.number_input(
                                f"Carga ({units}) · S{i+1}", 0.0, 1500.0,
                                value=round(weight,2), step=2.5,
                                help="Si marcás «Carga no informada», este valor "
                                     "no se guardará hasta que confirmes la carga real.",
                                key=f"weight_{ex['id']}_{edit_date.isoformat()}_{units}_{i}",
                            )
                        with c:
                            rep = st.number_input(
                                f"{'Segundos' if ex.get('duration_unit') == 'seconds' else ('Reps por lado' if ex.get('repetitions_per_side') else 'Reps')} · S{i+1}", 0, 10000,
                                value=max(0, min(10000, old_reps)),
                                step=1, key=f"reps_{ex['id']}_{edit_date.isoformat()}_{i}",
                            )
                        # Mantener metadatos de registros ya cargados
                        # (alcance de carga, fuente y notas de cada serie).
                        row = dict(oldset) if oldset else {}
                        row["kg"] = (
                            None if missing_load or load_condition not in ("Carga total externa", "Máquina o polea", "Disco", "Peso corporal") else
                            round(loaded * (0.45359237 if units=="lb" else 1.0), 3)
                        )
                        row["reps"] = int(rep) * (2 if ex.get("repetitions_per_side") else 1)
                        if ex.get("repetitions_per_side"):
                            row["reps_per_side"] = int(rep)
                        row["load_scope"] = load_condition
                        if missing_load:
                            row.pop("load_lb", None)
                        else:
                            row["load_lb"] = round(
                                loaded if units == "lb" else loaded / 0.45359237, 2
                            )
                        new_sets.append(row)
                    effort = st.selectbox(
                        "RIR real (opcional)", ["No registrado",0,1,2,3,4,5],
                        index=(["No registrado",0,1,2,3,4,5].index(previous.get("rir")) if previous and previous.get("rir") in [0,1,2,3,4,5] else 0), key=f"register_rir_{ex['id']}_{edit_date.isoformat()}",
                    )
                    note = st.text_area(
                        "Observaciones (opcional)",
                        value=previous.get("notes","") if previous else "",
                        key=f"register_notes_{ex['id']}_{edit_date.isoformat()}",
                    )
                    confirm_series_reduction = (
                        st.checkbox(
                            "Confirmo que quiero eliminar las series sobrantes "
                            "del registro anterior.",
                            key=f"confirm_reduce_{ex['id']}_{edit_date.isoformat()}",
                        )
                        if recorded_count and series_count < recorded_count
                        else False
                    )
                    submitted = st.form_submit_button(
                        "💾 GUARDAR ENTRENAMIENTO", type="primary",
                        use_container_width=True,
                    )

                if submitted:
                    if not new_sets:
                        st.error("No hay series para guardar.")
                    elif recorded_count and series_count < recorded_count and not confirm_series_reduction:
                        st.error("Confirmá primero la eliminación de las series guardadas.")
                    else:
                        try:
                            latest, _ = fetch_remote("data/history.json", TOKEN)
                            other = [s for s in latest.get("sessions", [])
                                     if s.get("id") != ident]
                            # Conservar el contexto original de cargas parciales:
                            # lb por lado, barra de peso desconocido y procedencia.
                            existing = next((s for s in latest.get("sessions", [])
                                             if s.get("id") == ident), None)
                            updated = dict(existing) if isinstance(existing, dict) else {}
                            updated.update({
                                "id":ident,
                                "date":edit_date.isoformat(),
                                "week":edit_week,
                                "day":edit_day,
                                "exercise_id":ex["id"],
                                "block_id": ACTIVE_BLOCK_ID,
                                "duration_unit": ex.get("duration_unit", "reps"),
                                "exercise":ex["exercise"],
                                "sets":new_sets,
                                "rir":None if effort=="No registrado" else int(effort),
                                "notes":note[:900],
                                "load_scope": load_condition,
                                "saved_at":datetime.now(timezone.utc).isoformat(),
                            })
                            other.append(updated)
                            persist_remote(
                                "data/history.json",
                                dict(latest, sessions=other),
                                TOKEN,
                                f"EFG Training: registrar {ex['exercise']} {edit_date.isoformat()}",
                            )
                            public_history.clear()
                            # No forzar st.rerun(): ese reinicio hacía volver
                            # a la pestaña "Mi rutina", abandonando ADMIN.
                            st.success(
                                f"✅ Entrenamiento GUARDADO en GitHub: "
                                f"{ex['exercise']} · {edit_date.strftime('%d/%m/%Y')} "
                                f"· {len(new_sets)} series. "
                                "Podés seguir cargando ejercicios desde ADMIN."
                            )
                        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                            st.error(f"No se pudo guardar: {error}")

            with edit_tabs[1]:
                st.caption(
                    "Editá la rutina y publicá los cambios en GitHub. "
                    "Se actualiza la vista de la app sin esperar un nuevo despliegue."
                )
                modify_week = st.selectbox("Semana", PLAN_WEEKS, key="modify_week")
                modify_day = st.selectbox(
                    "Día", [1,2,3,4,5], format_func=lambda x:DAY_NAMES[x-1],
                    key="modify_day",
                )
                modify_options = [
                    x for x in PLAN if x["week"]==modify_week and x["day"]==modify_day
                ]
                modify_index = st.selectbox(
                    "Ejercicio", range(len(modify_options)),
                    format_func=lambda i: modify_options[i]["exercise"], key="modify_select"
                )
                target = modify_options[modify_index]
                with st.form("modify_plan_form"):
                    e_name = st.text_input("Nombre del ejercicio", value=target["exercise"])
                    e_sets = st.text_input("Series", value=target["series"])
                    e_reps = st.text_input("Repeticiones", value=target["repetitions"])
                    e_rir = st.text_input("Intensidad / RIR", value=target["intensity"])
                    kind_options = ["individual", "superserie", "triserie"]
                    initial_kind = target.get("set_type", "individual")
                    if initial_kind not in kind_options:
                        initial_kind = "individual"
                    e_kind = st.selectbox(
                        "Tipo de bloque", kind_options,
                        index=kind_options.index(initial_kind),
                        format_func=lambda x: {
                            "individual": "Ejercicio individual",
                            "superserie": "Superserie (violeta)",
                            "triserie": "Triserie (azul)",
                        }[x],
                    )
                    group_options = ["", "A", "B", "C", "D", "E", "F", "G", "H"]
                    initial_group = target.get("set_group", "")
                    if initial_group not in group_options:
                        initial_group = ""
                    e_group = st.selectbox(
                        "Grupo del bloque", group_options,
                        index=group_options.index(initial_group),
                        format_func=lambda x: x or "Sin grupo / ejercicio individual",
                        help="Usá la misma letra para los ejercicios que van juntos.",
                    )
                    e_pattern = st.text_input("Patrón muscular", value=target["pattern"])
                    e_block = st.text_input("Bloque / orden", value=target["block"])
                    e_rest = st.text_input("Descanso", value=target.get("rest", "2 min"))
                    e_notes = st.text_area("Observaciones técnicas", value=target["notes"])
                    update_plan = st.form_submit_button(
                        "💜 PUBLICAR CAMBIOS DE RUTINA", type="primary",
                        use_container_width=True
                    )
                if update_plan:
                    if not e_name.strip() or not e_sets.strip():
                        st.error("El nombre y las series son obligatorios.")
                    elif e_kind != "individual" and not e_group:
                        st.error("Elegí la letra del grupo de la superserie o triserie.")
                    else:
                        try:
                            current, _ = fetch_remote("data/active_plan.json", TOKEN)
                            current_rows = current["entries"]
                            original = next((e for e in current_rows if e["id"]==target["id"]), None)
                            if not original:
                                raise ValueError("No se encontró el ejercicio en el plan online.")
                            original.update({
                                "exercise":e_name.strip()[:180],
                                "series":e_sets.strip()[:40],
                                "repetitions":e_reps.strip()[:40],
                                "intensity":e_rir.strip()[:100],
                                "set_type":e_kind,
                                "set_group":e_group if e_kind != "individual" else "",
                                "pattern":e_pattern.strip()[:100],
                                "block":e_block.strip()[:100],
                                "notes":e_notes.strip()[:1600],
                                "rest":e_rest.strip()[:100],
                            })
                            persist_remote(
                                "data/active_plan.json", current, TOKEN,
                                f"EFG Training: actualizar semana {modify_week} día {modify_day}",
                            )
                            public_plan.clear()
                            # La próxima interacción relee el plan remoto,
                            # sin sacar al administrador de esta pestaña.
                            st.success(
                                f"✅ RUTINA ACTUALIZADA en GitHub: semana {modify_week}, "
                                f"{DAY_NAMES[modify_day-1]} · {e_name.strip()[:80]}. "
                                "Podés continuar editando; el resto de las vistas "
                                "se actualizará al refrescar la app."
                            )
                        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                            st.error(f"No se pudo actualizar el plan: {error}")


            with edit_tabs[2]:
                st.markdown("#### ⚖️ Registrar peso corporal")
                st.caption(
                    "Una medición por fecha. Si volvés a guardar la misma fecha, "
                    "se actualiza el valor anterior. El registro es público."
                )
                with st.form("weight_form", clear_on_submit=False):
                    weight_date = st.date_input(
                        "Fecha del pesaje", value=date.today(),
                        format="DD/MM/YYYY", key="weight_date"
                    )
                    weight_value = st.number_input(
                        "Peso corporal (kg)", min_value=20.0, max_value=350.0,
                        value=80.0, step=0.1, format="%.2f", key="weight_value"
                    )
                    weight_notes = st.text_area(
                        "Observaciones opcionales",
                        placeholder="Ej.: pesaje matutino, antes de desayunar",
                        key="weight_notes"
                    )
                    weight_submit = st.form_submit_button(
                        "💾 GUARDAR PESO CORPORAL", type="primary",
                        use_container_width=True
                    )

                if weight_submit:
                    try:
                        current, _ = fetch_remote("data/weight.json", TOKEN)
                        existing = current.get("measurements", [])
                        if not isinstance(existing, list):
                            raise ValueError("La estructura de los pesajes no es válida.")
                        saved = [
                            row for row in existing
                            if str(row.get("date", "")) != weight_date.isoformat()
                        ]
                        saved.append({
                            "date": weight_date.isoformat(),
                            "kg": round(float(weight_value), 2),
                            "notes": weight_notes.strip()[:400],
                            "saved_at": datetime.now(timezone.utc).isoformat(),
                        })
                        saved.sort(key=lambda row: row.get("date", ""))
                        persist_remote(
                            "data/weight.json",
                            {"schema_version": 1, "measurements": saved},
                            TOKEN,
                            f"EFG Training: registrar peso corporal {weight_date.isoformat()}",
                        )
                        public_weight.clear()
                        st.success(
                            f"✅ PESO CORPORAL GUARDADO en GitHub: "
                            f"{weight_value:.2f} kg · {weight_date.strftime('%d/%m/%Y')}. "
                            "Podés seguir trabajando desde ADMIN."
                        )
                    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                        st.error(f"No se pudo guardar el peso corporal: {error}")

                if MEASUREMENTS:
                    st.markdown("**Pesajes ya registrados**")
                    weight_rows = sorted(
                        [
                            {"Fecha": r.get("date", ""), "Peso (kg)": r.get("kg", "")}
                            for r in MEASUREMENTS
                        ],
                        key=lambda item: item["Fecha"], reverse=True
                    )
                    st.dataframe(weight_rows, hide_index=True, use_container_width=True)

with tabs[9]:
    render_archive(LEGACY_PLAN, SESSIONS)
    render_legacy_reports(LEGACY_PLAN, plot_layout)

st.divider()
st.markdown(
    '<div class="mini-title">EFG TRAINING / STRENGTH IN NUMBERS · by EFG</div>'
    '<p class="muted">Rutina pública · Modificaciones protegidas · Datos almacenados en GitHub. '
    'Los indicadores son de entrenamiento, no evaluaciones médicas.</p>',
    unsafe_allow_html=True,
)
