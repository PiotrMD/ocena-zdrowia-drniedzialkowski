import os
import re
import smtplib
import tempfile
from datetime import date, datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


# =========================================================
# KONFIGURACJA STRONY
# =========================================================
st.set_page_config(
    page_title="Ocena stanu zdrowia - wywiad lekarski",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =========================================================
# CSS
# =========================================================
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .main .block-container {
        max-width: 980px;
        padding-top: 0.65rem;
        padding-bottom: 2rem;
    }

    .top-card {
        padding: 18px 18px;
        border-radius: 18px;
        border: 1px solid rgba(120,120,120,0.22);
        margin-bottom: 16px;
        background: rgba(250,250,250,0.03);
    }

    .title-main {
        text-align: center;
        font-size: 2.1rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        margin-top: 0.1rem;
        margin-bottom: 0.1rem;
    }

    .title-sub {
        text-align: center;
        font-size: 1.15rem;
        font-weight: 700;
        margin-top: 0;
        margin-bottom: 0.35rem;
    }

    .doctor-line {
        text-align: center;
        font-size: 1rem;
        margin-top: 0;
        margin-bottom: 0.4rem;
    }

    .site-line {
        text-align: center;
        font-size: 1rem;
        margin-top: 0;
        margin-bottom: 0.2rem;
        font-weight: 700;
    }

    .contact-line {
        text-align: center;
        font-size: 0.95rem;
        margin-top: 0;
        margin-bottom: 1rem;
    }

    .progress-box {
        padding: 12px 14px;
        border-radius: 14px;
        border: 1px solid rgba(120,120,120,0.22);
        margin-top: 6px;
        margin-bottom: 16px;
        background: rgba(250,250,250,0.02);
    }

    .send-button > button {
        width: 100%;
        height: 3.25rem;
        font-size: 1.05rem;
        font-weight: 700;
        border-radius: 12px;
    }

    .field-anchor {
        position: relative;
        top: -95px;
        visibility: hidden;
    }

    .field-error-box {
        border: 2px solid #d93025;
        border-radius: 10px;
        padding: 10px 12px;
        color: #d93025;
        background: rgba(217, 48, 37, 0.06);
        font-weight: 600;
        margin-top: -0.15rem;
        margin-bottom: 0.9rem;
    }

    .section-header {
        font-size: 1.75rem;
        font-weight: 700;
        margin-top: 1rem;
        margin-bottom: 0.45rem;
        line-height: 1.2;
    }

    .section-note {
        font-size: 0.94rem;
        opacity: 0.9;
        margin-top: -0.1rem;
        margin-bottom: 0.7rem;
    }

    .alarm-chip {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        color: #ffb4ab;
        background: rgba(217, 48, 37, 0.12);
        border: 1px solid rgba(217, 48, 37, 0.35);
        margin-left: 8px;
    }

    .symptom-card {
        border: 1px solid rgba(120,120,120,0.22);
        background: rgba(250,250,250,0.03);
        border-radius: 14px;
        padding: 12px;
        margin-top: 10px;
        margin-bottom: 14px;
    }

    @media (max-width: 768px) {
        .main .block-container {
            padding-top: 0.45rem;
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }

        .title-main {
            font-size: 1.55rem;
        }

        .title-sub {
            font-size: 1rem;
        }

        .doctor-line, .site-line, .contact-line {
            font-size: 0.9rem;
        }

        .symptom-card {
            padding: 10px;
            border-radius: 12px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# SECRETS
# =========================================================
def get_secret(name: str) -> str:
    if name not in st.secrets:
        st.error(f"Brakuje sekretu: {name}")
        st.stop()
    return st.secrets[name]


EMAIL_NADAWCA = get_secret("EMAIL_NADAWCA")
HASLO_APLIKACJI = get_secret("HASLO_APLIKACJI")
EMAIL_ODBIORCA1 = get_secret("EMAIL_ODBIORCA1")
EMAIL_ODBIORCA2 = get_secret("EMAIL_ODBIORCA2")

# =========================================================
# KONFIGURACJA MEDYCZNA
# =========================================================
PATTERN_OPTIONS = ["stałe", "napadowe", "trudno powiedzieć"]

SYMPTOM_GROUPS: Dict[str, List[Dict[str, Any]]] = {
    "Objawy ogólne / systemowe": [
        {"name": "Zmęczenie", "weight": 1},
        {"name": "Przewlekłe zmęczenie", "weight": 2},
        {"name": "Osłabienie", "weight": 1},
        {"name": "Gorączka", "weight": 2},
        {"name": "Dreszcze", "weight": 1},
        {"name": "Nocne poty", "weight": 2, "alarm": True},
        {"name": "Utrata masy ciała", "weight": 3, "alarm": True},
        {"name": "Zwiększenie masy ciała", "weight": 1},
        {"name": "Brak apetytu", "weight": 1},
        {"name": "Nadmierny apetyt", "weight": 1},
        {"name": "Bóle mięśni", "weight": 1},
        {"name": "Złe samopoczucie", "weight": 1},
        {"name": "Nadmierne pocenie się", "weight": 1},
        {"name": "Zawroty głowy", "weight": 1},
        {"name": "Brak energii", "weight": 1},
    ],
    "Układ oddechowy": [
        {"name": "Kaszel", "weight": 1},
        {"name": "Kaszel przewlekły", "weight": 2},
        {"name": "Duszność wysiłkowa", "weight": 2},
        {"name": "Duszność spoczynkowa", "weight": 3, "alarm": True},
        {"name": "Trudności z oddychaniem", "weight": 2},
        {"name": "Trudności w oddychaniu w pozycji leżącej", "weight": 3, "alarm": True},
        {"name": "Świszczący oddech", "weight": 2},
        {"name": "Uczucie ucisku w klatce piersiowej", "weight": 2},
        {"name": "Ból w klatce piersiowej przy oddychaniu", "weight": 2},
        {"name": "Ból gardła", "weight": 1},
        {"name": "Suchość w gardle", "weight": 1},
        {"name": "Utrata głosu", "weight": 1},
        {"name": "Zapalenie zatok", "weight": 1},
        {"name": "Przewlekłe zapalenie zatok", "weight": 2},
        {"name": "Nawracające infekcje dróg oddechowych", "weight": 1},
        {"name": "Chrapanie", "weight": 1},
        {"name": "Płytki oddech", "weight": 2},
        {"name": "Nadprodukcja śluzu", "weight": 1},
        {"name": "Krwioplucie", "weight": 4, "alarm": True},
    ],
    "Układ sercowo-naczyniowy": [
        {"name": "Kołatanie serca", "weight": 2},
        {"name": "Szybkie bicie serca", "weight": 1},
        {"name": "Nierówne bicie serca", "weight": 2},
        {"name": "Wolne bicie serca", "weight": 2},
        {"name": "Ból w klatce piersiowej", "weight": 4, "alarm": True},
        {"name": "Ból zamostkowy", "weight": 4, "alarm": True},
        {"name": "Ból promieniujący do ramienia", "weight": 4, "alarm": True},
        {"name": "Ból szczęki", "weight": 3},
        {"name": "Ból w nadbrzuszu", "weight": 2},
        {"name": "Omdlenia", "weight": 4, "alarm": True},
        {"name": "Zawroty głowy przy wstawaniu", "weight": 1},
        {"name": "Obrzęki podudzi", "weight": 2},
        {"name": "Obrzęk jednego podudzia", "weight": 4, "alarm": True},
        {"name": "Opuchlizna kostek", "weight": 2},
        {"name": "Zimne kończyny", "weight": 1},
        {"name": "Szybkie męczenie się", "weight": 1},
        {"name": "Żylaki podudzi", "weight": 1},
        {"name": "Pajączki na nogach", "weight": 1},
        {"name": "Duszność wysiłkowa", "weight": 2},
        {"name": "Duszność spoczynkowa", "weight": 3, "alarm": True},
        {"name": "Zimne poty", "weight": 3},
    ],
    "Układ pokarmowy": [
        {"name": "Ból brzucha", "weight": 2},
        {"name": "Ból brzucha po jedzeniu", "weight": 2},
        {"name": "Ból brzucha na czczo", "weight": 2},
        {"name": "Ból przy dotyku brzucha", "weight": 3},
        {"name": "Wzdęcia", "weight": 1},
        {"name": "Wzdęcia po posiłkach", "weight": 1},
        {"name": "Biegunki", "weight": 2},
        {"name": "Biegunki przewlekłe", "weight": 3},
        {"name": "Biegunka z krwią", "weight": 4, "alarm": True},
        {"name": "Zaparcia", "weight": 1},
        {"name": "Zaparcia przewlekłe", "weight": 2},
        {"name": "Nudności", "weight": 1},
        {"name": "Wymioty", "weight": 2},
        {"name": "Wymioty krwawe", "weight": 4, "alarm": True},
        {"name": "Zgaga", "weight": 1},
        {"name": "Zgaga nocna", "weight": 2},
        {"name": "Odbijanie", "weight": 1},
        {"name": "Gorzkie odbijanie", "weight": 1},
        {"name": "Trudności w przełykaniu", "weight": 3},
        {"name": "Uczucie pełności", "weight": 1},
        {"name": "Nieprzyjemny zapach z ust", "weight": 1},
        {"name": "Śluz w stolcu", "weight": 2},
        {"name": "Zmiana koloru stolca", "weight": 2},
        {"name": "Krwawienie z odbytu", "weight": 4, "alarm": True},
        {"name": "Hemoroidy", "weight": 1},
        {"name": "Swędzenie odbytu", "weight": 1},
    ],
    "Układ moczowy": [
        {"name": "Krwiomocz", "weight": 4, "alarm": True},
        {"name": "Ból podczas oddawania moczu", "weight": 2},
        {"name": "Pieczenie przy oddawaniu moczu", "weight": 2},
        {"name": "Parcie na mocz", "weight": 1},
        {"name": "Częste oddawanie moczu", "weight": 1},
        {"name": "Częstomocz nocny", "weight": 1},
        {"name": "Nietrzymanie moczu", "weight": 2},
        {"name": "Ból w podbrzuszu", "weight": 2},
        {"name": "Częste infekcje dróg moczowych", "weight": 2},
        {"name": "Zwiększone pragnienie", "weight": 1},
        {"name": "Polidypsja i poliuria", "weight": 2},
        {"name": "Mętny mocz", "weight": 1},
        {"name": "Nieprzyjemny zapach moczu", "weight": 1},
        {"name": "Ból pleców w okolicy nerek", "weight": 2},
        {"name": "Uczucie niepełnego opróżnienia pęcherza", "weight": 2},
        {"name": "Kolka nerkowa", "weight": 4, "alarm": True},
        {"name": "Pienienie się moczu", "weight": 2},
    ],
    "Układ rozrodczy / ginekologiczny / andrologiczny": [
        {"name": "Zmniejszony popęd seksualny", "weight": 1},
        {"name": "Zwiększony popęd seksualny", "weight": 1},
        {"name": "Zaburzenia miesiączkowania", "weight": 2},
        {"name": "Brak miesiączki", "weight": 2},
        {"name": "Obfite miesiączki", "weight": 2},
        {"name": "Krwawienia między miesiączkami", "weight": 3},
        {"name": "Krwawienie po stosunku", "weight": 3},
        {"name": "Krwawienie po menopauzie", "weight": 4, "alarm": True},
        {"name": "Ból podczas stosunku", "weight": 2},
        {"name": "Ból podczas miesiączki", "weight": 1},
        {"name": "Ból podczas owulacji", "weight": 1},
        {"name": "Nieregularne miesiączki", "weight": 1},
        {"name": "Suchość pochwy", "weight": 1},
        {"name": "Wydzielina z pochwy", "weight": 2},
        {"name": "Swędzenie pochwy", "weight": 2},
        {"name": "Ból piersi", "weight": 1},
        {"name": "Wyciek z sutków", "weight": 3},
        {"name": "Uczucie ciężkości w podbrzuszu", "weight": 1},
        {"name": "Ból w podbrzuszu", "weight": 2},
        {"name": "Zaburzenia erekcji", "weight": 2},
        {"name": "Ból jąder", "weight": 3},
        {"name": "Guz jądra", "weight": 4, "alarm": True},
    ],
    "Układ nerwowy i psychika": [
        {"name": "Bóle głowy", "weight": 1},
        {"name": "Bóle migrenowe", "weight": 2},
        {"name": "Zawroty głowy", "weight": 1},
        {"name": "Omdlenia", "weight": 3, "alarm": True},
        {"name": "Mrowienie kończyn", "weight": 2},
        {"name": "Drętwienie kończyn", "weight": 2},
        {"name": "Słabość mięśni", "weight": 3},
        {"name": "Problemy z równowagą", "weight": 2},
        {"name": "Zaburzenia pamięci", "weight": 2},
        {"name": "Problemy z koncentracją", "weight": 1},
        {"name": "Trudności w skupieniu się", "weight": 1},
        {"name": "Zaburzenia mowy", "weight": 4, "alarm": True},
        {"name": "Drżenie rąk", "weight": 2},
        {"name": "Nadwrażliwość na światło", "weight": 1},
        {"name": "Zaburzenia snu", "weight": 1},
        {"name": "Wybudzanie w nocy", "weight": 1},
        {"name": "Trudności w zasypianiu", "weight": 1},
        {"name": "Wstawanie zmęczony", "weight": 1},
        {"name": "Lęki", "weight": 1},
        {"name": "Nerwowość", "weight": 1},
        {"name": "Depresja", "weight": 2},
        {"name": "Padaczka / napady drgawkowe", "weight": 4, "alarm": True},
    ],
    "Układ kostno-stawowy i mięśniowy": [
        {"name": "Bóle stawów", "weight": 1},
        {"name": "Obrzęki stawów", "weight": 2},
        {"name": "Sztywność poranna", "weight": 2},
        {"name": "Ból przy ruchu", "weight": 1},
        {"name": "Trzeszczenie w stawach", "weight": 1},
        {"name": "Ból kolan", "weight": 1},
        {"name": "Ból bioder", "weight": 1},
        {"name": "Ból barków", "weight": 1},
        {"name": "Ból nadgarstków", "weight": 1},
        {"name": "Ból łokci", "weight": 1},
        {"name": "Bóle karku", "weight": 1},
        {"name": "Bóle szyi", "weight": 1},
        {"name": "Bóle lędźwi", "weight": 1},
        {"name": "Ból pleców", "weight": 1},
        {"name": "Bóle mięśni", "weight": 1},
        {"name": "Osłabienie mięśni", "weight": 2},
        {"name": "Ból kości", "weight": 2},
        {"name": "Złamania", "weight": 2},
        {"name": "Zwichnięcia", "weight": 2},
    ],
    "Skóra i tkanki podskórne": [
        {"name": "Wysypka", "weight": 1},
        {"name": "Pokrzywka", "weight": 2},
        {"name": "Świąd skóry", "weight": 1},
        {"name": "Suchość skóry", "weight": 1},
        {"name": "Łuszczenie skóry", "weight": 1},
        {"name": "Zaczerwienienia", "weight": 1},
        {"name": "Przebarwienia", "weight": 1},
        {"name": "Zmiany barwnikowe", "weight": 2},
        {"name": "Owrzodzenia skóry", "weight": 3},
        {"name": "Rany trudno gojące się", "weight": 3},
        {"name": "Infekcje skóry", "weight": 2},
        {"name": "Utrata włosów", "weight": 1},
        {"name": "Zmiany na paznokciach", "weight": 1},
        {"name": "Brodawki", "weight": 1},
        {"name": "Kłykciny", "weight": 2},
        {"name": "Pękanie skóry", "weight": 1},
        {"name": "Bladość skóry", "weight": 1},
    ],
    "Zmysły (wzrok, słuch, węch, smak)": [
        {"name": "Pogorszenie wzroku", "weight": 2},
        {"name": "Podwójne widzenie", "weight": 4, "alarm": True},
        {"name": "Zaburzenia widzenia", "weight": 2},
        {"name": "Mroczki przed oczami", "weight": 2},
        {"name": "Ból oczu", "weight": 2},
        {"name": "Nadmierne łzawienie", "weight": 1},
        {"name": "Zapalenie spojówek", "weight": 1},
        {"name": "Utrata słuchu", "weight": 2},
        {"name": "Bóle uszu", "weight": 1},
        {"name": "Szumy uszne", "weight": 1},
        {"name": "Zatkane uszy", "weight": 1},
        {"name": "Utrata węchu", "weight": 2},
        {"name": "Utrata smaku", "weight": 2},
        {"name": "Nadwrażliwość na zapachy", "weight": 1},
        {"name": "Krwawienie z nosa", "weight": 2},
        {"name": "Przewlekłe zatkanie nosa", "weight": 1},
        {"name": "Ból zatok", "weight": 1},
    ],
    "Układ immunologiczny / alergologiczny / hematologiczny": [
        {"name": "Częste infekcje", "weight": 2},
        {"name": "Powiększone węzły chłonne", "weight": 3},
        {"name": "Łatwe siniaczenie", "weight": 2},
        {"name": "Krwawienia z nosa", "weight": 2},
        {"name": "Krwawienia dziąseł", "weight": 2},
        {"name": "Niedokrwistość", "weight": 2},
        {"name": "Infekcje grzybicze", "weight": 2},
        {"name": "Alergie pokarmowe", "weight": 1},
        {"name": "Alergie wziewne", "weight": 1},
        {"name": "Alergie kontaktowe", "weight": 1},
        {"name": "Reakcje alergiczne na leki", "weight": 2},
        {"name": "Anafilaksja", "weight": 4, "alarm": True},
        {"name": "Obrzęki alergiczne", "weight": 3},
        {"name": "Katar sienny", "weight": 1},
        {"name": "Łzawienie oczu", "weight": 1},
        {"name": "Kichanie", "weight": 1},
        {"name": "Astma alergiczna", "weight": 2},
        {"name": "Egzema", "weight": 1},
    ],
}

DIAGNOSIS_GROUPS: Dict[str, List[str]] = {
    "Układ oddechowy": [
        "Astma",
        "POChP",
        "Przewlekłe zapalenie oskrzeli",
        "Przewlekłe zapalenie zatok",
        "Bezdech senny",
    ],
    "Układ sercowo-naczyniowy": [
        "Nadciśnienie tętnicze",
        "Choroba wieńcowa",
        "Zaburzenia rytmu serca",
        "Niewydolność serca",
        "Zakrzepica żylna",
        "Żylaki",
    ],
    "Układ pokarmowy": [
        "Refluks żołądkowo-przełykowy",
        "Choroba wrzodowa",
        "Zespół jelita drażliwego",
        "Choroba Crohna",
        "Wrzodziejące zapalenie jelita grubego",
        "Hemoroidy",
        "Kamica żółciowa",
    ],
    "Układ moczowy": [
        "Kamica nerkowa",
        "Nawracające ZUM",
        "Przerost prostaty",
        "Przewlekła choroba nerek",
        "Nietrzymanie moczu",
    ],
    "Układ rozrodczy / hormonalny": [
        "PCOS",
        "Endometrioza",
        "Mięśniaki macicy",
        "Menopauza",
        "Zaburzenia erekcji",
        "Niepłodność",
    ],
    "Układ nerwowy i psychika": [
        "Migrena",
        "Padaczka",
        "Depresja",
        "Zaburzenia lękowe",
        "Bezsenność",
        "Choroba Parkinsona",
    ],
    "Układ kostno-stawowy": [
        "Choroba zwyrodnieniowa stawów",
        "Dyskopatia",
        "Osteoporoza",
        "Reumatoidalne zapalenie stawów",
        "Dna moczanowa",
    ],
    "Skóra / immunologia": [
        "AZS",
        "Łuszczyca",
        "Pokrzywka przewlekła",
        "Alergia pokarmowa",
        "Alergia wziewna",
        "Choroba autoimmunologiczna",
    ],
    "Metaboliczne / ogólne": [
        "Cukrzyca",
        "Insulinooporność",
        "Niedoczynność tarczycy",
        "Nadczynność tarczycy",
        "Niedokrwistość",
        "Otyłość",
    ],
}

FAMILY_MEMBERS = [
    "Matka",
    "Ojciec",
    "Babcia od strony matki",
    "Dziadek od strony matki",
    "Babcia od strony ojca",
    "Dziadek od strony ojca",
    "Rodzeństwo",
]

FAMILY_DISEASES = [
    "Choroby serca",
    "Nadciśnienie",
    "Zawał",
    "Udar",
    "Cukrzyca",
    "Nowotwory",
    "Astma",
    "POChP",
    "Choroby tarczycy",
    "Choroby nerek",
    "Choroby wątroby",
    "Choroby autoimmunologiczne",
    "Choroby reumatyczne",
    "Migrena",
    "Padaczka",
    "Choroby psychiczne",
    "Choroba Alzheimera",
    "Choroba Parkinsona",
    "Osteoporoza",
    "Alergie",
    "Otyłość",
]

# =========================================================
# FUNKCJE POMOCNICZE
# =========================================================
def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    if isinstance(value, bool):
        return value
    return True


def safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d.%m.%Y")
    return str(value).strip()


def list_text(values: List[str]) -> str:
    return ", ".join([v for v in values if v])


def lines_from_text(text: str) -> List[str]:
    return [x.strip() for x in text.splitlines() if x.strip()]


def initials(full_name: str) -> str:
    parts = [p for p in full_name.strip().split() if p]
    if not parts:
        return ""
    return " ".join([p[0].upper() + "." for p in parts])


def validate_phone(raw: str) -> Optional[str]:
    text = (raw or "").strip()
    if not text:
        return None
    cleaned = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits.isdigit():
        return None
    if len(digits) < 7 or len(digits) > 15:
        return None
    return text


def validate_email(raw: str) -> Optional[str]:
    text = (raw or "").strip()
    if not text:
        return None
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    if not re.match(pattern, text):
        return None
    return text


def parse_optional_float(raw: str) -> Optional[float]:
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def bmi_calc(weight_kg: Optional[float], height_cm: Optional[float]):
    if not weight_kg or not height_cm or height_cm <= 0:
        return None
    return weight_kg / ((height_cm / 100.0) ** 2)


def bmi_label(bmi):
    if bmi is None:
        return "brak danych"
    if bmi < 18.5:
        return "niedowaga"
    if bmi < 25:
        return "masa ciała prawidłowa"
    if bmi < 30:
        return "nadwaga"
    if bmi < 35:
        return "otyłość I stopnia"
    if bmi < 40:
        return "otyłość II stopnia"
    return "otyłość III stopnia"


def select_with_placeholder(label: str, options: List[str], key: str) -> str:
    all_options = [""] + options
    return st.selectbox(
        label,
        all_options,
        format_func=lambda x: "wybierz" if x == "" else x,
        key=key,
    )


def error_box(message: str):
    st.markdown(
        f"<div class='field-error-box'>{message}</div>",
        unsafe_allow_html=True,
    )


def scroll_to_anchor(anchor_id: str):
    components.html(
        f"""
        <script>
        const target = window.parent.document.getElementById("{anchor_id}");
        if (target) {{
            target.scrollIntoView({{behavior: "smooth", block: "start"}});
        }}
        </script>
        """,
        height=0,
    )


def register_fonts():
    regular_font = "Helvetica"
    bold_font = "Helvetica-Bold"

    if os.path.exists("DejaVuSans.ttf"):
        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))
        regular_font = "DejaVuSans"

    if os.path.exists("DejaVuSans-Bold.ttf"):
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "DejaVuSans-Bold.ttf"))
        bold_font = "DejaVuSans-Bold"
    elif regular_font == "DejaVuSans":
        bold_font = "DejaVuSans"

    return regular_font, bold_font


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self._font_name = kwargs.pop("font_name", "Helvetica")
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states) + 1
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(page_count)
            super().showPage()
        self.draw_page_number(page_count)
        super().save()

    def draw_page_number(self, page_count: int):
        self.setFont(self._font_name, 9)
        self.drawCentredString(A4[0] / 2, 10 * mm, f"Strona {self._pageNumber} / {page_count}")


def add_pdf_section(story, title: str, rows: List[str], styles_dict):
    clean_rows = [r for r in rows if nonempty(r)]
    story.append(Paragraph(title, styles_dict["section"]))
    story.append(Spacer(1, 2.2 * mm))
    if clean_rows:
        for row in clean_rows:
            story.append(Paragraph(row.replace("\n", "<br/>"), styles_dict["body"]))
            story.append(Spacer(1, 1.2 * mm))
    else:
        story.append(Paragraph("Brak danych.", styles_dict["body"]))
        story.append(Spacer(1, 1.2 * mm))
    story.append(Spacer(1, 2.5 * mm))


def build_symptom_rows(
    selected_symptoms: Dict[str, List[str]],
    system_symptom_meta: Dict[str, Dict[str, str]],
) -> Tuple[List[str], List[str], List[str], Dict[str, float]]:
    detailed_rows: List[str] = []
    alarm_rows: List[str] = []
    summary_rows: List[str] = []
    system_scores: Dict[str, float] = {}

    for system_name, chosen_list in selected_symptoms.items():
        if not chosen_list:
            continue

        meta = system_symptom_meta.get(system_name, {})
        pattern = meta.get("pattern", "")
        since = meta.get("since", "")
        note = meta.get("note", "")

        score_sum = 0.0
        for symptom_name in chosen_list:
            found = next((x for x in SYMPTOM_GROUPS.get(system_name, []) if x["name"] == symptom_name), None)
            if found:
                score_sum += float(found.get("weight", 1))
                if found.get("alarm"):
                    alarm_rows.append(f"{system_name}: {symptom_name}")
            else:
                score_sum += 1.0

        system_scores[system_name] = round(score_sum, 1)

        summary_line = f"{system_name}: {len(chosen_list)} obj."
        if pattern:
            summary_line += f" | charakter: {pattern}"
        if since:
            summary_line += f" | od: {since}"
        summary_rows.append(summary_line)

        detailed_rows.append(f"<b>{system_name}</b>")
        detailed_rows.append(f"• Objawy: {', '.join(chosen_list)}")
        if pattern:
            detailed_rows.append(f"• Charakter: {pattern}")
        if since:
            detailed_rows.append(f"• Od kiedy: {since}")
        if note:
            detailed_rows.append(f"• Krótki opis / uwagi: {note}")
        detailed_rows.append("")

    dominant = sorted(system_scores.items(), key=lambda x: x[1], reverse=True)
    dominant = [x for x in dominant if x[1] > 0][:5]

    dominant_rows = []
    if dominant:
        dominant_rows.append(
            "Dominujące układy: " +
            ", ".join([f"{name} ({score} pkt)" for name, score in dominant])
        )

    return dominant_rows + summary_rows, detailed_rows, alarm_rows, system_scores


def build_diagnosis_rows(diagnoses_selected: Dict[str, List[str]], diagnoses_other: Dict[str, str]) -> List[str]:
    rows: List[str] = []
    nonempty_groups = 0

    for group_name, items in diagnoses_selected.items():
        other = diagnoses_other.get(group_name, "").strip()
        if items or other:
            nonempty_groups += 1
            rows.append(f"<b>{group_name}</b>")
            for item in items:
                rows.append(f"• {item}")
            if other:
                extra = [x.strip() for x in other.split(",") if x.strip()]
                if extra:
                    for x in extra:
                        rows.append(f"• Inne: {x}")
                else:
                    rows.append(f"• Inne: {other}")
            rows.append("")

    if nonempty_groups == 0:
        return ["Brak zgłoszonych rozpoznań."]
    return rows


def build_family_rows(family_selected: Dict[str, List[str]], family_other: Dict[str, str]) -> List[str]:
    rows: List[str] = []
    nonempty_members = 0

    for person in FAMILY_MEMBERS:
        items = family_selected.get(person, [])
        other = family_other.get(person, "").strip()
        if items or other:
            nonempty_members += 1
            rows.append(f"<b>{person}</b>")
            for item in items:
                rows.append(f"• {item}")
            if other:
                rows.append(f"• Inne: {other}")
            rows.append("")

    if nonempty_members == 0:
        return ["Brak istotnych obciążeń rodzinnych zgłoszonych w formularzu."]
    return rows


def send_email_with_pdf(subject: str, body_text: str, pdf_path: str):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_NADAWCA
    msg["To"] = EMAIL_NADAWCA
    msg["Bcc"] = f"{EMAIL_ODBIORCA1}, {EMAIL_ODBIORCA2}"
    msg.set_content(body_text)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename="wywiad_lekarski.pdf",
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_NADAWCA, HASLO_APLIKACJI)
        smtp.send_message(msg)


def calc_progress(values: List[Any]) -> int:
    if not values:
        return 0
    filled = sum(1 for v in values if nonempty(v))
    return int(round((filled / len(values)) * 100))


def make_pdf(data: Dict[str, Any]) -> str:
    regular_font, bold_font = register_fonts()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()

    doc = SimpleDocTemplate(
        tmp.name,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
    )

    base = getSampleStyleSheet()
    styles_dict = {
        "title_big": ParagraphStyle(
            "TitleBig",
            parent=base["Title"],
            alignment=TA_CENTER,
            fontName=bold_font,
            fontSize=16,
            leading=19,
            spaceAfter=1.5 * mm,
        ),
        "title_mid": ParagraphStyle(
            "TitleMid",
            parent=base["Title"],
            alignment=TA_CENTER,
            fontName=bold_font,
            fontSize=12,
            leading=15,
            spaceAfter=2 * mm,
        ),
        "doctor": ParagraphStyle(
            "Doctor",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName=regular_font,
            fontSize=10.5,
            leading=13,
            spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            alignment=TA_LEFT,
            fontName=bold_font,
            fontSize=11,
            leading=14,
            spaceBefore=2 * mm,
            spaceAfter=1.5 * mm,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            alignment=TA_LEFT,
            fontName=regular_font,
            fontSize=9.5,
            leading=12,
        ),
    }

    story = []
    story.append(Paragraph("OCENA STANU ZDROWIA", styles_dict["title_big"]))
    story.append(Paragraph("Wywiad lekarski", styles_dict["title_mid"]))
    story.append(Paragraph("dr n. med. Piotr Niedziałkowski", styles_dict["doctor"]))
    story.append(Spacer(1, 1 * mm))

    add_pdf_section(
        story,
        "Dane identyfikacyjne",
        [
            f"Pacjent: {data['initials']}",
            f"Telefon kontaktowy: {data['phone']}",
            f"Data urodzenia: {data['birth_date']}",
            f"Rodzaj wizyty: {data['visit_type']}",
            f"Data i godzina wypełnienia formularza: {data['submitted_at']}",
        ],
        styles_dict,
    )

    add_pdf_section(story, "Cel wykonania oceny zdrowia", data["sec_goal"], styles_dict)
    add_pdf_section(story, "Dane podstawowe", data["sec_basic"], styles_dict)
    add_pdf_section(story, "Ocena ogólna", data["sec_overall"], styles_dict)
    add_pdf_section(story, "Przebieg zdrowia i leki", data["sec_timeline"], styles_dict)
    add_pdf_section(story, "Objawy dominujące i rozkład układowy", data["sec_symptom_summary"], styles_dict)
    add_pdf_section(story, "Objawy alarmowe", data["sec_alarm"], styles_dict)
    add_pdf_section(story, "Objawy pogrupowane według układów", data["sec_symptom_details"], styles_dict)
    add_pdf_section(story, "Choroby współistniejące / rozpoznania", data["sec_diagnoses"], styles_dict)
    add_pdf_section(story, "Wywiad rodzinny", data["sec_family"], styles_dict)
    add_pdf_section(story, "Styl życia", data["sec_lifestyle"], styles_dict)
    add_pdf_section(story, "Podróże, zwierzęta, urazy, COVID, stres", data["sec_exposures"], styles_dict)
    add_pdf_section(story, "Specyficzne informacje ginekologiczne / andrologiczne", data["sec_sex_specific"], styles_dict)
    add_pdf_section(story, "Najważniejsze pytanie do lekarza", data["sec_question"], styles_dict)

    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: NumberedCanvas(*args, font_name=regular_font, **kwargs),
    )
    return tmp.name


# =========================================================
# STAN SESJI
# =========================================================
if "field_errors" not in st.session_state:
    st.session_state.field_errors = {}
if "scroll_target" not in st.session_state:
    st.session_state.scroll_target = None

field_errors: Dict[str, str] = st.session_state.field_errors

# =========================================================
# GÓRA APLIKACJI
# =========================================================
progress_placeholder = st.empty()

if os.path.exists("logo.PNG"):
    st.image("logo.PNG", use_container_width=True)
elif os.path.exists("logo.png"):
    st.image("logo.png", use_container_width=True)
elif os.path.exists("Logo OCENA ZDROWIA.PNG"):
    st.image("Logo OCENA ZDROWIA.PNG", use_container_width=True)

st.markdown("<div class='title-main'>OCENA STANU ZDROWIA</div>", unsafe_allow_html=True)
st.markdown("<div class='title-sub'>Wywiad lekarski</div>", unsafe_allow_html=True)
st.markdown("<div class='doctor-line'>dr n. med. Piotr Niedziałkowski</div>", unsafe_allow_html=True)
st.markdown("<div class='site-line'>www.ocenazdrowia.pl</div>", unsafe_allow_html=True)
st.markdown("<div class='contact-line'>W sprawie pytań proszę kontaktować się z recepcją: +48 690 584 584</div>", unsafe_allow_html=True)

st.markdown(
    """
    <div class="top-card">
    Szanowni Państwo,<br><br>
    Proszę zaznaczać tylko objawy, które rzeczywiście występują obecnie lub nawracają.<br>
    Przy każdym układzie można krótko dopisać od kiedy objawy trwają i ich ogólny charakter.<br>
    Dane z formularza nie są zapisywane w bazie aplikacji. Po wysłaniu dokument trafia wyłącznie do lekarza w celu przygotowania wizyty.
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# 1. DANE PODSTAWOWE
# =========================================================
with st.expander("1. Dane podstawowe", expanded=True):
    visit_type = select_with_placeholder("Rodzaj wizyty", ["Pierwsza", "Kontrolna"], key="visit_type")

    goal_of_assessment = select_with_placeholder(
        "Cel wykonania oceny zdrowia",
        [
            "Ocena stanu zdrowia bez dolegliwości",
            "Ocena stanu zdrowia, bo mam dolegliwości",
        ],
        key="goal_of_assessment",
    )

    st.markdown('<div id="anchor_first_name" class="field-anchor"></div>', unsafe_allow_html=True)
    first_name = st.text_input("Imię", key="first_name")
    if "first_name" in field_errors:
        error_box(field_errors["first_name"])

    st.markdown('<div id="anchor_last_name" class="field-anchor"></div>', unsafe_allow_html=True)
    last_name = st.text_input("Nazwisko", key="last_name")
    if "last_name" in field_errors:
        error_box(field_errors["last_name"])

    st.markdown('<div id="anchor_phone" class="field-anchor"></div>', unsafe_allow_html=True)
    phone = st.text_input("Telefon kontaktowy", key="phone")
    if "phone" in field_errors:
        error_box(field_errors["phone"])

    st.markdown('<div id="anchor_email" class="field-anchor"></div>', unsafe_allow_html=True)
    email = st.text_input("Adres e-mail", key="email")
    if "email" in field_errors:
        error_box(field_errors["email"])

    birth_date = st.date_input(
        "Data urodzenia",
        min_value=date(1900, 1, 1),
        max_value=date.today(),
        value=date(1990, 1, 1),
        key="birth_date",
    )

    sex = select_with_placeholder("Płeć", ["kobieta", "mężczyzna", "inne"], key="sex")
    nationality = st.text_input("Narodowość", key="nationality")
    profession = st.text_input("Obecnie wykonywany zawód", key="profession")
    current_status = select_with_placeholder(
        "Aktualny status",
        ["pracujący", "dziecko", "uczeń", "student", "emeryt", "inne"],
        key="current_status",
    )

    height_cm_text = st.text_input("Wzrost (cm)", key="height_cm_text")
    weight_kg_text = st.text_input("Masa ciała (kg)", key="weight_kg_text")

    height_cm = parse_optional_float(height_cm_text)
    weight_kg = parse_optional_float(weight_kg_text)
    bmi = bmi_calc(weight_kg, height_cm)

    if bmi is not None:
        st.info(f"BMI: {bmi:.1f} ({bmi_label(bmi)})")
    else:
        st.info("BMI: brak danych")

# =========================================================
# 2. OCENA OGÓLNA
# =========================================================
with st.expander("2. Ocena ogólna", expanded=False):
    physical_score = st.slider(
        "Jak oceniasz swój stan fizyczny? 0 = bardzo zły, 10 = bardzo dobry",
        0, 10, 6, key="physical_score"
    )
    mental_score = st.slider(
        "Jak oceniasz swój stan psychiczny? 0 = bardzo zły, 10 = bardzo dobry",
        0, 10, 6, key="mental_score"
    )
    weight_change = select_with_placeholder(
        "Czy w ostatnim roku zmieniła się masa ciała?",
        ["wzrosła", "spadła", "bez zmian"],
        key="weight_change",
    )
    weight_change_amount = ""
    if weight_change in ["wzrosła", "spadła"]:
        weight_change_amount = st.text_input("O ile mniej więcej kilogramów?", key="weight_change_amount")

# =========================================================
# 3. CHRONOLOGIA I LEKI
# =========================================================
with st.expander("3. Chronologia zdrowia i leki", expanded=False):
    health_timeline = st.text_area(
        "Opisz przebieg zdrowia od pierwszych problemów zdrowotnych do dziś",
        key="health_timeline",
        height=140,
    )
    current_meds = st.text_area(
        "Jakie leki obecnie przyjmujesz? Podaj nazwę i dawkowanie. Najlepiej każdy lek w osobnej linii.",
        key="current_meds",
        height=120,
    )

# =========================================================
# 4. OBJAWY WEDŁUG UKŁADÓW
# =========================================================
st.markdown("<div class='section-header'>Objawy według układów</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-note'>Zaznacz objawy obecne lub nawracające. Dla każdego układu możesz krótko dopisać charakter objawów i od kiedy trwają.</div>",
    unsafe_allow_html=True,
)

selected_symptoms: Dict[str, List[str]] = {}
system_symptom_meta: Dict[str, Dict[str, str]] = {}

for system_name, items in SYMPTOM_GROUPS.items():
    expander_open = len(st.session_state.get(f"symptoms_{system_name}", [])) > 0 or bool(
        st.session_state.get(f"other_{system_name}", "").strip()
    )

    with st.expander(system_name, expanded=expander_open):
        options = [item["name"] for item in items]

        chosen = st.multiselect(
            f"Zaznacz objawy dotyczące układu: {system_name}",
            options,
            key=f"symptoms_{system_name}",
            placeholder="Wybierz objawy",
        )

        other_text = st.text_area(
            f"Inne objawy z układu: {system_name}",
            key=f"other_{system_name}",
            height=80,
            placeholder="Wpisz inne objawy, jeśli nie ma ich na liście",
        )

        if other_text.strip():
            combined = list(chosen)
            combined.append(f"Inne objawy: {other_text.strip()}")
            selected_symptoms[system_name] = combined
        else:
            selected_symptoms[system_name] = list(chosen)

        st.markdown("<div class='symptom-card'>", unsafe_allow_html=True)
        pattern = st.radio(
            f"Ogólny charakter objawów w układzie: {system_name}",
            PATTERN_OPTIONS,
            key=f"pattern_{system_name}",
            horizontal=True,
        )
        since = st.text_input(
            f"Od kiedy trwają objawy w układzie: {system_name}",
            key=f"since_{system_name}",
            placeholder="np. od 3 miesięcy, od stycznia 2025",
        )
        note = st.text_area(
            f"Krótki opis / uwagi do objawów w układzie: {system_name}",
            key=f"note_{system_name}",
            height=90,
            placeholder="np. objawy nasilają się rano, po wysiłku, są zmienne, pojawiły się po infekcji",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        system_symptom_meta[system_name] = {
            "pattern": pattern,
            "since": since.strip(),
            "note": note.strip(),
        }

# =========================================================
# 5. CHOROBY WSPÓŁISTNIEJĄCE / ROZPOZNANIA
# =========================================================
with st.expander("5. Choroby współistniejące / rozpoznania", expanded=False):
    st.markdown("<div class='section-note'>Tutaj zaznacz rozpoznane choroby. Nie mieszamy ich z objawami.</div>", unsafe_allow_html=True)
    diagnoses_selected: Dict[str, List[str]] = {}
    diagnoses_other: Dict[str, str] = {}

    for group_name, options in DIAGNOSIS_GROUPS.items():
        chosen = st.multiselect(
            f"{group_name}",
            options,
            key=f"diag_{group_name}",
            placeholder="Wybierz choroby współistniejące",
        )
        other = st.text_input(
            f"Inne rozpoznania w grupie: {group_name}",
            key=f"diag_other_{group_name}",
            placeholder="Oddziel przecinkami, jeśli wpisujesz kilka",
        )
        diagnoses_selected[group_name] = chosen
        diagnoses_other[group_name] = other

# =========================================================
# 6. WYWIAD RODZINNY
# =========================================================
with st.expander("6. Wywiad rodzinny", expanded=False):
    st.markdown("<div class='section-note'>Dla każdej osoby zaznacz istotne choroby rodzinne.</div>", unsafe_allow_html=True)
    family_selected: Dict[str, List[str]] = {}
    family_other: Dict[str, str] = {}

    for person in FAMILY_MEMBERS:
        st.markdown(f"**{person}**")
        selected = st.multiselect(
            f"Choroby rodzinne: {person}",
            FAMILY_DISEASES,
            key=f"family_{person}",
            placeholder="Wybierz choroby",
        )
        other = st.text_input(
            f"Inne ważne informacje: {person}",
            key=f"family_other_{person}",
        )
        family_selected[person] = selected
        family_other[person] = other

# =========================================================
# 7. STYL ŻYCIA, NARAŻENIA
# =========================================================
with st.expander("7. Styl życia, narażenia i tło zdrowotne", expanded=False):
    lifestyle = select_with_placeholder(
        "Tryb życia",
        ["leżący", "siedzący", "nisko aktywny", "średnio aktywny", "bardzo aktywny", "inne"],
        key="lifestyle",
    )
    stimulants = st.multiselect(
        "Używki i codzienne nawyki",
        ["kawa", "herbata", "papierosy", "alkohol", "narkotyki", "słodycze", "inne"],
        key="stimulants",
        placeholder="Wybierz używki i nawyki",
    )
    stimulants_other = ""
    if "inne" in stimulants:
        stimulants_other = st.text_input("Jakie inne używki lub nawyki?", key="stimulants_other")

    sleep_hours = select_with_placeholder(
        "Ile średnio trwa sen na dobę?",
        ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
        key="sleep_hours",
    )

    travel_abroad = select_with_placeholder(
        "Czy w ciągu ostatnich 3 miesięcy był wyjazd za granicę?",
        ["tak", "nie"],
        key="travel_abroad",
    )
    travel_where = ""
    if travel_abroad == "tak":
        travel_where = st.text_input("Dokąd?", key="travel_where")

    animal_contact = select_with_placeholder(
        "Czy w ostatnich miesiącach było pogryzienie, zadrapanie lub bliski kontakt ze zwierzęciem?",
        ["tak", "nie"],
        key="animal_contact",
    )
    animal_contact_details = ""
    if animal_contact == "tak":
        animal_contact_details = st.text_area("Opisz kontakt ze zwierzęciem", key="animal_contact_details", height=90)

    major_injuries = st.text_area("Duże urazy, operacje, wypadki", key="major_injuries", height=100)

    covid = select_with_placeholder(
        "Czy wystąpiło zachorowanie na COVID-19?",
        ["tak", "nie", "nie wiem"],
        key="covid",
    )
    covid_details = ""
    if covid == "tak":
        covid_details = st.text_area("Kiedy i jaki był przebieg?", key="covid_details", height=90)

    strong_stress = st.text_area(
        "Silne reakcje stresowe lub trudne wydarzenia życiowe",
        key="strong_stress",
        height=100,
    )

# =========================================================
# 8. GINEKOLOGIA / ANDROLOGIA
# =========================================================
with st.expander("8. Ginekologia / andrologia", expanded=False):
    if sex == "kobieta":
        st.markdown("**Sekcja ginekologiczna**")
        gyn_problems = st.text_area("Problemy ginekologiczne", key="gyn_problems", height=90)
        menstruation = st.text_area("Miesiączka, menopauza, leczenie hormonalne", key="menstruation", height=90)
        first_menses = st.text_input("Pierwsza miesiączka", key="first_menses", placeholder="np. 12 r.ż.")
        last_menses = st.date_input(
            "Data ostatniej miesiączki",
            value=date.today(),
            min_value=date(1950, 1, 1),
            max_value=date.today(),
            key="last_menses",
        )
        potency = ""
        andrology_text = ""
    elif sex == "mężczyzna":
        st.markdown("**Sekcja andrologiczna**")
        potency = select_with_placeholder("Czy są problemy z erekcją?", ["nie", "czasami", "często"], key="potency")
        andrology_text = st.text_area("Inne problemy andrologiczne", key="andrology_text", height=90)
        gyn_problems = ""
        menstruation = ""
        first_menses = ""
        last_menses = None
    else:
        st.info("Sekcja pojawi się po wyborze płci kobieta albo mężczyzna.")
        gyn_problems = ""
        menstruation = ""
        first_menses = ""
        last_menses = None
        potency = ""
        andrology_text = ""

# =========================================================
# 9. NAJWAŻNIEJSZE PYTANIE
# =========================================================
with st.expander("9. Najważniejsze pytanie do lekarza", expanded=True):
    key_question = st.text_area(
        "Jakie jest najważniejsze pytanie do lekarza lub najważniejszy problem do omówienia?",
        key="key_question",
        height=120,
    )

# =========================================================
# 10. ZGODY
# =========================================================
with st.expander("10. Informacje organizacyjne i zgody", expanded=True):
    st.markdown(
        """
**Proszę przesłać wszystkie posiadane wyniki badań na adres:**  
niedzialkowski@ocenazdrowia.pl  

**lub wgrać je po zalogowaniu się na stronie:**  
https://aplikacja.medyc.pl/NiedzialkowskiPortal/#/login  

Najlepiej przesłać lub wgrać jeden plik PDF z wynikami ułożonymi chronologicznie.
"""
    )

    st.markdown('<div id="anchor_consent" class="field-anchor"></div>', unsafe_allow_html=True)
    consent_true = st.checkbox("Oświadczam, że podane informacje są prawdziwe.", key="consent_true")
    consent_visit = st.checkbox("Wyrażam zgodę na wykorzystanie tych informacji wyłącznie przez lekarza do przygotowania wizyty.", key="consent_visit")
    consent_privacy = st.checkbox("Przyjmuję do wiadomości, że formularz nie zapisuje danych w bazie aplikacji, a dokument wysyłany do lekarza zawiera ograniczone dane identyfikacyjne.", key="consent_privacy")
    contact_consent = st.checkbox("Wyrażam zgodę na kontakt telefoniczny lub mailowy w sprawach organizacyjnych związanych z wizytą.", key="contact_consent")

    if "consent" in field_errors:
        error_box(field_errors["consent"])

# =========================================================
# POSTĘP
# =========================================================
all_chosen_symptom_names = [sym for vals in selected_symptoms.values() for sym in vals]

progress_values = [
    visit_type, goal_of_assessment, first_name, last_name, phone, email, birth_date,
    sex, nationality, profession, current_status, height_cm_text, weight_kg_text,
    physical_score, mental_score, weight_change, weight_change_amount,
    health_timeline, current_meds, all_chosen_symptom_names,
    lifestyle, stimulants, stimulants_other, sleep_hours,
    travel_abroad, travel_where, animal_contact, animal_contact_details,
    major_injuries, covid, covid_details, strong_stress,
    key_question,
    consent_true, consent_visit, consent_privacy
]
progress_percent = calc_progress(progress_values)

with progress_placeholder.container():
    st.markdown("<div class='progress-box'>", unsafe_allow_html=True)
    st.write(f"**Postęp wypełniania formularza: {progress_percent}%**")
    st.progress(progress_percent / 100)
    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# PRZYCISK WYSYŁKI
# =========================================================
st.markdown('<div class="send-button">', unsafe_allow_html=True)
send_clicked = st.button("Wyślij")
st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# WALIDACJA I WYSYŁKA
# =========================================================
if send_clicked:
    st.session_state.field_errors = {}
    st.session_state.scroll_target = None

    first_name_clean = st.session_state.get("first_name", "").strip()
    last_name_clean = st.session_state.get("last_name", "").strip()
    phone_raw = st.session_state.get("phone", "").strip()
    email_raw = st.session_state.get("email", "").strip()

    validated_phone = validate_phone(phone_raw)
    validated_email = validate_email(email_raw) if email_raw else None
    full_name = f"{first_name_clean} {last_name_clean}".strip()

    if not first_name_clean:
        st.session_state.field_errors["first_name"] = "Wpisz imię."
    if not last_name_clean:
        st.session_state.field_errors["last_name"] = "Wpisz nazwisko."
    if not validated_phone:
        st.session_state.field_errors["phone"] = "Wpisz poprawny numer telefonu."
    if email_raw and not validated_email:
        st.session_state.field_errors["email"] = "Wpisz poprawny adres e-mail."
    if not consent_true or not consent_visit or not consent_privacy:
        st.session_state.field_errors["consent"] = "Zaznacz wszystkie wymagane zgody."

    anchor_order = [
        ("first_name", "anchor_first_name"),
        ("last_name", "anchor_last_name"),
        ("phone", "anchor_phone"),
        ("email", "anchor_email"),
        ("consent", "anchor_consent"),
    ]

    if st.session_state.field_errors:
        for field_key, anchor_id in anchor_order:
            if field_key in st.session_state.field_errors:
                st.session_state.scroll_target = anchor_id
                break
        st.rerun()

    patient_initials = initials(full_name)
    submitted_at = datetime.now().strftime("%d.%m.%Y, %H:%M")

    symptom_summary_rows, symptom_detail_rows, alarm_rows, system_scores = build_symptom_rows(
        selected_symptoms=selected_symptoms,
        system_symptom_meta=system_symptom_meta,
    )

    diagnosis_rows = build_diagnosis_rows(diagnoses_selected, diagnoses_other)
    family_rows = build_family_rows(family_selected, family_other)

    sex_specific_rows = []
    if sex == "kobieta":
        sex_specific_rows.extend([
            f"Problemy ginekologiczne: {gyn_problems}" if nonempty(gyn_problems) else "",
            f"Miesiączka / menopauza / hormony: {menstruation}" if nonempty(menstruation) else "",
            f"Pierwsza miesiączka: {first_menses}" if nonempty(first_menses) else "",
            f"Ostatnia miesiączka: {safe(last_menses)}" if last_menses else "",
        ])
    elif sex == "mężczyzna":
        sex_specific_rows.extend([
            f"Problemy z erekcją: {potency}" if nonempty(potency) else "",
            f"Inne problemy andrologiczne: {andrology_text}" if nonempty(andrology_text) else "",
        ])

    pdf_data = {
        "initials": patient_initials,
        "phone": validated_phone,
        "birth_date": birth_date.strftime("%d.%m.%Y"),
        "visit_type": visit_type,
        "submitted_at": submitted_at,
        "sec_goal": [goal_of_assessment],
        "sec_basic": [
            f"Płeć: {sex}" if nonempty(sex) else "",
            f"Narodowość: {nationality}" if nonempty(nationality) else "",
            f"Aktualny status: {current_status}" if nonempty(current_status) else "",
            f"Zawód: {profession}" if nonempty(profession) else "",
            f"Wzrost: {height_cm:.0f} cm" if height_cm is not None else "",
            f"Masa ciała: {weight_kg:.1f} kg" if weight_kg is not None else "",
            f"BMI: {bmi:.1f} ({bmi_label(bmi)})" if bmi is not None else "",
            f"Adres e-mail: {validated_email}" if validated_email else "",
        ],
        "sec_overall": [
            f"Ocena stanu fizycznego: {physical_score}/10",
            f"Ocena stanu psychicznego: {mental_score}/10",
            f"Zmiana masy ciała: {weight_change}" + (f", {weight_change_amount}" if nonempty(weight_change_amount) else "") if nonempty(weight_change) else "",
        ],
        "sec_timeline": [
            f"Chronologia zdrowia: {health_timeline}" if nonempty(health_timeline) else "",
            "Aktualnie przyjmowane leki:" if nonempty(current_meds) else "",
            *lines_from_text(current_meds),
        ],
        "sec_symptom_summary": symptom_summary_rows,
        "sec_alarm": alarm_rows if alarm_rows else ["Brak zaznaczonych objawów alarmowych."],
        "sec_symptom_details": symptom_detail_rows,
        "sec_diagnoses": diagnosis_rows,
        "sec_family": family_rows,
        "sec_lifestyle": [
            f"Tryb życia: {lifestyle}" if nonempty(lifestyle) else "",
            f"Używki i nawyki: {list_text(stimulants)}" if stimulants else "",
            f"Inne używki i nawyki: {stimulants_other}" if nonempty(stimulants_other) else "",
            f"Sen: {sleep_hours} godzin" if nonempty(sleep_hours) else "",
        ],
        "sec_exposures": [
            f"Wyjazd za granicę: {travel_abroad}" + (f", {travel_where}" if nonempty(travel_where) else "") if nonempty(travel_abroad) else "",
            f"Kontakt ze zwierzętami: {animal_contact}" + (f", {animal_contact_details}" if nonempty(animal_contact_details) else "") if nonempty(animal_contact) else "",
            f"Urazy / operacje / wypadki: {major_injuries}" if nonempty(major_injuries) else "",
            f"COVID-19: {covid}" + (f", {covid_details}" if nonempty(covid_details) else "") if nonempty(covid) else "",
            f"Silny stres / trudne wydarzenia: {strong_stress}" if nonempty(strong_stress) else "",
        ],
        "sec_sex_specific": sex_specific_rows,
        "sec_question": [key_question],
    }

    email_body = f"""Nowy formularz pacjenta został wysłany.

Imię i nazwisko: {full_name}
Telefon kontaktowy: {validated_phone}
Adres e-mail: {validated_email or ""}
Data urodzenia: {birth_date.strftime("%d.%m.%Y")}
Rodzaj wizyty: {visit_type}
Cel wykonania oceny zdrowia: {goal_of_assessment}
Data i godzina wypełnienia formularza: {submitted_at}
Liczba układów z objawami: {sum(1 for x in system_scores.values() if x > 0)}
Zgoda na kontakt organizacyjny: {"tak" if contact_consent else "nie"}
"""

    pdf_path = None
    try:
        with st.spinner("Trwa wysyłanie formularza..."):
            pdf_path = make_pdf(pdf_data)
            send_email_with_pdf(
                subject=f"Nowy formularz pacjenta - {full_name}",
                body_text=email_body,
                pdf_path=pdf_path,
            )

        st.session_state.field_errors = {}
        st.session_state.scroll_target = None
        st.success("Formularz został wysłany. Dziękujemy.")

    except Exception as e:
        st.error(f"Nie udało się wysłać formularza. Szczegóły: {e}")

    finally:
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass

# =========================================================
# PRZEWIJANIE DO BŁĘDU
# =========================================================
if st.session_state.scroll_target:
    scroll_to_anchor(st.session_state.scroll_target)
