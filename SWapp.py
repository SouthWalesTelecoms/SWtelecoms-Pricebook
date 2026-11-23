import streamlit as st
import pandas as pd
import math
import os
import json
import re
import hashlib
import hmac
import html as html_lib
import inspect
import base64
from pathlib import Path
from datetime import date
from fpdf import FPDF
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import numpy as np
import requests as _req
import secrets as _sec
try:
    from streamlit_drawable_canvas import st_canvas
    CANVAS_OK = True
except ImportError:
    CANVAS_OK = False


# ─── NOVALINK BRAND ──────────────────────────────────────────────────────────
# ─── PICTURES & FORMS live in the "assets" folder next to this file ───────────
# (logos, product photos, air-con photos, the Shire form). Upload that folder to GitHub once;
# after that you only ever swap this file.
ASSETS_DIR = Path(__file__).parent / "assets"
_ASSETS_MISSING = []

def _asset_bytes(rel):
    try:
        return (ASSETS_DIR / rel).read_bytes()
    except Exception:
        if rel not in _ASSETS_MISSING:
            _ASSETS_MISSING.append(rel)
        return None

def _asset_b64(rel):
    _b = _asset_bytes(rel)
    return base64.b64encode(_b).decode() if _b else ""

def _asset_ext(rel):
    _e = rel.rsplit(".", 1)[-1].lower()
    return "jpeg" if _e == "jpg" else _e

SYCOMMS_LOGO_B64 = _asset_b64("sw_logo_white.png")      # white logo for dark backgrounds
SW_LOGO_COLOUR_B64 = _asset_b64("sw_logo.png")        # colour logo for white backgrounds

st.set_page_config(
    page_title="Quotation Tool",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── EARLY CONFIG LOAD (needed for branding before login renders) ────────────
def _early_load_branding():
    """Minimal config load just to get branding for the login screen."""
    try:
        if Path("config.json").exists():
            with open("config.json") as _f:
                _c = json.load(_f)
            return _c.get("branding", {})
    except Exception:
        pass
    return {}

_early_brand = _early_load_branding()
_CO       = _early_brand.get("company_name",    "South Wales Comms")
_CO_LEGAL = _early_brand.get("company_legal",   "South Wales Comms Ltd")
_CO_TAG   = _early_brand.get("company_tagline", "South Wales Comms Pricing Tool")
_CO_CAP   = _early_brand.get("login_caption",   f"Authorised {_CO} users only.")
_CO_FOOT  = _early_brand.get("pdf_footer",      "South Wales Comms | All figures exclude VAT | This document is confidential")
_CO_PKG   = _early_brand.get("customer_pkg_label", "Your South Wales Comms Package")
_CO_FILE  = _early_brand.get("proposal_filename_prefix", "SWComms_Proposal")


# ─── MULTI-BRAND CONFIG ───────────────────────────────────────────────────────
BRAND_CONFIGS = {
    "SW Telecoms": {
        "name":       "South Wales Comms",
        "ui_accent":  "#1b78d6", "ui_accent2": "#00a7e1", "ui_rgb": "27,120,214", "mono": "SW",
        "legal":      "South Wales Comms Ltd",
        "tagline":    "South Wales Comms Pricebook",
        "caption":    "Authorised South Wales Comms users only.",
        "footer":     "South Wales Comms | All figures exclude VAT | This document is confidential",
        "pkg_label":  "Your South Wales Comms Package",
        "file_prefix":"SWComms_Proposal",
        "accent":     "#1b78d6",
        "logo_key":   "SYCOMMS_LOGO_B64",
        "header":     "<span style=\'color:#1b78d6\'>SW</span>&middot;TELECOMS",
        "pw_key":     "APP_PASSWORD",
        "address":    "10 Plas Melin, Westbourne Road, Whitchurch, Cardiff CF14 2BT",
        "email":      "support@sycomms.co.uk",
        "complaints_email": "support@sycomms.co.uk",
        "phone":      "01792 004439",
        "website":    "www.southwalestelecoms.co.uk",
        "about":      "South Wales Comms is a locally owned and operated telecoms and IT services company ",
    },
}


# ─── DESIGN SYSTEM (dark dashboard, per-brand accent) ────────────────────────
def _secret(key):
    """Read a Streamlit secret safely; missing secret (or no secrets file) returns ''."""
    try:
        return str(st.secrets.get(key, "") or "")
    except Exception:
        return ""

def esc(v):
    return html_lib.escape(str(v if v is not None else ""), quote=True)

def render_html(markup, target=None):
    # Flatten lines: indented HTML inside st.markdown becomes a code block otherwise
    (target or st).markdown("".join(l.strip() for l in markup.splitlines()), unsafe_allow_html=True)

def chip(text, tone=""):
    return f'<span class="pe-chip {tone}">{esc(text)}</span>'

def section_header(num, title, subtitle=""):
    render_html(f'<div class="pe-section"><div class="badge">{num}</div><div><div class="t">{esc(title)}</div>'
                + (f'<div class="s">{esc(subtitle)}</div>' if subtitle else "") + "</div></div>")

def _full_width():
    try:
        if "width" in inspect.signature(st.button).parameters:
            return {"width": "stretch"}
    except (TypeError, ValueError):
        pass
    return {"use_container_width": True}
FULL_WIDTH = _full_width()

# No discount sliders at South Wales Comms: everything is cost + 20%. Any slider that used to give a discount
# (or change the printer mark-up) is swapped for a fixed value and never drawn.
_SW_FIXED_SLIDERS = {"q_svc_discount": 0, "q_bb_discount": 0, "q_cs_discount": 0, "q_ac_discount": 0,
                     "c_svc_disc_w": 0, "c_bb_disc_w": 0, "c_cs_disc_w": 0, "c_ac_disc_w": 0,
                     "prn_uplift": 20, "prn_cpc_uplift": 20}
if not hasattr(st, '_sw_orig_slider'):
    st._sw_orig_slider = st.slider
_sw_real_slider = st._sw_orig_slider
def _sw_slider(*a, **k):
    _key = k.get("key")
    if _key in _SW_FIXED_SLIDERS:
        st.session_state[_key] = _SW_FIXED_SLIDERS[_key]
        return _SW_FIXED_SLIDERS[_key]
    return _sw_real_slider(*a, **k)
st.slider = _sw_slider

# Admin tables: a "sell" column is always worked out from the cost (cost + 20%), so it is shown but locked.
if not hasattr(st, '_sw_orig_editor'):
    st._sw_orig_editor = st.data_editor
_sw_real_editor = st._sw_orig_editor
def _sw_editor(data, *a, **k):
    try:
        _cols = list(getattr(data, "columns", []))
        if "sell" in _cols:
            _cc = dict(k.get("column_config") or {})
            _cc["sell"] = st.column_config.NumberColumn("Sell £ (cost + 20%, automatic)", format="%.2f", disabled=True)
            k["column_config"] = _cc
    except Exception:
        pass
    return _sw_real_editor(data, *a, **k)
st.data_editor = _sw_editor

_UI_BRAND = BRAND_CONFIGS.get(st.session_state.get("selected_brand", "SW Telecoms"), BRAND_CONFIGS["SW Telecoms"])

_APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--bg:#0A0E1A;--surface:#111827;--surface-2:#161F33;--surface-3:#1C2740;--border:rgba(148,163,184,.14);--border-strong:rgba(148,163,184,.26);--text:#E7EAF3;--muted:#8C98B0;--faint:#5E6A82;--accent:__A1__;--accent-2:__A2__;--accent-soft:rgba(__RGB__,.14);--accent-line:rgba(__RGB__,.35);--good:#34D399;--warn:#FBBF24;--risk:#FB923C;--bad:#F87171;--radius:14px;--grad:linear-gradient(135deg,__A1__ 0%,__A2__ 100%);}
html,body,[class*="css"],.stApp,button,input,textarea,select{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif!important}
.stApp{background:radial-gradient(1200px 500px at 85% -10%,rgba(__RGB__,.08),transparent 60%),radial-gradient(900px 500px at 10% -20%,rgba(__RGB__,.06),transparent 60%),var(--bg)}
[data-testid="stHeader"]{background:transparent}[data-testid="stDecoration"]{display:none}footer{visibility:hidden}[class*="viewerBadge"],[class*="_profileContainer"],[class*="_profilePreview"],a[href*="github.com/sammyatt2010"],[data-testid="appCreatorAvatar"],[data-testid="stAppDeployButton"]{display:none!important}h1>div>a,h2>div>a,h3>div>a,h4>div>a{display:none!important}[class*="viewerBadge"],[data-testid="stAppViewerBadge"],[class*="_profileContainer"],a[href*="github.com/sammyatt2010-hub"],a[href*="streamlit.io/cloud"]{display:none!important}
.block-container{padding-top:1.6rem!important;padding-bottom:3rem!important;max-width:1500px}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0D1322 0%,#0A0E1A 100%);border-right:1px solid var(--border)}
[data-testid="stSidebar"] h3{font-size:.78rem!important;font-weight:700!important;letter-spacing:.08em;text-transform:uppercase;color:var(--accent-2)!important;border-bottom:1px solid var(--border);padding-bottom:.4rem;margin-top:1.1rem!important}
[data-testid="stWidgetLabel"] p{font-size:.76rem!important;font-weight:600!important;color:var(--muted)!important;text-transform:uppercase;letter-spacing:.06em}
[data-testid="stCaptionContainer"]{color:var(--muted)!important}
.st-key-card-login,.st-key-card-hardware,.st-key-card-quote,.st-key-card-summary,.st-key-card-summary-cs,.st-key-card-summary-ac{background:linear-gradient(180deg,rgba(22,31,51,.85) 0%,rgba(17,24,39,.85) 100%);border:1px solid var(--border)!important;border-radius:var(--radius);padding:22px 22px 18px;box-shadow:0 1px 0 rgba(255,255,255,.03) inset,0 20px 40px -24px rgba(0,0,0,.6);margin-bottom:18px}
.st-key-card-summary,.st-key-card-summary-cs,.st-key-card-summary-ac{border-top:2px solid var(--accent)!important}
[data-testid="stColumn"]:has(.st-key-card-summary){position:sticky;top:1rem;align-self:flex-start}
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{background:var(--surface)!important;border:1px solid var(--border-strong)!important;border-radius:10px!important}
[data-baseweb="input"]:focus-within,[data-baseweb="select"]>div:focus-within,[data-baseweb="textarea"]:focus-within{border-color:var(--accent)!important;box-shadow:0 0 0 3px var(--accent-soft)!important}
[data-baseweb="input"]>div,[data-baseweb="base-input"]{background:transparent!important}
[data-testid="stTextInputRootElement"],[data-testid="stNumberInputContainer"],[data-testid="stTextAreaRootElement"],[data-testid="stSelectbox"] div:has(> input),[data-testid="stMultiSelect"] div:has(> input),[data-testid="stDateInput"] div:has(> input){background:var(--surface)!important;border:1px solid var(--border-strong)!important;border-radius:10px!important}
[data-testid="stTextInputRootElement"]:focus-within,[data-testid="stNumberInputContainer"]:focus-within,[data-testid="stTextAreaRootElement"]:focus-within,[data-testid="stSelectbox"] div:has(> input):focus-within,[data-testid="stMultiSelect"] div:has(> input):focus-within,[data-testid="stDateInput"] div:has(> input):focus-within{border-color:var(--accent)!important;box-shadow:0 0 0 3px var(--accent-soft)!important}
[data-testid="stMarkdownContainer"] :is(p,div,span,li,strong,em,h1,h2,h3,h4,h5,td,th):not([data-testid="stIconMaterial"]),[data-testid="stExpander"] summary p,[role="tab"] p{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif!important}
.stButton button,.stDownloadButton button,.stFormSubmitButton button,.stLinkButton a{border-radius:10px!important;font-weight:600!important;border:1px solid var(--border-strong)!important;background:var(--surface-2)!important;color:var(--text)!important;transition:all .15s ease}
.stButton button:hover,.stDownloadButton button:hover,.stLinkButton a:hover{border-color:var(--accent)!important;transform:translateY(-1px)}
.stButton button[kind="primary"],.stDownloadButton button[kind="primary"],.stFormSubmitButton button,[data-testid="stBaseButton-primary"],[data-testid="stBaseLinkButton-primary"]{background:var(--grad)!important;border:none!important;color:#0A0E1A!important;box-shadow:0 8px 24px -10px rgba(__RGB__,.8)}
.stButton button[kind="primary"] p,[data-testid="stBaseButton-primary"] p,.stFormSubmitButton button p,[data-testid="stBaseLinkButton-primary"] p{color:#0A0E1A!important;font-weight:700!important}
[data-testid="stTabs"] [role="tablist"],[data-baseweb="tab-list"]{gap:4px;background:var(--surface);padding:4px;border-radius:12px;border:1px solid var(--border);width:fit-content;max-width:100%;overflow-x:auto}
[data-testid="stTabs"] [role="tab"],[data-baseweb="tab"]{border-radius:9px!important;padding:8px 16px!important;color:var(--muted)!important;background:transparent!important}
[data-testid="stTabs"] [role="tab"][aria-selected="true"],[data-baseweb="tab"][aria-selected="true"]{background:var(--surface-3)!important;color:var(--text)!important}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"],[data-testid="stTabs"] .react-aria-SelectionIndicator{display:none!important}
[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:12px;overflow:hidden}
[data-testid="stExpander"] details{background:var(--surface);border:1px solid var(--border)!important;border-radius:12px!important}
[data-testid="stExpander"] summary:hover{color:var(--accent-2)!important}
[data-testid="stAlert"]{border-radius:12px!important}
[data-baseweb="slider"] [role="slider"]{background:var(--accent)!important;box-shadow:0 0 0 4px var(--accent-soft)!important}
[data-testid="stSliderThumbValue"]{color:var(--accent-2)!important}
[data-testid="stCheckbox"] label span:has(svg),[data-baseweb="checkbox"] span:has(svg){background-color:var(--accent)!important;border-color:var(--accent)!important}
[data-baseweb="radio"] div:first-child:has(div){border-color:var(--accent)!important}
a{color:var(--accent-2)}
hr{border-color:var(--border)!important}
/* Hero + stepper */
.pe-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;flex-wrap:wrap;padding:6px 2px 22px;margin-bottom:18px;border-bottom:1px solid var(--border)}
.pe-eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:.72rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--accent-2);margin-bottom:8px}
.pe-eyebrow .dot{width:7px;height:7px;border-radius:50%;background:var(--good);box-shadow:0 0 0 4px rgba(52,211,153,.15)}
.pe-title{font-size:2.05rem;font-weight:800;letter-spacing:-.035em;line-height:1.1;color:var(--text)}
.pe-title span{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.pe-sub{color:var(--muted);font-size:.95rem;margin-top:8px;max-width:620px}
.pe-stepper{display:flex;align-items:center;gap:6px;background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:6px}
.pe-step{display:flex;align-items:center;gap:8px;padding:7px 14px 7px 7px;border-radius:999px;font-size:.82rem;font-weight:600;color:var(--faint);white-space:nowrap}
.pe-step .num{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:.72rem;font-weight:700;border:1px solid var(--border-strong)}
.pe-step.done{color:var(--muted)}.pe-step.done .num{background:rgba(52,211,153,.14);border-color:rgba(52,211,153,.45);color:var(--good)}
.pe-step.active{background:var(--surface-3);color:var(--text)}.pe-step.active .num{background:var(--grad);border:none;color:#0A0E1A}
.pe-step-sep{width:14px;height:1px;background:var(--border-strong)}
.pe-section{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.pe-section .badge{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);font-weight:800;font-size:.85rem;border:1px solid var(--accent-line)}
.pe-section .t{font-size:1.08rem;font-weight:700;color:var(--text)}.pe-section .s{font-size:.82rem;color:var(--muted);margin-top:2px}
.pe-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:.76rem;font-weight:600;background:var(--surface-3);color:var(--text);border:1px solid var(--border);white-space:nowrap}
.pe-chip.accent{background:var(--accent-soft);color:var(--accent-2);border-color:var(--accent-line)}
.pe-chip.good{background:rgba(52,211,153,.12);color:var(--good);border-color:rgba(52,211,153,.3)}
.pe-chip.warn{background:rgba(251,191,36,.12);color:var(--warn);border-color:rgba(251,191,36,.3)}
.pe-chip.bad{background:rgba(248,113,113,.12);color:var(--bad);border-color:rgba(248,113,113,.3)}
.pe-logo{width:40px;height:40px;border-radius:12px;background:var(--grad);display:grid;place-items:center;color:#0A0E1A;font-weight:800;font-size:.9rem;letter-spacing:-.02em;overflow:hidden;box-shadow:0 10px 24px -10px rgba(__RGB__,.9)}
.pe-logo img{width:100%;height:100%;object-fit:cover}
.pe-login-head{text-align:center;margin:8vh 0 22px}.pe-login-head .pe-logo{width:54px;height:54px;margin:0 auto 16px;border-radius:16px;font-size:1.05rem}
.pe-login-head .t{font-size:1.6rem;font-weight:800;letter-spacing:-.03em;color:var(--text)}.pe-login-head .s{color:var(--muted);font-size:.92rem;margin-top:6px}
.pe-login-foot{text-align:center;color:var(--faint);font-size:.8rem;margin-top:4px}
.pe-kpi{background:var(--surface);border:1px solid var(--border);border-top:2px solid var(--accent);border-radius:14px;padding:16px 18px}
.pe-kpi .l{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.pe-kpi .v{font-size:1.8rem;font-weight:800;letter-spacing:-.03em;color:var(--text);margin-top:6px}
/* Sidebar brand block */
.pe-wide-logo{width:260px;max-width:80%;height:auto;display:block;margin:0 auto 10px}
.pe-brand{display:flex;align-items:center;gap:12px;padding:4px 0 14px;margin-bottom:6px;border-bottom:1px solid var(--border)}
.pe-brand .n{font-weight:800;font-size:1.02rem;color:var(--text);letter-spacing:-.02em}.pe-brand .g{font-size:.78rem;color:var(--muted)}
/* Product cards: light stage for product photos, accent glow when selected */
.pe-prod{border:1px solid var(--border);border-radius:12px;padding:8px;background:var(--surface);text-align:center;transition:border-color .15s ease}
.pe-prod.on{border-color:var(--accent-line);box-shadow:0 0 0 1px var(--accent-line),0 10px 26px -14px rgba(__RGB__,.9)}
.pe-prod-stage{border-radius:9px;background:radial-gradient(120% 90% at 50% 20%,#FFFFFF 0%,#EEF1F8 70%,#E3E8F2 100%);display:flex;align-items:center;justify-content:center;margin-bottom:6px;overflow:hidden}
.pe-prod-stage img{max-width:100%;object-fit:contain;filter:drop-shadow(0 6px 10px rgba(15,23,42,.18))}
.pe-prod-ph{border-radius:9px;background:var(--surface-3);display:flex;align-items:center;justify-content:center;font-size:1.8rem;margin-bottom:6px}
.pe-prod-name{font-size:.74rem;font-weight:600;color:var(--text);line-height:1.25}
.pe-prod-qty{display:inline-block;margin-top:4px;background:var(--accent-soft);color:var(--accent-2);border:1px solid var(--accent-line);border-radius:999px;padding:1px 8px;font-size:.7rem;font-weight:700}
/* Live summary */
.pe-sum-head{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.pe-sum-head .t{font-weight:700;color:var(--text);font-size:.98rem}
.pe-sum-total .l{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.pe-sum-total .v{font-size:2rem;font-weight:800;letter-spacing:-.035em;color:var(--text);line-height:1.1;margin-top:4px}
.pe-sum-total .v small{font-size:.8rem;font-weight:600;color:var(--muted);letter-spacing:0}
.pe-sum-rows{margin-top:14px;border-top:1px solid var(--border)}
.pe-sum-row{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:.86rem}
.pe-sum-row .k{color:var(--muted);white-space:nowrap}.pe-sum-row .v{color:var(--text);font-weight:600;text-align:right}
.pe-sum-foot{margin-top:12px;display:flex;flex-wrap:wrap;gap:6px}
.pe-empty{text-align:left}
.pe-empty .ic{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);border:1px solid var(--accent-line);margin-bottom:12px}
.pe-empty .t{font-weight:700;color:var(--text);margin-bottom:8px}
.pe-empty ol{margin:0;padding-left:1.1rem;color:var(--muted);font-size:.86rem;line-height:1.7}
/* Existing app classes, re-themed */
.brand-accent{color:var(--accent)}
.metric-card{background:var(--surface)!important;border:1px solid var(--border)!important;border-top:2px solid var(--accent)!important;border-radius:14px;padding:1.1rem 1.3rem;text-align:center;color:var(--text)!important}
.metric-label{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)!important;margin-bottom:.4rem}
.metric-value{font-size:1.8rem;font-weight:800;letter-spacing:-.03em;color:var(--text)!important;line-height:1.1}
.metric-value.green,.pat-good{color:var(--good)!important}.metric-value.amber,.pat-warn{color:var(--warn)!important}.metric-value.red,.pat-bad{color:var(--bad)!important}
.metric-sub{font-size:.75rem;color:var(--muted)!important;margin-top:.3rem}
.section-header{font-size:1.02rem;font-weight:700;color:var(--text);margin:1.4rem 0 .75rem;padding-bottom:.5rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.5rem}
.override-badge{background:rgba(251,191,36,.12);border:1px solid rgba(251,191,36,.35);border-radius:999px;padding:.15rem .6rem;font-size:.7rem;font-weight:700;color:var(--warn);text-transform:uppercase;letter-spacing:.05em}
.line-item-row{display:flex;justify-content:space-between;align-items:center;padding:.5rem 0;border-bottom:1px solid var(--border);font-size:.9rem}
.line-item-name{color:var(--text);flex:1}.line-item-qty{color:var(--muted);min-width:40px;text-align:center}.line-item-price{font-weight:600;color:var(--text);min-width:90px;text-align:right}
.promo-tag{background:var(--grad);color:#0A0E1A;font-size:.65rem;font-weight:700;padding:.15rem .5rem;border-radius:999px;text-transform:uppercase;letter-spacing:.06em;margin-left:.5rem}
.tab-content{padding:.6rem 0}
.warning-box,.success-box,.info-box{border-radius:12px;padding:.8rem 1rem;font-size:.86rem;margin:.5rem 0;border:1px solid}
.warning-box{background:rgba(251,191,36,.10);border-color:rgba(251,191,36,.30);color:#FDE68A}
.success-box{background:rgba(52,211,153,.10);border-color:rgba(52,211,153,.30);color:#A7F3D0}
.info-box{background:var(--accent-soft);border-color:var(--accent-line);color:var(--text)}
/* Customer View */
.cv-header{background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border:1px solid var(--border);border-top:2px solid var(--accent);border-radius:16px;padding:1.8rem 2.2rem;margin-bottom:1.5rem}
.cv-header h2{font-size:1.8rem;font-weight:800;letter-spacing:-.03em;margin:0;color:var(--text)!important}
.cv-header p{color:var(--muted);margin:.3rem 0 0;font-size:.95rem}
.cv-section{font-size:1rem;font-weight:700;color:var(--text);margin:1.5rem 0 .75rem;padding-bottom:.4rem;border-bottom:1px solid var(--border)}
.cv-hw-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px;text-align:center;height:100%}
.cv-hw-name{font-size:.8rem;font-weight:600;color:var(--text);margin-top:6px;line-height:1.3}
.cv-hw-qty{background:var(--accent-soft);color:var(--accent-2);border:1px solid var(--accent-line);border-radius:999px;padding:1px 10px;font-size:.75rem;font-weight:700;display:inline-block;margin-top:4px}
.cv-price-row{display:flex;justify-content:space-between;padding:.6rem 0;border-bottom:1px solid var(--border);font-size:.95rem}
.cv-price-label{color:var(--muted)}.cv-price-val{font-weight:600;color:var(--text)}
.cv-total-box{background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border:1px solid var(--accent-line);border-radius:14px;padding:1.5rem 2rem;margin-top:1rem;text-align:center}
.cv-total-label{color:var(--muted);font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
.cv-total-val{color:var(--text);font-size:2.5rem;font-weight:800;letter-spacing:-.035em;margin-top:.3rem}
.cv-total-note{color:var(--muted);font-size:.8rem;margin-top:.3rem}
.cv-include-item{font-size:.85rem;padding:.25rem 0;color:var(--text)}
@media (max-width:900px){.pe-hero{align-items:flex-start}.pe-stepper{flex-wrap:wrap;border-radius:16px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""
render_html("<style>" + _APP_CSS.replace("__A1__", _UI_BRAND["ui_accent"])
            .replace("__A2__", _UI_BRAND["ui_accent2"]).replace("__RGB__", _UI_BRAND["ui_rgb"]) + "</style>")

# ─── APP LOGIN GATE ──────────────────────────────────────────────────────────
# Brand passwords — add to Streamlit secrets:
#   APP_PASSWORD         = "..."   (South Wales Comms)
#   APP_PASSWORD_SWCOMMS = "..."   (SW Comms)
# Falls back to hardcoded default if secret not set.
def _get_brand_pw(pw_key):
    """Fail closed: no secret configured means nobody can sign in to that brand."""
    return _secret(pw_key)

# ── Individual user logins ───────────────────────────────────────────────────
# Users live in Streamlit Secrets under a [users."email"] table (name, role, hash, optional brand).
# Passwords are never stored - only salted PBKDF2 hashes. If no [users] table exists the app falls back
# to the old shared company password, so it can never lock you out mid-upgrade.
_DOMAIN_BRAND = {}

def _load_users():
    try:
        raw = st.secrets.get("users")
        if not raw:
            return {}
        out = {}
        for _k in raw:
            _v = raw[_k]
            out[str(_k).strip().lower()] = {
                "name":  str(_v.get("name", "") or ""),
                "role":  str(_v.get("role", "consultant") or "consultant").strip().lower(),
                "brand": str(_v.get("brand", "") or ""),
                "hash":  str(_v.get("hash", "") or ""),
                # prepared_by_company = true: this person's name never appears on the paperwork - it says "Prepared by <company>"
                "company_only": str(_v.get("prepared_by_company", False)).strip().lower() in ("true", "1", "yes"),
            }
        return out
    except Exception:
        return {}

def _verify_pw(pw, stored):
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False

_DUMMY_HASH = "pbkdf2_sha256$200000$" + "00" * 16 + "$" + "00" * 32
_USERS = _load_users()

def _maint_optout():
    return False


def _prepared_by():
    """Who the paperwork says it was prepared by: the consultant's name - or, for users set to 'prepared_by_company',
    the company currently selected (South Wales Comms), never their own name."""
    _cu = st.session_state.get("current_user") or {}
    if _cu.get("company_only"):
        return str(BRAND_CONFIGS.get(st.session_state.get("selected_brand", "SW Telecoms"), {}).get("name", "") or "").strip()
    return str(st.session_state.get("q_rep_name") or "").strip()

def _admin_own_pw_ok(entered):
    """An admin-role user can unlock the Admin / Consultant areas with their own login password."""
    _cu = st.session_state.get("current_user") or {}
    if _cu.get("role") != "admin":
        return False
    _u = _USERS.get(_cu.get("email", ""))
    return bool(_u) and _verify_pw(entered or "", _u["hash"])

if "app_authenticated" not in st.session_state:
    st.session_state.app_authenticated = False
if "selected_brand" not in st.session_state:
    st.session_state.selected_brand = "SW Telecoms"

if not st.session_state.app_authenticated:
    _sel_brand = st.session_state.selected_brand
    _bc        = BRAND_CONFIGS[_sel_brand]
    _lc, _mc, _rc = st.columns([1, 1.15, 1])
    with _mc:
        render_html(f'<div class="pe-login-head"><img class="pe-wide-logo" src="data:image/png;base64,{SYCOMMS_LOGO_B64}" alt="South Wales Comms">'
                    f'<div class="s">{esc(_bc["tagline"])}</div></div>')
        with st.container(key="card-login"):
            if _USERS:
                _em = st.text_input("Email", placeholder="you@yourcompany.co.uk", key="login_email")
                _pw = st.text_input("Password", type="password", placeholder="Enter your password",
                                    key="login_user_pw")
                if st.button("Sign in", type="primary", key="btn_sign_in_user", **FULL_WIDTH):
                    import time as _lt
                    _now = _lt.time()
                    if _now < st.session_state.get("_login_lock_until", 0):
                        st.error("Too many attempts - please wait a minute and try again.")
                    else:
                        _u = _USERS.get((_em or "").strip().lower())
                        _ok = _verify_pw(_pw or "", _u["hash"] if _u else _DUMMY_HASH) and bool(_u)
                        if _ok:
                            st.session_state["_login_fails"] = 0
                            st.session_state.current_user = {"email": (_em or "").strip().lower(),
                                                             "name": _u["name"], "role": _u["role"],
                                                             "company_only": bool(_u.get("company_only"))}
                            _dom = (_em or "").strip().lower().split("@")[-1]
                            _b = _u["brand"] if _u["brand"] in BRAND_CONFIGS else "SW Telecoms"
                            st.session_state.selected_brand = _b
                            if _u["name"] and not _u.get("company_only"):
                                st.session_state["q_rep_name"] = _u["name"]       # who is producing the deals
                            if _u["role"] == "admin":
                                st.session_state.admin_unlocked = True          # admins are already unlocked
                                st.session_state.consultant_unlocked = True
                            st.session_state.app_authenticated = True
                            st.rerun()
                        else:
                            _f = st.session_state.get("_login_fails", 0) + 1
                            st.session_state["_login_fails"] = _f
                            if _f >= 5:
                                st.session_state["_login_lock_until"] = _now + 60
                                st.session_state["_login_fails"] = 0
                            _lt.sleep(1)
                            st.error("Incorrect email or password - please try again.")
            else:
                brand_choice = _sel_brand
                entered = st.text_input("Password", type="password",
                                        placeholder="Enter the password",
                                        key="login_pw_input")
                if st.button("Sign in", type="primary", key="btn_sign_in", **FULL_WIDTH):
                    _correct_pw = _get_brand_pw(_bc["pw_key"])
                    if not _correct_pw:
                        st.error("Sign-in isn't set up yet. "
                                 f"Add {_bc['pw_key']} to the app's Secrets.")
                    elif hmac.compare_digest(entered.encode(), _correct_pw.encode()):
                        st.session_state.app_authenticated = True
                        st.rerun()
                    else:
                        st.error("Incorrect password - please try again.")
        render_html(f'<div class="pe-login-foot">{esc(_bc["caption"])}</div>')

    st.stop()   # ← nothing below renders until authenticated

# Tell the user straight away if the assets folder hasn't been uploaded next to app.py
if _ASSETS_MISSING:
    st.warning("Some pictures / forms couldn't be found, so they will be blank or unavailable. "
               "Please upload the 'assets' folder to GitHub next to app.py (missing: "
               + ", ".join(_ASSETS_MISSING[:6]) + (" ..." if len(_ASSETS_MISSING) > 6 else "") + ").")

# ─── CONFIG SYSTEM ───────────────────────────────────────────────────────────
CONFIG_FILE = "config.json"
_DEFAULT_PWD_HASH = hashlib.sha256(b"araconnect").hexdigest()

def _default_config():
    return {
        "meta": {"version": "1.0", "password_hash": _DEFAULT_PWD_HASH},
        "email": {
            "smtp_host":    "smtp.office365.com",
            "smtp_port":    587,
            "username":     "",
            "password":     "",
            "from_name":    "South Wales Comms",
            "reply_to":     "",
        },
        "branding": {
            "company_name":    "South Wales Comms",
            "company_legal":   "South Wales Comms Ltd",
            "company_tagline": "South Wales Comms Quotation Tool",
            "login_caption":   "Authorised South Wales Comms users only.",
            "pdf_footer":      "South Wales Comms | All figures exclude VAT | This document is confidential",
            "customer_pkg_label": "Your South Wales Comms Package",
            "proposal_filename_prefix": "SWComms_Proposal",
        },
        "handsets_desktop": [
            {"name": "Grandstream GRP2612W",      "buy": 42.00,  "poe": True,  "cat": "Desktop"},
            {"name": "Grandstream GRP2615",       "buy": 95.00,  "poe": True,  "cat": "Desktop"},
            {"name": "Grandstream GRP2650",       "buy": 98.00,  "poe": True,  "cat": "Desktop"},
            {"name": "Grandstream GXV3350",       "buy": 130.00, "poe": True,  "cat": "Desktop"},
            {"name": "Grandstream GXV3470",       "buy": 223.00, "poe": True,  "cat": "Desktop"},
            {"name": "Grandstream GXV3480",       "buy": 243.00, "poe": True,  "cat": "Desktop"},
            {"name": "Yealink T88 Pro",           "buy": 239.00, "poe": True,  "cat": "Desktop"},
            {"name": "Grandstream WP836 (Wi-Fi)", "buy": 88.00,  "poe": False, "cat": "Desktop"},
        ],
        "handsets_cordless": [
            {"name": "Grandstream DP720",              "buy": 35.00, "bogof": False, "cat": "DECT"},
            {"name": "Grandstream DP735 (Rugged)",     "buy": 59.00, "bogof": False, "cat": "DECT"},
            {"name": "Grandstream Dect Base Station",  "buy": 34.00, "bogof": False, "cat": "DECT"},
            {"name": "Grandstream DP760 Repeater",     "buy": 70.00, "bogof": False, "cat": "DECT"},
        ],
        "headsets": [
            {"name": "Poly Blackwire 3210 (Mono, Wired)",   "buy": 19.54},
            {"name": "Poly Blackwire 3220 (Stereo, Wired)", "buy": 29.31},
            {"name": "Yealink WH62 (Mono, Wireless)",       "buy": 97.39},
            {"name": "Yealink WH62 (Stereo, Wireless)",     "buy": 115.99},
        ],
        "other_hardware": [
            {"name": "GWN7660 WiFi AP (WiFi6)",      "buy": 58.00},
            {"name": "GWN7664E Outdoor WiFi AP",     "buy": 95.00},
            {"name": "GWN7604 Compact Switch",       "buy": 44.00},
            {"name": "Grandstream HT812 ATA",        "buy": 33.00},
            {"name": "Grandstream 4 Port ATA",       "buy": 80.00},
            {"name": "Grandstream 8 Port ATA",       "buy": 117.00},
            {"name": "Grandstream 24 Port ATA",      "buy": 300.00},
            {"name": "Grandstream GSC3518HS SIP Horn Speaker", "buy": 235.00},
            {"name": "Door Entry System",            "buy": 55.00},
            {"name": "Intercom System",              "buy": 90.00},
            {"name": "PBX Unit",                     "buy": 150.00},
            {"name": "Loud Speaker",                 "buy": 140.00},
            {"name": "CAT5 Socket & Cabling (ea)",   "buy": 65.00},
            {"name": "Broadband Router",             "buy": 65.00},
            {"name": "Bluetooth Headset",            "buy": 110.00},
            {"name": "Conference Unit (GAC250)",       "buy": 130.00, "sell": 390.00},
            {"name": "Call Scope AI Setup (one-off)",  "buy": 1000.00,"sell": 2500.00},
            {"name": "Call Answer (500 mins)",            "buy": 100.00, "sell": 149.00},
            {"name": "Website Widget",                    "buy": 30.00,  "sell": 50.00},
            {"name": "Call Scope Platform Setup",         "buy": 300.00, "sell": 500.00},
            {"name": "Call Scope AI Receptionist Setup (one-off)", "buy": 69.00, "sell": 100.00},
            {"name": "TP Link NX200 (4G/5G Standalone)",  "buy": 210.00, "sell": 630.00},
            {"name": "HIK Vision Turret 8MP",          "buy": 125.00, "sell": 427.50},
            {"name": "HIK Vision Dome 8MP",            "buy": 125.00, "sell": 400.00},
            {"name": "HIK Vision 24TB NVR",            "buy": 750.00, "sell": 1875.00},
        ],
        "switches": [
            {"name": "5-Port (4x POE)",   "buy": 29.00,  "poe_ports": 4,  "total_ports": 5},
            {"name": "8-Port (4x POE)",   "buy": 34.00,  "poe_ports": 4,  "total_ports": 8},
            {"name": "8-Port (8x POE)",   "buy": 57.00,  "poe_ports": 8,  "total_ports": 8},
            {"name": "16-Port (8x POE)",  "buy": 80.00,  "poe_ports": 8,  "total_ports": 16},
            {"name": "16-Port (16x POE)", "buy": 152.00, "poe_ports": 16, "total_ports": 16},
            {"name": "24-Port (24x POE)", "buy": 172.00, "poe_ports": 24, "total_ports": 24},
            {"name": "48-Port (32x POE)", "buy": 344.00, "poe_ports": 32, "total_ports": 48},
        ],
        "routers": [
            {"name": "Grandstream GWN7062E (FTTP)", "buy": 65.00, "sell": 200.00},
            {"name": "Draytek Vigor 2927 (FTTP/SoGEA)", "buy": 195.00},
            {"name": "Draytek 2927LAC (FTTP/Leased Line)", "buy": 386.40},
            {"name": "Zyxel DX Series (FTTP)",          "buy": 64.95},
            {"name": "TP Link NX200 (4G/5G)",           "buy": 210.00},
        ],
        "lease_rates": [
            {"months": 24, "label": "2 Year (1+23)", "rate": 46.94},
            {"months": 36, "label": "3 Year (1+35)", "rate": 35.32},
            {"months": 48, "label": "4 Year (1+47)", "rate": 27.62},
            {"months": 60, "label": "5 Year (1+59)", "rate": 23.31},
            {"months": 72, "label": "6 Year (1+71)", "rate": 19.11},
            {"months": 84, "label": "7 Year (1+83)", "rate": 18.25, "true_rate": 16.46},
        ],
        "broadband": [
            {"provider": "SW", "package": "FTTP 40/10 Unlimited",   "cost": 22.45, "sell": 35.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 80/20 Unlimited",   "cost": 29.00, "sell": 35.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 115/20 Unlimited",  "cost": 25.20, "sell": 35.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 160/30 Unlimited",  "cost": 26.48, "sell": 36.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 220/30 Unlimited",  "cost": 26.72, "sell": 37.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 330/50 Unlimited",  "cost": 34.66, "sell": 39.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 550/75 Unlimited",  "cost": 34.66, "sell": 45.00, "install": 100.00},
            {"provider": "SW", "package": "FTTP 1000/115 Unlimited","cost": 38.61, "sell": 55.00, "install": 100.00},
            {"provider": "SW", "package": "SOGEA 40/10 Unlimited",  "cost": 27.49, "sell": 30.00, "install": 122.50},
            {"provider": "SW", "package": "SOGEA 80/20 Unlimited",  "cost": 28.12, "sell": 32.00, "install": 122.50},
            {"provider": "SW", "package": "Leased Line / Other",    "cost": 0.00,   "sell": 0.00,  "install": 0.00},
        ],
        "constants": {
            "vc_cost_per_seat":    2.95,   # Professional Bundle buy cost per user/mo
            "vc_sell_per_seat":   12.00,   # Professional Bundle fixed sell price per user/mo
            "wallboard_sell":     99.00,   # Live HTML Wallboard sell price
            "wallboard_cost":      5.00,
            "cs_min_buy":          0.10,   # Call Scope minutes: our cost per minute
            "cs_min_sell":         0.25,   # Call Scope minutes: customer price per minute   # Live HTML Wallboard buy cost
            "default_service_uplift_pct": 40,
            "hw_uplift_pct":     20,       # cost + 20%
            "commission_unit_size": 1000,
            "commission_per_unit":  1000,
            "price_rise_pct":       5.0,    # Annual price increase on monthly service charges (shown as £ on the paperwork)
            "install_engineer":  450.00,   # On-site installation - per day
            "install_remote":     50.00,   # Remote installation
        }
    }

def _load_config():
    """Load config from config.json, restore images into session state, merge defaults."""
    if Path(CONFIG_FILE).exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            # Restore product images into session state if saved in config
            if "product_images" in cfg:
                imgs = {k: base64.b64decode(v) for k, v in cfg.pop("product_images").items()}
                st.session_state.uploaded_images = imgs
            # Merge with defaults so new keys are always present
            defaults = _default_config()
            for k, v in defaults.items():
                if k not in cfg:
                    cfg[k] = v
            if "constants" in defaults:
                for k, v in defaults["constants"].items():
                    cfg.setdefault("constants", {}).setdefault(k, v)
            # Merge new hardware items from defaults into existing lists
            # (so newly added catalogue items appear even with old config.json)
            for hw_key in ("handsets_desktop", "handsets_cordless", "headsets", "other_hardware", "routers"):
                if hw_key in defaults and hw_key in cfg:
                    existing_names = {d["name"] for d in cfg[hw_key] if "name" in d}
                    for item in defaults[hw_key]:
                        if item.get("name") and item["name"] not in existing_names:
                            cfg[hw_key].append(item)
            return cfg
        except Exception:
            pass
    return _default_config()

def _cfg_to_json(cfg):
    return json.dumps(cfg, indent=2, default=str)

# Persist config and images in session state
if "active_config" not in st.session_state:
    st.session_state.active_config = _load_config()
def _migrate_call_scope_prices(cfg):
    """One-off update (flagged in the config) of the Call Scope prices agreed on 13 Oct 2026."""
    if cfg.get("_cs_price_v", 0) >= 1:
        return
    new = {"AI Integration - Portal": (5.0, 32.0), "AI Integration - CRM": (5.0, 35.0),
           "Manager Dashboard": (5.0, 59.0), "Call Score": (20.0, 45.0), "AI Receptionist": (69.0, 89.0)}
    svc = cfg.setdefault("call_scope_services", [])
    for n, (b, s) in new.items():
        row = next((r for r in svc if r.get("name") == n), None)
        if row: row["buy"], row["sell"] = b, s
        else:   svc.append({"name": n, "buy": b, "sell": s})
    oh = cfg.setdefault("other_hardware", [])
    if not any(i.get("name") == "Call Scope AI Receptionist Setup (one-off)" for i in oh):
        oh.append({"name": "Call Scope AI Receptionist Setup (one-off)", "buy": 69.0, "sell": 100.0})
    cfg.setdefault("constants", {}).setdefault("cs_min_buy", 0.10)
    cfg["constants"].setdefault("cs_min_sell", 0.25)
    cfg["_cs_price_v"] = 1
def _migrate_call_scope_reseller(cfg):
    """One-off (flagged in the config): Call Scope is now sold on a reseller model - new buy prices agreed 18 Nov 2026."""
    if cfg.get("_cs_price_v", 0) >= 2:
        return
    svc = cfg.setdefault("call_scope_services", [])
    for n, (b, s) in {"AI Receptionist": (25.0, 89.0), "AI Integration - Portal": (18.0, 49.0)}.items():
        row = next((r for r in svc if r.get("name") == n), None)
        if row: row["buy"], row["sell"] = b, s
        else:   svc.append({"name": n, "buy": b, "sell": s})
    cfg["_cs_price_v"] = 2
_migrate_call_scope_prices(st.session_state.active_config)
_migrate_call_scope_reseller(st.session_state.active_config)
def _migrate_lease_84_funder(cfg):
    """One-off: 7-year funder rate 16.46 (only where no funder rate has been entered for that row)."""
    if cfg.get("_lr84_v", 0) >= 1:
        return
    for _r in cfg.get("lease_rates", []):
        if _r.get("months") == 84 and "true_rate" not in _r:
            _r["true_rate"] = 16.46
    cfg["_lr84_v"] = 1
_migrate_lease_84_funder(st.session_state.active_config)
if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False
if "consultant_unlocked" not in st.session_state:
    st.session_state.consultant_unlocked = False
if "q_loa_on" not in st.session_state:
    st.session_state["q_loa_on"] = True      # Letter of Authority ticked by default - consultants untick if not porting numbers
if "c_desired_rental" not in st.session_state:
    st.session_state.c_desired_rental = 0.0
if "c_svc_disc" not in st.session_state:
    st.session_state.c_svc_disc = 0
if "c_bb_disc" not in st.session_state:
    st.session_state.c_bb_disc = 0
if "c_cs_disc" not in st.session_state:
    st.session_state.c_cs_disc = 0
if "c_ac_disc" not in st.session_state:
    st.session_state.c_ac_disc = 0
if "c_svc_disc_w" not in st.session_state:
    st.session_state.c_svc_disc_w = 0
if "uploaded_images" not in st.session_state:
    st.session_state.uploaded_images = {}

cfg = st.session_state.active_config
SW_MARKUP = 1.20            # EVERYTHING is sold at cost + 20%
def _sw_sell(cost):
    try:
        return round(float(cost or 0) * SW_MARKUP, 2)
    except Exception:
        return 0.0

def _sw_normalise(cfg):
    """South Wales Comms sells everything at cost + 20%. Whatever sell prices are stored in the config (old saved
    config.json, edited tables) are reset here, so a sell price can never drift away from cost + 20%."""
    C_ = cfg.setdefault("constants", {})
    C_["hw_uplift_pct"] = 20
    C_["hw_uplift_upfront_pct"] = 20
    C_["commission_unit_size"] = 1000
    C_["printer_uplift_pct"] = 20
    C_["printer_cpc_uplift_pct"] = 20
    C_["default_service_uplift_pct"] = 20
    C_["vc_sell_per_seat"] = _sw_sell(C_.get("vc_cost_per_seat", 2.95))
    C_["wallboard_sell"] = _sw_sell(C_.get("wallboard_cost", 5.00))
    C_["cs_min_sell"] = _sw_sell(C_.get("cs_min_buy", 0.10))
    for _k in ("handsets_desktop", "handsets_cordless", "headsets", "other_hardware", "switches", "routers"):
        for _i in cfg.get(_k, []) or []:
            if isinstance(_i, dict) and _i.get("buy") not in (None, ""):
                try:
                    _i["sell"] = _sw_sell(_i["buy"])
                except Exception:
                    pass
    for _i in cfg.get("broadband", []) or []:
        if isinstance(_i, dict):
            _i["sell"] = _sw_sell(_i.get("cost", 0))
    for _k in ("call_scope_services", "mypa_bundles", "system_security"):
        for _i in cfg.get(_k, []) or []:
            if isinstance(_i, dict) and _i.get("buy") not in (None, ""):
                _i["sell"] = _sw_sell(_i["buy"])
    for _cat in (cfg.get("it_services") or {}).values():
        for _i in _cat.values():
            if isinstance(_i, dict) and "cost" in _i:
                _i["sell"] = _sw_sell(_i["cost"])
    _ac = cfg.setdefault("aircon", {}).setdefault("costs", {})
    _ac["install_mult"] = SW_MARKUP
    _ac["unit_size"] = 1000.0
    _ac["unit_value"] = 1000.0
    for _r in (cfg.get("aircon", {}).get("catalogue") or []):
        pass
_sw_normalise(cfg)

C   = cfg["constants"]   # shorthand for constants dict
hw_uplift_override         = 20                                  # cost + 20%
hw_uplift_upfront_override = C.get("hw_uplift_upfront_pct", 20)  # upfront purchase uplift

# ── Early rental estimate so sidebar caption is never one-rerun stale ─────────
# Reads current widget values from session state BEFORE sidebar renders.
# Mirrors the P&L cos_ex formula; keeps sidebar in sync with termination cost etc.
def _early_rental_estimate():
    """Quick rental estimate using session-state widget values (no UI needed)."""
    _term     = (float(st.session_state.get("q_term_lease", 0) or 0) + float(st.session_state.get("q_term_services", 0) or 0)) + sum(float(st.session_state.get(f"xc_amt_{_k}", 0) or 0) for _k in range(6))
    _lease    = int(st.session_state.get("q_lease_term", 36))
    _lr_map   = {24: 46.94, 36: 39.45, 48: 31.00, 60: 26.26, 72: 21.90, 84: 20.58}
    _sr       = _lr_map.get(_lease, 39.45)
    # Use stored hw_buy/sell from previous run to avoid rebuilding catalogues
    _cos_full = float(st.session_state.get("_prev_cos_full", 0))
    _base     = float(st.session_state.get("_prev_base_rental", 0))
    if _base > 0 and _cos_full > 0:
        # Adjust previous rental by change in termination cost
        _prev_term = float(st.session_state.get("_prev_termination_cost", 0))
        _delta     = _term - _prev_term
        return round(_base + (_sr / 1000.0) * _delta, 2)
    return _base

_early_est = _early_rental_estimate()
if _early_est > 0:
    st.session_state["_prev_base_rental"] = _early_est
# Store current termination cost so next rerun can compute delta
st.session_state["_prev_termination_cost"] = (float(st.session_state.get("q_term_lease", 0) or 0) + float(st.session_state.get("q_term_services", 0) or 0)) + sum(float(st.session_state.get(f"xc_amt_{_k}", 0) or 0) for _k in range(6))
_no_switch = False  # default - overridden by sidebar switch radio button
switch_quantities = {}  # for manual multi-switch mode
cctv_turret_qty = cctv_dome_qty = cctv_nvr_qty = 0  # CCTV defaults
mobile_rows = []   # default - overridden by sidebar
# Current customer cost defaults (overridden by sidebar)
current_calls = current_lines = current_bb = current_system = 0.0
current_support = current_hosted = current_onhold = current_other = current_it = 0.0
current_mobile = current_total = 0.0
current_printing = 0.0
printer_rows, printer_monthly, printer_print_est_mo, printer_count, printer_term = [], 0.0, 0.0, 0, 60
extra_costs, extra_costs_total = [], 0.0
commission_pct      = C.get("commission_pct", 25)   # fallback %
commission_unit_size = 1000   # £ of profit = 1 unit
PRICE_RISE_PCT = float(C.get("price_rise_pct", 5.0) or 0)        # annual price increase on monthly services
commission_per_unit  = C.get("commission_per_unit", 1000)   # £ per unit
# Override with appointment type rate if set
_appt_rates = {"Self Gen": 1000, "Base Deal": 600, "Acquisition": 500, "Telemarketer": 650}
commission_per_unit  = _appt_rates.get(st.session_state.get("q_appt_type", "Self Gen"), commission_per_unit)
B   = cfg.get("branding", {})     # shorthand for branding dict
# Branding helpers - refresh from full config (overrides early load)
# Apply selected brand overrides first, then let config.json further customise
_sb   = BRAND_CONFIGS.get(st.session_state.get("selected_brand", "SW Telecoms"), BRAND_CONFIGS["SW Telecoms"])
_CO       = _sb["name"]
_CO_LEGAL = _sb["legal"]
_CO_TAG   = _sb["tagline"]
_CO_CAP   = _sb["caption"]
_CO_FOOT  = _sb["footer"]
_CO_PKG   = _sb["pkg_label"]
_CO_FILE  = _sb["file_prefix"]
# Brand contact details shorthand (used throughout UI and PDFs)
_BRAND    = BRAND_CONFIGS.get(st.session_state.get("selected_brand", "SW Telecoms"), BRAND_CONFIGS["SW Telecoms"])
_CO_EMAIL = _BRAND["email"]
_CO_PHONE = _BRAND["phone"]
_CO_WEB   = _BRAND["website"]
_CO_ABOUT = _BRAND["about"]
# Let config.json further override ONLY for South Wales Comms (it's South Wales Comms-specific)
if st.session_state.get("selected_brand", "SW Telecoms") == "SW Telecoms":
    _CO       = B.get("company_name",                _CO)
    _CO_LEGAL = B.get("company_legal",               _CO_LEGAL)
    _CO_TAG   = B.get("company_tagline",             _CO_TAG)
    _CO_CAP   = B.get("login_caption",               _CO_CAP)
    _CO_FOOT  = B.get("pdf_footer",                  _CO_FOOT)
    _CO_PKG   = B.get("customer_pkg_label",          _CO_PKG)
    _CO_FILE  = B.get("proposal_filename_prefix",    _CO_FILE)

# Keys captured when saving a quote
QUOTE_KEYS = [
    "q_comp_name","q_comp_reg","q_biz_type","q_contact","q_phone",
    "q_dir_email","q_bill_email","q_address","q_employees",
    "q_deal_type","q_lease_term","q_install_type","q_install_days","q_num_sites",
    "q_bb_provider","q_bb_package","q_bb_care","q_second_fttp","q_ll_cost","q_ll_sell","q_ll_install",
    "q_bank_name","q_acc_holder","q_acc_no","q_sort_code",
    "q_bogof","q_darkweb","q_proactive","q_ooh","q_moh","q_website",
    "q_appt_type","q_svc_discount","q_bb_discount","q_cs_discount","c_svc_disc","c_bb_disc","c_cs_disc","cs_mypa","cs_website","cs_call_answer","cs_AI Integration - Portal","cs_AI Integration - CRM","cs_Manager Dashboard","cs_Call Score","cs_mins_AI Integration - Portal","cs_mins_AI Integration - CRM","sec_Bronze Security","sec_Silver Security","sec_Gold Security","q_term_lease","q_term_services","xc_desc_0","xc_amt_0","xc_desc_1","xc_amt_1","xc_desc_2","xc_amt_2","xc_desc_3","xc_amt_3","xc_desc_4","xc_amt_4","xc_desc_5","xc_amt_5","q_curr_calls","q_curr_lines","q_curr_bb","q_curr_system",
    "q_curr_support","q_curr_hosted","q_curr_onhold","q_curr_other",
    "q_rep_name","q_rep_position",
    "c_svc_disc",
]
# ── Saved quotes: capture EVERY deal input by name pattern, so new features are
#    included automatically instead of relying on a hand-kept list.
_QUOTE_PREFIXES = ("q_", "desk_", "cord_", "hs_", "oth_", "bb_extra_", "rt_qty_", "sw_qty_",
                   "mob_", "it_", "sec_", "cs_", "cctv_", "xc_", "prn_", "ac_")
_QUOTE_EXTRA = {
    "c_desired_rental", "c_svc_disc", "c_bb_disc", "c_cs_disc", "c_ac_disc", "c_notes_val",                       # consultant: target rental, discount, special conditions
    "router_mode", "switch_mode", "add_wired_ports", "standalone_softphones_key",
    "cs_ai_portal_free",
    "adm_bb_override", "adm_override_upfront", "adm_override_install", "adm_cp_json", "adm_xm_json", "adm_maint_optout",  # manager per-deal overrides
    "adm_credits_months", "adm_credits_amount", "adm_cashback", "mgr_cust", "mgr_init",
}
_QUOTE_EXCLUDE = {
    "q_sidebar_rental",                                     # display copy of the target rental (restored via sync)
    "cs_svc_apply", "cs_update", "sec_apply",               # buttons - can't be restored
    "cs_buy_input", "cs_sell_input",                        # admin catalogue price editors, not deal data
    "ac_clear_btn", "cs_target_box", "ac_target_box",   # the typing boxes - the applied figure is what's saved
}

def quote_snapshot():
    snap = {}
    for k, v in st.session_state.items():
        if k in _QUOTE_EXCLUDE or k.startswith("ac_w_") or not isinstance(v, (bool, int, float, str)):
            continue
        if k in QUOTE_KEYS or k in _QUOTE_EXTRA or k.startswith(_QUOTE_PREFIXES):
            snap[k] = v
    snap["_quote_brand"] = st.session_state.get("selected_brand", "")
    return snap


# Hardware quantity keys added dynamically after catalogues load


# ─── BUNDLED PRODUCT IMAGES (base64 JPEG, embedded for zero-config deployment) ─
BUNDLED_IMAGES = {}
for _n, _rel in {
 "Fanvil V66 Pro": "products/fanvil_v66_pro.jpg",
 "Fanvil V67": "products/fanvil_v67.jpg",
 "Fanvil V62 Pro": "products/fanvil_v62_pro.jpg",
 "Fanvil V62W": "products/fanvil_v62w.jpg",
 "Yealink T85w": "products/yealink_t85w.jpg",
 "Yealink T87w": "products/yealink_t87w.jpg",
 "Linkvil W610W": "products/linkvil_w610w.jpg",
 "Linkvil W620W (Rugged)": "products/linkvil_w620w_rugged.jpg",
 "Yealink AX83H": "products/yealink_ax83h.jpg",
 "Yealink AX86R (Rugged)": "products/yealink_ax86r_rugged.jpg",
 "Yealink W57R (Rugged)": "products/yealink_w57r_rugged.jpg",
 "Yealink W73H": "products/yealink_w73h.jpg",
 "Yealink W70B (Base)": "products/yealink_w70b_base.jpg",
 "__CS_AI__": "products/cs_ai.jpg",
 "__MYPA__": "products/mypa.jpg",
 "__GWN7062E__": "products/gwn7062e.jpg",
 "__CS_DASH__": "products/cs_dash.jpg",
 "__CS_LOGO__": "products/cs_logo.jpg",
 "PBX Unit": "products/pbx_unit.jpg",
 "Mobile App / Softphone Users": "products/mobile_app_softphone_users.jpg",
 "HIK Vision Turret 8MP": "products/hik_vision_turret_8mp.jpg",
 "HIK Vision Dome 8MP": "products/hik_vision_dome_8mp.jpg",
 "HIK Vision 24TB NVR": "products/hik_vision_24tb_nvr.jpg",
 "Grandstream GSC3518HS SIP Horn Speaker": "products/grandstream_gsc3518hs_sip_horn_speaker.jpg",
 "Grandstream HT812 ATA": "products/grandstream_ht802_ata.jpg"
}.items():
    _b = _asset_b64(_rel)
    if _b:
        BUNDLED_IMAGES[_n] = (_b, _asset_ext(_rel))


# ─── PRODUCT IMAGE MAPPING ───────────────────────────────────────────────────
# Place product images in an "images/" subfolder in the repo.
# Filenames below - add matching files to unlock real photos.
PRODUCT_IMAGES = {
    # ── Switches ─────────────────────────────────────────────────────────────
    "Switch: 5-Port (4x POE)":       "images/switch_5port.jpg",
    "Switch: 8-Port (4x POE)":       "images/switch_8port_4poe.jpg",
    "Switch: 8-Port (8x POE)":       "images/switch_8port_8poe.jpg",
    "Switch: 16-Port (8x POE)":      "images/switch_16port_8poe.jpg",
    "Switch: 16-Port (16x POE)":     "images/switch_16port_16poe.jpg",
    "Switch: 24-Port (24x POE)":     "images/switch_24port.jpg",
    "Switch: 48-Port (32x POE)":     "images/switch_48port.jpg",
    # ── Routers ──────────────────────────────────────────────────────────────
    "Draytek Vigor 2927 (FTTP/SoGEA)":      "images/draytek_vigor_2927.jpg",
    "Draytek 2927LAC (FTTP/Leased Line)":   "images/draytek_2927lac.jpg",
    "Zyxel DX Series (FTTP)":               "images/zyxel_dx.jpg",
    "TP Link NX200 (4G/5G)":                "images/tplink_nx200.jpg",
    # ── Software add-ons ──────────────────────────────────────────────────────
    "Mobile App / Softphone Users":  "images/mobile_app.jpg",
    "SW Comms Studio":               "images/sy_comms_studio.jpg",
    "Call Recording":                "images/call_recording.jpg",
    "Call Scope AI Agent":               "images/crm_ai.jpg",
    "ACD Light Agent":               "images/acd_light.jpg",
    "Click to Dial":                 "images/teams_integration.jpg",
    "Call Recording Dashboard":       "images/html_wallboard.jpg",
    # Ricoh printers - photos live in the repo's images/ folder
    "Ricoh IMC 401":                 "images/IMC 401.jpg",
    "Ricoh IMC 2010":                "images/IMC 2010.jpg",
    "Ricoh IMC 3010":                "images/IMC 3010.jpg",
    "Ricoh IMC 6010":                "images/IMC 6010.jpg",
    # ── Grandstream Desktop ───────────────────────────────────────────────────
    "Grandstream GRP2601P":    "images/grp2601p.jpg",
    "Grandstream GRP2602P":    "images/grp2602p.jpg",
    "Grandstream GRP2603P":    "images/grp2603p.jpg",
    "Grandstream GRP2615":     "images/grp2615.jpg",
    "Grandstream GRP2616":     "images/grp2616.jpg",
    "Grandstream GXV3350":     "images/gxv3350.jpg",
    "Grandstream GXV3470":     "images/gxv3470.jpg",
    "Grandstream GXV3480":     "images/gxv3480.jpg",
    # ── Grandstream DECT ──────────────────────────────────────────────────────
    "Grandstream DP720":        "images/dp720.jpg",
    "Grandstream DP722":        "images/dp722.jpg",
    "Grandstream DP730":        "images/dp730.jpg",
    "Grandstream DP750 (Base)": "images/dp750.jpg",
    "Grandstream DP752 (Base)": "images/dp752.jpg",
    "Poly Blackwire 3210 (Mono, Wired)":   "images/poly_bw3210.jpg",
    "Poly Blackwire 3220 (Stereo, Wired)": "images/poly_bw3220.jpg",
    "Yealink WH62 (Mono, Wireless)":       "images/yealink_wh62_mono.jpg",
    "Yealink WH62 (Stereo, Wireless)":     "images/yealink_wh62_stereo.jpg",
}

PRODUCT_ICONS = {
    "Desktop":    "🖥️",
    "Conference": "🎙️",
    "Wi-Fi":      "📶",
    "DECT":       "📞",
    "Wired":      "🎧",
    "Wireless":   "🎧",
}

def _norm(s):
    """Normalise a string for fuzzy image matching."""
    return "".join(c for c in s.lower() if c.isalnum())

def _image_alias(name):
    """Map product/service names to a shared bundled image.
    Order matters - most specific rules first."""
    n = (name or "").lower()
    if "my pa" in n:                              return "__MYPA__"      # Call Answer - My PA (any bundle)
    if "gwn7062e" in n:                           return "__GWN7062E__"  # Grandstream GWN7062E router
    if "manager dashboard" in n:                  return "__CS_DASH__"   # Call Scope Manager Dashboard
    if "ai integration" in n or "call scope ai" in n:
        return "__CS_AI__"                                            # AI Portal / AI CRM / minutes / AI setup
    if "call scope" in n or "call score" in n or "website widget" in n:
        return "__CS_LOGO__"                                          # everything else Call Scope
    return None


def get_product_image_b64(name):
    """Return (b64_data, ext) - checks bundled, then session upload, then images/ dir."""
    # 1. Bundled images - exact name first, then shared alias images
    if name in BUNDLED_IMAGES:
        return BUNDLED_IMAGES[name]
    _alias = _image_alias(name)
    if _alias and _alias in BUNDLED_IMAGES:
        return BUNDLED_IMAGES[_alias]
    # 2. Session-state uploaded images (fuzzy match)
    name_norm = _norm(name)
    best, best_score = None, 0
    for key, data in st.session_state.get("uploaded_images", {}).items():
        if name_norm in key or key in name_norm:
            score = len(key) / max(len(name_norm), 1)
            if score > best_score:
                best, best_score = (data, "jpeg"), score
    if best and best_score > 0.4:
        b64 = base64.b64encode(best[0]).decode()
        return b64, best[1]
    # 3. Explicit PRODUCT_IMAGES dict path
    img_path = PRODUCT_IMAGES.get(name)
    if img_path and Path(img_path).exists():
        try:
            with open(img_path, "rb") as f_:
                b64 = base64.b64encode(f_.read()).decode()
            return b64, img_path.rsplit(".", 1)[-1]
        except Exception:
            pass
    # 4. Auto-scan images/ directory with fuzzy name matching
    #    Matches any file whose name contains a key word from the product name
    img_dir = Path("images")
    if img_dir.exists():
        name_words = [w.lower() for w in name.replace("-","").replace("(","").replace(")","").split() if len(w) > 2]
        best_file, best_hits = None, 0
        for f_ in img_dir.iterdir():
            if f_.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                fname_lower = f_.stem.lower()
                hits = sum(1 for w in name_words if w in fname_lower)
                if hits > best_hits:
                    best_file, best_hits = f_, hits
        if best_file and best_hits >= 1:
            try:
                with open(best_file, "rb") as f_:
                    b64 = base64.b64encode(f_.read()).decode()
                return b64, best_file.suffix.lstrip(".")
            except Exception:
                pass
    return None, None

def product_card_html(name, info, qty=0, show_qty=False, img_height=80):
    """Product card: photo on a light stage (or icon tile), accent glow when selected."""
    b64, ext = get_product_image_b64(name)
    if b64:
        img_html = (f'<div class="pe-prod-stage" style="height:{img_height}px">'
                    f'<img src="data:image/{ext};base64,{b64}" style="height:{img_height - 10}px" alt=""></div>')
    else:
        icon = PRODUCT_ICONS.get(info.get("cat", "Desktop"), "📱")
        img_html = f'<div class="pe-prod-ph" style="height:{img_height}px">{icon}</div>'
    _sel = max([int(st.session_state.get(f"{pfx}_{name}", 0) or 0)
                for pfx in ("desk", "cord", "hs", "oth")] + [qty])
    _badge = f'<div class="pe-prod-qty">x{_sel}</div>' if _sel > 0 else ""
    return (f'<div class="pe-prod{" on" if _sel > 0 else ""}">{img_html}'
            f'<div class="pe-prod-name">{esc(name)}</div>{_badge}</div>')

def cs_card_html(label, img_name, qty=0, img_height=80):
    """Call Scope card (same look as the product cards) - a photo, the name, and a x-badge when selected."""
    b64, ext = get_product_image_b64(img_name)
    if b64:
        img_html = (f'<div class="pe-prod-stage" style="height:{img_height}px">'
                    f'<img src="data:image/{ext};base64,{b64}" style="height:{img_height - 10}px" alt=""></div>')
    else:
        img_html = f'<div class="pe-prod-ph" style="height:{img_height}px">🔮</div>'
    _badge = f'<div class="pe-prod-qty">x{int(qty)}</div>' if qty > 0 else ""
    return (f'<div class="pe-prod{" on" if qty > 0 else ""}">{img_html}'
            f'<div class="pe-prod-name">{esc(label)}</div>{_badge}</div>')


_CS_SERVICES_DEFAULT = [
    {"name": "AI Integration - Portal", "buy": 18.00,  "sell": 49.00},
    {"name": "AI Integration - CRM",    "buy": 5.00,  "sell": 35.00},
    {"name": "Manager Dashboard",        "buy": 5.00,  "sell": 59.00},
    {"name": "Call Score",               "buy": 20.00, "sell": 45.00},
    {"name": "AI Receptionist",          "buy": 25.00, "sell": 89.00},
]
CS_CARD_NAMES = ("AI Receptionist", "AI Integration - CRM")      # shown as cards under the DECT & Wireless Phones section
CS_DISPLAY_NAMES = {"AI Integration - CRM": "AI CRM Integration"}   # the name the customer sees


def cs_services_cfg():
    if "call_scope_services" not in st.session_state.active_config:
        st.session_state.active_config["call_scope_services"] = [dict(x) for x in _CS_SERVICES_DEFAULT]
    return st.session_state.active_config["call_scope_services"]

# ─── FULL PRODUCT CATALOGUE (from Excel NEW MECHANICS sheets) ────────────────

# ─── PRODUCT CATALOGUES - loaded from config (editable via Admin Panel) ────────
# Hard-coded broadband wholesale cost + customer sell rates (these win over anything saved in config.json)
BB_FIXED_RATES = {
    "FTTP 40/10 Unlimited":    (22.45, 35.00),
    "FTTP 80/20 Unlimited":    (29.00, 35.00),
    "FTTP 115/20 Unlimited":   (25.20, 35.00),
    "FTTP 160/30 Unlimited":   (26.48, 36.00),
    "FTTP 220/30 Unlimited":   (26.72, 37.00),
    "FTTP 330/50 Unlimited":   (34.66, 39.00),
    "FTTP 550/75 Unlimited":   (34.66, 45.00),
    "FTTP 1000/115 Unlimited": (38.61, 55.00),
    "SOGEA 40/10 Unlimited":   (27.49, 30.00),
    "SOGEA 80/20 Unlimited":   (28.12, 32.00),
}

def _clean_rows(rows):
    """Blank cells from the Admin tables come back as NaN - treat them as 'not set' so they can never reach a price."""
    out = []
    for r in rows or []:
        out.append({k: v for k, v in r.items() if not (isinstance(v, float) and v != v) and v is not None})
    return out

def _build_catalogues(cfg):
    cfg = dict(cfg)
    for _k in ("handsets_desktop", "handsets_cordless", "headsets", "other_hardware", "switches", "routers"):
        if _k in cfg:
            cfg[_k] = _clean_rows(cfg[_k])
    hd = {i["name"]: {k:v for k,v in i.items() if k!="name"} for i in cfg["handsets_desktop"]}
    hc = {i["name"]: {k:v for k,v in i.items() if k!="name"} for i in cfg["handsets_cordless"]}
    hs = {i["name"]: {"buy": i["buy"]}                         for i in cfg["headsets"]}
    oh = {i["name"]: {"buy": i["buy"], "sell": i.get("sell", i["buy"]*3)} for i in cfg["other_hardware"]}
    sw = cfg["switches"]
    rt = {i["name"]: i["buy"]                                  for i in cfg["routers"]}
    lr  = {i["months"]: i["rate"]                              for i in cfg["lease_rates"]}
    ltr = {i["months"]: i.get("true_rate", i["rate"]*0.8)     for i in cfg["lease_rates"]}
    ll  = {i["months"]: i["label"]                             for i in cfg["lease_rates"]}
    bb = {}
    for row in cfg["broadband"]:
        _c, _s = row["cost"], row.get("sell", 0)
        if row["provider"] == "SW" and row["package"] in BB_FIXED_RATES:
            _c = BB_FIXED_RATES[row["package"]][0]          # wholesale cost only - the sell price is always cost + 20%
        _s = round(float(_c or 0) * 1.2, 2)
        bb.setdefault(row["provider"], {})[row["package"]] = {
            "cost": _c, "sell": _s, "install": row["install"]
        }
    # "None / Customer Supplied" - zero cost/sell, appears first in selector
    bb["None / Customer Supplied"] = {
        "Customer keeps existing broadband": {"cost": 0.0, "sell": 0.0, "install": 0.0}
    }
    # 12-month rolling term - only offered when the payment model is In-house System Rental (no funder involved,
    # so these two rates are never used for money; they only stop a lookup from failing)
    lr.setdefault(12, 95.0); ltr.setdefault(12, 95.0); ll[12] = "1 Year Rolling (12 months)"
    return hd, hc, hs, oh, sw, rt, lr, ltr, ll, bb

HANDSETS_DESKTOP, HANDSETS_CORDLESS, HEADSETS, OTHER_HARDWARE, SWITCHES, ROUTERS, LEASE_RATES, TRUE_LEASE_RATES, LEASE_TERM_LABELS, BROADBAND = _build_catalogues(cfg)
# Optional fixed customer price per router (Admin - Hardware - Routers - "Customer sell £"). Blank = cost + upfront uplift.
ROUTER_SELL = {}
for _rr in _clean_rows(cfg.get("routers", [])):
    try:
        if float(_rr.get("sell", 0) or 0) > 0:
            ROUTER_SELL[_rr["name"]] = float(_rr["sell"])
    except Exception:
        pass

MOBILE_NETWORKS = {
    "EE": {
        "EE Unlimited Voice & Data":  {"cost": 7.88,  "sell": 15.00},
        "EE Data Only (Unlimited)":   {"cost": 10.35, "sell": 20.00},
    },
    "Three": {
        "3 Unlimited Voice & Data":   {"cost": 4.73,  "sell": 15.00},
        "3 Data Only (Unlimited)":    {"cost": 4.28,  "sell": 10.00},
    },
    "Vodafone": {
        "Vodafone Unlimited V&D":     {"cost": 17.00, "sell": 22.00},
        "Vodafone Data Only":         {"cost": 17.00, "sell": 22.00},
    },
    "O2": {
        "O2 Unlimited Voice & Data":  {"cost": 10.80, "sell": 15.00},
        "O2 Data Only (300GB)":       {"cost": 11.25, "sell": 15.00},
    },
}

for _n_ in MOBILE_NETWORKS.values():
    for _p_ in _n_.values():
        _p_["sell"] = round(_p_["cost"] * 1.2, 2)

_IT_SERVICES_DEFAULT = {
    "Microsoft 365": {
        "M365 Business Premium":             {"cost": 17.24},
        "M365 Business Standard + Copilot":  {"cost": 18.47},
        "M365 Business Premium + Copilot":   {"cost": 25.10},
    },
    "Exclaimer": {
        "Exclaimer Starter":  {"cost": 0.60},
        "Exclaimer Standard": {"cost": 0.71},
        "Exclaimer Pro":      {"cost": 0.73},
    },
    "Support": {
        "Support (per user)": {"cost": 25.00, "sell": 35.00},
    },
}
IT_SERVICES = st.session_state.active_config.get("it_services", _IT_SERVICES_DEFAULT)

# ─── RICOH PRINTERS ─────────────────────────────────────────────────────────
# cost = our device cost (£); cpc = our cost per print in PENCE. Leased separately on their own term.
_PRINTERS_DEFAULT = {
    "Ricoh IMC 401":  {"cost": 1249.00, "cpc": 0.33},
    "Ricoh IMC 2010": {"cost": 1997.00, "cpc": 0.26},
    "Ricoh IMC 3010": {"cost": 2751.00, "cpc": 0.26},
    "Ricoh IMC 6010": {"cost": 5832.00, "cpc": 0.26},
}
PRINTERS = st.session_state.active_config.get("printers", _PRINTERS_DEFAULT)
PRINTER_TERMS        = [24, 36, 48, 60]
PRINTER_SETUP_COST   = float(C.get("printer_setup_cost", 150.00))    # set up & delivery, per printer (our cost)
PRINTER_SETUP_CHARGE = float(C.get("printer_setup_charge", 150.00))  # what goes into the printer lease

IT_UPLIFT_PCT = 20.0  # % markup on cost price

HARDWARE_FUNDS = {"Bronze": 500, "Silver": 1000, "Gold": 1500}
SERVICE_UPLIFT = 0.40

# ─── STYLING ─────────────────────────────────────────────────────────────────


# ─── HEADER (hero is filled at the end of the script) ────────────────────────
_hero_ph = st.container(key="hero")  # keeps the old header on screen during a refresh, so the page never jumps

# ── Apply any pending quote load (must happen before widgets render) ────────────
if "_pending_quote" in st.session_state:
    _pq = st.session_state.pop("_pending_quote")
    if "q_termination" in _pq and "q_term_lease" not in _pq:     # quote saved before the two-box change
        _pq["q_term_lease"] = _pq.pop("q_termination")
    if "c_notes" in _pq and "c_notes_val" not in _pq:      # quote files saved before this change
        _pq["c_notes_val"] = _pq.pop("c_notes")
    st.session_state.pop("c_notes_w", None)                 # so the notes box refills from the loaded value
    # Clear the previous deal's admin overrides first, so nothing carries over unless the loaded deal has it
    for _k in ("adm_bb_override", "adm_override_upfront", "adm_override_install", "adm_cp_json", "adm_xm_json", "adm_maint_optout",
               "adm_credits_months", "adm_credits_amount", "adm_cashback"):
        if _k not in _pq:
            st.session_state.pop(_k, None)
    for _k in [k for k in list(st.session_state.keys()) if str(k).startswith(("cpf_", "cpx_"))]:
        st.session_state.pop(_k, None)                      # the admin price boxes refill from the loaded deal
    for _k, _v in _pq.items():
        if _k.startswith("_") or _k in _QUOTE_EXCLUDE:
            continue
        try:
            st.session_state[_k] = _v
        except Exception:
            pass   # e.g. an old file containing a button key - skip it rather than fail the load
    # Target rental: push the loaded figure into both rental boxes (sidebar + consultant view)
    st.session_state["_sync_rental_to_sidebar"] = True
    st.session_state["_sync_rental_to_cons"]    = True
    st.session_state["_sync_cs_box"] = True
    st.session_state["_sync_ac_box"] = True
    # Keep the loaded router choice (don't treat the provider change as a reason to reset it)
    st.session_state["_prev_bb_provider"] = st.session_state.get("q_bb_provider", "None / Customer Supplied")
    st.session_state["_quote_ready"] = False

# Termination calculator "use as buyout" button: apply before the buyout box is drawn
if "_pending_termination" in st.session_state:
    _pt = st.session_state.pop("_pending_termination")
    if isinstance(_pt, (tuple, list)):
        st.session_state["q_term_lease"]    = round(float(_pt[0]), 2)
        st.session_state["q_term_services"] = round(float(_pt[1]), 2)
    else:                                   # plain number: put it all in the lease box
        st.session_state["q_term_lease"]    = round(float(_pt), 2)
        st.session_state["q_term_services"] = 0.0

# ─── ZOHO CRM: look up a customer and fill in the basics (read-only) ──────────
# Secrets needed (Streamlit -> Settings -> Secrets):
#   ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN   (EU data centre unless ZOHO_DC is set)
#   Optional: ZOHO_REG_FIELD = API name of the Companies House number field on the Account
import time as _time

def _zsec(key):
    """Zoho setting: a value pasted into the Admin -> Zoho tab this session wins over Streamlit Secrets."""
    v = (st.session_state.get("_zoho_over", {}) or {}).get(key) or _secret(key)
    return "".join(str(v).split()).strip("\"'")   # drop stray spaces / line breaks / quotes from pasted values

def _zoho_dc():
    return (_zsec("ZOHO_DC") or "eu").strip().lower()

def _zoho_configured():
    return bool(_zsec("ZOHO_CLIENT_ID") and _zsec("ZOHO_CLIENT_SECRET") and _zsec("ZOHO_REFRESH_TOKEN"))

def _zoho_token():
    """Short-lived access token from the refresh token (cached for ~50 minutes)."""
    tok = st.session_state.get("_zoho_tok")
    if tok and tok[1] > _time.time():
        return tok[0]
    r = _req.post(f"https://accounts.zoho.{_zoho_dc()}/oauth/v2/token", timeout=15, data={
        "grant_type": "refresh_token", "client_id": _zsec("ZOHO_CLIENT_ID"),
        "client_secret": _zsec("ZOHO_CLIENT_SECRET"), "refresh_token": _zsec("ZOHO_REFRESH_TOKEN")})
    try:
        j = r.json()
    except Exception:
        _cid, _cs, _rt = _zsec("ZOHO_CLIENT_ID"), _zsec("ZOHO_CLIENT_SECRET"), _zsec("ZOHO_REFRESH_TOKEN")
        raise RuntimeError(f"Zoho rejected the sign-in request (status {r.status_code}, accounts.zoho.{_zoho_dc()}). "
                           f"Lengths seen - client ID {len(_cid)} (starts '{_cid[:6]}'), client secret {len(_cs)}, "
                           f"refresh token {len(_rt)} (starts '{_rt[:5]}'). A normal client ID is about 38 characters starting '1000.', "
                           f"a secret about 42, a refresh token about 70 starting '1000.'")
    if "access_token" not in j:
        raise RuntimeError(f"Zoho sign-in failed ({j.get('error', r.status_code)}) - the refresh token or client details may be wrong")
    st.session_state["_zoho_tok"] = (j["access_token"], _time.time() + 3000)
    return j["access_token"]

def _zoho_get(path, params=None):
    r = _req.get(f"https://www.zohoapis.{_zoho_dc()}/crm/v6/{path}", timeout=20, params=params or {},
                 headers={"Authorization": f"Zoho-oauthtoken {_zoho_token()}"})
    if r.status_code == 204 or not r.content:
        return {}
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"Zoho gave an unexpected reply (status {r.status_code}, from zohoapis.{_zoho_dc()}): {r.text[:120]!r}")

def zoho_search_accounts(text):
    """Accounts whose name matches the text -> list of dicts (empty list if none)."""
    reg = _secret("ZOHO_REG_FIELD")
    fields = ["Account_Name", "Phone", "Website", "Employees", "Billing_Street", "Billing_City",
              "Billing_State", "Billing_Code", "Billing_Country"] + ([reg] if reg else [])
    j = _zoho_get("Accounts/search", {"word": text, "per_page": 10})
    if j.get("code") and "data" not in j:
        raise RuntimeError(f"Zoho: {j.get('message') or j.get('code')}")
    return j.get("data", []) or []

def zoho_load_account(account_id):
    """Full Account record + its contacts. The account's own 'main contact' fields (if it has any) come first."""
    j = _zoho_get(f"Accounts/{account_id}")
    rec = (j.get("data") or [{}])[0]
    contacts = []
    # Main contact held on the account page itself (custom fields - found by name)
    def _find(*pats, need_at=False):
        for k, v in rec.items():
            kl = k.lower()
            if isinstance(v, (str, int, float)) and str(v).strip() and all(re.search(pt, kl) for pt in pats):
                if need_at and "@" not in str(v): continue
                return str(v).strip()
        return ""
    _mn, _me, _mp = _find("contact", "name"), _find("contact", "mail", need_at=True), _find("contact", "phone|mobile|number|tel")
    if _mn or _me:
        contacts.append({"Full_Name": _mn, "Email": _me, "Phone": _mp, "Title": "", "_src": "Account"})
    try:
        cj = _zoho_get(f"Accounts/{account_id}/Contacts", {"fields": "First_Name,Last_Name,Email,Title,Phone,Mobile", "per_page": 20})
        for c in (cj.get("data") or []):
            nm = f"{c.get('First_Name') or ''} {c.get('Last_Name') or ''}".strip()
            contacts.append({"Full_Name": nm, "Email": c.get("Email") or "", "Phone": c.get("Phone") or c.get("Mobile") or "",
                             "Title": c.get("Title") or "", "_src": "Contact"})
    except Exception:
        pass
    return rec, contacts

def zoho_search_leads(text):
    """Leads whose details match the text (non-converted leads only - converted ones live on as Accounts)."""
    j = _zoho_get("Leads/search", {"word": text, "per_page": 10})
    if j.get("code") and "data" not in j:
        raise RuntimeError(f"Zoho: {j.get('message') or j.get('code')}")
    out = []
    for r in (j.get("data") or []):
        r["_type"] = "Lead"
        r["Account_Name"] = r.get("Company") or r.get("Full_Name") or f"{r.get('First_Name') or ''} {r.get('Last_Name') or ''}".strip()
        r["Billing_City"] = r.get("City") or ""
        out.append(r)
    return out

def _lk(v, key="name"):
    """A Zoho lookup field comes back as {'name':..., 'id':...} (or empty)."""
    return str(v.get(key) or "") if isinstance(v, dict) else ""

def zoho_search_deals(text):
    """Deals whose details match the text -> list of dicts. Each shows the customer (the deal's Account) and the deal name."""
    j = _zoho_get("Deals/search", {"word": text, "per_page": 10})
    if j.get("code") and "data" not in j:
        raise RuntimeError(f"Zoho: {j.get('message') or j.get('code')}")
    out = []
    for r in (j.get("data") or []):
        r["_type"] = "Deal"
        r["_deal_name"] = str(r.get("Deal_Name") or "")
        r["_acct_id"] = _lk(r.get("Account_Name"), "id")
        r["_stage"] = str(r.get("Stage") or "")
        r["Account_Name"] = _lk(r.get("Account_Name")) or r["_deal_name"]
        r["Billing_City"] = ""
        out.append(r)
    return out

def zoho_load_deal(deal_id):
    """A Deal -> (customer record, contacts). Uses the deal's own Account for the company details and contacts, with the
    deal's contact first. A deal with no Account falls back to the deal's own details."""
    j = _zoho_get(f"Deals/{deal_id}")
    deal = (j.get("data") or [{}])[0]
    acct_id = _lk(deal.get("Account_Name"), "id")
    if acct_id:
        acct, contacts = zoho_load_account(acct_id)
    else:
        acct = {"Account_Name": str(deal.get("Deal_Name") or "")}
        contacts = []
    cid = _lk(deal.get("Contact_Name"), "id")
    if cid:
        try:
            c = ((_zoho_get(f"Contacts/{cid}").get("data")) or [{}])[0]
            nm = f"{c.get('First_Name') or ''} {c.get('Last_Name') or ''}".strip() or _lk(deal.get("Contact_Name"))
            dc = {"Full_Name": nm, "Email": c.get("Email") or "", "Phone": c.get("Phone") or c.get("Mobile") or "",
                  "Title": c.get("Title") or "", "_src": "Deal"}
            contacts = [dc] + [x for x in contacts if (x.get("Email") or x.get("Full_Name")) != (dc["Email"] or dc["Full_Name"])]
        except Exception:
            pass
    acct = dict(acct)
    acct["_deal"] = deal
    acct["_acct_id"] = acct_id
    return acct, contacts

def zoho_deal_info(rec):
    """(warning, context line) for a Deal - shown to the consultant, never printed on paperwork."""
    d = rec.get("_deal") or {}
    stage = str(d.get("Stage") or "")
    warn = f"This deal is marked '{stage}' in Zoho - check before quoting." if re.search(r"lost|dead|cancel", stage, re.I) else ""
    amt = d.get("Amount")
    bits = [("Deal", str(d.get("Deal_Name") or "")), ("Stage", stage),
            ("Amount", f"\u00a3{float(amt):,.2f}" if isinstance(amt, (int, float)) and amt else ""),
            ("Closing", str(d.get("Closing_Date") or "")), ("Owner", _lk(d.get("Owner")))]
    return warn, " | ".join(f"{k}: {v[:60]}" for k, v in bits if v)

def zoho_search_all(text):
    """Accounts first, then Leads -> (results, note). A Leads problem never hides the Account results."""
    res, note = [], ""
    for r in zoho_search_accounts(text):
        r["_type"] = "Account"; res.append(r)
    notes = []
    try:
        res += zoho_search_leads(text)
    except Exception as e:
        notes.append(f"Leads couldn't be searched ({e})")
    try:
        res += zoho_search_deals(text)
    except Exception as e:
        notes.append(f"Deals couldn't be searched ({e})")
    return res, " ".join(notes)

def zoho_load_lead(lead_id):
    """Full Lead record, reshaped so it fills the quote like an Account does. The lead itself is the contact."""
    j = _zoho_get(f"Leads/{lead_id}")
    rec = (j.get("data") or [{}])[0]
    def _fl(*pats, exclude=None):
        for k, v in rec.items():
            kl = re.sub(r"[^a-z0-9]", "", k.lower())
            if isinstance(v, (str, int, float)) and str(v).strip() and all(re.search(pt, kl) for pt in pats) \
               and not (exclude and re.search(exclude, kl)):
                return str(v).strip()
        return ""
    def _tidy(x): return str(x or "").strip().strip(",").strip()
    first, last = _tidy(rec.get("First_Name")), _tidy(rec.get("Last_Name"))
    name = f"{first} {last}".strip() or _tidy(rec.get("Full_Name"))
    position = _tidy(rec.get("Designation")) or _fl(r"^position$|designation|jobtitle")
    street = ", ".join(x for x in (_tidy(rec.get("Street")), _tidy(_fl(r"addressline1")), _tidy(_fl(r"addressline2")), _tidy(_fl(r"^address3$|addressline3"))) if x)
    street = ", ".join(dict.fromkeys(street.split(", "))) if street else ""
    code = _tidy(rec.get("Zip_Code")) or _fl(r"postalcode|postcode|zip")
    users = _fl(r"users")
    try: emp = int(float(re.sub(r"[^0-9.]", "", users))) if users else 0
    except Exception: emp = 0
    if emp < 1:
        try: emp = int(float(rec.get("No_of_Employees") or 0))
        except Exception: emp = 0
    acct = dict(rec)
    for k, v in (("Account_Name", _tidy(rec.get("Company"))), ("Phone", _tidy(rec.get("Phone")) or _tidy(rec.get("Mobile"))),
                 ("Billing_Street", street), ("Billing_City", _tidy(rec.get("City"))),
                 ("Billing_State", _tidy(rec.get("State")) or _fl(r"^county$")), ("Billing_Code", code),
                 ("Employees", emp if emp >= 1 else "")):
        if v not in ("", None): acct[k] = v
    contacts = [{"Full_Name": name, "Email": _tidy(rec.get("Email")), "Phone": _tidy(rec.get("Mobile")) or _tidy(rec.get("Phone")),
                 "Title": position, "_src": "Lead"}] if (name or rec.get("Email")) else []
    return acct, contacts

def zoho_lead_info(rec):
    """(warning, context line) for a Lead - shown to the consultant, never printed on paperwork."""
    def _g(*pats):
        for k, v in rec.items():
            kl = re.sub(r"[^a-z0-9]", "", k.lower())
            if isinstance(v, (str, int, float)) and str(v).strip() and any(re.search(pt, kl) for pt in pats):
                return str(v).strip()
        return ""
    status = str(rec.get("Lead_Status") or "")
    tags = " ".join(str(x.get("name", "")) if isinstance(x, dict) else str(x) for x in (rec.get("Tag") or []))
    warn = "This lead is marked '" + (status if re.search(r"not interested|dead|do not", status, re.I) else tags.strip() or status) + \
           "' in Zoho - check before quoting." if re.search(r"not interested|dead|do not contact|dnc", status + " " + tags, re.I) else ""
    bits = [("Status", status), ("Source", str(rec.get("Lead_Source") or "")), ("Current provider", _g(r"currentprovider")),
            ("Interest", _g(r"^interest")), ("Users", _g(r"^users"))]
    return warn, " | ".join(f"{k}: {v[:60]}" for k, v in bits if v)

def zoho_load_contracts(account_id):
    """Legal Contracts (custom module) linked to the account -> (list of dicts, note for the debug view)."""
    notes, mod = [], "CustomModule4"
    fmap = {}
    try:   # find the field names by their on-screen labels (needs the settings scope)
        fj = _zoho_get("settings/fields", {"module": mod})
        for f in (fj.get("fields") or []):
            lab = (f.get("field_label") or "").lower(); api = f.get("api_name")
            if not api: continue
            for key, pat in (("name", r"contract.?name|^name$"), ("amount", r"^amount|value"), ("period", r"billing.?period"),
                             ("end", r"end.?date"), ("type", r"^type")):
                if key not in fmap and re.search(pat, lab): fmap[key] = api
        if not fmap: notes.append("couldn't read field names (" + str(fj.get("code") or "empty") + ")")
    except Exception as e:
        notes.append(f"field lookup: {e}")
    guess = {"name": "Name", "amount": "Amount", "period": "Billing_Period", "end": "End_Date", "type": "Type"}
    cand_rel = []
    try:
        rj = _zoho_get("settings/related_lists", {"module": "Accounts"})
        for r in (rj.get("related_lists") or []):
            mm = r.get("module") or {}
            if (mm.get("api_name") == mod) or re.search(r"legal.?contract", str(r.get("display_label") or r.get("name") or ""), re.I):
                cand_rel.append(r.get("api_name"))
    except Exception as e:
        notes.append(f"related list lookup: {e}")
    cand_rel += [x for x in (mod, "Legal_Contracts") if x not in cand_rel]
    for rel in [c for c in cand_rel if c]:
        for fl in (list((fmap or guess).values()), [(fmap or guess).get("name", "Name")]):
            try:
                j = _zoho_get(f"Accounts/{account_id}/{rel}", {"fields": ",".join(fl), "per_page": 50})
            except Exception as e:
                notes.append(f"{rel}: {e}"); continue
            if "data" in j or not j:
                rows = []
                fm = fmap or guess
                for rec in (j.get("data") or []):
                    rows.append({"name": str(rec.get(fm.get("name", "Name")) or ""), "amount": rec.get(fm.get("amount", "Amount")),
                                 "period": str(rec.get(fm.get("period", "Billing_Period")) or ""),
                                 "end": str(rec.get(fm.get("end", "End_Date")) or ""), "type": str(rec.get(fm.get("type", "Type")) or "")})
                notes.append(f"read via {rel}, {len(rows)} contract(s)")
                return rows, "; ".join(notes)
            notes.append(f"{rel}: {j.get('code') or j.get('message') or 'no data'}")
    return [], "; ".join(notes)

def _contract_is_live_monthly(c):
    import datetime as _dt
    if "month" not in (c.get("period") or "").lower(): return False
    try:
        if float(re.sub(r"[^0-9.\-]", "", str(c.get("amount") or "")) or 0) <= 0: return False
    except Exception:
        return False
    e = c.get("end") or ""
    try:
        return _dt.date.fromisoformat(e[:10]) >= _dt.date.today() if e else True
    except Exception:
        return True

def _contract_months_left(c):
    """Whole months from today to the contract end date (0 if none / already ended)."""
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat((c.get("end") or "")[:10])
    except Exception:
        return 0
    return max(0, int(round((d - _dt.date.today()).days / 30.4375)))

def _contract_amt(c):
    try: return float(re.sub(r"[^0-9.\-]", "", str(c.get("amount") or "")) or 0)
    except Exception: return 0.0

def _zoho_fill_values(acct, contact, contract_rental=0.0, contract_settle=0.0):
    """Map a Zoho Account (+ optional contact) onto the quote's customer fields. Only non-empty values."""
    street = [str(acct.get(k) or "").strip() for k in ("Billing_Street", "Billing_City", "Billing_State", "Billing_Code")]
    _pcre = re.compile(r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}\b", re.I)
    if not _pcre.search(" ".join(street)):       # no postcode in the billing address - look for one elsewhere on the account
        _pcs = [str(acct.get(k) or "") for k in ("Shipping_Code", "Mailing_Zip", "Zip_Code", "Postcode", "Post_Code")]
        _pcs += [str(v) for k, v in acct.items() if isinstance(v, str) and re.search(r"post|zip|code", k, re.I) and k not in ("Billing_Code",)]
        _pcs += [str(v) for v in acct.values() if isinstance(v, str)]
        for _c in _pcs:
            _m = _pcre.search(_c)
            if _m: street.append(_m.group(0).upper()); break
    out = {
        "q_comp_name": str(acct.get("Account_Name") or "").strip(),
        "q_phone":     str(acct.get("Phone") or "").strip(),
        "q_address":   "\n".join(x for x in street if x),
    }
    try:
        emp = int(float(acct.get("Employees") or 0))
        if emp >= 1: out["q_employees"] = emp
    except Exception:
        pass
    # Extra account fields (found by name, ignoring spaces / underscores / capitals)
    def _num(v):
        try:
            return float(re.sub(r"[^0-9.\-]", "", str(v)) or 0)
        except Exception:
            return 0.0
    def _by_name(exact, fallback=None, skip=None):
        norm = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in acct.items() if isinstance(v, (str, int, float))}
        for e in exact:
            if e in norm and _num(norm[e]) > 0: return _num(norm[e])
        if fallback:
            for k, v in norm.items():
                if re.search(fallback, k) and not (skip and re.search(skip, k)) and _num(v) > 0: return _num(v)
        return 0.0
    _su = _by_name(["noofsystemusers", "numberofsystemusers", "systemusers"], r"system.?users|no.?of.?users")
    if _su >= 1: out["q_employees"] = int(round(_su))
    _mr = _by_name(["monthlyrental"], r"monthly.?rent")
    if _mr > 0: out["q_curr_system"] = round(_mr, 2)
    elif contract_rental and contract_rental > 0: out["q_curr_system"] = round(float(contract_rental), 2)
    _st = _by_name(["settlement", "settlementfigure", "settlementamount"], r"^settlement", r"date|status|requested")
    if _st > 0: out["q_term_lease"] = round(_st, 2)
    elif contract_settle and contract_settle > 0: out["q_term_lease"] = round(float(contract_settle), 2)
    def _find(*pats, need_at=False):
        for k, v in acct.items():
            kl = k.lower()
            if isinstance(v, (str, int, float)) and str(v).strip() and all(re.search(pt, kl) for pt in pats):
                if need_at and "@" not in str(v): continue
                return str(v).strip()
        return ""
    bill = (acct.get(_secret("ZOHO_BILLING_EMAIL_FIELD")) if _secret("ZOHO_BILLING_EMAIL_FIELD") else "") \
           or _find("bill", "mail", need_at=True)
    if bill: out["q_bill_email"] = str(bill).strip()
    reg = acct.get(_secret("ZOHO_REG_FIELD")) if _secret("ZOHO_REG_FIELD") else ""
    reg = reg or _find("companies.?house|company.?(no|num|reg)|reg.?(no|num)")
    if reg: out["q_comp_reg"] = str(reg).strip()
    if contact:
        nm, ttl = str(contact.get("Full_Name") or "").strip(), str(contact.get("Title") or "").strip()
        if nm: out["q_contact"] = f"{nm} - {ttl or 'Director'}"
        if contact.get("Email"): out["q_dir_email"] = str(contact["Email"]).strip()
        if not out.get("q_phone") and contact.get("Phone"): out["q_phone"] = str(contact["Phone"]).strip()
    return {k: v for k, v in out.items() if v not in ("", None)}

def _zoho_setup_ui(kp="_zt"):
    st.markdown("**Zoho connection** - makes a refresh token for the 'Pull customer from Zoho' feature")
    _zdc_opts = ["eu", "com", "in", "com.au", "jp"]
    _zdc = st.selectbox("Zoho data centre", _zdc_opts, index=_zdc_opts.index(_zoho_dc()) if _zoho_dc() in _zdc_opts else 0,
                        key=f"{kp}_dc", help="You use the EU one (accounts.zoho.eu).")
    st.markdown("**1. In the Zoho API Console (api-console.zoho." + _zdc + ") - Self Client - Generate Code, use this scope:**")
    st.code("ZohoCRM.modules.READ,ZohoCRM.settings.READ", language=None)
    st.caption("Read-only: the app can look up accounts, contacts and contracts but can never change anything in Zoho. "
               "Set the time duration to 10 minutes - the code only works once and expires quickly.")
    _zcid = st.text_input("Client ID", value=_secret("ZOHO_CLIENT_ID"), key=f"{kp}_cid")
    _zcs  = st.text_input("Client Secret", value="", type="password", key=f"{kp}_cs",
                          placeholder=("(Secrets holds one - " + str(len(_secret("ZOHO_CLIENT_SECRET"))) + " characters; a real secret is about 42 - paste the full one here)") if _secret("ZOHO_CLIENT_SECRET") else "paste the client secret")
    st.markdown("**2. Paste the code Zoho gives you:**")
    _zcode = st.text_input("Grant code", key=f"{kp}_code", placeholder="1000.xxxxxxxx.xxxxxxxx")
    if st.button("Create refresh token", type="primary", key=f"{kp}_make"):
        _cl = lambda s: "".join(str(s).split()).strip("\"'")
        _zcid = _cl(_zcid); _zcode = _cl(_zcode)
        _use_cs = _cl(_zcs or _secret("ZOHO_CLIENT_SECRET"))
        if not (_zcid and _use_cs and _zcode.strip()):
            st.error("Fill in the Client ID, Client Secret and the grant code first.")
        elif len(_use_cs) < 30:
            st.error(f"The Client Secret looks wrong - it is only {len(_use_cs)} characters and a real one is about 42. "
                     "I haven't sent anything to Zoho, so your grant code is still unused. Paste the full secret into the "
                     "Client Secret box (it is blank now, so the short one stored in Secrets was being used), then try again.")
        else:
            try:
                _zr = _req.post(f"https://accounts.zoho.{_zdc}/oauth/v2/token", timeout=20, data={
                    "grant_type": "authorization_code", "client_id": _zcid.strip(),
                    "client_secret": _use_cs.strip(), "code": _zcode.strip()})
                try:
                    _zj = _zr.json()
                except Exception:
                    _zj = None
                if _zj is None:
                    st.session_state[f"{kp}_result"] = None
                    st.error(f"Zoho rejected the request (status {_zr.status_code}). Lengths seen - client ID {len(_zcid)} "
                             f"(should be ~35-38, starts '1000.'), client secret {len(_use_cs)} (should be ~42), "
                             f"grant code {len(_zcode)}. Most likely the Client Secret is wrong or cut off - "
                             f"paste the full secret into the box above (it currently {'uses the one in Secrets' if not _zcs else 'uses what you typed'}).")
                elif _zj.get("refresh_token"):
                    st.session_state[f"{kp}_result"] = {"rt": _zj["refresh_token"], "cid": _zcid.strip(),
                                                      "cs": _use_cs.strip(), "dc": _zdc}
                else:
                    st.session_state[f"{kp}_result"] = None
                    st.error(f"Zoho said: {_zj.get('error', _zr.status_code)} - the code is probably used or expired. "
                             "Generate a fresh one and paste it straight away.")
            except Exception as _zte:
                st.error(f"Couldn't reach Zoho: {_zte}")
    _ztr = st.session_state.get(f"{kp}_result")
    if _ztr:
        st.success("Refresh token created. Copy it into the app's Secrets as ZOHO_REFRESH_TOKEN:")
        st.code(_ztr["rt"], language=None)
        st.code('ZOHO_CLIENT_ID = "' + _ztr["cid"] + '"\nZOHO_CLIENT_SECRET = "(your client secret)"\n'
                'ZOHO_REFRESH_TOKEN = "' + _ztr["rt"] + '"' + ('\nZOHO_DC = "' + _ztr["dc"] + '"' if _ztr["dc"] != "eu" else ""),
                language="toml")
        _zb1, _zb2 = st.columns(2)
        with _zb1:
            if st.button("Use it now (this session only)", key=f"{kp}_use"):
                st.session_state["_zoho_over"] = {"ZOHO_CLIENT_ID": _ztr["cid"], "ZOHO_CLIENT_SECRET": _ztr["cs"],
                                                  "ZOHO_REFRESH_TOKEN": _ztr["rt"], "ZOHO_DC": _ztr["dc"]}
                st.session_state.pop("_zoho_tok", None)
                st.session_state[f"{kp}_used"] = True
                st.rerun()
            if st.session_state.get(f"{kp}_used"):
                st.success("Active for this session - try 'Pull customer from Zoho' in the left panel.")
        with _zb2:
            st.caption("To keep it for everyone, paste the lines above into Streamlit -> Settings -> Secrets and save.")
    st.markdown("---")
    if st.button("Test the current Zoho connection", key=f"{kp}_test"):
        if not _zoho_configured():
            st.warning("Not connected yet - no refresh token in Secrets or created above.")
        else:
            try:
                st.session_state.pop("_zoho_tok", None)
                _zoho_token()
                st.success("Connected to Zoho - sign-in works.")
            except Exception as _zte:
                st.error(str(_zte))

# Apply a pending "fill from Zoho" before the customer widgets are drawn
if "_zoho_fill" in st.session_state:
    for _k, _v in st.session_state.pop("_zoho_fill").items():
        st.session_state[_k] = _v

# ─── COMPANIES HOUSE CREDIT CHECK (internal, read-only, public records) ───────
def _ch_get(path, params=None):
    key = _secret("COMPANIES_HOUSE_KEY")
    if not key:
        raise RuntimeError("COMPANIES_HOUSE_KEY isn't set in Streamlit Secrets yet.")
    r = _req.get("https://api.company-information.service.gov.uk" + path, params=params or {}, auth=(key, ""), timeout=20)
    if r.status_code == 404:
        return None
    if r.status_code in (401, 403):
        raise RuntimeError("Companies House refused the key - check COMPANIES_HOUSE_KEY in Secrets.")
    if r.status_code == 429:
        raise RuntimeError("Companies House is rate-limiting us - wait a minute and try again.")
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"Companies House gave an unexpected reply (status {r.status_code}).")

def ch_search(text):
    j = _ch_get("/search/companies", {"q": text, "items_per_page": 8}) or {}
    return [{"number": i.get("company_number", ""), "name": i.get("title", ""), "status": i.get("company_status", ""),
             "address": i.get("address_snippet", ""), "created": i.get("date_of_creation", "")} for i in j.get("items", [])]

def _ch_norm_number(s):
    s = re.sub(r"\s", "", str(s or "")).upper()
    return s.zfill(8) if s.isdigit() else s

def ch_assess(number):
    """Company profile + charges + officers -> {'level','headline','flags','facts'} (indicative only)."""
    import datetime as _dt
    n = _ch_norm_number(number)
    prof = _ch_get(f"/company/{n}")
    if not prof:
        raise RuntimeError(f"No company found with number {n}.")
    chg = _ch_get(f"/company/{n}/charges") or {}
    off = _ch_get(f"/company/{n}/officers", {"items_per_page": 50}) or {}
    today = _dt.date.today()
    red, amber, good, facts = [], [], [], []
    status = (prof.get("company_status") or "").lower()
    detail = (prof.get("company_status_detail") or "").lower()
    if status != "active":
        red.append(f"Company status is '{status.replace('-', ' ')}'")
    if "strike" in detail or "strike" in status:
        red.append("Strike-off action is in progress")
    if prof.get("has_insolvency_history"):
        red.append("Has an insolvency history on record")
    created = prof.get("date_of_creation")
    age_y = None
    if created:
        try:
            d = _dt.date.fromisoformat(created)
            age_y = (today - d).days / 365.25
            facts.append(f"Incorporated {d.strftime('%d %b %Y')} ({age_y:.1f} years)")
            if age_y < 1: amber.append("Less than 1 year old - very short track record")
            elif age_y < 3: amber.append("Under 3 years old - limited track record")
            else: good.append(f"Established ({age_y:.0f} years)")
        except Exception:
            pass
    acc = prof.get("accounts") or {}
    cs = prof.get("confirmation_statement") or {}
    la = (acc.get("last_accounts") or {})
    if acc.get("overdue"): amber.append("Annual accounts are OVERDUE at Companies House")
    if cs.get("overdue"): amber.append("Confirmation statement is OVERDUE")
    if acc.get("overdue") and cs.get("overdue"): red.append("Both accounts and confirmation statement are overdue")
    if not acc.get("overdue") and not cs.get("overdue"): good.append("Filings up to date")
    at = (la.get("type") or "").lower()
    if la.get("made_up_to"): facts.append(f"Last accounts made up to {la['made_up_to']} ({at.replace('-', ' ') or 'type unknown'})")
    if at == "dormant": amber.append("Last accounts were DORMANT - little or no trading shown")
    elif at in ("micro-entity", "total-exemption-small", "unaudited-abridged"):
        facts.append("Small-company accounts: balance sheet detail is limited")
    elif not la: amber.append("No accounts filed yet")
    items = chg.get("items", []) or []
    outst = [c for c in items if (c.get("status") or "").lower() == "outstanding"]
    if outst:
        lenders = []
        for c in outst:
            for pe in c.get("persons_entitled", []) or []:
                if pe.get("name") and pe["name"] not in lenders: lenders.append(pe["name"])
        _ltxt = f"{len(outst)} outstanding charge(s) / secured borrowing" + (f" - e.g. {', '.join(lenders[:2])}" if lenders else "")
        _filings_ok = not acc.get("overdue") and not cs.get("overdue")
        if age_y is not None and age_y >= 3 and _filings_ok and len(outst) <= 3:
            good.append(_ltxt + " - normal for an established business")      # routine borrowing is not a caution
        elif len(outst) >= 4:
            amber.append(_ltxt + " - several lenders, worth a closer look")
        else:
            amber.append(_ltxt)
    elif items:
        facts.append(f"{len(items)} charge(s) on record, all satisfied")
    if prof.get("registered_office_is_in_dispute"): amber.append("Registered office is in dispute")
    if prof.get("undeliverable_registered_office_address"): amber.append("Registered office address is undeliverable")
    offs = off.get("items", []) or []
    act = [o for o in offs if not o.get("resigned_on")]
    recent_res = 0
    for o in offs:
        ro = o.get("resigned_on")
        if ro:
            try:
                if (today - _dt.date.fromisoformat(ro)).days <= 365: recent_res += 1
            except Exception:
                pass
    facts.append(f"{len(act)} current officer(s)")
    if recent_res >= 2: amber.append(f"{recent_res} officers resigned in the last 12 months")
    if not act and status == "active": amber.append("No current officers listed")
    level = "red" if red else ("amber" if amber else "green")
    head = {"green": "Good - no red flags in the public record",
            "amber": "Some cautions - worth a closer look before committing",
            "red": "Serious warning signs in the public record"}[level]
    return {"level": level, "headline": head, "red": red, "amber": amber, "good": good, "facts": facts,
            "name": prof.get("company_name", ""), "number": n, "age": age_y,
            "advice": {"green": "Looks like a solid, established business - standard terms are reasonable. Public-record check only, so still rely on the funder's own checks.",
                       "amber": "Worth a closer look before committing. If the deal includes a lease and the cautions above concern you, consider a deposit or a personal guarantee from the director(s).",
                       "red": "Do not proceed without a manager's sign-off. If it goes ahead, ask for payment upfront rather than credit."}[level]}


# ─── BROADBAND AVAILABILITY (indicative, from Ofcom open postcode data in the bbdata/ folder) ──
import gzip as _gzip
_BB_DIR = Path(__file__).resolve().parent / "bbdata"
_PC_RE = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})\b", re.I)

def bb_find_postcode(text):
    m = _PC_RE.search(str(text or "").upper())
    return f"{m.group(1)} {m.group(2)}" if m else ""

def bb_meta():
    try:
        return json.loads((_BB_DIR / "meta.json").read_text())
    except Exception:
        return None

def bb_lookup(postcode):
    """-> dict of Ofcom figures for the postcode, or the average of its neighbours (flag 'area'), or None."""
    pc = re.sub(r"\s", "", str(postcode or "")).upper()
    if not re.fullmatch(r"[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2}", pc):
        return None
    f = _BB_DIR / f"{pc[0]}.csv.gz"
    if not f.exists():
        return None
    sector = pc[:-2]
    rows, exact = [], None
    with _gzip.open(f, "rt") as fh:
        head = fh.readline().strip().split(",")
        for line in fh:
            if line.startswith(pc + ","):
                exact = line.strip().split(","); break
            if line.startswith(sector):
                rows.append(line.strip().split(","))
    def conv(r):
        d = {}
        for k, v in zip(head[1:], r[1:]):
            try: d[k] = int(v)
            except Exception: d[k] = -1
        return d
    if exact:
        d = conv(exact); d["area"] = False; d["pc"] = pc; return d
    if rows:
        ds = [conv(r) for r in rows]; d = {}
        for k in head[1:]:
            vals = [x[k] for x in ds if x[k] >= 0]
            d[k] = int(round(sum(vals) / len(vals))) if vals else -1
        d["area"] = True; d["pc"] = pc; d["n"] = len(ds); return d
    return None

@st.cache_data(show_spinner=False)
def bb_exchanges():
    try:
        d = json.loads((_BB_DIR / "exchanges.json").read_text())
        return d.get("label", "Openreach build programme"), d.get("exchanges", [])
    except Exception:
        return "", []

def bb_exchange_status(e):
    """-> (colour, headline, [lines], recommendation) for one Openreach exchange row."""
    L = []
    if e.get("d"):   L.append("Openreach says it has finished the main part of its full-fibre build in this exchange area.")
    if e.get("b"):   L.append("Openreach is building full fibre in this exchange area now (coverage is growing).")
    if e.get("s"):   L.append("Openreach plans to build here within the next 12 months.")
    if e.get("f"):   L.append("Openreach plans to build here in the future (no date given).")
    if e.get("x"):   L.append("Stop-sell is active: new copper-based (FTTC / SOGEA-style) orders may be restricted on this exchange.")
    if e.get("e"):   L.append("This exchange is listed for exchange exit (copper switch-off planning).")
    if e.get("c"):   L.append("Status changed since Openreach's previous publication.")
    if not L:        L.append("Listed, but no build status is shown for this exchange.")
    if e.get("d") and not e.get("b"):
        return "#2e9e4f", "Full fibre (FTTP) build largely complete", L, "FTTP - confirm the exact address on the Openreach / Gamma checker."
    if e.get("d") or e.get("b"):
        return "#e0a000", "Full fibre partly built / still building", L, "FTTP if the address checker confirms it; otherwise SOGEA / FTTC for now."
    if e.get("x"):
        return "#e0a000", "Stop-sell active", L, "Check the address checker carefully - copper-based services may not be orderable."
    return "#c0392b", "Full fibre not yet built", L, "SOGEA / FTTC for now. Note the planned build timing above."

def bb_summary(d):
    """Plain-English assessment + recommendation from the Ofcom figures."""
    g, s = d.get("gig", -1), d.get("sfbb", -1)
    def band(x):
        return ("almost all premises" if x >= 90 else "most premises" if x >= 60 else "some premises" if x >= 25
                else "a few premises" if x >= 5 else "very few / none")
    if g >= 90:
        level, col, head = "green", "#1a9e5c", "Gigabit / full fibre is very likely available"
        rec = "Full fibre (FTTP / gigabit). Confirm the exact address on the Openreach or Gamma checker."
    elif s >= 90:
        level, col, head = "green", "#1a9e5c", "Superfast (FTTC) is almost certainly available"
        rec = "FTTC, ordered as SOGEA (no phone line needed)." + (" Full fibre is available at some premises here, so check the exact address in case FTTP can be offered." if g >= 25 else "")
    elif s >= 25 or g >= 25:
        level, col, head = "amber", "#e0a100", "Availability is patchy - check the exact address"
        rec = "SOGEA as the standard offer - but confirm on the Openreach or Gamma checker first, because not every premises here can get it."
    else:
        level, col, head = "red", "#d93636", "Very limited fixed broadband indicated"
        rec = "Check the exact address on the Openreach or Gamma checker" + (" and consider fixed wireless (4G/5G) broadband." if d.get("fwa", -1) >= 25 else ".")
    lines = []
    if g >= 0: lines.append(f"Gigabit-capable (full fibre or cable): {band(g)} ({g}%)")
    if s >= 0: lines.append(f"Superfast, 30 Mbit/s+ (FTTC / fibre / cable): {band(s)} ({s}%)")
    if d.get("ufbb100", -1) >= 0: lines.append(f"100 Mbit/s+ ultrafast: {d['ufbb100']}% of premises")
    sp = []
    if d.get("med_dl", -1) > 0: sp.append(f"median download about {d['med_dl']} Mbit/s")
    if d.get("max_dl", -1) > 0: sp.append(f"fastest seen {d['max_dl']} Mbit/s down / {d['max_ul']} up" if d.get("max_ul", -1) > 0 else f"fastest seen {d['max_dl']} Mbit/s down")
    if sp: lines.append("Speeds on this postcode (existing lines): " + ", ".join(sp))
    if d.get("fwa", -1) > 0: lines.append(f"Fixed wireless (4G/5G home broadband) possible for about {d['fwa']}% of premises")
    return level, col, head, lines, rec

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────

with st.sidebar:
    render_html(f'<div class="pe-brand" style="display:block"><img class="pe-wide-logo" style="width:100%;max-width:230px" src="data:image/png;base64,{SYCOMMS_LOGO_B64}" alt="South Wales Comms">'
                f'</div>')
    # ── Appointment Type — affects commission rate ────────────────────────────
    APPT_RATES = {"Self Gen": 1000, "Base Deal": 600, "Acquisition": 500, "Telemarketer": 650}
    appt_type = st.selectbox(
        "📋 Appointment Type",
        list(APPT_RATES.keys()),
        key="q_appt_type",
        help="Sets commission rate per unit for this deal"
    )
    _appt_rate = APPT_RATES[appt_type]
    st.markdown("---")
    with st.expander("🔎 Pull customer from Zoho", expanded=False):
        if not _zoho_configured():
            st.caption("Zoho isn't connected yet - please ask an admin (the connection is set up in the Admin panel).")
        if _zoho_configured():
            _zq = st.text_input("Company name", key="_zoho_q", placeholder="Start of the company name (accounts, leads and deals)")
            if st.button("Search Zoho", key="_zoho_search", use_container_width=True) and _zq.strip():
                try:
                    _zr_, _zn_ = zoho_search_all(_zq.strip())
                    st.session_state["_zoho_results"] = _zr_
                    st.session_state["_zoho_msg"] = _zn_ if _zr_ else ("No matching accounts, leads or deals found. " + _zn_).strip()
                except Exception as _ze:
                    st.session_state["_zoho_results"] = []
                    _zm = str(_ze)
                    st.session_state["_zoho_msg"] = (
                        "Zoho connected, but this refresh token doesn't have permission to read Accounts (it was made with a different scope). "
                        "Please ask an admin to make a new one in the Admin panel (Zoho connection) using the scope ZohoCRM.modules.READ,ZohoCRM.settings.READ." if "scope" in _zm.lower() else f"Couldn't reach Zoho: {_zm}")
            if st.session_state.get("_zoho_msg"):
                st.caption(st.session_state["_zoho_msg"])
            _zres = st.session_state.get("_zoho_results") or []
            if _zres:
                _zi = st.selectbox("Matches", range(len(_zres)), key="_zoho_pick",
                                   format_func=lambda i: (f"{_zres[i].get('Account_Name', '?')} [Deal: {_zres[i].get('_deal_name') or '-'}"
                                                          + (f" - {_zres[i].get('_stage')}" if _zres[i].get("_stage") else "") + "]")
                                                         if _zres[i].get("_type") == "Deal" else
                                                         (f"{_zres[i].get('Account_Name', '?')} [{_zres[i].get('_type', 'Account')}]"
                                                          + (f" - {_zres[i].get('Billing_City')}" if _zres[i].get("Billing_City") else "")))
                _za = _zres[_zi]
                _cache = st.session_state.setdefault("_zoho_cache", {})
                if _za["id"] not in _cache:
                    try:
                        _cache[_za["id"]] = (zoho_load_lead(_za["id"]) if _za.get("_type") == "Lead"
                                             else zoho_load_deal(_za["id"]) if _za.get("_type") == "Deal"
                                             else zoho_load_account(_za["id"]))
                    except Exception as _ze:
                        _cache[_za["id"]] = (dict(_za), [])
                        st.caption(f"Couldn't load the full account: {_ze}")
                _zrec, _zcons = _cache[_za["id"]]
                _zc = None
                _is_lead = _za.get("_type") == "Lead"
                _is_deal = _za.get("_type") == "Deal"
                if _is_deal:
                    _dw, _di = zoho_deal_info(_zrec)
                    if _dw: st.warning(_dw)
                    if _di: st.caption("Deal - " + _di)
                if _is_lead:
                    _lw, _li = zoho_lead_info(_zrec)
                    if _lw: st.warning(_lw)
                    if _li: st.caption("Lead - " + _li)
                if _zcons:
                    _ci = st.selectbox("Contact", range(len(_zcons)), key="_zoho_contact",
                                       format_func=lambda i: " - ".join(x for x in [_zcons[i].get("Full_Name") or "(no name)",
                                                                                   _zcons[i].get("Email") or ""] if x))
                    _zc = _zcons[_ci]
                else:
                    st.caption("No contact found on this lead." if _is_lead else "No contact found on this deal or its account." if _is_deal else "No contact found on this account.")
                _zcc = st.session_state.setdefault("_zoho_contracts", {})
                _zcid = (_za.get("_acct_id") or _zrec.get("_acct_id") or "") if _is_deal else _za["id"]     # a deal's contracts live on its Account
                if _zcid not in _zcc:
                    try:
                        _zcc[_zcid] = ([], "no contracts (lead or deal without an account)") if (_is_lead or not _zcid) else zoho_load_contracts(_zcid)
                    except Exception as _zce:
                        _zcc[_zcid] = ([], f"error: {_zce}")
                _zcl, _zcn = _zcc[_zcid]
                _zrent = 0.0; _zsettle = 0.0
                if _zcl:
                    _live = [i for i, c in enumerate(_zcl) if _contract_is_live_monthly(c)]
                    st.caption("Legal contracts on this account:")
                    _zsel = st.multiselect("Count as current phone-system rental (£/mo)", range(len(_zcl)), default=_live, key="_zoho_cpick",
                                           format_func=lambda i: f"{_zcl[i]['name'] or 'Contract'} - £{_contract_amt(_zcl[i]):,.2f} {_zcl[i]['period'] or ''} (ends {_zcl[i]['end'] or '?'})")
                    _zrent = sum(_contract_amt(_zcl[i]) for i in _zsel)
                    _zsettle = sum(_contract_amt(_zcl[i]) * _contract_months_left(_zcl[i]) for i in _zsel)
                    st.caption(f"Rental from contracts: £{_zrent:,.2f}/mo (only used if the account page itself has no Monthly Rental)")
                    if _zsettle > 0:
                        st.caption(f"Estimated settlement: £{_zsettle:,.2f} = monthly amount x months left to the end date "
                                   "(only used if the account page has no Settlement figure - you can edit it afterwards)")
                if st.button("Fill the quote from this lead" if _is_lead else "Fill the quote from this deal" if _is_deal else "Fill the quote from this account", key="_zoho_fill_btn", type="primary", use_container_width=True):
                    st.session_state["_zoho_fill"] = _zoho_fill_values(_zrec, _zc, _zrent, _zsettle)
                    _zf = st.session_state["_zoho_fill"]
                    _zx = [n for k, n in (("q_employees", "system users"), ("q_curr_system", "monthly rental"), ("q_term_lease", "settlement")) if k in _zf]
                    st.session_state["_zoho_msg"] = (f"Filled from {_za.get('Account_Name', 'Zoho')}"
                                                     + (f" (incl. {', '.join(_zx)})" if _zx else "") + " - check the details below.")
                    st.rerun()
                if st.checkbox("Show what Zoho holds for this account", key="_zoho_debug"):
                    st.caption("Contracts lookup: " + (_zcn or "-"))
                    st.caption("\n".join(f"{k}: {str(v)[:60]}" for k, v in _zrec.items()
                                          if isinstance(v, (str, int, float)) and str(v).strip())[:3000])
    with st.expander("🔍 Company credit check (internal)", expanded=False):
        st.caption("Public Companies House records only - indicative, not a credit score. Never shown to the customer or printed in the paperwork.")
        if not _secret("COMPANIES_HOUSE_KEY"):
            st.info("Add COMPANIES_HOUSE_KEY to Streamlit Secrets (same key as the Prospect Engine) to switch this on.")
        else:
            _chreg = _ch_norm_number(st.session_state.get("q_comp_reg", ""))
            _chname = (st.session_state.get("q_comp_name", "") or "").strip()
            _chn = _chreg if re.fullmatch(r"[A-Z]{0,2}\d{6,8}", _chreg or "") else ""
            if _chn:
                _chgo = st.button(f"Check company {_chn}", key="_ch_go", type="primary", use_container_width=True)
                if _chgo:
                    try:
                        st.session_state["_ch_report"] = ch_assess(_chn)
                    except Exception as _che:
                        st.session_state["_ch_report"] = None
                        st.error(f"Couldn't run the check: {_che}")
            elif _chname:
                if st.button("Find this company at Companies House", key="_ch_find", use_container_width=True):
                    try:
                        st.session_state["_ch_res"] = ch_search(_chname)
                        if not st.session_state["_ch_res"]: st.warning("No matching companies found.")
                    except Exception as _che:
                        st.error(f"Couldn't search: {_che}")
                _chres = st.session_state.get("_ch_res") or []
                if _chres:
                    _chi = st.selectbox("Which one?", range(len(_chres)), key="_ch_pick",
                                        format_func=lambda i: f"{_chres[i]['name']} ({_chres[i]['number']}, {_chres[i]['status']})")
                    if st.button("Check this company", key="_ch_go2", type="primary", use_container_width=True):
                        try:
                            st.session_state["_ch_report"] = ch_assess(_chres[_chi]["number"])
                            st.session_state["_zoho_fill"] = {"q_comp_reg": _chres[_chi]["number"]}
                            st.rerun()
                        except Exception as _che:
                            st.session_state["_ch_report"] = None
                            st.error(f"Couldn't run the check: {_che}")
            else:
                st.caption("Enter a company name or registration number above first.")
            _chr = st.session_state.get("_ch_report")
            if _chr:
                _col = {"green": "#1a9e5c", "amber": "#e0a100", "red": "#d93636"}[_chr["level"]]
                _lines = "".join(f"<li style='color:#d93636'>{esc(x)}</li>" for x in _chr["red"]) \
                       + "".join(f"<li style='color:#b07d00'>{esc(x)}</li>" for x in _chr["amber"]) \
                       + "".join(f"<li style='color:#1a9e5c'>{esc(x)}</li>" for x in _chr["good"])
                st.markdown(f"<div style='border-left:6px solid {_col};padding:8px 12px;border-radius:6px;background:rgba(128,128,128,.08)'>"
                            f"<b>{esc(_chr['name'])}</b> ({esc(_chr['number'])})<br>"
                            f"<span style='color:{_col};font-weight:700'>{'●'} {esc(_chr['level'].upper())}</span> - {esc(_chr['headline'])}"
                            f"<ul style='margin:6px 0 4px 16px;padding:0'>{_lines}</ul></div>", unsafe_allow_html=True)
                st.caption(" | ".join(_chr["facts"]))
                st.markdown(f"**Suggested approach:** {_chr['advice']}")
    with st.expander("📡 Broadband availability (indicative)", expanded=False):
        _bbm = bb_meta()
        if not _bbm:
            st.info("The broadband data folder (bbdata) isn't in the app yet - add it to GitHub next to app.py.")
        else:
            _apc = bb_find_postcode(st.session_state.get("q_address", ""))
            if _apc and st.session_state.get("_bb_pc_src") != _apc:       # pre-fill from the installation address
                st.session_state["_bb_pc"] = _apc
                st.session_state["_bb_pc_src"] = _apc
            _bbpc = st.text_input("Installation postcode", key="_bb_pc", placeholder="e.g. CF10 1AA")
            if _bbpc.strip():
                _bbd = bb_lookup(_bbpc)
                if not _bbd:
                    st.warning("Postcode not recognised or not in the Ofcom data. Check the format, or use the Openreach / Gamma checker.")
                else:
                    _lv, _col, _hd, _ls, _rec = bb_summary(_bbd)
                    st.markdown(f"<div style='border-left:6px solid {_col};padding:8px 12px;border-radius:6px;background:rgba(128,128,128,.08)'>"
                                f"<b>{esc(_bbd['pc'][:-3] + ' ' + _bbd['pc'][-3:])}</b><br>"
                                f"<span style='color:{_col};font-weight:700'>●</span> {esc(_hd)}"
                                f"<ul style='margin:6px 0 4px 16px;padding:0'>{''.join('<li>' + esc(x) + '</li>' for x in _ls)}</ul>"
                                f"<b>Recommended:</b> {esc(_rec)}</div>",
                                unsafe_allow_html=True)
                    if _bbd.get("area"):
                        st.caption("This exact postcode isn't in the Ofcom data (probably new), so this shows the average for nearby postcodes.")
            _exl, _exr = bb_exchanges()
            if _exr:
                _exq = st.text_input("Openreach exchange (optional)", key="_bb_ex_q",
                                     placeholder="Type the exchange name from the Openreach / Gamma checker, e.g. Huddersfield")
                if _exq.strip():
                    _q = _exq.strip().lower()
                    _hits = [x for x in _exr if _q in x["n"].lower()]
                    _hits.sort(key=lambda x: (not x["n"].lower().startswith(_q), x["n"]))
                    if not _hits:
                        st.caption("No exchange with that name in the Openreach list (it only covers Fibre First builds).")
                    else:
                        _ex = _hits[0] if len(_hits) == 1 else next((x for x in _hits if x["n"].lower() == _q), None)
                        if _ex is None:
                            _ex = st.selectbox("Matching exchanges", _hits[:50], format_func=lambda x: x["n"], key="_bb_ex_sel")
                        _xc, _xh, _xl, _xr = bb_exchange_status(_ex)
                        st.markdown(f"<div style='border-left:6px solid {_xc};padding:8px 12px;border-radius:6px;background:rgba(128,128,128,.08)'>"
                                    f"<b>{esc(_ex['n'])} exchange</b><br><span style='color:{_xc};font-weight:700'>●</span> {esc(_xh)}"
                                    f"<ul style='margin:6px 0 4px 16px;padding:0'>{''.join('<li>' + esc(x) + '</li>' for x in _xl)}</ul>"
                                    f"<b>Recommended:</b> {esc(_xr)}</div>", unsafe_allow_html=True)
                        st.caption(f"Exchange-level only (not address-specific). Source: {_exl}.")
            else:
                st.caption("Exchange look-up isn't available yet - add exchanges.json inside the bbdata folder on GitHub (next to meta.json), then reboot the app.")
            st.caption(f"Indicative only - not a guarantee for this address. Source: {_bbm.get('label', 'Ofcom')}. "
                       "Shows the share of premises on the postcode that can get each service, so confirm the exact address "
                       "on the Openreach / Gamma checker before promising a service or install date.")
    st.markdown("---")
    st.markdown("### 🏢 Customer Details")
    comp_name       = st.text_input("Company Name", placeholder="Acme Ltd", key="q_comp_name")
    comp_reg        = st.text_input("Company Reg. No.", placeholder="12345678", key="q_comp_reg")
    biz_type        = st.selectbox("Entity Type", ["Limited Company", "Sole Trader", "Partnership", "Other"], key="q_biz_type")
    contact_name    = st.text_input("Signatory Name & Position", placeholder="Jane Smith - Director", key="q_contact")
    company_phone   = st.text_input("Company Phone Number", key="q_phone")
    director_email  = st.text_input("Director's Email", key="q_dir_email")
    billing_email   = st.text_input("Billing Email", key="q_bill_email")
    install_address = st.text_area("Installation Address", height=80, key="q_address")
    num_employees   = st.number_input("No. of Employees", min_value=1, value=5, step=1, key="q_employees")

    st.markdown("### 📋 Deal Configuration")
    if (st.session_state.get("current_user") or {}).get("company_only"):
        st.text_input("Prepared by", value=_prepared_by(), disabled=True, key="q_rep_name_locked",
                      help="Your paperwork is always signed off with the company name, not a personal name.")
    else:
        st.text_input("Prepared by (consultant)", key="q_rep_name",
                      help="Filled in from your login. Shown on the paperwork so we know who produced the deal.")
    # Deal type derived from payment model selection below
    # (set after payment_model widget is rendered)
    _inh_now = "In-house" in str(st.session_state.get("q_payment_model", ""))
    _term_opts = [t for t in LEASE_TERM_LABELS.keys() if t != 12]
    if _inh_now:
        _term_opts = [12] + _term_opts            # 12-month rolling contract: in-house deals only
    elif st.session_state.get("q_lease_term") == 12:
        st.session_state["q_lease_term"] = 84     # no longer in-house: put the term back to a normal one
    lease_term = st.selectbox("Service Agreement Term", _term_opts,
                              format_func=lambda x: LEASE_TERM_LABELS[x],
                              index=(_term_opts.index(84) if 84 in _term_opts else 0), key="q_lease_term",
                              help=("A 1 Year Rolling contract is available because this is an In-house System Rental." if _inh_now else
                                    "Choose In-house System Rental as the hardware payment model to unlock the 1 Year Rolling contract."))
    install_type = st.selectbox("Installation Type", ["Engineer Install", "Remote Install", "Self Install"], key="q_install_type")
    if install_type == "Engineer Install":
        install_days = st.selectbox("Installation days", list(range(1, 11)), key="q_install_days",
                                    help="Each day of engineer installation is charged at the day rate (set in Admin).")
    else:
        install_days = 1
    payment_model = st.selectbox(
        "Hardware Payment Model",
        ["Lease (spread over contract term)", "Upfront Purchase (one-off payment)", "In-house System Rental (upfront price spread over term)"],
        key="q_payment_model",
        help="Lease: hardware on a finance lease, spread across monthly payments. Upfront: customer pays all hardware at start. In-house System Rental: the upfront price spread evenly over the service term - no finance company."
    )
    num_sites    = st.number_input("Number of Sites", min_value=1, value=1, key="q_num_sites")

    st.markdown("### 🌐 Broadband")
    _bb_providers = ["None / Customer Supplied"] + [k for k in BROADBAND.keys() if k != "None / Customer Supplied"]
    bb_provider  = st.selectbox("Provider", _bb_providers, key="q_bb_provider")
    # When the provider changes, reset the router choice to match (Auto-select when
    # there's broadband, None when there isn't). Otherwise the router setting stays
    # stuck on whatever it was when the page first loaded.
    _prev_bb_prov = st.session_state.get("_prev_bb_provider")
    if _prev_bb_prov is not None and _prev_bb_prov != bb_provider:
        st.session_state["router_mode"] = ("Auto-select" if bb_provider != "None / Customer Supplied"
                                           else "None / Customer Supplied")
    st.session_state["_prev_bb_provider"] = bb_provider
    bb_package   = st.selectbox("Package", list(BROADBAND[bb_provider].keys()), key="q_bb_package")
    if bb_provider != "None / Customer Supplied":
        bb_free_year = st.checkbox("\U0001f381 Free for first 12 months",
                                   key="q_bb_free_year",
                                   help="Shows £0/mo on customer docs then full price from month 13")
    else:
        bb_free_year = False
    # Bespoke price for Leased Line / Other
    if bb_package == "Leased Line / Other":
        _ll_col1, _ll_col2 = st.columns(2)
        with _ll_col1:
            ll_cost = st.number_input("Leased Line Cost (£/mo)", min_value=0.0, step=1.0,
                                      value=float(st.session_state.get("q_ll_cost", 0.0)),
                                      key="q_ll_cost", format="%.2f")
        with _ll_col2:
            ll_sell = round(float(ll_cost or 0) * 1.2, 2)
            st.metric("Leased Line Sell (£/mo)", f"£{ll_sell:,.2f}")
        ll_install = st.number_input("Install / Setup (£ one-off)", min_value=0.0, step=10.0,
                                     value=float(st.session_state.get("q_ll_install", 0.0)),
                                     key="q_ll_install", format="%.2f")
    else:
        ll_cost = ll_sell = ll_install = 0.0
    bb_care      = st.selectbox("Care Level", ["Standard (FOC)", "Business (+£8/mo)"], key="q_bb_care")
    # ── Additional broadband lines (multi-site) ──────────────────────────────
    extra_bb_lines = {}   # {package_name: qty}
    if bb_provider != "None / Customer Supplied":
        _extra_pkgs = [p for p in BROADBAND[bb_provider].keys() if p != "Leased Line / Other"]
        _extra_open = any(st.session_state.get(f"bb_extra_{p}", 0) > 0 for p in _extra_pkgs)
        with st.expander("➕ Additional Broadband Lines", expanded=_extra_open):
            st.caption("Extra lines on top of the main line above (e.g. other sites).")
            for _p in _extra_pkgs:
                _q = st.number_input(_p, min_value=0, max_value=50, value=0, step=1,
                                     key=f"bb_extra_{_p}")
                if _q > 0:
                    extra_bb_lines[_p] = int(_q)
    extra_bb_count  = sum(extra_bb_lines.values())
    # Legacy aliases so any older references stay safe
    second_fttp     = extra_bb_count > 0
    second_fttp_pkg = next(iter(extra_bb_lines), None)

    st.markdown("### 💰 Pricing")
    st.caption("Everything is priced at cost + 20%.")
    def _sync_sidebar_to_cons():
        st.session_state["c_svc_disc"] = st.session_state["q_svc_discount"]
    def _sync_sidebar_bb():
        st.session_state["c_bb_disc"] = st.session_state["q_bb_discount"]
    def _sync_sidebar_cs():
        st.session_state["c_cs_disc"] = st.session_state["q_cs_discount"]
    service_discount_pct = st.slider(
        "User licence discount %", 0, 50,
        value=int(st.session_state.get("c_svc_disc", 0)),
        step=5,
        help="Hosted user licences and software add-ons, up to 50%. Syncs with Consultant tab.",
        key="q_svc_discount", on_change=_sync_sidebar_to_cons
    )
    st.session_state["q_bb_discount"] = int(st.session_state.get("c_bb_disc", 0))
    st.slider("Broadband discount %", 0, 10, step=1, key="q_bb_discount", on_change=_sync_sidebar_bb,
              help="Broadband sell prices, up to 10%. Never goes below wholesale cost. Syncs with Consultant tab.")
    st.session_state["q_cs_discount"] = int(st.session_state.get("c_cs_disc", 0))
    st.slider("Call Scope discount %", 0, 80, step=5, key="q_cs_discount", on_change=_sync_sidebar_cs,
              help="Call Scope services, up to 80%. Syncs with Consultant tab.")
    def _sync_sidebar_ac():
        st.session_state["c_ac_disc"] = st.session_state["q_ac_discount"]
    st.session_state["q_ac_discount"] = int(st.session_state.get("c_ac_disc", 0))
    st.slider("Air conditioning discount %", 0, 20, step=1, key="q_ac_discount", on_change=_sync_sidebar_ac,
              help="Takes this % off the air-conditioning rental or cash price (up to 20%). Commission units drop with it. Syncs with Consultant tab.")
    # Silent floor: effective uplift never drops below 5% regardless of discount level
    service_uplift_pct = 20            # cost + 20%
    if any(int(st.session_state.get(f"prn_qty_{_pn}", 0) or 0) > 0 for _pn in PRINTERS):
        # Labels kept deliberately neutral (no "uplift" or "%") in case a customer sees the screen
        st.slider("Printer device", 20, 200, int(C.get("printer_uplift_pct", 100)), 5, key="prn_uplift")
        st.slider("Print per page", 20, 200, int(C.get("printer_cpc_uplift_pct", 100)), 5, key="prn_cpc_uplift")

    st.markdown("")
    st.markdown("**Desired Lease Rental**")
    # Only sync from consultant side when flag is set
    # Empty box = use the calculated rental. It only shows a number when a target rental is set.
    if st.session_state.pop("_sync_rental_to_sidebar", False):
        _tr = float(st.session_state.get("c_desired_rental") or 0.0)
        st.session_state["q_sidebar_rental"] = _tr if _tr > 0 else None
    _sidebar_rental = st.number_input(
        "Target Rental (£/mo)",
        min_value=0.0, value=None,
        step=10.0,
        key="q_sidebar_rental",
        placeholder="Using calculated rental",
        help="Enter a target monthly rental, then click Apply. Leave empty (or Clear) to use the calculated rental."
    )
    _sr_col1, _sr_col2 = st.columns(2)
    with _sr_col1:
        if st.button("✅ Apply", key="btn_apply_rental", use_container_width=True):
            st.session_state["c_desired_rental"]        = float(_sidebar_rental or 0.0)   # empty = calculated
            st.session_state["_sync_rental_to_cons"]    = True
            st.session_state["_sync_rental_to_sidebar"] = True
            st.rerun()
    with _sr_col2:
        if st.button("✖ Clear", key="btn_clear_rental", use_container_width=True):
            st.session_state["c_desired_rental"]        = 0.0
            st.session_state["_sync_rental_to_cons"]    = True
            st.session_state["_sync_rental_to_sidebar"] = True   # empties this box too
            st.rerun()
    # Units caption is filled in at the END of the run, from the same final figure the
    # Consultant view shows (after any services discount), so the two always match.
    _units_ph = st.container(key="units_caption")
    def _target_box(title, label, box_key, applied_key, step, ph, help_txt, tag):
        st.markdown(f"**{title}**")
        if st.session_state.pop(f"_sync_{tag}_box", False) or box_key not in st.session_state:
            _ap = float(st.session_state.get(applied_key) or 0.0)
            st.session_state[box_key] = _ap if _ap > 0 else None
        _v = st.number_input(label, min_value=0.0, value=None, step=step, key=box_key, placeholder=ph, help=help_txt)
        def _do_apply(_bk=box_key, _ak=applied_key):
            st.session_state[_ak] = float(st.session_state.get(_bk) or 0.0)
        def _do_clear(_bk=box_key, _ak=applied_key):
            st.session_state[_ak] = 0.0
            st.session_state[_bk] = None
        _c1, _c2 = st.columns(2)
        with _c1:
            st.button("✅ Apply", key=f"btn_apply_{tag}", use_container_width=True, on_click=_do_apply)
        with _c2:
            st.button("✖ Clear", key=f"btn_clear_{tag}", use_container_width=True, on_click=_do_clear)
        if float(_v or 0.0) != float(st.session_state.get(applied_key) or 0.0):
            st.caption(":orange[Not applied yet - press Apply (or Clear to go back to the calculated price).]")

    _target_box("Call Scope target rental", "Call Scope target (£/mo)", "cs_target_box", "cs_target_rental", 5.0,
                "Using standard price",
                "Type the monthly Call Scope price you want, then press Apply. Higher than standard earns more profit; lower is held at or above our buy price. Clear goes back to the standard price.", "cs")
    _cs_units_ph = st.container(key="cs_units_caption")
    _target_box("Air conditioning target rental", "Air conditioning target (£/mo)", "ac_target_box", "ac_desired_rental", 5.0,
                "Using calculated rental",
                "Type the monthly air-conditioning rental you want, then press Apply. Clear goes back to the calculated rental.", "ac")
    _ac_units_ph = st.container(key="ac_units_caption")
    _tot_units_ph = st.container(key="total_units_caption")

    st.markdown("### 🔒 Deal Adjustments (Internal Only)")
    termination_lease = st.number_input(
        "Lease terminations (£)",
        min_value=0.0, step=50.0,
        key="q_term_lease",
        help="Cost to exit the customer's existing phone system lease. Added to the lease spread - not shown to customer in the app."
    )
    termination_services = st.number_input(
        "Services terminations (£)",
        min_value=0.0, step=50.0,
        key="q_term_services",
        help="Cost to exit the customer's existing service contracts. Added to the lease spread - not shown to customer in the app."
    )
    # The total drives every existing calculation exactly as the single buyout box did
    termination_cost = round(float(termination_lease) + float(termination_services), 2)
    if termination_lease > 0 and termination_services > 0:
        st.caption(f"Total termination: £{termination_cost:,.2f}")

    # SW Add-ons moved to Licences & Add-ons expander in right column

    with st.expander("📊 Current Customer Costs", expanded=False):
        st.caption("Fill in what the customer currently pays - used in the comparison view.")
        curr_col1, curr_col2 = st.columns(2)
        with curr_col1:
            current_bb      = st.number_input("Broadband / Lines (£/mo)", 0.0, step=5.0, key="q_curr_bb")
            current_system  = st.number_input("Phone System (£/mo)",      0.0, step=5.0, key="q_curr_system")
            current_calls   = st.number_input("Call Charges (£/mo)",      0.0, step=5.0, key="q_curr_calls")
            current_it      = st.number_input("IT Services / M365 (£/mo)", 0.0, step=5.0, key="q_curr_it")
        with curr_col2:
            current_hosted  = st.number_input("Hosted User Licences (£/mo)", 0.0, step=5.0, key="q_curr_hosted")
            current_mobile  = st.number_input("Mobile (£/mo)",            0.0, step=5.0, key="q_curr_mobile")
            current_support = st.number_input("Support / Maintenance (£/mo)", 0.0, step=5.0, key="q_curr_support")
            current_other   = st.number_input("Other / Misc (£/mo)",      0.0, step=5.0, key="q_curr_other")
            current_printing = st.number_input("Printing / copiers (£/mo)", 0.0, step=5.0, key="q_curr_print",
                                               help="Current copier lease and print charges")
        current_total = current_bb + current_system + current_calls + current_mobile + current_support + current_other + current_it + current_hosted + current_printing

    _xc_open = any(float(st.session_state.get(f"xc_amt_{_i}", 0) or 0) > 0 for _i in range(6))
    with st.expander("🔒 Additional Costs (Internal)", expanded=_xc_open):
        st.caption("Anything out of scope we need to cover, e.g. a long cable run, scaffold hire or a site survey. "
                   "Added to our lease costings and never shown to the customer.")
        extra_costs = []
        for _i in range(6):
            if _i > 0 and not (float(st.session_state.get(f"xc_amt_{_i-1}", 0) or 0) > 0
                               or str(st.session_state.get(f"xc_desc_{_i-1}", "")).strip()):
                break   # show the next row only once the previous one is used
            _xc1, _xc2 = st.columns([1.5, 1])
            _xd = _xc1.text_input("Description", key=f"xc_desc_{_i}", placeholder="e.g. Scaffold hire",
                                  label_visibility="visible" if _i == 0 else "collapsed")
            _xa = _xc2.number_input("Cost (£)", min_value=0.0, step=25.0, key=f"xc_amt_{_i}",
                                    label_visibility="visible" if _i == 0 else "collapsed")
            if _xa > 0:
                extra_costs.append((_xd.strip() or "Additional cost", float(_xa)))
        extra_costs_total = round(sum(_a for _, _a in extra_costs), 2)
        if extra_costs_total > 0:
            if "In-house" in payment_model:
                st.caption(f"Total £{extra_costs_total:,.2f}  ·  added to the system price (spread over the term)")
            elif "Lease" in payment_model:
                _xrate = LEASE_RATES.get(lease_term, 0) or 0
                st.caption(f"Total £{extra_costs_total:,.2f}  ·  adds about £{_xrate / 1000 * extra_costs_total:,.2f}/mo to the lease")
            else:
                st.caption(f"Total £{extra_costs_total:,.2f}  ·  added to the upfront price")

    st.markdown("### 🏦 Bank Details")
    bank_name  = st.text_input("Bank Name", key="q_bank_name")
    acc_holder = st.text_input("Account Holder", key="q_acc_holder")
    acc_no     = st.text_input("Account Number", max_chars=8, key="q_acc_no")
    sort_code  = st.text_input("Sort Code", max_chars=6, key="q_sort_code")
    st.text_input("Bank branch address", key="q_bank_addr", help="Only used on the Shire Leasing Direct Debit form (air conditioning).")

    # Promos removed - always recurring, no BOGOF or add-on promos



# Hardcoded values (features/promos removed - must stay defined for PDF/CV references)
# Current customer cost defaults (0 unless consultant fills in)

bogof_active    = False
dark_web_mon    = False
proactive_bb    = False
ooh_support     = False
music_on_hold   = False
website_promo   = False
rental_discount = 0.0
hw_fund         = "None"
is_recurring    = True
# Software add-on defaults (overridden by sidebar widgets above)
sw_studio_qty = sw_callrec_qty = sw_crm_qty = 0
_sw_studio_on = False
sw_acd_qty = 0
sw_ctd_qty = sw_wallboard_qty = 0

# ─── CLOUD SAVED DEALS (a private GitHub repo that holds saved quote files) ───────────────
# Streamlit Secrets needs:   [saved_deals]   token = "ghp_..."   repo = "owner/SWComms-Saved-Deals"   (branch = "main" is optional)
# Every save makes a NEW file (version 1, 2, 3 ...), so earlier versions of a customer's deal are never overwritten.
def _sd_cfg():
    try:
        _s = st.secrets.get("saved_deals")
        if _s and _s.get("token") and _s.get("repo"):
            return {"token": str(_s["token"]), "repo": str(_s["repo"]).strip().strip("/"), "branch": str(_s.get("branch", "main") or "main")}
    except Exception:
        pass
    return None

def _sd_hdr(cfg, raw=False):
    return {"Authorization": "Bearer " + cfg["token"], "X-GitHub-Api-Version": "2022-11-28",
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}

def _sd_slug(s, keep="-"):
    return re.sub(r"[^a-z0-9" + re.escape(keep) + r"]+", "_", str(s or "").lower()).strip("_") or "x"

def _sd_owner():
    """Who the saved deal belongs to: the logged-in consultant's email (or their name when the shared password is used)."""
    _cu = st.session_state.get("current_user") or {}
    return _sd_slug(_cu.get("email") or st.session_state.get("q_rep_name") or "shared", keep="@.-").replace("@", "_at_")

def _sd_is_admin():
    _cu = st.session_state.get("current_user")
    return (_cu.get("role") == "admin") if _cu else bool(st.session_state.get("admin_unlocked"))

_SD_FILE = re.compile(r"^(?P<cust>.+)_v(?P<ver>\d+)_(?P<ts>\d{8}-\d{4})\.json$")

def _sd_list(cfg):
    """All saved deals the person may see: [{path, owner, customer, version, ts}] - newest first."""
    r = _req.get(f"https://api.github.com/repos/{cfg['repo']}/git/trees/{cfg['branch']}?recursive=1", headers=_sd_hdr(cfg), timeout=20)
    if r.status_code == 404:
        raise RuntimeError("Couldn't find the saved-deals repo or branch - check the repo name in Streamlit Secrets.")
    if r.status_code in (401, 403):
        raise RuntimeError("GitHub refused the token - check it is valid and has access to the saved-deals repo.")
    r.raise_for_status()
    me, admin, out = _sd_owner(), _sd_is_admin(), []
    for it in r.json().get("tree", []):
        p = it.get("path", "")
        parts = p.split("/")
        if len(parts) != 3 or parts[0] != "deals" or it.get("type") != "blob":
            continue
        m = _SD_FILE.match(parts[2])
        if not m or (not admin and parts[1] != me):
            continue
        out.append({"path": p, "owner": parts[1], "customer": m["cust"], "version": int(m["ver"]), "ts": m["ts"]})
    out.sort(key=lambda d: (d["ts"], d["version"]), reverse=True)
    return out

def _sd_save(cfg, snapshot):
    """Save as the next version for this consultant + customer. Returns (version, path)."""
    cust = _sd_slug(snapshot.get("q_comp_name") or "")
    if cust == "x":
        raise RuntimeError("Add a customer name first - the deal is saved under it.")
    owner = _sd_owner()
    existing = [d for d in _sd_list_owner(cfg, owner) if d["customer"] == cust]
    ver = max([d["version"] for d in existing] + [0]) + 1
    stamp = datetime_now_stamp()
    path = f"deals/{owner}/{cust}_v{ver}_{stamp}.json"
    _cu = st.session_state.get("current_user") or {}
    wrapper = {"_saved_deal": 1, "meta": {"customer": snapshot.get("q_comp_name", ""), "version": ver, "saved_by": _cu.get("name") or st.session_state.get("q_rep_name", ""),
               "owner": owner, "saved_at": stamp, "brand": snapshot.get("_quote_brand", "")}, "quote": snapshot}
    body = {"message": f"Save {cust} v{ver} ({owner})", "branch": cfg["branch"],
            "content": base64.b64encode(json.dumps(wrapper, indent=1, default=str).encode()).decode()}
    r = _req.put(f"https://api.github.com/repos/{cfg['repo']}/contents/{path}", headers=_sd_hdr(cfg), json=body, timeout=30)
    if r.status_code in (401, 403, 404):
        raise RuntimeError("GitHub wouldn't accept the save - check the token can write to the saved-deals repo.")
    r.raise_for_status()
    return ver, path

def _sd_list_owner(cfg, owner):
    r = _req.get(f"https://api.github.com/repos/{cfg['repo']}/contents/deals/{owner}?ref={cfg['branch']}", headers=_sd_hdr(cfg), timeout=20)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    out = []
    for it in r.json():
        m = _SD_FILE.match(it.get("name", ""))
        if m:
            out.append({"customer": m["cust"], "version": int(m["ver"])})
    return out

def datetime_now_stamp():
    from datetime import datetime as _dt
    return _dt.now().strftime("%Y%m%d-%H%M")

def _sd_load(cfg, path):
    r = _req.get(f"https://api.github.com/repos/{cfg['repo']}/contents/{path}?ref={cfg['branch']}", headers=_sd_hdr(cfg, raw=True), timeout=30)
    r.raise_for_status()
    d = r.json()
    return d.get("quote", d) if isinstance(d, dict) else d

def _sd_label(d, admin):
    _t = d["ts"]
    _when = f"{_t[6:8]}/{_t[4:6]}/{_t[0:4]} {_t[9:11]}:{_t[11:13]}"
    return f"{d['customer'].replace('_', ' ').title()} - version {d['version']} - {_when}" + (f" - {d['owner']}" if admin else "")

# ─── QUOTE SAVE / LOAD ───────────────────────────────────────────────────────
with st.expander("💾 Save / Load Quote", expanded=False):
    ql_col1, ql_col2, ql_col3 = st.columns(3)

    with ql_col1:
        st.markdown("**💾 Save current quote**")
        st.caption("Downloads a JSON file with all current inputs - share with manager or reload later.")
        if st.button("📥 Prepare Quote for Download", use_container_width=True, key="prep_save"):
            st.session_state["_quote_ready"] = True
        if st.session_state.get("_quote_ready"):
            snapshot = quote_snapshot()   # every deal input, including target rental and services
            import json as _json
            quote_name = (st.session_state.get("q_comp_name") or "quote").replace(" ", "_")
            st.download_button(
                f"📥 Download quote - {quote_name}.json",
                data=_json.dumps(snapshot, indent=2, default=str),
                file_name=f"{quote_name}_{date.today()}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_quote_btn"
            )

    with ql_col2:
        st.markdown("**📂 Load previous quote**")
        st.caption("Upload a previously saved quote JSON to restore all inputs.")
        _qu_key = f"quote_uploader_{st.session_state.get('_qu_reset', 0)}"
        loaded_quote_file = st.file_uploader("Upload quote JSON", type=["json"],
                                             key=_qu_key, label_visibility="collapsed")
        if loaded_quote_file:
            try:
                import json as _json
                q_data = _json.load(loaded_quote_file)
                # Store in temp key — applied BEFORE widgets render on next run
                # Increment reset counter to force file uploader to clear
                st.session_state["_qu_reset"] = st.session_state.get("_qu_reset", 0) + 1
                st.session_state["_pending_quote"] = q_data
                st.success(f"✅ Quote loaded — refreshing...")
                st.rerun()
            except Exception as e:
                st.error(f"Could not load quote: {e}")

    with ql_col3:
        st.markdown("**⚙️ Load config**")
        st.caption("Upload a config.json (downloaded from Admin panel) to restore pricing & catalogue.")
        loaded_cfg_file = st.file_uploader("Upload config JSON", type=["json"],
                                           key="cfg_uploader", label_visibility="collapsed")
        if loaded_cfg_file:
            try:
                import json as _json
                cfg_data = _json.load(loaded_cfg_file)
                if "product_images" in cfg_data:
                    imgs = {k: base64.b64decode(v) for k, v in cfg_data.pop("product_images").items()}
                    st.session_state.uploaded_images = imgs
                st.session_state.active_config = cfg_data
                n_imgs = len(st.session_state.get("uploaded_images", {}))
                st.success(f"✅ Config loaded! Pricing, catalogue and {n_imgs} image(s) restored.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not load config: {e}")

    # ── Cloud saved deals ──
    st.divider()
    st.markdown("**☁️ Saved deals (cloud)**")
    _sdc = _sd_cfg()
    if not _sdc:
        st.caption("Cloud saving isn't switched on yet - add the saved-deals token and repo to Streamlit Secrets (see the setup notes).")
    else:
        st.caption("Save this deal to the shared store, or bring back one of " + ("everyone's" if _sd_is_admin() else "your own") +
                   " saved deals with every figure. Saving again makes a new version - earlier ones are kept.")
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("☁️ Save this deal to the cloud", use_container_width=True, key="sd_save_btn"):
                try:
                    _v, _p = _sd_save(_sdc, quote_snapshot())
                    st.session_state["_sd_msg"] = f"✅ Saved as version {_v} for {st.session_state.get('q_comp_name', '')}."
                    st.session_state.pop("_sd_items", None)
                except Exception as _e:
                    st.session_state["_sd_msg"] = f"❌ Couldn't save: {_e}"
            if st.session_state.get("_sd_msg"):
                st.info(st.session_state["_sd_msg"])
        with _c2:
            if st.button("🔄 Show saved deals", use_container_width=True, key="sd_list_btn"):
                try:
                    st.session_state["_sd_items"] = _sd_list(_sdc)
                    st.session_state["_sd_err"] = ""
                except Exception as _e:
                    st.session_state["_sd_items"] = []
                    st.session_state["_sd_err"] = f"Couldn't get the list: {_e}"
        if st.session_state.get("_sd_err"):
            st.error(st.session_state["_sd_err"])
        _items = st.session_state.get("_sd_items")
        if _items is not None and not st.session_state.get("_sd_err"):
            _q = st.text_input("Search saved deals", key="sd_search", placeholder="customer name...")
            _shown = [d for d in _items if _q.strip().lower() in (d["customer"] + " " + d["owner"]).replace("_", " ").lower()] if _q.strip() else _items
            if not _shown:
                st.caption("No saved deals found.")
            else:
                _pick = st.selectbox("Saved deal", range(len(_shown)), format_func=lambda i: _sd_label(_shown[i], _sd_is_admin()), key="sd_pick")
                if st.button("📂 Load this deal", use_container_width=True, key="sd_load_btn"):
                    try:
                        st.session_state["_pending_quote"] = _sd_load(_sdc, _shown[_pick]["path"])
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Couldn't load that deal: {_e}")

# ═══════════════════════════════════════════════════════════════════════════
#  ❄️ AIR CONDITIONING  (the SteadyTemp price book, added as an extra offering)
#  Equipment is priced from the catalogue below; everything is leased at the rates already in this pricebook.
# ═══════════════════════════════════════════════════════════════════════════
import html as _ac_html
AC_CAT_DEFAULT = json.loads(r'''[{"group": "Wall Mounted", "kind": "wall", "name": "Midea Wall Mounted 2.5kw", "desc": "Wall Mounted", "rrp": 530.0, "cost": 260.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Midea Wall Mounted 3.5kw", "desc": "Wall Mounted", "rrp": 610.0, "cost": 305.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Midea Wall Mounted 5kw", "desc": "Wall Mounted", "rrp": 900.0, "cost": 460.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Midea Wall Mounted 7kw", "desc": "Wall Mounted", "rrp": 1310.0, "cost": 670.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Midea Wall Mounted 10kw", "desc": "Wall Mounted", "rrp": 1925.0, "cost": 984.54}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi Wall Mounted 2.5kw", "desc": "Wall Mounted", "rrp": 530.0, "cost": 260.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi Wall Mounted 3.5kw", "desc": "Wall Mounted", "rrp": 610.0, "cost": 305.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi Wall Mounted 5kw", "desc": "Wall Mounted", "rrp": 900.0, "cost": 460.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi Wall Mounted 7kw", "desc": "Wall Mounted", "rrp": 1310.0, "cost": 670.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi Wall Mounted 10kw", "desc": "Wall Mounted", "rrp": 1925.0, "cost": 984.54}, {"group": "Wall Mounted", "kind": "wall", "name": "Panasonic Wall Mounted 2.5kw", "desc": "Wall Mounted", "rrp": 530.0, "cost": 260.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Panasonic Wall Mounted 3.5kw", "desc": "Wall Mounted", "rrp": 610.0, "cost": 305.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Panasonic Wall Mounted 5kw", "desc": "Wall Mounted", "rrp": 900.0, "cost": 460.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Panasonic Wall Mounted 7kw", "desc": "Wall Mounted", "rrp": 1310.0, "cost": 670.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Panasonic Wall Mounted 10kw", "desc": "Wall Mounted", "rrp": 1925.0, "cost": 984.54}, {"group": "Wall Mounted", "kind": "wall", "name": "Samsung Wall Mounted 2.5kw", "desc": "Wall Mounted", "rrp": 530.0, "cost": 260.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Samsung Wall Mounted 3.5kw", "desc": "Wall Mounted", "rrp": 610.0, "cost": 305.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Samsung Wall Mounted 5kw", "desc": "Wall Mounted", "rrp": 900.0, "cost": 460.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Samsung Wall Mounted 7kw", "desc": "Wall Mounted", "rrp": 1310.0, "cost": 670.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Samsung Wall Mounted 10kw", "desc": "Wall Mounted", "rrp": 1925.0, "cost": 984.54}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi HI Wall Mounted 2.5kw", "desc": "Wall Mounted", "rrp": 530.0, "cost": 260.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi HI Wall Mounted 3.5kw", "desc": "Wall Mounted", "rrp": 610.0, "cost": 305.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi HI Wall Mounted 5kw", "desc": "Wall Mounted", "rrp": 900.0, "cost": 460.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi HI Wall Mounted 7kw", "desc": "Wall Mounted", "rrp": 1310.0, "cost": 670.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Mitsubishi HI Wall Mounted 10kw", "desc": "Wall Mounted", "rrp": 1925.0, "cost": 984.54}, {"group": "Wall Mounted", "kind": "wall", "name": "Fujitsu Wall Mounted 2.5kw", "desc": "Wall Mounted", "rrp": 530.0, "cost": 260.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Fujitsu Wall Mounted 3.5kw", "desc": "Wall Mounted", "rrp": 610.0, "cost": 305.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Fujitsu Wall Mounted 5kw", "desc": "Wall Mounted", "rrp": 900.0, "cost": 460.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Fujitsu Wall Mounted 7kw", "desc": "Wall Mounted", "rrp": 1310.0, "cost": 670.0}, {"group": "Wall Mounted", "kind": "wall", "name": "Fujitsu Wall Mounted 10kw", "desc": "Wall Mounted", "rrp": 1925.0, "cost": 984.54}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 3.5kw", "desc": "Ceiling Cassette", "rrp": 1178.0, "cost": 600.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 5kw", "desc": "Ceiling Cassette", "rrp": 1560.0, "cost": 800.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 7kw", "desc": "Ceiling Cassette", "rrp": 1986.0, "cost": 993.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 10kw", "desc": "Ceiling Cassette", "rrp": 2498.0, "cost": 1249.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 12kw", "desc": "Ceiling Cassette", "rrp": 2900.0, "cost": 1450.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 16kw", "desc": "Ceiling Cassette", "rrp": 3704.0, "cost": 1852.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Midea Ceiling Cassette 18kw", "desc": "Ceiling Cassette", "rrp": 4106.0, "cost": 2053.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 3.5kw", "desc": "Ceiling Cassette", "rrp": 1178.0, "cost": 600.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 5kw", "desc": "Ceiling Cassette", "rrp": 1560.0, "cost": 800.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 7kw", "desc": "Ceiling Cassette", "rrp": 1986.0, "cost": 993.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 10kw", "desc": "Ceiling Cassette", "rrp": 2498.0, "cost": 1249.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 12kw", "desc": "Ceiling Cassette", "rrp": 2900.0, "cost": 1450.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 16kw", "desc": "Ceiling Cassette", "rrp": 3704.0, "cost": 1852.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi Ceiling Cassette 18kw", "desc": "Ceiling Cassette", "rrp": 4106.0, "cost": 2053.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 3.5kw", "desc": "Ceiling Cassette", "rrp": 1178.0, "cost": 600.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 5kw", "desc": "Ceiling Cassette", "rrp": 1560.0, "cost": 800.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 7kw", "desc": "Ceiling Cassette", "rrp": 1986.0, "cost": 993.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 10kw", "desc": "Ceiling Cassette", "rrp": 2498.0, "cost": 1249.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 12kw", "desc": "Ceiling Cassette", "rrp": 2900.0, "cost": 1450.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 16kw", "desc": "Ceiling Cassette", "rrp": 3704.0, "cost": 1852.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Panasonic Ceiling Cassette 18kw", "desc": "Ceiling Cassette", "rrp": 4106.0, "cost": 2053.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 3.5kw", "desc": "Ceiling Cassette", "rrp": 1178.0, "cost": 600.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 5kw", "desc": "Ceiling Cassette", "rrp": 1560.0, "cost": 800.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 7kw", "desc": "Ceiling Cassette", "rrp": 1986.0, "cost": 993.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 10kw", "desc": "Ceiling Cassette", "rrp": 2498.0, "cost": 1249.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 12kw", "desc": "Ceiling Cassette", "rrp": 2900.0, "cost": 1450.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 16kw", "desc": "Ceiling Cassette", "rrp": 3704.0, "cost": 1852.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Samsung Ceiling Cassette 18kw", "desc": "Ceiling Cassette", "rrp": 4106.0, "cost": 2053.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 3.5kw", "desc": "Ceiling Cassette", "rrp": 1178.0, "cost": 600.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 5kw", "desc": "Ceiling Cassette", "rrp": 1560.0, "cost": 800.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 7kw", "desc": "Ceiling Cassette", "rrp": 1986.0, "cost": 993.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 10kw", "desc": "Ceiling Cassette", "rrp": 2498.0, "cost": 1249.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 12kw", "desc": "Ceiling Cassette", "rrp": 2900.0, "cost": 1450.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 16kw", "desc": "Ceiling Cassette", "rrp": 3704.0, "cost": 1852.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Mitsubishi HI Ceiling Cassette 18kw", "desc": "Ceiling Cassette", "rrp": 4106.0, "cost": 2053.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 3.5kw", "desc": "Ceiling Cassette", "rrp": 1178.0, "cost": 600.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 5kw", "desc": "Ceiling Cassette", "rrp": 1560.0, "cost": 800.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 7kw", "desc": "Ceiling Cassette", "rrp": 1986.0, "cost": 993.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 10kw", "desc": "Ceiling Cassette", "rrp": 2498.0, "cost": 1249.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 12kw", "desc": "Ceiling Cassette", "rrp": 2900.0, "cost": 1450.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 16kw", "desc": "Ceiling Cassette", "rrp": 3704.0, "cost": 1852.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "Fujitsu Ceiling Cassette 18kw", "desc": "Ceiling Cassette", "rrp": 4106.0, "cost": 2053.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 3.5kw", "desc": "A6 Ducted system", "rrp": 1194.0, "cost": 780.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 5kw", "desc": "A6 Ducted system", "rrp": 1524.0, "cost": 940.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 7kw", "desc": "A6 Ducted system", "rrp": 1882.0, "cost": 1113.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 10kw", "desc": "A6 Ducted system", "rrp": 2660.0, "cost": 1512.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 12kw", "desc": "A6 Ducted System", "rrp": 2800.0, "cost": 1585.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 14kw", "desc": "A6 Ducted System", "rrp": 3296.0, "cost": 1845.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 16kw", "desc": "A6 Ducted System", "rrp": 3392.0, "cost": 1896.0}, {"group": "Ducted", "kind": "ducted", "name": "Midea Ducted 20kw", "desc": "A6 Ducted System", "rrp": 3584.0, "cost": 2003.32}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 3.5kw", "desc": "Ducted system", "rrp": 1194.0, "cost": 780.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 5kw", "desc": "Ducted system", "rrp": 1524.0, "cost": 940.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 7kw", "desc": "Ducted system", "rrp": 1882.0, "cost": 1113.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 10kw", "desc": "Ducted system", "rrp": 2660.0, "cost": 1512.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 12kw", "desc": "Ducted system", "rrp": 2800.0, "cost": 1585.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 14kw", "desc": "Ducted system", "rrp": 3296.0, "cost": 1845.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 16kw", "desc": "Ducted system", "rrp": 3392.0, "cost": 1896.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi Ducted 20kw", "desc": "Ducted system", "rrp": 3584.0, "cost": 2003.32}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 3.5kw", "desc": "Ducted system", "rrp": 1194.0, "cost": 780.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 5kw", "desc": "Ducted system", "rrp": 1524.0, "cost": 940.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 7kw", "desc": "Ducted system", "rrp": 1882.0, "cost": 1113.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 10kw", "desc": "Ducted system", "rrp": 2660.0, "cost": 1512.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 12kw", "desc": "Ducted system", "rrp": 2800.0, "cost": 1585.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 14kw", "desc": "Ducted system", "rrp": 3296.0, "cost": 1845.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 16kw", "desc": "Ducted system", "rrp": 3392.0, "cost": 1896.0}, {"group": "Ducted", "kind": "ducted", "name": "Panasonic Ducted 20kw", "desc": "Ducted system", "rrp": 3584.0, "cost": 2003.32}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 3.5kw", "desc": "Ducted system", "rrp": 1194.0, "cost": 780.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 5kw", "desc": "Ducted system", "rrp": 1524.0, "cost": 940.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 7kw", "desc": "Ducted system", "rrp": 1882.0, "cost": 1113.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 10kw", "desc": "Ducted system", "rrp": 2660.0, "cost": 1512.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 12kw", "desc": "Ducted system", "rrp": 2800.0, "cost": 1585.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 14kw", "desc": "Ducted system", "rrp": 3296.0, "cost": 1845.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 16kw", "desc": "Ducted system", "rrp": 3392.0, "cost": 1896.0}, {"group": "Ducted", "kind": "ducted", "name": "Samsung Ducted 20kw", "desc": "Ducted system", "rrp": 3584.0, "cost": 2003.32}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 3.5kw", "desc": "Ducted system", "rrp": 1194.0, "cost": 780.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 5kw", "desc": "Ducted system", "rrp": 1524.0, "cost": 940.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 7kw", "desc": "Ducted system", "rrp": 1882.0, "cost": 1113.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 10kw", "desc": "Ducted system", "rrp": 2660.0, "cost": 1512.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 12kw", "desc": "Ducted system", "rrp": 2800.0, "cost": 1585.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 14kw", "desc": "Ducted system", "rrp": 3296.0, "cost": 1845.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 16kw", "desc": "Ducted system", "rrp": 3392.0, "cost": 1896.0}, {"group": "Ducted", "kind": "ducted", "name": "Mitsubishi HI Ducted 20kw", "desc": "Ducted system", "rrp": 3584.0, "cost": 2003.32}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 3.5kw", "desc": "Ducted system", "rrp": 1194.0, "cost": 780.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 5kw", "desc": "Ducted system", "rrp": 1524.0, "cost": 940.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 7kw", "desc": "Ducted system", "rrp": 1882.0, "cost": 1113.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 10kw", "desc": "Ducted system", "rrp": 2660.0, "cost": 1512.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 12kw", "desc": "Ducted system", "rrp": 2800.0, "cost": 1585.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 14kw", "desc": "Ducted system", "rrp": 3296.0, "cost": 1845.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 16kw", "desc": "Ducted system", "rrp": 3392.0, "cost": 1896.0}, {"group": "Ducted", "kind": "ducted", "name": "Fujitsu Ducted 20kw", "desc": "Ducted system", "rrp": 3584.0, "cost": 2003.32}, {"group": "Lossnay Air Exchange", "kind": "lossnay", "name": "Lossnay 150M3", "desc": "Lossnay air exchange unit", "rrp": 1194.0, "cost": 780.0}, {"group": "Lossnay Air Exchange", "kind": "lossnay", "name": "Lossnay 250M3", "desc": "Lossnay air exchange unit", "rrp": 1524.0, "cost": 940.0}, {"group": "Lossnay Air Exchange", "kind": "lossnay", "name": "Lossnay 350M3", "desc": "Lossnay air exchange unit", "rrp": 1882.0, "cost": 1113.0}, {"group": "Lossnay Air Exchange", "kind": "lossnay", "name": "Lossnay 500M3", "desc": "Lossnay air exchange unit", "rrp": 2660.0, "cost": 1512.0}, {"group": "Lossnay Air Exchange", "kind": "lossnay", "name": "Lossnay 800M3", "desc": "Lossnay air exchange unit", "rrp": 2800.0, "cost": 1585.0}, {"group": "Lossnay Air Exchange", "kind": "lossnay", "name": "Lossnay 1000M3", "desc": "Lossnay air exchange unit", "rrp": 3296.0, "cost": 1845.0}, {"group": "Materials", "kind": "material", "name": "Copper - ¼” 15 metre Roll", "desc": "¼” 15 metre Roll", "rrp": 19.04, "cost": 10.67}, {"group": "Materials", "kind": "material", "name": "Copper - 3/8” 15 metre Roll", "desc": "3/8” 15 metre Roll", "rrp": 33.59, "cost": 18.82}, {"group": "Materials", "kind": "material", "name": "Copper - ½” 15 metre Roll", "desc": "½” 15 metre Roll", "rrp": 45.87, "cost": 25.7}, {"group": "Materials", "kind": "material", "name": "Copper - 5/8” 15 metre Roll", "desc": "5/8” 15 metre Roll", "rrp": 64.93, "cost": 36.38}, {"group": "Materials", "kind": "material", "name": "Insulation - ¼  15 metre Roll", "desc": "¼  15 metre Roll", "rrp": 11.03, "cost": 6.13}, {"group": "Materials", "kind": "material", "name": "Insulation - 3/8” 15 metre Roll", "desc": "3/8” 15 metre Roll", "rrp": 11.55, "cost": 6.42}, {"group": "Materials", "kind": "material", "name": "Insulation - ½” 15 metre Roll", "desc": "½” 15 metre Roll", "rrp": 11.79, "cost": 6.55}, {"group": "Materials", "kind": "material", "name": "Insulation - 5/8” 15 metre Roll", "desc": "5/8” 15 metre Roll", "rrp": 12.2, "cost": 6.78}, {"group": "Materials", "kind": "material", "name": "Tank Pump - Machine mounted pump", "desc": "Machine mounted pump", "rrp": 63.84, "cost": 41.19}, {"group": "Materials", "kind": "material", "name": "Wall Pump - Wall mounted pump", "desc": "Wall mounted pump", "rrp": 129.23, "cost": 83.38}, {"group": "Materials", "kind": "material", "name": "Drain Pipe - 3 metre water pipe", "desc": "3 metre water pipe", "rrp": 9.12, "cost": 5.53}, {"group": "Materials", "kind": "material", "name": "3 core Flex cable - 100 metre 1.5 Roll", "desc": "100 metre 1.5 Roll", "rrp": 88.34, "cost": 49.63}, {"group": "Materials", "kind": "material", "name": "Electric SY Cable - 100 metre roll", "desc": "100 metre roll", "rrp": 165.0, "cost": 92.72}, {"group": "Materials", "kind": "material", "name": "Drain Hose - Water drain ¼ 15 metre roll", "desc": "Water drain ¼ 15 metre roll", "rrp": 13.74, "cost": 8.33}, {"group": "Materials", "kind": "material", "name": "Drain Hose - Water drain 3/8 15 metre roll", "desc": "Water drain 3/8 15 metre roll", "rrp": 20.74, "cost": 12.57}, {"group": "Materials", "kind": "material", "name": "Bracket - small", "desc": "small", "rrp": 47.6, "cost": 28.85}, {"group": "Materials", "kind": "material", "name": "Bracket - medium", "desc": "medium", "rrp": 56.47, "cost": 34.23}, {"group": "Materials", "kind": "material", "name": "Bracket - large", "desc": "large", "rrp": 73.93, "cost": 44.81}, {"group": "Labour", "kind": "labour", "name": "Engineers Labour - 1 day", "desc": "1 day", "rrp": 500.0, "cost": 500.0}, {"group": "Labour", "kind": "labour", "name": "Electricians Labour - 1 day", "desc": "1 day", "rrp": 500.0, "cost": 500.0}, {"group": "Extras", "kind": "extra", "name": "WIFI - Built in system wifi Midea", "desc": "Built in system wifi Midea", "rrp": 100.0, "cost": 20.0}, {"group": "Extras", "kind": "extra", "name": "External trunking - 3 meter wall trunking to hide pipes", "desc": "3 meter wall trunking to hide pipes", "rrp": 30.0, "cost": 10.0}, {"group": "Extras", "kind": "extra", "name": "External wall tray - 3 meter lengths 4”", "desc": "3 meter lengths 4”", "rrp": 11.48, "cost": 6.11}, {"group": "Extras", "kind": "extra", "name": "External wall tray - 3 meter length 6”", "desc": "3 meter length 6”", "rrp": 14.28, "cost": 7.6}, {"group": "Extras", "kind": "extra", "name": "Outdoor machine feet/stand - 1x set 450mm", "desc": "1x set 450mm", "rrp": 13.86, "cost": 9.24}, {"group": "Extras", "kind": "extra", "name": "Outdoor machine feet/stand - 1x set 1000mm", "desc": "1x set 1000mm", "rrp": 28.8, "cost": 19.2}, {"group": "Extras", "kind": "extra", "name": "WIFI - Mitsubishi system", "desc": "Mitsubishi system", "rrp": 80.0, "cost": 65.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw DualCool Pro", "desc": "Wall Mounted · DualCool Pro · WZ09AWN + WZ09AWU", "rrp": 617.0, "cost": 617.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw DualCool Special EZ", "desc": "Wall Mounted · DualCool Special EZ · EZ09CYN + EZ09CYU", "rrp": 674.0, "cost": 674.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw DualCool Special PZ", "desc": "Wall Mounted · DualCool Special PZ · PZ09EYN + PZ09EYU", "rrp": 798.0, "cost": 798.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw DualCool AI Air Special", "desc": "Wall Mounted · DualCool AI Air Special · P09SND + P09SND", "rrp": 869.0, "cost": 869.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw Artcool Mirror", "desc": "Wall Mounted · Artcool Mirror · AC09BK + AC09BK", "rrp": 1074.0, "cost": 1074.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw Artcool AI Air Mirror", "desc": "Wall Mounted · Artcool AI Air Mirror · AA09SP + AA09SP", "rrp": 1221.0, "cost": 1221.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 2.5kw Artcool Gallery Premium", "desc": "Wall Mounted · Artcool Gallery Premium · A09GA2N + A09GA2U", "rrp": 1845.0, "cost": 1845.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw DualCool Pro", "desc": "Wall Mounted · DualCool Pro · WZ12AWN + WZ12AWU", "rrp": 669.0, "cost": 669.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw DualCool Special EZ", "desc": "Wall Mounted · DualCool Special EZ · EZ12CYN + EZ12CYU", "rrp": 751.0, "cost": 751.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw DualCool Special PZ", "desc": "Wall Mounted · DualCool Special PZ · PZ12EYN + PZ12EYU", "rrp": 892.0, "cost": 892.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw DualCool AI Air Special", "desc": "Wall Mounted · DualCool AI Air Special · P12SND + P12SND", "rrp": 1019.0, "cost": 1019.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw Artcool Mirror", "desc": "Wall Mounted · Artcool Mirror · AC12BK + AC12BK", "rrp": 1259.0, "cost": 1259.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw Artcool AI Air Mirror", "desc": "Wall Mounted · Artcool AI Air Mirror · AA12SP + AA12SP", "rrp": 1345.0, "cost": 1345.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 3.5kw Artcool Gallery Premium", "desc": "Wall Mounted · Artcool Gallery Premium · A12GA2N + A12GA2U", "rrp": 2091.0, "cost": 2091.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 5kw DualCool Pro", "desc": "Wall Mounted · DualCool Pro · WZ18AWN + WZ18AWU", "rrp": 917.0, "cost": 917.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 5kw DualCool Special EZ", "desc": "Wall Mounted · DualCool Special EZ · EZ18CYN + EZ18CYU", "rrp": 1046.0, "cost": 1046.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 5kw DualCool Special PZ", "desc": "Wall Mounted · DualCool Special PZ · PZ18EYN + PZ18EYU", "rrp": 1225.0, "cost": 1225.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 5kw DualCool AI Air Special", "desc": "Wall Mounted · DualCool AI Air Special · P18SND + P18SND", "rrp": 1270.0, "cost": 1270.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 5kw Artcool Mirror", "desc": "Wall Mounted · Artcool Mirror · AC18BK + AC18BK", "rrp": 1725.0, "cost": 1725.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 5kw Artcool AI Air Mirror", "desc": "Wall Mounted · Artcool AI Air Mirror · AA18SP + AA18SP", "rrp": 1811.0, "cost": 1811.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 6.6kw DualCool Pro", "desc": "Wall Mounted · DualCool Pro · WZ24AWN + WZ24AWU", "rrp": 1151.0, "cost": 1151.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 6.6kw DualCool Special EZ", "desc": "Wall Mounted · DualCool Special EZ · EZ24CYN + EZ24CYU", "rrp": 1316.0, "cost": 1316.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 6.6kw DualCool Special PZ", "desc": "Wall Mounted · DualCool Special PZ · PZ24EYN + PZ24EYU", "rrp": 1548.0, "cost": 1548.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 6.6kw DualCool AI Air Special", "desc": "Wall Mounted · DualCool AI Air Special · P24SND + P24SND", "rrp": 1600.0, "cost": 1600.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 6.6kw Artcool Mirror", "desc": "Wall Mounted · Artcool Mirror · AC24BK + AC24BK", "rrp": 2134.0, "cost": 2134.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 6.6kw Artcool AI Air Mirror", "desc": "Wall Mounted · Artcool AI Air Mirror · AA24SP + AA24SP", "rrp": 2134.0, "cost": 2134.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 8kw Free Combination", "desc": "Wall Mounted · Free Combination · US30F + UUC1", "rrp": 2360.0, "cost": 2360.0}, {"group": "Wall Mounted", "kind": "wall", "name": "LG Wall Mounted 9.5kw Free Combination", "desc": "Wall Mounted · Free Combination · US36F + UUD1", "rrp": 3159.0, "cost": 3159.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 2.5kw Mini 4-Way", "desc": "Ceiling Cassette · Mini 4-Way · CT09F + UUA1", "rrp": 1421.0, "cost": 1421.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 3.4kw Mini 4-Way", "desc": "Ceiling Cassette · Mini 4-Way · CT12F + UUA1", "rrp": 1432.0, "cost": 1432.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 5kw Mini 4-Way", "desc": "Ceiling Cassette · Mini 4-Way · CT18F + UUB1", "rrp": 1781.0, "cost": 1781.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 6.8kw Mini 4-Way", "desc": "Ceiling Cassette · Mini 4-Way · CT24F + UUC1", "rrp": 2256.0, "cost": 2256.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 8kw 4-Way", "desc": "Ceiling Cassette · 4-Way · UT30F + UUC1", "rrp": 2345.0, "cost": 2345.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 9.5kw 4-Way", "desc": "Ceiling Cassette · 4-Way · UT36F + UUD1", "rrp": 3148.0, "cost": 3148.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 11kw Round", "desc": "Ceiling Cassette · Round · UT36F + UUD1", "rrp": 3634.0, "cost": 3634.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 12.1kw 4-Way", "desc": "Ceiling Cassette · 4-Way · UT42F + UUD1", "rrp": 3225.0, "cost": 3225.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 13.4kw 4-Way", "desc": "Ceiling Cassette · 4-Way · UT48F + UUD1", "rrp": 3582.0, "cost": 3582.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 13.4kw Round", "desc": "Ceiling Cassette · Round · UT48F + UUD1", "rrp": 3823.0, "cost": 3823.0}, {"group": "Ceiling Cassette", "kind": "ceiling", "name": "LG Ceiling Cassette 14.6kw 4-Way", "desc": "Ceiling Cassette · 4-Way · UT60F + UUD1", "rrp": 3898.0, "cost": 3898.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 2.5kw Low Static", "desc": "Ducted · Low Static · CL09F + UUA1", "rrp": 1419.0, "cost": 1419.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 3.4kw Low Static", "desc": "Ducted · Low Static · CL12F + UUA1", "rrp": 1449.0, "cost": 1449.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 5kw Low Static", "desc": "Ducted · Low Static · CL18F + UUB1", "rrp": 1763.0, "cost": 1763.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 5kw Mid Static Slim", "desc": "Ducted · Mid Static Slim · CM18F + UUB1", "rrp": 1903.0, "cost": 1903.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 6.8kw Low Static", "desc": "Ducted · Low Static · CL24F + UUC1", "rrp": 2217.0, "cost": 2217.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 6.8kw Mid Static Slim", "desc": "Ducted · Mid Static Slim · CM24F + UUC1", "rrp": 2352.0, "cost": 2352.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 7.5kw Mid Static", "desc": "Ducted · Mid Static · UM30F + UUC1", "rrp": 2440.0, "cost": 2440.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 9.5kw Mid Static", "desc": "Ducted · Mid Static · UM36F + UUD1", "rrp": 3222.0, "cost": 3222.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 12kw Mid Static", "desc": "Ducted · Mid Static · UM42F + UUD1", "rrp": 3245.0, "cost": 3245.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 13.4kw Mid Static", "desc": "Ducted · Mid Static · UM48F + UUD1", "rrp": 3434.0, "cost": 3434.0}, {"group": "Ducted", "kind": "ducted", "name": "LG Ducted 14.6kw Mid Static", "desc": "Ducted · Mid Static · UM60F + UUD1", "rrp": 3700.0, "cost": 3700.0}, {"group": "Extras", "kind": "extra", "name": "Blue Science - UV-C air sanitising (Midea)", "desc": "Covid and flu prevention ultra violet tech strip - optional extra for Midea units", "rrp": 140.0, "cost": 108.0}]''')
AC_IMG = {_k: _asset_b64(_rel) for _k, _rel in {"photo_wall": "ac/photo_wall.jpg", "photo_ceiling": "ac/photo_ceiling.jpg", "photo_ducted": "ac/photo_ducted.jpg", "photo_lossnay": "ac/photo_lossnay.jpg", "wall": "ac/wall.jpg", "ceiling": "ac/ceiling.jpg", "ducted": "ac/ducted.jpg", "copper": "ac/copper.jpg", "insulation": "ac/insulation.jpg", "pump": "ac/pump.jpg", "drainpipe": "ac/drainpipe.jpg", "cable": "ac/cable.jpg", "hose": "ac/hose.jpg", "bracket": "ac/bracket.jpg", "wifi": "ac/wifi.jpg", "trunking": "ac/trunking.jpg", "tray": "ac/tray.jpg", "feet": "ac/feet.jpg", "engineer": "ac/engineer.jpg", "electrician": "ac/electrician.jpg", "other": "ac/other.jpg"}.items()}

AC_COST_DEFAULT = {
    "srrp_mult": 2.0, "install_mult": 1.2,
    "maint_wall": 10.0, "maint_ceiling": 15.0, "maint_ducted": 25.0, "maint_lossnay": 25.0,
    "lab_wall": 650.0, "lab_ceiling": 1000.0, "lab_ducted": 2500.0, "lab_lossnay": 0.0,
    "electrician": 200.0, "cherry_picker": 700.0, "pump": 200.0,
    "install_day_rate": 500.0, "travel_hours": 2.0, "free_support_years": 1, "office_postcode": "CF14 2BT",
    # the SteadyTemp pricebook's own rental method (see ac_order_calc)
    "telemarketing": 200.0, "sales_override": 100.0, "min_commission": 0.0, "cash_load": 1.0, "midea_pack": 1.0,
    "unit_size": 1000.0, "unit_value": 1000.0,
}
AC_LEASE_DEFAULT = [          # rate = what the customer pays per GBP 1,000; true_rate = what the finance partner pays per GBP 1,000
    {"months": 36, "label": "3 Year (1+35)", "rate": 37.0, "true_rate": 37.0},
    {"months": 60, "label": "5 Year (1+59)", "rate": 26.0, "true_rate": 26.0},
    {"months": 84, "label": "7 Year (1+83)", "rate": 23.0, "true_rate": 23.0},
    {"months": 120, "label": "10 Year (1+119)", "rate": 19.0, "true_rate": 19.0},
]
AC_BRANDS = ["Midea", "Mitsubishi", "Mitsubishi HI", "Fujitsu", "Panasonic", "Samsung", "LG"]
AC_SYSTEM_GROUPS = ["Wall Mounted", "Ceiling Cassette", "Ducted", "Lossnay Air Exchange"]
AC_KINDS = ("wall", "ceiling", "ducted", "lossnay")
AC_INSTALL_NAME = "Air conditioning installation"

_ac_cfg = st.session_state.active_config.setdefault("aircon", {})
if not _ac_cfg.get("catalogue") or _ac_cfg.get("catalogue_src") != "steadytemp-pricebook":
    _ac_cfg["catalogue"] = [dict(i) for i in AC_CAT_DEFAULT]          # the SteadyTemp pricebook's catalogue (one-off switch)
    _ac_cfg["catalogue_src"] = "steadytemp-pricebook"
if not _ac_cfg.get("lease_rates"):
    _ac_cfg["lease_rates"] = [dict(i) for i in AC_LEASE_DEFAULT]
_ac_cfg["costs"] = {**AC_COST_DEFAULT, **(_ac_cfg.get("costs") or {})}
_ac_cfg["costs"]["install_mult"] = 1.2          # South Wales Comms: cost + 20%
_ac_cfg["costs"]["unit_size"] = 1000.0
_ac_cfg["costs"]["unit_value"] = 1000.0
AC_CAT = [i for i in _ac_cfg["catalogue"] if i.get("name")]
AC_COST = _ac_cfg["costs"]

def _ac_num(key, default=0.0):
    try:
        v = st.session_state.get(key, default)
        return float(v) if v not in (None, "") else float(default)
    except Exception:
        return float(default)

def _ac_esc(v):
    return _ac_html.escape(str(v), quote=True)

def _ac_brand(name):
    for b in sorted(AC_BRANDS + ["Lossnay"], key=len, reverse=True):
        if name.lower().startswith(b.lower() + " "):
            return b
    return name.split(" ")[0]

def _ac_srrp(it):
    return round(float(it.get("cost") or 0) * 1.2, 2)          # cost + 20%

_AC_IMG_DIR = Path(__file__).parent / "product_images"

@st.cache_data(show_spinner=False)
def _ac_read_b64(path, mtime):
    return base64.b64encode(Path(path).read_bytes()).decode()

def _ac_file_image(stem):
    """A picture dropped into the product_images folder, e.g. samsung_wall.jpg or logo_samsung.png (capitals and jpg/png/webp don't matter)."""
    try:
        want = stem.lower()
        for f in sorted(_AC_IMG_DIR.iterdir()):
            if f.is_file() and f.stem.lower() == want and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return _ac_read_b64(str(f), f.stat().st_mtime)
    except Exception:
        pass
    return ""

def _ac_slug(b):
    return re.sub(r"[^a-z0-9]+", "_", b.lower()).strip("_")

def _ac_logo(brand):
    return _ac_file_image("logo_" + _ac_slug(brand))

def _ac_img(it):
    """Base64 picture for a catalogue line: a photo from the product_images folder, else the built-in Midea photo, else a plain drawing."""
    n, kind = it["name"].lower(), it.get("kind", "")
    if kind in ("wall", "ceiling", "ducted"):
        own = _ac_file_image(f"{_ac_slug(_ac_brand(it['name']))}_{kind}")
        if own:
            return own
        return AC_IMG.get("photo_" + kind) if _ac_brand(it["name"]) == "Midea" else AC_IMG.get(kind)
    if kind == "lossnay":
        return _ac_file_image("air_exchange") or _ac_file_image("lossnay") or AC_IMG.get("photo_lossnay") or AC_IMG.get("other")
    for key, words in (("engineer", ("engineer",)), ("electrician", ("electrician",)), ("copper", ("copper",)), ("insulation", ("insulation",)),
                       ("pump", ("pump",)), ("hose", ("hose",)), ("drainpipe", ("drain pipe",)), ("cable", ("cable",)), ("bracket", ("bracket",)),
                       ("wifi", ("wifi", "wi-fi")), ("trunking", ("trunking",)), ("tray", ("tray",)), ("feet", ("feet", "stand"))):
        if any(w in n for w in words):
            return AC_IMG.get(key) or AC_IMG.get("other")
    return AC_IMG.get("other")

def _ac_ext(b64):
    return "png" if b64.startswith("iVBOR") else "webp" if b64.startswith("UklG") else "jpeg"

def _ac_img_html(b64, h=110):
    if not b64:
        return f"<div style='height:{h}px'></div>"
    return (f"<div style='height:{h}px;display:flex;align-items:center;justify-content:center;background:#fff;border-radius:10px;margin-bottom:.4rem'>"
            f"<img src='data:image/{_ac_ext(b64)};base64,{b64}' style='max-height:{h-10}px;max-width:92%;object-fit:contain'></div>")

# pictures for the paperwork / Customer View, matched by product name
for _i in AC_CAT:
    _b = _ac_img(_i)
    if _b:
        BUNDLED_IMAGES[_i["name"]] = (_b, _ac_ext(_b))
BUNDLED_IMAGES[AC_INSTALL_NAME] = (AC_IMG.get("engineer", ""), "jpeg")

def _ac_variant(it, brand):
    n = it["name"]
    for pre in (brand + " " + it["group"] + " ", brand + " "):
        if n.startswith(pre):
            n = n[len(pre):]; break
    return n

def _ac_qty_cb(name):
    st.session_state["ac_eq_" + name] = int(st.session_state.get("ac_w_" + name, 0) or 0)

def _ac_clear_all_cb():
    for _i in AC_CAT:
        st.session_state["ac_eq_" + _i["name"]] = 0

def _ac_site_postcode():
    m = re.findall(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", (st.session_state.get("q_address") or "").upper())
    return m[-1] if m else ""

def _ac_norm_pc(pc):
    return re.sub(r"\s+", "", (pc or "").upper())

def _ac_get_json(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "SWComms-quotes/1.0"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode("utf-8"))

@st.cache_data(show_spinner=False, ttl=60 * 60 * 24 * 7)
def _ac_journey(office_pc, site_pc):
    """Driving time and distance between two UK postcodes. Raises if it can't be worked out, so failures are never cached."""
    import math
    pts = []
    for pc in (office_pc, site_pc):
        d = _ac_get_json("https://api.postcodes.io/postcodes/" + _ac_norm_pc(pc))
        pts.append((float(d["result"]["latitude"]), float(d["result"]["longitude"])))
    (la1, lo1), (la2, lo2) = pts
    try:
        r = _ac_get_json(f"https://router.project-osrm.org/route/v1/driving/{lo1},{la1};{lo2},{la2}?overview=false")
        rt = r["routes"][0]
        return {"hours": rt["duration"] / 3600.0, "miles": rt["distance"] / 1609.34, "how": "driving route"}
    except Exception:
        p = math.pi / 180
        a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
        miles = 3958.8 * 2 * math.asin(math.sqrt(a)) * 1.3
        return {"hours": miles / 40.0, "miles": miles, "how": "estimate from distance"}

def _ac_journey_for(site_pc):
    if not re.search(r"\d[A-Za-z]{2}\s*$", (site_pc or "").strip()):
        return None
    import time as _t
    key = "_acjfail_" + _ac_norm_pc(site_pc)
    if _t.time() < st.session_state.get(key, 0):
        return None
    try:
        return _ac_journey(str(AC_COST.get("office_postcode") or "CF14 2BT"), site_pc.strip())
    except Exception:
        st.session_state[key] = _t.time() + 60
        return None

def ac_compute():
    """Prices the air-conditioning selection. Equipment and extras are listed one by one at the customer price; materials, labour and
    the installation work are rolled into a single installation line. Everything is leased at this pricebook's own rates."""
    C = AC_COST
    auto = bool(st.session_state.get("ac_auto", True))
    engineers = max(1, int(_ac_num("ac_engineers", 1)))
    listed, counts = [], {k: 0 for k in AC_KINDS}
    mat_cost = mat_sell = lab_cost = lab_sell = 0.0
    eng_days = 0
    for it in AC_CAT:
        q = int(_ac_num("ac_eq_" + it["name"]))
        if q <= 0:
            continue
        g = it.get("group", "")
        if g == "Materials":
            mat_cost += q * float(it["cost"]); mat_sell += q * _ac_srrp(it)
        elif g == "Labour":
            if auto:
                continue
            m = engineers if "engineer" in it["name"].lower() else 1
            lab_cost += q * m * float(it["cost"]); lab_sell += q * m * _ac_srrp(it)
            if "engineer" in it["name"].lower():
                eng_days += q
        else:
            listed.append((it, q))
            if it.get("kind") in counts:
                counts[it["kind"]] += q
    n_sys = counts["wall"] + counts["ceiling"] + counts["ducted"]
    n_units = sum(counts.values())
    maint_annual = 12.0 * (counts["wall"] * C["maint_wall"] + counts["ceiling"] * C["maint_ceiling"]
                           + counts["ducted"] * C["maint_ducted"] + counts["lossnay"] * C["maint_lossnay"])
    extras = (C["cherry_picker"] if st.session_state.get("ac_cherry") == "Yes" else 0.0) + int(_ac_num("ac_pumps")) * C["pump"]
    install_elec = n_sys * C["electrician"] if auto else 0.0
    install_eng = (counts["wall"] * C["lab_wall"] + counts["ceiling"] * C["lab_ceiling"]
                   + counts["ducted"] * C["lab_ducted"] + counts["lossnay"] * C["lab_lossnay"]) if auto else 0.0
    mode = st.session_state.get("ac_days_mode", "Automatic (from the customer's address)")
    site_pc = _ac_site_postcode()
    journey = _ac_journey_for(site_pc) if (auto and mode.startswith("Automatic") and n_units > 0) else None
    far = bool(journey and journey["hours"] > float(C["travel_hours"]))
    if not auto:
        extra_days = 0
    elif mode.startswith("Add"):
        extra_days = int(_ac_num("ac_days_manual"))
    elif mode.startswith("Automatic") and far:
        extra_days = n_units
    else:
        extra_days = 0
    days_worked = max(extra_days, 1)
    extra_eng_cost = (engineers - 1) * days_worked * C["install_day_rate"] if auto else 0.0
    extra_days_cost = extra_days * C["install_day_rate"] + extra_eng_cost
    if auto:
        inst_cost = install_elec + install_eng + extras + extra_days_cost + mat_cost
        inst_sell = (install_elec + install_eng + extras + extra_days_cost) * C["install_mult"] + mat_sell
        est_days = max(extra_days, 1) if engineers > 1 else extra_days
    else:
        inst_cost = lab_cost + extras + mat_cost
        inst_sell = lab_sell + extras * C["install_mult"] + mat_sell
        est_days = eng_days
    inst_name = AC_INSTALL_NAME
    if est_days > 0:
        inst_name += f" - estimated {est_days} day{'s' if est_days != 1 else ''}" + (f", {engineers} engineers" if engineers > 1 else "")
    equip_cost = sum(q * float(it["cost"]) for it, q in listed)
    equip_sell = sum(q * _ac_srrp(it) for it, q in listed)
    any_sel = bool(listed or inst_cost > 0)
    return dict(listed=listed, counts=counts, n_units=n_units, n_sys=n_sys, maint_annual=maint_annual, inst_cost=inst_cost, inst_sell=inst_sell,
                inst_name=inst_name, est_days=est_days, engineers=engineers, extra_days=extra_days, journey=journey, far=far, site_pc=site_pc,
                auto=auto, mode=mode, equip_cost=equip_cost, equip_sell=equip_sell, any=any_sel,
                inst_needed=bool(n_units or listed or mat_cost or lab_cost or extras))

def ac_render():
    """The Air Conditioning dropdown (minimised on entry). Returns the pricing dict."""
    with st.expander("❄️ Air Conditioning", expanded=False):
        st.caption("Choose the manufacturer and size, then the quantity. Air conditioning is quoted and signed as its own SteadyTemp agreement - "
                   "its own price, paperwork and finance, separate from the telephony.")
        t_sys, t_ext, t_mat, t_lab, t_agr = st.tabs(["Systems", "Extras", "Materials", "Labour & install", "Agreement & costs"])
        with t_sys:
            by_grp = {}
            for it in AC_CAT:
                if it.get("group") in AC_SYSTEM_GROUPS:
                    by_grp.setdefault(it["group"], {}).setdefault(_ac_brand(it["name"]), []).append(it)
            cards = [(g, by_grp[g]) for g in AC_SYSTEM_GROUPS if g in by_grp]
            for r0 in range(0, len(cards), 3):
                cols = st.columns(3)
                for col, (grp, by_brand) in zip(cols, cards[r0:r0 + 3]):
                    with col:
                        brands = [b for b in AC_BRANDS if b in by_brand] + [b for b in by_brand if b not in AC_BRANDS]
                        single = len(brands) == 1 and grp == "Lossnay Air Exchange"
                        mk = f"ac_mfr_{grp}"
                        if mk not in st.session_state:
                            st.session_state[mk] = next((b for b in brands for i in by_brand[b] if int(_ac_num("ac_eq_" + i["name"])) > 0), None)
                        _cur = brands[0] if single else st.session_state.get(mk)
                        _first = by_brand[_cur][0] if _cur in by_brand else by_brand[brands[0]][0]
                        _pic = _ac_img(_first) if _cur in by_brand else AC_IMG.get(_first.get("kind", ""))
                        st.markdown(_ac_img_html(_pic), unsafe_allow_html=True)
                        st.markdown(f"**{_ac_esc(grp)}**")
                        if not single:
                            brand = st.selectbox("Manufacturer", brands, index=None, placeholder="Choose manufacturer...", key=mk, label_visibility="collapsed")
                        else:
                            brand = brands[0]
                        if brand:
                            _lg = _ac_logo(brand)
                            if _lg:
                                st.markdown(f"<div style='display:inline-block;background:#fff;border-radius:8px;padding:.2rem .6rem;margin-bottom:.3rem'>"
                                            f"<img src='data:image/{_ac_ext(_lg)};base64,{_lg}' style='height:24px;max-width:130px;object-fit:contain'></div>", unsafe_allow_html=True)
                            items = by_brand[brand]
                            labels = {it["name"]: _ac_variant(it, brand) for it in items}
                            names = list(labels)
                            sk = f"ac_sel_{brand}_{grp}"
                            if sk not in st.session_state:
                                st.session_state[sk] = next((i["name"] for i in items if int(_ac_num("ac_eq_" + i["name"])) > 0), names[0])
                            pick = st.selectbox("Size", names, format_func=lambda n, _l=labels: _l[n], key=sk, label_visibility="collapsed")
                            it = next(i for i in items if i["name"] == pick)
                            st.caption(it.get("desc") or grp)
                            st.number_input("Qty", min_value=0, step=1, value=int(_ac_num("ac_eq_" + it["name"])), key="ac_w_" + it["name"],
                                            on_change=_ac_qty_cb, args=(it["name"],), label_visibility="collapsed")
                        else:
                            st.caption("Choose a manufacturer to pick the size.")
                        chosen = [(i, int(_ac_num("ac_eq_" + i["name"])), b) for b in brands for i in by_brand[b] if int(_ac_num("ac_eq_" + i["name"])) > 0]
                        if chosen:
                            st.markdown("<div style='font-size:.78rem;color:#FFB26B'>Selected</div>", unsafe_allow_html=True)
                            for i, q, b in chosen:
                                st.markdown(f"<div style='font-size:.82rem'>{q} × {_ac_esc(b + ' ' + _ac_variant(i, b) if not single else _ac_variant(i, b))}</div>", unsafe_allow_html=True)
        def _rows(group, tab):
            with tab:
                for it in [i for i in AC_CAT if i.get("group") == group]:
                    c0, c1, c2 = st.columns([1, 5, 2])
                    _b = _ac_img(it)
                    c0.markdown(_ac_img_html(_b, 48), unsafe_allow_html=True)
                    c1.markdown(f"<div style='padding-top:.55rem;font-size:.88rem'>{_ac_esc(it['name'])}</div>", unsafe_allow_html=True)
                    c2.number_input(it["name"], min_value=0, step=1, value=int(_ac_num("ac_eq_" + it["name"])), key="ac_w_" + it["name"],
                                    on_change=_ac_qty_cb, args=(it["name"],), label_visibility="collapsed")
        _rows("Extras", t_ext)
        with t_mat:
            st.caption("Materials are costed in the background and rolled into the installation line - they are not listed separately for the customer.")
        _rows("Materials", t_mat)
        with t_lab:
            st.checkbox("Use automatic installation costs", value=True, key="ac_auto",
                        help="Ticked: the install labour, electrician and any extra days are worked out for you. Untick to cost the installation yourself using the labour lines below.")
            st.selectbox("Number of engineers", [1, 2, 3, 4], key="ac_engineers",
                         help="Normally one engineer. Choose more if the job needs a bigger team.")
            _l1, _l2 = st.columns(2)
            _l1.radio("Cherry picker / access equipment needed?", ["No", "Yes"], key="ac_cherry", horizontal=True)
            _l2.number_input("Condensate pumps (install charge)", min_value=0, step=1, key="ac_pumps")
            st.radio("Extra install days (engineer time)", ["Automatic (from the customer's address)", "No extra days", "Add days manually"], key="ac_days_mode")
            if st.session_state.get("ac_days_mode", "").startswith("Add"):
                st.number_input("Extra install days", min_value=0, step=1, key="ac_days_manual")
            _rows("Labour", t_lab)
            st.caption("The labour lines are only used when automatic installation costs are switched off.")
        with t_agr:
            st.radio("How will the customer pay?", ["Lease (rental over term)", "Cash sale"], key="ac_pay_model", horizontal=True)
            _tm = [int(r["months"]) for r in _ac_cfg.get("lease_rates", AC_LEASE_DEFAULT)]
            st.selectbox("Rental term", _tm, index=(_tm.index(84) if 84 in _tm else len(_tm) - 1), key="ac_term",
                         format_func=lambda m: next((r["label"] for r in _ac_cfg.get("lease_rates", AC_LEASE_DEFAULT) if int(r["months"]) == int(m)), f"{m} months"))
            st.markdown("**Customer's existing air-conditioning costs (per month, for the comparison)**")
            _e1, _e2 = st.columns(2)
            for _i, (_lbl, _key) in enumerate((("Running costs", "ac_cur_running"), ("Service costs", "ac_cur_service"), ("Equipment leasing", "ac_cur_leasing"),
                                               ("Heating", "ac_cur_heating"), ("Other", "ac_cur_other"))):
                (_e1 if _i % 2 == 0 else _e2).number_input(_lbl + " £", min_value=0.0, step=10.0, key=_key)
            st.text_area("Special conditions (printed on the order form)", key="ac_special", height=70)
            if (st.session_state.get("current_user") or {}).get("role") == "admin":
                st.markdown("**Admin**")
                _a2, _a3 = st.columns(2)
                _a2.number_input("Cashback to customer £", min_value=0.0, step=10.0, key="ac_cashback")
                _a3.number_input("Cash-sale discount £", min_value=0.0, step=10.0, key="ac_vol_discount")
        R = ac_compute()
        if R["any"]:
            with st.container(border=True):
                st.markdown("**Air conditioning in this quote**")
                for it, q in R["listed"]:
                    st.markdown(f"<div style='font-size:.84rem'>{q} × {_ac_esc(it['name'])}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:.84rem'>1 × {_ac_esc(R['inst_name'])}</div>", unsafe_allow_html=True)
                if R["auto"]:
                    if R["mode"].startswith("Auto"):
                        j = R["journey"]
                        if not R["site_pc"]:
                            st.caption("Add a postcode to the installation address and the journey is worked out here.")
                        elif j is None:
                            st.caption("Couldn't work out the journey for that postcode - check it, or choose 'Add days manually'.")
                        elif R["far"]:
                            st.caption(f"{j['miles']:.0f} miles / {int(j['hours'])}h {int(round((j['hours'] % 1) * 60)):02d}m from the office - over {AC_COST['travel_hours']:g} hours, "
                                       f"so {R['extra_days']} extra install day{'s' if R['extra_days'] != 1 else ''} added.")
                        else:
                            st.caption("Within range - no extra install days.")
                if R["maint_annual"] > 0:
                    st.caption(f"On-site support: included for the first {int(AC_COST['free_support_years'])} year{'s' if int(AC_COST['free_support_years']) != 1 else ''}, then £{R['maint_annual']:,.2f} a year plus VAT.")
                st.button("Clear air conditioning", key="ac_clear_btn", on_click=_ac_clear_all_cb)
    return ac_compute()

def _ac_none(R):
    """The same air-conditioning dict with nothing in it - what the telephony quote sees."""
    z = dict(R)
    z.update(listed=[], counts={k: 0 for k in AC_KINDS}, n_units=0, n_sys=0, maint_annual=0.0, inst_cost=0.0, inst_sell=0.0,
             equip_cost=0.0, equip_sell=0.0, any=False, inst_needed=False)
    return z


def ac_rate_row(months):
    rows = _ac_cfg.get("lease_rates") or AC_LEASE_DEFAULT
    for r in rows:
        if int(r["months"]) == int(months):
            return r
    return rows[-1]


def ac_order_calc(R):
    """The air-conditioning order priced the SteadyTemp pricebook way: costs + customer price of the equipment, multiplied by the
    rental rate per GBP 1,000 for the term (or the cash price). None when nothing is selected."""
    if not R.get("any"):
        return None
    C = AC_COST
    G = st.session_state.get
    qty = list(R["listed"])
    equip_cost, equip_srrp = float(R["equip_cost"]), float(R["equip_sell"])
    mat_sell = lab_sell = 0.0
    for it in AC_CAT:
        q = int(_ac_num("ac_eq_" + it["name"]))
        if q <= 0:
            continue
        g = it.get("group")
        if g == "Materials":
            qty.append((it, q)); mat_sell += q * _ac_srrp(it)
        elif g == "Labour" and not R["auto"]:
            qty.append((it, q))
            lab_sell += q * (R["engineers"] if "engineer" in it["name"].lower() else 1) * _ac_srrp(it)
    if float(C.get("midea_pack", 1) or 0) > 0:             # Wi-Fi is added to every Midea unit, as the sheet does
        _midea = sum(q for it, q in R["listed"] if it.get("group") in ("Wall Mounted", "Ceiling Cassette", "Ducted") and _ac_brand(it["name"]) == "Midea")
        _wifi = next((i for i in AC_CAT if i["name"] == "WIFI - Built in system wifi Midea"), None)
        if _wifi and _midea > 0:
            _have = next((q for it, q in qty if it["name"] == _wifi["name"]), 0)
            if _midea - _have > 0:
                qty = [(it, q) for it, q in qty if it["name"] != _wifi["name"]] + [(_wifi, _midea)]
                equip_cost += (_midea - _have) * float(_wifi["cost"]); equip_srrp += (_midea - _have) * _ac_srrp(_wifi)
    other = float(G("ac_cashback", 0) or 0)
    additional = float(C["telemarketing"]) + float(C["sales_override"]) + float(C["min_commission"])
    set_up = float(R["maint_annual"]) + float(R["inst_cost"]) + equip_cost + other + additional
    subtotal = set_up + equip_srrp + mat_sell + lab_sell
    term = int(G("ac_term", 84) or 84)
    rr = ac_rate_row(term)
    term = int(rr["months"])
    rate, true_rate = float(rr["rate"]), float(rr.get("true_rate") or rr["rate"])
    try:
        _ov = json.loads(st.session_state.get("adm_cp_json") or "{}")
    except Exception:
        _ov = {}
    _dsc = 0.0                                   # no discounts at South Wales Comms
    calc_rental = subtotal * rate / 1000.0 * (1 - _dsc / 100.0)
    desired = float(G("ac_desired_rental", 0) or 0)
    rental = round(float(_ov["ac"]) if _ov.get("ac") is not None else (desired if desired > 0 else calc_rental), 2)
    funded = rental / true_rate * 1000.0 if true_rate > 0 else 0.0
    gp = funded - set_up
    unit_size = float(C.get("unit_size") or 0)
    commission = (gp / unit_size * float(C.get("unit_value") or 0)) if unit_size else 0.0
    cash_list = subtotal * float(C.get("cash_load") or 1) * (1 - _dsc / 100.0)
    cash_price = round(float(_ov["accash"]) if _ov.get("accash") is not None else cash_list - float(G("ac_vol_discount", 0) or 0), 2)
    is_cash = G("ac_pay_model") == "Cash sale"
    n_sys = R["n_sys"]
    return dict(
        qty=qty, counts=R["counts"], n_units=R["n_units"], is_cash=is_cash, term=term, term_label=rr["label"], profile=f"1+{term - 1}",
        rental=rental, calc_rental=round(calc_rental, 2), cash_list=round(cash_list - float(G("ac_vol_discount", 0) or 0), 2), cash_price=cash_price, discount=_dsc, support=round(float(R["maint_annual"]), 2),
        est_days=R["est_days"], engineers=R["engineers"], auto_install=R["auto"],
        install_elec=(n_sys * float(C["electrician"]) if R["auto"] else 0.0),
        set_up=set_up, subtotal=subtotal, gp=gp, commission=commission, funded=funded,
        cash_gp=cash_price - set_up, extra_days=R["extra_days"],
    )




# ───────────────────────────── Shire Leasing hire agreement (step 2 of signing) ─────────────────────────────
AC_SHIRE_B64 = ""   # the Shire form now lives in assets/shire_lease_agreement.pdf
AC_SHIRE_FILE = Path(__file__).parent / "shire_lease_agreement.pdf"     # drop a newer copy of the form next to app.py to replace the built-in one

def _ac_shire_template():
    import base64
    try:
        if AC_SHIRE_FILE.exists():
            return AC_SHIRE_FILE.read_bytes()
    except Exception:
        pass
    _b = _asset_bytes("shire_lease_agreement.pdf")
    if _b:
        return _b
    raise RuntimeError("The Shire form is missing - upload assets/shire_lease_agreement.pdf to GitHub next to app.py")

def _ac_num_words(n):
    ones = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
            "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    n = int(n)
    if n < 20:
        return ones[n]
    if n < 100:
        return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
    if n < 1000:
        return ones[n // 100] + " Hundred" + (" " + _ac_num_words(n % 100) if n % 100 else "")
    return str(n)

AC_SUPPLIER = {"legal": "South Wales Comms Ltd", "trading": "SteadyTemp Air Conditioning",
               "addr": "10 Plas Melin, Westbourne Road, Whitchurch, Cardiff CF14 2BT"}

def _ac_split_name_pos(raw):
    parts = [p.strip() for p in str(raw or "").split(" - ", 1)]
    return parts[0], (parts[1] if len(parts) > 1 else "")

def ac_shire_values(sign=None):
    """What goes on the Shire hire agreement - the air-conditioning part of the deal only, from the customer's details."""
    G = st.session_state.get
    vat = 1.20
    rental = float(ac_quote["rental"]) if ac_quote else 0.0
    parts = [f"{q} x {it['name']}" for it, q in AC_ORDER["listed"]]
    if AC_ORDER["inst_needed"]:
        parts.append(AC_ORDER["inst_name"])
    desc = "Air conditioning, supplied and installed: " + "; ".join(parts) if parts else "Air conditioning system"
    pc = _ac_site_postcode() or ""
    addr = " ".join(str(G("q_address") or "").replace("\n", ", ").split())
    sc = re.sub(r"\D", "", str(G("q_sort_code") or ""))
    acc = re.sub(r"\D", "", str(G("q_acc_no") or ""))
    nm, ps = _ac_split_name_pos((sign or {}).get("name") or G("q_contact") or "")
    term = int(ac_quote["term"]) if ac_quote else int(lease_term)
    return dict(
        hirer=G("q_comp_name") or "", address=addr, postcode=pc, tel=G("q_phone") or "", reg=G("q_comp_reg") or "",
        email=G("q_dir_email") or G("q_bill_email") or "", desc=desc,
        period=f"{_ac_num_words(term)} months", first_ex=f"{rental:,.2f}", first_inc=f"{rental * vat:,.2f}",
        n_after=str(term - 1), rent_ex=f"{rental:,.2f}", rent_inc=f"{rental * vat:,.2f}", maint="0.00",
        sup_name=f"{st_company()['legal']} (trading as {st_company()['trading']})", sup_addr=", ".join(x for x in st_company()["addr"] if x),
        bank=(G("q_bank_name") or "") + (", " + G("q_bank_addr") if G("q_bank_addr") else ""), holder=G("q_acc_holder") or G("q_comp_name") or "",
        acc=acc, sort=sc, signer=nm, position=ps,
        when=(sign or {}).get("ts", "") and str((sign or {}).get("ts", ""))[:10] or "",
    )

def _sig_transparent(png_bytes):
    """The saved signature on a transparent background (white becomes see-through), so it never blanks out printed lines."""
    from PIL import Image
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    lum = im.convert("L")
    alpha = lum.point(lambda v: max(0, min(255, int((255 - v) * 1.4))))
    out = Image.new("RGBA", im.size, (15, 15, 40, 0))
    out.putalpha(alpha)
    b = io.BytesIO(); out.save(b, format="PNG")
    return b.getvalue()


def tel_shire_values(sign=None):
    """What goes on the Shire hire agreement for the TELEPHONY lease - the hardware rental, from the customer's details."""
    G = st.session_state.get
    vat = 1.20
    rental = float(hw_monthly_spread or 0.0)
    parts = []
    for _d in (desktop_quantities, cordless_quantities, headset_quantities, other_quantities):
        for _n, _q in _d.items():
            if int(_q or 0) > 0:
                parts.append(f"{int(_q)} x {_n}")
    if not _no_switch:
        if switch_quantities:
            parts += [f"{int(_q)} x {_n}" for _n, _q in switch_quantities.items() if int(_q or 0) > 0]
        else:
            try:
                parts.append("1 x " + get_recommended_switch(compute_poe_needed())["name"])
            except Exception:
                pass
    if add_router:
        if router_quantities:
            parts += [f"{int(_q)} x {_n}" for _n, _q in router_quantities.items() if int(_q or 0) > 0]
        elif router_type not in ("None / Customer Supplied", ""):
            parts.append(f"1 x {router_type}")
    if compute_install_cost() > 0:
        parts.append("Installation, programming and project management")
    desc = "Telephone system, supplied and installed: " + "; ".join(parts) if parts else "Telephone system"
    addr = " ".join(str(G("q_address") or "").replace("\n", ", ").split())
    pc = ""
    try:
        pc = bb_find_postcode(addr) or ""
    except Exception:
        pc = ""
    sc = re.sub(r"\D", "", str(G("q_sort_code") or ""))
    acc = re.sub(r"\D", "", str(G("q_acc_no") or ""))
    nm, ps = _ac_split_name_pos((sign or {}).get("name") or G("q_contact") or "")
    term = int(lease_term)
    return dict(
        hirer=G("q_comp_name") or "", address=addr, postcode=pc, tel=G("q_phone") or "", reg=G("q_comp_reg") or "",
        email=G("q_dir_email") or G("q_bill_email") or "", desc=desc,
        period=f"{_ac_num_words(term)} months", first_ex=f"{rental:,.2f}", first_inc=f"{rental * vat:,.2f}",
        n_after=str(term - 1), rent_ex=f"{rental:,.2f}", rent_inc=f"{rental * vat:,.2f}", maint="0.00",
        sup_name=_CO_LEGAL, sup_addr=str(_BRAND.get("address", "")),
        bank=(G("q_bank_name") or "") + (", " + G("q_bank_addr") if G("q_bank_addr") else ""), holder=G("q_acc_holder") or G("q_comp_name") or "",
        acc=acc, sort=sc, signer=nm, position=ps,
        when=(sign or {}).get("ts", "") and str((sign or {}).get("ts", ""))[:10] or "",
    )


def ac_build_shire(sign=None, values=None):
    """The Shire Leasing hire agreement, completed from the quote (and signed if `sign` has the signature). Returns PDF bytes.
    `values` = tel_shire_values(sign) for the telephony lease; the default is the air-conditioning one."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, ArrayObject
    v = values or ac_shire_values(sign)
    rd = PdfReader(io.BytesIO(_ac_shire_template()))
    PW, PH = float(rd.pages[0].mediabox.width), float(rd.pages[0].mediabox.height)
    # where each form box sits (page number, rectangle)
    box = {}
    for pi, pg in enumerate(rd.pages, 1):
        for a in (pg.get("/Annots") or []):
            a = a.get_object()
            if a.get("/Subtype") == "/Widget":
                nm = a.get("/T") or (a["/Parent"].get_object().get("/T") if a.get("/Parent") else None)
                if nm:
                    x0, y0, x1, y1 = [float(z) for z in a["/Rect"]]
                    box[(pi, str(nm))] = (x0, PH - y1, x1 - x0, y1 - y0)       # x, top, width, height
    ov = FPDF(unit="pt", format=(PW, PH)); ov.set_auto_page_break(False)
    ops = {n: [] for n in range(1, len(rd.pages) + 1)}

    def txt(pg, name, text, size=8.5, bold=False, align="L"):
        b = box.get((pg, name))
        if b and text:
            ops[pg].append(("t", b, s(text), size, bold, align))

    def free(pg, x, top, w, h, text, size=8.5, bold=False, align="L"):
        if text:
            ops[pg].append(("t", (x, top, w, h), s(text), size, bold, align))

    # page 3 - the agreement itself
    txt(3, "Full Business Name inc any Trading Name", v["hirer"], 9, True)
    txt(3, "Address", v["address"]); txt(3, "Post Code", v["postcode"]); txt(3, "Telephone No", v["tel"])
    txt(3, "Company Reg No", v["reg"]); txt(3, "Email", v["email"])
    b = box.get((3, "Description of the Equipment including software"))
    if b:
        ops[3].append(("m", b, s(v["desc"]), 8))
    txt(3, "Minimum Period", v["period"], 8)
    txt(3, "fill_23", v["first_ex"], 9, True); txt(3, "fill_24", v["first_inc"], 9, True)
    txt(3, "Followed by", v["n_after"], 9, True); txt(3, "fill_25", v["rent_ex"], 9, True); txt(3, "fill_26", v["rent_inc"], 9, True)
    txt(3, "fill_27", v["maint"], 9)
    txt(3, "Full Business Name", v["sup_name"], 8.5); txt(3, "Address_2", v["sup_addr"], 8)
    # page 4 - direct debit instruction
    txt(4, "Name and full postal address of your Bank or Building Society branch", v["bank"], 8)
    txt(4, "Names of account holders", v["holder"], 9)
    for i, d in enumerate(v["acc"][:8]):
        txt(4, f"Text{22 + i}", d, 11, True, "C")
    for i, d in enumerate(v["sort"][:6]):
        txt(4, f"Text{30 + i}", d, 11, True, "C")
    # page 5 - confirmation of delivery (details always; name, date and signature when the customer signs)
    txt(5, "Full Business Name inc any Trading Name", v["hirer"], 9, True)
    txt(5, "Address", v["address"] + (", " + v["postcode"] if v["postcode"] else ""), 8)
    b = box.get((5, "Description of the Equipment including software"))
    if b:
        ops[5].append(("m", b, s(v["desc"]), 8))
    # page 2 - Shire's printed example ("Alex Sample", 20/07/18): cover the sample entries, and show this customer's own when signed
    for r in ((165, 284, 150, 25), (165, 316, 130, 15), (409, 290, 62, 15), (409, 316, 62, 15)):
        ops[2].append(("w", r))
    # signatures, names, positions and dates (the form has no boxes for these, so they are placed on the printed lines)
    if sign:
        free(3, 138, 740, 170, 12, v["signer"], 9); free(3, 470, 741, 100, 12, v["position"], 9); free(3, 470, 715, 100, 12, v["when"] or date.today().strftime("%d/%m/%Y"), 9)
        free(4, 495, 596, 80, 12, v["when"] or date.today().strftime("%d/%m/%Y"), 9)
        _d = v["when"] or date.today().strftime("%d/%m/%Y")
        free(5, 115, 482, 300, 12, (v["signer"] or "").upper(), 9); free(5, 471, 482, 100, 12, v["position"], 9); free(5, 471, 453, 100, 12, _d, 9)
        free(2, 168, 318, 150, 12, v["signer"], 8, True); free(2, 410, 318, 62, 12, v["position"], 8, True); free(2, 410, 292, 62, 12, _d, 8, True)
        ops[2].append(("sig", (168, 285, 140, 24)))
        sigs = {3: (136, 700, 175, 36), 4: (350, 566, 200, 30), 5: (115, 436, 175, 36)}
        for pg, (x, top, w, h) in sigs.items():
            ops[pg].append(("sig", (x, top, w, h)))
    for n in range(1, len(rd.pages) + 1):
        ov.add_page()
        for op in ops[n]:
            if op[0] == "t":
                _, (x, top, w, h), text, size, bold, align = op
                ov.set_text_color(10, 20, 110); ov.set_font("Helvetica", "B" if bold else "", size)
                while ov.get_string_width(text) > w - 3 and size > 5:
                    size -= 0.5; ov.set_font("Helvetica", "B" if bold else "", size)
                ov.set_xy(x + 1.5, top + max((h - size) / 2 - 0.5, 0)); ov.cell(w - 3, size + 1, text, align=align)
            elif op[0] == "m":
                _, (x, top, w, h), text, size = op
                ov.set_text_color(10, 20, 110); ov.set_font("Helvetica", "", size)
                ov.set_xy(x + 1.5, top + 2); ov.multi_cell(w - 3, size + 1.6, text, max_line_height=size + 1.6)
            elif op[0] == "w":
                _, (x, top, w, h) = op
                ov.set_fill_color(255, 255, 255); ov.rect(x, top, w, h, "F")
            elif op[0] == "sig" and sign and sign.get("bytes"):
                _, (x, top, w, h) = op
                try:
                    # a small white patch over just the grey "Hirer signature" prompt, so the printed lines of the form stay visible
                    ov.set_fill_color(255, 255, 255); _po = {4: (3, 13)}.get(n, (12, 14)); ov.rect(x - 2, top + _po[0], 80, _po[1], "F")
                    ov.image(io.BytesIO(_sig_transparent(sign["bytes"])), x=x, y=top + 1, w=min(w, (h - 5) * 3.1), h=h - 5, keep_aspect_ratio=True)
                except Exception:
                    pass
    ovr = PdfReader(io.BytesIO(bytes(ov.output())))
    wr = PdfWriter()
    for i, src_pg in enumerate(rd.pages):
        pg = wr.add_page(src_pg)          # attach the page to the writer first (newer pypdf requires this before merging)
        keep = [a for a in (pg.get("/Annots") or []) if a.get_object().get("/Subtype") != "/Widget"]      # drop the fillable boxes (and their old sample text)
        if keep:
            pg[NameObject("/Annots")] = ArrayObject(keep)
        elif "/Annots" in pg:
            del pg["/Annots"]
        pg.merge_page(ovr.pages[i])
    out = io.BytesIO(); wr.write(out)
    return out.getvalue()

# ─── HARDWARE BUILDER (main area) ────────────────────────────────────────────

_main_col, _sum_col = st.columns([4, 1.3], gap="medium")
with _main_col:
    _hw_card = st.container(key="card-hardware")
with _hw_card:
    section_header("01", "Hardware", "Phones, networking, CCTV and add-ons for this customer")
    col_hw1, col_hw2 = st.columns([3, 2])
with _sum_col:
    _sum_card = st.container(key="card-summary")
    _sum_card_cs = st.container(key="card-summary-cs")      # Call Scope gets its own card under the telephony one
    _sum_card_ac = st.container(key="card-summary-ac")      # and so does SteadyTemp air conditioning

# ─── SYSTEM HARDWARE BUILDER ─────────────────────────────────────────────────
with col_hw1:
    st.markdown("**🖥️ System Desk Phones**")
    desktop_quantities = {}
    desk_cols = st.columns(3)
    for i, (name, info) in enumerate(HANDSETS_DESKTOP.items()):
        with desk_cols[i % 3]:
            st.markdown(product_card_html(name, info), unsafe_allow_html=True)
            qty = st.number_input(
                f"{'PoE ' if info['poe'] else ''}{name}",
                min_value=0, value=0, step=1, key=f"desk_{name}",
                label_visibility="collapsed"
            )
            if qty > 0:
                desktop_quantities[name] = qty

    # PBX fills the empty column after the last phone card
    _desk_count = len(HANDSETS_DESKTOP)
    _pbx_col_idx = _desk_count % 3  # which column position PBX lands in
    _pbx_col_idx = _desk_count % 3
    with desk_cols[_pbx_col_idx]:
        st.markdown(product_card_html("PBX Unit", {"buy": 150.0, "sell": 500.0, "cat": "Other"}),
                    unsafe_allow_html=True)
        pbx_qty = st.number_input("PBX Unit", min_value=0, value=0, step=1,
                                   key="oth_PBX Unit", label_visibility="collapsed")

    st.markdown("**📞 DECT & Wireless Phones**")
    cordless_quantities = {}
    cord_cols = st.columns(3)
    for i, (name, info) in enumerate(HANDSETS_CORDLESS.items()):
        with cord_cols[i % 3]:
            st.markdown(product_card_html(name, info), unsafe_allow_html=True)
            qty = st.number_input(
                name, min_value=0, value=0, step=1, key=f"cord_{name}",
                label_visibility="collapsed"
            )
            if qty > 0:
                cordless_quantities[name] = qty
    # ── Call Scope: the two headline options as cards ──
    # Call Scope minutes bundles are priced per minute (admin: Service Pricing) - buy 10p / sell 25p by default
    _CS_MIN_BUY  = float(C.get("cs_min_buy", 0.10))
    _CS_MIN_SELL = float(C.get("cs_min_sell", 0.25))
    _CS_MIN_SIZES = (500, 1000, 1500)
    _CS_MINS_COSTS = {f"{m} mins": round(m * _CS_MIN_SELL, 2) for m in _CS_MIN_SIZES}     # label shows minutes only - no prices on screen
    _CS_MINS_BUY   = {f"{m} mins": round(m * _CS_MIN_BUY, 2) for m in _CS_MIN_SIZES}
    _CS_MIN_OPTS = ["None"] + list(_CS_MINS_COSTS)
    _cs_cards_cfg = {x["name"]: x for x in cs_services_cfg()}
    st.markdown("**🔮 Call Scope**")
    _cs_c1, _cs_c2 = st.columns(2)
    with _cs_c1:
        _rq = int(st.session_state.get("cs_AI Receptionist", 0) or 0)
        st.markdown(cs_card_html("AI Receptionist", "Call Scope AI Receptionist", _rq), unsafe_allow_html=True)
        _rec_price = float((_cs_cards_cfg.get("AI Receptionist") or {}).get("sell", 89.0))
        st.number_input(f"AI Receptionist  £{_rec_price:.2f}/mo", min_value=0, value=0, step=1, key="cs_AI Receptionist")
    with _cs_c2:
        _crmq = int(st.session_state.get("cs_AI Integration - CRM", 0) or 0)
        st.markdown(cs_card_html("AI CRM Integration", "Call Scope AI CRM Integration", _crmq), unsafe_allow_html=True)
        st.number_input("AI CRM Integration", min_value=0, value=0, step=1, key="cs_AI Integration - CRM")
        if int(st.session_state.get("cs_AI Integration - CRM", 0) or 0) > 0:
            _mk = "cs_mins_AI Integration - CRM"
            if st.session_state.get(_mk, "None") not in _CS_MIN_OPTS:       # old saved label -> match on the minutes
                _old = str(st.session_state.get(_mk, "None")).split(" ")[0]
                st.session_state[_mk] = next((o for o in _CS_MIN_OPTS if o.split(" ")[0] == _old), "None")
            st.selectbox("Minutes for AI CRM Integration", _CS_MIN_OPTS, key=_mk)
            st.text_input("Customer's CRM (required)", key="cs_crm_name", placeholder="e.g. Zoho, HubSpot, Salesforce",
                          help="Which CRM the customer uses. It is needed before the Call Scope paperwork can be produced.")
            if not str(st.session_state.get("cs_crm_name", "")).strip():
                st.caption(":red[Enter the customer's CRM - the Call Scope paperwork is held back until it is filled in.]")
    # ── Air conditioning (minimised until opened) ──
    AC_ORDER = ac_render()
    AC = _ac_none(AC_ORDER)       # air conditioning is its own SteadyTemp order, so the telephony side sees none of it (see ac_order_calc)
    ac_quote = ac_order_calc(AC_ORDER)
    ac_active = bool(ac_quote)
with col_hw2:
    # ── PBX & CCTV - prominent quick-select ───────────────────────────────────
    st.markdown("<div style='margin-top:2.6rem'></div>", unsafe_allow_html=True)
    with st.expander("📹 CCTV, Security & Access", expanded=False):
        _cctv_col1, _cctv_col2, _cctv_col3 = st.columns(3)
        with _cctv_col1:
            cctv_turret_qty = st.number_input("HIK Vision Turret 8MP", min_value=0, value=0, step=1,
                                               key="cctv_turret", help="buy £125 / sell £427.50")
            cctv_dome_qty   = st.number_input("HIK Vision Dome 8MP",   min_value=0, value=0, step=1,
                                               key="cctv_dome",   help="buy £125 / sell £400.00")
            cctv_nvr_qty    = st.number_input("HIK Vision 24TB NVR",   min_value=0, value=0, step=1,
                                               key="cctv_nvr",    help="buy £750 / sell £1,875")
        with _cctv_col2:
            cctv_int_qty  = st.number_input("Intercom System", min_value=0, value=0, step=1,
                                             key="oth_Intercom System")
            cctv_spk_qty  = st.number_input("Loud Speaker", min_value=0, value=0, step=1,
                                             key="oth_Loud Speaker")
        with _cctv_col3:
            door_qty      = st.number_input("Door Entry System", min_value=0, value=0, step=1,
                                             key="oth_Door Entry System")
            cctv_mon_qty  = st.number_input("Monitor", min_value=0, value=0, step=1, key="cctv_monitor")

    with st.expander("🎧 Headsets", expanded=False):
        headset_quantities = {}
        for name, info in HEADSETS.items():
            qty = st.number_input(name, min_value=0, value=0, step=1, key=f"hs_{name}")
            if qty > 0:
                headset_quantities[name] = qty

    with st.expander("📦 Other Hardware (ATA, WiFi, Routers)", expanded=False):
        other_quantities = {}
        for name, info in OTHER_HARDWARE.items():
            # Skip items handled elsewhere:
            # - CCTV section: HIK Vision cameras/NVR
            # - Router section: Broadband Router (auto-added)
            # - CCTV section: Intercom, Loud Speaker, Door Entry
            # - Headsets section: Bluetooth Headset
            # - PBX: shown in desktop grid
            if name in (
                "PBX Unit",
                "Door Entry System", "Intercom System", "Loud Speaker",
                "HIK Vision Turret 8MP", "HIK Vision Dome 8MP", "HIK Vision 24TB NVR",
                "Broadband Router",
                "Call Scope AI Setup (one-off)",
                "Bluetooth Headset",
                # Call Scope items are chosen in the Call Scope section; Platform Setup is added automatically
                "Call Answer (500 mins)", "Website Widget", "Call Scope Platform Setup",
                "Call Scope AI Receptionist Setup (one-off)",
            ):
                continue
            qty = st.number_input(name, min_value=0, value=0, step=1, key=f"oth_{name}")
            if qty > 0:
                other_quantities[name] = qty

    # Merge quick-select system add-ons into other_quantities
    if pbx_qty > 0:     other_quantities["PBX Unit"] = pbx_qty
    if door_qty > 0:    other_quantities["Door Entry System"] = door_qty
    if cctv_int_qty > 0: other_quantities["Intercom System"] = cctv_int_qty
    if cctv_spk_qty > 0: other_quantities["Loud Speaker"] = cctv_spk_qty
    # CCTV cameras - merge into other_quantities with pricebook pricing
    if cctv_turret_qty > 0: other_quantities["HIK Vision Turret 8MP"] = cctv_turret_qty
    if cctv_dome_qty   > 0: other_quantities["HIK Vision Dome 8MP"]   = cctv_dome_qty
    if cctv_nvr_qty    > 0: other_quantities["HIK Vision 24TB NVR"]   = cctv_nvr_qty

    # Auto-add Broadband Router when BB is selected.
    # Key insight: the "Other Hardware" expander widgets only appear in session_state
    # once the expander is opened. So get("oth_Broadband Router", 1) returns 1 (not 0)
    # when the user has never opened the expander - meaning auto-add should fire.
    # If the user opened the expander and explicitly set it to 0, it returns 0 - skip auto-add.
    _router_user_val = st.session_state.get("oth_Broadband Router", 1)
    # Check via session state whether the router section will add a router
    _router_mode_val = st.session_state.get("router_mode", "Auto-select")
    _router_will_add = (
        (_router_mode_val == "Auto-select" and bb_provider != "None / Customer Supplied") or
        (_router_mode_val == "Manual select" and
         any(st.session_state.get(f"rt_qty_{rn}", 0) > 0 for rn in ROUTERS.keys()))
    )
    _bb_auto_router = (
        bb_provider != "None / Customer Supplied" and
        "Broadband Router" in OTHER_HARDWARE and
        "Broadband Router" not in other_quantities and
        _router_user_val != 0 and                        # 0 = user explicitly cleared it
        not _router_will_add and                         # skip if router section will add one
        _router_mode_val != "None / Customer Supplied"   # respect explicit "no router" choice
    )
    if _bb_auto_router:
        other_quantities["Broadband Router"] = 1

    # Auto-add Call Scope AI Setup fee when agent is selected
    if st.session_state.get("q_sw_crm", 0) > 0:
        if "Call Scope AI Setup (one-off)" not in other_quantities:
            other_quantities["Call Scope AI Setup (one-off)"] = 1
        # Ensure it's in the catalogue (may be missing from old config)
        if "Call Scope AI Setup (one-off)" not in OTHER_HARDWARE:
            OTHER_HARDWARE["Call Scope AI Setup (one-off)"] = {"buy": 1000.00, "sell": 2500.00}

    # Auto-add PBX Unit when total users >= 5 (pricebook rule)
    # total_voice_channels computed after this block - use desk phone count as proxy
    _desk_total = sum(desktop_quantities.values())
    _soft_total = st.session_state.get("standalone_softphones_key", 0)
    # DECT / wireless handsets (DP720, DP735 etc.) are users too; base stations and repeaters are not
    _dect_total = sum(q for n, q in cordless_quantities.items()
                      if not any(k in str(n).lower() for k in ("base station", "repeater")))
    _total_users_preview = _desk_total + _dect_total + _soft_total
    if _total_users_preview >= 5 and "PBX Unit" not in other_quantities:
        other_quantities["PBX Unit"] = 1
        st.info("🔧 PBX Unit auto-added (required for 5+ users)")


    st.markdown("**🎙️ Licences & Add-ons**")
    wallboard_users = 0

    with st.expander("💻 Software Licences & Add-ons", expanded=False):
        st.caption("Optional Telepo features and softphone users")
        standalone_softphones = st.number_input(
            "📱 Mobile App / Softphone-Only Users",
            min_value=0, value=0, step=1,
            help="Users with no desk phone - mobile app or PC softphone. Each adds one hosted user licence.",
            key="standalone_softphones_key"
        )
        st.markdown("---")
        _sw_col1, _sw_col2 = st.columns(2)
        with _sw_col1:
            _sw_studio_on    = st.checkbox("SW Comms Studio  (£5.40/mo)", key="q_sw_studio")
            sw_studio_qty    = 1 if _sw_studio_on else 0
        with _sw_col2:
            sw_ctd_qty       = st.number_input("Click to Dial",     0, 50, 0, key="q_sw_ctd",    help="sell £0.90/user")
            sw_wallboard_qty = st.number_input("Call Recording Dashboard", 0, 10, 0, key="q_sw_wb", help="sell £29.00/instance")
    SW_ADDONS = [
        ("SW Comms Studio",   sw_studio_qty,    4.50, round(4.50 * 1.2, 2)),
        ("Click to Dial",     sw_ctd_qty,       0.75, round(0.75 * 1.2, 2)),
        ("Call Recording Dashboard", sw_wallboard_qty, 0.00, 29.00),   # no cost entered yet - kept at £29 until a cost is set
    ]
    sw_sell_total = sum(qty * sell for _, qty, _, sell in SW_ADDONS if qty > 0)
    sw_cost_total = sum(qty * cost for _, qty, cost, _ in SW_ADDONS if qty > 0)

    with st.expander("🌐 Networking", expanded=False):
        _switch_mode = st.radio("Switch", ["Auto-select", "Manual select", "None / Customer Supplied"],
                                horizontal=True, key="switch_mode")
        if _switch_mode == "None / Customer Supplied":
            auto_switch = False; manual_switch_name = None; _no_switch = True
            switch_quantities = {}
        elif _switch_mode == "Auto-select":
            auto_switch = True; manual_switch_name = None; _no_switch = False
            switch_quantities = {}
        else:
            auto_switch = False
            _no_switch  = False
            manual_switch_name = None
            st.caption("Set quantities for each switch needed:")
            _sw_cols = st.columns(3)
            switch_quantities = {}
            for _si, _sw in enumerate(SWITCHES):
                with _sw_cols[_si % 3]:
                    _sq = st.number_input(_sw["name"], min_value=0, value=0, step=1,
                                          key=f"sw_qty_{_sw['name']}", label_visibility="visible")
                    if _sq > 0:
                        switch_quantities[_sw["name"]] = _sq
        # Auto-select Draytek when South Wales Comms BB is selected, same pattern as switch
        _default_router_mode = "Auto-select" if bb_provider != "None / Customer Supplied" else "None / Customer Supplied"
        _router_mode = st.radio("Router", ["Auto-select", "Manual select", "None / Customer Supplied"],
                                horizontal=True, key="router_mode",
                                index=["Auto-select","Manual select","None / Customer Supplied"].index(
                                    st.session_state.get("router_mode", _default_router_mode)
                                ) if st.session_state.get("router_mode") else
                                ["Auto-select","Manual select","None / Customer Supplied"].index(_default_router_mode))
        # Smart default: FTTP → GWN 706, SoGEA → Technicolour, else Draytek
        _bb_pkg_lower = (bb_package or "").lower()
        if "fttp" in _bb_pkg_lower and "Grandstream GWN7062E (FTTP)" in ROUTERS:
            _default_router = "Grandstream GWN7062E (FTTP)"
        elif "fttp" in _bb_pkg_lower and "Grandstream GWN 706 (FTTP)" in ROUTERS:
            _default_router = "Grandstream GWN 706 (FTTP)"
        elif "sogea" in _bb_pkg_lower and "Technicolour DGA Series (SoGEA)" in ROUTERS:
            _default_router = "Technicolour DGA Series (SoGEA)"
        elif any(x in _bb_pkg_lower for x in ("sogea", "fttp", "leased", "etherway")):
            # Other fibre types — use Draytek as fallback
            _default_router = next((k for k in ROUTERS if "Draytek" in k), list(ROUTERS.keys())[0])
        else:
            # FTTC, ADSL etc — no auto router (ISP provides modem/router)
            _default_router = None
        def _router_for_pkg(_pkg):
            _pl = (_pkg or "").lower()
            if "fttp" in _pl and "Grandstream GWN7062E (FTTP)" in ROUTERS:
                return "Grandstream GWN7062E (FTTP)"
            if "fttp" in _pl and "Grandstream GWN 706 (FTTP)" in ROUTERS:
                return "Grandstream GWN 706 (FTTP)"
            if "sogea" in _pl and "Technicolour DGA Series (SoGEA)" in ROUTERS:
                return "Technicolour DGA Series (SoGEA)"
            if any(x in _pl for x in ("sogea", "fttp", "leased", "etherway")):
                return next((k for k in ROUTERS if "Draytek" in k), list(ROUTERS.keys())[0])
            return None   # FTTC / ADSL - ISP supplied
        router_quantities = {}
        add_router = False
        if _router_mode == "None / Customer Supplied":
            router_type = "None / Customer Supplied"
            add_router  = False
        elif _router_mode == "Auto-select":
            if bb_provider != "None / Customer Supplied":
                # Main line + every additional line gets a matching router
                if _default_router:
                    router_quantities[_default_router] = 1
                for _xp, _xq in extra_bb_lines.items():
                    _xr = _router_for_pkg(_xp)
                    if _xr:
                        router_quantities[_xr] = router_quantities.get(_xr, 0) + _xq
            if router_quantities:
                router_type = _default_router or next(iter(router_quantities))
                add_router  = True
                st.caption("Auto: " + ", ".join(f"{q} x {n}" for n, q in router_quantities.items()))
            else:
                router_type = "None / Customer Supplied"
                add_router  = False
        else:  # Manual select
            add_router = False
            router_type = "None / Customer Supplied"
            st.caption("Set quantities for each router needed:")
            _rt_cols = st.columns(2)
            for _ri, (_rname, _rbuy) in enumerate(ROUTERS.items()):
                with _rt_cols[_ri % 2]:
                    _rq = st.number_input(_rname, min_value=0, value=0, step=1,
                                          key=f"rt_qty_{_rname}", label_visibility="visible")
                    if _rq > 0:
                        router_quantities[_rname] = _rq
                        add_router = True
                        router_type = _rname

        additional_wired_ports = st.number_input(
            "Additional wired network ports", min_value=0,
            value=st.session_state.get("add_wired_ports", 0),
            step=1, key="add_wired_ports",
            help="Extra ports beyond desk phones. Sizes the switch and adds one socket & cable run per port to the lease costs")
        # Each extra wired port = one cable run, priced from the Other Hardware catalogue (editable in Admin)
        _CABLE_ITEM = next((n for n in OTHER_HARDWARE if "cat5" in n.lower() or "cabling" in n.lower()), None)
        if _CABLE_ITEM is None:
            _CABLE_ITEM = "CAT5 Socket & Cabling (ea)"
            OTHER_HARDWARE[_CABLE_ITEM] = {"buy": 65.00}
        if additional_wired_ports > 0:
            other_quantities[_CABLE_ITEM] = other_quantities.get(_CABLE_ITEM, 0) + int(additional_wired_ports)
            st.caption(f"Adds {int(additional_wired_ports)} x {_CABLE_ITEM} to the lease costs")

        # Auto-select only adds a switch once there is something to plug in: a desk phone or an extra wired port.
        if _switch_mode == "Auto-select" and not (any(int(q) > 0 for q in desktop_quantities.values()) or additional_wired_ports > 0):
            auto_switch = False; _no_switch = True
            st.caption("No switch added yet - one is chosen automatically once a desk phone or wired port is added.")

    with st.expander("📱 Mobiles", expanded=False):
        mobile_rows = []
        for net, pkgs in MOBILE_NETWORKS.items():
            for pkg, pricing in pkgs.items():
                qty = st.number_input(
                    f"{net} - {pkg}",
                    min_value=0, value=0, step=1, key=f"mob_{net}_{pkg}"
                )
                if qty > 0:
                    mobile_rows.append({"network": net, "package": pkg, "qty": qty, **pricing})


    with st.expander("💻 IT Services", expanded=False):
        st.caption("Per-user monthly licences — billed separately to the hardware lease")
        it_rows = []
        for it_cat, it_pkgs in IT_SERVICES.items():
            st.markdown(f"**{it_cat}**")
            for pkg_name, pkg_info in it_pkgs.items():
                _it_sell = round(pkg_info["cost"] * 1.2, 2)
                qty = st.number_input(
                    f"{pkg_name}  (£{_it_sell:.2f}/user/mo)",
                    min_value=0, value=0, step=1, key=f"it_{pkg_name}"
                )
                if qty > 0:
                    it_rows.append({"service": pkg_name, "qty": qty,
                                    "cost": pkg_info["cost"], "sell": _it_sell})

    # ── System Security expander ─────────────────────────────────────────────
    with st.expander("🛡️ System Security", expanded=False):
        st.caption("Managed security tiers — per instance per month")
        if "system_security" not in st.session_state.active_config:
            st.session_state.active_config["system_security"] = [
                {"name": "Bronze Security", "buy": 7.00,  "sell": 10.00},
                {"name": "Silver Security", "buy": 10.00, "sell": 15.00},
                {"name": "Gold Security",   "buy": 14.00, "sell": 20.00},
            ]
        sec_cfg = st.session_state.active_config.get("system_security", [])
        for _sc in sec_cfg:
            st.number_input(f"{_sc['name']}  (£{_sc['sell']:.2f}/instance/mo)",
                            min_value=0, value=0, step=1, key=f"sec_{_sc['name']}")


    with st.expander("🔮 Call Scope", expanded=False):
        st.caption("More Call Scope modules (monthly services). The AI Receptionist and AI CRM Integration are the cards on the left. "
                   "Call Scope is quoted and signed as its own agreement, separate from the telephony.")
        _cs_exp_cfg = [x for x in cs_services_cfg() if x["name"] not in CS_CARD_NAMES]
        _cse_col1, _cse_col2 = st.columns(2)
        with _cse_col1:
            for _cs in _cs_exp_cfg[:1]:
                st.number_input(_cs["name"], min_value=0, value=0, step=1, key=f"cs_{_cs['name']}")
                if "AI Integration" in _cs["name"] and st.session_state.get(f"cs_{_cs['name']}", 0) > 0:
                    _mk = f"cs_mins_{_cs['name']}"
                    if st.session_state.get(_mk, "None") not in _CS_MIN_OPTS:       # old saved label -> match on the minutes
                        _old = str(st.session_state.get(_mk, "None")).split(" ")[0]
                        st.session_state[_mk] = next((o for o in _CS_MIN_OPTS if o.split(" ")[0] == _old), "None")
                    st.selectbox(f"Minutes for {_cs['name']}", _CS_MIN_OPTS, key=_mk)
            _mypa_opts_cfg = st.session_state.active_config.get("mypa_bundles", [
                {"name": "My PA 500 mins",  "sell": 149.0},
                {"name": "My PA 1000 mins", "sell": 199.0},
                {"name": "My PA 2000 mins", "sell": 249.0},
            ])
            _mypa_opts = ["None"] + [mp["name"].replace("My PA ", "") for mp in _mypa_opts_cfg]
            _cur_mypa = st.session_state.get("cs_mypa", "None")
            if _cur_mypa not in _mypa_opts:                                          # old saved label with a price in it
                st.session_state["cs_mypa"] = next((o for o in _mypa_opts if o.split(" ")[0] == str(_cur_mypa).split(" ")[0]), "None")
            st.selectbox("Call Answer - My PA", _mypa_opts, key="cs_mypa")
        with _cse_col2:
            for _cs in _cs_exp_cfg[1:]:
                st.number_input(_cs["name"], min_value=0, value=0, step=1, key=f"cs_{_cs['name']}")
            if st.session_state.get("cs_website", "None") not in ("None", "Include"):
                st.session_state["cs_website"] = "Include"                            # old saved label with a price in it
            st.selectbox("Website Widget", ["None", "Include"], key="cs_website")
        st.checkbox("🎁 AI Portal — 1st month free (500 mins)", key="cs_ai_portal_free",
                    help="Promotional offer: first month of AI Portal 500-min bundle at no charge")
        st.markdown("**Call Scope agreement**")
        _cag1, _cag2 = st.columns(2)
        with _cag1:
            st.selectbox("Call Scope term", [12, 24, 36, 48, 60, 84], index=2, key="cs_term", format_func=lambda m: f"{m} months")
        with _cag2:
            pass
        if (st.session_state.get("current_user") or {}).get("role") == "admin":
            st.checkbox("Waive the Call Scope set-up fees", key="cs_setup_waive")

# ─── POST-EXPANDER REBUILDS (session state → module-level lists) ─────────────
# Call Scope services
cs_cfg_mod = st.session_state.active_config.get("call_scope_services", [
    {"name": "AI Integration - Portal", "buy": 18.00, "sell": 49.00},
    {"name": "AI Integration - CRM", "buy": 5.00, "sell": 35.00},
    {"name": "Manager Dashboard", "buy": 5.00, "sell": 59.00},
    {"name": "Call Score", "buy": 20.00, "sell": 45.00},
    {"name": "AI Receptionist", "buy": 25.00, "sell": 89.00},
])
# ─── LETTER OF AUTHORITY (number porting) ─────────────────────────────────────
_LOA_PAGES = {}     # first/last page numbers of the LOA inside the core pack (used to cut out a stand-alone copy)

def _loa_split_address(text, postcode_hint=""):
    """Best-effort split of a free-text address into building, street, town, county, postcode."""
    txt = (text or "").strip()
    pc = ""
    try:
        pc = bb_find_postcode(txt) or ""
    except Exception:
        pc = ""
    lines = [l.strip(" ,") for l in re.split(r"[\n]+", txt) if l.strip(" ,")]
    if pc:
        pc_pat = re.compile(re.escape(pc).replace(r"\ ", r"\s*"), re.I)
        lines = [l for l in (pc_pat.sub("", l).strip(" ,") for l in lines) if l]
    b = st_ = t = c = ""
    if len(lines) >= 4:
        b, t, c = lines[0], lines[-2], lines[-1]; st_ = ", ".join(lines[1:-2])
    elif len(lines) == 3:
        st_, t, c = lines
    elif len(lines) == 2:
        st_, t = lines
    elif len(lines) == 1:
        st_ = lines[0]
    return {"building": b, "street": st_, "town": t, "county": c, "postcode": pc or postcode_hint}

def _loa_numbers():
    """Customer's main number first, then any extras the consultant typed. De-duplicated by digits."""
    main = (st.session_state.get("q_phone") or "").strip()
    extra = re.split(r"[\n,;]+", st.session_state.get("q_loa_numbers") or "")
    out, seen = [], set()
    for n in ([main] if main else []) + extra:
        n = " ".join(n.split())
        d = re.sub(r"\D", "", n)
        if n and d and d not in seen:
            seen.add(d); out.append(n)
    return out

def _loa_data():
    g = lambda k: (st.session_state.get(k) or "").strip()
    site_txt = g("q_loa_site") or g("q_address")
    bill_txt = g("q_loa_bill") or site_txt
    nums = _loa_numbers()
    cn = g("q_contact"); nm, _, jt = cn.partition(" - ")
    return {"on": bool(st.session_state.get("q_loa_on", True)), "numbers": nums,
            "provider": g("q_loa_provider"), "prov_addr": g("q_loa_prov_addr"),
            "mbn": g("q_loa_mbn") or (nums[0] if nums else ""), "acct": g("q_loa_acct"),
            "site": _loa_split_address(site_txt), "bill": _loa_split_address(bill_txt),
            "comp": g("q_comp_name"), "reg": g("q_comp_reg"),
            "name": nm.strip(), "title": jt.strip(), "email": g("q_dir_email")}

def _loa_pages(pdf, add_header, sig_bytes=None, sig_ts=""):
    """Draws the Customer Letter of Authority (plus continuation sheets) onto the pack. Own-brand look,
    same fields as the standard CLoA form. Latin-1 safe via s()."""
    d = _loa_data()
    _apb, _bm = pdf.auto_page_break, pdf.b_margin
    pdf.set_auto_page_break(False)
    L, W = pdf.l_margin, pdf.epw
    NAVY, TEAL, GREY = (8, 31, 58), (27, 120, 214), (235, 236, 242)
    first_page = pdf.page_no() + 1

    def hdr_cell(x, y, w, h, text, align="L", size=9.5):
        pdf.set_fill_color(*NAVY); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", size)
        pdf.set_xy(x, y); pdf.cell(w, h, "  " + s(text), fill=True, align=align, border=1)
        pdf.set_text_color(0, 0, 0)

    def lab(x, y, w, h, text):
        pdf.set_fill_color(*GREY); pdf.set_font("Helvetica", "", 8.2)
        pdf.set_xy(x, y); pdf.cell(w, h, "  " + s(text), fill=True, border=1)

    def val(x, y, w, h, text, bold=False, size=8.6):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_xy(x, y); pdf.cell(w, h, " " + s(text), border=1)

    def requester_block(y, with_sig):
        hdr_cell(L, y, W, 7, "Requester's Details"); y += 7
        lab(L, y, 38, 14, "Signed"); pdf.set_xy(L + 38, y); pdf.cell(W - 38, 14, "", border=1)
        if with_sig and sig_bytes and len(sig_bytes) > 100:
            try:
                import tempfile as _t, os as _o
                with _t.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    f.write(sig_bytes); pth = f.name
                try:
                    pdf.image(pth, x=L + 41, y=y + 1, h=12)
                finally:
                    _o.unlink(pth)
            except Exception:
                pass
        y += 14
        lab(L, y, 38, 7, "Print Name"); val(L + 38, y, 62, 7, d["name"])
        lab(L + 100, y, 22, 7, "Job title"); val(L + 122, y, W - 122, 7, d["title"]); y += 7
        lab(L, y, 38, 7, "Date (DD/MM/YYYY)")
        val(L + 38, y, 62, 7, (sig_ts.split()[0] if (sig_bytes and sig_ts) else (date.today().strftime("%d/%m/%Y") if sig_bytes else "")))
        lab(L + 100, y, 22, 7, "Email"); val(L + 122, y, W - 122, 7, d["email"])
        return y + 7

    nums = d["numbers"]
    CAP = 22
    if len(nums) > CAP:
        on_page, overflow = nums[:CAP - 2], nums[CAP - 2:]
    else:
        on_page, overflow = nums, []

    # ── Page 1 ────────────────────────────────────────────────────────────────
    pdf.add_page(); add_header(pdf, "Customer Letter of Authority (CLoA)")
    y = 48
    pdf.set_font("Helvetica", "I", 8.5); pdf.set_xy(L, y); pdf.cell(W, 5, "for the porting of numbers from one provider to another", align="C")
    y += 7
    hw = W / 2
    hdr_cell(L, y, hw, 7, "Current Provider", "C"); hdr_cell(L + hw, y, hw, 7, "New Provider", "C"); y += 7
    lab(L, y, 22, 7, "Name"); val(L + 22, y, hw - 22, 7, d["provider"] or "")
    lab(L + hw, y, 22, 7, "Name"); val(L + hw + 22, y, hw - 22, 7, _BRAND["legal"]); y += 7
    lab(L, y, 22, 16, "Address:"); pdf.set_xy(L + 22, y); pdf.cell(hw - 22, 16, "", border=1)
    pdf.set_font("Helvetica", "", 8.2); pdf.set_xy(L + 23, y + 1)
    pdf.multi_cell(hw - 24, 4, s(d["prov_addr"]) if d["prov_addr"] else "")
    lab(L + hw, y, 22, 16, "Address:"); pdf.set_xy(L + hw + 22, y); pdf.cell(hw - 22, 16, "", border=1)
    pdf.set_font("Helvetica", "", 8.2); pdf.set_xy(L + hw + 23, y + 1); pdf.multi_cell(hw - 24, 4, s(_BRAND["address"]))
    y += 21

    lw = 100
    hdr_cell(L, y, lw, 7, "Site address to register against numbers")
    hdr_cell(L + lw, y, W - lw, 7, "Numbers to be Ported (Geo & non-Geo)", "C", 8.8)
    y += 7
    row = 6.5; site = d["site"]
    srows = [("Building Name / Number", site["building"]), ("Street Name", site["street"]), ("Town/City", site["town"]),
             ("County", site["county"]), ("Post Code", site["postcode"]), ("MBN - Main Billing No. (Geo)", d["mbn"])]
    for i, (a, b) in enumerate(srows):
        lab(L, y + i * row, 44, row, a); val(L + 44, y + i * row, lw - 44, row, b)
    box_h = row * len(srows)
    pdf.set_xy(L + lw, y); pdf.cell(W - lw, box_h, "", border=1)
    pdf.set_font("Helvetica", "B", 8.6)
    colw = (W - lw) / 2
    for i, n in enumerate(on_page):
        cx = L + lw + (i // 11) * colw; cy = y + 1.2 + (i % 11) * 3.45
        pdf.set_xy(cx + 1.5, cy); pdf.cell(colw - 2, 3.4, s(n))
    if overflow:
        pdf.set_font("Helvetica", "I", 7); pdf.set_xy(L + lw + colw + 1.5, y + 1.2 + 10 * 3.45)
        pdf.cell(colw - 2, 3.4, f"+{len(overflow)} more - see next sheet")
    y += box_h + 6

    hdr_cell(L, y, W, 7, "Customer's Company Details (as shown on most recent bill from current provider)"); y += 7
    bill = d["bill"]
    crow = [("Company Name", d["comp"]),
            ("Billing Address", ", ".join(x for x in (bill["building"], bill["street"]) if x)),
            ("Town/City", bill["town"]), ("County", bill["county"]), ("Post Code", bill["postcode"]),
            ("Company Registration No.", d["reg"]), ("Billing Account No. (Non-Geo only)", d["acct"])]
    for i, (a, b) in enumerate(crow):
        lab(L, y + i * row, 62, row, a); val(L + 62, y + i * row, W - 62, row, b)
    y += row * len(crow) + 6

    pdf.set_font("Helvetica", "", 8.2); pdf.set_xy(L, y)
    pdf.multi_cell(W, 4.2, s("**Fao my current provider**; this CLoA is to notify you that I (representing the customer shown above) have taken the decision to move my "
        "telephony services to a new Provider and require the numbers associated with those services to be ported across to my chosen new "
        "Provider (stated above)."), align="J", markdown=True)
    pdf.ln(1.5); pdf.set_x(L)
    pdf.multi_cell(W, 4.2, s("My new Provider is authorised to act on my behalf in this matter and you have my authority to disclose to my new "
        "Provider (at their request) any other service or site-specific details they might need to allow this port to proceed (e.g. site / "
        "billing address post code, DDI number range, Main Billing Number (MBN), etc.)."), align="J")
    pdf.ln(1.5); pdf.set_x(L)
    pdf.multi_cell(W, 4.2, s("I recognise that it is my responsibility to arrange the cessation of, or changes to, any other services provided "
        "by my current Provider."), align="J")
    y = pdf.get_y() + 4
    requester_block(y, True)

    # ── Continuation sheets ───────────────────────────────────────────────────
    PER_PAGE, COLS = 96, 4
    pg = 0
    while overflow:
        chunk, overflow = overflow[:PER_PAGE], overflow[PER_PAGE:]
        pg += 1
        pdf.add_page(); add_header(pdf, f"Letter of Authority - Continuation Sheet {pg}")
        y = 48
        pdf.set_font("Helvetica", "", 8.5); pdf.set_xy(L, y)
        pdf.multi_cell(W, 4.5, s(f"Customer: {d['comp']}   |   Current provider: {d['provider'] or '-'}   |   New provider: {_BRAND['legal']}"))
        y = pdf.get_y() + 2
        hdr_cell(L, y, W, 7, "Numbers to be Ported (Geo & non-Geo) - continued"); y += 7
        cw = W / COLS; rows_n = -(-len(chunk) // COLS)
        for r in range(rows_n):
            for c in range(COLS):
                i = r * COLS + c
                pdf.set_xy(L + c * cw, y + r * 6); pdf.set_font("Helvetica", "", 8.6)
                pdf.cell(cw, 6, " " + (s(chunk[i]) if i < len(chunk) else ""), border=1)
        y += rows_n * 6 + 8
        requester_block(y, True)

    _LOA_PAGES["range"] = (first_page, pdf.page_no())
    pdf.set_auto_page_break(_apb, _bm)

# ── Printers (Ricoh): own expander in the right-hand column ────────────────
printer_rows = []
with col_hw2:
    _prn_open = any(int(st.session_state.get(f"prn_qty_{_pn}", 0) or 0) > 0 for _pn in PRINTERS)
    with st.expander("🖨️ Printers (Ricoh)", expanded=_prn_open):
        st.caption("Leased separately on their own term. Set up & delivery is included per printer. "
                   "Print charges are per page, billed on usage.")
        st.selectbox("Printer lease term", PRINTER_TERMS, index=PRINTER_TERMS.index(60), key="prn_term",
                     format_func=lambda _m: f"{_m} months")
        for _pn, _pi in PRINTERS.items():
            _pq_now = int(st.session_state.get(f"prn_qty_{_pn}", 0) or 0)
            _pc1, _pc2 = st.columns([1, 1.5])
            with _pc1:
                st.markdown(product_card_html(_pn, {"cat": "Printer"}, qty=_pq_now, img_height=70), unsafe_allow_html=True)
            with _pc2:
                _pq = st.number_input("Quantity", 0, 20, 0, 1, key=f"prn_qty_{_pn}")
                _pv = 0
                if _pq > 0:
                    _pv = st.number_input("Est. prints per month", 0, 500000, 1000, 250, key=f"prn_vol_{_pn}")
            if _pq > 0:
                printer_rows.append({"name": _pn, "qty": int(_pq), "cost": float(_pi["cost"]),
                                     "cpc_cost": float(_pi["cpc"]), "volume": int(_pv)})

# ── Number porting: Letter of Authority ────────────────────────────────────
with col_hw2:
    with st.expander("📞 Number porting - Letter of Authority", expanded=False):
        st.caption("Ticked by default so it isn't forgotten. Untick it if we are not taking over any of the customer's existing "
                   "numbers. When ticked, a Letter of Authority is added to the pack, and can also be downloaded on its own "
                   "to send to the old provider.")
        st.checkbox("Include a Letter of Authority", key="q_loa_on")
        if st.session_state.get("q_loa_on"):
            st.text_input("Existing service provider", key="q_loa_provider",
                          placeholder="e.g. BT, Virgin Media Business, Gamma")
            st.text_area("Existing provider's address (optional)", key="q_loa_prov_addr", height=70)
            _mn = (st.session_state.get("q_phone") or "").strip()
            st.caption(f"Main number from the customer form: **{_mn}** - it is included automatically." if _mn
                       else "No main number on the customer form yet - add it under Customer Details, or list it below.")
            st.text_area("Additional numbers to port", key="q_loa_numbers", height=110,
                         placeholder="One per line (or separated by commas)\n01743 123456\n01743 123457\n0800 123 4567")
            st.text_input("Main billing number - MBN (optional)", key="q_loa_mbn",
                          help="Geographic numbers only. If left blank the customer's main number is used.")
            st.text_input("Billing account number (optional)", key="q_loa_acct", help="Non-geographic numbers only.")
            st.text_area("Site address for the numbers (only if different from the installation address)", key="q_loa_site", height=70)
            st.text_area("Billing address on the latest bill (only if different from the site address)", key="q_loa_bill", height=70)
            _ld = _loa_data()
            st.caption(f"{len(_ld['numbers'])} number(s) will be ported.")
            if not _ld["provider"]:
                st.caption(":orange[Add the existing service provider - it goes on the form.]")
            if not _ld["numbers"]:
                st.caption(":orange[No numbers yet - nothing will be added to the pack until there is at least one.]")

cs_svc_rows = []
for _cs in cs_cfg_mod:
    qty = st.session_state.get(f"cs_{_cs['name']}", 0)
    if qty > 0:
        cs_svc_rows.append({"name": CS_DISPLAY_NAMES.get(_cs["name"], _cs["name"]), "qty": qty, "buy": _cs["buy"], "sell": _cs["sell"]})
        # Add minutes bundle cost if selected for AI Integration modules
        if "AI Integration" in _cs["name"]:
            _mins_sel = st.session_state.get(f"cs_mins_{_cs['name']}", "None")
            _mins_cost = _CS_MINS_COSTS.get(_mins_sel, 0.0)
            if _mins_cost > 0:
                cs_svc_rows.append({"name": f"{CS_DISPLAY_NAMES.get(_cs['name'], _cs['name'])} — {_mins_sel.split('—')[0].strip()}",
                                    "qty": 1, "buy": _CS_MINS_BUY.get(_mins_sel, _mins_cost * 0.4), "sell": _mins_cost, "minutes": True})
_rec_qty = int(st.session_state.get("cs_AI Receptionist", 0) or 0)      # its set-up goes on the separate Call Scope order, not the lease
_cs_mypa_sel  = st.session_state.get("cs_mypa", "None")
_cs_web_sel   = st.session_state.get("cs_website", "None")
cs_call_answer = _cs_mypa_sel != "None"
cs_website     = _cs_web_sel != "None"
cs_any_selected = bool(cs_svc_rows or cs_call_answer or cs_website)
# Build My PA cost lookup from config (picks up admin price changes)
_mypa_defaults_calc = [
    {"name": "My PA 500 mins",  "buy": 100.0, "sell": 149.0},
    {"name": "My PA 1000 mins", "buy": 140.0, "sell": 199.0},
    {"name": "My PA 2000 mins", "buy": 180.0, "sell": 249.0},
]
_mypa_cfg_calc = st.session_state.active_config.get("mypa_bundles", _mypa_defaults_calc)
_CS_MYPA_COSTS = {mp["name"].replace("My PA ", ""): round(float(mp["buy"]) * 1.2, 2) for mp in _mypa_cfg_calc}
_CS_MYPA_BUY = {mp["name"].replace("My PA ", ""): mp["buy"] for mp in _mypa_cfg_calc}
_mypa_sel = st.session_state.get("cs_mypa", "None")
if _mypa_sel != "None":
    _mypa_cost = _CS_MYPA_COSTS.get(_mypa_sel, 0.0)
    _mypa_buy  = _CS_MYPA_BUY.get(_mypa_sel, _mypa_cost * 0.7)
    if _mypa_cost > 0:
        cs_svc_rows.append({"name": f"Call Answer - My PA ({_mypa_sel})",
                            "qty": 1, "buy": _mypa_buy, "sell": _mypa_cost})
_web_sel = st.session_state.get("cs_website", "None")
if _web_sel != "None":
    _web_cs_cfg = next((s for s in st.session_state.active_config.get("call_scope_services", [])
                        if s.get("name") == "Website Widget"), {"buy": 30.0, "sell": 50.0})
    cs_svc_rows.append({"name": "Website Widget", "qty": 1,
                        "buy": _web_cs_cfg.get("buy", 30.0), "sell": round(float(_web_cs_cfg.get("buy", 30.0)) * 1.2, 2)})

for _r_ in cs_cfg_mod:
    _r_["sell"] = round(float(_r_["buy"]) * 1.2, 2)
# System Security
sec_cfg_mod = st.session_state.active_config.get("system_security", [
    {"name": "Bronze Security", "buy": 7.00, "sell": 10.00},
    {"name": "Silver Security", "buy": 10.00, "sell": 15.00},
    {"name": "Gold Security", "buy": 14.00, "sell": 20.00},
])
for _r_ in sec_cfg_mod:
    _r_["sell"] = round(float(_r_["buy"]) * 1.2, 2)
sec_rows = []
for _sc in sec_cfg_mod:
    qty = st.session_state.get(f"sec_{_sc['name']}", 0)
    if qty > 0:
        sec_rows.append({"name": _sc["name"], "qty": qty, "buy": _sc["buy"], "sell": _sc["sell"]})

# Call Scope is its own agreement: its services and set-up fees are priced on their own order (see "CALL SCOPE ORDER" below),
# so the telephony side of the quote - lease, services, P&L and paperwork - sees none of it.
cs_order_rows = [dict(r) for r in cs_svc_rows]
cs_svc_rows = []

# ─── MANAGER OVERRIDE SECTION ────────────────────────────────────────────────

# --- AUTO-CALCULATE VOICE CHANNELS -----------------------------------
# One licence required per physical handset (mirrors Excel SYSTEM BUILDER I16)
# Standalone softphones add extra seats on top
# DECT base stations and repeaters are not users, so they never add a licence
_NON_USER_DECT = ("base station", "repeater")
def _is_user_handset(_n): return not any(k in str(_n).lower() for k in _NON_USER_DECT)
auto_handset_licences = (
    sum(desktop_quantities.values()) +
    sum(q for n, q in cordless_quantities.items() if _is_user_handset(n))
)
user_licences        = auto_handset_licences
softphone_licences   = standalone_softphones
total_voice_channels = user_licences + softphone_licences

st.info(
    f"🎙️ **Voice Channels: {total_voice_channels}** "
    f"({user_licences} desk phone{"s" if user_licences != 1 else ""} + {softphone_licences} softphone/mobile app)"
)
if total_voice_channels >= 5:
    _pbx_qty = sum(q for n, q in other_quantities.items() if "PBX" in n.upper() or "pbx" in n.lower())
    if _pbx_qty == 0:
        st.warning("⚠️ 5+ users: a **PBX Unit** is required - add one from the Other Hardware section above.")
    else:
        st.success(f"✅ PBX Unit included (×{_pbx_qty})")

# ─── TABS ─────────────────────────────────────────────────────────────────────

def s(text):
    """Sanitise text for fpdf2 - replaces/strips characters outside latin-1."""
    if not text:
        return ""
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ",
        "\u00ae": "(R)", "\u00a9": "(C)", "\u00e9": "e", "\u00e8": "e",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def price_rise_figures():
    """(monthly services £, rise £/month, new monthly £, pct, rise £/year) - the increase applies to monthly services only (hardware rental is fixed)."""
    base = round(float(svc.get("total_sell", 0) or 0), 2)
    pct = float(PRICE_RISE_PCT or 0)
    inc = round(base * pct / 100.0, 2)
    return base, inc, round(base + inc, 2), pct, round(inc * 12, 2)

def build_proposal_pdf(sign=None, cis=False):
    """Two-page proposal in the app's dark style, using the logged-in brand's accent.
    Page 1: headline saving / daily investment + full cost comparison.
    Page 2: new system, monthly services, agreement terms, why us, call to action."""
    from fpdf import FPDF

    def _ps(text):
        t = str(text or "").replace("\u2014", "-").replace("\u2013", "-").replace("\u2019", "'")
        return t.encode("latin-1", errors="replace").decode("latin-1")

    def _rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def gbp(v):
        return f"\u00a3{v:,.2f}"

    BG, SURF, SURF2, SURF3 = (10, 14, 26), (17, 24, 39), (22, 31, 51), (28, 39, 64)
    LINE, TEXT, MUTED, FAINT = (41, 50, 71), (231, 234, 243), (140, 152, 176), (94, 106, 130)
    GOOD = (52, 211, 153)
    ACC  = _rgb(_BRAND.get("ui_accent", "#1b78d6"))
    ACC2 = _rgb(_BRAND.get("ui_accent2", "#6EE7D8"))
    ACC_SOFT = tuple(int(SURF[i] + (ACC[i] - SURF[i]) * 0.18) for i in range(3))
    STAGE = (236, 240, 247)
    PW, PH, M = 210, 297, 15
    CW = PW - 2 * M

    _logo_raw = base64.b64decode(SYCOMMS_LOGO_B64) if _BRAND.get("logo_key") else None

    class _Dark(FPDF):
        def header(self):
            self.set_fill_color(*BG)
            self.rect(0, 0, PW, PH, "F")

        def footer(self):
            self.set_y(-11)
            self.set_draw_color(*LINE); self.set_line_width(0.2)
            self.line(M, PH - 13, PW - M, PH - 13)
            self.set_font("Helvetica", "", 6.8); self.set_text_color(*FAINT)
            self.cell(CW * 0.8, 5, _ps(f"{_CO_LEGAL}  \u00b7  {_CO_EMAIL}  \u00b7  {_CO_PHONE}  \u00b7  {_CO_WEB}"))
            self.cell(CW * 0.2, 5, f"{self.page_no()}", align="R")

    p = _Dark(format="A4")
    p.set_margins(M, M, M)
    p.set_auto_page_break(True, margin=18)

    # ── small building blocks ────────────────────────────────────────────────
    def topbar(right_text):
        y = 12
        if _logo_raw:
            p.image(io.BytesIO(_logo_raw), x=M, y=y + 0.5, w=44, keep_aspect_ratio=True)
            p.set_xy(M, y + 9.2); p.set_font("Helvetica", "", 7); p.set_text_color(*MUTED)
            p.cell(90, 4, "Contract information sheet" if cis else "Customer proposal")
        else:
            p.set_fill_color(*ACC)
            p.rect(M, y, 10, 10, "F", round_corners=True, corner_radius=2.5)
            p.set_font("Helvetica", "B", 7.5); p.set_text_color(*BG)
            p.set_xy(M, y + 2.5); p.cell(10, 5, _ps(_BRAND.get("mono", _CO[:2])), align="C")
            p.set_xy(M + 13, y + 0.8); p.set_font("Helvetica", "B", 11); p.set_text_color(*TEXT)
            p.cell(90, 5, _ps(_CO))
            p.set_xy(M + 13, y + 5.6); p.set_font("Helvetica", "", 7); p.set_text_color(*MUTED)
            p.cell(90, 4, "Contract information sheet" if cis else "Customer proposal")
        p.set_xy(M, y + 2.6); p.set_font("Helvetica", "", 8); p.set_text_color(*MUTED)
        p.cell(CW, 5, _ps(right_text), align="R")
        p.set_draw_color(*LINE); p.set_line_width(0.2)
        p.line(M, y + 15, PW - M, y + 15)
        return y + 15

    def eyebrow(text, y):
        p.set_fill_color(*GOOD); p.ellipse(M, y + 1.1, 2.2, 2.2, "F")
        p.set_xy(M + 4, y); p.set_font("Helvetica", "B", 7.5); p.set_text_color(*ACC2)
        p.set_char_spacing(1.1); p.cell(CW - 4, 4.5, _ps(text.upper())); p.set_char_spacing(0)

    def section(num, title, sub=""):
        if p.get_y() > PH - 55:
            p.add_page(); p.set_y(topbar(comp_name or "") + 8)
        y = p.get_y()
        p.set_fill_color(*ACC_SOFT); p.set_draw_color(*ACC); p.set_line_width(0.25)
        p.rect(M, y, 9, 9, "DF", round_corners=True, corner_radius=2.2)
        p.set_xy(M, y + 2.2); p.set_font("Helvetica", "B", 8); p.set_text_color(*ACC)
        p.cell(9, 4.6, num, align="C")
        p.set_xy(M + 12, y + (0.4 if sub else 2)); p.set_font("Helvetica", "B", 12); p.set_text_color(*TEXT)
        p.cell(CW - 12, 5.5, _ps(title))
        if sub:
            p.set_xy(M + 12, y + 5.4); p.set_font("Helvetica", "", 7.8); p.set_text_color(*MUTED)
            p.cell(CW - 12, 4, _ps(sub))
        p.set_y(y + 13)

    def card(x, y, w, h, fill=SURF, border=LINE, r=3):
        p.set_fill_color(*fill); p.set_draw_color(*border); p.set_line_width(0.2)
        p.rect(x, y, w, h, "DF", round_corners=True, corner_radius=r)

    has_cur   = current_total > 0
    saving_mo = current_total - total_mo
    term_lbl  = LEASE_TERM_LABELS.get(lease_term, "") if is_spread else "Upfront hardware"

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1 — the headline and the full comparison
    # ════════════════════════════════════════════════════════════════════════
    p.add_page()
    y = topbar(date.today().strftime("%d %B %Y")) + 9
    eyebrow(f"Prepared for {comp_name or 'your business'}"
            + (f"  \u00b7  by {_prepared_by()}" if _prepared_by() else ""), y)
    p.set_xy(M, y + 6.5); p.set_font("Helvetica", "B", 24); p.set_text_color(*TEXT)
    _t1 = _ps("Contract information " if cis else f"Your {_CO} "); p.cell(p.get_string_width(_t1), 11, _t1)
    p.set_text_color(*ACC); p.cell(0, 11, "sheet" if cis else "proposal", new_x="LMARGIN", new_y="NEXT")
    p.set_font("Helvetica", "", 10); p.set_text_color(*MUTED)
    p.cell(0, 6, _ps("A summary of your contract costs and term, for you to review and sign before the full paperwork." if cis
                     else "What you pay today, side by side with what you'll pay with us." if has_cur
                     else "Everything included in your new system, in one monthly figure."),
           new_x="LMARGIN", new_y="NEXT")

    # Hero: the one number that matters
    hy, hh = p.get_y() + 7, 48
    card(M, hy, CW, hh, fill=SURF2, r=4)
    hero_col = GOOD if has_cur else ACC
    p.set_fill_color(*hero_col); p.rect(M + 5, hy, CW - 10, 0.9, "F")
    if has_cur and saving_mo >= 0:
        lbl, big, sub = "Annual saving", gbp(saving_mo * 12), f"{gbp(saving_mo)} less every month"
    elif has_cur:
        lbl, big, sub = "Daily investment", gbp(abs(saving_mo) / 30.44), "per day, for everything included"
    else:
        lbl, big, sub = "Total monthly", gbp(total_mo), "+ VAT, all services and hardware"
    lx = M + 9
    p.set_xy(lx, hy + 9); p.set_font("Helvetica", "B", 8); p.set_text_color(*hero_col)
    p.set_char_spacing(1.1); p.cell(95, 4, lbl.upper()); p.set_char_spacing(0)
    p.set_xy(lx, hy + 15); p.set_font("Helvetica", "B", 32); p.set_text_color(*hero_col)
    p.cell(100, 15, _ps(big))
    p.set_xy(lx, hy + 33); p.set_font("Helvetica", "", 9); p.set_text_color(*MUTED)
    p.cell(100, 5, _ps(sub))
    rx = M + CW * 0.58; rw = PW - M - 9 - rx
    p.set_draw_color(*LINE); p.line(rx - 6, hy + 9, rx - 6, hy + hh - 9)
    # The agreement term lives on page 2 ("Agreement at a glance"), so page 1 keeps just the money
    stats = ([("Today", f"{gbp(current_total)}/mo")] if has_cur else []) + [
        (f"With {_CO}", f"{gbp(total_mo)}/mo")]
    sy = hy + (hh - len(stats) * 10.5) / 2 + 1.5   # vertically centred in the card
    for i, (k, v) in enumerate(stats):
        p.set_xy(rx, sy); p.set_font("Helvetica", "", 8.5); p.set_text_color(*MUTED)
        p.cell(rw * 0.45, 6, _ps(k))
        p.set_font("Helvetica", "B", 10.5); p.set_text_color(*TEXT)
        p.cell(rw * 0.55, 6, _ps(v), align="R")
        if i < len(stats) - 1:
            p.set_draw_color(*LINE); p.line(rx, sy + 8.8, rx + rw, sy + 8.8)
        sy += 10.5

    # 01 Cost comparison
    p.set_y(hy + hh + 10)
    rows = build_comparison_rows()
    if has_cur:
        section("01", "Cost comparison", "Monthly costs by category, excluding VAT")
        W = [CW - 108, 36, 36, 36]
        ty = p.get_y()
        p.set_fill_color(*SURF3)
        p.rect(M, ty, CW, 8.5, "F", round_corners=True, corner_radius=2.5)
        p.set_xy(M, ty); p.set_font("Helvetica", "B", 7); p.set_text_color(*MUTED); p.set_char_spacing(0.8)
        for w, h, al in zip(W, ("CATEGORY", "CURRENT", _CO.upper(), "DIFFERENCE"), "LRRR"):
            p.cell(w, 8.5, _ps(("   " if al == "L" else "") + h + ("   " if al == "R" else "")), align=al)
        p.set_char_spacing(0); p.ln(8.5)
        for label, cur, new in rows:
            d = cur - new
            if abs(d) < 0.005:
                dtxt, dcol = gbp(0), MUTED
            else:
                dtxt, dcol = (f"-{gbp(d)}" if d > 0 else f"+{gbp(abs(d))}"), GOOD
            yy = p.get_y()
            p.set_font("Helvetica", "", 9); p.set_text_color(*TEXT); p.cell(W[0], 7.6, _ps("   " + label))
            p.set_text_color(*MUTED); p.cell(W[1], 7.6, _ps(gbp(cur) + "   "), align="R")
            p.set_font("Helvetica", "B", 9); p.set_text_color(*TEXT); p.cell(W[2], 7.6, _ps(gbp(new) + "   "), align="R")
            p.set_text_color(*dcol); p.cell(W[3], 7.6, _ps(dtxt + "   "), align="R")
            p.ln(7.6)
            p.set_draw_color(*LINE); p.line(M, yy + 7.6, PW - M, yy + 7.6)
        ty = p.get_y() + 1.5
        p.set_fill_color(*SURF2); p.rect(M, ty, CW, 9.5, "F", round_corners=True, corner_radius=2.5)
        p.set_fill_color(*ACC); p.rect(M, ty, 1.2, 9.5, "F")
        p.set_xy(M, ty); p.set_font("Helvetica", "B", 9.5); p.set_text_color(*TEXT)
        p.cell(W[0], 9.5, "   Total monthly (excl. VAT)")
        p.set_text_color(*MUTED); p.cell(W[1], 9.5, _ps(gbp(current_total) + "   "), align="R")
        p.set_text_color(*TEXT); p.cell(W[2], 9.5, _ps(gbp(total_mo) + "   "), align="R")
        p.set_text_color(*GOOD)
        p.cell(W[3], 9.5, _ps((f"-{gbp(saving_mo)}" if saving_mo >= 0 else f"+{gbp(abs(saving_mo))}") + "   "), align="R")
        p.set_y(ty + 13)
        p.set_font("Helvetica", "", 7); p.set_text_color(*FAINT)
        p.multi_cell(CW, 3.6, _ps("Current costs are as provided by you. Calls are included in your user licences. "
                                  "All figures exclude VAT."))
    else:
        section("01", "Your monthly investment", "Excluding VAT")
        for label, _cur, new in rows:
            yy = p.get_y()
            p.set_font("Helvetica", "", 9); p.set_text_color(*TEXT); p.cell(CW - 50, 7.6, _ps("   " + label))
            p.set_font("Helvetica", "B", 9); p.cell(50, 7.6, _ps(gbp(new) + "/mo   "), align="R")
            p.ln(7.6); p.set_draw_color(*LINE); p.line(M, yy + 7.6, PW - M, yy + 7.6)

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2 — what's included
    # ════════════════════════════════════════════════════════════════════════
    p.add_page()
    p.set_y(topbar(comp_name or "") + 9)

    _phones = [(n, q) for n, q in list(desktop_quantities.items()) + list(cordless_quantities.items()) if q > 0]
    _n_handsets = sum(q for _, q in _phones)
    # air-conditioning systems and extras chosen in the Air Conditioning dropdown (pictures included)
    _ac_cards = [(it["name"], q) for it, q in AC["listed"] if it.get("group") in AC_SYSTEM_GROUPS or it.get("group") == "Extras"]
    _ac_cards.sort(key=lambda t: 0 if any(g in next((i for i in AC_CAT if i["name"] == t[0]), {}).get("group", "") for g in AC_SYSTEM_GROUPS) else 1)
    _n_ac = sum(q for it, q in AC["listed"] if it.get("group") in AC_SYSTEM_GROUPS)
    _show_ac = _ac_cards[:3]
    _phones_all = _phones
    _phones = _show_ac + _phones_all[:max(0, 5 - len(_show_ac))]
    _extra_cards = len(_ac_cards) - len(_show_ac) + max(0, len(_phones_all) - max(0, 5 - len(_show_ac)))
    section("02", "Your new system",
            (f"{_n_handsets} handset{'s' if _n_handsets != 1 else ''}  \u00b7  " if _n_handsets else "")
            + (f"{_n_ac} air conditioning unit{'s' if _n_ac != 1 else ''}  \u00b7  " if _n_ac else "")
            + (f"{'system rental' if is_inhouse else 'hardware lease'} {gbp(hw_monthly_spread)}/mo over {term_lbl}" if is_spread
               else f"hardware {gbp(upfront)} one-off"))
    def _cards(_phones, _extra_cards):
      if _phones:
          n = min(len(_phones), 5); gap = 4
          cw_ = (CW - gap * 4) / 5; ch_ = 38; cy_ = p.get_y()
          for i, (name, qty) in enumerate(_phones[:5]):
              cx_ = M + i * (cw_ + gap)
              card(cx_, cy_, cw_, ch_, r=3)
              p.set_fill_color(*STAGE); p.rect(cx_ + 2, cy_ + 2, cw_ - 4, 23, "F", round_corners=True, corner_radius=2)
              b64, ext = get_product_image_b64(name)
              _drawn = False
              if b64:
                  try:
                      p.image(io.BytesIO(base64.b64decode(b64)), x=cx_ + 4, y=cy_ + 3.5, w=cw_ - 8, h=20,
                              keep_aspect_ratio=True)
                      _drawn = True
                  except Exception:
                      pass
              if not _drawn:   # simple desk-phone drawing on the stage
                  bx, by = cx_ + cw_ / 2 - 9, cy_ + 7
                  p.set_fill_color(58, 66, 84)
                  p.rect(bx, by + 4, 18, 11, "F", round_corners=True, corner_radius=1.5)       # body
                  p.rect(bx - 1.5, by + 1, 4.5, 14, "F", round_corners=True, corner_radius=1.5)  # handset
                  p.set_fill_color(*ACC); p.rect(bx + 5, by + 5.5, 11, 4, "F", round_corners=True, corner_radius=0.8)  # screen
                  p.set_fill_color(150, 160, 178)
                  for kr in range(2):
                      for kc in range(4):
                          p.rect(bx + 5.2 + kc * 2.8, by + 10.8 + kr * 2, 1.6, 1.1, "F")
              p.set_xy(cx_ + 1, cy_ + 26.5); p.set_font("Helvetica", "B", 6.4); p.set_text_color(*TEXT)
              p.cell(cw_ - 2, 3.5, _ps(name.split("(")[0].replace("Wall Mounted", "Wall").replace("Ceiling Cassette", "Cassette").replace("Air conditioning installation", "Installation").strip()[:22]), align="C")
              chip_w = 9; p.set_fill_color(*ACC_SOFT)
              p.rect(cx_ + (cw_ - chip_w) / 2, cy_ + 31.2, chip_w, 4.4, "F", round_corners=True, corner_radius=2.2)
              p.set_xy(cx_ + (cw_ - chip_w) / 2, cy_ + 31.4); p.set_font("Helvetica", "B", 6.5); p.set_text_color(*ACC2)
              p.cell(chip_w, 4, f"x{qty}", align="C")
          p.set_y(cy_ + ch_ + 3)
          if _extra_cards > 0:
              p.set_font("Helvetica", "", 7.5); p.set_text_color(*MUTED)
              p.cell(0, 4, _ps(f"+ {_extra_cards} more item(s) on your order form"),
                     new_x="LMARGIN", new_y="NEXT")
          p.ln(5)
    _cards(_phones, _extra_cards)

    # 03 Monthly services
    svc_rows = []
    if svc["bb_sell"] > 0:
        if bb_free_year and _bb_yr1_saving > 0:
            svc_rows.append((f"Broadband - {bb_provider} {bb_package} (FREE year 1)",
                             f"{gbp(0)} then {gbp(_bb_full_sell)}/mo", True))
        else:
            svc_rows.append((f"Broadband - {bb_provider} {bb_package}"
                             + (f" + {extra_bb_count} additional line(s)" if extra_bb_count else ""),
                             f"{gbp(svc['bb_sell'])}/mo", False))
    if svc["lic_monthly"] > 0:
        svc_rows.append((f"User licences ({total_voice_channels} users, calls included)",
                         f"{gbp(svc['lic_monthly'])}/mo", False))
    if sw_sell_total + svc.get("wallboard_mo", 0.0) > 0:
        svc_rows.append(("Software & add-ons", f"{gbp(sw_sell_total + svc.get('wallboard_mo', 0.0))}/mo", False))
    for _r in cs_svc_rows:
        if _r.get("qty", 0) > 0:
            svc_rows.append((_r["name"], f"{gbp(_r['sell'] * _r['qty'])}/mo", False))
    for _r in sec_rows:
        if _r.get("qty", 0) > 0:
            svc_rows.append((f"{_r['name']} x{_r['qty']}", f"{gbp(_r['sell'] * _r['qty'])}/mo", False))
    for _r in it_rows:
        if _r.get("qty", 0) > 0:
            svc_rows.append((f"{_r['service']} x{_r['qty']}", f"{gbp(_r['sell'] * _r['qty'])}/mo", False))
    for _r in mobile_rows:
        if _r.get("qty", 0) > 0:
            svc_rows.append((f"Mobile - {mobile_label(_r)} x{_r['qty']}",
                             f"{gbp(_r['sell'] * _r['qty'])}/mo", False))
    for _d_, _a_ in XM_ROWS:
        svc_rows.append((_d_, f"{gbp(_a_)}/mo", False))
    if printer_rows:
        svc_rows.append((f"Printer lease - {printer_count} printer(s), {printer_term} months", f"{gbp(printer_monthly)}/mo", False))
        svc_rows.append((f"Printing (est. {sum(_r['volume'] for _r in printer_rows):,} prints/month)",
                         f"{gbp(printer_print_est_mo)}/mo", False))
    if svc_rows:
        section("03", "Monthly services included", "Excluding VAT")
        for label, val, promo in svc_rows:
            yy = p.get_y()
            p.set_font("Helvetica", "", 8.8); p.set_text_color(*TEXT); p.cell(CW - 55, 7, _ps("   " + label))
            p.set_font("Helvetica", "B", 8.8); p.set_text_color(*(GOOD if promo else TEXT))
            p.cell(55, 7, _ps(val + "   "), align="R")
            p.ln(7); p.set_draw_color(*LINE); p.line(M, yy + 7, PW - M, yy + 7)
        ty = p.get_y() + 1.5
        p.set_fill_color(*SURF2); p.rect(M, ty, CW, 9, "F", round_corners=True, corner_radius=2.5)
        p.set_fill_color(*ACC); p.rect(M, ty, 1.2, 9, "F")
        p.set_xy(M, ty); p.set_font("Helvetica", "B", 9.2); p.set_text_color(*TEXT)
        p.cell(CW - 55, 9, "   Total monthly services")
        p.cell(55, 9, _ps(f"{gbp(svc['total_sell'])}/mo   "), align="R")
        p.set_y(ty + 15)

    _sn = [3]
    def _nx():
        _sn[0] += 1
        return f"{_sn[0]:02d}"

    def _room(h):
        if p.get_y() + h > PH - 20:
            p.add_page(); p.set_y(topbar(comp_name or "") + 9)

    def _rowblock(rows, total_label=None, total_val=None):
        _room(7 * len(rows) + (12 if total_label else 0))
        for label, val, promo in rows:
            yy = p.get_y()
            p.set_font("Helvetica", "", 8.8); p.set_text_color(*TEXT); p.cell(CW - 70, 7, _ps("   " + label))
            p.set_font("Helvetica", "B", 8.8); p.set_text_color(*(GOOD if promo else TEXT))
            p.cell(70, 7, _ps(val + "   "), align="R")
            p.ln(7); p.set_draw_color(*LINE); p.line(M, yy + 7, PW - M, yy + 7)
        if total_label:
            ty = p.get_y() + 1.5
            p.set_fill_color(*SURF2); p.rect(M, ty, CW, 9, "F", round_corners=True, corner_radius=2.5)
            p.set_fill_color(*ACC); p.rect(M, ty, 1.2, 9, "F")
            p.set_xy(M, ty); p.set_font("Helvetica", "B", 9.2); p.set_text_color(*TEXT)
            p.cell(CW - 70, 9, _ps("   " + total_label))
            p.cell(70, 9, _ps(total_val + "   "), align="R")
            p.set_y(ty + 15)

    # Call Scope (its own agreement and company)
    if cs_active and not cs_crm_missing:
        _cb = cs_brand(); _q = cs_quote
        section(_nx(), f"Your {_cb['trading']} services", f"Provided by {_cb['legal']} under its own agreement  \u00b7  {_q['term']} months  \u00b7  excluding VAT")
        _crow = []
        for _l in _q["lines"]:
            _crow.append((_l["name"] + (f" x{_l['qty']}" if _l["qty"] > 1 else ""), f"{gbp(_l['total'])}/mo", False))
        if _q["discount"] > 0:
            _crow.append((f"Includes {_q['discount']:g}% discount on the standard price", "", True))
        for _s in _q["setup"]:
            _crow.append((f"{_s['name']}" + (f" x{_s['qty']}" if _s["qty"] > 1 else "") + " (one-off)",
                          "Waived" if _q["setup_mode"] == "waived" else gbp(_s["total"]), _q["setup_mode"] == "waived"))
        _rowblock(_crow, f"Total monthly {_cb['trading']}" + (" (year 1)" if _q["discount"] > 0 and _q["style"] == "stepped" and _q["years"] > 1 else ""),
                  f"{gbp(_q['monthly_total'])}/mo")

    # SteadyTemp air conditioning (its own agreement and company)
    if ac_active:
        _co = st_company(); _q = ac_quote
        section(_nx(), f"Your {_co['trading']}", f"Provided by {_co['legal']} under its own agreement  \u00b7  "
                + ("one-off purchase" if _q["is_cash"] else f"{_q['term']} months") + "  \u00b7  excluding VAT")
        _acc = [(it["name"], q) for it, q in AC_ORDER["listed"] if it.get("group") in AC_SYSTEM_GROUPS or it.get("group") == "Extras"]
        _acc.sort(key=lambda t_: 0 if any(g in next((i for i in AC_CAT if i["name"] == t_[0]), {}).get("group", "") for g in AC_SYSTEM_GROUPS) else 1)
        _cards(_acc[:5], max(0, len(_acc) - 5))
        _arow = []
        if _q["is_cash"]:
            _arow.append(("Air conditioning - supplied and installed", gbp(_q["cash_price"]), False))
        else:
            _arow.append((f"Air conditioning rental ({_q['term']} months)", f"{gbp(_q['rental'])}/mo", False))
        _arow.append(("On-site support after year 1", f"{gbp(_q['support'])}/yr", False))
        _cur_ac = sum(float(st.session_state.get(k, 0) or 0) for k in ("ac_cur_running", "ac_cur_service", "ac_cur_leasing", "ac_cur_heating", "ac_cur_other"))
        if _cur_ac > 0 and not _q["is_cash"]:
            _dd = _cur_ac - _q["rental"]
            _arow.append(("Your current heating / cooling costs", f"{gbp(_cur_ac)}/mo", False))
            _arow.append(("Annual saving" if _dd >= 0 else "Cost per day", gbp(_dd * 12) if _dd >= 0 else gbp(abs(_dd) / 30.44), True))
        _rowblock(_arow, "Air conditioning one-off price" if _q["is_cash"] else "Total monthly air conditioning",
                  gbp(_q["cash_price"]) if _q["is_cash"] else f"{gbp(_q['rental'])}/mo")

    # Everything together
    _all_rows = []
    if _tele_any:
        _all_rows.append((f"{_CO} - telephony and services", f"{gbp(total_mo)}/mo", False))
    if cs_active and not cs_crm_missing:
        _all_rows.append((f"{cs_brand()['trading']}", f"{gbp(cs_quote['monthly_total'])}/mo", False))
    if ac_active:
        _all_rows.append((st_company()["trading"] + (" (one-off)" if ac_quote["is_cash"] else ""),
                          gbp(ac_quote["cash_price"]) if ac_quote["is_cash"] else f"{gbp(ac_quote['rental'])}/mo", False))
    if len(_all_rows) > 1:
        _mo_all = (total_mo if _tele_any else 0.0) + (cs_quote["monthly_total"] if (cs_active and not cs_crm_missing) else 0.0) \
                  + (ac_quote["rental"] if (ac_active and not ac_quote["is_cash"]) else 0.0)
        section(_nx(), "Everything together", "Each under its own agreement  \u00b7  excluding VAT")
        _rowblock(_all_rows, "Total monthly (excl. VAT)", f"{gbp(_mo_all)}/mo")

    # 04 Agreement at a glance
    section(_nx(), "Agreement at a glance")
    tiles = [("Agreement", term_lbl), ("Installation", install_type)] + (
        [("Maintenance", "Not included"), ("Hardware", "Manufacturer warranty")] if _maint_optout()
        else [("On-site warranty", "12 months inclusive"), ("Support", "Remote diagnostics")])
    tw_ = (CW - 3 * 4) / 4; ty_ = p.get_y()
    for i, (k, v) in enumerate(tiles):
        tx_ = M + i * (tw_ + 4)
        card(tx_, ty_, tw_, 15, r=2.5)
        p.set_xy(tx_ + 3.5, ty_ + 3); p.set_font("Helvetica", "B", 6.3); p.set_text_color(*MUTED)
        p.set_char_spacing(0.7); p.cell(tw_ - 6, 3.5, _ps(k.upper())); p.set_char_spacing(0)
        p.set_xy(tx_ + 3.5, ty_ + 8); p.set_font("Helvetica", "B", 8.3); p.set_text_color(*TEXT)
        p.cell(tw_ - 6, 4, _ps(v))
    p.set_y(ty_ + 21)

    # 05 Why us
    section(_nx(), f"Why businesses choose {_CO}")
    vals = [("One bill", "Hardware, licences, broadband and support in one monthly payment."),
            ("Fully managed", "We handle installation and programming." if _maint_optout() else "We handle installation, programming, warranty and helpdesk."),
            ("Local engineers", "On-site support from engineers who know your area.")]
    vw = (CW - 2 * 4) / 3; vy = p.get_y()
    for i, (t, d) in enumerate(vals):
        vx = M + i * (vw + 4)
        card(vx, vy, vw, 21, r=2.5)
        p.set_fill_color(*ACC); p.rect(vx, vy + 3, 1.2, 15, "F")
        p.set_xy(vx + 5, vy + 3.5); p.set_font("Helvetica", "B", 8.5); p.set_text_color(*ACC2)
        p.cell(vw - 8, 4.5, _ps(t))
        p.set_xy(vx + 5, vy + 9); p.set_font("Helvetica", "", 7.2); p.set_text_color(*MUTED)
        p.multi_cell(vw - 8, 3.6, _ps(d), align="L")
    p.set_y(vy + 27)

    # Agreement to proceed: replaces the call to action with a sign-off block
    def _covers():
        c = []
        if _tele_any:
            c.append(f"Telephony and services - {_CO_LEGAL}: {gbp(total_mo)}/mo" + (f" over {term_lbl}" if is_spread else "") + " (excl. VAT)")
        if cs_active and not cs_crm_missing:
            c.append(f"{cs_brand()['trading']} - {cs_brand()['legal']}: {gbp(cs_quote['monthly_total'])}/mo over {cs_quote['term']} months (excl. VAT)")
        if ac_active:
            _co_ = st_company()
            c.append(f"Air conditioning - {_co_['legal']}: " + (f"{gbp(ac_quote['cash_price'])} one-off (excl. VAT)" if ac_quote["is_cash"]
                     else f"{gbp(ac_quote['rental'])}/mo over {ac_quote['term']} months (excl. VAT)"))
        return c

    def _agree_box(sign, intro, covers=None, title="Agreement to proceed", tag="STEP 2 OF 2  -  FULL PAPERWORK PACK", sig_label="Customer signature - agreeing to proceed"):
        covers = covers or []
        ay_ = p.get_y()
        ah_ = 44 if not covers else 50 + 4.6 * len(covers)
        if ay_ + ah_ > PH - 18 + (0 if not covers else -1000):   # keep it on the page by tightening up if needed
            if covers or ay_ + ah_ > PH - 18 + 8:
                p.add_page(); p.set_y(topbar(comp_name or "") + 9); ay_ = p.get_y()
            else:
                ay_ = PH - 18 - ah_
        card(M, ay_, CW, ah_, fill=SURF2, border=ACC, r=4)
        p.set_xy(M + 8, ay_ + 4); p.set_font("Helvetica", "B", 12); p.set_text_color(*TEXT)
        p.cell(CW - 16, 6, _ps(title))
        if tag:
            p.set_xy(M + 8, ay_ + 5.2); p.set_font("Helvetica", "B", 6.4); p.set_text_color(*ACC2)
            p.set_char_spacing(0.8); p.cell(CW - 16, 4, _ps(tag), align="R"); p.set_char_spacing(0)
        p.set_xy(M + 8, ay_ + 10.5); p.set_font("Helvetica", "", 7.8); p.set_text_color(*MUTED)
        p.multi_cell(CW - 16, 3.8, _ps(intro), align="L")
        by_ = ay_ + 22
        if covers:
            _iy = p.get_y() + 0.8
            p.set_font("Helvetica", "B", 7.8); p.set_text_color(*TEXT)
            for _c in covers:
                p.set_xy(M + 10, _iy); p.cell(CW - 20, 4.4, _ps("-  " + _c)); _iy += 4.6
            by_ = _iy + 2
        p.set_fill_color(255, 255, 255); p.rect(M + 8, by_, 78, 17, "F")   # white panel for the signature
        _sb = sign.get("sig_bytes")
        if _sb and len(_sb) > 100:
            try:
                import tempfile, os as _o
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _tf:
                    _tf.write(_sb); _tp = _tf.name
                try:
                    p.image(_tp, x=M + 10, y=by_ + 1, w=40, h=15)
                finally:
                    _o.unlink(_tp)
            except Exception:
                pass
        else:
            p.set_draw_color(120, 128, 150); p.set_line_width(0.3)
            p.line(M + 12, by_ + 13, M + 82, by_ + 13)
        p.set_font("Helvetica", "", 7); p.set_text_color(*MUTED)
        p.set_xy(M + 8, by_ + 17.5); p.cell(CW - 16, 4, _ps(sig_label))
        p.set_font("Helvetica", "B", 8.5); p.set_text_color(*TEXT)
        p.set_xy(M + 92, by_ + 1.5); p.cell(CW - 100, 5, _ps(f"Name: {sign.get('name') or ''}"))
        p.set_xy(M + 92, by_ + 7.5); p.cell(CW - 100, 5, _ps(f"Company: {sign.get('company') or comp_name or ''}"))
        p.set_xy(M + 92, by_ + 13.5); p.cell(CW - 100, 5, _ps(f"Date: {str(sign.get('timestamp') or '')[:10]}"))

    _intro_pack = (f"I confirm that I would like {_CO} to proceed with the services and equipment in this proposal, "
                   "subject to the Order Form, Network Services & Broadband Agreement and Terms & Conditions in this pack.")

    # ════════════════════════════════════════════════════════════════════════
    # CONTRACT INFORMATION SHEET (step 1 of signing): page 3 = term + costings, then the sign-off
    # ════════════════════════════════════════════════════════════════════════
    if cis:
        p.add_page(); p.set_y(topbar(comp_name or "") + 9)
        _months = int(lease_term)
        _term_txt = LEASE_TERM_LABELS.get(lease_term, f"{_months} months")
        section("06", "Your contract term", "The main points, in one place")
        _tiles = [("Agreement term", _term_txt), ("Billing", "Monthly in advance"),
                  ("Invoices due", "Within 14 days"), ("After the term", "Renews 12 months*")]
        tw_ = (CW - 3 * 4) / 4; ty_ = p.get_y()
        for i, (k, v) in enumerate(_tiles):
            tx_ = M + i * (tw_ + 4)
            card(tx_, ty_, tw_, 15, r=2.5)
            p.set_xy(tx_ + 3.5, ty_ + 3); p.set_font("Helvetica", "B", 6.3); p.set_text_color(*MUTED)
            p.set_char_spacing(0.7); p.cell(tw_ - 6, 3.5, _ps(k.upper())); p.set_char_spacing(0)
            p.set_xy(tx_ + 3.5, ty_ + 8); p.set_font("Helvetica", "B", 8.3); p.set_text_color(*TEXT)
            p.cell(tw_ - 6, 4, _ps(v))
        p.set_y(ty_ + 18)
        p.set_font("Helvetica", "", 7); p.set_text_color(*FAINT)
        p.multi_cell(CW, 3.6, _ps("* Unless 90 days' written notice is given before the end of the term. Cancelling during the term "
                                  "incurs a cancellation charge - see the Terms & Conditions in your full paperwork."))
        p.set_y(p.get_y() + 5)

        section("07", "Your contract costings", "Excluding VAT unless stated")
        _prn = round(float(printer_monthly or 0) + float(printer_print_est_mo or 0), 2)
        _hw = round(float(hw_monthly_spread or 0), 2) if is_spread else 0.0
        _svc = round(float(total_mo) - _hw - _prn, 2)
        _lines = []
        if _hw > 0: _lines.append((f"{'System rental' if is_inhouse else 'Hardware rental'} over {_term_txt}", _hw))
        _lines.append(("Monthly services (user licences, broadband and add-ons)", _svc))
        if _prn > 0: _lines.append(("Printer rental and estimated print charges", _prn))
        for label, amt in _lines:
            yy = p.get_y()
            p.set_font("Helvetica", "", 9); p.set_text_color(*TEXT); p.cell(CW - 50, 7.6, _ps("   " + label))
            p.set_font("Helvetica", "B", 9); p.cell(50, 7.6, _ps(gbp(amt) + "/mo   "), align="R")
            p.ln(7.6); p.set_draw_color(*LINE); p.line(M, yy + 7.6, PW - M, yy + 7.6)
        ty = p.get_y() + 1.5
        p.set_fill_color(*SURF2); p.rect(M, ty, CW, 9.5, "F", round_corners=True, corner_radius=2.5)
        p.set_fill_color(*ACC); p.rect(M, ty, 1.2, 9.5, "F")
        p.set_xy(M, ty); p.set_font("Helvetica", "B", 9.5); p.set_text_color(*TEXT)
        p.cell(CW - 50, 9.5, "   Total monthly (excl. VAT)")
        p.cell(50, 9.5, _ps(gbp(total_mo) + "/mo   "), align="R")
        p.set_y(ty + 12)
        _vat = round(total_mo * 0.2, 2)
        p.set_font("Helvetica", "", 8.5); p.set_text_color(*MUTED)
        p.cell(CW - 50, 6, _ps(f"   VAT at 20%: {gbp(_vat)}      Total monthly including VAT:"), align="L")
        p.set_font("Helvetica", "B", 8.5); p.set_text_color(*TEXT)
        p.cell(50, 6, _ps(gbp(total_mo + _vat) + "/mo   "), align="R"); p.ln(7)
        if (not is_spread) and upfront and upfront > 0:
            p.set_font("Helvetica", "", 9); p.set_text_color(*TEXT)
            p.cell(CW - 50, 7, _ps("   Hardware - one-off payment (excl. VAT)"))
            p.set_font("Helvetica", "B", 9); p.cell(50, 7, _ps(gbp(upfront) + "   "), align="R"); p.ln(8)
        _tot_term = round(total_mo * _months + (upfront if (not is_spread and upfront) else 0.0), 2)
        p.set_font("Helvetica", "", 8.5); p.set_text_color(*MUTED)
        p.cell(CW - 50, 6, _ps(f"   Total payable over the {_term_txt} term (excl. VAT, before any price increase)"))
        p.set_font("Helvetica", "B", 8.5); p.set_text_color(*TEXT)
        p.cell(50, 6, _ps(gbp(_tot_term) + "   "), align="R"); p.ln(9)

        _pb, _pi, _pn, _pp, _py = price_rise_figures()
        if _pp > 0 and _pb > 0:
            section("08", "Annual price review", "Fixed amount, shown in pounds and pence")
            card(M, p.get_y(), CW, 19, r=2.5); _cy = p.get_y()
            p.set_fill_color(*ACC); p.rect(M, _cy + 3, 1.2, 13, "F")
            p.set_xy(M + 6, _cy + 3.2); p.set_font("Helvetica", "B", 8.8); p.set_text_color(*TEXT)
            p.cell(CW - 12, 4.5, _ps(f"Monthly services increase by {gbp(_pi)} per month ({_pp:g}%) on your first anniversary, then by {_pp:g}% each year."))
            p.set_xy(M + 6, _cy + 9); p.set_font("Helvetica", "", 7.6); p.set_text_color(*MUTED)
            p.multi_cell(CW - 12, 3.7, _ps(f"That takes your monthly services from {gbp(_pb)} to {gbp(_pn)} (excl. VAT), an extra {gbp(_py)} over a year. "
                                           + (("System rental does not change. " if is_inhouse else "Hardware rental under your lease does not change. ") if is_spread else "")
                                           + "The full year-by-year schedule is on the Annual Price Review page of your paperwork."), align="L")
            p.set_y(_cy + 23)
        _agree_box(sign or {}, "I confirm that I have read and understood the contract term and costings above, and I accept them. "
                               "This is not the final agreement: the full paperwork (Order Form, Network Services & Broadband Agreement and Terms & Conditions) "
                               "follows, with its own Agreement to proceed.",
                   title="Acceptance of contract terms", tag="STEP 1 OF 2  -  CONTRACT INFORMATION SHEET",
                   sig_label="Customer signature - accepting the term and costings")
        return bytes(p.output())

    if sign is not None:
        _cv = _covers()
        _agree_box(sign, (_intro_pack if len(_cv) <= 1 else
                          f"I confirm that I would like to proceed with the services and equipment listed below. Each is provided under its own agreement, "
                          "subject to its Order Form and Terms & Conditions in the pack."), _cv if len(_cv) > 1 else None)
        return bytes(p.output())

    # Call to action
    if p.get_y() > PH - 45:
        p.add_page(); p.set_y(topbar(comp_name or "") + 9)
    cy_ = p.get_y()
    card(M, cy_, CW, 24, fill=SURF2, border=ACC, r=4)
    p.set_xy(M + 8, cy_ + 5); p.set_font("Helvetica", "B", 12.5); p.set_text_color(*TEXT)
    p.cell(CW - 16, 6, "Ready to proceed?")
    p.set_xy(M + 8, cy_ + 11.5); p.set_font("Helvetica", "", 8.5); p.set_text_color(*MUTED)
    p.cell(CW - 16, 4.5, _ps("Reply to this proposal or give us a call, and we'll take care of the rest."))
    p.set_xy(M + 8, cy_ + 16.8); p.set_font("Helvetica", "B", 8.5); p.set_text_color(*ACC2)
    p.cell(CW - 16, 4.5, _ps(f"{_CO_EMAIL}   \u00b7   {_CO_PHONE}   \u00b7   {_CO_WEB}"))

    return bytes(p.output())


def _build_pdf_core(sig_bytes=None, sig_name='', sig_company='', sig_timestamp='', sig_ip='',
              curr_total=0.0, curr_bb=0.0, curr_system=0.0, curr_calls=0.0,
              curr_mobile=0.0, curr_support=0.0, curr_other=0.0):
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)

    # Sanitise all user inputs going into PDF
    _comp     = s(comp_name)
    _reg      = s(comp_reg)
    _btype    = s(biz_type)
    _contact  = s(contact_name)
    _signer   = s(sig_name) if (sig_name and str(sig_name).strip()) else _contact   # when signed, show who actually signed
    _phone    = s(company_phone)
    _demail   = s(director_email)
    _bemail   = s(billing_email)
    _addr     = s(install_address)
    _bank     = s(bank_name)
    _holder   = s(acc_holder)
    _accno    = s(acc_no)
    _sort     = s(sort_code)

    # -- PAGE 1: PROPOSAL --
    # Embed logo for PDF (conditional on brand having a logo)
    _logo_bytes = base64.b64decode(SYCOMMS_LOGO_B64) if _BRAND["logo_key"] else None
    _logo_buf   = io.BytesIO(_logo_bytes) if _logo_bytes else None

    def _add_header(pdf_obj, subtitle="Customer Proposal & Order Documentation"):
        # Deep purple background
        pdf_obj.set_fill_color(8, 31, 58)
        pdf_obj.rect(0, 0, 210, 42, 'F')
        if _logo_buf:
            pdf_obj.image(_logo_buf, x=10, y=9, w=70)
            _logo_buf.seek(0)
        else:
            pdf_obj.set_font("Helvetica", "B", 20)
            pdf_obj.set_text_color(255, 255, 255)
            pdf_obj.set_y(7); pdf_obj.set_x(48)
            pdf_obj.cell(120, 10, s(_CO.upper()), ln=False, align="L")
        pdf_obj.set_text_color(255, 255, 255)
        pdf_obj.set_font("Helvetica", "", 9)
        pdf_obj.set_y(24)
        pdf_obj.set_x(10)
        pdf_obj.cell(120, 6, s(subtitle), ln=False, align="L")
        _rep_hdr = s(_prepared_by())
        if _rep_hdr:
            pdf_obj.set_font("Helvetica", "I", 8)
            pdf_obj.set_text_color(200, 205, 225)
            pdf_obj.set_y(31); pdf_obj.set_x(10)
            pdf_obj.cell(120, 5, f"Prepared by: {_rep_hdr}", ln=False, align="L")
        # Teal accent bar
        pdf_obj.set_fill_color(27, 120, 214)
        pdf_obj.rect(0, 42, 210, 2, 'F')
        pdf_obj.set_text_color(0, 0, 0)
        pdf_obj.set_y(48)

    # ── PAGE 1: SY COMMS COMPANY INTRODUCTION ───────────────────────────────
    pdf.set_auto_page_break(False)   # disable so cover page content doesn't spill
    pdf.add_page()

    # Full-page gradient cover
    pdf.set_fill_color(8, 31, 58)
    pdf.rect(0, 0, 210, 297, 'F')

    # Teal accent stripe at top
    pdf.set_fill_color(27, 120, 214)
    pdf.rect(0, 0, 210, 5, 'F')

    # Logo centred - large (only shown for brands that have a logo)
    if _logo_buf:
        pdf.image(_logo_buf, x=40, y=38, w=130)
        _logo_buf.seek(0)

    # Company name
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(90)
    pdf.cell(0, 12, s(_CO.upper()), ln=True, align="C")

    # Tagline
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(27, 120, 214)
    pdf.set_y(106)
    pdf.cell(0, 8, "Short term contracts, long term relationships", ln=True, align="C")

    # Divider
    pdf.set_draw_color(27, 120, 214)
    pdf.set_line_width(0.6)
    pdf.line(40, 120, 170, 120)

    # Proposal label
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(126)
    pdf.cell(0, 8, s(f"CUSTOMER PROPOSAL"), ln=True, align="C")
    if _comp:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(27, 120, 214)
        pdf.set_y(136)
        pdf.cell(0, 7, s(f"Prepared for: {_comp}"), ln=True, align="C")
        _rep_cov = s(_prepared_by())
        if _rep_cov:
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, f"Prepared by: {_rep_cov}", ln=True, align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(200, 200, 220)
    pdf.set_y(146)
    pdf.cell(0, 6, s(f"Date: {date.today().strftime('%d %B %Y')}"), ln=True, align="C")

    # ── About Us section ──────────────────────────────────────────────────────
    pdf.set_y(165)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(27, 120, 214)
    pdf.cell(0, 8, s(f"About {_CO}"), ln=True, align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(220, 220, 230)
    pdf.set_x(30)
    pdf.multi_cell(150, 5.5,
        s(_CO_ABOUT +
        "serving businesses across South Wales and the surrounding areas. We understand the "
        "unique needs of our community and are committed to delivering solutions that "
        "work for you. Our experienced local engineers are always on hand to provide "
        "friendly, fast and personalised service."),
        align="C"
    )

    # ── Values section ────────────────────────────────────────────────────────
    pdf.set_y(215)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(27, 120, 214)
    pdf.cell(0, 7, "Our Values", ln=True, align="C")
    pdf.ln(1)

    values = [
        (">  Rapid",    "Response times within the hour to minimise downtime"),
        (">  Complete", "Full-stack: Telecoms, Mobile, Networking, IT & Payments"),
    ]
    for title, desc in values:
        pdf.set_x(30)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(45, 5.5, s(title), ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(190, 190, 210)
        pdf.cell(0, 5.5, s(desc), ln=True)
        pdf.ln(0.5)

    # ── Contact footer ────────────────────────────────────────────────────────
    pdf.set_fill_color(27, 120, 214)
    pdf.rect(0, 263, 210, 0.6, 'F')

    pdf.set_y(267)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(200, 200, 220)
    pdf.cell(0, 5, s(f"{_CO_PHONE}   |   {_CO_EMAIL}   |   {_CO_WEB}"), ln=True, align="C")
    pdf.set_y(273)
    pdf.cell(0, 5, s(_BRAND.get("address", "10 Plas Melin, Westbourne Road, Whitchurch, Cardiff CF14 2BT")), ln=True, align="C")

    # Teal accent stripe at bottom
    pdf.set_fill_color(27, 120, 214)
    pdf.rect(0, 292, 210, 5, 'F')

    # ── PAGE 2 onwards: standard proposal pages ───────────────────────────────
    # ── CONTRACT SUMMARY (Ofcom) - given before signing, generated per deal ──
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    _add_header(pdf, "Contract Summary")

    def _cs_bar(title):
        pdf.ln(2)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6.5, s("  " + title), fill=True, ln=True)
        pdf.set_text_color(0, 0, 0); pdf.ln(1.5)

    _cs_k = 1.0     # density: tightened below for deals with many lines so the summary stays on one page

    def _cs_row(label, value, bold=False, shade=False):
        pdf.set_x(pdf.l_margin)
        if shade:
            pdf.set_fill_color(245, 247, 255)
        pdf.set_font("Helvetica", "B" if bold else "", 8.5 if _cs_k > 0.85 else 8)
        pdf.cell(130, 6 * _cs_k, s("  " + label), fill=shade, ln=False)
        pdf.cell(0, 6 * _cs_k, s(value), fill=shade, ln=True, align="R")

    def _cs_text(text, size=8.2, style=""):
        pdf.set_font("Helvetica", style, size); pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 4.2 * max(_cs_k, 0.85), s(text))

    _cs_months = int(lease_term)
    _cs_term_lbl = LEASE_TERM_LABELS.get(lease_term, f"{_cs_months} months")
    _cs_text(f"This summary sets out the main parts of your contract with {_CO_LEGAL}, as required by Ofcom. "
             "Please read it before you sign. It forms part of your contract together with the Order Form, "
             "the agreements in this pack and our Terms & Conditions.", 8.5)
    pdf.ln(1)
    _cs_text(f"Provider: {_CO_LEGAL}, {_BRAND.get('address', '')}  |  {_CO_PHONE}  |  {_CO_EMAIL}  |  {_CO_WEB}", 7.8)
    _cs_text(f"Customer: {_comp or '-'}", 7.8)

    # Services & equipment
    _cs_bar("1. Your services and equipment (monthly, excluding VAT)")
    _cs_lines = []
    if svc["bb_sell"] > 0:
        _cs_lines.append((f"Broadband - {bb_provider} {bb_package}"
                          + (f" + {extra_bb_count} additional line(s)" if extra_bb_count else ""), svc["bb_sell"]))
    if svc["lic_monthly"] > 0:
        _cs_lines.append((f"User licences ({total_voice_channels} users, UK calls included)", svc["lic_monthly"]))
    if sw_sell_total + svc.get("wallboard_mo", 0.0) > 0:
        _cs_lines.append(("Software & add-ons", sw_sell_total + svc.get("wallboard_mo", 0.0)))
    for _r in cs_svc_rows:
        if _r.get("qty", 0) > 0:
            _cs_lines.append((_r["name"], _r["sell"] * _r["qty"]))
    for _r in sec_rows:
        if _r.get("qty", 0) > 0:
            _cs_lines.append((f"{_r['name']} x{_r['qty']}", _r["sell"] * _r["qty"]))
    for _r in it_rows:
        if _r.get("qty", 0) > 0:
            _cs_lines.append((f"{_r['service']} x{_r['qty']}", _r["sell"] * _r["qty"]))
    for _r in mobile_rows:
        if _r.get("qty", 0) > 0:
            _cs_lines.append((f"Mobile - {mobile_label(_r)} x{_r['qty']}", _r["sell"] * _r["qty"]))
    for _d_, _a_ in XM_ROWS:
        _cs_lines.append((_d_, _a_))
    if is_spread:
        _cs_lines.append(((f"System rental over {_cs_term_lbl}" if is_inhouse else f"Hardware (equipment lease over {_cs_term_lbl})"), hw_monthly_spread))
    if printer_rows:
        _cs_lines.append((f"Printers - lease over {printer_term} months ({printer_count} printer(s), incl. set up & delivery)",
                          printer_monthly))
        for _r in printer_rows:
            _cs_lines.append((f"Printing - {_r['name']}: est. {_r['volume']:,} prints/month at {_r['cpc_sell']:.3f}p per print",
                              _r["print_mo"]))
    _cs_k = max(0.6, 1.0 - 0.05 * max(0, len(_cs_lines) + max(1, -(-int(lease_term) // 12)) - 12))
    for _i, (_l, _v) in enumerate(_cs_lines):
        _cs_row(_l, f"£{_v:,.2f}", shade=(_i % 2 == 0))
    _cs_row("Total monthly charge", f"£{total_mo:,.2f}", bold=True)
    if not is_spread:
        _cs_row("Hardware - one-off payment", f"£{upfront:,.2f}")
    _cs_text("Broadband speeds are estimates and depend on the network - see the Network Services & Broadband Agreement.", 7.5, "I")

    # Term, leaving early, after the minimum term
    _cs_bar("2. How long your contract lasts")
    _cs_text(f"Minimum term: {_cs_term_lbl} ({_cs_months} months) from the date your services go live.", 8.3, "B")
    _cs_text("Leaving early: if you cancel during the minimum term, a Cancellation Charge applies as set out in our "
             "Terms & Conditions (broadly, the charges remaining to the end of the minimum term)."
             + (" Your equipment is on a separate lease with the finance company - see the Equipment Lease Agreement."
                if is_lease else ""), 8)
    _cs_text(C.get("contract_after_term_text",
                   "After the minimum term: your contract continues until you give notice. We will contact you "
                   "before your minimum term ends to remind you and tell you about our best prices. See our "
                   "Terms & Conditions for notice periods."), 8)

    # Important information
    _cs_bar("3. Important information")
    _cs_text("Emergency calls (999/112): our phone services use your broadband. If there is a power cut or your "
             "broadband goes down, you may not be able to make calls, including emergency calls. Keep a mobile "
             "phone or traditional line available for emergencies. Emergency call location may be limited.", 8)
    pdf.ln(0.5)
    _cmp_mail = _BRAND.get("complaints_email", _CO_EMAIL)
    _cs_text(f"Complaints: call {_CO_PHONE} or email {_cmp_mail}. Our complaints policy is at {_CO_WEB}/complaints-policy. "
             "If your complaint isn't resolved within 8 weeks, or you receive a deadlock letter, you can take it to "
             "the Communications Ombudsman (www.commsombudsman.org) free of charge.", 8)
    pdf.ln(0.5)
    _cs_text(f"Accessibility: if you have accessibility needs or would like this information in another format, "
             f"contact us on {_CO_PHONE} or {_CO_EMAIL}.", 8)

    pdf.set_auto_page_break(True, margin=15)   # re-enable for content pages
    pdf.add_page()
    _add_header(pdf)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "CUSTOMER PROFILE", ln=True)
    pdf.set_draw_color(240, 240, 240)
    pdf.set_line_width(0.3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    def row2(l1, v1, l2="", v2=""):
        """Two-column label+value row. Auto-shrinks font if value is long."""
        def _val_font(val):
            """Pick font size so text fits in 55mm column."""
            return 8 if len(str(val)) > 28 else 10

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(40, 6, l1, ln=False)
        pdf.set_font("Helvetica", "", _val_font(v1))
        pdf.set_text_color(0, 0, 0)
        # Clip at 40 chars to guarantee no overflow
        v1_str = str(v1)[:40] + ("..." if len(str(v1)) > 40 else "")
        pdf.cell(55, 6, v1_str, ln=False)
        if l2:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(40, 6, l2, ln=False)
            pdf.set_font("Helvetica", "", _val_font(v2))
            pdf.set_text_color(0, 0, 0)
            v2_str = str(v2)[:36] + ("..." if len(str(v2)) > 36 else "")
            pdf.cell(0, 6, v2_str, ln=True)
        else:
            pdf.ln()

    row2("Company:", _comp or "-", "Entity Type:", _btype)
    row2("Reg. No.:", _reg or "-", "No. of Employees:", str(num_employees))
    row2("Contact:", _contact or "-", "Phone:", _phone or "-")
    row2("Email:", _demail or "-", "Billing Email:", _bemail or "-")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(40, 6, "Install Address:", ln=False)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(pdf.l_margin + 40)          # start AFTER the label, not at left edge
    pdf.multi_cell(pdf.epw - 40, 5.5, _addr or "-")
    pdf.ln(4)

    # Commercial Summary
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "COMMERCIAL SUMMARY", ln=True)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)

    # Cost comparison table
    pdf.set_fill_color(8, 31, 58)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 7, "Description", border=0, fill=True, ln=False)
    pdf.cell(50, 7, "Current", border=0, fill=True, ln=False, align="C")
    pdf.cell(50, 7, _CO, border=0, fill=True, ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)

    if is_spread:
        curr_hw  = f"£{current_system:.2f}/mo" if current_system > 0 else "-"
        curr_svc = f"£{(current_bb + current_calls + current_mobile):.2f}/mo" if (current_bb + current_calls + current_mobile) > 0 else "-"
        _curr_hosted = f"£{current_hosted:.2f}/mo" if current_hosted > 0 else "-"
        rows = [
            (("System rental" if is_inhouse else "Hardware (spread over term)"), curr_hw,  f"£{hw_monthly_spread:.2f}/mo"),
            ("User / Voice Licences", _curr_hosted, f"£{svc['lic_monthly']:.2f}/mo"),
            ("Network & Connectivity (BB, Mobile)", curr_svc, f"£{pure_connectivity:.2f}/mo"),
            ("Installation / Setup", "-", "Included in system rental" if is_inhouse else "Included in lease rental"),
        ]
    else:
        curr_hw  = f"£{current_system:.2f}/mo" if current_system > 0 else "-"
        curr_svc = f"£{(current_bb + current_calls + current_mobile):.2f}/mo" if (current_bb + current_calls + current_mobile) > 0 else "-"
        _curr_hosted = f"£{current_hosted:.2f}/mo" if current_hosted > 0 else "-"
        rows = [
            ("Upfront Hardware (one-off)", curr_hw,  f"£{upfront:.2f}"),
            ("User / Voice Licences", _curr_hosted, f"£{svc['lic_monthly']:.2f}/mo"),
            ("Network & Connectivity (BB, Mobile)", curr_svc, f"£{pure_connectivity:.2f}/mo"),
            ("Installation", "-", f"£{compute_install_cost():.2f}"),
        ]
    for i, (desc, curr, new) in enumerate(rows):
        bg = (248, 249, 255) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.cell(90, 6, f"  {desc}", border=0, fill=True, ln=False)
        pdf.cell(50, 6, curr, border=0, fill=True, ln=False, align="C")
        pdf.cell(50, 6, new, border=0, fill=True, ln=True, align="C")

    # Total row
    curr_total_str = f"£{current_total:.2f}/mo" if current_total > 0 else "-"
    pdf.set_fill_color(27, 120, 214)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 7, "  TOTAL MONTHLY (excl. VAT)", fill=True, ln=False)
    pdf.cell(50, 7, curr_total_str, fill=True, ln=False, align="C")
    pdf.cell(50, 7, f"£{total_mo:.2f}/mo" + ("" if is_spread else f" + £{upfront:.2f} upfront"), fill=True, ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if credits_months > 0:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, f"* Introductory credit of £{credits_amount:.2f}/month applied for {credits_months} months", ln=True)
    pdf.ln(2)

    # Equipment table
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "EQUIPMENT & SERVICES", ln=True)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)

    pdf.set_fill_color(8, 31, 58)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(110, 7, "Description", fill=True, ln=False)
    pdf.cell(30, 7, "Qty", fill=True, ln=False, align="C")
    pdf.cell(50, 7, "Monthly Charge", fill=True, ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)

    all_equip_pdf = []
    _pdf_hw_billing = ("In System Rental" if is_inhouse else "In Monthly Lease") if is_spread else "Paid Upfront"

    # Physical hardware (qty > 0 only)
    for name, qty in {**desktop_quantities, **cordless_quantities,
                       **headset_quantities, **other_quantities}.items():
        if qty > 0:
            all_equip_pdf.append((name, qty, _pdf_hw_billing))
    if auto_switch and not _no_switch:
        all_equip_pdf.append((f"Switch: {rec_switch['name']}", 1, _pdf_hw_billing))
    if add_router:
        if router_quantities:
            for _rn, _rq in router_quantities.items():
                all_equip_pdf.append((_rn, _rq, _pdf_hw_billing))
        elif router_type not in ("None / Customer Supplied", ""):
            all_equip_pdf.append((router_type, 1, _pdf_hw_billing))

    # Voice Channel Licences
        vc_billing_pdf = f"£{svc['lic_monthly']:.2f}/mo"  # always monthly - not part of lease
        all_equip_pdf.append((f"User / Voice Licences x{total_voice_channels}",
                               total_voice_channels, vc_billing_pdf))

    # Software add-ons
    for addon_name, addon_qty, addon_cost, addon_sell in SW_ADDONS:
        if addon_qty > 0:
            addon_billing_pdf = f"£{addon_sell * addon_qty:.2f}/mo"  # SW always monthly
            all_equip_pdf.append((addon_name, addon_qty, addon_billing_pdf))

    # Network & Connectivity
    if svc["bb_sell"] > 0:
        all_equip_pdf.append((f"Broadband - {bb_provider} {bb_package}", 1,
                               f"£{svc['bb1_sell']:.2f}/mo"))
    for _xp, _xq, _xs in extra_bb_display():
        all_equip_pdf.append((f"Broadband - {bb_provider} {_xp} (additional)", _xq, f"£{_xs:.2f}/mo"))
    for r in mobile_rows:
        if r["qty"] > 0:
            all_equip_pdf.append((f"{r['network']} - {r['package']}", r["qty"],
                                   f"£{r['sell']*r['qty']:.2f}/mo"))
    for r in it_rows:
        if r["qty"] > 0:
            all_equip_pdf.append((f"IT: {r['service']} x{r['qty']}", r["qty"],
                                   f"£{r['sell']*r['qty']:.2f}/mo"))
    for _r in printer_rows:
        all_equip_pdf.append((f"Printer: {_r['name']}", _r["qty"], f"Printer lease ({printer_term} mo)"))
    if AC["maint_annual"] > 0 and AC["listed"]:
        all_equip_pdf.append((f"Air conditioning on-site support (after year {int(AC_COST['free_support_years'])})", 1, f"£{AC['maint_annual']:,.2f}/yr"))


    for i, (name, qty, charge) in enumerate(all_equip_pdf):
        bg = (248, 249, 255) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.cell(110, 6, f"  {name}", fill=True, ln=False)
        pdf.cell(30, 6, str(qty), fill=True, ln=False, align="C")
        pdf.cell(50, 6, charge, fill=True, ln=True, align="C")
    pdf.ln(4)

    # -- PAGE 2: ORDER FORM --
    pdf.add_page()
    _add_header(pdf, "Telephony System Order Form")

    row2("Date:", str(date.today()), "Contract Term:", LEASE_TERM_LABELS[lease_term])
    row2("Company:", _comp or "-", "Reg. No.:", _reg or "-")
    row2("No. of Employees:", str(num_employees), "Install Type:", install_type)
    row2("No. of Sites:", str(num_sites), "Payment Profile:", f"1+{lease_term-1}")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Equipment & Services", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_fill_color(8, 31, 58)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(130, 6, "Item", fill=True, ln=False)
    pdf.cell(30, 6, "Quantity", fill=True, ln=False, align="C")
    pdf.cell(30, 6, "Notes", fill=True, ln=True, align="C")
    pdf.set_text_color(0, 0, 0)

    _ac_names = {it["name"] for it, _q in AC["listed"]} | {AC["inst_name"]}
    _order_rows = [r for r in all_equip_pdf if r[0] not in _ac_names and not str(r[0]).startswith("Air conditioning on-site support")]
    if len(_order_rows) != len(all_equip_pdf):
        _order_rows.append(("Air conditioning - see the separate Shire Leasing hire agreement", 1, ""))
    for i, (name, qty, charge) in enumerate(_order_rows):
        bg = (248, 249, 255) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.cell(130, 6, f"  {name}", fill=True, ln=False)
        pdf.cell(30, 6, str(qty), fill=True, ln=False, align="C")
        pdf.cell(30, 6, "", fill=True, ln=True)
    pdf.ln(4)

    # Hardware & payment summary
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Hardware & Payment Summary", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(pdf.l_margin)
    if is_spread:
        # Note: hw_monthly_spread includes termination cost if applicable - do not
        # expose the raw hw_sell figure as the maths would not reconcile for the customer
        pdf.multi_cell(pdf.epw, 5,
            f"Your {'system rental' if is_inhouse else 'system investment'} of £{hw_monthly_spread:.2f} + VAT per month covers all hardware, "
            f"configuration and associated setup costs, spread over the {LEASE_TERM_LABELS[lease_term]} agreement. "
            f"Total monthly payment of £{total_mo:.2f} + VAT will be collected by Direct Debit, "
            f"covering your complete telephony solution and all service charges."
        )
    else:
        pdf.multi_cell(pdf.epw, 5,
            f"Hardware is provided on a one-off upfront basis. "
            f"Total hardware investment: £{upfront:.2f} + VAT. "
            f"Monthly service charges of £{total_mo:.2f} + VAT will be collected by Direct Debit."
        )
    pdf.ln(4)

    # Special conditions
    if credits_months > 0 or cashback_amount > 0:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Special Conditions", ln=True)
        pdf.set_font("Helvetica", "", 9)
        if credits_months > 0:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(pdf.epw, 5,
                f"An introductory credit of £{credits_amount:.2f}/month will be applied for {credits_months} months, "
                f"after which it will automatically cease. {_CO} reserves the right to suspend or withdraw "
                "this credit in the event of any arrears."
            )
        if cashback_amount > 0:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(pdf.epw, 5,
                f"{_CO_LEGAL} agrees to contribute £{cashback_amount:.2f} towards extricating the customer "
                f"from existing agreements. This amount will be paid once {_CO} have taken over the lines and the "
                "system has been formally accepted into service."
            )
        pdf.ln(3)

    # Termination charges breakdown (only when there are terminations)
    if is_spread and (termination_lease > 0 or termination_services > 0):
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Termination Charges Breakdown", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_fill_color(248, 249, 255)
        for _tl, _tv in (("Lease terminations", termination_lease), ("Service charge terminations", termination_services)):
            if _tv > 0:
                pdf.cell(130, 6, s("  " + _tl), fill=True, ln=False)
                pdf.cell(0, 6, f"up to £{_tv:,.2f}  ", fill=True, ln=True, align="R")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(130, 6.5, "  Total termination charges", ln=False)
        pdf.cell(0, 6.5, f"up to £{termination_cost:,.2f}  ", ln=True, align="R")
        pdf.ln(0.5)
        pdf.set_font("Helvetica", "I", 7.5); pdf.set_text_color(90, 90, 110); pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 3.8, s(
            'These figures are "up to" amounts and no more than these sums will be payable. Payment is made on '
            "receipt of invoices from the losing providers, provided within 3 months of the installation."))
        pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 9)
        pdf.ln(3)

    # Pointer to the declaration page (keeps this page short and the order details together)
    pdf.set_font("Helvetica", "I", 8.5); pdf.set_text_color(90, 90, 110); pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 4.5, s("Declaration, small business information and signatures are on the next page."))
    pdf.set_text_color(0, 0, 0)

    # ── DECLARATION & SIGNATURE PAGE (its own page) ──────────────────────────────
    pdf.add_page()
    _add_header(pdf, "Declaration & Signatures")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 8.5); pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 4.5, s(f"Order for: {_comp or '-'}   |   Contract term: {LEASE_TERM_LABELS.get(lease_term, '')}   |   "
                                   f"Total monthly: £{total_mo:,.2f} + VAT"))
    pdf.ln(3)
    # Documents provided before signing (Ofcom)
    pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, "  Documents provided before signing", fill=True, ln=True)
    pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 9); pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 4.5, s("I confirm that, before signing this Order Form, I was given a copy of the following "
                                   "documents and had the opportunity to read them:"))
    pdf.ln(1)
    _docs = ["Contract Summary", f"Terms & Conditions (summary in this pack; full terms at {_CO_WEB}/terms-conditions)",
             "Network Services & Broadband Agreement"] + (["Equipment Lease Agreement"] if is_lease else []) + ["This Order Form"]
    for _d in _docs:
        _yb = pdf.get_y() + 0.8
        pdf.set_draw_color(8, 31, 58); pdf.rect(pdf.l_margin + 2, _yb, 3.4, 3.4)
        _bx = pdf.l_margin + 2; pdf.set_line_width(0.45)                      # pre-ticked
        pdf.line(_bx + 0.6, _yb + 1.8, _bx + 1.4, _yb + 2.8); pdf.line(_bx + 1.4, _yb + 2.8, _bx + 2.9, _yb + 0.6)
        pdf.set_line_width(0.2)
        pdf.set_x(pdf.l_margin + 8); pdf.set_font("Helvetica", "", 9); pdf.cell(0, 6, s(_d), ln=True)
    pdf.set_draw_color(0, 0, 0); pdf.ln(4)

    # Small business 24-month right - separate, express waiver (Ofcom)
    _small_limit = int(C.get("small_business_max_employees", 9))    # fewer than 10 employees
    if int(lease_term) > 24 and int(num_employees or 0) <= _small_limit:
        _wy = pdf.get_y()
        pdf.set_fill_color(255, 248, 225); pdf.set_draw_color(230, 150, 30); pdf.set_line_width(0.5)
        pdf.set_x(pdf.l_margin + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.multi_cell(pdf.epw - 6, 5, "Small business - your right to a contract of no more than 24 months", fill=True)
        pdf.set_x(pdf.l_margin + 3); pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(pdf.epw - 6, 4.2, s(
            f"If your business has fewer than {_small_limit + 1} employees, or is a not-for-profit, Ofcom's rules give you "
            f"the right to a maximum contract length of 24 months. The minimum term of this contract is {int(lease_term)} "
            "months, which is longer than 24 months. By initialling or signing here, you separately and expressly confirm that you "
            "understand this right, and that you choose to waive it in order to enter into this longer contract term."),
            fill=True)
        pdf.set_x(pdf.l_margin + 3); pdf.set_font("Helvetica", "B", 8.5)
        _wsig_ok = bool(sig_bytes) and len(sig_bytes) > 100
        if _wsig_ok:
            # Signed: put the captured signature and date in the box
            _sy = pdf.get_y()
            pdf.cell(pdf.epw - 6, 14, "", fill=True, ln=True)
            pdf.set_xy(pdf.l_margin + 5, _sy + 4.5)
            pdf.cell(38, 5, "Customer signature:")
            try:
                import tempfile, os as _os2
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _wtf:
                    _wtf.write(sig_bytes); _wsp = _wtf.name
                try:
                    pdf.image(_wsp, x=pdf.l_margin + 44, y=_sy + 0.8, w=34, h=12.4)
                finally:
                    _os2.unlink(_wsp)
            except Exception:
                pass
            pdf.set_xy(pdf.l_margin + 90, _sy + 4.5)
            pdf.cell(pdf.epw - 96, 5, s(f"Date:  {str(sig_timestamp or date.today())[:10]}"))
            pdf.set_y(_sy + 14)
        else:
            pdf.cell(pdf.epw - 6, 8, "Customer initials:  ____________        Date:  ____________", fill=True, ln=True)
        pdf.rect(pdf.l_margin + 1.5, _wy - 1, pdf.epw - 3, pdf.get_y() - _wy + 2)
        pdf.set_draw_color(0, 0, 0); pdf.set_line_width(0.2); pdf.ln(3)

    # Signatures (same page as the declaration and waiver being confirmed)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Signatures", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "For (Company Name):", ln=True)
    pdf.ln(2)
    _embed_sig(pdf, sig_bytes, signer_name=sig_name,
               company=sig_company, timestamp=sig_timestamp)
    pdf.cell(0, 0.5, "", border="T", ln=True)
    pdf.ln(3)
    pdf.cell(0, 5, f"Name & Position: {_signer or '___________________________'}", ln=True)
    pdf.ln(6)

    # -- PAGE 3: NETWORK SERVICES AGREEMENT --
    pdf.add_page()
    _add_header(pdf, "Network Services & Broadband Agreement")

    row2("Date:", str(date.today()), "Agreement Term:", LEASE_TERM_LABELS[lease_term])
    row2("Company:", _comp or "-", "Company Phone:", _phone or "-")
    row2("Billing Email:", _bemail or "-")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Service Charge Breakdown", ln=True)
    pdf.set_font("Helvetica", "", 9)

    if bb_free_year and _bb_yr1_saving > 0:
        svc_items = [(f"{bb_provider} - {bb_package} (FREE months 1-12)", 1,
                      f"£0.00/mo (then £{_bb_full_sell:.2f}/mo)")]
    else:
        svc_items = [(f"{bb_provider} - {bb_package}", 1, f"£{svc['bb1_sell']:.2f}/mo")]
    for _xp, _xq, _xs in extra_bb_display():
        svc_items.append((f"{bb_provider} - {_xp} (additional)", _xq, f"£{_xs:.2f}/mo"))
    if total_voice_channels > 0:
        svc_items.append((f"User / Voice Licences x{total_voice_channels}", total_voice_channels, f"£{svc['lic_monthly']:.2f}/mo"))
    if ooh_support:
        svc_items.append(("24/7 OOH Support", 1, "£25.00/mo"))
    if dark_web_mon:
        svc_items.append(("Dark Web Monitoring", 1, "£10.00/mo (after 3m FOC)"))
    if proactive_bb:
        svc_items.append(("Proactive Broadband Management", 1, "£10.00/mo (after 3m FOC)"))
    # Call Scope monthly services
    for _csr in cs_svc_rows:
        if _csr.get("qty", 0) > 0:
            svc_items.append((s(_csr["name"]), _csr["qty"],
                              f"£{_csr['sell']*_csr['qty']:.2f}/mo"))
    # Security tiers
    for _sr in sec_rows:
        if _sr.get("qty", 0) > 0:
            svc_items.append((s(_sr["name"]), _sr["qty"],
                              f"£{_sr['sell']*_sr['qty']:.2f}/mo"))
    # Mobile SIMs
    for _mr in mobile_rows:
        if _mr.get("qty", 0) > 0:
            svc_items.append((s(f"Mobile - {mobile_label(_mr)}"), _mr["qty"],
                              f"£{_mr['sell']*_mr['qty']:.2f}/mo"))

    for _d_, _a_ in XM_ROWS:
        svc_items.append((s(_d_), 1, f"£{_a_:.2f}/mo"))
    pdf.set_fill_color(8, 31, 58)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(100, 6, "Service", fill=True, ln=False)
    pdf.cell(30, 6, "Qty", fill=True, ln=False, align="C")
    pdf.cell(60, 6, "Monthly Charge", fill=True, ln=True, align="C")
    pdf.set_text_color(0, 0, 0)

    for i, (name, qty, charge) in enumerate(svc_items):
        bg = (248, 249, 255) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.cell(100, 6, f"  {name}", fill=True, ln=False)
        pdf.cell(30, 6, str(qty), fill=True, ln=False, align="C")
        pdf.cell(60, 6, charge, fill=True, ln=True, align="C")

    pdf.set_fill_color(27, 120, 214)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(130, 6, "  TOTAL MONTHLY SERVICE CHARGES", fill=True, ln=False)
    pdf.cell(60, 6, f"£{svc['total_sell']:.2f}/mo", fill=True, ln=True, align="C")
    pdf.set_font("Helvetica","I",7); pdf.set_text_color(128,128,128)
    pdf.set_text_color(0,0,0)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 8)
    terms = (
        f"Whilst {_CO} have agreed to supply connectivity services, we are not the provider of these services. "
        f"{_CO} can advise on lead times, however you understand that there are circumstances outside of our control "
        f"(for example, if infrastructure is required in your area, or subject to survey), which {_CO} are not liable for. "
        "The broadband speeds stated are estimates only and are dependent on services supplied by third-party network providers. "
        "Actual speeds may vary due to network availability and other external factors.\n\n"
        "NB: the above charges are estimated based on information provided and are subject to an engineer report. "
        "Your first bill will be higher due to part period charges."
    )
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 4.5, terms)
    # Emergency calls warning (hosted voice)
    pdf.ln(2)
    pdf.set_fill_color(255, 240, 240); pdf.set_draw_color(200, 60, 60); pdf.set_line_width(0.4)
    pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", "B", 8.5)
    pdf.multi_cell(pdf.epw, 5, "Important: emergency calls (999/112)", border="LTR", fill=True)
    pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(pdf.epw, 4.2, s("Our phone services run over your broadband. If there is a power cut or your broadband "
                                   "goes down, you may not be able to make calls, including calls to 999/112. Please keep "
                                   "a mobile phone or traditional line available for emergencies. Emergency call location "
                                   "information may be limited."), border="LBR", fill=True)
    pdf.set_draw_color(0, 0, 0); pdf.set_line_width(0.2)
    pdf.ln(3)

    # ── Special Conditions (from consultant notes) ───────────────────────────
    _special_conds = str(st.session_state.get("c_notes_val", "") or "").strip()
    if _special_conds:
        pdf.ln(2)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(0, 6, "  Special Conditions / Agreed Terms", fill=True, ln=True)
        pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 8)
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(255, 250, 230)
        pdf.multi_cell(pdf.epw, 4.5, s(_special_conds.replace("-", "-").replace("-", "-")), fill=True, align="J")
        pdf.ln(4)
        pdf.set_fill_color(255, 255, 255)


    pdf.set_font("Helvetica", "B", 9)
    pdf.set_font("Helvetica", "B", 9)
    pdf.ln(2)
    _embed_sig(pdf, sig_bytes, signer_name=sig_name,
    company=sig_company, timestamp=sig_timestamp)
    pdf.cell(0, 0.5, "", border="T", ln=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Name & Position: {_signer or '___________________________'}", ln=True)
    pdf.ln(4)
    # -- PAGE 4: LEASE AGREEMENT / QUOTATION SUMMARY --
    pdf.add_page()
    _add_header(pdf, "System Rental Summary" if is_inhouse else "Equipment Lease Agreement")

    # ── Quotation Includes ────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Quotation Includes", ln=True)
    pdf.ln(1)

    def _qi_row(label, value, bold_val=False):
        pdf.set_fill_color(248, 249, 255)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(120, 6, f"  {label}", fill=True, ln=False)
        pdf.set_font("Helvetica", "B" if bold_val else "", 9)
        pdf.cell(0, 6, str(value), fill=True, ln=True, align="R")

    _settle_str = f"£{termination_cost:.2f}" if termination_cost > 0 else "£0.00"
    _qi_row("Settlements", _settle_str)
    _qi_row("Programmed equipment for self installation", "Yes")
    _qi_row("Full equipment and software listed", "Yes")
    _qi_row("Project management", "Yes")
    _qi_row("Includes 1 year on-site warranty", "No" if _maint_optout() else "Yes")
    pdf.ln(6)

    # ── Equipment Rental Terms ────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Equipment Rental Terms", ln=True)
    pdf.ln(1)

    pdf.set_fill_color(8, 31, 58)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(60, 8, "  Monthly rental period of", fill=True, ln=False)
    pdf.set_fill_color(27, 120, 214)
    pdf.cell(35, 8, f"  £{(hw_monthly_spread if is_spread else pl_data['rental']):.2f}", fill=True, ln=False)
    pdf.set_fill_color(8, 31, 58)
    pdf.cell(0, 8, "  plus VAT at the prevailing rate", fill=True, ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    # ── Separate billing note ─────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 4.5,
    f"Monthly services (hosted licences, broadband, calls) of £{svc['total_sell']:.2f} + VAT "
    + (f"will be billed by {_CO} Ltd together with your system rental. " if is_inhouse else
       f"will be billed separately by {_CO} Ltd under a separate agreement. ") +
    f"Total monthly commitment: £{total_mo:.2f} + VAT. "
    f"*Fair usage policy applies, subject to terms and conditions.",
    align="J"
    )
    pdf.ln(6)

    # ── Customer confirmation text ────────────────────────────────────────────
    pdf.set_fill_color(248, 249, 255)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 4.5,
    f"I confirm that the above figures are representative of our current average expenditure "
    f"and I understand that I will be billed in line with {_CO} Ltd's current Terms and Conditions. "
    + (f"I understand that I will be billed by {_CO} Ltd for the system rental, lines, calls{'' if _maint_optout() else ', maintenance'} and broadband. "
       if is_inhouse else
       f"I understand that I will be billed separately for the system rental by a 3rd party funder "
       f"and lines, calls{'' if _maint_optout() else ', maintenance'} and broadband by {_CO} Ltd under a separate agreement. ")
    + f"*Fair usage policy applies, subject to terms and conditions.",
    align="J"
    )
    pdf.ln(8)

    # ── Signature section ─────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, f"For {s(_comp or 'Company Name')}:", ln=True)
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Company Name: {s(_comp or '')}", ln=True)

    if sig_bytes:
        try:
            import tempfile as _tf2, os as _os2
            with _tf2.NamedTemporaryFile(suffix=".png", delete=False) as _stf:
                _stf.write(sig_bytes); _stf_path = _stf.name
            try:
                pdf.image(_stf_path, x=pdf.l_margin, y=pdf.get_y(), h=14)
            finally:
                _os2.unlink(_stf_path)
            pdf.ln(16)
        except Exception:
            pdf.cell(0, 14, "Signed: ________________", ln=True)
    else:
        pdf.cell(0, 14, "Signed: ________________", ln=True)
    pdf.set_font("Helvetica", "", 9)
    _la_contact_raw = sig_name or _contact or ""
    _la_parts = [p.strip() for p in _la_contact_raw.split(" - ", 1)]
    _la_name  = s(_la_parts[0]) if _la_parts[0] else "________________________"
    _la_pos   = s(_la_parts[1]) if len(_la_parts) > 1 else "________________________"
    pdf.cell(0, 5, f"Name: {_la_name}", ln=True)
    pdf.cell(0, 5, f"Position / Title: {_la_pos}", ln=True)
    pdf.cell(0, 5, f"Date: {date.today().strftime('%d/%m/%Y')}", ln=True)

    # ── PRINTER LEASE AGREEMENT (only when printers are on the deal) ──────────
    if printer_rows:
        pdf.add_page()
        _add_header(pdf, "Printer Lease Agreement")
        pdf.set_font("Helvetica", "B", 11); pdf.cell(0, 7, "Printers", ln=True); pdf.ln(1)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 9)
        pdf.cell(120, 7, "  Model", fill=True); pdf.cell(0, 7, "Quantity  ", fill=True, ln=True, align="R")
        pdf.set_text_color(0, 0, 0)
        for _i, _r in enumerate(printer_rows):
            pdf.set_fill_color(*((248, 249, 255) if _i % 2 == 0 else (255, 255, 255)))
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(120, 6, s(f"  {_r['name']}"), fill=True); pdf.cell(0, 6, f"{_r['qty']}  ", fill=True, ln=True, align="R")
        pdf.ln(3)
        _qi_row("Set up & delivery", "Included")
        _qi_row("Lease term", f"{printer_term} months")
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11); pdf.cell(0, 7, "Printer Rental Terms", ln=True); pdf.ln(1)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 10)
        pdf.cell(60, 8, "  Monthly rental of", fill=True, ln=False)
        pdf.set_fill_color(27, 120, 214); pdf.cell(35, 8, f"  £{printer_monthly:.2f}", fill=True, ln=False)
        pdf.set_fill_color(8, 31, 58); pdf.cell(0, 8, f"  plus VAT, for {printer_term} months", fill=True, ln=True)
        pdf.set_text_color(0, 0, 0); pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11); pdf.cell(0, 7, "Print Charges", ln=True); pdf.ln(1)
        pdf.set_fill_color(230, 233, 245); pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(70, 6.5, "  Model", fill=True); pdf.cell(35, 6.5, "Price per print", fill=True, align="R")
        pdf.cell(40, 6.5, "Est. prints / month", fill=True, align="R"); pdf.cell(0, 6.5, "Est. monthly  ", fill=True, ln=True, align="R")
        pdf.set_font("Helvetica", "", 8.5)
        for _r in printer_rows:
            pdf.cell(70, 6, s(f"  {_r['name']}")); pdf.cell(35, 6, f"{_r['cpc_sell']:.3f}p", align="R")
            pdf.cell(40, 6, f"{_r['volume']:,}", align="R"); pdf.cell(0, 6, f"£{_r['print_mo']:.2f}  ", ln=True, align="R")
        pdf.ln(3)
        pdf.set_font("Helvetica", "", 8); pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 4.5, s(
            f"Print charges are billed monthly in arrears on actual usage at the per-print prices above, which are fixed "
            f"for the {printer_term}-month term. Estimated monthly print charges of £{printer_print_est_mo:.2f} + VAT are "
            f"for guidance only. The printer rental is billed separately from your telephony services."), align="J")
        pdf.ln(5)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 4.5, s(
            f"I confirm the printers, rental and print charges above, and I understand I will be billed in line with "
            f"{_CO_LEGAL}'s current Terms and Conditions."), align="J")
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 9); pdf.cell(0, 5, f"For {s(_comp or 'Company Name')}:", ln=True); pdf.ln(2)
        pdf.set_font("Helvetica", "", 9)
        if sig_bytes:
            try:
                import tempfile as _tf3, os as _os3
                with _tf3.NamedTemporaryFile(suffix=".png", delete=False) as _stf3:
                    _stf3.write(sig_bytes); _stf3_path = _stf3.name
                try:
                    pdf.image(_stf3_path, x=pdf.l_margin, y=pdf.get_y(), h=14)
                finally:
                    _os3.unlink(_stf3_path)
                pdf.ln(16)
            except Exception:
                pdf.cell(0, 14, "Signed: ________________", ln=True)
        else:
            pdf.cell(0, 14, "Signed: ________________", ln=True)
        pdf.cell(0, 5, f"Name: {_la_name}", ln=True)
        pdf.cell(0, 5, f"Position / Title: {_la_pos}", ln=True)
        pdf.cell(0, 5, f"Date: {date.today().strftime('%d/%m/%Y')}", ln=True)
    pdf.add_page()
    _add_header(pdf, "Direct Debit Mandate & Customer Checklist")

    if True:      # always printed - with no bank details entered it is a blank mandate the customer can complete themselves
        _blank_dd = not (bank_name or acc_no)
        _bl = "______________________"
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, "Direct Debit Banking Mandate", ln=True)
        if _blank_dd:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 5, "Please complete your bank details below and sign.", ln=True)
        row2("Bank Name:", _bank or _bl, "Account Holder:", _holder or _bl)
        row2("Account Number:", _accno or _bl, "Sort Code:", _sort or _bl)
        pdf.ln(3)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 4.5,
        f"By signing this mandate you authorise {_CO} to collect payments by Direct Debit in "
        "accordance with the agreed terms. Payments will be collected on or around the 1st of each month."
        )
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Authorised Signature:", ln=True)
        pdf.ln(2)
        _embed_sig(pdf, sig_bytes, signer_name=sig_name,
                   company=sig_company, timestamp=sig_timestamp)
        pdf.cell(90, 0.5, "", border="T", ln=False)
        pdf.cell(15, 0.5, "", ln=False)
        pdf.cell(75, 0.5, "", border="T", ln=True)
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Customer Requirements Checklist", ln=True)
    pdf.set_font("Helvetica", "", 9)
    checklist = [
        "I am aware there may be a delay in switching to the agreed carrier after installation.",
        f"I acknowledge the monthly service charge is £{total_mo:.2f} + VAT per month for {LEASE_TERM_LABELS[lease_term]}.",
        f"I understand {_CO} will only pay the amounts stated toward extricating us from current agreements.",
        "I understand that any 'Special Conditions' are only valid if stated on the Order Form and initialled.",
        "I agree that service charges apply regardless of third-party supplier performance.",
        "I confirm I have received copies of: Support Agreement, Network Service Agreement, Line Rental Agreement, Order Form, Rental Document, and Customer Requirements.",
    ]
    for i, item in enumerate(checklist, 1):
        pdf.set_x(pdf.l_margin)
        pdf.cell(8, 4.5, f"{i}.", ln=False)
        pdf.multi_cell(pdf.epw - 8, 4.5, item)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, f"For {_comp or '(Company Name)'}:", ln=True)
    pdf.ln(2)
    _embed_sig(pdf, sig_bytes, signer_name=sig_name,
               company=sig_company, timestamp=sig_timestamp)
    pdf.cell(90, 0.5, "", border="T", ln=False)
    pdf.cell(15, 0.5, "", ln=False)
    pdf.cell(75, 0.5, "", border="T", ln=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Name & Position: {_signer or '___________________________'}", ln=True)
    pdf.cell(0, 5, f"Date: {date.today()}", ln=True)



    # ── EXCEPTIONAL COMMERCIAL ARRANGEMENT (only when settlement > 0) ──
    if termination_cost > 0:
        # Read rep details from session state (defined in sidebar, not passed as params)
        rep_name     = _prepared_by()
        rep_position = st.session_state.get("q_rep_position", "")
        pdf.add_page()
        _add_header(pdf, "Exceptional Commercial Arrangement")
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Customer Acknowledgement & Authority to Proceed", ln=True)
        pdf.ln(2)
        def _eca_row(lbl, val=""):
            pdf.set_font("Helvetica", "", 9); pdf.set_fill_color(248,249,255)
            pdf.cell(70, 5, f"  {lbl}", fill=True, ln=False)
            pdf.cell(0, 5, f"  {val}", fill=True, ln=True, border="B")
        def _eca_hdr(title):
            pdf.set_fill_color(8,31,58); pdf.set_text_color(255,255,255)
            pdf.set_font("Helvetica","B",10); pdf.cell(0,6,f"  {title}",fill=True,ln=True)
            pdf.set_text_color(0,0,0)
        _eca_hdr("Customer Details")
        _eca_row("Customer Name", s(_signer or "________________________"))
        _eca_row("Company",       s(_comp    or "________________________"))
        _eca_row("Date",          date.today().strftime("%d/%m/%Y"))
        pdf.ln(2)
        _eca_hdr("Commercial Summary")
        pdf.set_font("Helvetica","B",8); pdf.set_fill_color(210,218,235)
        pdf.cell(0,4,"  Existing Finance Agreements",fill=True,ln=True)
        _eca_row("Current Monthly Lease Payment", f"\xa3{current_system:.2f}" if current_system > 0 else "\xa3________________")
        _eca_row("Total Lease Settlement charges", f"\xa3{termination_cost:.2f}")
        pdf.set_font("Helvetica","B",8); pdf.set_fill_color(210,218,235)
        pdf.cell(0,4,"  New System Rental" if is_inhouse else "  New Finance Agreement",fill=True,ln=True)
        _eca_row("Provider" if is_inhouse else "Finance Provider", s(_CO_LEGAL) if is_inhouse else "Shire Leasing")
        _eca_row("Agreement Term",           LEASE_TERM_LABELS[lease_term])
        _eca_row("Monthly Amount",           f"\xa3{hw_monthly_spread:.2f} + VAT")
        _eca_row("Total Existing Finance to settle", f"\xa3{termination_cost:.2f}")
        pdf.ln(2)
        _eca_hdr("Customer Acknowledgement")
        pdf.set_font("Helvetica","",7.5)
        for n, ack in enumerate([
            (f"Telecommunications equipment supplied by {_CO_LEGAL.upper()} is provided under an in-house system rental, paid monthly to {_CO_LEGAL}." if is_inhouse else f"Telecommunications equipment supplied by {_CO_LEGAL.upper()} are financed under a new finance agreement."),
            "Our existing finance agreement will be terminated early and an early settlement payment is required.",
            "We understand the settlement of our existing finance agreement does not include settlement of any existing contracts for telecom services or maintenance.",
            "We have reviewed the Commercial Summary and confirm it accurately reflects the key commercial terms.",
            "We have had sufficient opportunity to ask questions.",
            "We have had the opportunity to obtain independent legal and/or financial advice.",
            "We are entering into this agreement voluntarily.",
            f"This transaction is our own commercial decision. {_CO_LEGAL.upper()} has not provided legal, financial, tax or accounting advice.",
            (f"We authorise {_CO_LEGAL.upper()} to proceed and to settle our existing finance agreement on our behalf, the cost of which is included in our system rental." if is_inhouse else f"We authorise {_CO_LEGAL.upper()} to proceed and authorise {_CO_LEGAL} to receive the settlement payment from the new finance provider."),
        ], 1):
            pdf.set_x(pdf.l_margin); pdf.multi_cell(pdf.epw, 3.8, f"{n}.  {s(ack)}", align="J")
        pdf.ln(2)
        _eca_hdr("Customer Initial Confirmation")
        for item in [
            "I understand the Current Lease Settlement Figure.",
            f"I understand the new agreement is for {LEASE_TERM_LABELS[lease_term]}.",
            "I understand the new monthly payment.",
            ("I understand the settlement cost is included in my system rental." if is_inhouse else "I understand the Total Finance Amount."),
            f"I authorise {_CO_LEGAL.upper()} to settle the existing agreement.",
            "I understand this is my company's commercial decision.",
            ("I understand any settlement amount may change until confirmed by the existing finance provider." if is_inhouse else "I understand any settlement amount may change until confirmed by the finance provider."),
            "I confirm I have authority to enter into this agreement on behalf of the Customer.",
        ]:
            pdf.set_font("Helvetica","",8)
            pdf.set_x(pdf.l_margin)
            # Draw tick box instead of initials/blank
            _bx = pdf.l_margin + 2
            _by = pdf.get_y() + 1
            _bs = 4.5
            pdf.set_draw_color(8, 31, 58)
            pdf.rect(_bx, _by, _bs, _bs)
            pdf.set_draw_color(27, 120, 214)
            pdf.line(_bx + 0.6, _by + 2.2, _bx + 1.7, _by + 3.8)
            pdf.line(_bx + 1.7, _by + 3.8, _bx + 3.9, _by + 0.6)
            pdf.set_draw_color(0, 0, 0)
            pdf.set_x(pdf.l_margin + 10)
            pdf.multi_cell(pdf.epw - 10, 5, s(item))
            pdf.set_x(pdf.l_margin)
        pdf.ln(2)
        _eca_hdr("Final Declaration")
        pdf.set_font("Helvetica","",7.5); pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw,3.8,
            "This document records the exceptional commercial arrangement only and does not amend or replace "
            + ("the terms of the Commercial Proposal or Service Agreement. " if is_inhouse else "the terms of the Commercial Proposal, Service Agreement or Finance Agreement. ")
            + ("We confirm this document, together with the Commercial Proposal and Service Agreement, " if is_inhouse else "We confirm this document, together with the Commercial Proposal, Service Agreement and Finance Agreement, ")
            +
            f"accurately reflects the transaction we have chosen to enter into. We authorise {_CO_LEGAL.upper()} to proceed.", align="J")
        pdf.ln(1)
        _eca_hdr("Signatures")
        pdf.set_font("Helvetica","B",9)
        pdf.cell(0,5,"Customer Signature",ln=True)
        pdf.set_font("Helvetica","",9)
        pdf.cell(80,5,f"Name: {s(_signer or '')}",ln=False)
        pdf.cell(0,5,f"Company: {s(_comp or '')}",ln=True)
        if sig_bytes:
            try:
                import tempfile as _tf2, os as _os2
                with _tf2.NamedTemporaryFile(suffix=".png", delete=False) as _stf:
                    _stf.write(sig_bytes); _stf_path = _stf.name
                try:
                    pdf.image(_stf_path, x=pdf.l_margin, y=pdf.get_y(), h=14)
                finally:
                    _os2.unlink(_stf_path)
                pdf.ln(15)
            except Exception: pdf.cell(0,14,"Signature: ________________",ln=True)
        else:
            pdf.cell(0,14,"Signature: ________________",ln=True)
        pdf.cell(0,5,f"Date: {date.today().strftime('%d/%m/%Y')}",ln=True)
        pdf.set_font("Helvetica","I",7); pdf.set_text_color(128,128,128)
        pdf.multi_cell(pdf.epw,3.5,"I confirm that I am authorised to sign this agreement on behalf of the Customer.",align="C")
        pdf.set_text_color(0,0,0)

    # ── LETTER OF AUTHORITY (only when the consultant has switched it on) ─────────
    _LOA_PAGES.pop("range", None)
    if _loa_data()["on"] and _loa_data()["numbers"]:
        _loa_pages(pdf, _add_header, sig_bytes=sig_bytes, sig_ts=sig_timestamp)

    # ── ON-SITE WARRANTY FORM ─────────────────────────────────────────────────
    if not _maint_optout():      # opted out of maintenance: no On-Site Warranty / maintenance page
        pdf.add_page()
        _add_header(pdf, "On-Site Warranty Agreement")

        # Maintenance monthly charge from P&L: (hw_buy × 1.5 × 0.2) / 12
        _maint_monthly = round(pl_data.get("maintenance_annual", 0) / 12, 2)

        # Customer details
        pdf.set_font("Helvetica","B",10)
        pdf.set_fill_color(8,31,58); pdf.set_text_color(255,255,255)
        pdf.cell(0,6,"  Customer Details",fill=True,ln=True)
        pdf.set_text_color(0,0,0)
        pdf.set_font("Helvetica","",9)
        pdf.set_fill_color(248,249,255)
        def _w_row(lbl, val):
            pdf.cell(60,5,f"  {lbl}:",fill=True,ln=False)
            pdf.cell(0,5,f"  {s(val)}",fill=True,ln=True,border="B")
        _w_row("Customer Name",   _comp or "")
        _w_row("Address",         _addr or "")
        _w_row("Date",            date.today().strftime("%d/%m/%Y"))
        pdf.ln(4)

        # Equipment list
        pdf.set_fill_color(8,31,58); pdf.set_text_color(255,255,255)
        pdf.set_font("Helvetica","B",10)
        pdf.cell(0,6,"  Equipment Covered",fill=True,ln=True)
        pdf.set_text_color(0,0,0)
        pdf.set_font("Helvetica","B",8)
        pdf.set_fill_color(210,218,235)
        pdf.cell(95,5,"  Item",fill=True,ln=False)
        pdf.cell(45,5,"Qty",fill=True,ln=False,align="C")
        pdf.cell(0,5,"Billing",fill=True,ln=True,align="C")
        pdf.set_font("Helvetica","",8)
        # Warranty covers PHYSICAL HARDWARE ONLY. Built from the hardware catalogues
        # directly, so licences, software add-ons (e.g. Wallboard), broadband, mobiles,
        # IT services and Call Scope can never appear here.
        _NON_PHYSICAL = ("call scope", "call answer", "website widget", "my pa",
                         "wallboard", "licence", "license", "setup (one-off)", "air conditioning installation")
        def _is_physical(_n):
            return not any(k in _n.lower() for k in _NON_PHYSICAL)
        warranty_items = []
        for _name, _qty in {**desktop_quantities, **cordless_quantities,
                            **headset_quantities, **other_quantities}.items():
            if _qty > 0 and _is_physical(_name) and _name not in {it["name"] for it, _q in AC["listed"]}:
                warranty_items.append((_name, _qty))
        if auto_switch and not _no_switch:
            warranty_items.append((f"Switch: {rec_switch['name']}", 1))
        if add_router:
            if router_quantities:
                for _rn, _rq in router_quantities.items():
                    warranty_items.append((_rn, _rq))
            elif router_type not in ("None / Customer Supplied", ""):
                warranty_items.append((router_type, 1))
        if not warranty_items:
            pdf.set_font("Helvetica","I",8)
            pdf.cell(0,5,"  No physical hardware on this order.",ln=True)
            pdf.set_font("Helvetica","",8)
        for _name, _qty in warranty_items:
            pdf.set_fill_color(248,249,255)
            pdf.cell(95,5,f"  {s(_name)}",fill=True,ln=False)
            pdf.cell(45,5,str(_qty),fill=True,ln=False,align="C")
            pdf.cell(0,5,s(_pdf_hw_billing),fill=True,ln=True,align="C")
        pdf.ln(4)

        # Warranty terms
        pdf.set_fill_color(8,31,58); pdf.set_text_color(255,255,255)
        pdf.set_font("Helvetica","B",10)
        pdf.cell(0,6,"  Warranty Terms",fill=True,ln=True)
        pdf.set_text_color(0,0,0); pdf.set_font("Helvetica","",8.5)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw,4,
            f"{_CO_LEGAL} agrees to provide on-site warranty cover including remote diagnostics "
            f"and programming of faults to the equipment listed above for an agreement term of "
            f"{LEASE_TERM_LABELS[lease_term]}. "
            f"Faulty equipment will be repaired or replaced. Additional equipment added will be "
            f"charged and warranty premium will be added to this agreement.",align="J")
        pdf.ln(2)

        # Inclusive period + monthly charge highlight
        pdf.set_fill_color(27,120,214); pdf.set_text_color(255,255,255)
        pdf.set_font("Helvetica","B",9)
        pdf.cell(0,7,f"  Inclusive Period: 12 months  |  Monthly charge after inclusive period: £{_maint_monthly:.2f} + VAT",
                 fill=True,ln=True,align="C")
        pdf.set_text_color(0,0,0)
        pdf.ln(2)

        # Tier level
        pdf.set_font("Helvetica","B",9)
        pdf.cell(0,5,"Tier 1 Support Includes:",ln=True)
        pdf.set_font("Helvetica","",8.5)
        pdf.cell(0,5,"  [X]  Remote diagnostics and programming",ln=True)
        pdf.cell(0,5,"  [X]  Engineer call-outs for repair or replacement of equipment",ln=True)
        pdf.set_font("Helvetica","I",8)
        pdf.set_text_color(120,120,120)
        pdf.cell(0,5,"  Note: Excludes additional equipment added to the system in future.",ln=True)
        pdf.set_text_color(0,0,0)
        pdf.ln(3)

        # Declaration
        pdf.set_fill_color(8,31,58); pdf.set_text_color(255,255,255)
        pdf.set_font("Helvetica","B",10)
        pdf.cell(0,6,"  Declaration",fill=True,ln=True)
        pdf.set_text_color(0,0,0)
        pdf.set_font("Helvetica","",8)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw,4,
            f"{_CO_LEGAL} agrees to provide remote and on-site maintenance cover for the equipment above "
            "at the tier level set out above and the customer agrees to pay the monthly charge as set out "
            "above for the Agreement Term, subject to the terms and conditions. As a duly authorised "
            "representative of the customer, I confirm that I have read, understood and accept the terms "
            "and conditions of this agreement.",align="J")
        pdf.ln(4)

        # Signature
        pdf.set_font("Helvetica","B",9)
        pdf.cell(0,5,"On Behalf of (The Customer):",ln=True)
        pdf.set_font("Helvetica","",9)
        pdf.cell(80,5,f"Name & Position: {s(_signer or '')}",ln=False)
        pdf.cell(0,5,f"Date: {date.today().strftime('%d/%m/%Y')}",ln=True)
        if sig_bytes:
            try:
                import tempfile as _tf2, os as _os2
                with _tf2.NamedTemporaryFile(suffix=".png", delete=False) as _stf:
                    _stf.write(sig_bytes); _stf_path = _stf.name
                try:
                    pdf.image(_stf_path, x=pdf.l_margin, y=pdf.get_y(), h=14)
                finally:
                    _os2.unlink(_stf_path)
                pdf.ln(16)
            except Exception:
                pdf.cell(0,14,"Signed: ________________",ln=True)
        else:
            pdf.cell(0,14,"Signed: ________________",ln=True)
        pdf.ln(2)
        pdf.set_font("Helvetica","I",7.5); pdf.set_text_color(80,80,80)
        pdf.cell(0,4,"Annual price review applies after inclusive period. Subject to standard Terms & Conditions.",ln=True,align="C")
        pdf.set_text_color(0,0,0)


    # ── CUSTOMER REQUIREMENT FORM ────────────────────────────────────────────
    pdf.add_page()
    # Header
    pdf.set_font("Helvetica","B",11)
    pdf.cell(0,5,"CUSTOMER REQUIREMENT FORM",ln=True,align="C")
    pdf.ln(1)
    pdf.set_font("Helvetica","",8)
    pdf.set_text_color(100,100,100)
    pdf.multi_cell(0,4,f"{_CO_LEGAL} are committed to the very highest levels of customer care. This Questionnaire "
        "is essential for our understanding of your needs and therefore satisfaction with our services.",align="C")
    pdf.set_text_color(0,0,0)
    pdf.ln(2)

    # Helper functions
    def _crf_tick(checked=False):
        return "[X]" if checked else "[ ]"

    def _crf_q(num, text, has_yn=False, yn=None, extra=""):
        pdf.set_font("Helvetica","B",8)
        pdf.set_fill_color(245,247,255)
        pdf.cell(8,5,str(num),fill=True,ln=False)
        pdf.set_font("Helvetica","",7.5)
        pdf.set_x(pdf.l_margin+8)
        if has_yn:
            _yn_start_y = pdf.get_y()
            pdf.multi_cell(pdf.epw-28,3.5,s(text))
            _yn_end_y = pdf.get_y()
            # Place Yes/No at the top-right aligned with question start
            pdf.set_xy(pdf.w - pdf.r_margin - 26, _yn_start_y)
            pdf.cell(13,3.5,f"Yes {_crf_tick(yn==True)}",ln=False,align="C")
            pdf.cell(13,3.5,f"No  {_crf_tick(yn==False)}",ln=False,align="C")
            pdf.set_y(_yn_end_y)
        else:
            pdf.multi_cell(pdf.epw-8,4,s(text))
        if extra:
            pdf.set_x(pdf.l_margin+8)
            pdf.set_font("Helvetica","I",7)
            pdf.set_text_color(120,120,120)
            pdf.multi_cell(pdf.epw-8,3.8,s(extra))
            pdf.set_text_color(0,0,0)
        pdf.ln(1)

    # Y/N header
    pdf.set_font("Helvetica","",7.5)
    pdf.ln(1)

    _bb_desc = f"{bb_provider} {bb_package}" if svc["bb_sell"]>0 else "None / Customer Supplied"
    _vc_desc = str(total_voice_channels)

    _crf_q(1,"I currently have a PDQ line that connects to a Bank or Post office. (Yes / No)")
    _crf_q(2,"I currently have a Redcare, or similar alarm system connected to a telephone line. "
             "I understand that liaison with the alarm company is my responsibility. (Yes / No)",
             extra="If alarm works via the main system lines then a new standalone line may need to be added.")
    _crf_q(3,f"This agreement includes: {_vc_desc} voice channels and {_bb_desc} broadband service(s) as agreed. "
             "Additional services will be added at our standard tariffs.")
    _crf_q(4,f"I can confirm that I currently have {num_employees or '______'} employees")
    _crf_q(5,f"{_CO_LEGAL} are unable to make any representations to any carrier or service provider on our behalf. "
             f"I appreciate that {_CO_LEGAL} can provide advice, but understand that any correspondence with current providers is ultimately our responsibility.")
    _crf_q(6,"I am aware that there may be a delay in switching chosen carrier after installation has taken place "
             "and that calls during this period may be routed through your existing provider.")
    _crf_q(7,"I understand that in the event that our telephone numbers do not exist within the BT network, "
             f"{_CO_LEGAL} cannot guarantee that they will be ported to the {_CO_LEGAL} Network.")
    _crf_q(8,"I am aware that the engineer will conduct a physical line check on site to help identify all available lines "
             "coming into the premises. It is ultimately my responsibility to ensure all lines are accounted for.")
    if termination_cost > 0:
        _crf_q(9,f"We acknowledge that in entering into the above agreement you have agreed to not only rent new equipment "
                 f"supplied by {_CO_LEGAL}, but also settlement of an existing agreement to the maximum sum of: "
                 f"£{termination_cost:.2f} as per the figure agreed on the order forms.")
    else:
        _crf_q(9,"We acknowledge that in entering into the above agreement you have agreed to rent new equipment "
                 f"supplied by {_CO_LEGAL} as per the figure agreed on the order forms.")
    _crf_q(10,"I have confirmed the number of months remaining on existing contracts to the sales consultant")
    _crf_q(11,"I understand that only the settlement for ETC charges agreed & listed on the order forms will be paid "
             f"by {_CO_LEGAL} upon receipt of a copy invoice & contract from the previous supplier")
    _crf_q(12,f"I understand that any 'Special Conditions' agreed by {_CO_LEGAL} representative may not be considered "
             f"valid by {_CO_LEGAL} unless stated on the Order Form and clearly initialled by their representative.")
    _crf_q(13,"I understand that UK Local, UK National and UK Mobile call costs only have been accounted for on my "
             f"call cost proposal with {_CO_LEGAL}")
    _crf_q(14,f"I understand that if I do not take {_CO_LEGAL} mobiles after my current contract ends "
             f"{_CO_LEGAL} cannot guarantee the mobile savings.")
    _crf_q(15,"I agree that the rentals due under the Rental Agreement have been calculated based on the full purchase "
             "price of the Equipment. We agree and accept that our obligation to pay the Rentals in full on their due "
             "dates without reduction, deduction, withholding, or offset whatsoever, shall apply notwithstanding any "
             "failure on the part of the Supplier or the Equipment.")
    if _maint_optout():
        _crf_q(16,f"I understand that I have chosen not to take a maintenance agreement with {_CO_LEGAL}. I remain responsible for "
                 "keeping the Equipment maintained and for complying with all obligations under the Rental Agreement.")
    else:
        _crf_q(16,f"I fully understand that {_CO_LEGAL} will be and will at all times remain solely responsible for "
                 "providing any maintenance or service provision in respect of the Equipment in a separate agreement. "
                 "We are fully aware that if the Supplier stops providing maintenance for any reason we must fully "
                 "comply with all obligations under the Rental Agreement to keep the Equipment maintained.")
    _crf_q(17,f"I understand that due to the data protection act, {_CO_LEGAL} have no authority to cancel any "
             "existing agreements with 3rd party suppliers. I am aware that (where applicable) it is my responsibility "
             "to cancel any existing agreements.")
    _crf_q(18,"Any settlement charges other than those on the Order Form can only be settled with supporting contracts "
             f"from existing providers which must be provided to {_CO_LEGAL} on request.")
    _crf_q(19,f"I understand that due to current trading climate {_CO_LEGAL} may require supportive additional "
             "financial information prior to installation.")
    _crf_q(20,f"I have provided a copy of bills relevant to the new services to be provided by {_CO_LEGAL}.")
    _crf_q(21,"I am fully aware that the CTI (screen popping) may not fully integrate with my current database "
             "and that screen popping may not be possible.")

    # Received forms checklist
    pdf.ln(2)
    pdf.set_font("Helvetica","I",8)
    pdf.multi_cell(0,4,"I have been explained in detail the following forms and am in receipt of copies for: (tick as appropriate)",align="L")
    pdf.ln(1)
    _forms = [
        ("This Form","[X]"),("Order Form","[X]"),("Terms & Conditions","[X]"),
        ("Quotation - inc. tariff","[X]"),("Rental Document","[X]"),("Network Service Agreement","[X]"),
        ("On Site Maintenance Agreement","[X]"),
    ]
    if _maint_optout():
        _forms = [f for f in _forms if "Maintenance" not in f[0]]
    pdf.set_font("Helvetica","",8)
    _fc = st.columns if False else None  # PDF only - use cells
    for i in range(0,len(_forms),3):
        for label,tick in _forms[i:i+3]:
            pdf.cell(65,5,f"{tick}  {label}",ln=False)
        pdf.ln(5)

    # Declaration & signature
    pdf.ln(3)
    pdf.set_font("Helvetica","",8)
    pdf.multi_cell(0,4,"I declare that, to the best of my knowledge, the above statements are true.",align="L")
    pdf.ln(3)
    pdf.set_font("Helvetica","B",9)
    pdf.cell(0,5,"For & on Behalf of (The Customer)",ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica","",9)
    pdf.cell(90,5,f"Name & Position: {s(_signer or '')} {s(_btype or '')}",ln=False)
    pdf.cell(0,5,f"Date: {date.today().strftime('%d/%m/%Y')}",ln=True)
    if sig_bytes:
        try:
            import tempfile as _tf2, os as _os2
            with _tf2.NamedTemporaryFile(suffix=".png", delete=False) as _stf:
                _stf.write(sig_bytes); _stf_path = _stf.name
            try:
                pdf.image(_stf_path, x=pdf.l_margin, y=pdf.get_y(), h=14)
            finally:
                _os2.unlink(_stf_path)
            pdf.ln(16)
        except Exception:
            pdf.cell(0,14,"Signed: ________________",ln=True)
    else:
        pdf.cell(0,14,"Signed: ________________",ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica","I",7.5)
    pdf.set_text_color(80,80,80)
    pdf.multi_cell(0,3.8,s(f"{_CO_LEGAL} confirm that any financial information given will be treated with utmost confidentiality."),align="C")
    pdf.set_text_color(0,0,0)

    # ── ANNUAL PRICE REVIEW PAGE (price increase shown in pounds and pence) ───────
    _pr_b, _pr_i, _pr_n, _pr_p, _pr_y = price_rise_figures()
    if _pr_p > 0 and _pr_b > 0:
        pdf.add_page()
        _add_header(pdf, "Annual Price Review")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 4.8, s(
            "Your monthly service charges are reviewed once a year. So that there are no surprises, this page sets out in "
            "pounds and pence exactly what the increase will be, for every year of your agreement."))
        pdf.ln(3)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(60, 6.5, "  Period", fill=True, ln=False)
        pdf.cell(65, 6.5, "Monthly services (excl. VAT)", fill=True, ln=False, align="C")
        pdf.cell(65, 6.5, "Increase from previous year", fill=True, ln=True, align="C")
        pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 9)
        _pr_years = max(1, min(8, -(-int(lease_term) // 12)))
        _pr_prev = None
        for _yi in range(_pr_years):
            _pr_amt = round(_pr_b * ((1 + _pr_p / 100.0) ** _yi), 2)
            pdf.set_fill_color(*((248, 249, 255) if _yi % 2 == 0 else (255, 255, 255)))
            _lbl = "Year 1 (from your start date)" if _yi == 0 else f"Year {_yi + 1} (from anniversary {_yi})"
            pdf.cell(60, 6.5, "  " + _lbl, fill=True, ln=False)
            pdf.cell(65, 6.5, f"£{_pr_amt:,.2f} per month", fill=True, ln=False, align="C")
            pdf.cell(65, 6.5, "-" if _pr_prev is None else f"+ £{_pr_amt - _pr_prev:,.2f} per month", fill=True, ln=True, align="C")
            _pr_prev = _pr_amt
        pdf.ln(4)
        pdf.set_fill_color(27, 120, 214); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 9)
        pdf.cell(190, 7, s(f"  Your first increase: + £{_pr_i:,.2f} per month ({_pr_p:g}%), taking your monthly services to £{_pr_n:,.2f} (excl. VAT)"),
                 fill=True, ln=True)
        pdf.set_text_color(0, 0, 0); pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9); pdf.cell(0, 6, "How it works", ln=True)
        pdf.set_font("Helvetica", "", 8.5)
        _pr_pts = [
            f"The increase is {_pr_p:g}% of your monthly service charges and is applied once a year, on each anniversary of your start date.",
            "We will confirm the new monthly amount in writing at least 30 days before it takes effect.",
            "It applies to your monthly service charges only (user licences, broadband and add-on services)."
            + ((" System rental does not change." if is_inhouse else " Hardware rental under your lease agreement does not change.") if is_spread else ""),
            "All amounts exclude VAT, which is charged at the prevailing rate.",
        ]
        for _pt in _pr_pts:
            pdf.set_x(pdf.l_margin); pdf.cell(5, 4.6, "-")
            pdf.multi_cell(pdf.epw - 5, 4.6, s(_pt)); pdf.ln(0.8)
        pdf.ln(4)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 8)
        pdf.cell(0, 6, "  Acknowledgement - I have read and understood the Annual Price Review", fill=True, ln=True)
        pdf.set_text_color(0, 0, 0); pdf.ln(3); pdf.set_font("Helvetica", "", 8)
        _pr_half = pdf.epw / 2
        _pr_parts = [x.strip() for x in (sig_name or _contact or "").split(" - ", 1)]
        _pr_name = s(_pr_parts[0]) if _pr_parts[0] else "________________________"
        _pr_pos  = s(_pr_parts[1]) if len(_pr_parts) > 1 else "________________________"
        pdf.cell(_pr_half, 5.5, f"Name:     {_pr_name}", ln=False)
        pdf.cell(_pr_half, 5.5, f"Company:  {s(_comp or '________________________')}", ln=True)
        pdf.ln(1)
        pdf.cell(_pr_half, 5.5, f"Date:     {date.today().strftime('%d/%m/%Y')}", ln=False)
        pdf.cell(_pr_half, 5.5, f"Position / Title:  {_pr_pos}", ln=True)
        pdf.ln(4)
        pdf.cell(40, 5, "Signature:", ln=False)
        if sig_bytes:
            try:
                import tempfile as _tf_pr, os as _os_pr
                with _tf_pr.NamedTemporaryFile(suffix=".png", delete=False) as _spr:
                    _spr.write(sig_bytes); _spr_path = _spr.name
                try:
                    pdf.image(_spr_path, x=pdf.get_x(), y=pdf.get_y() - 1, h=12)
                finally:
                    _os_pr.unlink(_spr_path)
                pdf.ln(14)
            except Exception:
                pdf.cell(0, 14, "________________________________", ln=True)
        else:
            pdf.cell(0, 14, "________________________________", ln=True)
        pdf.set_text_color(0, 0, 0)

    # ── TERMS & CONDITIONS PAGE ──────────────────────────────────────
    pdf.add_page()
    _add_header(pdf, "Terms & Conditions - Network Services")

    _tc_sections = [
        ("1. DEFINITIONS", f"Contract means these terms and the Order. Charges are payable under clause 10. Initial Term means 12 months from Start Date. Extended Term means any 12-month renewal per clause 3. We/us means {_CO_LEGAL}. You means the customer in the Order."),
        ("3. DURATION & AUTOMATIC RENEWAL", "This contract automatically extends for 12 months at the end of the Minimum Term and each Extended Term unless 90 days written notice is given. You may add Services at any time."),
        ("4. SERVICES", "We provide Services with reasonable skill and care. We do not warrant uninterrupted or error-free service. Service Failures must be reported via our Helpdesk."),
        ("6. USE OF SERVICES", "Services are for business use only and must comply with our Acceptable Use Policy. You must not use Services to breach any law, compromise network security, or degrade service to other customers."),
        ("10. CHARGES AND PAYMENT", "All Charges exclude VAT. Invoices due within 14 days. Late payment fee £25 after 7 days. DD cancellation fee £50. Monthly service charges are reviewed once a year - see the Annual Price Review page. Rental invoiced in advance; calls in arrears. Port/activation: £25+VAT per CLI. Engineer callout: min £250+VAT. Remote changes: £35+VAT. Call recording: included 12 months then £20/month+VAT."),
        ("12. LIABILITY", "No liability for loss of profits, business opportunity, goodwill or indirect loss. Total liability capped at Charges paid in prior 12 months. Nothing limits liability for death or fraud."),
        ("13. CANCELLATION", "90 days notice required. Cancellation during term incurs Cancellation Charge. Introductory credits repayable on early exit. Subsidised early termination charges repayable pro-rata."),
        ("15. TERMINATION FEES", "On termination all invoices become immediately due; Equipment must be returned. Cancellation fee: £299+VAT per CLI. Port-away: £15+VAT per number. Account closure: £250+VAT. We may terminate for non-payment (7+ days), unremedied breach, or insolvency."),
        ("16. CONFIDENTIALITY", "Each party protects the other's confidential information with reasonable care for 3 years."),
        ("20. GENERAL", "This Contract is the whole agreement between us, governed by English law. We may vary terms on notice. You may not assign without our prior written consent. Subject to the exclusive jurisdiction of the English courts."),
    ]
    for _sec_title, _sec_text in _tc_sections:
        pdf.ln(2)
        pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(0, 5, f"  {_sec_title}", fill=True, ln=True)
        pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 7)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 3.8, s(_sec_text), align="J")
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 6.5); pdf.set_text_color(128, 128, 128)
    pdf.multi_cell(pdf.epw, 3.5,
        "This is a summary of key terms. Full Terms & Conditions available at https://southwalestelecoms.co.uk "
        "- by signing below you confirm you have read, understood and agree to the full Terms & Conditions at the link above.",
        align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    # ── T&C Confirmation Signature ────────────────────────────────────────────
    pdf.set_fill_color(8, 31, 58); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 6, "  Confirmation - I have read and agree to the full Terms & Conditions", fill=True, ln=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(3)
    pdf.set_font("Helvetica", "", 8)
    _tc_half = pdf.epw / 2
    # Split "Name - Position" from the contact field
    _tc_contact_raw = sig_name or _contact or ""
    _tc_parts   = [p.strip() for p in _tc_contact_raw.split(" - ", 1)]
    _tc_name    = s(_tc_parts[0]) if _tc_parts[0] else "________________________"
    _tc_pos     = s(_tc_parts[1]) if len(_tc_parts) > 1 else "________________________"
    # Row 1: Name + Company
    pdf.cell(_tc_half, 5.5, f"Name:     {_tc_name}", ln=False)
    pdf.cell(_tc_half, 5.5, f"Company:  {s(_comp or '________________________')}", ln=True)
    pdf.ln(1)
    # Row 2: Date (pre-filled) + Position/Title (split from contact field)
    pdf.cell(_tc_half, 5.5, f"Date:     {date.today().strftime('%d/%m/%Y')}", ln=False)
    pdf.cell(_tc_half, 5.5, f"Position / Title:  {_tc_pos}", ln=True)
    pdf.ln(4)
    # Signature row — stamp if captured, else blank line
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(40, 5, "Signature:", ln=False)
    if sig_bytes:
        try:
            import tempfile as _tf_tc, os as _os_tc
            with _tf_tc.NamedTemporaryFile(suffix=".png", delete=False) as _stc:
                _stc.write(sig_bytes); _stc_path = _stc.name
            try:
                pdf.image(_stc_path, x=pdf.get_x(), y=pdf.get_y() - 1, h=12)
            finally:
                _os_tc.unlink(_stc_path)
            pdf.ln(14)
        except Exception:
            pdf.cell(0, 14, "________________________________", ln=True)
    else:
        pdf.cell(0, 14, "________________________________", ln=True)
    pdf.set_text_color(0, 0, 0)

    # ── AUDIT CERTIFICATE PAGE - DocuSign-style ─────────────────────────────
    if sig_bytes and sig_timestamp:
        import uuid as _uuid, hashlib as _hl
        from datetime import datetime as _dt

        _envelope_id = str(_uuid.uuid4()).upper()
        _doc_hash    = _hl.sha256(sig_bytes).hexdigest().upper()
        _signed_at   = sig_timestamp
        _sent_at     = _signed_at  # same session
        _signer_name = sig_name or "Customer"
        _signer_co   = sig_company or _comp or "-"
        _signer_email= _demail or _bemail or "-"
        _signer_ip   = sig_ip or "Not captured"
        _orig_email  = cfg.get("email", {}).get("username", "") or _BRAND.get("email", "")

        # ── Helper functions ──────────────────────────────────────────────────
        def _section(title):
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_fill_color(220, 235, 245)
            pdf.set_text_color(13, 46, 74)
            pdf.cell(0, 6, f"  {title}", fill=True, ln=True)
            pdf.set_text_color(0, 0, 0)

        def _row3(c1, c2, c3, h=5.5, bold1=False):
            """Three-column table row."""
            pdf.set_font("Helvetica", "B" if bold1 else "", 8)
            pdf.cell(65, h, c1, border="B", ln=False)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(65, h, c2, border="B", ln=False)
            pdf.cell(0,  h, c3, border="B", ln=True)

        def _kv(label, value, lw=52):
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(lw, 5.5, label, ln=False)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 5.5, str(value), ln=True)

        pdf.add_page()

        # ── Page header (light - no logo for certificate page) ────────────────
        pdf.set_fill_color(8, 31, 58)
        pdf.rect(0, 0, 210, 22, "F")
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(255, 255, 255)
        pdf.set_y(5)
        pdf.cell(0, 6, "CERTIFICATE OF COMPLETION", ln=True, align="C")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, s(f"{_CO}  |  Electronic Signing Record"), ln=True, align="C")
        pdf.set_fill_color(0, 180, 216)
        pdf.rect(0, 22, 210, 1.5, "F")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(8)

        # ── Envelope summary grid ─────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(13, 46, 74)
        lx = pdf.l_margin
        pdf.cell(0, 6, "Envelope Summary", ln=True)
        pdf.set_draw_color(0, 180, 216)
        pdf.set_line_width(0.4)
        pdf.line(lx, pdf.get_y(), 195, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.set_draw_color(200, 200, 200)
        pdf.ln(2)

        def _env_row(l, v, color=(0,0,0)):
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(52, 5.5, l, ln=False)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*color)
            pdf.cell(0, 5.5, str(v)[:70], ln=True)
            pdf.set_text_color(0, 0, 0)

        _env_row("Envelope ID:", _envelope_id)
        _env_row("Status:", "COMPLETED", color=(0, 140, 70))
        _env_row("Subject:", s(f"{_CO} Proposal - {_signer_co[:40]}"))
        _env_row("Originator:", s(_CO))
        _env_row("Document Pages:", "4   |   Signatures: 3")
        _env_row("Time Zone:", "(UTC+00:00) Dublin, Edinburgh, Lisbon, London")
        _env_row("Originator Email:", _orig_email)
        pdf.ln(4)

        # ── Record Tracking ───────────────────────────────────────────────────
        _section("Record Tracking")
        pdf.ln(1)
        _row3("Status", "Holder", "Location", bold1=True)
        _row3("Original", s(_CO), s(_CO_TAG))
        _row3(_sent_at, _orig_email, "Streamlit Cloud")
        pdf.ln(4)

        # ── Signer Events ─────────────────────────────────────────────────────
        _section("Signer Events")
        pdf.ln(1)
        _row3("Signer Details", "Signature", "Timestamps", bold1=True)

        # Left: signer info
        y_row = pdf.get_y()
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(65, 5, _signer_name, ln=False)
        pdf.set_font("Helvetica", "", 8)
        # Middle: signature image
        if sig_bytes:
            try:
                import tempfile as _tf3, os as _os3
                with _tf3.NamedTemporaryFile(suffix=".png",delete=False) as _atf:
                    _atf.write(sig_bytes); _atf_path=_atf.name
                _s_buf2 = open(_atf_path,"rb")
                pdf.image(_s_buf2, x=lx + 67, y=y_row, w=60, h=18)
            except Exception:
                pass
        # Right: timestamps
        pdf.set_xy(lx + 135, y_row)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.cell(0, 5, f"Sent:   {_sent_at}", ln=True)
        pdf.set_xy(lx + 135, y_row + 5)
        pdf.cell(0, 5, f"Viewed: {_sent_at}", ln=True)
        pdf.set_xy(lx + 135, y_row + 10)
        pdf.cell(0, 5, f"Signed: {_signed_at}", ln=True)

        pdf.set_y(y_row + 5.5)        # below the signer's name (was overlapping the email)
        pdf.set_x(lx)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(65, 5, _signer_email, ln=True)
        pdf.set_x(lx)
        pdf.cell(65, 5, _signer_co, ln=True)
        pdf.set_x(lx)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(65, 5, "Security: In-person, Device", ln=True)
        pdf.set_x(lx)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.cell(65, 5, f"Using IP: {_signer_ip}", ln=True)
        pdf.set_x(lx)
        pdf.cell(65, 5, "Signature Adoption: Hand-drawn (in person)", ln=True)
        pdf.ln(2)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(lx, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(4)

        # ── Carbon Copy Events ────────────────────────────────────────────────
        _section("Carbon Copy Events")
        pdf.ln(1)
        _row3("Recipient", "Status", "Timestamps", bold1=True)
        _row3(_orig_email, "COPIED", f"Sent: {_sent_at}")
        pdf.ln(4)

        # ── Envelope Summary Events ───────────────────────────────────────────
        _section("Envelope Summary Events")
        pdf.ln(1)
        _row3("Event", "Status", "Timestamp", bold1=True)
        _row3("Envelope Sent",      "Hashed / Encrypted",   _sent_at)
        _row3("Certified Delivered","Security Checked",      _sent_at)
        _row3("Signing Complete",   "Security Checked",      _signed_at)
        _row3("Completed",          "Security Checked",      _signed_at)
        pdf.ln(4)

        # ── Document Integrity ────────────────────────────────────────────────
        _section("Document Integrity")
        pdf.ln(2)
        _kv("Document Hash (SHA-256):", _doc_hash[:40])
        _kv("Signing Method:",          "In-person electronic signature")
        _kv("Platform:",                "South Wales Comms Pricebook - Streamlit Cloud")
        _kv("Full Envelope ID:",        _envelope_id)
        pdf.ln(4)

        # ── Disclaimer ────────────────────────────────────────────────────────
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(120, 120, 120)
        pdf.set_x(lx)
        pdf.multi_cell(pdf.epw, 4,
            "This certificate serves as an electronic record confirming that the above-named "
            "signer reviewed and signed the attached documentation. The timestamp, IP address and "
            "signature were recorded at the moment of signing by the South Wales Comms Quotation "
            "Tool. This record constitutes a valid electronic agreement under the Electronic "
            "Communications Act 2000 and eIDAS Regulation (EU) 910/2014."
        )


    return bytes(pdf.output())


def _embed_sig(pdf_obj, sig_bytes, x=15, w=65, h=20,
               signer_name="", company="", timestamp=""):
    """Render signature + metadata in the LEFT customer column only.
    Layout:
      [image if available]
      Signed: Name | Company | Date  (italic, left-aligned, below image)
    Then the signature underline is drawn by the caller.
    """
    if not (sig_bytes or signer_name):
        return
    try:
        y_start = pdf_obj.get_y()
        if sig_bytes and len(sig_bytes) > 100:  # skip placeholder/corrupt bytes
            try:
                import tempfile, os as _os
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _tf:
                    _tf.write(sig_bytes)
                    _tmp_sig_path = _tf.name
                try:
                    pdf_obj.image(_tmp_sig_path, x=x, y=y_start, w=w, h=h)
                    pdf_obj.set_y(y_start + h + 1)
                finally:
                    _os.unlink(_tmp_sig_path)
            except Exception:
                pass  # image unreadable - skip, show name only

        # Metadata - always in left column (x=15), max 90mm wide
        pdf_obj.set_font("Helvetica", "I", 8)
        pdf_obj.set_text_color(80, 80, 80)
        for line in [
            f"Signed: {signer_name}",
            f"Company: {company}",
            f"Date/Time: {timestamp}",
        ]:
            if line.split(": ", 1)[1]:          # only print if value exists
                pdf_obj.set_x(x)
                pdf_obj.cell(90, 5, line, ln=True)
        pdf_obj.set_text_color(0, 0, 0)
        pdf_obj.ln(2)
    except Exception:
        pass



# ─── CALL SCOPE PAPERWORK (own branding, price schedule, editable Terms & Conditions) ─────────────────────
_CS_BRAND_DEFAULT = {
    "trading": "Call Scope", "byline": "", "legal": "Call Scope Ltd",
    "address": "10 Plas Melin, Westbourne Road, Whitchurch, Cardiff CF14 2BT",
    "email": "hello@callscope.co.uk", "phone": "",
    "website": "callscope.co.uk", "accent": "#7870E8", "navy": "#101938",
    "tag": "Every conversation. More intelligence.", "logo_b64": "",
}

_CS_TERMS_DEFAULT = """## 1. ABOUT THESE TERMS
These terms apply to the {BRAND} services listed on your Call Scope Service Order (the Services), which {PROVIDER} ("we", "us") provides to the customer named on the Order ("you"). They sit alongside your main agreement with us for telephony and connectivity services. If the two conflict about the Services, these terms apply to the Services. Nothing here changes your signed main agreement in any other respect.

"Order" means the Call Scope services and prices shown in the order paperwork you sign with us. "Minimum Term" means the term shown on the Order, starting on the date the Services are first made available to you (the Start Date). "Charges" means the prices on the Order as they change under clause 11. "Customer Content" means call recordings, transcripts, text and other data that you or your users put into, or create using, the Services.

## 2. THE SERVICES
{BRAND} is a cloud-based call intelligence service. Depending on the modules on your Order it can transcribe, summarise and score calls, answer calls with an AI receptionist, connect to your CRM and portal, and report on call activity. We provide the Services with reasonable skill and care. We do not promise that they will be uninterrupted or error-free. We may carry out maintenance, updates and improvements, and will give notice of planned work that is likely to affect you where we reasonably can.

## 3. YOUR ACCOUNT AND USERS
The Services are for business use. You must give us accurate information, keep login details secure, and you are responsible for everything done under your accounts. Accounts and modules are for the users and modules on your Order and must not be shared between people to avoid paying for extra users. Tell us promptly if you think an account has been compromised. You may add users or modules at any time; they are charged at the prices then applying and run to the end of the Minimum Term.

## 4. AI OUTPUT
Parts of the Services use artificial intelligence, including language models and speech recognition supplied by third parties. AI output (transcripts, summaries, scores, classifications, suggestions and automated call handling) can contain mistakes, omissions or inappropriate content, and can differ from one run to the next. You must review AI output before relying on it. It is not legal, financial, HR, medical or other professional advice. Do not use output on its own to make decisions about a person (for example disciplinary, employment or credit decisions) without meaningful human review. We give no warranty that output is accurate, complete or fit for any particular purpose.

## 5. RECORDING, CONSENT AND LAWFUL USE
You are responsible for making sure that recording, transcribing and analysing calls is lawful. In the UK this includes the Investigatory Powers Act 2000, the Telecommunications (Lawful Business Practice) (Interception of Communications) Regulations 2000, the UK GDPR and the Data Protection Act 2018. You must have a lawful basis, tell callers and staff that calls are recorded and analysed (including by AI) and why, and keep your own privacy notices up to date. We do not decide what you record. If you use the Services for calls with people outside the UK, you are responsible for complying with local consent laws.

## 6. DATA PROTECTION
For personal data in Customer Content you are the controller and we are your processor. We will: (a) process it only on your documented instructions (these terms, the Order and your use of the Services are your instructions); (b) make sure anyone we allow to access it is bound by confidentiality; (c) keep appropriate technical and organisational security measures; (d) use sub-processors (such as hosting and AI providers) only under written terms giving the same level of protection, and give you a list on request and notice of significant changes, with a right to object; (e) help you respond to data subject requests and meet your security, impact assessment and breach obligations; (f) tell you without undue delay after becoming aware of a personal data breach affecting your data; (g) not transfer personal data outside the UK without lawful safeguards, such as an adequacy decision or approved contractual clauses; (h) provide the information reasonably needed to show compliance and allow reasonable audits on notice, no more than once a year unless a regulator requires otherwise; and (i) when the Services end, let you export your Customer Content for 30 days and then delete it, unless the law requires us to keep it. Further detail of the processing (subject matter, duration, types of data and data subjects) is in our data processing schedule, available from {EMAIL}.

## 7. YOUR CONTENT AND OUR RIGHTS
You own your Customer Content. You give us a limited licence to use it only as needed to provide, secure and support the Services to you. We will not sell it or use it to train our own AI models, and we require our AI providers to process it only to deliver the Services. We own or license the platform, software, prompts, scoring methods, designs and documentation, and you must not copy or reverse engineer them. We may use anonymised usage statistics that do not identify you or any individual to run and improve the Services.

## 8. ACCEPTABLE USE
You must not use the Services: unlawfully (including to record calls without a lawful basis); to upload malware or harmful or infringing content; to reverse engineer, scrape or extract source code, prompts or models; to resell, sublicense or give access to others without our written consent; for bulk, automated or excessive use beyond normal business use for your own calls, including training your own AI models on the output; or to get around limits, minute bundles or security. Minute bundles are for your own call volumes. We may suspend access to stop a breach of this clause and will tell you as soon as reasonably possible.

## 9. THIRD PARTY SERVICES
The Services connect to services we do not control, such as telephony platforms, CRMs, AI and speech providers and hosting. We are not responsible for outages, changes or behaviour of those services, but we will use reasonable efforts to restore affected integrations promptly.

## 10. CHARGES AND PAYMENT
All Charges exclude VAT. Monthly Charges are invoiced monthly in advance and are due within 14 days of the invoice date. A late payment fee of GBP 25 applies if an invoice is more than 7 days overdue, in line with your main agreement. One-off set-up charges are shown separately on the Order. Where a module includes a minutes bundle, usage above the bundle is charged at our standard per-minute rate then in force, which we will confirm on request. Unused minutes do not carry over.

## 11. PRICES AND PRICE CHANGES
The Charges for the Services are fixed for the first 12 months from the Start Date. {PROVIDER} sets its own prices for the Services, independently of the prices of any other products or services you buy from us or from any other company. After the first 12 months we may increase the Charges for the Services, including by reducing or removing any introductory discount, at our own discretion and on at least 30 days' written notice. Any increase we make under this clause is separate from, and may be in addition to, any annual price review of other services under your main agreement. If you add or remove users or modules, the Charges change accordingly.

## 12. TERM, RENEWAL AND CANCELLATION
The Services start on the Start Date and continue for the Minimum Term of {TERM}. At the end of the Minimum Term, and of each renewal, they renew automatically for 12 months unless either party gives at least 90 days' written notice to end them at the end of the then-current term. If you cancel during the Minimum Term (other than because of our material breach that we have not fixed), the Charges for the rest of the Minimum Term, at the Charges then applying, become payable.

## 13. SUSPENSION AND TERMINATION
We may suspend or end the Services if an invoice stays unpaid 7 days after we notify you, if you breach clause 5 or 8, or if you become insolvent. Either party may end the Services if the other commits a material breach and does not fix it within 30 days of notice. When the Services end, your access stops, unpaid Charges become due, and clause 6(i) applies to your data. Clauses that by their nature should continue (including 4, 5, 7 and 14 to 17) do so.

## 14. WARRANTIES AND LIABILITY
Except as set out here, the Services are provided "as is" and "as available" and all implied warranties are excluded as far as the law allows. Nothing limits liability for death or personal injury caused by negligence, for fraud, or for anything else that cannot be limited by law. Subject to that: we are not liable for loss of profit, business, goodwill or any indirect or consequential loss; we are not liable for loss caused by your reliance on AI output or by your unlawful recording or use of calls; and our total liability for all claims in a contract year is limited to the Charges you paid for the Services in the 12 months before the claim arose.

## 15. INDEMNITY
You will cover our reasonable losses and costs arising from third party claims that result from your breach of clause 5 or 8, your Customer Content, or your unlawful recording or use of calls. We will tell you promptly of any claim and let you help defend it.

## 16. CONFIDENTIALITY
Each party must protect the other's confidential information with reasonable care, use it only for this agreement, and not disclose it except to staff, advisers and sub-processors who need it or where the law requires. This lasts for 3 years after the agreement ends.

## 17. CHANGES TO THESE TERMS
We may update these terms where reasonably necessary, for example for changes in law, security, new features, or if our Call Scope business moves to a new company. We will give you at least 30 days' notice of any material change by email or in the Services. If a change is materially to your disadvantage you may end the Services without charge within that period; otherwise continued use means you accept it.

## 18. GENERAL
This is the whole agreement for the Services and replaces anything said before it. Neither party is liable for delay caused by events outside its reasonable control. If part of these terms cannot be enforced, the rest continues. Only the parties can enforce this agreement (Contracts (Rights of Third Parties) Act 1999). You may not transfer your rights without our written consent; we may transfer ours to another company in our group, or to a company that takes over the Call Scope business, on notice to you. Notices must be in writing to the contact details on the Order. English law applies and the courts of England and Wales have exclusive jurisdiction. Questions: {EMAIL}.
"""


import types as _types
import base64
# ─── STEADYTEMP ENGINE (paperwork layouts from the stand-alone SteadyTemp pricebook, kept inside this one file) ───
_STX_SRC = r'''"""SteadyTemp paperwork engine (embedded in the pricebook so app.py stays a single file).
Document layouts taken from the stand-alone SteadyTemp pricebook. The pricebook fills CO, COST, TERMS and QD before building."""
import io, re, uuid, html as html_lib
from datetime import date
from fpdf import FPDF

CO = {}          # company details (trading, legal, reg_office, addr, reg, vat, email, phone, web, funder, legal_line)
COST = {}        # settings the paperwork quotes (free_support_years ...)
TERMS = []       # [[heading, text], ...]
QD = {}          # the deal / customer details, under the stand-alone tool's q_* names
LOGO_BYTES = None
CFG = {}

def esc(v):
    return html_lib.escape(str(v if v is not None else ""), quote=True)

def s(text):
    if text is None:
        return ""
    text = str(text)
    for a, b in {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                 "\u2026": "...", "\u00a0": " ", "\u00ae": "(R)", "\u00a9": "(C)", "\u2022": "-"}.items():
        text = text.replace(a, b)
    return text.encode("latin-1", errors="replace").decode("latin-1")

def money(v, dp=2):
    try:
        return f"\u00a3{float(v):,.{dp}f}"
    except Exception:
        return "\u00a30.00"

def _num(key, default=0.0):
    try:
        v = QD.get(key, default)
        return float(v) if v not in (None, "") else float(default)
    except Exception:
        return float(default)

def _logo_stream():
    return io.BytesIO(LOGO_BYTES) if LOGO_BYTES else None

# SteadyTemp brand pack (Oct 2026): Steady Blue is the only brand colour, everything else is neutral
NAVY   = (11, 99, 246)      # Steady Blue  #0B63F6 - logo tile, rules, table bars
ACCENT = (91, 155, 255)     # Sky Blue     #5B9BFF - small accents
PALE   = (232, 240, 254)    # Blue Soft    #E8F0FE - tinted panels
DEEP   = (10, 15, 26)       # Black        #0A0F1A - footer band, headlines
INK    = (17, 24, 39)       # Ink          #111827 - paragraph text
GREY   = (91, 100, 114)     # Grey         #5B6472 - secondary text
FONT = "Helvetica"          # becomes Instrument Sans when assets/fonts is present
FONT_FILES = {}             # {"": regular.ttf, "B": medium.ttf} - filled in by the pricebook

def Q(key, default=""):
    v = QD.get(key, default)
    return "" if v is None else str(v).strip()

def cust_address_lines():
    return [x for x in (Q("q_addr1"), Q("q_addr2"), Q("q_town"), Q("q_county"), Q("q_postcode")) if x]

def split_name_pos(raw):
    parts = [p.strip() for p in str(raw or "").split(" - ", 1)]
    return parts[0], (parts[1] if len(parts) > 1 else "")

def company_lines():
    """The two lines of company details printed at the foot of every page (as on the letterhead)."""
    l1 = "  |  ".join(x for x in (CO.get("legal"), CO.get("reg_office"), CO.get("reg")) if x)
    l2 = "  |  ".join(x for x in (", ".join(a for a in CO["addr"] if a), CO.get("vat") if "pending" not in str(CO.get("vat", "")).lower() else "") if x)
    return l1, l2

class DocPDF(FPDF):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        global FONT
        FONT = "Helvetica"
        try:
            if FONT_FILES.get("") and FONT_FILES.get("B"):
                for _st, _f in (("", FONT_FILES[""]), ("B", FONT_FILES["B"]), ("I", FONT_FILES[""]), ("BI", FONT_FILES["B"])):
                    self.add_font("InstrumentSans", _st, _f)
                FONT = "InstrumentSans"
        except Exception:
            FONT = "Helvetica"

    def footer(self):
        """Brand footer: Steady Blue line over a black band with the company details."""
        h = 14
        y = self.h - h
        self.set_fill_color(*NAVY); self.rect(0, y - 1.1, self.w, 1.1, "F")
        self.set_fill_color(*DEEP); self.rect(0, y, self.w, h, "F")
        l1, l2 = company_lines()
        self.set_text_color(255, 255, 255)
        self.set_xy(10, y + 2.6); self.set_font(FONT, "B", 7.2); self.cell(self.w - 20, 3.8, s(l1), align="C")
        self.set_xy(10, y + 6.6); self.set_font(FONT, "", 7); self.cell(self.w - 20, 3.8, s(l2), align="C")
        if CO.get("legal_line"):
            self.set_xy(10, y + 10); self.set_font(FONT, "I", 6); self.cell(self.w - 20, 3, s(CO["legal_line"]), align="C")
        self.set_xy(self.w - 40, y - 5.5); self.set_font(FONT, "", 7); self.set_text_color(*GREY)
        self.cell(30, 4, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(*INK)

def doc_header(pdf, title, subtitle=""):
    """Letterhead-style page top: logo on the left, document title on the right, blue rule with an orange accent."""
    pdf.add_page()
    pdf.set_fill_color(*NAVY); pdf.rect(0, 0, pdf.w, 2.2, "F")
    lg = _logo_stream()
    title_y = 9
    if lg is not None:
        try:
            pdf.image(lg, x=pdf.l_margin, y=8.5, h=12)
        except Exception:
            lg = None
    if lg is None:
        pdf.set_xy(pdf.l_margin, 9); pdf.set_font(FONT, "B", 18); pdf.set_text_color(*DEEP)
        pdf.cell(100, 9, s(CO["trading"]), ln=True)
    pdf.set_xy(pdf.w - pdf.r_margin - 95, title_y); pdf.set_font(FONT, "B", 15); pdf.set_text_color(*DEEP)
    pdf.cell(95, 8, s(title), align="R", ln=True)
    pdf.set_xy(pdf.w - pdf.r_margin - 95, title_y + 8); pdf.set_font(FONT, "", 8); pdf.set_text_color(*GREY)
    pdf.cell(95, 4.5, s(subtitle or "Air conditioning supplied, installed and supported"), align="R", ln=True)
    rep = Q("q_rep")
    if rep:
        pdf.set_x(pdf.w - pdf.r_margin - 95); pdf.set_font(FONT, "I", 7.5)
        pdf.cell(95, 4, s(f"Prepared by: {rep}"), align="R")
    pdf.set_draw_color(*NAVY); pdf.set_line_width(0.6); pdf.line(pdf.l_margin, 26, pdf.w - pdf.r_margin, 26)
    pdf.set_draw_color(0, 0, 0); pdf.set_line_width(0.2)
    pdf.set_text_color(*INK)
    pdf.set_y(32)

def band(pdf, text):
    pdf.ln(2)
    pdf.set_fill_color(*NAVY); pdf.set_text_color(255, 255, 255); pdf.set_font(FONT, "B", 9)
    pdf.cell(0, 6, "  " + s(text), fill=True, ln=True)
    pdf.set_text_color(*INK)
    pdf.ln(1)

def para(pdf, text, size=8.5, h=4.4, align="J", style=""):
    pdf.set_font(FONT, style, size)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, h, s(text), align=align)

def kv(pdf, label, value, lw=42):
    pdf.set_font(FONT, "B", 8.5); pdf.set_text_color(*GREY)
    pdf.cell(lw, 5.2, s(label), ln=False)
    pdf.set_font(FONT, "", 8.5); pdf.set_text_color(*INK)
    pdf.cell(0, 5.2, s(value), ln=True)

def company_block(pdf):
    pdf.set_font(FONT, "", 7.5); pdf.set_text_color(*GREY)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 3.8, s("  |  ".join(x for x in (CO["legal"], ", ".join(x for x in CO["addr"] if x), CO["reg"], CO["vat"]) if x)))
    pdf.set_text_color(*INK)

def customer_block(pdf):
    band(pdf, "Customer details")
    kv(pdf, "Customer:", Q("q_company"))
    kv(pdf, "Company reg no:", Q("q_reg"))
    kv(pdf, "Address:", ", ".join(cust_address_lines()))
    kv(pdf, "Contact:", Q("q_contact") or split_name_pos(Q("q_signatory"))[0])
    if Q("q_tel") or Q("q_mobile"):
        kv(pdf, "Telephone:", " / ".join(x for x in (Q("q_tel"), Q("q_mobile")) if x))
    kv(pdf, "Customer email:", Q("q_email"))
    kv(pdf, "Billing email:", Q("q_bill_email") or Q("q_email"))
    if Q("q_inv_addr"):
        kv(pdf, "Invoice address:", Q("q_inv_addr").replace("\n", ", "))

def equipment_table(pdf, C):
    band(pdf, "Equipment")
    pdf.set_font(FONT, "B", 8); pdf.set_fill_color(*PALE)
    pdf.cell(118, 5.5, "  Item", fill=True); pdf.cell(48, 5.5, "Type", fill=True); pdf.cell(0, 5.5, "Qty", fill=True, ln=True, align="C")
    pdf.set_font(FONT, "", 8.5)
    shown = 0
    for it, q in C["qty"]:
        if it["group"] in ("Materials", "Labour"):
            continue
        pdf.cell(118, 5.4, "  " + s(it["name"])[:70], border="B")
        pdf.cell(48, 5.4, s(it["group"]), border="B")
        pdf.cell(0, 5.4, str(q), border="B", ln=True, align="C")
        shown += 1
    if not shown:
        pdf.set_text_color(160, 60, 60); pdf.cell(0, 6, "  (no equipment selected yet)", ln=True); pdf.set_text_color(*INK)

def sig_block(pdf, heading, sign, note=""):
    if pdf.get_y() > 243:
        pdf.add_page(); pdf.set_y(20)
    pdf.ln(3)
    pdf.set_font(FONT, "B", 9); pdf.cell(0, 5, s(heading), ln=True)
    y = pdf.get_y()
    if sign and sign.get("bytes"):
        try:
            pdf.image(io.BytesIO(sign["bytes"]), x=pdf.l_margin, y=y + 0.5, w=52, h=17)
        except Exception:
            pass
        pdf.set_y(y + 18.5)
    else:
        pdf.set_y(y + 14)
    pdf.cell(80, 0.4, "", border="T", ln=True)
    pdf.ln(1)
    if sign:
        nm, ps = sign["name"], ""
        n2, p2 = split_name_pos(sign["name"])
        nm, ps = n2, p2
        when = sign.get("ts", "")
        co = sign.get("company", "")
    else:
        nm, ps = split_name_pos(Q("q_signatory"))
        when, co = "", Q("q_company")
    pdf.set_font(FONT, "", 8.5)
    pdf.cell(95, 5, s(f"Name:  {nm or '____________________________'}"), ln=False)
    pdf.cell(0, 5, s(f"Date:  {when or '____ / ____ / ________'}"), ln=True)
    pdf.cell(95, 5, s(f"Position:  {ps or '____________________________'}"), ln=False)
    pdf.cell(0, 5, s(f"Company:  {co or '____________________________'}"), ln=True)
    if note:
        pdf.ln(1); pdf.set_font(FONT, "I", 7.5); pdf.set_text_color(*GREY)
        pdf.multi_cell(pdf.epw, 3.8, s(note)); pdf.set_text_color(*INK)

def payment_text(C):
    t = CO["trading"]; cust = Q("q_company") or "the customer"
    if C["is_cash"]:
        return (f"{t} agrees to sell, and {cust} (the customer) agrees to buy, the equipment specified above for a price of "
                f"{money(C['cash_price'])} plus VAT, payable on the terms set out in our invoice. Ownership of the equipment passes to "
                f"the customer when payment is received in full.")
    n = C["term"] - 1
    return (f"{t} agrees with {cust}, the hirer, that the equipment specified above shall be rented to you by {CO['legal']} or a "
            f"3rd party finance provider, for an initial payment of {money(C['rental'])} plus VAT followed by {n} further payments of "
            f"{money(C['rental'])} plus VAT. {t} will assist with the application for 3rd party finance to facilitate {C['term']} "
            f"monthly payments of {money(C['rental'])} plus VAT and shall arrange for {CO['funder']} to enter into a rental agreement with the hirer.")

def existing_costs():
    rows = [("Existing running costs", Q("q_cur_running")), ("Existing service costs", Q("q_cur_service")),
            ("Existing equipment leasing costs", Q("q_cur_leasing")), ("Existing heating costs", Q("q_cur_heating")),
            ("Other", Q("q_cur_other"))]
    out = []
    for lbl, v in rows:
        try:
            f = float(v)
        except Exception:
            f = 0.0
        out.append((lbl, f))
    return out, sum(f for _, f in out)

def doc_proposal(pdf, C, sign):
    doc_header(pdf, "Air Conditioning Proposal")
    pdf.set_font(FONT, "", 9)
    kv(pdf, "Date:", date.today().strftime("%d/%m/%Y"))
    kv(pdf, "Prepared for:", Q("q_company"))
    kv(pdf, "Address:", ", ".join(cust_address_lines()))
    kv(pdf, "Proposed by:", CO["trading"])
    pdf.set_x(pdf.l_margin + 42); company_block(pdf)
    para(pdf, "Everything below is supplied, installed and supported by us, so there is one team to call.", h=4.6)
    equipment_table(pdf, C)
    names = " ".join(it["name"] for it, _ in C["qty"])
    if "Blue Science" in names:
        band(pdf, "Blue Science air sanitising")
        para(pdf, "Blue Science uses the disinfectant properties of UV-C light to turn an air conditioning unit into an air sanitiser. Warm, "
                  "contaminated air is pulled in through the top of the unit and cooled by the cooling coil, where the Blue Science UV-C strip "
                  "sanitises it. The cooled air is then released free of airborne viruses, bacteria, moulds and odours.")
    if C["counts"]["lossnay"]:
        band(pdf, "Lossnay air exchange")
        para(pdf, "A commercial ventilation system that extracts stale air and recovers the heating or cooling energy to warm or cool the "
                  "incoming fresh air, using the Lossnay core for high energy-recovery efficiency.")
    band(pdf, "Monthly quotation" if not C["is_cash"] else "Quotation")
    ex, ex_total = existing_costs()
    if ex_total > 0:
        pdf.set_font(FONT, "B", 8.5); pdf.cell(0, 5, "Your existing monthly air conditioning costs", ln=True)
        pdf.set_font(FONT, "", 8.5)
        for lbl, v in ex:
            if v:
                pdf.cell(120, 5, "  " + s(lbl), ln=False); pdf.cell(0, 5, money(v), ln=True, align="R")
        pdf.set_font(FONT, "B", 8.5); pdf.cell(120, 5.5, "  TOTAL existing", border="T", ln=False); pdf.cell(0, 5.5, money(ex_total), border="T", ln=True, align="R")
        pdf.ln(2)
    pdf.set_font(FONT, "B", 8.5); pdf.cell(0, 5, "New air conditioning costs", ln=True)
    pdf.set_font(FONT, "", 8.5)
    if C["is_cash"]:
        pdf.cell(120, 5.2, "  Equipment, installation and set-up (one-off, plus VAT)", ln=False); pdf.cell(0, 5.2, money(C["cash_price"]), ln=True, align="R")
    else:
        pdf.cell(120, 5.2, "  Equipment rental charge per month (plus VAT)", ln=False); pdf.cell(0, 5.2, money(C["rental"]), ln=True, align="R")
    fy = int(COST["free_support_years"])
    pdf.cell(120, 5.2, s(f"  On-site support - first {fy} year{'s' if fy != 1 else ''}"), ln=False); pdf.cell(0, 5.2, "Included", ln=True, align="R")
    pdf.cell(120, 5.2, s(f"  On-site support after year {fy} (annual charge, plus VAT)"), ln=False); pdf.cell(0, 5.2, money(C["support"]), ln=True, align="R")
    if not C["is_cash"] and ex_total > 0:
        diff = ex_total - C["rental"]
        pdf.set_font(FONT, "B", 8.5)
        pdf.cell(120, 5.6, "  Estimated monthly difference", border="T", ln=False)
        pdf.cell(0, 5.6, (money(diff) + " saving") if diff >= 0 else (money(-diff) + " more"), border="T", ln=True, align="R")
    pdf.ln(1)
    band(pdf, "Your quotation includes")
    cash_back = _num("q_cashback")
    _eng, _elec = install_summary(C)
    yes = [("Installation & set up", "Yes")]
    if C["est_days"] > 0:
        yes.append(("Engineer installation", f"{C['est_days']} day{'s' if C['est_days'] != 1 else ''}"
                    + (f" x {C['engineers']} engineers" if C.get("engineers", 1) > 1 else "")))
    if _elec:
        yes.append(("Electrician", _elec.split(" - ")[1] if " - " in _elec else "Included"))
    _wy = warranty_years(C)
    yes += [("Warranty", f"{_wy} year{'s' if _wy != 1 else ''}" + ("" if C["is_cash"] else " (full term)")),
            (f"{fy} year on-site support", "Yes"),
            ("Cherry picker / access equipment", Q("q_cherry") or "No")]
    if int(_num("q_pumps")):
        yes.append(("Condensate pump(s)", str(int(_num("q_pumps")))))
    if cash_back > 0:
        yes.append(("Cashback towards your requirements", money(cash_back)))
    for lbl, v in yes:
        pdf.set_font(FONT, "", 8.5); pdf.cell(120, 5, "  " + s(lbl), ln=False); pdf.cell(0, 5, s(v), ln=True, align="R")
    if not C["is_cash"]:
        pdf.ln(1)
        para(pdf, f"Equipment rental terms: monthly rental period of {C['profile']} ({C['term_label']}), plus VAT at the prevailing rate.", style="B")
    pdf.ln(1)
    para(pdf, "I confirm that I wish to proceed with the proposal above. I understand that I will be billed in line with "
              f"{CO['legal']}'s current Terms and Conditions" + ("" if C["is_cash"] else ", that the equipment rental is billed separately by a "
              "3rd party funder, and that support and all other costs are billed by us under a separate agreement") + ".", size=8)
    sig_block(pdf, "Signed on behalf of the customer", sign)

def doc_order(pdf, C, sign):
    doc_header(pdf, "Order Form")
    pdf.set_font(FONT, "", 8); company_block(pdf)
    kv(pdf, "Date:", date.today().strftime("%d/%m/%Y"))
    customer_block(pdf)
    equipment_table(pdf, C)
    if Q("q_special"):
        band(pdf, "Special conditions"); para(pdf, Q("q_special"))
    band(pdf, "Payment schedule")
    para(pdf, payment_text(C))
    pdf.ln(1)
    para(pdf, f"{CO['trading']} agrees to supply, install and decommission the above equipment, and the customer agrees to make the "
              "associated payments in accordance with the payment schedule above, subject to the terms and conditions"
              + ("" if C["is_cash"] else " and the terms of the hire agreement with the finance provider")
              + ". As a duly authorised representative of the customer, I confirm that I have read, understood and accept the terms and "
                "conditions of this agreement.")
    sig_block(pdf, "On behalf of (the customer)", sign)

def doc_support(pdf, C, sign):
    doc_header(pdf, "On-Site Support Agreement")
    kv(pdf, "Date:", date.today().strftime("%d/%m/%Y"))
    customer_block(pdf)
    equipment_table(pdf, C)
    fy = int(COST["free_support_years"])
    band(pdf, "Support terms")
    para(pdf, f"{CO['trading']} agrees to provide on-site warranty cover, to include remote diagnostics and programming of faults, for the "
              f"equipment listed above for an agreement term of {C['term']} months. Faulty equipment will be repaired or replaced. "
              "Additional equipment added later will be charged for, and its warranty premium added to this agreement.")
    pdf.ln(1)
    kv(pdf, "Warranty:", f"{warranty_years(C)} year{'s' if warranty_years(C) != 1 else ''} from installation" + ("" if C["is_cash"] else " - the full term of the agreement"), 42)
    kv(pdf, "Inclusive period:", f"{fy} year{'s' if fy != 1 else ''} on-site support from installation", 42)
    kv(pdf, "Annual charge after:", f"{money(C['support'])} plus VAT per year, for the remainder of the term", 42)
    pdf.ln(1)
    para(pdf, f"{CO['trading']} agrees to provide remote and on-site maintenance cover for the equipment above, and the customer agrees to pay "
              "the annual charge set out above for the agreement term, subject to the terms and conditions. As a duly authorised representative "
              "of the customer, I confirm that I have read, understood and accept the terms and conditions of this agreement.")
    sig_block(pdf, "On behalf of (the customer)", sign)

def doc_dd(pdf, C, sign):
    doc_header(pdf, "Direct Debit Set-up")
    band(pdf, "Set up your bank or building society to pay by Direct Debit")
    para(pdf, f"Our support charges and any other amounts we bill are collected by Direct Debit through GoCardless. "
              + ("Your equipment rental is billed separately by the finance provider. " if not C["is_cash"] else "")
              + "It only takes a couple of minutes:", h=5)
    pdf.ln(2)
    steps = [("Step one", f"You will receive a GoCardless email from {CO['legal']} ({CO['trading']})."),
             ("Step two", "Set up your account by entering the account holder's name, sort code and account number."),
             ("Step three", "Once complete you will receive an email confirming your registration.")]
    for a, b in steps:
        pdf.set_fill_color(*PALE); pdf.set_font(FONT, "B", 9)
        pdf.cell(30, 9, "  " + a, fill=True, border="B"); pdf.set_font(FONT, "", 9)
        pdf.cell(0, 9, "  " + s(b), fill=True, border="B", ln=True)
        pdf.ln(1)
    pdf.ln(2)
    band(pdf, "Direct Debit mandate - your bank details")
    sc = re.sub(r"\D", "", Q("q_bank_sort"))
    sc = f"{sc[0:2]}-{sc[2:4]}-{sc[4:6]}" if len(sc) == 6 else Q("q_bank_sort")
    blank = "______________________"
    kv(pdf, "Bank / building society:", Q("q_bank_name") or blank, 52)
    kv(pdf, "Account holder name:", Q("q_bank_holder") or Q("q_company") or blank, 52)
    kv(pdf, "Account number:", Q("q_bank_acc") or blank, 52)
    kv(pdf, "Sort code:", sc or blank, 52)
    kv(pdf, "Billing email:", Q("q_bill_email") or Q("q_email") or blank, 52)
    pdf.ln(1)
    para(pdf, f"I/we authorise {CO['legal']} (trading as {CO['trading']}) to collect by Direct Debit, through GoCardless, the "
              + ("annual on-site support charge and any other amounts invoiced to us under this agreement. " if C["is_cash"] else
                 "annual on-site support charge and any other amounts invoiced to us under this agreement (the equipment rental itself is collected by the finance provider). ")
              + "Payments are collected on or around the due date shown on our invoice, and we will tell you in advance of any change to the amount or date. "
              "This mandate is subject to the Direct Debit Guarantee below.", size=8.3, h=4.2)
    sig_block(pdf, "Authorised signature (the account holder)", sign)
    pdf.ln(2)
    para(pdf, "THE DIRECT DEBIT GUARANTEE - The Guarantee is offered by all banks and building societies that accept instructions to pay Direct Debits. "
              "If there are any changes to the amount, date or frequency of your Direct Debit, the organisation will notify you (normally 10 working days) in advance "
              "of your account being debited or as otherwise agreed. If an error is made in the payment of your Direct Debit, you are entitled to a full and immediate "
              "refund of the amount paid from your bank or building society. You can cancel a Direct Debit at any time by simply contacting your bank or building society. "
              "Written confirmation may be required; please also notify us.", size=7, h=3.6, style="I")

def doc_terms(pdf, C, sign):
    doc_header(pdf, "Terms & Conditions")
    fill = dict(legal=CO["legal"], trading=CO["trading"], free=int(COST["free_support_years"]))
    for title, text in TERMS:
        if pdf.get_y() + 14 > pdf.page_break_trigger:      # don't leave a clause heading on its own at the foot of a page
            pdf.add_page()
        pdf.set_fill_color(*NAVY); pdf.set_text_color(255, 255, 255); pdf.set_font(FONT, "B", 8)
        pdf.cell(0, 5, "  " + s(title), fill=True, ln=True); pdf.set_text_color(*INK)
        try:
            body = text.format(**fill)
        except Exception:
            body = text
        pdf.set_font(FONT, "", 7.4); pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 3.7, s(body), align="J"); pdf.ln(1.2)
    sig_block(pdf, "Confirmation - I have read and agree to these Terms & Conditions", sign)

def doc_certificate(pdf, C, sign):
    doc_header(pdf, "Certificate of Completion", "Electronic signing record")
    env = str(uuid.uuid4()).upper()
    import hashlib as _h
    kv(pdf, "Envelope ID:", env, 48)
    kv(pdf, "Status:", "COMPLETED", 48)
    kv(pdf, "Document:", f"{CO['trading']} proposal - {Q('q_company')}"[:80], 48)
    kv(pdf, "Signer:", sign["name"], 48)
    kv(pdf, "Company:", sign.get("company", ""), 48)
    kv(pdf, "Signed at:", sign.get("ts", ""), 48)
    kv(pdf, "IP address:", sign.get("ip", "Not captured"), 48)
    kv(pdf, "Signature fingerprint:", _h.sha256(sign["bytes"]).hexdigest().upper()[:48], 48)
    kv(pdf, "Time zone:", "UK (London)", 48)
    pdf.ln(4)
    para(pdf, "This record confirms that the signer above applied the signature shown in this document electronically, using a secure "
              "session, on the date and time shown. The same signature has been applied to each signature block in this pack.", size=8)

from PIL import Image as _PIm

def _png_bytes(b64):
    """Any picture (jpg / png / webp, with or without transparency) -> plain PNG on white, safe for the PDF."""
    import base64
    im = _PIm.open(io.BytesIO(base64.b64decode(b64)))
    im = im.convert("RGBA"); bg = _PIm.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
    out = io.BytesIO(); bg.convert("RGB").save(out, format="PNG"); return out.getvalue()

def warranty_years(C):
    """Warranty runs for the whole deal: the lease term in years (3, 5, 7, 10...). Cash sales keep the included support period."""
    if C["is_cash"]:
        return int(COST["free_support_years"])
    return max(1, round(int(C["term"]) / 12))

def warranty_text(C):
    y = warranty_years(C)
    return f"{y}-year warranty" + ("" if C["is_cash"] else " - for the full term of the agreement")

def install_summary(C):
    """(engineer line, electrician line) for the customer paperwork - either can be '' if not in the deal."""
    eng = ""
    if C["est_days"] > 0:
        eng = (f"Engineer installation - estimated {C['est_days']} day{'s' if C['est_days'] != 1 else ''}"
               + (f" with {C['engineers']} engineers" if C.get("engineers", 1) > 1 else ""))
    elec = ""
    if C.get("auto_install"):
        if C.get("install_elec", 0) > 0:
            n = C.get("n_units", 0)
            elec = f"Qualified electrician to connect and wire in your system{'s' if n != 1 else ''}"
    else:
        d = sum(q for it, q in C["qty"] if it["group"] == "Labour" and "electrician" in it["name"].lower())
        if d > 0:
            elec = f"Qualified electrician - {d} day{'s' if d != 1 else ''}"
    return eng, elec


def build_pack(C, sign=None):
    pdf = DocPDF()
    pdf.set_margins(15, 15, 15); pdf.set_auto_page_break(True, 24); pdf.alias_nb_pages()
    for fn in (doc_proposal, doc_order, doc_support, doc_dd, doc_terms):
        fn(pdf, C, sign)
    if sign and sign.get("bytes"):
        doc_certificate(pdf, C, sign)
    return bytes(pdf.output())
'''
_stx = _types.ModuleType("stx_embedded")
exec(compile(_STX_SRC, "stx_embedded", "exec"), _stx.__dict__)

ST_LOGO_B64 = ""   # SteadyTemp logo now lives in assets/steadytemp_logo.png
ST_COMPANY_DEFAULT = {
    "trading": "SteadyTemp Air Conditioning", "legal": "SteadyTemp LTD", "legal_line": "",
    "reg_office": "The Belfry, 4400 Parkway, Whiteley, Fareham, England, PO15 7FJ",
    "addr": ["Suite C Jupiter House", "Sitka Drive", "Shrewsbury Business Park", "Shropshire", "SY2 6LG"],
    "reg": "Company number 17506149", "vat": "VAT Registration No. Pending",
    "email": "andy@steadytemp.co.uk", "phone": "01743 832049", "web": "www.steadytemp.co.uk", "funder": "our finance partner",
}
ST_TERMS_DEFAULT = json.loads(r'''[["1. DEFINITIONS", "Order means the SteadyTemp order form signed by you. Equipment means the air conditioning units, controls and associated materials listed on the Order. We/us means {legal} trading as {trading}. You means the customer named on the Order. Site means the premises where the Equipment is to be installed. Funder means the third party finance provider that rents the Equipment to you. Initial Period means the first {free} year(s) of on-site support included in the price."], ["2. THE CONTRACT", "These terms and the Order form the whole agreement between us for the supply, installation and support of the Equipment. If you are renting the Equipment from a Funder, the Funder's rental agreement is a separate contract between you and the Funder and these terms do not replace it. Prices are quoted in pounds sterling and exclude VAT, which is added at the prevailing rate."], ["3. SUPPLY AND INSTALLATION", "We will supply and install the Equipment at the Site with reasonable skill and care, using suitably qualified engineers, and in line with the regulations that apply to refrigerant-containing equipment, including the F-Gas regulations. Installation dates are estimates and time is not of the essence. We will make good any damage we cause to the Site. Standard installation covers the pipework, cabling, drainage and fixings described in the Order; additional work found to be needed on the day (for example specialist access equipment, structural or electrical upgrades) will be agreed with you before it is carried out."], ["4. YOUR RESPONSIBILITIES", "You will give our engineers safe and timely access to the Site, provide a suitable electrical supply and any consents needed from your landlord or building owner, and tell us about hazards at the Site (including asbestos). You must not move, alter or repair the Equipment, or let anyone other than us or the Funder do so, without our written consent. You must use the Equipment in line with the manufacturer's instructions and keep filters clean as advised."], ["5. RENTAL THROUGH A FUNDER", "Where the Equipment is rented through a Funder, the rental is invoiced and collected by the Funder under its own agreement, for the term and at the monthly amount shown on the Order, plus VAT. We will help you apply for finance but approval is at the Funder's discretion; if the Funder declines, we may offer a different payment option or cancel the Order without liability on either side. The Equipment belongs to the Funder, and you must not sell, move or part with it. Rental payments must continue for the whole term whether or not you are using the Equipment."], ["6. CASH SALE", "Where you buy the Equipment outright, the price shown on the Order is payable as set out in the payment schedule. Ownership of the Equipment passes to you only when we have received payment in full; until then you must keep it insured, safe and identifiable as ours. Risk passes to you on delivery to the Site."], ["7. WARRANTY AND ON-SITE SUPPORT", "During the Initial Period we provide on-site warranty cover, including remote diagnostics and programming of faults, as described in the On-Site Support Agreement. Faulty Equipment will be repaired or replaced. Warranty and support do not cover damage caused by misuse, accident, unauthorised work, power faults, flooding or fair wear and tear on consumables. After the Initial Period the annual support charge shown on the Order applies for the term of the agreement. Equipment added later will be charged for, and its support premium added, by agreement."], ["8. CHARGES AND PAYMENT", "All charges exclude VAT. Our invoices are due within 14 days. A late payment fee of £25 applies after 7 days. Support and other charges that we bill are collected by Direct Debit through GoCardless; a direct debit cancellation fee of £50 applies. We may charge interest on overdue amounts at 4% above the Bank of England base rate. We may suspend support while an account is overdue."], ["9. TERM AND RENEWAL", "The support agreement runs for the term shown on the Order. At the end of the term the Equipment may be returned, renewed or replaced as set out in the Funder's agreement; our support continues year to year at our then-current annual charge unless either of us gives 90 days' written notice."], ["10. CANCELLATION", "Once installation has started, or the Equipment has been ordered specially for you, you cannot cancel the Order without paying our reasonable costs to that point. Rental and support commitments are for the full term shown on the Order. If you end the support agreement early, the remaining annual charges become due."], ["11. LIABILITY", "We are not liable for loss of profits, business opportunity, goodwill or indirect loss. Our total liability is capped at the amount you have paid us in the previous 12 months under the Order. Nothing in these terms limits liability for death or personal injury caused by negligence, fraud, or anything else that cannot be limited by law. Air conditioning does not guarantee a particular temperature in all conditions; performance depends on correct use and the building."], ["12. TERMINATION", "Either of us may end the contract if the other commits a serious breach that is not put right within 14 days of written notice, or becomes insolvent. We may end it at once if payment is more than 7 days overdue after a reminder. On ending, all unpaid sums become due, and we or the Funder may collect the Equipment from the Site."], ["13. DATA PROTECTION", "We use the personal details you give us to provide the Equipment and support, to arrange finance and to bill you, and share them with the Funder and our installers where needed. We keep them secure and do not sell them. See our privacy notice for your rights."], ["14. FORCE MAJEURE", "Neither of us is liable for delay or failure caused by events beyond our reasonable control, including severe weather, supply shortages, strikes, or failure of utilities."], ["15. GENERAL", "These terms and the Order are the whole agreement between us and are governed by the law of England and Wales, with the English courts having exclusive jurisdiction. We may change these terms by written notice; changes do not alter a signed Order. You may not transfer your rights without our written consent. If any clause is found unenforceable the rest remains in force."]]''')


def st_company():
    c = dict(ST_COMPANY_DEFAULT)
    for k, v in (st.session_state.active_config.get("steadytemp_company") or {}).items():
        if v:
            c[k] = v
    if isinstance(c.get("addr"), str):
        c["addr"] = [x.strip() for x in c["addr"].split(",") if x.strip()]
    return c


def st_terms():
    raw = st.session_state.active_config.get("steadytemp_terms_text")
    if not raw:
        return [list(x) for x in ST_TERMS_DEFAULT]
    out, cur = [], None
    for line in raw.splitlines():
        if line.startswith("## "):
            cur = [line[3:].strip(), ""]; out.append(cur)
        elif cur is not None:
            cur[1] = (cur[1] + " " + line.strip()).strip()
    return out or [list(x) for x in ST_TERMS_DEFAULT]


def build_steadytemp_pack(sign=None):
    """The separate SteadyTemp pack - Air Conditioning Proposal, Order Form, On-Site Support Agreement, Direct Debit set-up and
    Terms & Conditions (plus a signing certificate when signed). sign = {"bytes","name","company","ts","ip"} or None."""
    if not ac_quote:
        return None
    G = st.session_state.get
    addr = " ".join(str(G("q_address") or "").replace("\n", ", ").split())
    pc = _ac_site_postcode() or ""
    nm = str(G("q_contact") or "")
    _stx.CO = st_company()
    _stx.COST = {"free_support_years": int(AC_COST.get("free_support_years", 1))}
    _stx.TERMS = st_terms()
    try:
        _stx.LOGO_BYTES = _asset_bytes("steadytemp_logo.png")
    except Exception:
        _stx.LOGO_BYTES = None
    _fr, _fm = ASSETS_DIR / "fonts" / "InstrumentSans-Regular.ttf", ASSETS_DIR / "fonts" / "InstrumentSans-Medium.ttf"
    _stx.FONT_FILES = {"": str(_fr), "B": str(_fm)} if (_fr.exists() and _fm.exists()) else {}    # no font files -> plain Helvetica
    _stx.QD = {
        "q_company": G("q_comp_name") or "", "q_reg": G("q_comp_reg") or "", "q_addr1": addr,
        "q_postcode": ("" if (pc and pc.upper() in addr.upper()) else pc), "q_contact": nm.split(" - ")[0].strip(), "q_signatory": nm,
        "q_tel": G("q_phone") or "", "q_email": G("q_dir_email") or "", "q_bill_email": G("q_bill_email") or "",
        "q_special": G("ac_special") or "", "q_bank_name": G("q_bank_name") or "", "q_bank_holder": G("q_acc_holder") or G("q_comp_name") or "",
        "q_bank_acc": G("q_acc_no") or "", "q_bank_sort": G("q_sort_code") or "", "q_rep": _prepared_by(),
        "q_cur_running": G("ac_cur_running", 0), "q_cur_service": G("ac_cur_service", 0), "q_cur_leasing": G("ac_cur_leasing", 0),
        "q_cur_heating": G("ac_cur_heating", 0), "q_cur_other": G("ac_cur_other", 0),
        "q_cashback": G("ac_cashback", 0), "q_cherry": G("ac_cherry") or "No", "q_pumps": G("ac_pumps", 0),
    }
    return _stx.build_pack(ac_quote, sign)


def _sign_cs(sg):
    return None if not sg else {"sig": sg["sig_bytes"], "name": sg["name"], "date": date.today().strftime("%d/%m/%Y")}


def _sign_st(sg):
    return None if not sg else {"bytes": sg["sig_bytes"], "name": sg["name"], "company": sg.get("company", ""), "ts": sg.get("ts", ""), "ip": sg.get("ip", "")}


def n_packs():
    return int(bool(_tele_any)) + int(bool(cs_active)) + int(bool(ac_active))


def build_combined(tele_bytes, sg=None):
    """Telephony pack first (if there is one), then Call Scope, then SteadyTemp - one file for sending or signing."""
    parts = [tele_bytes if _tele_any else None]
    if cs_active and not cs_crm_missing:
        parts.append(build_callscope_pack(_sign_cs(sg)))
    if ac_active:
        parts.append(build_steadytemp_pack(_sign_st(sg)))
    return merge_pdfs(*parts)


# ─── CALL SCOPE ENGINE (pricing maths + pack layout from the stand-alone Call Scope pricebook, kept inside this one file) ───
_CSX_SRC = r'''"""Call Scope paperwork engine (embedded in the pricebook so app.py stays a single file).
Pricing maths and PDF layout taken from the stand-alone Call Scope pricebook."""
import io
import math
from datetime import date
from fpdf import FPDF

LOGO_BYTES = None   # set by the pricebook before building a pack



def r2(x):
    return round(float(x) + 1e-9, 2)


def money(x, dp=2):
    x = float(x or 0)
    sign = "-" if x < 0 else ""
    return f"{sign}£{abs(x):,.{dp}f}"


def mod_by_id(cfg):
    return {m["id"]: m for m in cfg["modules"]}


def setup_by_id(cfg):
    return {s["id"]: s for s in cfg["setup"]}


def max_discount_for(cfg, months):
    for t in cfg["customer_terms"]:
        if int(t["months"]) == int(months):
            return float(t["max_discount"])
    return 0.0


# ─────────────────────────── CUSTOMER (direct) ───────────────────────────
def discount_steps(discount, years, style="stepped"):
    """Discount % for each contract year.
    stepped: full discount in year 1, then equal steps down so the final year is the standard price.
    fixed:   the same discount every year of the term."""
    d = float(discount)
    if years <= 1 or style == "fixed":
        return [d] * max(1, years)
    return [r2(d * (years - 1 - i) / (years - 1)) for i in range(years)]


def _disc_unit(m, d, floor=True):
    """Unit price after discount d% - never below what it costs us (unless floor is off)."""
    u = r2(m["rrp"] * (1 - d / 100))
    return max(u, r2(m["buy"])) if floor and m.get("buy") else u

def customer_quote(cfg, qty, minutes=0, agent_setups=0, term=60, discount=0.0, style="stepped",
                   review_pct=None, setup_mode="invoice", floor=True):
    mods = cfg["modules"]
    review = cfg["annual_review_pct"] if review_pct is None else float(review_pct)
    years = max(1, math.ceil(int(term) / 12))
    steps = discount_steps(discount, years, style)

    lines = []
    for m in mods:
        q = int(qty.get(m["id"], 0) or 0)
        if q <= 0:
            continue
        d = steps[0] if m.get("discountable", True) else 0.0
        unit = _disc_unit(m, d, floor)
        lines.append({"id": m["id"], "name": m["name"], "unit_label": m.get("unit", ""), "qty": q,
                      "rrp": r2(m["rrp"]), "price": unit, "total": r2(unit * q), "buy": r2(m["buy"]),
                      "discountable": m.get("discountable", True)})
    mins = int(minutes or 0)
    if mins:
        mc = cfg["minutes"]
        p = r2(mins * mc["rrp_per_min"])
        lines.append({"id": "minutes", "name": f"AI minutes bundle - {mins:,} mins", "unit_label": "per month",
                      "qty": 1, "rrp": p, "price": p, "total": p, "buy": r2(mins * mc["buy_per_min"]),
                      "discountable": False})

    # yearly schedule (unit prices rounded to the penny each year so every document agrees)
    sched = []
    standard = r2(sum(l["rrp"] * l["qty"] for l in lines))
    prev = None
    for y in range(years):
        d = steps[y]
        mo = r2(sum((_disc_unit(l, d, floor) if l["discountable"] else l["rrp"]) * l["qty"] for l in lines))
        mo_rev = r2(mo * (1 + review / 100) ** y)
        m_from = y * 12 + 1
        m_to = min(int(term), (y + 1) * 12)
        sched.append({"year": y + 1, "months": f"{m_from} - {m_to}", "n_months": m_to - m_from + 1,
                      "discount": d, "monthly": mo, "monthly_with_review": mo_rev,
                      "change": None if prev is None else r2(mo - prev)})
        prev = mo

    # one-off set-up
    sid = setup_by_id(cfg)
    setup = []
    if lines:
        s = sid.get("platform")
        if s:
            setup.append({"name": s["name"], "qty": 1, "price": r2(s["rrp"]), "buy": r2(s["buy"])})
        n_rec = int(qty.get("receptionist", 0) or 0)
        s = sid.get("rec_setup")
        if s and n_rec:
            setup.append({"name": s["name"], "qty": n_rec, "price": r2(s["rrp"]), "buy": r2(s["buy"])})
        s = sid.get("agent_setup")
        if s and agent_setups:
            setup.append({"name": s["name"], "qty": int(agent_setups), "price": r2(s["rrp"]), "buy": r2(s["buy"])})
    for s in setup:
        s["total"] = r2(s["price"] * s["qty"])
    setup_total = r2(sum(s["total"] for s in setup)) if setup_mode != "waived" else 0.0
    setup_list_total = r2(sum(s["total"] for s in setup))

    monthly_total = sched[0]["monthly"] if lines else 0.0
    services_value = r2(sum(s["monthly"] * s["n_months"] for s in sched))
    services_value_rev = r2(sum(s["monthly_with_review"] * s["n_months"] for s in sched))
    buy_mo = r2(sum(l["buy"] * l["qty"] for l in lines))
    setup_buy = r2(sum(s["buy"] * s["qty"] for s in setup))
    profit = r2(services_value - buy_mo * int(term) + setup_total - setup_buy)
    return {
        "lines": lines, "schedule": sched, "setup": setup, "setup_total": setup_total,
        "setup_list_total": setup_list_total, "setup_mode": setup_mode,
        "standard_monthly": standard, "monthly_total": monthly_total, "term": int(term), "years": years,
        "discount": float(discount), "style": style, "review_pct": review,
        "services_value": services_value, "services_value_with_review": services_value_rev,
        "contract_value": r2(services_value + setup_total),
        "buy_monthly": buy_mo, "setup_buy": setup_buy, "profit": profit,
        "saving_vs_standard": r2(standard * int(term) - services_value),
    }



INK, MUTE, LINE = (30, 32, 44), (110, 116, 135), (222, 224, 236)

_MAP = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "•": "-",
        "…": "...", " ": " ", "→": "->", "≥": ">=", "≤": "<="}


def s(x):
    t = str(x if x is not None else "")
    for k, v in _MAP.items():
        t = t.replace(k, v)
    return t.encode("latin-1", "replace").decode("latin-1")


def hx(h, dflt):
    try:
        h = str(h).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return dflt


def tint(rgb, f):
    return tuple(int(255 - (255 - c) * f) for c in rgb)


class Doc(FPDF):
    def __init__(self, brand, label):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.B = brand
        self.label = label
        self.VIO = hx(brand.get("accent"), (120, 112, 232))
        self.NAVY = hx(brand.get("navy"), (16, 25, 56))
        self.TINT = tint(self.VIO, 0.09)
        self.alias_nb_pages()
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(True, margin=20)

    def header(self):
        B = self.B
        if LOGO_BYTES:
            try:
                self.image(io.BytesIO(LOGO_BYTES), x=15, y=8, h=17)
            except Exception:
                pass
        self.set_xy(45, 10.5)
        self.set_font("Helvetica", "B", 13); self.set_text_color(*self.NAVY)
        self.cell(90, 6, s(B["trading"]), new_x="LMARGIN", new_y="NEXT")
        self.set_x(45)
        self.set_font("Helvetica", "", 8); self.set_text_color(*MUTE)
        self.cell(100, 4.5, s(f"{B['byline']}  |  {B['tag']}" if B.get("byline") else B.get("tag", "")))
        self.set_xy(120, 11)
        self.set_font("Helvetica", "B", 8); self.set_text_color(*self.VIO)
        self.cell(75, 5, s(self.label), align="R")
        if getattr(self, "supplier", None):
            self.set_xy(110, 16.5)
            self.set_font("Helvetica", "", 7.5); self.set_text_color(*MUTE)
            self.cell(85, 4, s("Supplied by " + self.supplier.get("company", "")), align="R")
        self.set_fill_color(*self.VIO); self.rect(15, 28, 180, 0.9, "F")
        self.set_y(34)

    def footer(self):
        B = self.B
        self.set_y(-14)
        self.set_font("Helvetica", "", 7); self.set_text_color(*MUTE)
        bits = [f"{B['trading']} {B.get('byline', '')}".strip(), B.get("legal", ""), B.get("email", ""), B.get("website", ""), "All figures exclude VAT", "Confidential"]
        self.cell(0, 4, s("  |  ".join(b for b in bits if b)), align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 4, f"Page {self.page_no()} of {{nb}}", align="C")

    # ── building blocks ──
    def doc_title(self, text, sub=""):
        self.set_font("Helvetica", "B", 17); self.set_text_color(*self.NAVY)
        self.cell(0, 9, s(text), new_x="LMARGIN", new_y="NEXT")
        if sub:
            self.set_font("Helvetica", "", 8); self.set_text_color(*MUTE)
            self.cell(0, 5, s(sub), new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def section(self, text):
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*self.VIO); self.rect(15, y + 0.6, 1.4, 5.2, "F")
        self.set_x(19.5)
        self.set_font("Helvetica", "B", 10.5); self.set_text_color(*self.NAVY)
        self.cell(0, 6.5, s(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def para(self, text, size=8.5, color=INK, h=4.3):
        self.set_font("Helvetica", "", size); self.set_text_color(*color)
        self.multi_cell(180, h, s(text), new_x="LMARGIN", new_y="NEXT")

    def details_box(self, pairs_left, pairs_right):
        y0 = self.get_y()
        rows = max(len(pairs_left), len(pairs_right))
        h = rows * 6 + 4
        self.set_fill_color(*self.TINT); self.set_draw_color(*tint(self.VIO, 0.3))
        self.rect(15, y0, 180, h, "DF")
        for col, pairs in ((0, pairs_left), (1, pairs_right)):
            for i, (k, v) in enumerate(pairs):
                x = 18 + col * 90
                self.set_xy(x, y0 + 2 + i * 6)
                self.set_font("Helvetica", "B", 7.5); self.set_text_color(*MUTE)
                self.cell(24, 6, s(k))
                self.set_font("Helvetica", "", 8.5); self.set_text_color(*INK)
                self.cell(64, 6, s(v)[:52])
        self.set_y(y0 + h + 2)

    def table(self, cols, rows, bold_cols=(), mute_cols=(), zebra=True, size=8.5):
        """cols: [(header, width, align)]. rows: list of lists of strings."""
        self.set_fill_color(*self.NAVY); self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        for h, w, a in cols:
            self.cell(w, 7, s(" " + h + " ") if a == "L" else s(h + " "), align=a, fill=True)
        self.ln(7)
        for i, r in enumerate(rows):
            if self.get_y() > 265:
                self.add_page()
            fill = zebra and i % 2 == 1
            self.set_fill_color(*tint(self.VIO, 0.05))
            for j, (v, (h, w, a)) in enumerate(zip(r, cols)):
                self.set_font("Helvetica", "B" if j in bold_cols else "", size)
                self.set_text_color(*(MUTE if j in mute_cols else INK))
                self.cell(w, 6.6, s(" " + str(v) + " ") if a == "L" else s(str(v) + " "), align=a, fill=fill)
            self.ln(6.6)

    def total_bar(self, label, value):
        self.set_fill_color(*self.NAVY); self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 9.5)
        self.cell(140, 8.5, s("  " + label), fill=True)
        self.cell(40, 8.5, s(value + " "), align="R", fill=True, new_x="LMARGIN", new_y="NEXT")

    def callout(self, head, body):
        y0 = self.get_y() + 2
        self.set_xy(18, y0 + 2)
        self.set_font("Helvetica", "B", 8.5); self.set_text_color(*self.VIO)
        self.multi_cell(174, 4.5, s(head), new_x="LMARGIN", new_y="NEXT")
        self.set_x(18)
        self.set_font("Helvetica", "", 7.8); self.set_text_color(*INK)
        self.multi_cell(174, 4, s(body), new_x="LMARGIN", new_y="NEXT")
        y1 = self.get_y() + 2
        self.set_draw_color(*self.VIO); self.set_line_width(0.35)
        self.rect(15, y0, 180, y1 - y0, "D")
        self.set_line_width(0.2)
        self.set_y(y1 + 1)

    def tiles(self, items, per_row=4):
        w = (180 - (per_row - 1) * 3) / per_row
        for start in range(0, len(items), per_row):
            y0 = self.get_y()
            for i, (k, v) in enumerate(items[start:start + per_row]):
                x = 15 + i * (w + 3)
                self.set_fill_color(*self.TINT); self.set_draw_color(*tint(self.VIO, 0.3))
                self.rect(x, y0, w, 15, "DF")
                self.set_xy(x + 3, y0 + 2)
                self.set_font("Helvetica", "B", 6.5); self.set_text_color(*MUTE)
                self.cell(w - 6, 4, s(k.upper()))
                self.set_xy(x + 3, y0 + 7.5)
                self.set_font("Helvetica", "B", 9); self.set_text_color(*self.NAVY)
                self.cell(w - 6, 5, s(v))
            self.set_y(y0 + 18)

    def bars(self, values, labels, sub=None, h=26):
        if not values:
            return
        n = len(values)
        top = max(values) or 1
        gap = 4
        w = min(32, (180 - gap * (n - 1)) / n)
        y0 = self.get_y() + 2
        base = y0 + h
        for i, v in enumerate(values):
            x = 15 + i * (w + gap)
            bh = max(1.5, h * v / top)
            f = 0.45 + 0.55 * (i / max(1, n - 1))
            self.set_fill_color(*tint(self.VIO, f))
            self.rect(x, base - bh, w, bh, "F")
            self.set_xy(x, base + 1)
            self.set_font("Helvetica", "B", 7.5); self.set_text_color(*INK)
            self.cell(w, 4, s(labels[i]), align="C")
            if sub:
                self.set_xy(x, base + 4.6)
                self.set_font("Helvetica", "", 6.8); self.set_text_color(*MUTE)
                self.cell(w, 3.5, s(sub[i]), align="C")
        self.set_y(base + 10)

    def bullets(self, items, size=8.3):
        for it in items:
            self.set_x(17)
            self.set_font("Helvetica", "", size); self.set_text_color(*MUTE)
            self.cell(4, 4.4, "-")
            self.set_text_color(*INK)
            self.multi_cell(174, 4.4, s(it), new_x="LMARGIN", new_y="NEXT")

    def terms_pages(self, title, terms, provider_line):
        self.add_page()
        self.doc_title(title, provider_line)
        for head, paras in terms:
            if self.get_y() > 258:
                self.add_page()
            self.ln(1.6)
            self.set_fill_color(*self.TINT); self.set_text_color(*self.VIO); self.set_font("Helvetica", "B", 8)
            self.cell(180, 5.2, s("  " + head), fill=True, new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(*INK); self.set_font("Helvetica", "", 7.1)
            for p in paras:
                self.multi_cell(180, 3.5, s(p), align="J", new_x="LMARGIN", new_y="NEXT")
                self.ln(0.6)

    def sign_block(self, heading, left_title, left_lines, right_title, right_lines):
        if self.get_y() > 225:
            self.add_page()
        self.ln(3)
        self.set_fill_color(*self.NAVY); self.set_text_color(255, 255, 255); self.set_font("Helvetica", "B", 8.5)
        self.cell(180, 7, s("  " + heading), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        y0 = self.get_y()
        for col, (t, lines) in enumerate(((left_title, left_lines), (right_title, right_lines))):
            self.set_xy(15 + col * 92, y0)
            self.set_font("Helvetica", "B", 8.3); self.set_text_color(*INK)
            self.cell(88, 5.5, s(t))
            for i, ln in enumerate(lines):
                self.set_xy(15 + col * 92, y0 + 6 + i * 6.2)
                self.set_font("Helvetica", "", 8.3)
                self.cell(88, 6, s(ln))
        self.set_y(y0 + 6 + max(len(left_lines), len(right_lines)) * 6.2 + 2)


def _blank(v, n=24):
    return v if v else "_" * n


def supplier_panel(pdf, sup):
    """'Your supplier' box with the reseller's logo and contact details."""
    y0 = pdf.get_y() + 1
    pdf.set_fill_color(255, 255, 255); pdf.set_draw_color(*tint(pdf.VIO, 0.35))
    pdf.rect(15, y0, 180, 20, "DF")
    x = 19
    lb = sup.get("logo_b64")
    if lb:
        try:
            import base64 as _b64
            pdf.image(io.BytesIO(_b64.b64decode(lb)), x=19, y=y0 + 3, h=14, keep_aspect_ratio=True)
            x = 62
        except Exception:
            pass
    pdf.set_xy(x, y0 + 3); pdf.set_font("Helvetica", "B", 6.8); pdf.set_text_color(*pdf.VIO)
    pdf.cell(80, 4, "YOUR SUPPLIER")
    pdf.set_xy(x, y0 + 7.5); pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*pdf.NAVY)
    pdf.cell(130, 5, s(sup.get("company", "")))
    pdf.set_xy(x, y0 + 12.8); pdf.set_font("Helvetica", "", 7.8); pdf.set_text_color(*MUTE)
    pdf.cell(130, 4, s("  |  ".join(v for v in (sup.get("phone"), sup.get("email"), sup.get("address")) if v))[:120])
    pdf.set_y(y0 + 23)


def cover_page(pdf, cfg, who, title_line, tiles, docs, services=None, prepared_by="", sign=None, highlight=None):
    """Page 1: 'Agreement to proceed'. One signature here accepts every page of the pack - the box to drop the
    Zoho Sign signature field onto (or the on-screen signature when signed in person)."""
    B = cfg["brand"]
    sign = sign or {}
    pdf.label = "AGREEMENT TO PROCEED"
    pdf.add_page()
    pdf.doc_title("Agreement to proceed", title_line)
    pdf.para(f"Thank you for choosing {B['trading']}. This page summarises your agreement. Signing once, at the bottom of this page, "
             "confirms you accept every page in this pack - there is nothing else to sign.")
    pdf.ln(3)
    if getattr(pdf, "supplier", None):
        supplier_panel(pdf, pdf.supplier)
    pdf.tiles(tiles)
    if highlight:
        pdf.callout(*highlight)
    if services:
        pdf.section("What you are ordering")
        pdf.table([("Item", 150, "L"), ("Qty", 30, "C")], [[n, q] for n, q in services], zebra=False)
    pdf.section("What is in this pack")
    pdf.table([("Document", 55, "L"), ("Pages", 25, "C"), ("What it covers", 100, "L")], docs, bold_cols=(0,), zebra=False)

    # declaration + signature panel - kept together at the foot of the page
    need = 70
    if pdf.get_y() + need > 277:
        pdf.add_page()
    else:
        pdf.set_y(max(pdf.get_y() + 4, 277 - need))
    company = who.get("company") or "the business named above"
    pdf.set_fill_color(*pdf.NAVY); pdf.set_text_color(255, 255, 255); pdf.set_font("Helvetica", "B", 9)
    pdf.cell(180, 7.5, s("  Agreement to proceed"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)
    pdf.set_font("Helvetica", "", 8.2); pdf.set_text_color(*INK)
    pdf.multi_cell(180, 4.2, s(f"I am authorised to sign for {company}. I have read and agree to everything in this pack (pages 2 to {{nb}}) "
                               f"and I ask {B['legal']} to proceed."), new_x="LMARGIN", new_y="NEXT")
    y0 = pdf.get_y() + 3
    # signature box
    pdf.set_fill_color(255, 255, 255); pdf.set_draw_color(*pdf.VIO); pdf.set_line_width(0.5)
    pdf.rect(15, y0, 92, 30, "DF")
    pdf.set_line_width(0.2)
    pdf.set_xy(18, y0 + 2); pdf.set_font("Helvetica", "B", 6.8); pdf.set_text_color(*pdf.VIO)
    pdf.cell(60, 4, "CUSTOMER SIGNATURE" if who.get("_kind") != "partner" else "PARTNER SIGNATURE")
    sb = sign.get("sig")
    if sb and len(sb) > 100:
        try:
            pdf.image(io.BytesIO(sb), x=20, y=y0 + 7, w=60, h=20, keep_aspect_ratio=True)
        except Exception:
            pass
    # name / position / company / date
    rows = [("Name", sign.get("name") or who.get("contact", "")), ("Position", sign.get("position") or who.get("position", "")),
            ("Company", who.get("company", "")), ("Date", sign.get("date", ""))]
    for i, (k, v) in enumerate(rows):
        yy = y0 + 1 + i * 7.3
        pdf.set_xy(112, yy); pdf.set_font("Helvetica", "B", 7); pdf.set_text_color(*MUTE)
        pdf.cell(18, 6, s(k.upper()))
        pdf.set_font("Helvetica", "", 8.6); pdf.set_text_color(*INK)
        pdf.cell(65, 6, s(v)[:40])
        pdf.set_draw_color(*LINE); pdf.line(130, yy + 6, 195, yy + 6)
    pdf.set_y(y0 + 33)
    pdf.set_font("Helvetica", "", 7.4); pdf.set_text_color(*MUTE)
    pdf.cell(0, 4.5, s(f"For {B['legal']}:  {_blank(prepared_by, 26)}    Date:  {date.today().strftime('%d/%m/%Y')}"),
             new_x="LMARGIN", new_y="NEXT")


def signed_note(pdf, text):
    pdf.ln(4)
    pdf.set_fill_color(*pdf.TINT); pdf.set_text_color(*pdf.VIO); pdf.set_font("Helvetica", "B", 8)
    pdf.cell(180, 7, s("  " + text), fill=True, new_x="LMARGIN", new_y="NEXT")


# ─────────────────────────── CUSTOMER PACK ───────────────────────────
DD_GUARANTEE = [
    "The Guarantee is offered by all banks and building societies that accept instructions to pay Direct Debits.",
    "If there are any changes to the amount, date or frequency of your Direct Debit, {WHO} will notify you in advance of your account being debited or as otherwise agreed.",
    "If you request {WHO} to collect a payment, confirmation of the amount and date will be given to you at the time of the request.",
    "If an error is made in the payment of your Direct Debit, by {WHO} or your bank or building society, you are entitled to a full and immediate refund of the amount paid from your bank or building society. If you receive a refund you are not entitled to, you must pay it back when {WHO} asks you to.",
    "You can cancel a Direct Debit at any time by simply contacting your bank or building society. Written confirmation may be required. Please also notify {WHO}.",
]


def mandate_page(pdf, cfg, q, cust, bank, sign=None):
    """Direct Debit mandate for the Call Scope monthly charges - bank details, authority, guarantee and a signature box."""
    B = cfg["brand"]
    sign = sign or {}
    bank = bank or {}
    who = B["legal"] or B["trading"]
    pdf.label = "DIRECT DEBIT MANDATE"
    pdf.add_page()
    pdf.doc_title("Direct Debit Mandate", f"For the monthly {B['trading']} charges  |  {who}")
    pdf.details_box([("Business", cust.get("company", "")), ("Contact", cust.get("contact", ""))],
                    [("Email", cust.get("email", "")), ("Telephone", cust.get("phone", ""))])
    pdf.section("Your bank details")
    pdf.details_box([("Bank name", bank.get("bank", "")), ("Account holder", bank.get("holder", ""))],
                    [("Account no.", bank.get("accno", "")), ("Sort code", bank.get("sort", ""))])
    if bank.get("addr"):
        pdf.para("Bank address: " + bank["addr"], size=8, color=MUTE)
    pdf.section("Your instruction")
    amt = money(q["monthly_total"])
    paras = [
        f"I/we instruct my/our bank or building society to pay {who} by Direct Debit the monthly charges for the {B['trading']} "
        f"services on the attached Service Order. The first monthly payment is {amt} + VAT. The amount changes as shown on the "
        f"Price Schedule, and when services are added or removed, and {who} will tell you in advance, as set out in the Guarantee below.",
        "Payments are collected on or around the 1st of each month, starting from the date the services go live.",
    ]
    if q["setup"] and q["setup_mode"] == "invoice":
        paras.append(f"One-off set-up charges ({money(q['setup_total'])} + VAT) are invoiced separately when the Order is accepted "
                     "and are not part of the monthly Direct Debit unless we agree otherwise in writing.")
    for t in paras:
        pdf.para(t)
        pdf.ln(1.5)
    pdf.section("The Direct Debit Guarantee")
    pdf.set_font("Helvetica", "", 7.6); pdf.set_text_color(*INK)
    for t in DD_GUARANTEE:
        pdf.set_x(17)
        pdf.cell(4, 4, "-")
        pdf.multi_cell(174, 4, s(t.replace("{WHO}", who)), new_x="LMARGIN", new_y="NEXT")
    y0 = pdf.get_y() + 6
    if y0 > 235:
        pdf.add_page(); y0 = pdf.get_y() + 4
    pdf.set_fill_color(255, 255, 255); pdf.set_draw_color(*pdf.VIO); pdf.set_line_width(0.5)
    pdf.rect(15, y0, 92, 30, "DF"); pdf.set_line_width(0.2)
    pdf.set_xy(18, y0 + 2); pdf.set_font("Helvetica", "B", 6.8); pdf.set_text_color(*pdf.VIO)
    pdf.cell(70, 4, "ACCOUNT HOLDER SIGNATURE")
    sb = sign.get("sig")
    if sb and len(sb) > 100:
        try:
            pdf.image(io.BytesIO(sb), x=20, y=y0 + 7, w=60, h=20, keep_aspect_ratio=True)
        except Exception:
            pass
    rows = [("Name", sign.get("name") or cust.get("contact", "")), ("Company", cust.get("company", "")),
            ("Date", sign.get("date", ""))]
    for i, (k, v) in enumerate(rows):
        yy = y0 + 4 + i * 8
        pdf.set_xy(112, yy); pdf.set_font("Helvetica", "B", 7); pdf.set_text_color(*MUTE)
        pdf.cell(18, 6, s(k.upper()))
        pdf.set_font("Helvetica", "", 8.6); pdf.set_text_color(*INK)
        pdf.cell(65, 6, s(v)[:40])
        pdf.set_draw_color(*LINE); pdf.line(130, yy + 6, 195, yy + 6)
    pdf.set_y(y0 + 34)


def customer_pack(cfg, q, cust, terms, prepared_by="", sign=None, bank=None, notes=None, price_note="", show_mandate=True):
    """Call Scope pack: Agreement to proceed, Service Order, Price Schedule, Terms & Conditions, Direct Debit mandate.
    terms: [(heading, [paragraphs])] already filled in."""
    B = cfg["brand"]
    q = dict(q, show_review=False)
    pdf = Doc(B, "SERVICE ORDER")
    pdf.supplier = None
    disc = q["discount"] > 0
    stepped = disc and q["style"] == "stepped" and q["years"] > 1
    setup_txt = {"invoice": money(q["setup_total"]), "spread": "Over 12 months", "included": "In equipment deal",
                 "waived": "Waived"}[q["setup_mode"]] if q["setup"] else "None"
    docs = [["Service Order", "2", "Your services, prices and set-up"],
            ["Price Schedule", "3", "How your monthly charge changes each year"],
            ["Terms & Conditions", "4 onwards", f"The {B['trading']} terms for the service"]]
    if show_mandate:
        docs.append(["Direct Debit Mandate", "Last page", "How the monthly charges are paid"])
    cover_page(pdf, cfg, cust, f"{B['trading']} for {cust.get('company') or 'your business'}  |  "
               f"Prepared {date.today().strftime('%d %B %Y')}" + (f" by {prepared_by}" if prepared_by else ""),
               [("Monthly" + (" (year 1)" if stepped else ""), money(q["monthly_total"])), ("Minimum term", f"{q['term']} months"),
                ("One-off set-up", setup_txt), ("Starts", "On go-live")],
               docs, services=[(l["name"], l["qty"]) for l in q["lines"]], prepared_by=prepared_by, sign=sign)
    pdf.label = "SERVICE ORDER"
    pdf.add_page()
    today = date.today().strftime("%d %B %Y")
    pdf.doc_title(f"{B['trading']} Service Order", f"Prepared {today}" + (f"  |  by {prepared_by}" if prepared_by else ""))
    contact = cust.get("contact", "") + (f" - {cust['position']}" if cust.get("position") else "")
    pdf.details_box([("Customer", cust.get("company", "")), ("Contact", contact), ("Email", cust.get("email", ""))],
                    [("Company no.", cust.get("company_no", "")), ("Address", cust.get("address", "")),
                     ("Telephone", cust.get("phone", ""))])
    pdf.section(f"Your {B['trading']} services")
    cols = [("Service", 95, "L"), ("Qty", 15, "C"), ("Standard /mo", 24, "R"), ("Your price /mo", 23, "R"), ("Monthly total", 23, "R")]
    rows = [[l["name"], l["qty"], money(l["rrp"]), money(l["price"]), money(l["total"])] for l in q["lines"]]
    pdf.table(cols, rows, bold_cols=(3, 4), mute_cols=(2,), zebra=False)
    pdf.total_bar("Monthly total at the start of the agreement (excl. VAT)", money(q["monthly_total"]))
    if disc:
        if q["years"] <= 1 or q["style"] == "fixed":
            body = "Applies for the whole of your minimum term - see the Price Schedule on the next page."
            head = f"Your discount: {q['discount']:g}% off the standard price"
        else:
            body = ("Applies for the first 12 months, then reduces in steps to the standard price - "
                    "see the Price Schedule on the next page.")
            head = f"Introductory discount: {q['discount']:g}% off the standard price"
        pdf.callout(head, body)
    for head, body in (notes or []):
        pdf.callout(head, body)
    if q["setup"]:
        pdf.section("One-off set-up")
        cols = [("Item", 130, "L"), ("Qty", 20, "C"), ("Price (excl. VAT)", 30, "R")]
        rows = [[x["name"], x["qty"], money(x["total"])] for x in q["setup"]]
        pdf.table(cols, rows, zebra=False)
        note = {"invoice": "Set-up is invoiced when your Order is accepted.",
                "spread": f"Set-up is spread over your first 12 months: {money(q['setup_list_total'] / 12)} per month on top of the charges above.",
                "waived": "Set-up has been waived for this Order.",
                "included": "Set-up is included in your separate equipment or telephony agreement and spread over its term."}[q["setup_mode"]]
        pdf.set_font("Helvetica", "I", 7.5); pdf.set_text_color(*MUTE)
        pdf.cell(0, 5, s(note), new_x="LMARGIN", new_y="NEXT")
    pdf.section("Your agreement at a glance")
    pdf.tiles([("Minimum term", f"{q['term']} months"), ("Billing", "Monthly in advance"),
               ("Start date", "On go-live"), ("Renewal", f"Rolling {int(cfg['renewal_months'])} months")])
    pdf.set_font("Helvetica", "", 7.5); pdf.set_text_color(*MUTE)
    pdf.multi_cell(180, 4, s(f"This Order is a stand-alone agreement for {B['trading']} services, separate from any telephony or "
                             f"equipment agreement you have with us. The {B['trading']} Terms & Conditions follow the Price Schedule."),
                   new_x="LMARGIN", new_y="NEXT")

    # price schedule
    pdf.label = "PRICE SCHEDULE"
    pdf.add_page()
    pdf.doc_title("Your Price Schedule", f"How your monthly {B['trading']} charges move over your {q['term']}-month agreement")
    sched = q["schedule"]
    std = q["standard_monthly"]
    if q["years"] <= 1 or q["style"] == "fixed" or not disc:
        intro = (f"Your monthly charge is {money(q['monthly_total'])}"
                 + (f", which includes a {q['discount']:g}% discount on your modules (standard price {money(std)} per month)" if disc else "")
                 + f" and applies for your whole {q['term']}-month minimum term.")
    else:
        intro = (f"You are receiving an introductory discount of {q['discount']:g}% on the standard {B['trading']} price. "
                 f"It applies in full for your first 12 months. After that it reduces in equal steps each year, so that in year "
                 f"{q['years']} - the final year of your agreement - you pay the full standard price of {money(std)} per month. "
                 "It does not jump straight to the full price after the first year.")
    pdf.para(intro)
    pdf.ln(3)
    cols = [("Year", 25, "L"), ("Months", 40, "L"), ("Monthly charge", 40, "R"), ("Change on last year", 40, "R"), ("Discount remaining", 35, "R")]
    rows, prev = [], None
    for r in sched:
        mo = r["monthly"]
        ch = "-" if prev is None else ("+ " + money(mo - prev) if mo >= prev else "- " + money(prev - mo))
        dl = "Standard price" if r["discount"] <= 0 else f"{r['discount']:g}% off"
        rows.append([f"Year {r['year']}", f"Months {r['months']}", money(mo), ch, dl])
        prev = mo
    pdf.table(cols, rows, bold_cols=(2,))
    pdf.set_font("Helvetica", "I", 7.5); pdf.set_text_color(*MUTE)
    pdf.cell(0, 5, s(f"All figures are per month, exclude VAT, and apply to the {B['trading']} services listed on your Order."),
             new_x="LMARGIN", new_y="NEXT")
    vals = [r["monthly"] for r in sched]
    pdf.bars(vals, [money(v) for v in vals], [f"Year {r['year']}" for r in sched])
    pdf.section("What this means")
    pts = []
    if stepped:
        pts.append(f"Months 1 to 12: you pay your discounted price of {money(sched[0]['monthly'])} per month.")
        pts.append(f"From month 13 the discount reduces in equal annual steps. By year {q['years']} - the end of your agreement - "
                   "you pay the full standard price.")
    else:
        pts.append(f"Your monthly charge of {money(q['monthly_total'])} applies for the whole minimum term, subject to the price terms below.")
    if price_note:
        pts.append(price_note)
    pts.append("If you add or remove users or modules, this schedule is recalculated in the same way.")
    pdf.bullets(pts)
    signed_note(pdf, "This Order and Price Schedule are accepted by signing the Agreement to proceed on page 1.")

    pdf.label = "TERMS & CONDITIONS"
    pdf.terms_pages(f"{B['trading']} Terms & Conditions", terms,
                    f"Provided by {B['legal']}" + (f"  |  {B['address']}" if B.get("address") else ""))
    if show_mandate:
        mandate_page(pdf, cfg, q, cust, bank, sign)
    return bytes(pdf.output())
'''
_csx = _types.ModuleType("csx_embedded")
exec(compile(_CSX_SRC, "csx_embedded", "exec"), _csx.__dict__)

def cs_brand():
    b = dict(_CS_BRAND_DEFAULT)
    b.update({k: v for k, v in (st.session_state.active_config.get("callscope_brand") or {}).items() if v})
    for _k in ("legal", "address", "email", "website"):       # an empty box in Admin falls back to the Call Scope Ltd details
        b[_k] = b[_k] or _CS_BRAND_DEFAULT[_k]
    if "sycomms.cloud" in str(b.get("website", "")):          # old saved website -> the new one
        b["website"] = _CS_BRAND_DEFAULT["website"]
    return b


def cs_logo_bytes(b=None):
    b = b or cs_brand()
    try:
        if b.get("logo_b64"):
            return base64.b64decode(b["logo_b64"])
    except Exception:
        pass
    try:
        return base64.b64decode(BUNDLED_IMAGES["__CS_LOGO__"][0])
    except Exception:
        return None


def cs_terms_list(term_months=None):
    """[(heading, [paragraphs])] - the Call Scope Terms & Conditions with the brand details filled in."""
    b = cs_brand()
    raw = st.session_state.active_config.get("callscope_terms_text") or _CS_TERMS_DEFAULT
    subs = {"{PROVIDER}": b["legal"], "{BRAND}": b["trading"], "{EMAIL}": b["email"] or "the address on your Order",
            "{TERM}": f"{int(term_months or lease_term)} months"}
    out, cur = [], None
    for line in raw.splitlines():
        if line.startswith("## "):
            cur = [line[3:].strip(), [[]]]
            out.append(cur)
        elif cur is not None:
            if not line.strip():
                if cur[1][-1]:
                    cur[1].append([])
            else:
                cur[1][-1].append(line.strip())
    res = []
    for h, paras in out:
        txt = [" ".join(p) for p in paras if p]
        for k, v in subs.items():
            h = h.replace(k, v)
            txt = [t.replace(k, v) for t in txt]
        res.append((h, txt))
    return res


def merge_pdfs(*parts):
    """Join PDFs end to end (telephony pack first, then Call Scope)."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for src in parts:
        if src:
            for pg in PdfReader(io.BytesIO(src)).pages:
                w.add_page(pg)
    out = io.BytesIO(); w.write(out)
    return out.getvalue()


_CS_PRICE_NOTE = ("Call Scope sets its own prices. The charges are fixed for the first 12 months; after that they may be increased on at least "
                  "30 days' notice, including by removing any introductory discount (see the price clause in the Terms & Conditions).")


def build_callscope_pack(sign=None):
    """The separate Call Scope pack: Agreement to proceed, Service Order, Price Schedule, Terms & Conditions and a Direct Debit mandate.
    sign = {"sig": png bytes or None, "name": str, "date": str}. None if no Call Scope is selected."""
    if not cs_quote:
        return None
    B = cs_brand()
    G = st.session_state.get
    sign = sign or {}
    _csx.LOGO_BYTES = cs_logo_bytes(B)
    cfgx = {"brand": B, "renewal_months": 12, "annual_review_pct": 0.0}
    nm = str(G("q_contact") or "")
    parts = [x.strip() for x in nm.split(" - ", 1)]
    cust = {"company": G("q_comp_name") or "", "contact": parts[0], "position": parts[1] if len(parts) > 1 else "",
            "email": G("q_dir_email") or "", "phone": G("q_phone") or "", "address": G("q_address") or "",
            "company_no": G("q_comp_reg") or ""}
    bank = {"bank": G("q_bank_name") or "", "holder": G("q_acc_holder") or G("q_comp_name") or "", "accno": G("q_acc_no") or "",
            "sort": G("q_sort_code") or "", "addr": G("q_bank_addr") or ""}
    sg = {"sig": sign.get("sig"), "name": sign.get("name") or parts[0], "position": parts[1] if len(parts) > 1 else "",
          "date": sign.get("date", "")}
    return _csx.customer_pack(cfgx, cs_quote, cust, cs_terms_list(cs_quote["term"]), prepared_by=_prepared_by(), sign=sg,
                              bank=bank, notes=cs_notes, price_note=_CS_PRICE_NOTE)




def build_loa_pdf(sig_bytes=None, sig_ts=""):
    """Stand-alone Letter of Authority for the old provider - cut out of the pack so no pricing is ever shared."""
    core = _build_pdf_core(sig_bytes=sig_bytes, sig_timestamp=sig_ts)
    rng = _LOA_PAGES.get("range")
    if not rng:
        return None
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(io.BytesIO(core)); w = PdfWriter()
    for i in range(rng[0] - 1, rng[1]):
        w.add_page(r.pages[i])
    out = io.BytesIO(); w.write(out)
    return out.getvalue()


def build_pdf(sig_bytes=None, sig_name='', sig_company='', sig_timestamp='', sig_ip='', sign_proposal=False, **kw):
    """Full pack = signed 2-page Proposal Summary first, then the paperwork."""
    core = _build_pdf_core(sig_bytes=sig_bytes, sig_name=sig_name, sig_company=sig_company,
                           sig_timestamp=sig_timestamp, sig_ip=sig_ip, **kw)
    try:
        from pypdf import PdfReader, PdfWriter
        prop = build_proposal_pdf(sign={"sig_bytes": (sig_bytes if sign_proposal else None), "name": sig_name,   # blank for the single pack (signed in Zoho Sign); signed in the combined pack
                                        "company": sig_company, "timestamp": sig_timestamp})
        w = PdfWriter()      # Call Scope has its own separate pack (build_callscope_pack) - nothing of it goes in here
        for src in (prop, core):
            if not src:
                continue
            for pg in PdfReader(io.BytesIO(src)).pages:
                w.add_page(pg)
        out = io.BytesIO(); w.write(out)
        return out.getvalue()
    except Exception as _merge_err:
        st.session_state["_pack_merge_error"] = str(_merge_err)[:200]
        return core      # never block the pack if the merge fails


# ─── EMAIL SEND HELPER ───────────────────────────────────────────────────────


# ── Admin panel variable defaults (overridden inside tab7 when unlocked) ──────
# These must be defined before tabs so tab1-tab6 can reference them safely.
# Values are read from session state where widgets write them.
override_customer       = st.session_state.get("mgr_cust", "")
override_initials       = st.session_state.get("mgr_init", "")
override_monthly_lease  = 0.0
override_bb_sell        = float(st.session_state.get("adm_bb_override", 0.0))
override_upfront        = float(st.session_state.get("adm_override_upfront", 0.0))
override_install_cost   = float(st.session_state.get("adm_override_install", 0.0))
credits_months          = int(st.session_state.get("adm_credits_months", 0))
credits_amount          = float(st.session_state.get("adm_credits_amount", 0.0))
cashback_amount         = float(st.session_state.get("adm_cashback", 0.0))


# ─── CALCULATIONS ENGINE (Recurring model - hardware upfront, services monthly) ─

def compute_poe_needed():
    poe = 0
    for name, qty in desktop_quantities.items():
        if HANDSETS_DESKTOP[name]["poe"]:
            poe += qty
    poe += additional_wired_ports
    return poe

def get_recommended_switch(poe_needed):
    if not auto_switch and manual_switch_name:
        return next((s for s in SWITCHES if s["name"] == manual_switch_name), SWITCHES[0])
    # Each desk phone needs 1 POE port (for phone) + 1 standard port (for PC)
    # Total ports needed = poe_needed (phones) + poe_needed (PCs)
    total_ports_needed = poe_needed * 2
    for sw in SWITCHES:
        if sw["poe_ports"] >= poe_needed and sw.get("total_ports", sw["poe_ports"]) >= total_ports_needed:
            return sw
    return SWITCHES[-1]

def compute_hw_buy():
    """Sum of all hardware at wholesale buy price."""
    total = 0.0
    for name, qty in desktop_quantities.items():
        total += HANDSETS_DESKTOP[name]["buy"] * qty
    for name, qty in cordless_quantities.items():
        total += HANDSETS_CORDLESS[name]["buy"] * qty
    for name, qty in headset_quantities.items():
        total += HEADSETS[name]["buy"] * qty
    for name, qty in other_quantities.items():
        _oh_info = OTHER_HARDWARE.get(name)
        if _oh_info: total += _oh_info["buy"] * qty
    if not _no_switch:
        if switch_quantities:  # manual multi-switch
            for _sn, _sq in switch_quantities.items():
                _si = next((s for s in SWITCHES if s["name"] == _sn), None)
                if _si: total += _si["buy"] * _sq
        else:  # auto-select
            poe_n = compute_poe_needed()
            total += get_recommended_switch(poe_n)["buy"]
    if add_router:
        if router_quantities:
            for _rn, _rq in router_quantities.items():
                if _rn in ROUTERS: total += ROUTERS[_rn] * _rq
        elif router_type not in ("None / Customer Supplied", "") and router_type in ROUTERS:
            total += ROUTERS[router_type]
    return total

_CP_KEYS = ("lic", "bb1", "sysrent", "cs", "ac", "accash", "hw", "inst", "bbinst", "desk", "cord", "hs", "other", "switch", "router",
           "bb2", "wall", "mob", "sw", "sec", "it", "prn")

def _cp_saved():
    """South Wales Comms has no per-deal price overrides - everything is cost + 20%."""
    return {}
    try:
        _d = json.loads(st.session_state.get("adm_cp_json") or "{}")
        return _d if isinstance(_d, dict) else {}
    except Exception:
        return {}

def _xm_saved():
    """No extra monthly charge boxes at South Wales Comms."""
    return []
    try:
        _d = json.loads(st.session_state.get("adm_xm_json") or "[]")
        return [(str(x[0]).strip() or "Additional monthly charge", round(float(x[1]), 2)) for x in _d if float(x[1]) > 0]
    except Exception:
        return []

def compute_hw_sell(uplift_pct=None, apply_ov=True):
    """Compute total hardware sell value.
    Falls back to buy x (1 + uplift/100) for items without a sell price.
    Admin can override the customer price of each category for this deal (Per-Deal Overrides): 0 = automatic."""
    if uplift_pct is None:
        uplift_pct = hw_uplift_override
    _up = 1 + hw_uplift_override / 100
    sub = {"desk": 0.0, "cord": 0.0, "hs": 0.0, "other": 0.0, "switch": 0.0, "router": 0.0}
    for name, qty in desktop_quantities.items():
        info = HANDSETS_DESKTOP[name]
        sub["desk"] += info.get("sell", info["buy"] * _up) * qty
    for name, qty in cordless_quantities.items():
        info = HANDSETS_CORDLESS[name]
        sub["cord"] += info.get("sell", info["buy"] * _up) * qty
    for name, qty in headset_quantities.items():
        info = HEADSETS[name]
        sub["hs"] += info.get("sell", info["buy"] * _up) * qty
    for name, qty in other_quantities.items():
        _oh_info2 = OTHER_HARDWARE.get(name)
        if _oh_info2:
            # the automatic "Broadband Router" line is a router for pricing purposes
            sub["router" if name == "Broadband Router" else "other"] += _oh_info2.get("sell", _oh_info2["buy"] * _up) * qty
    # Switch uses uplift; routers use their fixed "Customer sell £" if one is set in Admin, otherwise uplift
    if not _no_switch:
        if switch_quantities:
            for _sn, _sq in switch_quantities.items():
                _si = next((s for s in SWITCHES if s["name"] == _sn), None)
                if _si: sub["switch"] += _si["buy"] * _up * _sq
        else:
            sw = get_recommended_switch(compute_poe_needed())
            sub["switch"] += sw.get("sell", sw["buy"] * _up)
    if add_router:
        if router_quantities:
            for _rn, _rq in router_quantities.items():
                if _rn in ROUTERS: sub["router"] += ROUTER_SELL.get(_rn, ROUTERS[_rn] * _up) * _rq
        elif router_type not in ("None / Customer Supplied", "") and router_type in ROUTERS:
            sub["router"] += ROUTER_SELL.get(router_type, ROUTERS[router_type] * _up)
    # Per-deal manager overrides - the customer price for the whole category, or for all the hardware
    if apply_ov:
        _cp = _cp_saved()
        for _k in ("desk", "cord", "hs", "other", "switch", "router"):
            _ov = _cp.get(_k)
            if _ov is not None and sub[_k] > 0:          # only where the deal actually has that kind of equipment
                sub[_k] = float(_ov)
        if _cp.get("hw") is not None:
            return round(float(_cp["hw"]), 2)
    return round(sum(sub.values()), 2)

def compute_install_cost(apply_ov=True):
    if apply_ov and _cp_saved().get("inst") is not None:
        return float(_cp_saved()["inst"])
    if apply_ov and override_install_cost > 0:
        return override_install_cost         # manager override
    if install_type == "Engineer Install":
        return round(float(C.get("install_engineer", 450.0)) * max(1, int(install_days)), 2)
    return 0.0

def _bb_install_main(apply_ov=True):
    v = ll_install if bb_package == "Leased Line / Other" else BROADBAND[bb_provider][bb_package]["install"]
    if apply_ov and _cp_saved().get("bbinst") is not None:
        return float(_cp_saved()["bbinst"])
    return v


def compute_service_charges(sw_sell=0.0, sw_cost=0.0):
    """Compute all monthly service charges. sw_sell/sw_cost come from software add-ons."""
    uplift   = service_uplift_pct / 100.0
    bb_cost  = BROADBAND[bb_provider][bb_package]["cost"]
    if bb_package == "Leased Line / Other":
        bb_cost = ll_cost
    if bb_package == "Leased Line / Other":
        bb1_sell  = ll_sell                  # bespoke sell price entered by consultant
        bb1_floor = ll_cost                  # bespoke cost is the floor
    elif override_bb_sell > 0:
        bb1_sell  = override_bb_sell         # manager override
        bb1_floor = bb_cost
    else:
        _fixed_s  = BROADBAND[bb_provider][bb_package].get("sell", 0) or 0
        # Fixed sell rate from the broadband price table; cost + uplift only if no sell rate is set
        bb1_sell  = 0.0 if bb_cost == 0.0 else (_fixed_s if _fixed_s > 0 else bb_cost * (1.0 + uplift))
        bb1_floor = bb_cost                  # wholesale - never sell below this
    if bb_care == "Business (+£8/mo)":
        bb1_sell  += 8.0
        bb1_floor += 8.0                     # care charge passed through, not discountable
    bb2_sell = bb2_floor = 0.0
    for _xp, _xq in extra_bb_lines.items():
        _xcost     = BROADBAND[bb_provider][_xp]["cost"]
        _xs        = BROADBAND[bb_provider][_xp].get("sell", 0) or 0
        bb2_sell  += (_xs if _xs > 0 else _xcost * (1.0 + uplift)) * _xq
        bb2_floor += _xcost * _xq
    bb_sell = bb1_sell + bb2_sell

    # Voice channels - fixed sell price from pricebook (Professional Bundle)
    vc_sell_per_seat = C.get("vc_sell_per_seat", 12.00)
    vc_cost_per_seat = C.get("vc_cost_per_seat", 2.95)
    lic_monthly      = total_voice_channels * vc_sell_per_seat

    # Wallboard - computed here to avoid global scope issues
    wallboard_mo_val = wallboard_users * C.get("wallboard_sell", 99.00)

    mobile_sell      = sum(r["sell"] * r["qty"] for r in mobile_rows)
    mobile_cost      = sum(r["cost"] * r["qty"] for r in mobile_rows)
    total_sell       = bb_sell + lic_monthly + wallboard_mo_val + mobile_sell + sw_sell

    return {
        "bb_cost":        bb_cost,
        "bb_sell":        bb_sell,
        "bb1_sell":       bb1_sell,
        "bb2_sell":       bb2_sell,
        "bb1_floor":      bb1_floor,
        "bb2_floor":      bb2_floor,
        "lic_monthly":    lic_monthly,
        "wallboard_mo":   wallboard_mo_val,
        "mobile_sell":    mobile_sell,
        "mobile_cost":    mobile_cost,
        "sw_sell":        sw_sell,
        "sw_cost":        sw_cost,
        "total_sell":     total_sell,
    }


def extra_bb_display():
    """[(package, qty, monthly_total)] for each additional line, after discount.
    Uses the same ratio as the aggregate bb2 price so rows always sum to svc['bb2_sell']."""
    _rows = []
    def _x_list(p):
        _s = BROADBAND[bb_provider][p].get("sell", 0) or 0
        return _s if _s > 0 else BROADBAND[bb_provider][p]["cost"] * (1.0 + service_uplift_pct / 100.0)
    _list_total = sum(_x_list(p) * q for p, q in extra_bb_lines.items())
    _ratio = (svc["bb2_sell"] / _list_total) if _list_total > 0 else 0.0
    for p, q in extra_bb_lines.items():
        _line_list = _x_list(p) * q
        _rows.append((p, q, round(_line_list * _ratio, 2)))
    return _rows

def extra_bb_install_total():
    return sum(BROADBAND[bb_provider][p]["install"] * q for p, q in extra_bb_lines.items())


def mobile_label(r):
    """'EE Unlimited Voice & Data' rather than 'EE EE Unlimited Voice & Data'."""
    net, pkg = str(r.get("network", "")), str(r.get("package", ""))
    return pkg if net and net.lower() in pkg.lower() else f"{net} {pkg}".strip()


def build_comparison_rows():
    """Current vs new monthly cost by category: [(label, current, new)].
    One row per category whenever either side has a value; new services are grouped
    (e.g. all Call Scope in one row). Any remainder goes to "Other" so both columns
    always add up to current_total and total_mo."""
    _cmp = [
        ("Phone System / Hardware",   current_system,  hw_monthly_spread if is_spread else 0.0),
        ("User Licences",             current_hosted,  svc["lic_monthly"]),
        ("Call Charges",              current_calls,   0.0),
        ("Broadband",                 current_bb,      svc["bb_sell"]),
        ("Mobiles",                   current_mobile,  svc.get("mobile_sell", 0.0)),
        ("IT Services / M365",        current_it,      svc.get("it_sell", 0.0)),
        ("Support & Maintenance",     current_support, 0.0),
        ("Software & Add-ons",        0.0,             sw_sell_total + svc.get("wallboard_mo", 0.0)),
        ("Call Scope",                0.0,             svc.get("cs_sell", 0.0)),
        ("System Security",           0.0,             svc.get("sec_sell", 0.0)),
        ("Printing / copiers",        current_printing, printer_monthly + printer_print_est_mo),
        ("Other",                     current_other,   svc.get("xm_sell", 0.0)),
    ]
    rows = [(l, round(cv, 2), round(nv, 2)) for l, cv, nv in _cmp if cv > 0.004 or nv > 0.004]
    _cur_gap = round(current_total - sum(r[1] for r in rows), 2)
    _new_gap = round(total_mo      - sum(r[2] for r in rows), 2)
    if abs(_cur_gap) >= 0.01 or abs(_new_gap) >= 0.01:
        _oth = next((i for i, r in enumerate(rows) if r[0] == "Other"), None)
        if _oth is None:
            rows.append(("Other", _cur_gap, _new_gap))
        else:
            rows[_oth] = ("Other", rows[_oth][1] + _cur_gap, rows[_oth][2] + _new_gap)
    return rows


def compute_pricebook_pl():
    """P&L using exact pricebook formula (verified against P & L Calcs sheet).
    hw_rrp=hw_buy×1.5 | maintenance=0.2×hw_rrp | hw_srrp=hw_sell×1.5
    sub_total=cos_ex+hw_srrp | rental=(sales_rate/1000)×sub_total
    disc_turnover=(rental/true_rate)×1000 | gp=disc_turnover-cos_full
    commission=(gp/1000)×1000
    """
    # LEASE_RATES is {months: sales_rate}, TRUE_LEASE_RATES is {months: true_rate}
    _fallback_lr = {36: (39.45, 31.56), 60: (26.26, 21.01), 84: (20.58, 16.46), 24: (46.94, 37.5)}
    sales_rate = LEASE_RATES.get(lease_term, _fallback_lr.get(lease_term, (20.58, 16.46))[0])
    true_rate  = TRUE_LEASE_RATES.get(lease_term, _fallback_lr.get(lease_term, (20.58, 16.46))[1])
    _hw_buy    = compute_hw_buy()
    _hw_sell   = compute_hw_sell()
    hw_rrp     = _hw_buy  * 1.5
    hw_srrp    = _hw_sell * 1.5
    maintenance_normal = 0.2 * hw_rrp
    maintenance_annual = 0.0 if _maint_optout() else maintenance_normal      # opt-out: no maintenance provided, charged or costed
    cos_ex     = maintenance_annual + 200.0 + compute_install_cost() + termination_cost + extra_costs_total + 400.0
    # A blank quote (nothing selected at all) carries no costs - the fixed £200 / £400 / install only
    # start to count once something is actually on the deal.
    try:
        _blank = (_hw_sell <= 0 and _hw_buy <= 0 and termination_cost <= 0 and extra_costs_total <= 0
                  and not (globals().get("AC") or {}).get("listed")
                  and float(svc.get("total_sell", 0) or 0) <= 0 and extra_bb_install_total() <= 0
                  and not printer_rows and not (st.session_state.get("c_desired_rental") or 0) > 0)
    except Exception:
        _blank = False
    if _blank:
        maintenance_annual = 0.0
        cos_ex = 0.0
    sub_total  = cos_ex + hw_srrp
    rental     = (sales_rate / 1000.0) * sub_total
    disc_turn  = (rental / true_rate) * 1000.0
    cos_full   = cos_ex + _hw_buy
    gp         = disc_turn - cos_full
    units      = gp / float(commission_unit_size or 1000)
    return {
        "gross_profit": round(gp, 2), "comm_units": round(units, 3),
        "commission": round(units * 1000, 2), "rental": round(rental, 2),
        "disc_turnover": round(disc_turn, 2), "sub_total": round(sub_total, 2),
        "hw_srrp": round(hw_srrp, 2), "maintenance_annual": round(maintenance_annual, 2), "maintenance_normal": round(maintenance_normal, 2),
        "cos_full": round(cos_full, 2), "sales_rate": sales_rate, "true_rate": true_rate,
    }

def compute_pat(svc):
    """Legacy - returns gross_profit from pricebook P&L formula as PAT proxy."""
    return compute_pricebook_pl()["gross_profit"]

# ── Compute everything ────────────────────────────────────────────────────────
poe_needed = compute_poe_needed()
rec_switch = get_recommended_switch(poe_needed)
hw_buy     = compute_hw_buy()
hw_sell    = compute_hw_sell()
svc        = compute_service_charges(sw_sell=sw_sell_total, sw_cost=sw_cost_total)

# BB free year: compute Year 1 total (£0 BB) for customer display
bb_free_year   = st.session_state.get("q_bb_free_year", False)
_bb_full_sell  = svc["bb_sell"]                                   # standard BB sell price
_bb_yr1_sell   = 0.0 if bb_free_year else _bb_full_sell          # £0 in year 1 if promo
_bb_yr1_saving = _bb_full_sell if bb_free_year else 0.0          # saving in yr1

# Add Call Scope services + Security to total monthly
_cs_svc_sell  = sum(r["sell"] * r["qty"] for r in cs_svc_rows)
_cs_svc_cost  = sum(r["buy"]  * r["qty"] for r in cs_svc_rows)
_sec_svc_sell = sum(r["sell"] * r["qty"] for r in sec_rows)
_sec_svc_cost = sum(r["buy"]  * r["qty"] for r in sec_rows)
svc["cs_sell"]  = _cs_svc_sell
svc["sec_sell"] = _sec_svc_sell
# IT Services (M365, Exclaimer, support etc.) are billed monthly, so they belong in the total
_it_svc_sell = round(sum(r["sell"] * r["qty"] for r in it_rows), 2)
_it_svc_cost = round(sum(r["cost"] * r["qty"] for r in it_rows), 2)
svc["it_sell"] = _it_svc_sell
svc["total_sell"] = svc["total_sell"] + _cs_svc_sell + _sec_svc_sell + _it_svc_sell

# ── Consultant services discount (0-40% slider in Consultant tab) ─────────────
# Applies to hosted user licences, software add-ons and broadband (broadband is capped
# at wholesale cost). Mobiles are not discountable. Commission is reduced by the same %.
_total_list_pre = float(svc["total_sell"])     # monthly services at list price, before any discount
svc_disc_pct  = 0.0
_svc_mult     = 1.0 - svc_disc_pct / 100.0
bb_disc_pct   = 0.0   # separate broadband discount, up to 10%
_bb_mult      = 1.0 - bb_disc_pct / 100.0
cs_disc_pct   = 0.0   # Call Scope services, up to 50%
_cs_mult      = 1.0 - cs_disc_pct / 100.0
_cs_list_total = float(_cs_svc_sell)
lic_list_total = float(svc["lic_monthly"])          # undiscounted, for consultant display
bb1_list       = float(svc["bb1_sell"])
bb2_list       = float(svc["bb2_sell"])
sw_list_total  = float(sw_sell_total)               # undiscounted, for consultant display
if cs_disc_pct > 0:
    for _r in cs_svc_rows:                       # discount the Call Scope rows themselves so every document agrees
        _r["sell"] = max(round(_r["sell"] * _cs_mult, 2), float(_r.get("buy") or 0))
    _cs_svc_sell = sum(r["sell"] * r["qty"] for r in cs_svc_rows)
    svc["cs_sell"] = _cs_svc_sell
# ═══ CALL SCOPE ORDER - priced on its own, never added into the telephony totals, lease, P&L or paperwork ═══
cs_quote = None
cs_auto_monthly = 0.0
cs_target_note = ""
cs_notes = []
cs_crm_missing = False
if cs_order_rows:
    _cs_mods = []
    for _i, _r in enumerate(cs_order_rows):
        _mid = "receptionist" if _r["name"] == "AI Receptionist" else f"m{_i}"
        _cs_mods.append({"id": _mid, "name": _r["name"], "unit": "", "buy": float(_r["buy"]), "wholesale": 0.0,
                         "rrp": float(_r["sell"]), "discountable": not _r.get("minutes"), "qty": int(_r["qty"])})
    _plat = OTHER_HARDWARE.get("Call Scope Platform Setup", {"buy": 300.0, "sell": 500.0})
    _recs = OTHER_HARDWARE.get("Call Scope AI Receptionist Setup (one-off)", {"buy": 69.0, "sell": 100.0})
    _cs_cfgx = {"modules": [{k: v for k, v in m.items() if k != "qty"} for m in _cs_mods],
                "minutes": {"buy_per_min": 0.0, "rrp_per_min": 0.0},
                "setup": [{"id": "platform", "name": "Call Scope Platform Setup", "buy": float(_plat["buy"]), "rrp": float(_plat["sell"])},
                          {"id": "rec_setup", "name": "AI Call Answer Setup", "buy": float(_recs["buy"]), "rrp": float(_recs["sell"])}],
                "annual_review_pct": 0.0}
    cs_disc_eff = float(cs_disc_pct)
    cs_target_note = ""
    _disc_tot = sum(m["rrp"] * m["qty"] for m in _cs_mods if m["discountable"])
    _fix_tot = sum(m["rrp"] * m["qty"] for m in _cs_mods if not m["discountable"])
    def _cs_total_at(_d, _floor=True):          # monthly total at discount _d%, each item held at or above its buy price when _floor
        return round(_fix_tot + sum(max(round(m["rrp"] * (1 - _d / 100), 2), m["buy"] if _floor else 0.0) * m["qty"]
                                    for m in _cs_mods if m["discountable"]), 2)
    def _cs_solve(tgt, _floor=True):
        if _disc_tot <= 0:
            return None, "no discountable items"
        if tgt >= _cs_total_at(0.0, _floor):
            return 0.0, "above the standard price - quoted at standard"
        if tgt <= _cs_total_at(80.0, _floor):
            return 80.0, ("at the lowest price allowed (down to our buy price)" if _floor else "below the 80% discount limit - quoted at the lowest allowed")
        _lo, _hi = 0.0, 80.0
        for _ in range(40):
            _mid = (_lo + _hi) / 2
            if _cs_total_at(_mid, _floor) > tgt:
                _lo = _mid
            else:
                _hi = _mid
        return round(_hi, 2), ""
    _cs_tgt = float(st.session_state.get("cs_target_rental") or 0)
    if _cs_tgt > 0:
        if _disc_tot > 0 and _cs_tgt > _cs_total_at(0.0):
            # a target ABOVE the standard price: the Call Scope prices are raised in proportion to reach it
            _k_up = (_cs_tgt - _fix_tot) / _disc_tot
            for _m in _cs_mods:
                if _m["discountable"]:
                    _m["rrp"] = round(_m["rrp"] * _k_up, 2)
            _cs_cfgx["modules"] = [{k: v for k, v in m.items() if k != "qty"} for m in _cs_mods]
            _disc_tot = sum(m["rrp"] * m["qty"] for m in _cs_mods if m["discountable"])
            cs_target_note = "target price above standard"
        else:
            _dd, cs_target_note = _cs_solve(_cs_tgt)
            if _dd is not None:
                cs_disc_eff = _dd
    cs_auto_monthly = _cs_total_at(cs_disc_eff)     # before any admin override
    _cs_ov = _cp_saved().get("cs")
    if _cs_ov is not None:
        _dd, cs_target_note = _cs_solve(float(_cs_ov), False)      # an admin price may go below our buy price - their call
        if _dd is not None:
            cs_disc_eff = _dd
        cs_target_note = ("admin price: " + cs_target_note) if cs_target_note else ""
    cs_quote = _csx.customer_quote(
        _cs_cfgx, {m["id"]: m["qty"] for m in _cs_mods}, term=int(st.session_state.get("cs_term", 36) or 36),
        discount=cs_disc_eff, style=("fixed" if str(st.session_state.get("cs_style", "")).startswith("Fixed") else "stepped"),
        review_pct=0.0, setup_mode=("waived" if st.session_state.get("cs_setup_waive") else "invoice"), floor=(_cs_ov is None))
    for _l in cs_quote["lines"]:
        if _l["name"] == "AI Receptionist":
            _l["name"] = "AI Receptionist"
    _crm_n = str(st.session_state.get("cs_crm_name", "") or "").strip()
    if int(st.session_state.get("cs_AI Integration - CRM", 0) or 0) > 0:
        if _crm_n:
            cs_notes.append(("Customer's CRM", f"AI CRM Integration is set up for: {_crm_n}."))
        else:
            cs_crm_missing = True
    if st.session_state.get("cs_ai_portal_free", False):
        cs_notes.append(("Promotion: AI Portal first month free",
                         "The first month of the AI Portal 500-minute bundle is free of charge."))
cs_active = bool(cs_quote)
if not cs_order_rows:
    cs_target_note = ""
_tele_any = bool(desktop_quantities or cordless_quantities or headset_quantities or other_quantities
                 or standalone_softphones > 0 or float(svc["total_sell"]) > 0)

if svc_disc_pct > 0 or bb_disc_pct > 0 or cs_disc_pct > 0:
    SW_ADDONS = [(n, q, c, round(sell * _svc_mult, 2)) for n, q, c, sell in SW_ADDONS]
    sw_sell_total = sum(qty * sell for _, qty, _, sell in SW_ADDONS if qty > 0)
    svc["sw_sell"]     = sw_sell_total
    svc["lic_monthly"] = round(lic_list_total * _svc_mult, 2)
    # Broadband: discounted, but NEVER below wholesale cost (per line)
    if bb1_list > 0:
        svc["bb1_sell"] = round(max(bb1_list * _bb_mult, svc["bb1_floor"]), 2)
    if bb2_list > 0:
        svc["bb2_sell"] = round(max(bb2_list * _bb_mult, svc["bb2_floor"]), 2)
    svc["bb_sell"]     = svc["bb1_sell"] + svc["bb2_sell"]
    svc["total_sell"]  = (svc["bb_sell"] + svc["lic_monthly"] + svc.get("wallboard_mo", 0.0) +
                          svc.get("mobile_sell", 0.0) + sw_sell_total +
                          _cs_svc_sell + _sec_svc_sell + _it_svc_sell)
# ── Manager overrides of the customer's monthly prices (Admin - Per-Deal Overrides - Customer prices) ──
# Applied to the list total as well as the final one, so an override never counts as a "discount" against commission.
_cp = _cp_saved()
_cp_auto = {"sysrent": 0.0, "lic": float(svc["lic_monthly"]), "bb1": float(svc["bb1_sell"]), "cs": float(cs_auto_monthly),
            "ac": float(ac_quote["calc_rental"]) if ac_quote else 0.0, "accash": float(ac_quote["cash_list"]) if ac_quote else 0.0}
_cp_auto.update({"bb2": float(svc["bb2_sell"]), "wall": float(svc.get("wallboard_mo", 0.0)), "mob": float(svc.get("mobile_sell", 0.0)),
                 "sw": float(svc.get("sw_sell", 0.0)), "sec": float(svc.get("sec_sell", 0.0)), "it": float(svc.get("it_sell", 0.0)), "prn": 0.0})
def _cp_rescale(rows, target):
    """Spread a forced monthly total across the line items so every document shows lines that add up to it exactly."""
    _tot = sum(r["sell"] * r["qty"] for r in rows)
    if _tot <= 0 or not rows:
        return
    _k = target / _tot
    for r in rows:
        r["sell"] = round(r["sell"] * _k, 2)
    _diff = round(target - sum(r["sell"] * r["qty"] for r in rows), 2)
    if abs(_diff) >= 0.005:
        _one = next((r for r in rows if r["qty"] == 1), None)
        if _one is not None:
            _one["sell"] = round(_one["sell"] + _diff, 2)
        else:
            rows[0]["sell"] = round(rows[0]["sell"] + _diff / rows[0]["qty"], 2)
_cp_delta = 0.0
if _cp.get("lic") is not None:
    _n = round(float(_cp["lic"]), 2); _cp_delta += _n - svc["lic_monthly"]; svc["lic_monthly"] = _n
if _cp.get("bb1") is not None:
    _n = round(float(_cp["bb1"]), 2); _cp_delta += _n - svc["bb1_sell"]; svc["bb1_sell"] = _n
    svc["bb_sell"] = svc["bb1_sell"] + svc["bb2_sell"]
for _ck, _sk in (("bb2", "bb2_sell"), ("wall", "wallboard_mo"), ("mob", "mobile_sell"), ("sw", "sw_sell"), ("sec", "sec_sell"), ("it", "it_sell")):
    if _cp.get(_ck) is not None and float(svc.get(_sk, 0) or 0) > 0:          # only where the deal actually has that item
        _n = round(float(_cp[_ck]), 2); _cp_delta += _n - float(svc[_sk]); svc[_sk] = _n
        if _ck == "bb2":
            svc["bb_sell"] = svc["bb1_sell"] + svc["bb2_sell"]
        elif _ck == "mob":
            _cp_rescale(mobile_rows, _n)
        elif _ck == "sec":
            _cp_rescale(sec_rows, _n)
        elif _ck == "it":
            _cp_rescale(it_rows, _n)
        elif _ck == "sw":
            _swr = [{"sell": s_, "qty": q_, "n": n_, "c": c_} for n_, q_, c_, s_ in SW_ADDONS if q_ > 0]
            _cp_rescale(_swr, _n)
            _sw_new = {r["n"]: r["sell"] for r in _swr}
            SW_ADDONS = [(n_, q_, c_, _sw_new.get(n_, s_) if q_ > 0 else s_) for n_, q_, c_, s_ in SW_ADDONS]
            sw_sell_total = _n
XM_ROWS = _xm_saved()
svc["xm_sell"] = round(sum(a for _, a in XM_ROWS), 2)
_cp_delta += svc["xm_sell"]
if _cp_delta:
    svc["total_sell"] = svc["total_sell"] + _cp_delta
    _total_list_pre   = _total_list_pre + _cp_delta
# Commission lost = the share of the deal's monthly services that is given away. Each discount is weighted by
# how big its category is, so 50% off a small Call Scope order costs far less than 50% off all the licences.
_disc_given_mo  = max(0.0, _total_list_pre - float(svc["total_sell"]))
comm_loss_pct   = min(100.0, 100.0 * _disc_given_mo / _total_list_pre) if _total_list_pre > 0 else 0.0
pat_base   = compute_pat(svc)
pl_data    = compute_pricebook_pl()  # full pricebook P&L breakdown

is_lease   = ("Lease" in payment_model)
is_inhouse = ("In-house" in payment_model)
is_spread  = is_lease or is_inhouse      # customer pays for the hardware monthly (finance lease OR in-house rental)
HW_WORD    = "System rental" if is_inhouse else "Hardware lease"
inhouse_price = 0.0

if is_lease:
    # Use pricebook lease rental formula
    hw_monthly_spread = pl_data["rental"]
    total_mo   = svc["total_sell"] + hw_monthly_spread
    upfront    = 0.0
    pat        = pat_base
else:
    # Upfront: compute hw_sell at upfront uplift % (default 20%, not lease uplift)
    hw_sell    = compute_hw_sell(uplift_pct=hw_uplift_upfront_override)
    hw_monthly_spread = 0.0
    _bb_inst   = _bb_install_main()
    upfront    = hw_sell + compute_install_cost() + _bb_inst + extra_bb_install_total() + termination_cost + extra_costs_total
    if override_upfront > 0:
        upfront = override_upfront           # manager override
    total_mo   = svc["total_sell"]
    pat        = pat_base
    if is_inhouse:
        # In-house: same price as an upfront purchase, but spread evenly over the service term.
        # No finance company and no lease agreement - the customer simply pays it monthly to us.
        inhouse_price     = upfront
        hw_monthly_spread = round(inhouse_price / max(1, lease_term), 2)
        upfront           = 0.0
        total_mo          = svc["total_sell"] + hw_monthly_spread
# ── Consultant desired rental - adjusts lease amount and commission ───────────
deal_type = ("In-house System Rental (upfront price spread over term)" if is_inhouse else "Hardware Lease (spread over term)") if is_spread else f"Upfront Purchase (cost + {hw_uplift_upfront_override:.0f}% uplift)"
base_rental   = pl_data["rental"]      # the calculated lease rental (floor/reference)
st.session_state["_prev_base_rental"] = round(base_rental, 2)
true_rate     = pl_data["true_rate"]

_cp_auto["sysrent"] = float(hw_monthly_spread) if is_inhouse else float(base_rental)
# Read consultant's desired rental from session state (default = calculated rental)
# The rental the customer is quoted: the manager's "what the customer pays" figure wins, then the consultant's target, else the calculated rental.
_sr_ov      = _cp_saved().get("sysrent")
_eff_target = float(_sr_ov) if _sr_ov is not None else float(st.session_state.get("c_desired_rental", 0.0) or 0.0)
_inhouse_calc = hw_monthly_spread if is_inhouse else 0.0       # in-house system rental as calculated: price / term
if is_inhouse:
    base_rental = _inhouse_calc                                  # the reference for an in-house deal is its own calculated system rental
    if _eff_target > 0:
        hw_monthly_spread = round(_eff_target, 2)
        total_mo          = svc["total_sell"] + hw_monthly_spread
    _desired_rental = hw_monthly_spread
else:
    _desired_rental = _eff_target
    if _desired_rental <= 0:
        _desired_rental = base_rental      # default to calculated if not set

# Recalculate GP and commission from desired rental
# Formula: disc_turnover = (desired_rental / true_rate) × 1000
# GP = disc_turnover - cos_full
_desired_disc_turnover = (_desired_rental / true_rate) * 1000 if true_rate > 0 else 0
# ONE RULE for lease value, max termination and lease profit - the "base rental":
#   * no target rental -> the equipment-only calculated rental (the customer's rental still rises to cover
#     any buyout, but that uplift is NOT counted as value or profit, so a buyout can't lift its own limit)
#   * target rental    -> the consultant's rental, counted in full (their choice to add value to the deal)
# The buyout then comes straight off lease profit.
_buyout_rental_share   = (pl_data["sales_rate"] / 1000.0) * termination_cost
_calc_rental_ex_buyout = (pl_data["sales_rate"] / 1000.0) * max(0.0, pl_data["sub_total"] - termination_cost)
_target_active         = _eff_target > 0 and abs(_desired_rental - base_rental) > 0.01
# Value for the max = equipment rental, plus any rental ABOVE what is needed to cover the buyout.
# Continuous: at the pricebook rental it equals the equipment-only rental; a target below the
# buyout-covering rental gives the same; every pound above that raises the max.
_lv_rental             = max(_calc_rental_ex_buyout, _desired_rental - _buyout_rental_share)
_lv_equipment_only     = _lv_rental                       # equipment-only value rental (kept for the info line)
if _target_active:
    _lv_rental = _desired_rental                          # consultant's target rental counts in full: what the funder pays for THIS deal
_buyout_funding        = max(0.0, _desired_rental - _lv_rental)       # rental that funds the buyout (info only)
# Profit counts ALL the funder money; cos_full already contains the buyout, so it comes off once.
_profit_disc_turnover  = (_desired_rental / true_rate) * 1000 if true_rate > 0 else 0
if is_inhouse:
    _profit_disc_turnover = hw_monthly_spread * lease_term     # in-house: no funder - the customer pays the system rental to us over the term
elif not is_lease:
    _profit_disc_turnover = float(upfront)                     # upfront: no funder, no rental - the customer pays it all now
_adjusted_gp           = _profit_disc_turnover - pl_data["cos_full"]
_gp_before_buyout      = _adjusted_gp + termination_cost
# Lease value = what the funder pays for the lease at the rental in the deal (incl. any target rental);
# the most we'd put towards settling a customer's existing agreement is a % of it (default 70%).
MAX_TERMINATION_PCT = float(C.get("max_termination_pct", 70))
# Lease value = what the FUNDER PAYS (rental / funder rate x 1000) - the cash a settlement comes out of.
#   * No target rental: the equipment-only calculated rental, with any buyout taken out (so a buyout can't
#     raise its own limit).
#   * Target rental set: the consultant's rental - more value in the deal raises the maximum. A buyout
#     doesn't move a target rental, so there's no circularity.
lease_value_ex_buyout  = (round(_lv_rental / true_rate * 1000.0, 2)
                          if (is_lease and true_rate > 0) else 0.0)
_customer_total_ex_buyout = round(_calc_rental_ex_buyout * lease_term, 2) if is_lease else 0.0
lease_value            = lease_value_ex_buyout
max_termination        = round(lease_value_ex_buyout * MAX_TERMINATION_PCT / 100.0, 2)
termination_over       = is_lease and (termination_cost - max_termination) >= 1.0            # £1 tolerance for rounding
# ── Safeguards when a target rental is in play ───────────────────────────────
_rental_to_cover     = _calc_rental_ex_buyout + _buyout_rental_share        # rental that fully covers the buyout
rental_short_of_buyout = (round(_rental_to_cover - _desired_rental, 2)
                          if (is_lease and _target_active and termination_cost > 0
                              and _rental_to_cover - _desired_rental >= 0.01) else 0.0)
# Largest buyout that keeps lease profit at or above zero at the rental in the deal (never above the max)
safe_buyout          = round(max(0.0, min(max_termination, _gp_before_buyout)), 2) if is_lease else 0.0
safe_buyout_limited  = is_lease and (max_termination - safe_buyout) >= max(100.0, 0.01 * max_termination)   # ignore trivial gaps
lease_profit_negative = is_lease and _adjusted_gp < -0.5
# ── Likelihood to pass finance: funded value per handset ────────────────────
# Rule of thumb: up to £1,500 per handset is comfortable, up to £2,000 is a stretch, above that is
# likely to be rejected. Stops a deal being "pumped" with a huge target rental. (Admin-adjustable.)
FIN_OK_PER_HANDSET  = float(C.get("finance_ok_per_handset", 1500))
FIN_MAX_PER_HANDSET = float(C.get("finance_max_per_handset", 2000))
fin_handsets        = int(sum(desktop_quantities.values()) + sum(q for n, q in cordless_quantities.items() if _is_user_handset(n)))
fin_funded          = (_desired_rental / true_rate * 1000.0) if (is_lease and true_rate > 0) else 0.0
fin_per_handset     = (fin_funded / fin_handsets) if fin_handsets > 0 else 0.0
fin_band            = ("none" if (not is_lease or fin_handsets == 0) else
                       "good" if fin_per_handset <= FIN_OK_PER_HANDSET else
                       "stretch" if fin_per_handset <= FIN_MAX_PER_HANDSET else "unlikely")
fin_rental_ok       = FIN_OK_PER_HANDSET  * fin_handsets * true_rate / 1000.0   # rental at the comfortable limit
fin_rental_max      = FIN_MAX_PER_HANDSET * fin_handsets * true_rate / 1000.0   # rental at the upper limit
termination_over_pct   = (max(1.0, round((termination_cost - max_termination) / max_termination * 100.0, 0))
                          if (termination_over and max_termination > 0) else 0.0)
# ── Printers: separate lease on its own term + estimated print charges ─────
PRN_UPLIFT     = float(st.session_state.get("prn_uplift", C.get("printer_uplift_pct", 100)))
PRN_CPC_UPLIFT = float(st.session_state.get("prn_cpc_uplift", C.get("printer_cpc_uplift_pct", 100)))
printer_term   = int(st.session_state.get("prn_term", 60) or 60)
for _r in printer_rows:
    _r["sell"]     = round(_r["cost"] * (1 + PRN_UPLIFT / 100.0), 2)
    _r["cpc_sell"] = round(_r["cpc_cost"] * (1 + PRN_CPC_UPLIFT / 100.0), 3)      # pence per print
    _r["print_mo"] = round(_r["volume"] * _r["cpc_sell"] / 100.0, 2)               # £/month estimate
printer_count        = sum(_r["qty"] for _r in printer_rows)
printer_setup        = round(PRINTER_SETUP_CHARGE * printer_count, 2)
printer_capital      = round(sum(_r["sell"] * _r["qty"] for _r in printer_rows) + printer_setup, 2)
_prn_sr              = float(LEASE_RATES.get(printer_term) or LEASE_RATES.get(60) or 26.26)
_prn_tr              = float(TRUE_LEASE_RATES.get(printer_term) or TRUE_LEASE_RATES.get(60) or 21.01)
printer_monthly      = round(printer_capital * _prn_sr / 1000.0, 2)
printer_print_est_mo = round(sum(_r["print_mo"] for _r in printer_rows), 2)
_cp_auto["prn"] = round(printer_monthly + printer_print_est_mo, 2)
if _cp_saved().get("prn") is not None and printer_rows:          # manager's forced printing price (lease + estimated prints); profit follows it
    printer_monthly = round(max(0.0, float(_cp_saved()["prn"]) - printer_print_est_mo), 2)
printer_funder       = round(printer_monthly / _prn_tr * 1000.0, 2) if _prn_tr else 0.0
printer_cost_total   = round(sum(_r["cost"] * _r["qty"] for _r in printer_rows) + PRINTER_SETUP_COST * printer_count, 2)
printer_lease_profit = round(printer_funder - printer_cost_total, 2)
printer_print_margin_mo = round(sum(_r["volume"] * (_r["cpc_sell"] - _r["cpc_cost"]) / 100.0 for _r in printer_rows), 2)

# Units: phone lease profit + printer lease profit, the same way (print margin, like service margin, isn't included)
commission_units       = (_adjusted_gp + printer_lease_profit) / float(commission_unit_size or 1000)
commission             = round(commission_units * commission_per_unit, 2)
st.session_state["_prev_commission_units"] = round(commission_units, 2)
st.session_state["_prev_true_rate"]        = pl_data["true_rate"]
st.session_state["_prev_cos_full"]         = pl_data["cos_full"]
# Services discount removes the same % of commission (e.g. 10% discount = -10% commission)
commission_full        = commission
_comm_mult = max(0.0, 1.0 - comm_loss_pct / 100.0)
if (svc_disc_pct > 0 or bb_disc_pct > 0 or cs_disc_pct > 0) and commission > 0:
    commission_units   = commission_units * _comm_mult
    commission         = round(commission * _comm_mult, 2)
commission_lost        = round(commission_full - commission, 2)

# Rental adjustment (vs calculated) - can be positive (premium) or negative (discount)
rental_adjustment = _desired_rental - base_rental

# In lease mode, use desired_rental as the actual hw_monthly_spread
if is_lease:
    hw_monthly_spread = _desired_rental
# the air-conditioning part of that lease (its own Shire Leasing agreement): the share of the hardware sell value
AC_SHIRE_RENTAL = 0.0
if is_lease and AC["listed"]:
    _ac_sell = AC["equip_sell"] + (AC["inst_sell"] if AC["inst_needed"] else 0.0)
    _hw_all = max(compute_hw_sell(apply_ov=False), _ac_sell, 0.01)
    AC_SHIRE_RENTAL = round(hw_monthly_spread * _ac_sell / _hw_all, 2)
if is_lease:
    total_mo          = svc["total_sell"] + hw_monthly_spread

total_mo = round(total_mo + printer_monthly + printer_print_est_mo, 2)

base_total_mo = total_mo
rate_uplift   = rental_adjustment  # for display purposes
adjusted_pat  = _adjusted_gp + printer_lease_profit
pat           = _adjusted_gp + printer_lease_profit   # warnings use the real deal profit, incl. printer leases

# Aliases for PDF / legacy references
kit_cost    = hw_buy
lease_mo    = hw_monthly_spread  # used in PDF as "Hardware Monthly" when spread
rec_upfront = upfront

# Pure connectivity cost - broadband + mobile only (for Commercial Summary card)
pure_connectivity = round(svc["bb_sell"] + svc["mobile_sell"], 2)

# SGP / sales comms
# SGP / sales comms
sgp          = pat * 0.10



with st.container(key="card-quote"):
    section_header("02", "Quote & paperwork", "Check the proposal, review the numbers and produce the documents")
    _cu_role = (st.session_state.get("current_user") or {}).get("role")
    _show_admin = (not _USERS) or (_cu_role == "admin")      # consultants never see the Admin tab
    _tab_names = ["📄 Proposal Summary", "🖋️ Order Form Preview", "📥 Download Documents", "👤 Customer View", "💼 Consultant", "✍️ Sign & Send"]
    if _show_admin:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(_tab_names + ["🔐 Admin"])
    else:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(_tab_names); tab7 = None

# ── TAB 1: PROPOSAL SUMMARY ──────────────────────────────────────────────────
def solution_totals():
    """Monthly and one-off figures for every agreement on the deal (each its own company), excluding VAT."""
    mo, one = [], []
    if _tele_any:
        mo.append((f"{_CO} - telephony and services", float(total_mo)))
        if (not is_spread) and upfront and upfront > 0:
            one.append((f"{_CO} - hardware (one-off)", float(upfront)))
    if cs_active and not cs_crm_missing:
        mo.append((cs_brand()["trading"], float(cs_quote["monthly_total"])))
        if cs_quote["setup_mode"] != "waived":
            _s = sum(x["total"] for x in cs_quote["setup"])
            if _s > 0:
                one.append((f"{cs_brand()['trading']} - set-up", float(_s)))
    if ac_active:
        if ac_quote["is_cash"]:
            one.append((f"{st_company()['trading']} (one-off)", float(ac_quote["cash_price"])))
        else:
            mo.append((st_company()["trading"], float(ac_quote["rental"])))
    return mo, one


def _kv_row(label, val, colour="var(--text)"):
    st.markdown(f"<div style='display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid var(--border);font-size:0.88rem'>"
                f"<span style='color:var(--muted)'>{esc(label)}</span><span style='color:{colour};font-weight:500;text-align:right'>{esc(val)}</span></div>",
                unsafe_allow_html=True)


def _big_total(label, value, sub=""):
    return (f'<div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);margin-bottom:0.4rem;padding-left:0.2rem">{label}</div>'
            f'<div style="background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border-radius:12px;padding:1.2rem 1.4rem;border:1px solid rgba(27,120,214,0.25)">'
            f'<div style="font-size:2rem;font-weight:800;color:var(--accent)">{value}</div>'
            f'<div style="font-size:0.8rem;color:rgba(255,255,255,0.45);margin-top:0.4rem">{sub}</div></div>')


def _cs_lines_df():
    q = cs_quote
    rows = [{"Item": l["name"], "Qty": l["qty"], "Charge": f"£{l['total']:.2f}/mo"} for l in q["lines"]]
    for s_ in q["setup"]:
        rows.append({"Item": s_["name"] + " (one-off)", "Qty": s_["qty"], "Charge": "Waived" if q["setup_mode"] == "waived" else f"£{s_['total']:.2f}"})
    return pd.DataFrame(rows)


def _ac_items():
    return [(it, q) for it, q in ac_quote["qty"] if it.get("group") not in ("Materials", "Labour")]


with tab1:
    st.markdown('<div class="tab-content"></div>', unsafe_allow_html=True)

    if comp_name:
        st.markdown(f"### Prepared for: **{comp_name}** ({biz_type})")
    if install_address:
        st.markdown(f"📍 {install_address}")
    st.markdown("")

    if n_packs() >= 2:
        st.markdown("## 📞 Telephony")
    prop_col1, prop_col2 = st.columns(2)

    with prop_col1:
        st.markdown("#### 🖥️ System, Software & Hardware")

        all_hw_items = []
        _hw_billing = ("In System Rental" if is_inhouse else "In Monthly Lease") if is_spread else "Paid Upfront"
        _sw_billing = "Monthly Add-on"

        # Physical hardware
        for name, qty in desktop_quantities.items():
            if qty > 0: all_hw_items.append((name, qty, _hw_billing))
        for name, qty in cordless_quantities.items():
            if qty > 0: all_hw_items.append((name, qty, _hw_billing))
        for name, qty in headset_quantities.items():
            if qty > 0: all_hw_items.append((name, qty, _hw_billing))
        for name, qty in other_quantities.items():
            if qty > 0: all_hw_items.append((name, qty, _hw_billing))
        if not _no_switch:
            if switch_quantities:
                for _sn, _sq in switch_quantities.items():
                    all_hw_items.append((f"Switch: {_sn}", _sq, _hw_billing))
            elif auto_switch:
                all_hw_items.append((f"Switch: {rec_switch['name']}", 1, _hw_billing))
        if add_router:
            if router_quantities:
                for _rn, _rq in router_quantities.items():
                    all_hw_items.append((_rn, _rq, _hw_billing))
            elif router_type not in ("None / Customer Supplied", ""):
                all_hw_items.append((router_type, 1, _hw_billing))
        for _r in printer_rows:
            all_hw_items.append((_r["name"], _r["qty"], f"Printer lease ({printer_term} mo)"))
        if all_hw_items:
            hw_df = pd.DataFrame(all_hw_items, columns=["Description", "Qty", "Billing"])
            st.dataframe(hw_df, use_container_width=True, hide_index=True)
        else:
            st.info("No hardware selected yet.")

        st.markdown("#### 🌐 Network & Connectivity")
        st.caption("Ongoing monthly service charges")
        net_items = []
        if svc["bb_sell"] > 0:
            net_items.append((f"{bb_provider} - {bb_package}", 1, f"£{svc['bb1_sell']:.2f}/mo"))
        # Voice Channel Licences - always show with monthly amount
        if total_voice_channels > 0:
            net_items.append((f"Hosted User Licences x{total_voice_channels} (Professional Bundle)",
                              total_voice_channels, f"£{svc['lic_monthly']:.2f}/mo"))
        # SW Add-ons - monthly amounts
        for addon_name, addon_qty, addon_cost, addon_sell in SW_ADDONS:
            if addon_qty > 0:
                net_items.append((addon_name, addon_qty, f"£{addon_sell * addon_qty:.2f}/mo"))
        # 2nd line BB
        for _xp, _xq, _xs in extra_bb_display():
            net_items.append((f"{bb_provider} - {_xp} (additional)", _xq, f"£{_xs:.2f}/mo"))
        # Mobile rows

        if printer_rows:
            net_items.append((f"Printer lease ({printer_term} months, incl. set up)", printer_count, f"£{printer_monthly:.2f}/mo"))
            for _r in printer_rows:
                net_items.append((f"Printing - {_r['name']} ({_r['volume']:,}/mo at {_r['cpc_sell']:.3f}p)", 1, f"£{_r['print_mo']:.2f}/mo est."))
        net_df = pd.DataFrame(net_items, columns=["Service", "Qty", "Charge"])
        st.dataframe(net_df, use_container_width=True, hide_index=True)

        if cs_svc_rows:
            st.markdown("#### 🔮 Call Scope Services")
            cs_df = pd.DataFrame([{"Service": r["name"], "Qty": r["qty"],
                                   "Monthly": f"£{r['sell']*r['qty']:.2f}/mo"} for r in cs_svc_rows])
            st.dataframe(cs_df, use_container_width=True, hide_index=True)

    with prop_col2:
        st.markdown("#### Commercial Summary")
        # Build commercial summary cards - content varies by payment model
        _hw_card = "" if is_spread else f"""
        <div class="metric-card" style="text-align:left; margin-bottom:1rem">
          <div class="metric-label">Upfront Hardware Cost</div>
          <div style="font-size:1.4rem; font-weight:700">£{upfront:.2f} (one-off)</div>
        </div>"""

        _spread_note = f"""
        <div class="metric-card" style="text-align:left; margin-bottom:1rem">
          <div class="metric-label">{"System Rental" if is_inhouse else "Hardware Lease Rental"}</div>
          <div style="font-size:1.4rem; font-weight:700; color:var(--accent)">
            £{hw_monthly_spread:.2f}/mo
          </div>
          <div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">
            Spread over {LEASE_TERM_LABELS[lease_term]}
          </div>
        </div>""" if is_spread else ""

        st.markdown(f"""
        <div style="font-size:0.72rem;color:var(--muted);margin-bottom:0.2rem">
          Agreement term: <strong>{lease_term} months</strong>
        </div>
        {_hw_card}
        {_spread_note}
        <div class="metric-card" style="text-align:left; margin-bottom:1rem">
          <div class="metric-label">Network & Services</div>
          <div style="font-size:1.4rem; font-weight:700">£{svc["total_sell"]:.2f} + VAT</div>
          <div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">Licences, broadband, software &amp; mobiles</div>
        </div>
        <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
             letter-spacing:0.1em;color:var(--muted);margin-bottom:0.4rem;padding-left:0.2rem">
          TOTAL MONTHLY COMMITMENT
        </div>
        <div style="background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border-radius:12px;
             padding:1.2rem 1.4rem;border:1px solid rgba(27,120,214,0.25)">
          <div style="font-size:2rem;font-weight:800;color:var(--accent)">
            £{total_mo:.2f} + VAT
          </div>
          <div style="font-size:0.8rem;color:rgba(255,255,255,0.45);margin-top:0.4rem">
            {"All services + hardware included" if is_spread else "Services per month"}
            &nbsp;·&nbsp; {LEASE_TERM_LABELS[lease_term]}
          </div>
        </div>
        """, unsafe_allow_html=True)

        if credits_months > 0:
            st.markdown(f'<div class="info-box">🎁 Introductory credit of <strong>£{credits_amount:.2f}/mo</strong> applied for {credits_months} months</div>', unsafe_allow_html=True)

        if mobile_rows:
            st.markdown("#### Mobile SIMs")
            mob_df = pd.DataFrame([
                {"Network": r["network"], "Package": r["package"], "Qty": r["qty"], "Monthly": f"£{r['sell'] * r['qty']:.2f}"}
                for r in mobile_rows
            ])
            st.dataframe(mob_df, use_container_width=True, hide_index=True)

        if it_rows:
            st.markdown("#### 💻 IT Services")
            it_df = pd.DataFrame([
                {"Service": r["service"], "Qty": r["qty"],
                 "Monthly": f"£{r['sell']*r['qty']:.2f}/mo"}
                for r in it_rows
            ])
            st.dataframe(it_df, use_container_width=True, hide_index=True)

        if sec_rows:
            st.markdown("#### 🛡️ System Security")
            sec_df = pd.DataFrame([{"Tier": r["name"], "Qty": r["qty"],
                                    "Monthly": f"£{r['sell']*r['qty']:.2f}/mo"} for r in sec_rows])
            st.dataframe(sec_df, use_container_width=True, hide_index=True)



    # ── Call Scope and air conditioning: each its own company, so each its own summary ──
    if cs_active:
        _cb = cs_brand(); _q = cs_quote
        st.markdown("---")
        st.markdown(f"## 🔮 {esc(_cb['trading'])}")
        st.caption(f"Provided by {_cb['legal']} under its own agreement.")
        if cs_crm_missing:
            st.warning("Enter the customer's CRM in the Call Scope card - the Call Scope paperwork is held back until then.")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("#### Services")
            st.dataframe(_cs_lines_df(), use_container_width=True, hide_index=True)
            if _q["discount"] > 0:
                st.caption(f"Includes a {_q['discount']:g}% discount on the standard price" + (" (year 1, stepping back to standard)" if _q["style"] == "stepped" and _q["years"] > 1 else "") + ".")
        with s2:
            st.markdown("#### Commercial Summary")
            st.markdown(f"<div style='font-size:0.72rem;color:var(--muted);margin-bottom:0.2rem'>Agreement term: <strong>{_q['term']} months</strong></div>", unsafe_allow_html=True)
            _setup_t = 0.0 if _q["setup_mode"] == "waived" else sum(x["total"] for x in _q["setup"])
            st.markdown(f'<div class="metric-card" style="text-align:left;margin-bottom:1rem"><div class="metric-label">Set-up (one-off)</div>'
                        f'<div style="font-size:1.4rem;font-weight:700">{"Waived" if _q["setup_mode"] == "waived" else "£" + format(_setup_t, ",.2f")}</div></div>',
                        unsafe_allow_html=True)
            st.markdown(_big_total("TOTAL MONTHLY COMMITMENT", f"£{_q['monthly_total']:,.2f} + VAT", f"Billed monthly in advance · {_q['term']} months"), unsafe_allow_html=True)
    if ac_active:
        _co = st_company(); _q = ac_quote
        st.markdown("---")
        st.markdown(f"## ❄️ {esc(_co['trading'])}")
        st.caption(f"Provided by {_co['legal']} under its own agreement.")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("#### Equipment")
            st.dataframe(pd.DataFrame([{"Description": it["name"], "Type": it.get("group", ""), "Qty": q} for it, q in _ac_items()]),
                         use_container_width=True, hide_index=True)
            st.caption(("Installation by our engineer" if _q["auto_install"] else "Installation as selected")
                       + f" · {_q['est_days']:g} day(s) · {_q['engineers']} engineer(s) · electrician " + ("included" if _q["install_elec"] > 0 or _q["auto_install"] else "as selected") + ".")
        with s2:
            st.markdown("#### Commercial Summary")
            st.markdown(f"<div style='font-size:0.72rem;color:var(--muted);margin-bottom:0.2rem'>Agreement: <strong>{'One-off purchase' if _q['is_cash'] else str(_q['term']) + ' months'}</strong></div>", unsafe_allow_html=True)
            st.markdown(f'<div class="metric-card" style="text-align:left;margin-bottom:1rem"><div class="metric-label">On-site support after year 1</div>'
                        f'<div style="font-size:1.4rem;font-weight:700">£{_q["support"]:,.2f} / year</div>'
                        f'<div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">The first year is included</div></div>', unsafe_allow_html=True)
            if _q["is_cash"]:
                st.markdown(_big_total("AIR CONDITIONING PRICE", f"£{_q['cash_price']:,.2f} + VAT", "One-off, supplied and installed"), unsafe_allow_html=True)
            else:
                st.markdown(_big_total("TOTAL MONTHLY COMMITMENT", f"£{_q['rental']:,.2f} + VAT", f"Rental · {_q['term']} months"), unsafe_allow_html=True)
    if n_packs() >= 2:
        _mo, _one = solution_totals()
        st.markdown("---")
        st.markdown("## 🧾 Total solution")
        t1, t2 = st.columns(2)
        with t1:
            for _l, _v in _mo:
                _kv_row(_l, f"£{_v:,.2f}/mo")
            st.markdown(_big_total("TOTAL MONTHLY", f"£{sum(v for _, v in _mo):,.2f} + VAT", "All agreements together"), unsafe_allow_html=True)
        with t2:
            for _l, _v in _one:
                _kv_row(_l, f"£{_v:,.2f}")
            st.markdown(_big_total("TOTAL ONE-OFF", f"£{sum(v for _, v in _one):,.2f} + VAT", "Hardware, set-up and cash sales"), unsafe_allow_html=True)

    # summary banner removed
with tab2:
    st.markdown('<div class="tab-content"></div>', unsafe_allow_html=True)
    missing = []
    if not comp_name:     missing.append("Company Name")
    if not comp_reg:      missing.append("Company Registration No.")
    if not install_address: missing.append("Installation Address")
    if not contact_name:  missing.append("Signatory Name & Position")
    if not bank_name:     missing.append("Bank Name")
    if not acc_no:        missing.append("Account Number")
    if not sort_code:     missing.append("Sort Code")

    if missing:
        st.markdown(f'<div class="warning-box">⚠️ Missing fields required for order form: <strong>{", ".join(missing)}</strong></div>', unsafe_allow_html=True)

    of_col1, of_col2 = st.columns(2)

    with of_col1:
        st.markdown("#### 🏢 Legal & Company Details")
        fields = {
            "Trading / Company Name": comp_name or "⚠️ Not provided",
            "Company Reg. No.": comp_reg or "⚠️ Not provided",
            "Entity Type": biz_type,
            "No. of Employees": str(num_employees),
            "Signatory Name & Position": contact_name or "⚠️ Not provided",
            "Company Phone": company_phone or "-",
            "Director's Email": director_email or "-",
            "Billing Email": billing_email or "-",
            "Installation Address": install_address or "⚠️ Not provided",
        }
        for label, val in fields.items():
            colour = "#FBBF24" if "⚠️" in val else "#E7EAF3"
            st.markdown(f"<div style='display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid var(--border);font-size:0.88rem'><span style='color:var(--muted)'>{label}</span><span style='color:{colour};font-weight:500'>{val}</span></div>", unsafe_allow_html=True)

        st.markdown("#### 🏦 Direct Debit Mandate")
        bank_fields = {
            "Bank Name": bank_name or "⚠️ Not provided",
            "Account Holder": acc_holder or "⚠️ Not provided",
            "Account Number": acc_no or "⚠️ Not provided",
            "Sort Code": sort_code or "⚠️ Not provided",
        }
        for label, val in bank_fields.items():
            colour = "#FBBF24" if "⚠️" in val else "#E7EAF3"
            st.markdown(f"<div style='display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid var(--border);font-size:0.88rem'><span style='color:var(--muted)'>{label}</span><span style='color:{colour};font-weight:500'>{val}</span></div>", unsafe_allow_html=True)

    with of_col2:
        st.markdown("#### 📋 Deal & System Configuration")
        config_fields = {
            "Deal Type":       deal_type,
            "Contract Term":   LEASE_TERM_LABELS[lease_term],
            "Payment Profile": f"1+{lease_term-1}",
            "Installation":    install_type,
            "No. of Sites":    str(num_sites),
        }
        if svc["bb_sell"] > 0:
            config_fields["Broadband"] = f"{bb_provider} - {bb_package}"
        if is_spread:
            config_fields["Hardware Rental" if not is_inhouse else "System Rental"] = f"£{hw_monthly_spread:.2f}/mo ({'in-house system rental' if is_inhouse else 'lease'})"
            config_fields["Note"] = "Install & setup included in system rental" if is_inhouse else "Install & setup included in lease rental"
        else:
            config_fields["Upfront Hardware"] = f"£{upfront:.2f} (one-off)"
        if mobile_rows:
            config_fields["Mobile SIMs"] = (f"{sum(r['qty'] for r in mobile_rows)} connections - "
                                            f"£{svc.get('mobile_sell', 0.0):.2f}/mo")
        config_fields["Monthly Services"] = f"£{svc['total_sell']:.2f} + VAT"
        config_fields["Total Monthly"]    = f"£{total_mo:.2f} + VAT"
        if credits_months > 0:
            config_fields["Introductory Credit"] = f"£{credits_amount:.2f}/mo × {credits_months} months"
        if cashback_amount > 0:
            config_fields["Settlement / Cashback"] = f"£{cashback_amount:.2f}"
        for label, val in config_fields.items():
            st.markdown(f"<div style='display:flex;justify-content:space-between;padding:0.3rem 0;border-bottom:1px solid var(--border);font-size:0.88rem'><span style='color:var(--muted)'>{label}</span><span style='color:var(--text);font-weight:500'>{val}</span></div>", unsafe_allow_html=True)

        st.markdown("#### 📦 Equipment Summary")
        all_equip = [(n, q) for n, q in list(desktop_quantities.items()) +
                     list(cordless_quantities.items()) + list(headset_quantities.items()) +
                     list(other_quantities.items()) if q > 0]
        if auto_switch:
            all_equip.append((f"Switch: {rec_switch['name']}", 1))
        if add_router:
            if router_quantities:
                for _rn, _rq in router_quantities.items():
                    all_equip.append((_rn, _rq))
            elif router_type not in ("None / Customer Supplied", ""):
                all_equip.append((router_type, 1))
        if total_voice_channels > 0:
            all_equip.append((f"User / Voice Licences x{total_voice_channels}", total_voice_channels))
        for _ir in it_rows:
            if _ir["qty"] > 0:
                all_equip.append((f"IT: {_ir['service']} x{_ir['qty']}", _ir["qty"]))
        for addon_name, addon_qty, _, _ in SW_ADDONS:
            if addon_qty > 0:
                all_equip.append((addon_name, addon_qty))
        for r in cs_svc_rows:
            if r.get("qty", 0) > 0:
                all_equip.append((r["name"], r["qty"]))
        for r in sec_rows:
            if r.get("qty", 0) > 0:
                all_equip.append((r["name"], r["qty"]))
        for r in mobile_rows:
            if r["qty"] > 0:
                all_equip.append((f"Mobile SIM: {r['network']} - {r['package']}", r["qty"]))
        for _r in printer_rows:
            all_equip.append((f"Printer: {_r['name']}", _r["qty"]))
        for name, qty in all_equip:
            st.markdown(f"<div style='display:flex;justify-content:space-between;padding:0.2rem 0;font-size:0.85rem'><span style='color:var(--muted)'>{name}</span><span style='font-weight:600'>×{qty}</span></div>", unsafe_allow_html=True)

    # ── Call Scope and air-conditioning order forms (each its own agreement) ──
    if cs_active:
        _cb = cs_brand(); _q = cs_quote
        st.markdown("---")
        st.markdown(f"## 🔮 {esc(_cb['trading'])} order")
        o1, o2 = st.columns(2)
        with o1:
            st.markdown("#### Agreement")
            _kv_row("Provider", _cb["legal"])
            _kv_row("Customer", comp_name or "⚠️ Not provided", "#FBBF24" if not comp_name else "var(--text)")
            _kv_row("Contract term", f"{_q['term']} months")
            _kv_row("Billing", "Monthly in advance, by Direct Debit")
            _crm = str(st.session_state.get("cs_crm_name", "") or "").strip()
            if int(st.session_state.get("cs_AI Integration - CRM", 0) or 0) > 0:
                _kv_row("Customer's CRM", _crm or "⚠️ Not provided", "#FBBF24" if not _crm else "var(--text)")
            if _q["discount"] > 0:
                _kv_row("Discount on standard price", f"{_q['discount']:g}%")
            for _h, _tx in cs_notes:
                _kv_row(_h, _tx)
            _kv_row("Monthly total", f"£{_q['monthly_total']:,.2f} + VAT")
            if cs_crm_missing:
                st.warning("The Call Scope paperwork is held back until the customer's CRM is entered.")
        with o2:
            st.markdown("#### Services ordered")
            st.dataframe(_cs_lines_df(), use_container_width=True, hide_index=True)
    if ac_active:
        _co = st_company(); _q = ac_quote
        st.markdown("---")
        st.markdown(f"## ❄️ {esc(_co['trading'])} order")
        o1, o2 = st.columns(2)
        with o1:
            st.markdown("#### Agreement")
            _kv_row("Provider", _co["legal"])
            _kv_row("Customer", comp_name or "⚠️ Not provided", "#FBBF24" if not comp_name else "var(--text)")
            _kv_row("Payment", "Cash sale" if _q["is_cash"] else f"Rental over {_q['term_label']}")
            if _q["is_cash"]:
                _kv_row("Price", f"£{_q['cash_price']:,.2f} + VAT (one-off)")
            else:
                _kv_row("Payment profile", _q["profile"])
                _kv_row("Monthly rental", f"£{_q['rental']:,.2f} + VAT")
                _kv_row("Finance", f"Shire Leasing hire agreement ({_co['funder']})")
            _kv_row("On-site support", f"Year 1 included, then £{_q['support']:,.2f}/yr")
            _kv_row("Installation", f"{_q['est_days']:g} day(s), {_q['engineers']} engineer(s)")
            _sp = str(st.session_state.get("ac_special") or "").strip()
            if _sp:
                _kv_row("Special conditions", _sp)
        with o2:
            st.markdown("#### Equipment ordered")
            st.dataframe(pd.DataFrame([{"Description": it["name"], "Qty": q} for it, q in _ac_items()]), use_container_width=True, hide_index=True)
            _cur_ac = sum(float(st.session_state.get(k, 0) or 0) for k in ("ac_cur_running", "ac_cur_service", "ac_cur_leasing", "ac_cur_heating", "ac_cur_other"))
            if _cur_ac > 0:
                _kv_row("Customer's current heating / cooling costs", f"£{_cur_ac:,.2f}/mo")


# ── TAB 3: DOWNLOAD ───────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="tab-content"></div>', unsafe_allow_html=True)
    st.markdown("Generate the complete customer-facing paperwork package. All documents are pre-populated from the deal configuration.")

    doc_col1, doc_col2 = st.columns(2)

    with doc_col1:
        st.markdown("#### 📄 What's included in the PDF")
        docs = [
            "✅ Commercial Proposal / Cost Comparison",
            "✅ Equipment Rental Agreement",
            "✅ Network Services & Broadband Agreement",
            "✅ Telephone System Order Form",
            "✅ Inclusive Support & Maintenance",
            "✅ Customer Requirements Checklist",
            "✅ Direct Debit Mandate",
        ] + (["✅ Letter of Authority (number porting)"] if (_loa_data()["on"] and _loa_data()["numbers"]) else []) + [
            "✅ Signature Blocks (all sections)",
        ]
        if _maint_optout():
            docs = [d for d in docs if "Maintenance" not in d]
            docs.append("🚫 Maintenance opted out - no warranty / maintenance page")
        for d in docs:
            st.markdown(f"<div style='font-size:0.88rem;padding:0.25rem 0'>{d}</div>", unsafe_allow_html=True)

    with doc_col2:
        st.markdown("#### 📋 Deal Summary")
        summary = [
            f"Customer: {comp_name or '-'}",
            f"Agreement Term: {LEASE_TERM_LABELS[lease_term]}",
            f"Payment Model: {payment_model}",
            f"Monthly Total: £{total_mo:.2f} + VAT",
            f"Broadband: {bb_provider} - {bb_package}",
            f"Voice Channels: {total_voice_channels}",
            f"Install Type: {install_type}",
        ]
        for d in summary:
            st.markdown(f"<div style='font-size:0.88rem;padding:0.2rem 0;color:var(--muted)'>{d}</div>", unsafe_allow_html=True)

    # ── DOWNLOAD BUTTON ──
    st.markdown("")
    pdf_ready = bool(comp_name)

    if not pdf_ready:
        st.markdown('<div class="warning-box">⚠️ Add a company name in the sidebar to enable PDF generation.</div>', unsafe_allow_html=True)
    else:
        st.session_state.pop("_pack_merge_error", None)
        pdf_bytes = build_pdf()
        if st.session_state.get("_pack_merge_error"):
            st.warning("⚠️ The Proposal Summary could not be added to the front of the pack "
                       f"({st.session_state['_pack_merge_error']}). Add `pypdf` to requirements.txt in GitHub and reboot the app.")
        safe_name = s(comp_name).replace(" ", "_").replace("/", "-")
        st.download_button(
            label=f"📥 Download Full Proposal Pack - {comp_name}",
            data=pdf_bytes,
            file_name=f"SWComms_Proposal_{safe_name}_{date.today()}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        st.markdown('<div class="success-box">✅ PDF ready - Proposal Summary (with agreement to proceed), Order Form, Network Agreement, Mandate & Checklist.</div>', unsafe_allow_html=True)
        if _loa_data()["on"] and _loa_data()["numbers"]:
            st.markdown("---")
            st.markdown("#### 📞 Letter of Authority only")
            st.caption("For sending to the old provider on its own - it has no pricing in it.")
            _loa_only = build_loa_pdf()
            if _loa_only:
                st.download_button(
                    label="📞 Download Letter of Authority (unsigned)",
                    data=_loa_only,
                    file_name=f"LetterOfAuthority_{safe_name}_{date.today()}.pdf",
                    mime="application/pdf", use_container_width=True, key="dl_loa_docs")
        if cs_active:
            st.markdown("---")
            st.markdown("#### 🔮 Call Scope pack (separate agreement)")
            st.caption("Call Scope has its own paperwork: Agreement to proceed, Service Order, Price Schedule, Terms & Conditions and a Direct Debit mandate. "
                       "It is not part of the telephony pack above.")
            if cs_crm_missing:
                st.warning("Enter the customer's CRM in the Call Scope card (AI CRM Integration) to produce this pack.")
            else:
                try:
                    st.download_button(label=f"📥 Download Call Scope Pack - {comp_name}", data=build_callscope_pack(),
                                       file_name=f"CallScope_{safe_name}_{date.today()}.pdf", mime="application/pdf",
                                       use_container_width=True, key="dl_cs_pack_docs")
                except Exception as _cse:
                    st.error(f"Couldn't build the Call Scope pack: {_cse}")
        if ac_active:
            st.markdown("---")
            st.markdown("#### ❄️ SteadyTemp pack (separate agreement)")
            st.caption("Air conditioning has its own paperwork under SteadyTemp LTD: Proposal, Order Form, On-Site Support Agreement, Direct Debit set-up and Terms & Conditions.")
            try:
                st.download_button(label=f"📥 Download SteadyTemp Pack - {comp_name}", data=build_steadytemp_pack(),
                                   file_name=f"SteadyTemp_{safe_name}_{date.today()}.pdf", mime="application/pdf",
                                   use_container_width=True, key="dl_st_pack_docs")
            except Exception as _ste:
                st.error(f"Couldn't build the SteadyTemp pack: {_ste}")
        if n_packs() >= 2 and not cs_crm_missing:
            try:
                st.download_button(label=f"📦 Download COMBINED pack (all selected) - {comp_name}",
                                   data=build_combined(pdf_bytes),
                                   file_name=f"Combined_Pack_{safe_name}_{date.today()}.pdf", mime="application/pdf",
                                   use_container_width=True, key="dl_combined_docs")
            except Exception as _cse:
                st.error(f"Couldn't build the combined pack: {_cse}")
        st.markdown("")
        st.markdown("---")
        st.markdown("#### 📋 One-Page Proposal")
        st.caption("Two-page summary in the app's dark style: the customer's saving (or daily investment) and full cost comparison, then everything included. Great for emailing before the full paperwork.")
        proposal_bytes = build_proposal_pdf()
        st.download_button(
            label=f"📋 Download Proposal Summary - {comp_name}",
            data=proposal_bytes,
            file_name=f"SWComms_Proposal_Summary_{safe_name}_{date.today()}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_proposal"
        )

# ── TAB 4: CUSTOMER VIEW ──────────────────────────────────────────────────────
with tab4:

    # Header
    st.markdown(f"""
    <div class="cv-header">
      <h2>{_CO_PKG}</h2>
      <p>{'Prepared for: ' + comp_name if comp_name else 'Complete the customer details in the sidebar'} &nbsp;|&nbsp; {LEASE_TERM_LABELS[lease_term]} agreement</p>
    </div>
    """, unsafe_allow_html=True)

    if not (desktop_quantities or cordless_quantities or headset_quantities or other_quantities or standalone_softphones > 0):
        if not cs_active:
            st.info("👈 Select hardware from the builder above to populate this view.")
    else:
        # ── Selected Hardware ──────────────────────────────────────────────────
        st.markdown('<div class="cv-section">📦 Your New System</div>', unsafe_allow_html=True)

        # Items hidden from customer view (backend/setup costs)
        _CV_HIDE = {"Call Scope AI Setup (one-off)", "Call Scope AI Receptionist Setup (one-off)"}
        all_selected = (
            [(n, q, HANDSETS_DESKTOP[n])   for n, q in desktop_quantities.items() if q > 0]  +
            [(n, q, HANDSETS_CORDLESS[n])  for n, q in cordless_quantities.items() if q > 0] +
            [(n, q, HEADSETS[n])           for n, q in headset_quantities.items()   if q > 0] +
            [(n, q, OTHER_HARDWARE.get(n, {"cat":"Other"}))
             for n, q in other_quantities.items()
             if q > 0 and n not in _CV_HIDE]
        )

        # Add switch card(s)
        if switch_quantities:
            for _sn, _sq in switch_quantities.items():
                all_selected.append((f"Switch: {_sn}", _sq, {"cat": "Switch"}))
        elif not _no_switch:
            sw_name = rec_switch["name"]
            all_selected.append((f"Switch: {sw_name}", 1, {"cat": "Switch"}))

        # Add router card(s) - iterate router_quantities for multi-router support
        if add_router:
            if router_quantities:
                for _rn, _rq in router_quantities.items():
                    all_selected.append((_rn, _rq, {"cat": "Router"}))
            elif router_type not in ("None / Customer Supplied", ""):
                all_selected.append((router_type, 1, {"cat": "Router"}))
        for _r in printer_rows:
            all_selected.append((_r["name"], _r["qty"], {"cat": "Printer"}))
        # Add software add-ons as cards
        for addon_name, addon_qty, _, _ in SW_ADDONS:
            if addon_qty > 0:
                all_selected.append((addon_name, addon_qty, {"cat": "Software"}))

        # IT service cards
        for _ir in it_rows:
            all_selected.append((_ir["service"], _ir["qty"], {"cat": "IT"}))


        # Call Scope service cards
        for _ir in cs_svc_rows:
            all_selected.append((f"Call Scope: {_ir['name']}", _ir["qty"], {"cat": "Call Scope"}))
        # Security cards
        for _ir in sec_rows:
            all_selected.append((_ir["name"], _ir["qty"], {"cat": "Security"}))
        # Add Mobile App / Softphone users as a card
        if standalone_softphones > 0:
            all_selected.append((
                "Mobile App / Softphone Users",
                standalone_softphones,
                {"cat": "Mobile"}
            ))


        # Show in rows of 4
        for row_start in range(0, len(all_selected), 4):
            row_items = all_selected[row_start:row_start + 4]
            cols = st.columns(4)
            for col, (name, qty, info) in zip(cols, row_items):
                with col:
                    b64_cv, ext_cv = get_product_image_b64(name)
                    if b64_cv:
                        img_html = f'<img src="data:image/{ext_cv};base64,{b64_cv}" style="width:100%;height:100px;object-fit:contain;border-radius:8px;">'
                    else:
                        cat = info.get("cat", "Desktop")
                        icon_map = {"Desktop":"📱","DECT":"📞","Wi-Fi":"📡","Switch":"🔌","Router":"🌐","Software":"💻","IT":"🖥️","Mobile":"📱","Headset":"🎧"}
                        icon = icon_map.get(cat, PRODUCT_ICONS.get(cat, "📱"))
                        img_html = f'<div style="height:100px;background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2.8rem">{icon}</div>'

                    st.markdown(f"""
                    <div class="cv-hw-card">
                      {img_html}
                      <div class="cv-hw-name">{name}</div>
                      <div class="cv-hw-qty">Qty: {qty}</div>
                    </div>
                    """, unsafe_allow_html=True)

        # Auto-included note (simplified)
        st.markdown(f"""
        <div style="margin-top:0.75rem;padding:0.6rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted)">
          <strong>{total_voice_channels} Voice Channel Licence{"s" if total_voice_channels != 1 else ""}</strong> included
          &nbsp;&middot;&nbsp; {LEASE_TERM_LABELS[lease_term]} agreement
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")

        # ── Pricing breakdown ──────────────────────────────────────────────────
        # ── Pricing breakdown ──────────────────────────────────────────────────
    # ── COST COMPARISON SECTION ───────────────────────────────────────
    if current_total > 0:
        st.markdown("---")
        st.markdown('''
        <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;
             color:var(--text);margin:1rem 0 0.6rem">📊 Cost Comparison</div>
        ''', unsafe_allow_html=True)

        saving_mo  = current_total - total_mo
        saving_yr  = saving_mo * 12
        saving_pct = (saving_mo / current_total * 100) if current_total > 0 else 0

        # Build comparison rows
        # Build comparison using pricebook category structure
        # South Wales Comms side matches: Call Charges | Hosted Licences | Software | BB | Equipment Rental
        comp_rows = build_comparison_rows()

        # Comparison table - built as a flat string to avoid markdown code-block indentation
        _saving_bg  = "rgba(52,211,153,.12)"  # always green — increase is also a positive investment
        _saving_col = "#34D399"  # always green
        if saving_mo >= 0:
            _saving_lbl  = "Annual Saving"
            _saving_disp = f"{chr(163)}{abs(saving_yr):,.2f}"
            _saving_sub  = f"per year  ({chr(163)}{abs(saving_mo):.2f}/mo)"
        else:
            _daily       = abs(saving_mo) / 30.44
            _saving_lbl  = "Daily Investment"
            _saving_disp = f"{chr(163)}{_daily:.2f}"
            _saving_sub  = "per day"
        _arrow = "-" if saving_mo >= 0 else "+"

        _tbl = '<table style="width:100%;border-collapse:collapse;font-size:0.88rem;background:var(--surface);border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06)">'
        _tbl += '<thead><tr style="background:var(--surface-3);color:#fff">'
        _tbl += '<th style="padding:10px 12px;text-align:left">Category</th>'
        _tbl += '<th style="padding:10px 12px;text-align:right">Current</th>'
        _tbl += f'<th style="padding:10px 12px;text-align:right">{esc(_CO)}</th>'
        _tbl += '<th style="padding:10px 12px;text-align:right">Difference</th>'
        _tbl += "</tr></thead><tbody>"

        for _label, _curr_v, _new_v in comp_rows:
            _diff  = _curr_v - _new_v
            if abs(_diff) < 0.005:
                _dcol, _dstr = "var(--muted)", f"{chr(163)}0.00"
            else:
                _dcol  = "#34D399"  # always green - an increase is presented as an investment, not a warning
                _dstr  = f"-{chr(163)}{_diff:.2f}" if _diff > 0 else f"+{chr(163)}{abs(_diff):.2f}"
            _tbl += f'<tr>'
            _tbl += f'<td style="padding:8px 12px;border-bottom:1px solid var(--border)">{_label}</td>'
            _tbl += f'<td style="padding:8px 12px;border-bottom:1px solid var(--border);text-align:right;color:var(--muted)">{chr(163)}{_curr_v:.2f}</td>'
            _tbl += f'<td style="padding:8px 12px;border-bottom:1px solid var(--border);text-align:right;color:var(--text);font-weight:600">{chr(163)}{_new_v:.2f}</td>'
            _tbl += f'<td style="padding:8px 12px;border-bottom:1px solid var(--border);text-align:right;color:{_dcol};font-weight:700">{_dstr}</td>'
            _tbl += "</tr>"

        _tbl += f'<tr style="background:var(--surface-2);font-weight:700">'
        _tbl += f'<td style="padding:10px 12px">Total Monthly (excl. VAT)</td>'
        _tbl += f'<td style="padding:10px 12px;text-align:right">{chr(163)}{current_total:.2f}</td>'
        _tbl += f'<td style="padding:10px 12px;text-align:right;color:var(--text)">{chr(163)}{total_mo:.2f}</td>'
        _tbl += f'<td style="padding:10px 12px;text-align:right;color:{_saving_col}">{_arrow}{chr(163)}{abs(saving_mo):.2f}</td>'
        _tbl += "</tr></tbody></table>"

        _tbl += f'<div style="margin-top:1rem;padding:1rem 1.4rem;background:{_saving_bg};border-radius:10px;border-left:4px solid {_saving_col}">'
        _tbl += f'<div style="font-size:0.8rem;color:{_saving_col};font-weight:700;text-transform:uppercase;letter-spacing:.06em">{_saving_lbl}</div>'
        _tbl += f'<div style="font-size:1.8rem;font-weight:800;color:{_saving_col}">{_saving_disp}</div>'
        _tbl += f'<div style="font-size:1rem;color:{_saving_col};margin-top:0.2rem">{_saving_sub}</div>'
        _tbl += "</div>"

        st.markdown(_tbl, unsafe_allow_html=True)
    else:
        st.markdown('''
    <div style="margin-top:1rem;padding:0.8rem 1rem;background:var(--surface-2);border-radius:8px;
         font-size:0.83rem;color:var(--muted);text-align:center;border:1px dashed var(--border-strong)">
      💡 Fill in the customer's <strong>Current Customer Costs</strong> in the sidebar
      to show a cost comparison here.
    </div>
    ''', unsafe_allow_html=True)



    cv_col1, cv_col2 = st.columns([3, 2])

    with cv_col1:
        st.markdown('<div class="cv-section">🌐 Your Services</div>', unsafe_allow_html=True)
        svc_lines = [
            (f"Business Broadband - {bb_provider} {bb_package}", f"£{svc['bb1_sell']:.2f}/mo"),
        ]
        for _xp, _xq, _xs in extra_bb_display():
            svc_lines.append((f"Additional line x{_xq} - {bb_provider} {_xp}", f"£{_xs:.2f}/mo"))
        if total_voice_channels > 0:
            svc_lines.append((f"User / Voice Licences ({total_voice_channels} users)", f"£{svc['lic_monthly']:.2f}/mo"))
        if ooh_support:
            svc_lines.append(("24/7 Out-of-Hours Support", "£25.00/mo"))
        if dark_web_mon:
            svc_lines.append(("Dark Web Monitoring", "£10.00/mo (after 3m FOC)"))
        if proactive_bb:
            svc_lines.append(("Proactive Broadband Management", "£10.00/mo (after 3m FOC)"))
        for r in mobile_rows:
            if r["qty"] > 0:
                svc_lines.append((f"Mobile - {mobile_label(r)} x{r['qty']}",
                                  f"£{r['sell'] * r['qty']:.2f}/mo"))
        for _d_, _a_ in XM_ROWS:
            svc_lines.append((_d_, f"£{_a_:.2f}/mo"))
        if printer_rows:
            svc_lines.append((f"Printer lease - {printer_count} printer(s) over {printer_term} months", f"£{printer_monthly:.2f}/mo"))
            for _r in printer_rows:
                svc_lines.append((f"Printing - {_r['name']}: {_r['volume']:,} prints at {_r['cpc_sell']:.3f}p (est.)",
                                  f"£{_r['print_mo']:.2f}/mo"))

        for label, val in svc_lines:
            st.markdown(f"""
            <div class="cv-price-row">
              <span class="cv-price-label">{label}</span>
              <span class="cv-price-val">{val}</span>
            </div>""", unsafe_allow_html=True)

            for _ir in it_rows:
                if _ir["qty"] > 0:
                    all_equip.append((f"IT: {_ir['service']}", _ir["qty"]))
        st.markdown('<div class="cv-section">✅ What\'s Included</div>', unsafe_allow_html=True)
        includes = [
            "Manufacturer hardware warranty",
            "Full configuration & setup",
        ]
        if credits_months > 0:
            includes.append(f"£{credits_amount:.2f}/mo introductory credit for {credits_months} months")
        if cashback_amount > 0:
            includes.append(f"£{cashback_amount:.2f} settlement contribution")
        if AC["maint_annual"] > 0 and AC["listed"]:
            includes.append(f"Air conditioning on-site support: included for {int(AC_COST['free_support_years'])} year, then £{AC['maint_annual']:,.2f} a year plus VAT")

        for item in includes:
            st.markdown(f'<div class="cv-include-item">✅ {item}</div>', unsafe_allow_html=True)

        # Software add-on images - show if any selected
        active_addons = [(name, qty) for name, qty, _, _ in SW_ADDONS if qty > 0]
        if active_addons:
            st.markdown('<div class="cv-section">💻 Software &amp; Add-ons</div>', unsafe_allow_html=True)
            addon_cols = st.columns(min(len(active_addons), 4))
            for idx, (addon_name, addon_qty) in enumerate(active_addons):
                with addon_cols[idx % 4]:
                    b64_sw, ext_sw = get_product_image_b64(addon_name)
                    if b64_sw:
                        st.markdown(
                            f'<div style="background:var(--surface-2);border-radius:10px;padding:0.6rem;text-align:center;margin-bottom:0.5rem">'
                            f'<img src="data:image/{ext_sw};base64,{b64_sw}" style="max-height:70px;max-width:100%;object-fit:contain;border-radius:6px"/>'
                            f'<div style="font-size:0.75rem;color:var(--text);font-weight:600;margin-top:0.3rem">{addon_name}</div>'
                            f'<div style="font-size:0.7rem;color:var(--muted)">x{addon_qty}</div></div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f'<div style="background:var(--surface-2);border-radius:10px;padding:0.8rem;text-align:center;margin-bottom:0.5rem">'
                            f'<div style="font-size:1.6rem">💻</div>'
                            f'<div style="font-size:0.75rem;color:var(--text);font-weight:600;margin-top:0.3rem">{addon_name}</div>'
                            f'<div style="font-size:0.7rem;color:var(--muted)">x{addon_qty}</div></div>',
                            unsafe_allow_html=True
                        )


    with cv_col2:
        st.markdown('<div class="cv-section">💳 Your Investment</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="cv-price-row">
          <span class="cv-price-label">{("System Rental (monthly)" if is_inhouse else "Hardware Lease (monthly rental)") if is_spread else "Hardware (one-off)"}</span>
          <span class="cv-price-val" style="color:var(--text);font-weight:700">
            {"£" + f"{hw_monthly_spread:.2f}" + "/mo" if is_spread else "£" + f"{upfront:.2f}"}
          </span>
        </div>
        <div class="cv-price-row">
          <span class="cv-price-label">Network &amp; Services</span>
          <span class="cv-price-val" style="color:var(--text);font-weight:700">£{svc["total_sell"]:.2f}/mo</span>
        </div>
        <div class="cv-price-row" style="font-weight:700;border-top:2px solid var(--border-strong);margin-top:4px;padding-top:8px">
          <span style="color:var(--text)">Total (excl. VAT)</span>
          <span style="color:var(--text);font-size:1.1rem">£{total_mo - _bb_yr1_saving:.2f}/mo</span>
        </div>
        """, unsafe_allow_html=True)
        if bb_free_year and _bb_yr1_saving > 0:
            st.markdown(f"""
            <div style="background:rgba(52,211,153,.12);border-left:3px solid var(--good);border-radius:6px;
                 padding:0.5rem 0.8rem;font-size:0.8rem;color:var(--good);margin-top:0.3rem">
              🎁 <strong>Broadband FREE for the first 12 months</strong><br>
              From month 13: £{total_mo:.2f}/mo (broadband £{_bb_full_sell:.2f}/mo resumes)
            </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align:center;padding:0.5rem 0;font-size:0.8rem;color:var(--muted)">
          Agreement term: <strong style="color:var(--muted)">{lease_term} months</strong>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="margin-top:1rem;padding:0.8rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted);text-align:center">
          All figures exclude VAT.<br>
          Subject to survey & credit approval.
        </div>
        """, unsafe_allow_html=True)



    # ── Call Scope package (its own agreement, so its own section) ──
    if cs_active:
        _q = cs_quote
        _cb = cs_brand()
        st.markdown(f"""
        <div class="cv-header" style="margin-top:2rem">
          <h2>Your {esc(_cb['trading'])} Package</h2>
          <p>{'Prepared for: ' + esc(comp_name) if comp_name else 'Complete the customer details in the sidebar'} &nbsp;|&nbsp; {_q['term']} month agreement &nbsp;|&nbsp; provided by {esc(_cb['legal'])}</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="cv-section">🔮 Your Call Scope Services</div>', unsafe_allow_html=True)
        _cs_cards = [(l["name"], l["qty"]) for l in _q["lines"] if "mins" not in l["name"] or l["qty"] > 1 or True]
        for _rs in range(0, len(_cs_cards), 4):
            _cc = st.columns(4)
            for _col, (_n, _qt) in zip(_cc, _cs_cards[_rs:_rs + 4]):
                with _col:
                    _b64, _ext = get_product_image_b64("Call Scope " + _n)
                    if _b64:
                        _img = f'<img src="data:image/{_ext};base64,{_b64}" style="width:100%;height:100px;object-fit:contain;border-radius:8px;">'
                    else:
                        _img = '<div style="height:100px;display:flex;align-items:center;justify-content:center;font-size:2rem">🔮</div>'
                    st.markdown(f"""
                    <div class="cv-hw-card">
                      {_img}
                      <div class="cv-hw-name">{esc(_n)}</div>
                      <div class="cv-hw-qty">Qty: {_qt}</div>
                    </div>
                    """, unsafe_allow_html=True)
        st.markdown(f"""
        <div style="margin-top:0.75rem;padding:0.6rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted)">
          {_q['term']} month agreement &nbsp;&middot;&nbsp; billed monthly in advance &nbsp;&middot;&nbsp; its own paperwork, terms and Direct Debit
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        _csl = []
        for _l in _q["lines"]:
            _csl.append((f"{_l['name']}" + (f" x{_l['qty']}" if _l["qty"] > 1 else ""), f"£{_l['total']:.2f}/mo"))
        if _q["discount"] > 0:
            _csl.append((f"Includes {_q['discount']:g}% discount on the standard price", ""))
        for _r in _q["schedule"] if (_q["discount"] > 0 and _q["style"] == "stepped" and _q["years"] > 1) else []:
            _csl.append((f"Year {_r['year']} (months {_r['months']})", f"£{_r['monthly']:.2f}/mo"))
        for _s in _q["setup"]:
            _csl.append((f"{_s['name']} x{_s['qty']} (one-off)" if _s["qty"] > 1 else f"{_s['name']} (one-off)",
                         "Waived" if _q["setup_mode"] == "waived" else f"£{_s['total']:.2f}"))
        st.markdown('<div class="cv-section">🌐 Your Call Scope Charges</div>', unsafe_allow_html=True)
        for _label, _val in _csl:
            st.markdown(f"""
            <div class="cv-price-row">
              <span class="cv-price-label">{esc(_label)}</span>
              <span class="cv-price-val">{_val}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="margin-top:1rem;padding:1rem 1.4rem;background:var(--surface-2);border-radius:10px;border-left:4px solid var(--accent)">
          <div style="font-size:0.8rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.06em">Call Scope monthly</div>
          <div style="font-size:1.8rem;font-weight:800;color:var(--text)">£{_q['monthly_total']:,.2f} <span style="font-size:0.9rem;color:var(--muted)">+ VAT</span></div>
        </div>
        <div style="margin-top:1rem;padding:0.8rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted);text-align:center">
          All figures exclude VAT.<br>{esc(_cb['legal'])} provides Call Scope under its own agreement.
        </div>
        """, unsafe_allow_html=True)

    # ── SteadyTemp package (its own agreement, so its own section) ──
    if ac_active:
        _q = ac_quote
        _co = st_company()
        st.markdown(f"""
        <div class="cv-header" style="margin-top:2rem">
          <h2>Your {esc(_co['trading'])} Package</h2>
          <p>{'Prepared for: ' + esc(comp_name) if comp_name else 'Complete the customer details in the sidebar'} &nbsp;|&nbsp; {'One-off purchase' if _q['is_cash'] else str(_q['term']) + ' month agreement'} &nbsp;|&nbsp; provided by {esc(_co['legal'])}</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="cv-section">❄️ Your New Air Conditioning</div>', unsafe_allow_html=True)
        _ac_items = [(it, qt) for it, qt in _q["qty"] if it.get("group") not in ("Materials", "Labour")]
        for _rs in range(0, len(_ac_items), 4):
            _cc = st.columns(4)
            for _col, (_it, _qt) in zip(_cc, _ac_items[_rs:_rs + 4]):
                with _col:
                    _b64 = _ac_img(_it)
                    st.markdown(f"""
                    <div class="cv-hw-card">
                      {_ac_img_html(_b64, 100)}
                      <div class="cv-hw-name">{esc(_it['name'])}</div>
                      <div class="cv-hw-qty">Qty: {_qt}</div>
                    </div>
                    """, unsafe_allow_html=True)
        st.markdown(f"""
        <div style="margin-top:0.75rem;padding:0.6rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted)">
          Supply and installation included &nbsp;&middot;&nbsp; on-site support after year 1 &nbsp;&middot;&nbsp; its own paperwork, terms and Direct Debit
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        st.markdown('<div class="cv-section">🌐 Your Air Conditioning Charges</div>', unsafe_allow_html=True)
        _acrows = []
        if _q["is_cash"]:
            _acrows.append(("Air conditioning - supplied and installed", f"£{_q['cash_price']:,.2f}"))
        else:
            _acrows.append((f"Air conditioning rental ({_q['term']} months)", f"£{_q['rental']:,.2f}/mo"))
        _acrows.append(("On-site support after year 1", f"£{_q['support']:,.2f}/yr"))
        for _label, _val in _acrows:
            st.markdown(f"""
            <div class="cv-price-row">
              <span class="cv-price-label">{esc(_label)}</span>
              <span class="cv-price-val">{_val}</span>
            </div>""", unsafe_allow_html=True)
        _big = f"£{_q['cash_price']:,.2f}" if _q["is_cash"] else f"£{_q['rental']:,.2f}"
        st.markdown(f"""
        <div style="margin-top:1rem;padding:1rem 1.4rem;background:var(--surface-2);border-radius:10px;border-left:4px solid var(--accent)">
          <div style="font-size:0.8rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.06em">{'Air conditioning one-off price' if _q['is_cash'] else 'Air conditioning monthly rental'}</div>
          <div style="font-size:1.8rem;font-weight:800;color:var(--text)">{_big} <span style="font-size:0.9rem;color:var(--muted)">+ VAT</span></div>
        </div>
        """, unsafe_allow_html=True)
        # existing costs vs new
        _G = st.session_state.get
        _cur_ac = sum(float(_G(k, 0) or 0) for k in ("ac_cur_running", "ac_cur_service", "ac_cur_leasing", "ac_cur_heating", "ac_cur_other"))
        _new_mo = (_q["rental"] if not _q["is_cash"] else _q["cash_price"] / 12.0)
        if _cur_ac > 0 and not _q["is_cash"]:
            _d = _cur_ac - _new_mo
            _msg = (f"Saving £{_d * 12:,.0f} a year" if _d >= 0 else f"£{abs(_d) / 30.44:,.2f} a day investment")
            st.markdown('<div class="cv-section">📊 Existing costs vs SteadyTemp</div>', unsafe_allow_html=True)
            st.markdown(f"""
            <div class="cv-price-row"><span class="cv-price-label">Current heating / cooling costs</span><span class="cv-price-val">£{_cur_ac:,.2f}/mo</span></div>
            <div class="cv-price-row"><span class="cv-price-label">{esc(_co['trading'])} rental</span><span class="cv-price-val">£{_new_mo:,.2f}/mo</span></div>
            <div style="margin-top:1rem;padding:1rem 1.4rem;background:var(--surface-2);border-radius:10px;border-left:4px solid var(--accent)">
              <div style="font-size:1.4rem;font-weight:800;color:var(--text)">{_msg}</div></div>
            """, unsafe_allow_html=True)
        st.markdown(f"""
        <div style="margin-top:1rem;padding:0.8rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted);text-align:center">
          All figures exclude VAT.<br>{esc(_co['legal'])} provides air conditioning under its own agreement.
        </div>
        """, unsafe_allow_html=True)

    # ── Total solution costs (everything together, each under its own agreement) ──
    if n_packs() >= 2:
        _mo, _one = solution_totals()
        _mo_t, _one_t = sum(v for _, v in _mo), sum(v for _, v in _one)
        st.markdown('<div class="cv-header" style="margin-top:2rem"><h2>Your Total Solution Costs</h2>'
                    '<p>Everything above, together - each part provided under its own agreement</p></div>', unsafe_allow_html=True)
        st.markdown('<div class="cv-section">🌐 Monthly</div>', unsafe_allow_html=True)
        for _l, _v in _mo:
            st.markdown(f"""
            <div class="cv-price-row">
              <span class="cv-price-label">{esc(_l)}</span>
              <span class="cv-price-val">£{_v:,.2f}/mo</span>
            </div>""", unsafe_allow_html=True)
        if _one:
            st.markdown('<div class="cv-section">💳 One-off</div>', unsafe_allow_html=True)
            for _l, _v in _one:
                st.markdown(f"""
                <div class="cv-price-row">
                  <span class="cv-price-label">{esc(_l)}</span>
                  <span class="cv-price-val">£{_v:,.2f}</span>
                </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="margin-top:1rem;padding:1.2rem 1.6rem;background:var(--surface-2);border-radius:10px;border-left:4px solid var(--accent)">
          <div style="font-size:0.8rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.06em">Total solution - monthly</div>
          <div style="font-size:2.1rem;font-weight:800;color:var(--text)">£{_mo_t:,.2f} <span style="font-size:0.9rem;color:var(--muted)">+ VAT</span></div>
          {('<div style="margin-top:.6rem;font-size:0.8rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.06em">Total one-off</div><div style="font-size:1.4rem;font-weight:800;color:var(--text)">£' + format(_one_t, ",.2f") + ' <span style="font-size:0.85rem;color:var(--muted)">+ VAT</span></div>') if _one else ''}
        </div>
        <div style="margin-top:1rem;padding:0.8rem 1rem;background:var(--surface-2);border-radius:8px;font-size:0.82rem;color:var(--muted);text-align:center">
          All figures exclude VAT.
        </div>
        """, unsafe_allow_html=True)


# ── TAB 5: CONSULTANT VIEW ──────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="tab-content"></div>', unsafe_allow_html=True)

    # ── Password gate ──────────────────────────────────────────────────────
    if not st.session_state.consultant_unlocked:
        st.markdown("### 💼 Consultant View")
        st.caption("Enter the consultant password to access deal pricing tools.")
        c_col1, c_col2 = st.columns([3, 1])
        with c_col1:
            c_pw = st.text_input("", type="password", placeholder="Enter consultant password...",
                                 label_visibility="collapsed", key="consultant_pw")
        with c_col2:
            if st.button("Unlock 💼", type="primary", use_container_width=True, key="c_unlock"):
                _cons_pw = _secret("CONSULTANT_PASSWORD")
                if _admin_own_pw_ok(c_pw):
                    st.session_state.consultant_unlocked = True
                    st.rerun()
                elif not _cons_pw:
                    st.error("Consultant sign-in isn't set up yet. Add CONSULTANT_PASSWORD to the app's Secrets.")
                elif hmac.compare_digest(c_pw.encode(), _cons_pw.encode()):
                    st.session_state.consultant_unlocked = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
    else:
        # ── Locked button ──────────────────────────────────────────────────
        if _cu_role != "admin" and st.button("🔒 Lock Consultant View", key="c_lock"):   # admins stay unlocked
            st.session_state.consultant_unlocked = False
            st.rerun()

        st.markdown("## 💼 Consultant Deal Tools")

        # ── Deal snapshot strip ────────────────────────────────────────────
        st.markdown(f"""
        <div style="background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border-radius:12px;
             padding:1rem 1.5rem;margin-bottom:1.2rem;display:flex;
             justify-content:space-between;align-items:center;color:#fff">
          <div><div style="font-size:0.72rem;color:rgba(255,255,255,0.55)">CUSTOMER</div>
               <div style="font-size:1rem;font-weight:700">{esc(comp_name or "-")}</div></div>
          <div style="text-align:center">
               <div style="font-size:0.72rem;color:rgba(255,255,255,0.55)">BASE MONTHLY</div>
               <div style="font-size:1.4rem;font-weight:800;color:var(--accent)">£{total_mo:.2f}</div></div>
          <div style="text-align:right">
               <div style="font-size:0.72rem;color:rgba(255,255,255,0.55)">TERM</div>
               <div style="font-size:1rem;font-weight:700">{LEASE_TERM_LABELS[lease_term]}</div></div>
        </div>
        """, unsafe_allow_html=True)

        # ── Desired Rental adjustment ─────────────────────────────────
        st.markdown("### 🎯 Lease Rental Adjustment")
        if is_inhouse:
            st.info(f"In-house System Rental: the calculated monthly rental is the upfront price divided by the term (£{_inhouse_calc:,.2f}). "
                    "Set the rental you want below and it becomes what the customer pays; profit is the rental over the term less our costs, so it can go negative.")
        st.caption("Adjust the hardware lease rental. "
                   "Increasing earns more commission. Decreasing discounts the deal (reduces commission). "
                   "Commission is calculated only on the lease amount, not total monthly.")

        c_left, c_right = st.columns([3, 2])
        with c_left:
            # Only sync from sidebar when flag is set
            if st.session_state.pop("_sync_rental_to_cons", False) or "c_desired_rental_input" not in st.session_state:
                st.session_state["c_desired_rental_input"] = round(
                    st.session_state.get("c_desired_rental") or base_rental, 2)
            desired_rental_input = st.number_input(
                "Desired Lease Rental (£/mo)",
                min_value=0.0,
                step=1.0,
                key="c_desired_rental_input",
                help=f"Calculated rental: £{base_rental:.2f}. "
                     "Increase to earn more commission, decrease to offer the customer a discount."
            )
            btn1, btn2 = st.columns(2)
            with btn1:
                if st.button("✅ Apply Rental", type="primary",
                             use_container_width=True, key="c_apply"):
                    st.session_state["c_desired_rental"]        = desired_rental_input
                    st.session_state["_sync_rental_to_sidebar"] = True
                    st.rerun()
            with btn2:
                if st.button("↩️ Reset to Calculated", use_container_width=True, key="c_reset"):
                    st.session_state["c_desired_rental"]        = 0.0
                    st.session_state["_sync_rental_to_sidebar"] = True
                    st.session_state["_sync_rental_to_cons"]    = True
                    st.rerun()
            est_earnings = commission

        with c_right:
            _adj_colour = "#34D399" if rental_adjustment >= 0 else "#F87171"
            _adj_bg     = "rgba(52,211,153,.12)" if rental_adjustment >= 0 else "rgba(248,113,113,.12)"
            _adj_label  = "Premium vs Calculated" if rental_adjustment >= 0 else "Discount vs Calculated"
            _adj_prefix = "+" if rental_adjustment >= 0 else ""
            st.markdown(f"""
            <div style="background:{_adj_bg};border-left:4px solid {_adj_colour};
                 border-radius:0 8px 8px 0;padding:1rem 1.2rem;margin-top:1.6rem">
              <div style="font-size:0.72rem;color:{_adj_colour};font-weight:700;text-transform:uppercase">{_adj_label}</div>
              <div style="font-size:1.6rem;font-weight:800;color:{_adj_colour}">{_adj_prefix}£{rental_adjustment:.2f}/mo</div>
              <div style="font-size:0.8rem;color:var(--muted);margin-top:0.2rem">
                Calculated: £{base_rental:.2f}/mo &nbsp;·&nbsp; Desired: £{_desired_rental:.2f}/mo
              </div>
            </div>
            """, unsafe_allow_html=True)


        # Row 1 - Lease-only comparison
        r1a, r1b, r1c = st.columns(3)
        with r1a:
            if current_system > 0:
                st.markdown(f"""
                <div style="background:var(--surface);border:2px solid var(--border);border-radius:12px;
                     padding:1.2rem;text-align:center">
                  <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                       letter-spacing:.08em;color:var(--muted);margin-bottom:0.5rem">Phone System / Lease (Current)</div>
                  <div style="font-size:2rem;font-weight:800;color:var(--bad)">£{current_system:.2f}</div>
                  <div style="font-size:0.78rem;color:var(--muted)">per month + VAT</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background:var(--surface-2);border:2px dashed var(--border-strong);border-radius:12px;
                     padding:1.2rem;text-align:center">
                  <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                       letter-spacing:.08em;color:var(--muted);margin-bottom:0.5rem">Phone System / Lease (Current)</div>
                  <div style="font-size:1rem;color:var(--muted)">Enter under<br>Current Costs →</div>
                </div>
                """, unsafe_allow_html=True)

        with r1b:
            st.markdown(f"""
            <div style="background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);
                 border-radius:12px;padding:1.2rem;text-align:center;border:2px solid var(--accent)">
              <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:.08em;color:rgba(255,255,255,0.6);margin-bottom:0.5rem">New Monthly Lease with South Wales Comms</div>
              <div style="font-size:2rem;font-weight:800;color:var(--accent)">£{_desired_rental:.2f}</div>
              <div style="font-size:0.78rem;color:rgba(255,255,255,0.5)">hardware lease per month + VAT</div>
            </div>
            """, unsafe_allow_html=True)

        with r1c:
            if current_system > 0:
                _ls_saving = current_system - _desired_rental
                _ls_col    = "#34D399" if _ls_saving >= 0 else "#F87171"
                _ls_bg     = "rgba(52,211,153,.12)" if _ls_saving >= 0 else "rgba(248,113,113,.12)"
                _ls_lbl    = "Lease Saving" if _ls_saving >= 0 else "Lease Increase"
                _ls_pfx    = "-" if _ls_saving >= 0 else "+"
                st.markdown(f"""
                <div style="background:{_ls_bg};border:2px solid {_ls_col};
                     border-radius:12px;padding:1.2rem;text-align:center">
                  <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                       letter-spacing:.08em;color:{_ls_col};margin-bottom:0.5rem">{_ls_lbl}</div>
                  <div style="font-size:2rem;font-weight:800;color:{_ls_col}">{_ls_pfx}£{abs(_ls_saving):.2f}</div>
                  <div style="font-size:0.78rem;color:{_ls_col}">per month  &middot;  {_ls_pfx}£{abs(_ls_saving*12):.0f}/yr</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background:var(--surface-2);border:2px dashed var(--border-strong);border-radius:12px;
                     padding:1.2rem;text-align:center">
                  <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;
                       letter-spacing:.08em;color:var(--muted);margin-bottom:0.5rem">Lease Saving</div>
                  <div style="font-size:1rem;color:var(--muted)">Add current costs<br>to calculate</div>
                </div>
                """, unsafe_allow_html=True)

        # Row 2 - Full monthly total
        # Use adjusted values from breakdown if consultant has made changes
        _c_adj_total = svc["total_sell"] + _desired_rental
        _diff_total    = current_total - _c_adj_total
        _diff_col      = "#34D399" if _diff_total >= 0 else "#F87171"
        _curr_total_str = f"£{current_total:.2f}" if current_total > 0 else "-"
        _curr_sys_str   = f"£{current_system:.2f}" if current_system > 0 else "-"
        st.markdown(f"""
        <div style="background:var(--surface-2);border:1px solid var(--border-strong);border-radius:10px;
             padding:0.8rem 1.2rem;margin-top:0.5rem">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="flex:1;text-align:center;border-right:1px solid var(--border-strong);padding-right:1rem">
              <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;color:var(--muted)">Customer Current Total</div>
              <div style="font-size:1.4rem;font-weight:800;color:var(--bad)">{_curr_total_str}<span style="font-size:0.75rem;font-weight:400"> /mo</span></div>
              <div style="font-size:0.72rem;color:var(--muted)">Lease {_curr_sys_str} + other spend</div>
            </div>
            <div style="flex:1;text-align:center;padding:0 1rem">
              <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;color:var(--text)">New Monthly Total (Lease + Services)</div>
              <div style="font-size:1.6rem;font-weight:800;color:var(--text)">£{_c_adj_total:.2f}<span style="font-size:0.75rem;font-weight:400"> + VAT</span></div>
              <div style="font-size:0.72rem;color:var(--muted)">£{_desired_rental:.2f} lease + £{svc["total_sell"]:.2f} services</div>
            </div>
            <div style="flex:1;text-align:center;border-left:1px solid var(--border-strong);padding-left:1rem">
              <div style="font-size:0.68rem;font-weight:700;text-transform:uppercase;color:{_diff_col}">{"Total Saving" if _diff_total >= 0 else "Total Increase"}</div>
              <div style="font-size:1.4rem;font-weight:800;color:{_diff_col}">{"+" if _diff_total < 0 else "-"}£{abs(_diff_total):.2f}<span style="font-size:0.75rem;font-weight:400"> /mo</span></div>
              <div style="font-size:0.72rem;color:{_diff_col}">£{abs(_diff_total*12):.0f}/yr</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)


        st.markdown("")

        # Row 2 - Commission (full width, prominent)
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#0d4a2a,#1a7a40);border-radius:12px;
             padding:1.4rem 2rem;margin-top:0.5rem;display:flex;
             justify-content:space-between;align-items:center">
          <div>
            <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
                 letter-spacing:.1em;color:rgba(255,255,255,0.6)">Your Estimated Commission</div>
            <div style="font-size:2.2rem;font-weight:800;color:#fff">£{est_earnings:.2f}</div>
          <div style="font-size:0.82rem;color:rgba(255,255,255,0.55)">{commission_units:.2f} units × £{commission_per_unit:.0f} - {LEASE_TERM_LABELS[lease_term]}</div>\n          </div>
          {"<div style='text-align:right'><div style='font-size:0.75rem;color:rgba(255,255,255,0.5);'>Rate Uplift Applied</div><div style='font-size:1.3rem;font-weight:700;color:var(--good)'>+£" + f"{rate_uplift:.2f}" + "/mo</div></div>" if rate_uplift > 0 else "<div style='text-align:right'><div style='font-size:0.75rem;color:rgba(255,255,255,0.5)'>Tip</div><div style='font-size:0.88rem;color:rgba(255,255,255,0.7)'>Increase the monthly<br>rate above to earn more</div></div>"}
        </div>
        """, unsafe_allow_html=True)


        # ── Services Discount (slider) ────────────────────────────────────────
        _appt = st.session_state.get("q_appt_type", "Self Gen")
        _appt_rates = {"Self Gen": 1000, "Base Deal": 600, "Acquisition": 500, "Telemarketer": 650}
        st.info(f"📋 Appointment type: **{_appt}** — commission rate £{_appt_rates.get(_appt, 1000):,}/unit")
        st.markdown("### 🏷️ Pricing")
        st.caption("All hardware and services are sold at cost + 20%. The target rental below is where you earn more: every £1,000 of profit is one commission unit.")

        def _sync_svc_disc():
            st.session_state["c_svc_disc"]    = st.session_state["c_svc_disc_w"]
            st.session_state["q_svc_discount"] = st.session_state["c_svc_disc_w"]

        _sd_col1, _sd_col2 = st.columns([3, 2])
        with _sd_col1:
            # Keep widget key in sync with c_svc_disc (allows sidebar to push value here)
            st.session_state["c_svc_disc_w"] = int(st.session_state.get("c_svc_disc", 0))
            st.slider("User licence discount (%)", min_value=0, max_value=50, step=5,
                      key="c_svc_disc_w", on_change=_sync_svc_disc,
                      help="Applies to hosted user licences and software add-ons. Broadband and Call Scope have their own sliders. "
                           "Mobiles are not discountable.")
            def _sync_bb_disc():
                st.session_state["c_bb_disc"] = st.session_state["c_bb_disc_w"]
                st.session_state["q_bb_discount"] = st.session_state["c_bb_disc_w"]
            def _sync_cs_disc():
                st.session_state["c_cs_disc"] = st.session_state["c_cs_disc_w"]
                st.session_state["q_cs_discount"] = st.session_state["c_cs_disc_w"]
            st.session_state["c_bb_disc_w"] = int(st.session_state.get("c_bb_disc", 0))
            st.slider("Broadband discount (%)", min_value=0, max_value=10, step=1,
                      key="c_bb_disc_w", on_change=_sync_bb_disc,
                      help="Separate discount on broadband sell prices, up to 10%. Broadband can never go below wholesale cost.")
            st.session_state["c_cs_disc_w"] = int(st.session_state.get("c_cs_disc", 0))
            st.slider("Call Scope discount (%)", min_value=0, max_value=80, step=5,
                      key="c_cs_disc_w", on_change=_sync_cs_disc,
                      help="Discount on Call Scope services, up to 80%.")
            def _sync_ac_disc():
                st.session_state["c_ac_disc"] = st.session_state["c_ac_disc_w"]
                st.session_state["q_ac_discount"] = st.session_state["c_ac_disc_w"]
            st.session_state["c_ac_disc_w"] = int(st.session_state.get("c_ac_disc", 0))
            st.slider("Air conditioning discount (%)", min_value=0, max_value=20, step=1,
                      key="c_ac_disc_w", on_change=_sync_ac_disc,
                      help="Takes this % off the air-conditioning rental or cash price, up to 20%. Commission units drop with it.")

            def _svc_row(label, list_price, new_price, note=""):
                _chg = new_price < list_price - 0.005
                _was = (f"<span style='color:var(--muted);text-decoration:line-through;margin-right:0.5rem'>£{list_price:.2f}</span>"
                        if _chg else "")
                _nt  = f"<span style='color:var(--muted);font-size:0.75rem'> {note}</span>" if note else ""
                return (f"<div style='display:flex;justify-content:space-between;padding:0.35rem 0;"
                        f"border-bottom:1px solid var(--border);font-size:0.88rem'>"
                        f"<span style='color:var(--muted)'>{label}{_nt}</span>"
                        f"<span>{_was}<strong style='color:var(--text)'>£{new_price:.2f}/mo</strong></span></div>")

            _svc_saving = ((lic_list_total - svc["lic_monthly"]) + (sw_list_total - sw_sell_total) +
                           (bb1_list + bb2_list - svc["bb_sell"]) + (_cs_list_total - _cs_svc_sell))
            _rows = ""
            if lic_list_total > 0:
                _rows += _svc_row(f"Hosted User Licences ({total_voice_channels} users)", lic_list_total, svc["lic_monthly"])
            for _an, _aq, _ac, _asell in SW_ADDONS:
                if _aq > 0:
                    _alist = _asell / _svc_mult if _svc_mult > 0 else _asell
                    _rows += _svc_row(f"{_an} x{_aq}", _alist * _aq, _asell * _aq)
            if bb1_list > 0:
                _rows += _svc_row(f"Broadband - {bb_package}", bb1_list, svc["bb1_sell"],
                                  "(at wholesale floor)" if bb_disc_pct > 0 and svc["bb1_sell"] <= svc["bb1_floor"] + 0.005 else "")
            if bb2_list > 0:
                _rows += _svc_row(f"Broadband additional lines ({extra_bb_count})", bb2_list, svc["bb2_sell"],
                                  "(at wholesale floor)" if bb_disc_pct > 0 and svc["bb2_sell"] <= svc["bb2_floor"] + 0.005 else "")
            if _cs_list_total > 0:
                _rows += _svc_row("Call Scope services", _cs_list_total, _cs_svc_sell)
            if svc.get("mobile_sell", 0) > 0:
                _rows += _svc_row("Mobiles", svc["mobile_sell"], svc["mobile_sell"], "(fixed)")
            if not _rows:
                _rows = "<div style='color:var(--muted);font-size:0.85rem'>No licences or services on this deal yet.</div>"
            st.markdown(_rows + _svc_row("<strong>Total monthly services</strong>",
                                         svc["total_sell"] + _svc_saving,
                                         svc["total_sell"]),
                        unsafe_allow_html=True)

        with _sd_col2:
            _cm_col = "#F87171" if commission_lost > 0 else "#34D399"
            _cm_bg  = "rgba(248,113,113,.12)" if commission_lost > 0 else "rgba(52,211,153,.12)"
            st.markdown(f"""
            <div style="background:{_cm_bg};border-left:4px solid {_cm_col};
                 border-radius:0 8px 8px 0;padding:1rem 1.2rem;margin-top:1.6rem">
              <div style="font-size:0.72rem;color:{_cm_col};font-weight:700;text-transform:uppercase">Commission Impact</div>
              <div style="font-size:0.85rem;color:var(--muted);margin-top:0.3rem">Before discount: <strong>£{commission_full:.2f}</strong></div>
              <div style="font-size:0.85rem;color:{_cm_col}">Discount (£{_disc_given_mo:.2f}/mo = {comm_loss_pct:.1f}% of services): <strong>-£{commission_lost:.2f}</strong></div>
              <div style="font-size:1.5rem;font-weight:800;color:var(--text);margin-top:0.3rem">£{commission:.2f}</div>
              <div style="font-size:0.75rem;color:var(--muted)">Services saving to customer: £{_svc_saving:.2f}/mo</div>
            </div>
            """, unsafe_allow_html=True)

        # Values used by the panels below
        adj_rental      = float(_desired_rental)
        adj_total_mo    = svc["total_sell"] + adj_rental
        _adj_units      = commission_units
        _adj_commission = commission

        # Feasibility mini-panel ────────────────────────────────────────────────
        _buyout_rental      = (pl_data["sales_rate"] / 1000.0) * termination_cost
        _feas_lease_total   = max(adj_rental - _buyout_rental, 0) * lease_term
        _feas_max_settle    = round(_feas_lease_total * 0.70, 2)
        _settle_ok          = termination_cost <= _feas_max_settle
        _f_col  = "#34D399" if _settle_ok else "#F87171"
        _f_bg   = "rgba(52,211,153,.12)" if _settle_ok else "rgba(248,113,113,.12)"
        _f_icon = "✅" if _settle_ok else "🔴"
        _f_msg  = "Settlement feasible" if _settle_ok else "Settlement exceeds 70% - review"
        _f_diff = _feas_max_settle - termination_cost

        st.markdown(f"""
        <div style="margin-top:0.8rem;padding:0.8rem 1.2rem;background:{_f_bg};border:1px solid {_f_col};
             border-radius:10px;display:flex;justify-content:space-between;align-items:center">
          <div>
            <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;color:{_f_col}">
              {_f_icon} Feasibility - Max Settlement (70%)</div>
            <div style="font-size:1.2rem;font-weight:800;color:{_f_col}">£{_feas_max_settle:.2f}</div>
            <div style="font-size:0.78rem;color:{_f_col}">{_f_msg} &nbsp;·&nbsp;
              {"£" + f"{abs(_f_diff):.2f}" + " headroom" if _settle_ok else "£" + f"{abs(_f_diff):.2f}" + " over limit"}
            </div>
          </div>
          <div style="text-align:right">
            <div style="font-size:0.75rem;color:{_f_col}">Settlement / Buyout</div>
            <div style="font-size:1.4rem;font-weight:800;color:{_f_col}">£{termination_cost:.2f}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Summary bar ────────────────────────────────────────────────────────────
        st.markdown(f"""
        <div style="background:var(--surface-3);border-radius:10px;padding:0.8rem 1.2rem;margin-top:0.6rem;
             display:flex;justify-content:space-between;align-items:center;color:#fff">
          <div><span style="font-size:0.8rem;color:rgba(255,255,255,0.6)">ADJUSTED TOTAL</span>
               <div style="font-size:1.6rem;font-weight:800;color:var(--accent)">£{adj_total_mo:.2f}/mo</div></div>
          <div style="text-align:right">
               <span style="font-size:0.8rem;color:rgba(255,255,255,0.6)">COMMISSION ON ADJ. RENTAL</span>
               <div style="font-size:1.4rem;font-weight:700;color:var(--good)">£{_adj_commission:.2f}
               <span style="font-size:0.8rem;font-weight:400"> ({_adj_units:.2f} units)</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Sales Calcs (pricebook-style) ─────────────────────────────────
        st.markdown("### 📐 Sales Calcs")
        _cash_price_load = 1.10   # pricebook: Cash Price Load % = 1.10
        _cash_price      = round(pl_data["sub_total"] * _cash_price_load, 2)
        _cash_gp         = _cash_price - pl_data["cos_full"]
        _cash_units      = round(_cash_gp / float(commission_unit_size or 1000), 2)

        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown(f"""
            <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;
                 padding:1rem;font-size:0.85rem">
              <table style="width:100%;border-collapse:collapse">
                <tr><td style="color:var(--muted);padding:3px 0">Cash Sale?</td>
                    <td style="font-weight:600;text-align:right">No (Lease)</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Term</td>
                    <td style="font-weight:600;text-align:right">1+{lease_term-1}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Rental (Calculated)</td>
                    <td style="font-weight:600;text-align:right;color:var(--text)">£{pl_data["rental"]:.2f}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Adjustment</td>
                    <td style="font-weight:600;text-align:right;color:{"#34D399" if rental_adjustment>=0 else "#F87171"}">{"+" if rental_adjustment>=0 else ""}£{rental_adjustment:.2f}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Units</td>
                    <td style="font-weight:600;text-align:right;color:var(--accent)">{commission_units:.2f}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Desired Rental</td>
                    <td style="font-weight:600;text-align:right;color:var(--text)">£{_desired_rental:.2f}</td></tr>
                <tr style="border-top:1px solid var(--border)">
                    <td style="color:var(--muted);padding:3px 0">Adjustment Required</td>
                    <td style="font-weight:600;text-align:right">£{abs(rental_adjustment):.2f}</td></tr>
              </table>
            </div>
            """, unsafe_allow_html=True)
        with sc2:
            st.markdown(f"""
            <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;
                 padding:1rem;font-size:0.85rem">
              <table style="width:100%;border-collapse:collapse">
                <tr><td style="color:var(--muted);padding:3px 0">Cash Adjustment</td>
                    <td style="font-weight:600;text-align:right">£0.00</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Cash Price</td>
                    <td style="font-weight:600;text-align:right">£{_cash_price:.2f}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Cash Units</td>
                    <td style="font-weight:600;text-align:right">{_cash_units:.2f}</td></tr>
                <tr style="border-top:1px solid var(--border)">
                    <td style="color:var(--muted);padding:3px 0">Other Costs</td>
                    <td style="font-weight:600;text-align:right">£{termination_cost:.2f}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Sub Total</td>
                    <td style="font-weight:600;text-align:right">£{pl_data["sub_total"]:.2f}</td></tr>
                <tr><td style="color:var(--muted);padding:3px 0">Gross Profit</td>
                    <td style="font-weight:600;text-align:right;color:var(--good)">£{pl_data["gross_profit"]:.2f}</td></tr>
              </table>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")
        # ── Proposal notes ─────────────────────────────────────────────────
        st.markdown("### 📝 Consultant Notes / Special Conditions")
        # Notes are stored in c_notes_val (saved with quotes, read by the paperwork);
        # the box is filled from it, so a loaded quote always shows its notes.
        consultant_notes = st.text_area(
            "", height=100, key="c_notes_w", value=st.session_state.get("c_notes_val", ""),
            placeholder="Add any special conditions, agreed credits, or notes for this deal...",
            label_visibility="collapsed"
        )
        st.session_state["c_notes_val"] = consultant_notes

# ── TAB 6: SIGN & SEND ────────────────────────────────────────────────────────

    # ── Termination Calculator ─────────────────────────────────────────
    st.markdown('---')
    with st.expander('🧮 Termination Calculator', expanded=False):
        st.caption("Estimates what the customer owes to leave their current agreements, from the Current "
                   "Customer Costs in the sidebar and the end date(s). Call charges are usage, so they're left out.")

        def _months_left(end):
            if not end:
                return 0
            t = date.today()
            m = (end.year - t.year) * 12 + (end.month - t.month) + (1 if end.day > t.day else 0)
            return max(0, m)

        _tc_lease_mo = float(current_system or 0)
        _tc_svc_parts = [("Broadband", current_bb), ("User licences", current_hosted), ("Mobiles", current_mobile),
                         ("IT services / M365", current_it), ("Support & maintenance", current_support),
                         ("Printing / copiers", current_printing), ("Other", current_other)]
        _tc_svc_mo = float(sum(v or 0 for _, v in _tc_svc_parts))

        tc1, tc2 = st.columns(2)
        with tc1:
            st.markdown("**Phone system lease**")
            st.caption(f"Current phone system: £{_tc_lease_mo:,.2f}/mo")
            _tc_lease_end = st.date_input("Lease end date", value=None, key="tc_lease_end", format="DD/MM/YYYY")
            _tc_lease_pct = st.number_input("% of remaining payments due", 0, 100, 100, 5, key="tc_lease_pct",
                                            help="Most lease settlements are the remaining rentals; lower this if the "
                                                 "finance company offers a rebate.")
        with tc2:
            st.markdown("**Service contracts**")
            st.caption(f"Current services: £{_tc_svc_mo:,.2f}/mo")
            _tc_same = st.checkbox("Same end date as the lease", value=True, key="tc_same_end")
            _tc_svc_end = (_tc_lease_end if _tc_same else
                           st.date_input("Services end date", value=None, key="tc_svc_end", format="DD/MM/YYYY"))
            _tc_svc_pct = st.number_input("% of remaining charges due", 0, 100, 100, 5, key="tc_svc_pct",
                                          help="Many providers charge the full remaining contract; some charge less.")

        _tc_lease_months = _months_left(_tc_lease_end)
        _tc_svc_months   = _months_left(_tc_svc_end)
        _tc_lease_settle = round(_tc_lease_mo * _tc_lease_months * _tc_lease_pct / 100.0, 2)
        _tc_svc_settle   = round(_tc_svc_mo * _tc_svc_months * _tc_svc_pct / 100.0, 2)
        _tc_total        = round(_tc_lease_settle + _tc_svc_settle, 2)

        if not (_tc_lease_end or _tc_svc_end):
            st.info("Enter the end date of the customer's current agreement to see the estimate.")
        else:
            k1, k2, k3 = st.columns(3)
            for _col, _lbl, _val, _sub in (
                (k1, "Lease settlement", _tc_lease_settle,
                 f"£{_tc_lease_mo:,.2f} × {_tc_lease_months} months × {_tc_lease_pct}%"),
                (k2, "Services settlement", _tc_svc_settle,
                 f"£{_tc_svc_mo:,.2f} × {_tc_svc_months} months × {_tc_svc_pct}%"),
                (k3, "Total estimated termination", _tc_total, "Lease + services")):
                with _col:
                    render_html(f'<div class="pe-kpi"><div class="l">{esc(_lbl)}</div>'
                                f'<div class="v">£{_val:,.0f}</div>'
                                f'<div style="color:var(--muted);font-size:.78rem;margin-top:4px">{esc(_sub)}</div></div>')
            with st.expander("What's included in services", expanded=False):
                for _n, _v in _tc_svc_parts:
                    if (_v or 0) > 0:
                        st.caption(f"{_n}: £{_v:,.2f}/mo")
            _cmp_max = (f" - the maximum for this deal is £{max_termination:,.0f}"
                        + (" (this total is over it)" if _tc_total - max_termination >= 1 else "")) if is_lease else ""
            st.caption(f"Estimate only - confirm with the customer's settlement letters.{_cmp_max}")
            if st.button(f"Use these figures (£{_tc_lease_settle:,.0f} lease + £{_tc_svc_settle:,.0f} services)", type="primary", key="tc_use_btn",
                         disabled=_tc_total <= 0):
                st.session_state["_pending_termination"] = (_tc_lease_settle, _tc_svc_settle)
                st.rerun()

    # ── Feasibility Calculator ──────────────────────────────────────────
    st.markdown('---')
    with st.expander('📊 Feasibility Calculator', expanded=False):
        st.caption('Checks whether the customer\'s existing settlement can be absorbed into the new lease.')
        # Same figures as the sidebar and Admin panel (one shared calculation)
        _new_rental     = float(_desired_rental)
        _buyout_rental  = _buyout_rental_share
        _lease_total    = lease_value_ex_buyout
        _max_settlement = max_termination
        _settlement_ok  = not termination_over
    
        feas_col1, feas_col2 = st.columns(2)
        with feas_col1:
            st.markdown(f"""
            <div style='background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.2rem'>
              <div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;color:var(--muted)'>New Monthly Rental</div>
              <div style='font-size:2rem;font-weight:800;color:var(--text)'>£{_new_rental:.2f}</div>
              <div style='font-size:0.8rem;color:var(--muted)'>per month over {LEASE_TERM_LABELS[lease_term]}</div>
              <hr style='margin:0.8rem 0'>
              <div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;color:var(--muted)'>Lease Value (funder pays)</div>
              <div style='font-size:1.3rem;font-weight:700;color:var(--text)'>£{_lease_total:.2f}</div>
              <div style='font-size:0.8rem;color:var(--muted)'>(£{_lv_rental:.2f}/mo ÷ {true_rate:.2f} × 1,000{'' if _target_active else ', before any buyout'})</div>
              <hr style='margin:0.8rem 0'>
              <div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;color:var(--muted)'>Max Settlement ({MAX_TERMINATION_PCT:.0f}%)</div>
              <div style='font-size:1.6rem;font-weight:800;color:var(--good)'>£{_max_settlement:.2f}</div>
              <div style='font-size:0.8rem;color:var(--muted)'>{MAX_TERMINATION_PCT:.0f}% of total lease value</div>
            </div>
            """, unsafe_allow_html=True)
        with feas_col2:
            _col  = '#34D399' if _settlement_ok else '#FBBF24'
            _bg   = 'rgba(52,211,153,.12)' if _settlement_ok else 'rgba(251,191,36,.12)'
            _icon = '✅' if _settlement_ok else '🔴'
            _msg  = 'Settlement FEASIBLE' if _settlement_ok else f'Settlement {termination_over_pct:.0f}% over the maximum - review required'
            _diff = _max_settlement - termination_cost
            st.markdown(f"""
            <div style='background:{_bg};border:2px solid {_col};border-radius:12px;padding:1.4rem;text-align:center'>
              <div style='font-size:2.5rem'>{_icon}</div>
              <div style='font-size:1rem;font-weight:700;color:{_col};margin-top:0.5rem'>{_msg}</div>
              <hr style='margin:0.8rem 0;border-color:{_col};opacity:0.3'>
              <div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;color:{_col}'>Customer Settlement / Buyout</div>
              <div style='font-size:1.8rem;font-weight:800;color:{_col}'>£{termination_cost:.2f}</div>
              <div style='font-size:0.8rem;color:{_col};margin-top:0.4rem'>
                {'£' + f'{abs(_diff):.2f}' + ' headroom remaining' if _settlement_ok else '£' + f'{abs(_diff):.2f}' + ' over the limit'}
              </div>
            </div>
            """, unsafe_allow_html=True)
    
        if termination_cost == 0:
            st.info('💡 Enter a buyout / termination cost in the sidebar Deal Adjustments to run the feasibility check.')
    
    

with tab6:
    st.markdown('<div class="tab-content"></div>', unsafe_allow_html=True)

    if not comp_name:
        st.warning("👈 Add a customer name in the sidebar first.")
    em_cfg = st.session_state.active_config.get("email", {})

    # Capture client IP from Streamlit request headers (best effort)
    def _get_ip():
        try:
            headers = st.context.headers
            for h in ["X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP", "True-Client-IP"]:
                ip = headers.get(h, "")
                if ip:
                    return ip.split(",")[0].strip()
        except Exception:
            pass
        return "Not captured"
    _client_ip = _get_ip()

    # ── Deal summary strip ────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:linear-gradient(160deg,var(--surface-3) 0%,var(--surface-2) 100%);border-radius:12px;
            padding:1rem 1.5rem;margin-bottom:1.2rem;display:flex;
            justify-content:space-between;align-items:center;color:#fff">
      <div>
    <div style="font-size:0.75rem;color:rgba(255,255,255,0.6);text-transform:uppercase;letter-spacing:.08em">Customer</div>
    <div style="font-size:1.1rem;font-weight:700">{esc(comp_name)}</div>
      </div>
      <div style="text-align:center">
    <div style="font-size:0.75rem;color:rgba(255,255,255,0.6);text-transform:uppercase;letter-spacing:.08em">Monthly Services</div>
    <div style="font-size:1.4rem;font-weight:800;color:var(--accent)">£{total_mo:.2f} + VAT</div>
      </div>
      <div style="text-align:right">
    <div style="font-size:0.75rem;color:rgba(255,255,255,0.6);text-transform:uppercase;letter-spacing:.08em">Upfront</div>
    <div style="font-size:1.1rem;font-weight:700">£{upfront:.2f} + VAT</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    sign_col, send_col = st.columns([3, 2])

    with sign_col:
        st.markdown("### Customer Signature")
        st.caption("Ask the customer to sign below, or photograph their signature.")

        # Two options: draw on screen OR upload photo
        sig_method = st.radio(
            "Capture method:",
            ["Draw on screen", "Upload photo of signature"],
            horizontal=True, key="sig_method_radio"
        )

        if sig_method == "Upload photo of signature":
            st.caption("Take a photo of the customer's handwritten signature or upload an image file.")
            sig_upload = st.file_uploader(
                "Signature image (JPG or PNG)", type=["jpg","jpeg","png"],
                key="sig_photo_upload", label_visibility="collapsed"
            )
            if sig_upload:
                from PIL import Image as _PILImage
                _simg = _PILImage.open(sig_upload).convert("RGB")
                # Resize to standard signature dimensions
                _simg = _simg.resize((400, 120), _PILImage.LANCZOS)
                _sbuf = io.BytesIO()
                _simg.save(_sbuf, format="PNG")
                st.session_state["_sig_bytes"] = _sbuf.getvalue()
                st.image(sig_upload, caption="Signature preview", width=300)
                st.success("Signature uploaded")
            elif not st.session_state.get("_sig_bytes"):
                st.session_state.pop("_sig_bytes", None)

        else:  # Draw on screen
            if not CANVAS_OK:
                st.warning("Drawing pad unavailable. Please use Upload photo instead.")
            else:
                with st.container(border=True):
                    st.caption("Draw with mouse, finger or stylus. Toolbar (top-right of box) to undo/clear.")
                    try:
                        canvas_result = st_canvas(
                            fill_color="rgba(0,0,0,0)",
                            stroke_width=3,
                            stroke_color="#000000",
                            background_color="#EAF4FB",
                            update_streamlit=True,
                            height=180,
                            width=510,
                            drawing_mode="freedraw",
                            display_toolbar=True,
                            key="sig_canvas",
                        )
                    except TypeError:
                        canvas_result = st_canvas(
                            fill_color="rgba(0,0,0,0)",
                            stroke_width=3,
                            stroke_color="#000000",
                            background_color="#EAF4FB",
                            update_streamlit=True,
                            height=180,
                            width=510,
                            drawing_mode="freedraw",
                            key="sig_canvas",
                        )
                # Explicit save button - more reliable than auto-detect
                _btn_col, _clr_col = st.columns(2)
                with _btn_col:
                    if st.button("✅ Save Signature", use_container_width=True,
                                 type="primary", key="btn_save_sig"):
                        try:
                            _img_data = canvas_result.image_data if canvas_result else None
                            if _img_data is not None:
                                from PIL import Image as _PILImage
                                # Save as RGBA PNG - fpdf2 temp file handles transparency
                                sig_pil = _PILImage.fromarray(
                                    _img_data.astype("uint8"), "RGBA"
                                )
                                # Flatten onto white
                                _white = _PILImage.new("RGBA", sig_pil.size, (255,255,255,255))
                                _white.paste(sig_pil, mask=sig_pil.split()[3])
                                sig_pil_rgb = _white.convert("RGB")
                                # Turn the pad's pale-blue background pure white so the signature sits naturally on the paperwork
                                _arr = np.array(sig_pil_rgb).astype("int16")
                                _bgd = np.abs(_arr - np.array([234, 244, 251])).max(axis=2)
                                _arr[_bgd < 40] = 255
                                sig_pil_rgb = _PILImage.fromarray(_arr.astype("uint8"), "RGB")
                                sig_buf = io.BytesIO()
                                sig_pil_rgb.save(sig_buf, format="PNG")
                                st.session_state["_sig_bytes"] = sig_buf.getvalue()
                                st.rerun()
                            else:
                                st.warning("Canvas returned no data - please try Upload photo.")
                        except Exception as _ce:
                            st.warning(f"Canvas capture failed ({type(_ce).__name__}: {_ce}). Use Upload photo.")
                with _clr_col:
                    if st.button("🗑️ Clear", use_container_width=True, key="btn_clr_sig"):
                        st.session_state.pop("_sig_bytes", None)
                        st.rerun()

        sig_bytes = st.session_state.get("_sig_bytes")
        if sig_bytes:
            # Show preview so consultant can confirm it captured correctly
            st.success("✅ Signature saved")
            try:
                st.image(sig_bytes, width=200, caption="Signature preview")
            except Exception:
                pass
        else:
            st.caption("✏️ Draw signature above then click Save Signature")

        sig_bytes = st.session_state.get("_sig_bytes")
        if sig_bytes:
            st.success("✅ Signature saved - ready to download")
        else:
            st.caption("✏️ Draw signature above then click Save Signature")

        # Confirm name typed
        sig_name = st.text_input("Customer full name and position (typed confirmation)",
                                 value=contact_name or "", key="sig_name_confirm",
                                 placeholder="e.g. Jane Smith - Director")
    with send_col:
        st.markdown("### 📥 Download & Send")
        sig_bytes = st.session_state.get("_sig_bytes")
        safe = (comp_name or "quote").replace(" ","_")
        from datetime import datetime as _dtnow
        _ts = _dtnow.now().strftime("%d/%m/%Y  %H:%M")

        _two = n_packs() >= 2
        st.markdown("### 🧭 Signing steps")
        _unsigned_bytes = build_pdf(sig_bytes=None, curr_total=current_total, curr_bb=current_bb,
                                    curr_system=current_system, curr_calls=current_calls, curr_mobile=current_mobile)

        # ── Steps 1-2: the initial document, signed in Zoho Sign ────────────────
        if _tele_any:
            st.markdown("#### Step 1 - Download the unsigned agreement to proceed")
            st.caption("The Contract Information Sheet: the contract term and costings with a single signature box ('Acceptance of contract terms'), for Zoho Sign.")
            _cis_blank = build_proposal_pdf(sign={"sig_bytes": None, "name": sig_name or "", "company": comp_name or "", "timestamp": ""}, cis=True)
            st.download_button("📥 Download unsigned Contract Information Sheet", data=_cis_blank,
                               file_name=f"SWComms_{safe}_ContractInfoSheet_{date.today()}.pdf",
                               mime="application/pdf", use_container_width=True, key="dl_cis_blank")
            with st.expander("Or sign this first document here instead"):
                if sig_bytes and sig_name:
                    st.download_button("✅ Contract Information Sheet - signed now",
                                       data=build_proposal_pdf(sign={"sig_bytes": sig_bytes, "name": sig_name, "company": comp_name or "", "timestamp": _ts}, cis=True),
                                       file_name=f"SWComms_{safe}_ContractInfoSheet_SIGNED_{date.today()}.pdf",
                                       mime="application/pdf", use_container_width=True, type="primary", key="dl_cis_signed")
                else:
                    st.caption("Add the signature and name (step 3) to sign it here.")
            st.markdown("#### Step 2 - Send it via Zoho Sign")
            st.link_button("Open Zoho Sign - send the Contract Information Sheet →", "https://sign.zoho.eu")
            _cis_done = st.checkbox("Step 2 complete - the customer has signed it and it has been returned", key="cis_done")
        else:
            _cis_done = True
            st.info("There is no telephony on this deal, so the Contract Information Sheet (steps 1 and 2) isn't needed - start at step 3.")

        # ── Step 3: capture ────────────────────────────────────────────────────
        st.markdown("#### Step 3 - Capture the customer's signature, name and position")
        st.caption("On the left: draw or upload the signature, press Save Signature, then type their full name and position.")
        st.markdown(("✅" if sig_bytes else "⬜") + " Signature saved  \n" + ("✅" if sig_name else "⬜") + " Name and position typed")

        # ── Step 4: signed pack ───────────────────────────────────────────────
        st.markdown("#### Step 4 - Download the " + ("combined " if _two else "") + "signed pack")
        st.caption("The signature, name and date are filled in everywhere they belong - apart from the single 'Agreement to proceed' box on the proposal, "
                   "which is left blank for Zoho Sign.")
        if cs_crm_missing:
            st.warning("Call Scope is held back from the pack until the customer's CRM is entered in the Call Scope card.")
        _signed_bytes = None
        _sgx = {"sig_bytes": sig_bytes, "name": sig_name, "company": comp_name or "", "ts": _ts, "ip": _client_ip}
        if sig_bytes and sig_name and _cis_done:
            if _tele_any:
                _signed_bytes = build_pdf(sig_bytes=sig_bytes, sig_name=sig_name, sig_company=comp_name or "", sig_timestamp=_ts, sig_ip=_client_ip,
                                          curr_total=current_total, curr_bb=current_bb, curr_system=current_system,
                                          curr_calls=current_calls, curr_mobile=current_mobile)
            try:
                _main = build_combined(_signed_bytes, _sgx) if (_two or not _tele_any) else _signed_bytes
                st.session_state["_signed_pdf_bytes"]    = _main
                st.session_state["_signed_pdf_filename"] = f"{'Combined_Pack' if _two else 'SWComms'}_{safe}_SIGNED_{date.today()}.pdf"
                st.download_button("✅ Download the " + ("COMBINED " if _two else "") + "signed pack", data=_main,
                                   file_name=st.session_state["_signed_pdf_filename"], mime="application/pdf",
                                   use_container_width=True, type="primary", key="dl_signed")
            except Exception as _cse:
                st.error(f"Couldn't build the signed pack: {_cse}")
        else:
            _why = []
            if _tele_any and not _cis_done: _why.append("tick 'Step 2 complete' above")
            if not sig_bytes: _why.append("save the signature")
            if not sig_name: _why.append("type the customer name and position")
            st.button("✅ Download the " + ("COMBINED " if _two else "") + "signed pack", disabled=True, use_container_width=True, key="dl_signed_dis")
            st.caption("To unlock it: " + ", ".join(_why) + ".")

        # ── Step 5 ────────────────────────────────────────────────────────────
        st.markdown("#### Step 5 - Send it via Zoho Sign")
        st.caption("Upload the signed pack. The customer signs the one 'Agreement to proceed' box that was left blank.")
        st.link_button("Open Zoho Sign - send the signed pack →", "https://sign.zoho.eu")

        # ── Step 6 ────────────────────────────────────────────────────────────
        st.markdown("#### Step 6 - Save the " + ("combined " if _two else "") + "document pack")
        st.caption("When Zoho Sign returns the completed document, save it together with this quote file, so the deal can be reopened later "
                   "(Load previous quote) - for example to correct the branding and re-issue the paperwork.")
        st.download_button("💾 Save the quote file (.json)", data=json.dumps(quote_snapshot(), indent=2, default=str),
                           file_name=f"SWComms_{safe}_QUOTE_{date.today()}.json", mime="application/json",
                           use_container_width=True, key="dl_signed_quote")

        st.divider()
        st.markdown("### 🗂️ Individual packs and other documents")
        st.caption("If you only need one pack, or want to preview a blank one, use these.")
        if _tele_any:
            st.markdown("**Telephony pack**")
            st.download_button("📥 Download Full Pack (Unsigned)", data=_unsigned_bytes, file_name=f"SWComms_{safe}_{date.today()}.pdf",
                               mime="application/pdf", use_container_width=True, key="dl_unsigned")
            if _signed_bytes:
                st.download_button("✅ Download Signed Telephony Pack", data=_signed_bytes, file_name=f"SWComms_{safe}_SIGNED_{date.today()}.pdf",
                                   mime="application/pdf", use_container_width=True, key="dl_signed_tele")
        if _two and not cs_crm_missing:
            st.markdown("**Combined pack - blank signature boxes**")
            try:
                st.download_button("📦 Combined pack - blank (for review or Zoho Sign)", data=build_combined(_unsigned_bytes),
                                   file_name=f"Combined_Pack_{safe}_{date.today()}.pdf", mime="application/pdf",
                                   use_container_width=True, key="dl_comb_blank")
            except Exception as _cse:
                st.error(f"Couldn't build the combined pack: {_cse}")

        if cs_active:
            st.divider()
            st.markdown("#### Call Scope pack (separate agreement)")
            st.caption("Its own Agreement to proceed, order, price schedule, Terms & Conditions and Direct Debit mandate - signed separately from the telephony pack.")
            if cs_crm_missing:
                st.warning("Enter the customer's CRM in the Call Scope card (AI CRM Integration) to produce this pack.")
            else:
                try:
                    st.download_button("📥 Call Scope pack - blank signature (for Zoho Sign)", data=build_callscope_pack(),
                                       file_name=f"CallScope_{safe}_{date.today()}.pdf", mime="application/pdf",
                                       use_container_width=True, key="dl_cs_blank")
                    if sig_bytes and sig_name:
                        st.download_button("✅ Call Scope pack - signed now",
                                           data=build_callscope_pack({"sig": sig_bytes, "name": sig_name, "date": date.today().strftime("%d/%m/%Y")}),
                                           file_name=f"CallScope_{safe}_SIGNED_{date.today()}.pdf", mime="application/pdf",
                                           use_container_width=True, type="primary", key="dl_cs_signed")
                    else:
                        st.caption("To sign it here instead, add the signature and name on the left.")
                except Exception as _cse:
                    st.error(f"Couldn't build the Call Scope pack: {_cse}")

        if is_lease and float(hw_monthly_spread or 0) > 0:
            st.divider()
            st.markdown("**Shire Leasing hire agreement (the finance company's form for the telephone system)**")
            st.caption("Completed automatically from the customer details and the lease rental. Signed with the same signature.")
            _tbk_miss = [n for n, v in (("bank name", bank_name), ("account number", acc_no), ("sort code", sort_code)) if not v]
            if _tbk_miss:
                st.caption("Direct Debit details still missing in the left-hand bar (" + ", ".join(_tbk_miss) + ") - those boxes stay blank on the form.")
            try:
                st.download_button("📥 Shire agreement - blank signature (for Zoho Sign)", data=ac_build_shire(None, tel_shire_values(None)),
                                   file_name=f"{_CO_FILE.split('_')[0]}_{safe}_Shire_Agreement_{date.today()}.pdf", mime="application/pdf",
                                   use_container_width=True, key="dl_tel_shire_blank")
                if sig_bytes and sig_name:
                    _tsg = {"bytes": sig_bytes, "name": sig_name, "company": comp_name or "", "ts": _ts}
                    st.download_button("✅ Shire agreement - signed now", data=ac_build_shire(_tsg, tel_shire_values(_tsg)),
                                       file_name=f"{_CO_FILE.split('_')[0]}_{safe}_Shire_Agreement_SIGNED_{date.today()}.pdf", mime="application/pdf",
                                       use_container_width=True, type="primary", key="dl_tel_shire_signed")
            except Exception as _tse:
                st.error(f"Couldn't build the Shire agreement: {_tse}")

        if ac_active:
            st.divider()
            st.markdown("#### ❄️ SteadyTemp pack (separate agreement)")
            st.caption("Its own Proposal, Order Form, On-Site Support Agreement, Direct Debit set-up and Terms & Conditions under SteadyTemp LTD - signed separately from the telephony pack.")
            try:
                st.download_button("📥 SteadyTemp pack - blank signature (for Zoho Sign)", data=build_steadytemp_pack(),
                                   file_name=f"SteadyTemp_{safe}_{date.today()}.pdf", mime="application/pdf",
                                   use_container_width=True, key="dl_st_blank")
                if sig_bytes and sig_name:
                    st.download_button("✅ SteadyTemp pack - signed now",
                                       data=build_steadytemp_pack({"sig_bytes": sig_bytes, "name": sig_name, "company": comp_name or "", "ts": _ts, "ip": _client_ip}),
                                       file_name=f"SteadyTemp_{safe}_SIGNED_{date.today()}.pdf", mime="application/pdf",
                                       use_container_width=True, type="primary", key="dl_st_signed")
                else:
                    st.caption("To sign it here instead, add the signature and name on the left.")
            except Exception as _ste:
                st.error(f"Couldn't build the SteadyTemp pack: {_ste}")
            if not ac_quote["is_cash"]:
                st.markdown("**Shire Leasing hire agreement (the finance company's form for the air conditioning)**")
                st.caption("Filled in from the customer details above and signed with the same signature.")
                _bk_miss = [n for n, v in (("bank name", bank_name), ("account number", acc_no), ("sort code", sort_code)) if not v]
                if _bk_miss:
                    st.caption("Direct Debit details still missing in the left-hand bar (" + ", ".join(_bk_miss) + ") - those boxes stay blank on the form.")
                try:
                    st.download_button("📥 Shire agreement - blank signature (for Zoho Sign)", data=ac_build_shire(None),
                                       file_name=f"SteadyTemp_{safe}_Shire_Agreement_{date.today()}.pdf", mime="application/pdf",
                                       use_container_width=True, key="dl_shire_blank")
                    if sig_bytes and sig_name:
                        st.download_button("✅ Shire agreement - signed now",
                                           data=ac_build_shire({"bytes": sig_bytes, "name": sig_name, "company": comp_name or "", "ts": _ts}),
                                           file_name=f"SteadyTemp_{safe}_Shire_Agreement_SIGNED_{date.today()}.pdf", mime="application/pdf",
                                           use_container_width=True, type="primary", key="dl_shire_signed")
                except Exception as _e:
                    st.error(f"Couldn't build the Shire agreement: {_e}")

        if _loa_data()["on"] and _loa_data()["numbers"]:
            st.divider()
            st.markdown("**Letter of Authority (for the old provider)**")
            st.caption("On its own, with no pricing - ready to send to the customer's current provider.")
            _loa_signed = bool(sig_bytes and sig_name and _cis_done)
            _loa_bytes = build_loa_pdf(sig_bytes=sig_bytes if _loa_signed else None, sig_ts=_ts if _loa_signed else "")
            if _loa_bytes:
                st.download_button(
                    "📞 Download Letter of Authority" + (" (signed)" if _loa_signed else " (unsigned)"),
                    data=_loa_bytes,
                    file_name=f"LetterOfAuthority_{safe}_{'SIGNED_' if _loa_signed else ''}{date.today()}.pdf",
                    mime="application/pdf", use_container_width=True, key="dl_loa_sign")

        st.divider()


    st.divider()
    st.markdown("### ✍️ Send via Zoho Sign")
    st.caption("Follow the six signing steps above. The Contract Information Sheet goes to Zoho Sign first; once it is signed, the signed pack "
               "(combined, if Call Scope or air conditioning is on the deal) goes with its single 'Agreement to proceed' box left blank.")
    st.link_button("Open Zoho Sign →", "https://sign.zoho.eu", use_container_width=False)

if _show_admin:
    with tab7:
        st.markdown('<div class="tab-content"></div>', unsafe_allow_html=True)

        st.markdown("### 🔐 Manager & Admin Panel")

        # ── PASSWORD GATE ──────────────────────────────────────────────────────────
        if not st.session_state.admin_unlocked:
            st.markdown("#### Enter password to unlock")
            pw_col1, pw_col2 = st.columns([3, 1])
            with pw_col1:
                entered_pw = st.text_input("Password", type="password", key="admin_pw_input", label_visibility="collapsed", placeholder="Enter your login password (or the manager password)...")
            with pw_col2:
                if st.button("Unlock 🔓", use_container_width=True):
                    h = hashlib.sha256(entered_pw.encode()).hexdigest()
                    _adm_secret = _secret("ADMIN_PASSWORD")
                    _cfg_hash   = st.session_state.active_config["meta"].get("password_hash", "")
                    _cfg_ok     = bool(_cfg_hash) and _cfg_hash != _DEFAULT_PWD_HASH  # ignore built-in default
                    if _admin_own_pw_ok(entered_pw):
                        st.session_state.admin_unlocked = True
                        st.rerun()
                    elif (st.session_state.get("current_user") or {}).get("role") == "admin" and not _adm_secret and not _cfg_ok:
                        st.error("Incorrect password - use the password you signed in with.")
                    elif not _adm_secret and not _cfg_ok:
                        st.error("Admin sign-in isn't set up yet. Add ADMIN_PASSWORD to the app's Secrets"
                                 + (", or sign in as an admin user and use your own password." if _USERS else "."))
                    elif ((_adm_secret and hmac.compare_digest(entered_pw.encode(), _adm_secret.encode()))
                          or (_cfg_ok and hmac.compare_digest(h, _cfg_hash))):
                        st.session_state.admin_unlocked = True
                        st.rerun()
                    else:
                        st.error("Incorrect password")
            # Still need these vars defined even when locked
            override_customer = ""; override_initials = ""
            override_monthly_lease = 0.0; override_bb_sell = 0.0
            override_upfront = 0.0; override_install_cost = 0.0
            credits_months = 0; credits_amount = 0.0; cashback_amount = 0.0
        else:
            # ── UNLOCKED - show lock button + tabs ─────────────────────────────────
            lock_col, info_col = st.columns([1, 4])
            with lock_col:
                if _cu_role != "admin" and st.button("🔒 Lock Panel", use_container_width=True):   # admins stay unlocked
                    st.session_state.admin_unlocked = False
                    st.rerun()
            with info_col:
                st.markdown('<span class="override-badge">🔓 Admin Unlocked</span>', unsafe_allow_html=True)

            panel_tabs = st.tabs(["📋 Deal Extras", "🖥️ Hardware", "💳 Service Pricing", "🌐 Broadband & Rates", "💰 Costs & Fees", "🎨 Branding", "📧 Email", "📸 Images", "🔒 Security", "🔗 Zoho"])

            # ── TAB 1: Deal extras (credits / cashback only - there are no price overrides at South Wales Comms) ──
            with panel_tabs[0]:
                st.caption("Everything is sold at cost + 20%, so there are no price overrides. Change a hardware cost in the Hardware tab and its sell price follows.")
                mgr_col1, mgr_col2 = st.columns(2)
                with mgr_col1:
                    override_customer = st.text_input("Customer Name (for audit)", key="mgr_cust")
                    override_initials = st.text_input("Manager Initials", key="mgr_init")
                    override_monthly_lease = 0.0
                    override_bb_sell = 0.0
                with mgr_col2:
                    override_upfront = 0.0
                    override_install_cost = 0.0
                    credits_months = st.number_input("Introductory Credit Period (months)", min_value=0, value=int(st.session_state.get("adm_credits_months",0)), step=1, key="adm_credits_months")
                    credits_amount = st.number_input("Monthly Credit Amount (£)", min_value=0.0, value=float(st.session_state.get("adm_credits_amount",0.0)), step=5.0, key="adm_credits_amount")
                    cashback_amount = st.number_input("Cashback / Settlement Fund (£)", min_value=0.0, value=float(st.session_state.get("adm_cashback",0.0)), step=50.0, key="adm_cashback")

            # ── TAB 2: Hardware Catalogue ──────────────────────────────────────────
            with panel_tabs[1]:
                st.markdown("**System Desk Phones** - edit buy prices, add or remove rows")
                desk_df = pd.DataFrame(cfg["handsets_desktop"])
                edited_desk = st.data_editor(desk_df, num_rows="dynamic", use_container_width=True, key="de_desktop",
                    column_config={"poe": st.column_config.CheckboxColumn("PoE"),
                                   "buy": st.column_config.NumberColumn("Buy £", format="%.2f"),
                                   "cat": st.column_config.SelectboxColumn("Category", options=["Desktop","Conference"])})

                st.markdown("**Cordless Handsets**")
                cord_df = pd.DataFrame(cfg["handsets_cordless"])
                edited_cord = st.data_editor(cord_df, num_rows="dynamic", use_container_width=True, key="de_cordless",
                    column_config={"bogof": st.column_config.CheckboxColumn("BOGOF Promo"),
                                   "buy": st.column_config.NumberColumn("Buy £", format="%.2f"),
                                   "cat": st.column_config.SelectboxColumn("Category", options=["Wi-Fi","DECT"])})

                st.markdown("**Headsets**")
                hs_df = pd.DataFrame(cfg["headsets"])
                edited_hs = st.data_editor(hs_df, num_rows="dynamic", use_container_width=True, key="de_headsets",
                    column_config={"buy": st.column_config.NumberColumn("Buy £", format="%.2f")})

                # ── Call Scope AI Setup cost ──────────────────────────────────
                st.markdown("**Call Scope AI Setup (one-off lease cost)**")
                _cs_item = next((i for i in cfg["other_hardware"]
                                 if i.get("name") == "Call Scope AI Setup (one-off)"), None)
                _cs_buy  = float(_cs_item["buy"]) if _cs_item else 1000.0
                _cs_sell = float(_cs_item.get("sell", 2500.0)) if _cs_item else 2500.0
                cs_col1, cs_col2 = st.columns(2)
                with cs_col1:
                    new_cs_buy  = st.number_input("Setup Cost to South Wales Comms (Buy £)", value=_cs_buy,
                                                   step=50.0, key="cs_buy_input")
                with cs_col2:
                    new_cs_sell = round(new_cs_buy * 1.2, 2)
                    st.caption(f"Setup price to customer: £{new_cs_sell:,.2f} (cost + 20%)")
                if st.button("Update Call Scope Setup Cost", key="cs_update"):
                    for item in st.session_state.active_config["other_hardware"]:
                        if item.get("name") == "Call Scope AI Setup (one-off)":
                            item["buy"]  = new_cs_buy
                            item.setdefault("sell", new_cs_sell)
                            item["sell"] = new_cs_sell
                            break
                    else:
                        st.session_state.active_config["other_hardware"].append(
                            {"name": "Call Scope AI Setup (one-off)", "buy": new_cs_buy, "sell": new_cs_sell}
                        )
                    st.success(f"Updated: Buy £{new_cs_buy:.2f} / Sell £{new_cs_sell:.2f}")
                    st.rerun()
                st.markdown("---")
                st.markdown("**Other Hardware**")
                st.markdown("**Call Scope Platform — Service Pricing**")
                cs_svc_df = pd.DataFrame(cfg.get("call_scope_services", []))
                if not cs_svc_df.empty:
                    edited_cs = st.data_editor(cs_svc_df, num_rows="dynamic",
                        use_container_width=True, key="de_cs_svc",
                        column_config={
                            "buy": st.column_config.NumberColumn("Buy £/user/mo", format="%.2f"),
                            "sell": st.column_config.NumberColumn("Sell £/user/mo", format="%.2f")})

                    if st.button("Apply Call Scope Service Pricing", key="cs_svc_apply"):
                        st.session_state.active_config["call_scope_services"] = edited_cs.to_dict("records")
                        st.success("Call Scope service pricing updated"); st.rerun()
                st.markdown("**Call Scope Lease Items (incl. Platform Setup Fee)**")
                _cs_lease_items = [i for i in cfg.get("other_hardware", [])
                                   if i.get("name","") in ("Call Answer (500 mins)", "Website Widget", "Call Scope Platform Setup", "Call Scope AI Receptionist Setup (one-off)")]
                cs_lease_df = pd.DataFrame(_cs_lease_items)
                if not cs_lease_df.empty:
                    edited_csl = st.data_editor(cs_lease_df, num_rows="fixed",
                        use_container_width=True, key="de_cs_lease",
                        column_config={
                            "buy": st.column_config.NumberColumn("Buy £", format="%.2f"),
                            "sell": st.column_config.NumberColumn("Sell £", format="%.2f")})
                    if st.button("Apply Call Scope Lease Pricing", key="csl_apply"):
                        names_to_update = {r["name"]: r for r in edited_csl.to_dict("records")}
                        for item in st.session_state.active_config["other_hardware"]:
                            if item.get("name") in names_to_update:
                                item.update(names_to_update[item["name"]])
                        st.success("Call Scope lease pricing updated"); st.rerun()
                st.markdown("**System Security Tier Pricing**")
                sec_df_admin = pd.DataFrame(cfg.get("system_security", []))
                if not sec_df_admin.empty:
                    edited_sec = st.data_editor(sec_df_admin, num_rows="fixed",
                        use_container_width=True, key="de_security",
                        column_config={
                            "buy": st.column_config.NumberColumn("Buy £/instance/mo", format="%.2f"),
                            "sell": st.column_config.NumberColumn("Sell £/instance/mo", format="%.2f")})
                    if st.button("Apply Security Pricing", key="sec_apply"):
                        st.session_state.active_config["system_security"] = edited_sec.to_dict("records")
                        st.success("Security tier pricing updated"); st.rerun()
                st.markdown("---")
                oh_df = pd.DataFrame(cfg["other_hardware"])
                edited_oh = st.data_editor(oh_df, num_rows="dynamic", use_container_width=True, key="de_other",
                    column_config={"buy": st.column_config.NumberColumn("Buy £", format="%.2f")})

                hw_col1, hw_col2 = st.columns(2)
                with hw_col1:
                    st.markdown("**Switches**")
                    sw_df = pd.DataFrame(cfg["switches"])
                    edited_sw = st.data_editor(sw_df, num_rows="dynamic", use_container_width=True, key="de_switches",
                        column_config={"buy": st.column_config.NumberColumn("Buy £", format="%.2f"),
                                       "poe_ports": st.column_config.NumberColumn("POE Ports")})
                with hw_col2:
                    st.markdown("**Routers**")
                    st.caption("Customer sell £ is optional: a fixed upfront price per router. Leave blank to use cost + the upfront uplift.")
                    rt_df = pd.DataFrame(_clean_rows(cfg["routers"]))
                    if "sell" not in rt_df.columns:
                        rt_df["sell"] = None
                    edited_rt = st.data_editor(rt_df, num_rows="dynamic", use_container_width=True, key="de_routers",
                        column_config={"buy": st.column_config.NumberColumn("Buy £", format="%.2f"),
                                       "sell": st.column_config.NumberColumn("Customer sell £", format="%.2f")})

                if st.button("✅ Apply Hardware Changes", type="primary", key="apply_hw"):
                    st.session_state.active_config["handsets_desktop"] = _clean_rows(edited_desk.dropna(subset=["name"]).to_dict("records"))
                    st.session_state.active_config["handsets_cordless"] = _clean_rows(edited_cord.dropna(subset=["name"]).to_dict("records"))
                    st.session_state.active_config["headsets"] = _clean_rows(edited_hs.dropna(subset=["name"]).to_dict("records"))
                    st.session_state.active_config["other_hardware"] = _clean_rows(edited_oh.dropna(subset=["name"]).to_dict("records"))
                    st.session_state.active_config["switches"] = _clean_rows(edited_sw.dropna(subset=["name"]).to_dict("records"))
                    st.session_state.active_config["routers"] = _clean_rows(edited_rt.dropna(subset=["name"]).to_dict("records"))
                    st.success("Hardware catalogue updated! Changes are live for this session.")
                    st.rerun()

                st.markdown("---")
                st.markdown("**❄️ Air conditioning - catalogue & costs**")
                st.caption("The air-conditioning equipment shown in the Air Conditioning dropdown. Cost = what we pay; RRP x the customer price multiplier = what the customer is charged. "
                           "Lease rates and commission are the pricebook's own.")
                _ac_df = pd.DataFrame(cfg.get("aircon", {}).get("catalogue") or AC_CAT_DEFAULT)
                for _c in ("name", "group", "kind", "desc", "cost", "rrp"):
                    if _c not in _ac_df.columns:
                        _ac_df[_c] = None
                _ac_edit = st.data_editor(_ac_df[["name", "group", "kind", "desc", "cost", "rrp"]], num_rows="dynamic", use_container_width=True, key="de_aircon",
                    column_config={"cost": st.column_config.NumberColumn("Cost £", format="%.2f"), "rrp": st.column_config.NumberColumn("RRP £", format="%.2f"),
                                   "group": st.column_config.SelectboxColumn("Group", options=["Wall Mounted", "Ceiling Cassette", "Ducted", "Lossnay Air Exchange", "Extras", "Materials", "Labour"]),
                                   "kind": st.column_config.SelectboxColumn("Kind", options=["wall", "ceiling", "ducted", "lossnay", "extra", "material", "labour"])})
                _ac_labels = {"srrp_mult": "Customer price multiplier (x RRP)", "install_mult": "Installation customer price multiplier (x cost)",
                              "maint_wall": "Support £/mo - wall", "maint_ceiling": "Support £/mo - cassette", "maint_ducted": "Support £/mo - ducted", "maint_lossnay": "Support £/mo - Lossnay",
                              "lab_wall": "Install labour £ - wall", "lab_ceiling": "Install labour £ - cassette", "lab_ducted": "Install labour £ - ducted", "lab_lossnay": "Install labour £ - Lossnay",
                              "electrician": "Electrician £ per system", "cherry_picker": "Cherry picker £", "pump": "Condensate pump £",
                              "install_day_rate": "Engineer day rate £", "travel_hours": "Extra days when more than (hours) from the office", "free_support_years": "Included support (years)",
                              "telemarketing": "Telemarketing cost £ (in the rental)", "sales_override": "Sales override £ (in the rental)", "min_commission": "Minimum commission £ (in the rental)",
                              "cash_load": "Cash sale multiplier (x set-up + RRP)"}
                _ac_new = {}
                _acc = st.columns(3)
                for _n, (_k, _lab) in enumerate(_ac_labels.items()):
                    with _acc[_n % 3]:
                        _ac_new[_k] = st.number_input(_lab, value=float(AC_COST.get(_k, AC_COST_DEFAULT[_k])), step=1.0 if _k not in ("srrp_mult", "install_mult") else 0.1, key="acadm_" + _k)
                _ac_new["office_postcode"] = st.text_input("Office postcode (for the journey)", value=str(AC_COST.get("office_postcode", "CF14 2BT")), key="acadm_pc")
                st.markdown("**SteadyTemp rental rates** (per £1,000 of the deal, per month)")
                _lr_df = pd.DataFrame(_ac_cfg.get("lease_rates") or AC_LEASE_DEFAULT)[["months", "label", "rate", "true_rate"]]
                _lr_edit = st.data_editor(_lr_df, num_rows="dynamic", use_container_width=True, key="de_ac_lease",
                    column_config={"rate": st.column_config.NumberColumn("Customer rate", format="%.2f"), "true_rate": st.column_config.NumberColumn("Finance partner rate", format="%.2f")})
                if st.button("✅ Save SteadyTemp rental rates", key="acadm_lr"):
                    st.session_state.active_config["aircon"] = {**(st.session_state.active_config.get("aircon") or {}),
                        "lease_rates": [r for r in _lr_edit.dropna(subset=["months"]).to_dict("records")]}
                    st.success("Rental rates saved"); st.rerun()
                if st.button("✅ Apply air-conditioning changes", type="primary", key="acadm_apply"):
                    _rows_ac = [r for r in _ac_edit.dropna(subset=["name"]).to_dict("records") if str(r.get("name") or "").strip()]
                    for _r in _rows_ac:
                        _r["cost"] = float(_r.get("cost") or 0); _r["rrp"] = float(_r.get("rrp") or 0)
                    st.session_state.active_config["aircon"] = {**(st.session_state.active_config.get("aircon") or {}), "catalogue": _rows_ac, "costs": {**AC_COST, **_ac_new}}
                    st.success("Air-conditioning prices updated - live for this session. Download the config from Admin to keep them.")
                    st.rerun()

                st.markdown("---")
                st.markdown("**🖼️ Product Image Assignment**")
                st.caption("Assign an image to any product - saved directly in config.json "
                           "so it's always matched by exact name, no fuzzy logic needed.")

                # Build complete product list from all categories
                _all_products = (
                    [d["name"] for d in cfg.get("handsets_desktop", []) if d.get("name")] +
                    [d["name"] for d in cfg.get("handsets_cordless", []) if d.get("name")] +
                    [d["name"] for d in cfg.get("headsets", []) if d.get("name")] +
                    [d["name"] for d in cfg.get("other_hardware", []) if d.get("name")] +
                    [f"Switch: {d['name']}" for d in cfg.get("switches", []) if d.get("name")] +
                    [d["name"] for d in cfg.get("routers", []) if d.get("name")] +
                    ["SW Comms Studio", "Call Scope AI Agent",
                     "ACD Light Agent", "Click to Dial", "Call Recording Dashboard"]
                )

                img_col1, img_col2 = st.columns([2, 3])
                with img_col1:
                    selected_product = st.selectbox("Select product", sorted(_all_products),
                                                    key="img_product_select")
                    img_upload = st.file_uploader("Upload image (JPG or PNG)",
                                                  type=["jpg","jpeg","png"],
                                                  key="img_product_upload",
                                                  label_visibility="collapsed")
                    if img_upload and selected_product:
                        from PIL import Image as _PILImg
                        _img = _PILImg.open(img_upload).convert("RGB")
                        _img = _img.resize((400, 300), _PILImg.LANCZOS)
                        _buf = io.BytesIO()
                        _img.save(_buf, format="JPEG", quality=85, optimize=True)
                        _b64 = base64.b64encode(_buf.getvalue()).decode()
                        if "product_images" not in st.session_state.active_config:
                            st.session_state.active_config["product_images"] = {}
                        st.session_state.active_config["product_images"][selected_product] = _b64
                        st.success(f"✅ Image assigned to '{selected_product}' - download config.json below to make permanent.")

                with img_col2:
                    _assigned = st.session_state.active_config.get("product_images", {})
                    if _assigned:
                        st.markdown(f"**Currently assigned: {len(_assigned)} product image(s)**")
                        _img_cols = st.columns(min(len(_assigned), 4))
                        for _idx, (_pname, _pb64) in enumerate(_assigned.items()):
                            with _img_cols[_idx % 4]:
                                st.markdown(
                                    f'<div style="background:var(--surface-2);border-radius:8px;padding:0.4rem;'
                                    f'text-align:center;margin-bottom:0.4rem">'
                                    f'<img src="data:image/jpeg;base64,{_pb64}" '
                                    f'style="max-height:60px;max-width:100%;object-fit:contain;border-radius:4px"/>'
                                    f'<div style="font-size:0.65rem;color:var(--muted);margin-top:0.2rem;'
                                    f'word-break:break-word">{_pname}</div></div>',
                                    unsafe_allow_html=True
                                )
                                if st.button("🗑️", key=f"del_img_{_idx}", help=f"Remove image for {_pname}"):
                                    del st.session_state.active_config["product_images"][_pname]
                                    st.rerun()
                    else:
                        st.info("No product images assigned yet. Upload one on the left.")


            # ── TAB 3: Service Pricing ────────────────────────────────────────────
            with panel_tabs[2]:
                st.markdown("### 💳 Service Pricing")
                st.caption("Edit wholesale (buy) and customer (sell) prices for all monthly service items. Changes apply immediately to new deals.")

                # Show current deal discount impact
                _adm_disc = max(0.0, min(50.0, float(st.session_state.get("c_svc_disc", 0))))
                if _adm_disc > 0:
                    st.info(f"ℹ️ Consultant has applied a **{_adm_disc:.0f}% service discount** on this deal. "
                            f"Effective sell prices and margins shown below reflect this.")
                else:
                    st.caption("No service discount active — prices shown are list prices.")
                _adm_mult = 1.0 - _adm_disc / 100.0

                # ── Call Scope — Monthly Services ─────────────────────────────────
                st.markdown("#### 🔮 Call Scope — Monthly Services")
                st.caption("Per-user per-month charges. Buy = South Wales Comms wholesale cost. Sell = customer price.")
                cs_svc_cfg = st.session_state.active_config.get("call_scope_services", [
                    {"name": "AI Integration - Portal", "buy": 18.00,  "sell": 49.00},
                    {"name": "AI Integration - CRM",    "buy": 5.00,  "sell": 35.00},
                    {"name": "Manager Dashboard",        "buy": 5.00,  "sell": 59.00},
                    {"name": "Call Score",               "buy": 20.00, "sell": 45.00},
                    {"name": "AI Receptionist",          "buy": 25.00, "sell": 89.00},
                ])
                cs_svc_cols = st.columns(4)
                cs_svc_new = []
                for _ci, _cs in enumerate(cs_svc_cfg):
                    with cs_svc_cols[_ci % 4]:
                        st.markdown(f"**{_cs['name']}**")
                        _b = st.number_input(f"Buy £/mo", value=float(_cs["buy"]), step=0.50,
                                             key=f"adm_cs_buy_{_ci}", format="%.2f")
                        _s = st.number_input(f"Sell £/mo", value=float(_cs.get("sell", _cs["buy"]*1.45)), step=0.50,
                                             key=f"adm_cs_sell_{_ci}", format="%.2f")
                        _eff_s  = round(_s * _adm_mult, 2)
                        _margin = round((_eff_s - _b) / _eff_s * 100, 1) if _eff_s > 0 else 0
                        _disc_note = f" → £{_eff_s:.2f}/mo after discount" if _adm_disc > 0 else ""
                        st.caption(f"Margin: {_margin:.1f}%{_disc_note}")
                        cs_svc_new.append({"name": _cs["name"], "buy": _b, "sell": _s})
                if st.button("💾 Save Call Scope Service Pricing", key="adm_cs_svc_save"):
                    st.session_state.active_config["call_scope_services"] = cs_svc_new
                    st.success("Call Scope service pricing saved"); st.rerun()

                st.markdown("---")

                # ── Call Scope — Minutes (per-minute pricing, separate from My PA) ──
                st.markdown("#### ⏱️ Call Scope — Minutes")
                st.caption("Per-minute price for the Call Scope 500 / 1000 / 1500 minute bundles on the AI Integration modules. "
                           "Separate from the My PA bundles below.")
                _mc1, _mc2 = st.columns(2)
                with _mc1:
                    _cs_min_b = st.number_input("Buy £ per minute", value=float(cfg["constants"].get("cs_min_buy", 0.10)),
                                                step=0.01, min_value=0.0, format="%.3f", key="adm_cs_min_buy")
                with _mc2:
                    _cs_min_s = st.number_input("Sell £ per minute", value=float(cfg["constants"].get("cs_min_sell", 0.25)),
                                                step=0.01, min_value=0.0, format="%.3f", key="adm_cs_min_sell")
                _cs_min_margin = round((_cs_min_s - _cs_min_b) / _cs_min_s * 100, 1) if _cs_min_s > 0 else 0
                st.caption("Bundles: " + " · ".join(f"{m} mins = £{m * _cs_min_s:,.2f}/mo sell (cost £{m * _cs_min_b:,.2f})"
                                                     for m in (500, 1000, 1500)) + f"  ·  margin {_cs_min_margin:.1f}%")
                if st.button("💾 Save Call Scope Minutes Pricing", key="adm_cs_min_save"):
                    st.session_state.active_config["constants"]["cs_min_buy"]  = _cs_min_b
                    st.session_state.active_config["constants"]["cs_min_sell"] = _cs_min_s
                    st.success("Call Scope minutes pricing saved"); st.rerun()

                with st.expander("📜 Call Scope paperwork - branding & Terms and Conditions", expanded=False):
                    st.caption("Used on the separate Call Scope pack (Agreement, Service Order, Price Schedule, Terms & Conditions and Direct Debit mandate). Call Scope Ltd is its own company - its name, email and website are set here - "
                               "no code change needed. Leave a box empty to use the default.")
                    _cbr = st.session_state.active_config.get("callscope_brand", {}) or {}
                    _b1, _b2 = st.columns(2)
                    with _b1:
                        _n_trading = st.text_input("Trading name", value=_cbr.get("trading", "Call Scope"), key="csb_trading")
                        _n_legal   = st.text_input("Legal company name", value=_cbr.get("legal", ""), key="csb_legal",
                                                   placeholder=f"Default: {_CO_LEGAL}")
                        _n_addr    = st.text_input("Registered address", value=_cbr.get("address", ""), key="csb_addr")
                        _n_web     = st.text_input("Website", value=_cbr.get("website", "callscope.co.uk"), key="csb_web")
                    with _b2:
                        _n_email   = st.text_input("Contact email", value=_cbr.get("email", ""), key="csb_email")
                        _n_phone   = st.text_input("Contact phone", value=_cbr.get("phone", ""), key="csb_phone")
                        _n_acc     = st.text_input("Brand colour (hex)", value=_cbr.get("accent", "#7870E8"), key="csb_acc")
                        _n_byline  = st.text_input("Byline", value=_cbr.get("byline", "by South Wales Comms"), key="csb_byline",
                                                   help="Shown under the name. Clear it once Call Scope stands on its own.")
                    _logo_up = st.file_uploader("Call Scope logo (PNG or JPG, white or transparent background)", type=["png", "jpg", "jpeg"], key="csb_logo")
                    if st.button("💾 Save Call Scope branding", key="csb_save"):
                        _nb = {"trading": _n_trading.strip() or "Call Scope", "legal": _n_legal.strip(), "address": _n_addr.strip(),
                               "website": _n_web.strip(), "email": _n_email.strip(), "phone": _n_phone.strip(),
                               "accent": _n_acc.strip() or "#7870E8", "byline": _n_byline.strip(),
                               "logo_b64": _cbr.get("logo_b64", "")}
                        if _logo_up is not None:
                            _nb["logo_b64"] = base64.b64encode(_logo_up.getvalue()).decode()
                        st.session_state.active_config["callscope_brand"] = _nb
                        st.success("Call Scope branding saved"); st.rerun()
                    st.markdown("**Terms & Conditions**")
                    st.caption("One clause per block: start each heading with ## and leave a blank line between paragraphs. "
                               "You can use {BRAND}, {PROVIDER}, {EMAIL} and {TERM} - they are filled in automatically. "
                               "This is a working draft built from your existing terms and common SaaS terms - have a solicitor review it before it is relied on.")
                    _terms_now = st.session_state.active_config.get("callscope_terms_text") or _CS_TERMS_DEFAULT
                    _terms_new = st.text_area("Call Scope Terms & Conditions", value=_terms_now, height=520, key="csb_terms",
                                              label_visibility="collapsed")
                    _tb1, _tb2 = st.columns(2)
                    with _tb1:
                        if st.button("💾 Save Terms & Conditions", key="csb_terms_save", type="primary"):
                            st.session_state.active_config["callscope_terms_text"] = _terms_new
                            st.success("Terms saved"); st.rerun()
                    with _tb2:
                        if st.button("↩️ Reset to the default draft", key="csb_terms_reset"):
                            st.session_state.active_config.pop("callscope_terms_text", None)
                            st.success("Reset to the default"); st.rerun()

                with st.expander("❄️ SteadyTemp paperwork - company details & Terms and Conditions", expanded=False):
                    st.caption("Used on the separate SteadyTemp pack (Proposal, Order Form, On-Site Support Agreement, Direct Debit set-up and Terms & Conditions). Leave a box empty to use the default.")
                    _sco = st_company()
                    _s1, _s2 = st.columns(2)
                    with _s1:
                        _v_trading = st.text_input("Trading name", value=_sco["trading"], key="stb_trading")
                        _v_legal = st.text_input("Legal company name", value=_sco["legal"], key="stb_legal")
                        _v_reg = st.text_input("Company number line", value=_sco["reg"], key="stb_reg")
                        _v_vat = st.text_input("VAT line", value=_sco["vat"], key="stb_vat")
                        _v_ro = st.text_input("Registered office", value=_sco["reg_office"], key="stb_ro")
                    with _s2:
                        _v_addr = st.text_input("Trading address (comma separated)", value=", ".join(_sco["addr"]), key="stb_addr")
                        _v_email = st.text_input("Email", value=_sco["email"], key="stb_email")
                        _v_phone = st.text_input("Phone", value=_sco["phone"], key="stb_phone")
                        _v_web = st.text_input("Website", value=_sco["web"], key="stb_web")
                        _v_fund = st.text_input("Finance partner wording", value=_sco["funder"], key="stb_fund")
                    if st.button("💾 Save SteadyTemp company details", key="stb_save"):
                        st.session_state.active_config["steadytemp_company"] = {
                            "trading": _v_trading.strip(), "legal": _v_legal.strip(), "reg": _v_reg.strip(), "vat": _v_vat.strip(),
                            "reg_office": _v_ro.strip(), "addr": [x.strip() for x in _v_addr.split(",") if x.strip()],
                            "email": _v_email.strip(), "phone": _v_phone.strip(), "web": _v_web.strip(), "funder": _v_fund.strip()}
                        st.success("SteadyTemp company details saved"); st.rerun()
                    st.markdown("**Terms & Conditions**")
                    st.caption("Start each clause heading with ## and put its text underneath.")
                    _st_default = "\n\n".join(f"## {a}\n{b}" for a, b in ST_TERMS_DEFAULT)
                    _st_now = st.session_state.active_config.get("steadytemp_terms_text") or _st_default
                    _st_new = st.text_area("SteadyTemp Terms & Conditions", value=_st_now, height=420, key="stb_terms", label_visibility="collapsed")
                    _t1, _t2 = st.columns(2)
                    with _t1:
                        if st.button("💾 Save SteadyTemp Terms", key="stb_terms_save", type="primary"):
                            st.session_state.active_config["steadytemp_terms_text"] = _st_new
                            st.success("Terms saved"); st.rerun()
                    with _t2:
                        if st.button("↩️ Reset SteadyTemp Terms", key="stb_terms_reset"):
                            st.session_state.active_config.pop("steadytemp_terms_text", None)
                            st.success("Reset to the default"); st.rerun()

                st.markdown("---")

                # ── Call Scope — My PA Minute Bundles ─────────────────────────────
                st.markdown("#### 📞 Call Answer - My PA Bundles")
                st.caption("Flat monthly fee per bundle. These are service charges (not lease).")
                _mypa_defaults = [
                    {"name": "My PA 500 mins", "buy": 100.0, "sell": 149.0},
                    {"name": "My PA 1000 mins","buy": 140.0, "sell": 199.0},
                    {"name": "My PA 2000 mins","buy": 180.0, "sell": 249.0},
                ]
                _mypa_cfg = st.session_state.active_config.get("mypa_bundles", _mypa_defaults)
                mypa_cols = st.columns(3)
                mypa_new = []
                for _mi, _mp in enumerate(_mypa_cfg):
                    with mypa_cols[_mi]:
                        st.markdown(f"**{_mp['name']}**")
                        _mb = st.number_input("Buy £/mo", value=float(_mp["buy"]), step=5.0,
                                              key=f"adm_mypa_buy_{_mi}", format="%.2f")
                        _ms = st.number_input("Sell £/mo", value=float(_mp.get("sell", _mp["buy"]*1.5)), step=5.0,
                                              key=f"adm_mypa_sell_{_mi}", format="%.2f")
                        _eff_ms = round(_ms * _adm_mult, 2)
                        _mm = round((_eff_ms - _mb) / _eff_ms * 100, 1) if _eff_ms > 0 else 0
                        _mypa_note = f" → £{_eff_ms:.2f}/mo" if _adm_disc > 0 else ""
                        st.caption(f"Margin: {_mm:.1f}%{_mypa_note}")
                        mypa_new.append({"name": _mp["name"], "buy": _mb, "sell": _ms})
                if st.button("💾 Save My PA Bundle Pricing", key="adm_mypa_save"):
                    st.session_state.active_config["mypa_bundles"] = mypa_new
                    st.success("My PA pricing saved"); st.rerun()

                st.markdown("---")

                # ── Call Scope — Lease Add-ons ─────────────────────────────────────
                st.markdown("#### 🏷️ Call Scope — Lease Add-ons")
                st.caption("One-off items added to the hardware lease (Website Widget, Platform Setup).")
                _cs_lease_names = ("Website Widget", "Call Scope Platform Setup", "Call Scope AI Setup (one-off)", "Call Scope AI Receptionist Setup (one-off)")
                _cs_lease_items = [i for i in cfg.get("other_hardware", [])
                                    if i.get("name","") in _cs_lease_names]
                if _cs_lease_items:
                    cl_cols = st.columns(len(_cs_lease_items))
                    cl_new_vals = {}
                    for _li, _li_item in enumerate(_cs_lease_items):
                        with cl_cols[_li]:
                            st.markdown(f"**{_li_item['name']}**")
                            _lb = st.number_input("Buy £", value=float(_li_item["buy"]), step=5.0,
                                                  key=f"adm_cl_buy_{_li}", format="%.2f")
                            _ls = st.number_input("Sell £", value=float(_li_item.get("sell", _li_item["buy"]*1.5)), step=5.0,
                                                  key=f"adm_cl_sell_{_li}", format="%.2f")
                            _lm = round((_ls - _lb) / _ls * 100, 1) if _ls > 0 else 0
                            st.caption(f"Margin: {_lm:.1f}%")
                            cl_new_vals[_li_item["name"]] = {"buy": _lb, "sell": _ls}
                    if st.button("💾 Save Lease Add-on Pricing", key="adm_cl_save"):
                        for item in st.session_state.active_config["other_hardware"]:
                            if item.get("name") in cl_new_vals:
                                item.update(cl_new_vals[item["name"]])
                        st.success("Lease add-on pricing saved"); st.rerun()

                st.markdown("---")

                # ── System Security ────────────────────────────────────────────────
                st.markdown("#### 🛡️ System Security Tiers")
                st.caption("Per-instance per-month. Buy = South Wales Comms cost. Sell = customer price.")
                _sec_defaults = [
                    {"name": "Bronze Security", "buy": 7.00,  "sell": 10.00},
                    {"name": "Silver Security", "buy": 10.00, "sell": 15.00},
                    {"name": "Gold Security",   "buy": 14.00, "sell": 20.00},
                ]
                _sec_cfg = st.session_state.active_config.get("system_security", _sec_defaults)
                sec_adm_cols = st.columns(3)
                sec_new = []
                for _si, _sc in enumerate(_sec_cfg):
                    with sec_adm_cols[_si]:
                        st.markdown(f"**{_sc['name']}**")
                        _sb = st.number_input("Buy £/mo", value=float(_sc["buy"]), step=0.50,
                                              key=f"adm_sec_buy_{_si}", format="%.2f")
                        _ss = st.number_input("Sell £/mo", value=float(_sc.get("sell", _sc["buy"]*1.43)), step=0.50,
                                              key=f"adm_sec_sell_{_si}", format="%.2f")
                        _eff_ss = round(_ss * _adm_mult, 2)
                        _sm = round((_eff_ss - _sb) / _eff_ss * 100, 1) if _eff_ss > 0 else 0
                        _sec_note = f" → £{_eff_ss:.2f}/mo" if _adm_disc > 0 else ""
                        st.caption(f"Margin: {_sm:.1f}%{_sec_note}")
                        sec_new.append({"name": _sc["name"], "buy": _sb, "sell": _ss})
                if st.button("💾 Save Security Tier Pricing", key="adm_sec_save"):
                    st.session_state.active_config["system_security"] = sec_new
                    st.success("Security tier pricing saved"); st.rerun()

                st.markdown("---")

                # ── IT Services ────────────────────────────────────────────────────
                st.markdown("#### 💻 IT Services")
                st.caption("Per-user per-month. Buy = wholesale cost. Sell = customer price (explicit sell overrides IT uplift %).")
                _it_svc_all = []
                for _cat, _pkgs in IT_SERVICES.items():
                    for _pname, _pinfo in _pkgs.items():
                        _it_svc_all.append({"category": _cat, "name": _pname,
                                            "buy": _pinfo.get("cost", 0),
                                            "sell": round(_pinfo.get("cost", 0) * 1.2, 2)})
                if _it_svc_all:
                    it_df = pd.DataFrame(_it_svc_all)
                    edited_it = st.data_editor(it_df, num_rows="dynamic", use_container_width=True,
                        key="adm_it_svc",
                        column_config={
                            "category": st.column_config.TextColumn("Category"),
                            "name":     st.column_config.TextColumn("Service"),
                            "buy":      st.column_config.NumberColumn("Buy £/user/mo", format="%.2f"),
                            "sell":     st.column_config.NumberColumn("Sell £/user/mo", format="%.2f"),
                        })
                    st.caption("Note: updating IT pricing here updates the live catalogue for the current session.")
                    if st.button("💾 Apply IT Services Pricing", key="adm_it_save"):
                        # Rebuild IT_SERVICES from edited data
                        for row in edited_it.to_dict("records"):
                            cat, name, buy, sell = row["category"], row["name"], row["buy"], row["sell"]
                            if cat in IT_SERVICES and name in IT_SERVICES[cat]:
                                IT_SERVICES[cat][name]["cost"] = buy
                                IT_SERVICES[cat][name]["sell"] = sell
                            else:
                                if cat not in IT_SERVICES:
                                    IT_SERVICES[cat] = {}
                                IT_SERVICES[cat][name] = {"cost": buy, "sell": sell}
                        # Persist to active_config so it survives rerun
                        st.session_state.active_config["it_services"] = IT_SERVICES
                        st.success("IT Services pricing updated for this session"); st.rerun()

            # ── TAB 3: Broadband & Lease Rates ────────────────────────────────────

            with panel_tabs[3]:
                # ── Lease rates: drive rental, lease value, max termination, profit, units, finance status ──
                st.markdown("**Lease Rates** - per £1,000 per month. Applying re-prices the current deal straight away.")
                import time as _lr_time
                if _lr_time.time() - float(st.session_state.get("_lr_applied_at", 0)) < 8:
                    st.success("Lease rates updated - the deal has been re-priced with the new rates.")
                _lr_rows = sorted(
                    [{"months": int(_i["months"]), "label": _i.get("label", f"{_i['months']} months"),
                      "rate": float(_i["rate"]), "true_rate": float(_i.get("true_rate", round(_i["rate"] * 0.8, 2)))}
                     for _i in cfg["lease_rates"]], key=lambda _r: _r["months"])
                edited_lr = st.data_editor(
                    pd.DataFrame(_lr_rows), num_rows="fixed", use_container_width=True, hide_index=True,
                    key="de_lease_rates", disabled=["months"],
                    column_config={
                        "months":    st.column_config.NumberColumn("Term (months)", format="%d"),
                        "label":     st.column_config.TextColumn("Label"),
                        "rate":      st.column_config.NumberColumn("Sales rate", format="%.2f", min_value=0.01,
                                         help="Customer rental per £1,000 per month"),
                        "true_rate": st.column_config.NumberColumn("Funder rate", format="%.2f", min_value=0.01,
                                         help="What the funder pays: lease value = rental ÷ funder rate × 1,000"),
                    })
                _lr_bad = [int(_r["months"]) for _r in edited_lr.to_dict("records")
                           if float(_r["true_rate"] or 0) >= float(_r["rate"] or 0)]
                if _lr_bad:
                    st.warning("Funder rate is at or above the sales rate for "
                               + ", ".join(f"{_m} months" for _m in _lr_bad) + " - those terms make no lease margin.")
                if not any("true_rate" in _i for _i in cfg["lease_rates"]):
                    st.caption("Funder rates are currently estimated at 80% of the sales rate - enter your real funder rates and apply.")
                st.caption(f"This deal ({LEASE_TERM_LABELS.get(lease_term, '')}): rental £{_desired_rental:,.2f}/mo · "
                           f"lease value £{lease_value_ex_buyout:,.0f} · {commission_units:.2f} units")
                if st.button("✅ Apply Lease Rates", type="primary", key="apply_lease_rates", disabled=bool(_lr_bad)):
                    st.session_state.active_config["lease_rates"] = [
                        {"months": int(_r["months"]), "label": str(_r["label"]),
                         "rate": round(float(_r["rate"]), 2), "true_rate": round(float(_r["true_rate"]), 2)}
                        for _r in edited_lr.to_dict("records")]
                    import time as _lr_time2
                    st.session_state["_lr_applied_at"] = _lr_time2.time()
                    st.rerun()
                st.caption("To keep new rates permanently, use 💾 Save Configuration below and commit config.json to GitHub.")
                st.markdown("---")
                st.markdown("**Broadband Packages** - edit wholesale costs and install charges")
                bb_df = pd.DataFrame(cfg["broadband"])
                edited_bb = st.data_editor(bb_df, num_rows="dynamic", use_container_width=True, key="de_bb",
                    column_config={
                        "provider": st.column_config.TextColumn("Provider"),
                        "package":  st.column_config.TextColumn("Package"),
                        "cost":     st.column_config.NumberColumn("Wholesale Cost £", format="%.2f"),
                        "install":  st.column_config.NumberColumn("Install Charge £", format="%.2f"),
                    })

                if st.button("✅ Apply Broadband Changes", type="primary", key="apply_bb"):
                    st.session_state.active_config["broadband"] = edited_bb.dropna(subset=["provider","package"]).to_dict("records")
                    st.success("Broadband updated!")
                    st.rerun()

            # ── TAB 4: Costs & Fees ───────────────────────────────────────────────
            with panel_tabs[4]:
                st.markdown("**Fixed Deal Costs** - these feed directly into the lease capital calculation")
                c = cfg["constants"]
                cc1, cc2 = st.columns(2)
                with cc1:
                    new_vc_cost    = st.number_input("Voice Channel Cost £/seat/mo (wholesale)", value=float(c.get("vc_cost_per_seat", 2.95)), step=0.10)
                    new_vc_sell    = round(new_vc_cost * 1.2, 2)
                    st.caption(f"Customer price per seat: £{new_vc_sell:,.2f}/mo (cost + 20%)")
                    new_wallboard  = float(c.get("wallboard_sell", 6.00))
                    new_install_day = st.number_input("Engineer Installation £ per day", value=float(c.get("install_engineer", 450.00)), step=25.0,
                                                      min_value=0.0, help="Charged once per installation day chosen by the consultant.")
                    new_uplift     = 20.0
                with cc2:
                    new_hw_uplift_up = 20
                    new_hw_uplift  = 20
                    st.caption("Hardware and services are always cost + 20%.")
                    new_price_rise = st.number_input("Annual price increase (%)", min_value=0.0, max_value=25.0, step=0.5,
                        value=float(c.get("price_rise_pct", 5.0)), key="adm_price_rise",
                        help="Applied to the monthly service charges and shown to the customer as a £ amount on the Annual Price Review page and the Contract Information Sheet.")
                    new_commission = st.slider("Commission per Unit (£)",
                        min_value=500, max_value=5000, value=min(5000, max(500, int(c.get("commission_per_unit", 1000)))), step=50,
                        help="£ paid per unit of gross profit. 1 unit = £1,000 profit. Internal only - not visible to consultants.")

                if st.button("✅ Apply Cost Changes", type="primary", key="apply_costs"):
                    st.session_state.active_config["constants"].update({
                        "vc_cost_per_seat":  new_vc_cost,
                        "vc_sell_per_seat":  new_vc_sell,
                        "wallboard_sell":   new_wallboard,
                        "install_engineer": new_install_day,
                        "default_service_uplift_pct": new_uplift,
                        "hw_uplift_upfront_pct": new_hw_uplift_up,
                        "hw_uplift_pct": new_hw_uplift,
                        "commission_per_unit": new_commission,
                        "price_rise_pct": new_price_rise,
                    })
                    st.success("Costs updated!"); st.rerun()

            # ── TAB 5: Branding ───────────────────────────────────────────────────
            with panel_tabs[5]:
                st.markdown("**Company Branding** - updates login screen, all PDF documents and customer view instantly")
                br = cfg.get("branding", {})
                bc1, bc2 = st.columns(2)
                with bc1:
                    new_co_name   = st.text_input("Company Name",          value=br.get("company_name",    "South Wales Comms"), key="br_name")
                    new_co_legal  = st.text_input("Legal Entity Name",     value=br.get("company_legal",   "South Wales Comms Ltd"), key="br_legal",
                                                  help="Used in legal clauses in PDF documents")
                    new_co_tag    = st.text_input("App Tagline",           value=br.get("company_tagline", "South Wales Comms Pricing Tool"), key="br_tag")
                with bc2:
                    new_co_cap    = st.text_input("Login Page Caption",    value=br.get("login_caption",   f"Authorised {br.get('company_name','South Wales Comms')} users only."), key="br_cap")
                    new_co_pkg    = st.text_input("Customer Package Label",value=br.get("customer_pkg_label", "Your South Wales Comms Package"), key="br_pkg",
                                                  help="Shown on the Customer View tab header")
                    new_co_file   = st.text_input("PDF Filename Prefix",   value=br.get("proposal_filename_prefix", "SWComms_Proposal"), key="br_file",
                                                  help="e.g. 'Acme_Proposal' → Acme_Proposal_CompanyName_2026-01-01.pdf")
                    new_co_foot   = st.text_input("PDF Footer Text",       value=br.get("pdf_footer", "South Wales Comms | All figures exclude VAT | This document is confidential"), key="br_foot")

                st.info("💡 After applying, download **config.json** below and commit to GitHub to make permanent.")

                if st.button("✅ Apply Branding", type="primary", key="apply_branding"):
                    st.session_state.active_config["branding"] = {
                        "company_name":    new_co_name,
                        "company_legal":   new_co_legal,
                        "company_tagline": new_co_tag,
                        "login_caption":   new_co_cap,
                        "customer_pkg_label": new_co_pkg,
                        "proposal_filename_prefix": new_co_file,
                        "pdf_footer":      new_co_foot,
                    }
                    st.success(f"✅ Branding updated to '{new_co_name}' - takes effect immediately!")
                    st.rerun()

            # ── TAB 6: Email Settings ────────────────────────────────────────────
            with panel_tabs[6]:
                st.markdown("**Email / SMTP Configuration** - used to send signed proposals to customers")
                em = cfg.get("email", {})
                ecol1, ecol2 = st.columns(2)
                with ecol1:
                    new_smtp_host  = st.text_input("SMTP Host",     value=em.get("smtp_host",  "smtp.gmail.com"),  help="Gmail: smtp.gmail.com  |  Outlook: smtp.office365.com")
                    new_smtp_port  = st.number_input("SMTP Port",   value=int(em.get("smtp_port",  587)), step=1, help="587 (TLS) or 465 (SSL)")
                    new_from_name  = st.text_input("From Name",     value=em.get("from_name",  "South Wales Comms"))
                with ecol2:
                    new_email_user = st.text_input("Email Address / Username", value=em.get("username", ""))
                    new_email_pass = st.text_input("App Password",  value=em.get("password",  ""), type="password",
                                                   help="For Gmail use an App Password (not your regular password). Settings → Security → 2-Step → App Passwords")
                    new_reply_to   = st.text_input("Reply-To Address", value=em.get("reply_to", ""), help="Leave blank to use sender address")

                st.info("💡 Gmail users: enable 2-Step Verification then create an **App Password** at myaccount.google.com/apppasswords")
                if st.button("✅ Save Email Settings", type="primary", key="save_email"):
                    st.session_state.active_config["email"] = {
                        "smtp_host":  new_smtp_host,
                        "smtp_port":  int(new_smtp_port),
                        "username":   new_email_user,
                        "password":   new_email_pass,
                        "from_name":  new_from_name,
                        "reply_to":   new_reply_to,
                    }
                    st.success("✅ Email settings saved! Download config.json below to make permanent.")

            # ── TAB 7: Product Images ─────────────────────────────────────────────
            with panel_tabs[7]:
                st.markdown("**Upload product images** - filenames are matched to product names automatically")
                st.caption("Tip: name files like `fanvil_v66_pro.jpg` or `v66pro.png` - the app fuzzy-matches the name")
                uploaded_files = st.file_uploader(
                    "Drag & drop product images here",
                    type=["jpg", "jpeg", "png", "webp"],
                    accept_multiple_files=True,
                    key="img_uploader_admin"
                )
                if uploaded_files:
                    for uf in uploaded_files:
                        raw = uf.name.rsplit(".", 1)[0].lower()
                        norm = "".join(c for c in raw if c.isalnum())
                        st.session_state.uploaded_images[norm] = uf.read()
                if st.session_state.uploaded_images:
                    st.success(f"✅ {len(st.session_state.uploaded_images)} image(s) loaded for this session")
                    img_names = list(st.session_state.uploaded_images.keys())
                    st.caption("Loaded: " + ", ".join(img_names))
                    if st.button("🗑️ Clear all images", key="clear_imgs"):
                        st.session_state.uploaded_images = {}
                        st.rerun()

            # ── TAB 6: Security ───────────────────────────────────────────────────
            with panel_tabs[9]:
                _zoho_setup_ui("_zt")

            with panel_tabs[8]:
                st.markdown("**Change Admin Password**")
                pw1 = st.text_input("New password", type="password", key="new_pw1")
                pw2 = st.text_input("Confirm new password", type="password", key="new_pw2")
                if st.button("Update Password", key="update_pw"):
                    if pw1 and pw1 == pw2:
                        st.session_state.active_config["meta"]["password_hash"] = hashlib.sha256(pw1.encode()).hexdigest()
                        st.success("Password updated! Download config below to make it permanent.")
                    elif pw1 != pw2:
                        st.error("Passwords don't match")
                    else:
                        st.warning("Enter a new password first")

            # ── SAVE CONFIG ───────────────────────────────────────────────────────
            st.divider()
            st.markdown("**💾 Save Configuration**")
            _n_imgs = len(st.session_state.get("uploaded_images", {}))
            _img_note = f" + {_n_imgs} product image(s)" if _n_imgs else " (upload images in the Images tab to include them)"
            st.caption(f"Saves all pricing, branding{_img_note}. Commit to GitHub to make permanent.")
            config_json = _cfg_to_json(st.session_state.active_config)
            st.download_button(
                "📥 Download config.json",
                data=config_json,
                file_name="config.json",
                mime="application/json",
                use_container_width=True,
                key="dl_config"
            )

    # ─── KPI METRICS ROW ─────────────────────────────────────────────────────────

def pat_class(v):
    if v >= 1000: return "green"
    if v >= 500:  return "amber"
    return "red"

# ── 3 customer-safe metrics always visible ─────────────────────────────────
# Admin-only switch to hide the whole Deal Dashboard (customer-safe cards and internal financials)
if st.session_state.admin_unlocked:
    st.toggle("📊 Show Deal Dashboard", value=True, key="show_deal_dashboard")
_show_dash = st.session_state.get("show_deal_dashboard", True) if st.session_state.admin_unlocked else True
if _show_dash:
    st.markdown('<div class="section-header">📊 Deal Dashboard</div>', unsafe_allow_html=True)
    if n_packs() >= 2:
        st.markdown("#### 📞 Telephony")

    if is_spread:
        k1, k2 = st.columns(2)
        with k1:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">Total Monthly</div>
              <div class="metric-value">£{total_mo:.2f}</div>
              <div class="metric-sub">Services + HW spread excl. VAT</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">Monthly Services</div>
              <div class="metric-value">£{svc["total_sell"]:.2f}</div>
              <div class="metric-sub">BB + Licences + Mobiles</div>
            </div>""", unsafe_allow_html=True)
    else:
        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">Total Monthly</div>
              <div class="metric-value">£{total_mo:.2f}</div>
              <div class="metric-sub">Services excl. VAT</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">Upfront Hardware</div>
              <div class="metric-value">£{upfront:.0f}</div>
              <div class="metric-sub">One-off payment excl. VAT</div>
            </div>""", unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">Monthly Services</div>
              <div class="metric-value">£{svc["total_sell"]:.2f}</div>
              <div class="metric-sub">BB + Licences + Mobiles</div>
            </div>""", unsafe_allow_html=True)

    # ── Internal financials
    # ── Internal financials - collapsed by default, hidden from customer ────────
    pc = pat_class(pat)
    pat_warn = ""
    if pat < 500:
        pat_warn = "⚠️ Low PAT - consider manager review"

    if st.session_state.admin_unlocked:
        # Row 1 - 4 original cards
        _gp_sub = (f"Rental £{_desired_rental:.2f}/mo (calculated £{pl_data['rental']:.2f})"
                   if abs(_desired_rental - pl_data["rental"]) > 0.01 else f"Rental: £{pl_data['rental']:.2f}/mo")
        _DM_NAME = "Lease" if is_lease else ("System Rental" if is_inhouse else "Hardware")       # what the profit card is called for this deal type
        _DM_PROFIT = "Lease Profit" if is_lease else ("System Profit" if is_inhouse else "Hardware Profit")
        if is_inhouse:
            _gp_sub = f"£{hw_monthly_spread:,.2f}/mo × {lease_term} months, less costs £{pl_data['cos_full']:,.0f} (no funder)"
        elif not is_lease:
            _gp_sub = f"Upfront £{upfront:,.0f} less costs £{pl_data['cos_full']:,.0f} (no funder)"
        fi1, fi2, fi3, fi4 = st.columns(4)
        with fi1:
            st.markdown(f'''<div class="metric-card">
              <div class="metric-label">Gross Profit ({_DM_NAME})</div>
              <div class="metric-value {pc}">£{_adjusted_gp:.0f}</div>
              <div class="metric-sub">{_gp_sub}</div>
            </div>''', unsafe_allow_html=True)
        with fi2:
            st.markdown(f'''<div class="metric-card">
              <div class="metric-label">HW Buy → Sell</div>
              <div class="metric-value" style="font-size:1.3rem">£{hw_buy:.0f} → £{hw_sell:.0f}</div>
              <div class="metric-sub">Sell: £{hw_sell:.0f} (pricebook rates)</div>
            </div>''', unsafe_allow_html=True)
        with fi3:
            st.markdown(f'''<div class="metric-card">
              <div class="metric-label">Sub Total (SRRP basis)</div>
              <div class="metric-value" style="font-size:1.3rem">£{pl_data["sub_total"]:.0f}</div>
              <div class="metric-sub">SRRP £{pl_data["hw_srrp"]:.0f} + COS £{pl_data["cos_full"]:.0f}</div>
            </div>''', unsafe_allow_html=True)
        with fi4:
            st.markdown(f'''<div class="metric-card">
              <div class="metric-label">Commission ({commission_units:.2f} units)</div>
              <div class="metric-value" style="font-size:1.3rem;color:var(--accent)">£{commission:.0f}</div>
              <div class="metric-sub">£{commission_per_unit:.0f}/unit · £{commission_unit_size:.0f} GP = 1 unit</div>
            </div>''', unsafe_allow_html=True)
        st.markdown("---")
        # Row 2 - Profit breakdown cards
        _svc_cost_pm    = (svc["bb_cost"] + total_voice_channels * C.get("vc_cost_per_seat",2.95) + sw_cost_total
                           + svc.get("mobile_cost",0.0) + _cs_svc_cost + _sec_svc_cost + _it_svc_cost)
        _svc_sell_pm    = svc["total_sell"]
        _svc_margin_pm  = _svc_sell_pm - _svc_cost_pm
        _svc_profit_term = round(_svc_margin_pm * lease_term, 2)
        _total_gp        = round(_adjusted_gp + _svc_profit_term + printer_lease_profit, 2)
        _lp_is_target    = _eff_target > 0 and abs(_desired_rental - base_rental) > 0.01
        # Lease value + maximum termination
        if is_lease:
            lv1, lv2 = st.columns(2)
            with lv1:
                st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--accent)">
                  <div class="metric-label">Lease Value</div>
                  <div class="metric-value">{"£" + format(lease_value, ",.0f") if is_lease else "n/a"}</div>
                  <div class="metric-sub">{("What the funder pays for the £" + format(_lv_rental, ",.2f") + "/mo rental in this deal (÷ " + format(true_rate, ".2f") + " rate × 1,000)" if _target_active else "What the funder pays for £" + format(_lv_rental, ",.2f") + "/mo value rental (÷ " + format(true_rate, ".2f") + " rate × 1,000), before any buyout") if is_lease else ("In-house system rental - no finance lease" if is_inhouse else "Upfront purchase - no lease")}</div>{('<div class="metric-sub" style="margin-top:.35rem;color:var(--accent-2)!important">This deal: £' + format(_desired_rental, ",.2f") + "/mo incl. buyout, funder pays £" + format(_desired_rental / true_rate * 1000.0 if true_rate > 0 else 0, ",.0f") + "</div>") if (is_spread and not _target_active and abs(_desired_rental - _lv_rental) > 0.01) else ""}{('<div class="metric-sub" style="margin-top:.35rem">Equipment only (before buyout cover): £' + format(_lv_equipment_only / true_rate * 1000.0 if true_rate > 0 else 0, ",.0f") + " funder pays</div>") if (is_lease and _target_active and abs(_lv_rental - _lv_equipment_only) > 0.01) else ""}
                </div>''', unsafe_allow_html=True)
            with lv2:
                _over = termination_over
                st.markdown(f'''<div class="metric-card" style="border-left:4px solid {"var(--warn)" if _over else "var(--good)"}">
                  <div class="metric-label">Max Termination ({MAX_TERMINATION_PCT:.0f}% of lease value)</div>
                  <div class="metric-value" style="color:{"var(--warn)" if _over else "var(--good)"}!important">{"£" + format(max_termination, ",.0f") if is_lease else "n/a"}</div>
                  <div class="metric-sub">{("Buyout £" + format(termination_cost, ",.0f") + (" - " + format(termination_over_pct, ".0f") + "% (£" + format(termination_cost - max_termination, ",.0f") + ") over the maximum" if _over else " - within the maximum")) if (is_spread and termination_cost > 0) else ("No buyout. At the maximum, lease profit would be £" + format(_gp_before_buyout - max_termination, ",.0f") if is_spread else "No buyout on this deal")}</div>{("<div class='metric-sub' style='color:var(--warn)!important;margin-top:.3rem'>Safe buyout at this rental: £" + format(safe_buyout, ",.0f") + "</div>") if safe_buyout_limited else ""}{("<div class='metric-sub' style='color:var(--warn)!important;margin-top:.3rem'>Target rental £" + format(rental_short_of_buyout, ",.2f") + "/mo short of covering the buyout</div>") if rental_short_of_buyout > 0 else ""}
                </div>''', unsafe_allow_html=True)
        else:
            lv1, lv2 = st.columns(2)
            _income = round(hw_monthly_spread * lease_term, 2) if is_inhouse else round(float(upfront), 2)
            with lv1:
                st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--accent)">
                  <div class="metric-label">{"System Income (over the term)" if is_inhouse else "Upfront Income"}</div>
                  <div class="metric-value">£{_income:,.0f}</div>
                  <div class="metric-sub">{("£" + format(hw_monthly_spread, ",.2f") + "/mo × " + str(lease_term) + " months paid to us - in-house, no funder") if is_inhouse else "One-off hardware, install and set-up charge paid by the customer - no funder"}</div>
                </div>''', unsafe_allow_html=True)
            with lv2:
                st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--border-strong)">
                  <div class="metric-label">Cost of the Deal</div>
                  <div class="metric-value">£{pl_data["cos_full"]:,.0f}</div>
                  <div class="metric-sub">Hardware, install and other costs we pay up front{(" - recovered through the monthly system rental" if is_inhouse else "")}</div>
                </div>''', unsafe_allow_html=True)
        if printer_rows:
            pr1, pr2 = st.columns(2)
            with pr1:
                st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--accent)">
                  <div class="metric-label">Printer Lease Profit</div>
                  <div class="metric-value">£{printer_lease_profit:,.0f}</div>
                  <div class="metric-sub">Funder pays £{printer_funder:,.0f} for £{printer_monthly:.2f}/mo over {printer_term} months, less costs £{printer_cost_total:,.0f} · {printer_lease_profit / 4000:.2f} units</div>
                </div>''', unsafe_allow_html=True)
            with pr2:
                st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--accent)">
                  <div class="metric-label">Print Margin (estimated)</div>
                  <div class="metric-value">£{printer_print_margin_mo:,.2f}/mo</div>
                  <div class="metric-sub">Device uplift {PRN_UPLIFT:.0f}% · print uplift {PRN_CPC_UPLIFT:.0f}%</div>
                </div>''', unsafe_allow_html=True)
        # Finance viability - admin only (consultants no longer see this)
        if fin_band != "none":
            _fb = {"good":    ("Likely to pass",     "var(--good)"),
                   "stretch": ("Possible (stretch)", "var(--warn)"),
                   "unlikely":("Unlikely to pass",   "var(--bad, #F87171)")}[fin_band]
            st.markdown(f'''<div class="metric-card" style="border-left:4px solid {_fb[1]}">
              <div class="metric-label">Finance Viability</div>
              <div class="metric-value" style="color:{_fb[1]}">{_fb[0]}</div>
              <div class="metric-sub">Funded £{fin_funded:,.0f} across {fin_handsets} handset(s) = £{fin_per_handset:,.0f} per handset
              (comfortable up to £{FIN_OK_PER_HANDSET:,.0f}, stretch up to £{FIN_MAX_PER_HANDSET:,.0f})</div>
            </div>''', unsafe_allow_html=True)
        if is_lease:
            LP_SUB = ("At £" + format(_desired_rental, ",.2f") + "/mo " + ("target" if _lp_is_target else "calculated") + " rental: " +
                      (("£" + format(_gp_before_buyout, ",.0f") + " before buyout, less £" + format(termination_cost, ",.0f") + " buyout") if termination_cost > 0
                       else ("funder pays £" + format(_profit_disc_turnover, ",.0f") + " less costs £" + format(pl_data["cos_full"], ",.0f"))))
        else:
            LP_SUB = "£" + format(_profit_disc_turnover, ",.0f") + " paid by the customer less costs £" + format(pl_data["cos_full"], ",.0f") + " - no funder"
        pb1, pb2, pb3   = st.columns(3)
        with pb1:
            st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--border-strong)">
              <div class="metric-label">{_DM_PROFIT}</div>
              <div class="metric-value" style="color:var(--text)">£{_adjusted_gp:.0f}</div>
              <div class="metric-sub">{LP_SUB}</div>
            </div>''', unsafe_allow_html=True)
        with pb2:
            st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--accent)">
              <div class="metric-label">Services Profit</div>
              <div class="metric-value" style="color:var(--accent)">£{_svc_profit_term:.0f}</div>
              <div class="metric-sub">£{_svc_margin_pm:.2f}/mo × {lease_term}mo  ·  sell £{_svc_sell_pm:.2f} cost £{_svc_cost_pm:.2f}</div>
            </div>''', unsafe_allow_html=True)
        with pb3:
            st.markdown(f'''<div class="metric-card" style="border-left:4px solid var(--good);background:rgba(52,211,153,.08)">
              <div class="metric-label" style="color:var(--good)">Total Gross Profit</div>
              <div class="metric-value" style="color:var(--good)">£{_total_gp:.0f}</div>
              <div class="metric-sub">{_DM_NAME if not is_lease else "Lease"} £{_adjusted_gp:.0f} + Services £{_svc_profit_term:.0f}{(" + Printers £" + format(printer_lease_profit, ".0f")) if printer_rows else ""}</div>
            </div>''', unsafe_allow_html=True)
        if termination_cost > 0:
            st.markdown(
                f'<div class="info-box">🔒 Termination / Buyout: <strong>£{termination_cost:.2f}</strong> - '
                f'{"spread at £" + str(round(termination_cost/lease_term,2)) + "/mo over " + LEASE_TERM_LABELS[lease_term] if is_spread else "included in upfront cost"}</div>',
                unsafe_allow_html=True
            )
        if pat_warn:
            st.markdown(f'<div class="warning-box">{pat_warn}</div>', unsafe_allow_html=True)
        if override_bb_sell > 0:
            st.markdown(f'<div class="info-box">🔐 BB Override by: {override_initials or "?"} | Customer: {override_customer or "?"}</div>', unsafe_allow_html=True)

    # ── Call Scope, air conditioning and the overall deal (each its own agreement) ──
    def _mcard(label, value, sub="", col="var(--text)", border="var(--border-strong)", size="1.6rem"):
        return (f'<div class="metric-card" style="border-left:4px solid {border}"><div class="metric-label">{label}</div>'
                f'<div class="metric-value" style="color:{col};font-size:{size}">{value}</div><div class="metric-sub">{sub}</div></div>')
    _is_adm = bool(st.session_state.admin_unlocked)
    _cs_on = bool(cs_active and not cs_crm_missing)
    _unit_sz = float(commission_unit_size or 1000)
    _cs_units = (float(cs_quote.get("profit", 0) or 0) / _unit_sz) if _cs_on else 0.0
    _ac_gp = ((ac_quote["cash_gp"] if ac_quote["is_cash"] else ac_quote["gp"]) if ac_active else 0.0)
    _ac_units = _ac_gp / _unit_sz if ac_active else 0.0
    if _cs_on:
        st.markdown("#### 🔮 Call Scope")
        _q = cs_quote
        _cols = st.columns(3 if not _is_adm else 3)
        _cols[0].markdown(_mcard("Call Scope Monthly", f"£{_q['monthly_total']:,.2f}",
                                 f"{_q['term']} months, excl. VAT" + (f" · {_q['discount']:g}% discount" if _q["discount"] > 0 else "")), unsafe_allow_html=True)
        _setup_tot = sum(s_["total"] for s_ in _q["setup"]) if _q["setup_mode"] != "waived" else 0.0
        _cols[1].markdown(_mcard("Set-up (one-off)", f"£{_setup_tot:,.2f}", "Waived" if _q["setup_mode"] == "waived" else "Excl. VAT"), unsafe_allow_html=True)
        _cols[2].markdown(_mcard("Value over term", f"£{_q['services_value']:,.0f}", f"{_q['term']} months of Call Scope"), unsafe_allow_html=True)
        if _is_adm:
            a1, a2, a3, a4 = st.columns(4)
            a1.markdown(_mcard("Monthly cost", f"£{_q['buy_monthly']:,.2f}", "What Call Scope costs us each month"), unsafe_allow_html=True)
            a2.markdown(_mcard("Monthly margin", f"£{_q['monthly_total'] - _q['buy_monthly']:,.2f}", "Sell less cost", col="var(--accent)", border="var(--accent)"), unsafe_allow_html=True)
            a3.markdown(_mcard("Profit over term", f"£{_q['profit']:,.0f}", "After set-up costs", col="var(--good)", border="var(--good)"), unsafe_allow_html=True)
            a4.markdown(_mcard("Units", f"{_cs_units:.2f}", f"£{commission_per_unit:.0f}/unit = £{_cs_units * commission_per_unit:,.0f}", col="var(--accent)", border="var(--accent)"), unsafe_allow_html=True)
    if ac_active:
        st.markdown("#### ❄️ Air conditioning")
        _q = ac_quote
        b1_, b2_, b3_ = st.columns(3)
        if _q["is_cash"]:
            b1_.markdown(_mcard("Cash Price", f"£{_q['cash_price']:,.2f}", "One-off, excl. VAT" + (f" · {_q['discount']:g}% discount" if _q["discount"] > 0 else "")), unsafe_allow_html=True)
        else:
            b1_.markdown(_mcard("Air Con Monthly", f"£{_q['rental']:,.2f}", f"{_q['term']} months, excl. VAT" + (f" · {_q['discount']:g}% discount" if _q["discount"] > 0 else "")), unsafe_allow_html=True)
        b2_.markdown(_mcard("Units fitted", f"{_q['n_units']}", f"{_q['est_days']:g} day(s) · {_q['engineers']} engineer(s)"), unsafe_allow_html=True)
        b3_.markdown(_mcard("Support after year 1", f"£{_q['support']:,.2f}", "Per year, excl. VAT"), unsafe_allow_html=True)
        if _is_adm:
            c1_, c2_, c3_, c4_ = st.columns(4)
            c1_.markdown(_mcard("Lease value" if not _q["is_cash"] else "Cash price", f"£{(_q['funded'] if not _q['is_cash'] else _q['cash_price']):,.0f}",
                                "What the funder pays for this rental" if not _q["is_cash"] else "Customer pays up front"), unsafe_allow_html=True)
            c2_.markdown(_mcard("Cost to us", f"£{_q['set_up']:,.0f}", "Equipment, install, support year 1 and fees"), unsafe_allow_html=True)
            c3_.markdown(_mcard("Gross profit", f"£{_ac_gp:,.0f}", "Lease value less cost" if not _q["is_cash"] else "Cash price less cost", col="var(--good)", border="var(--good)"), unsafe_allow_html=True)
            c4_.markdown(_mcard("Units", f"{_ac_units:.2f}", f"£{commission_per_unit:.0f}/unit = £{_ac_units * commission_per_unit:,.0f}", col="var(--accent)", border="var(--accent)"), unsafe_allow_html=True)
    if n_packs() >= 2:
        st.markdown("#### 🧾 Overall - all agreements together")
        _o_mo = (total_mo if _tele_any else 0.0) + (cs_quote["monthly_total"] if _cs_on else 0.0) + (ac_quote["rental"] if (ac_active and not ac_quote["is_cash"]) else 0.0)
        _o_one = ((upfront if (_tele_any and not is_spread) else 0.0)
                  + (sum(s_["total"] for s_ in cs_quote["setup"]) if (_cs_on and cs_quote["setup_mode"] != "waived") else 0.0)
                  + (ac_quote["cash_price"] if (ac_active and ac_quote["is_cash"]) else 0.0))
        _parts = ([f"Telephony £{total_mo:,.2f}"] if _tele_any else []) + ([f"Call Scope £{cs_quote['monthly_total']:,.2f}"] if _cs_on else []) \
                 + ([f"Air con £{ac_quote['rental']:,.2f}"] if (ac_active and not ac_quote["is_cash"]) else [])
        o1_, o2_ = st.columns(2)
        o1_.markdown(_mcard("Total Monthly (all)", f"£{_o_mo:,.2f}", " + ".join(_parts) + " · excl. VAT"), unsafe_allow_html=True)
        o2_.markdown(_mcard("Total One-off (all)", f"£{_o_one:,.2f}", "Hardware, set-up and cash sales · excl. VAT"), unsafe_allow_html=True)
        if _is_adm:
            _t_units = float(commission_units or 0) + _cs_units + _ac_units
            _t_gp = (float(_total_gp) if _tele_any else 0.0) + (float(cs_quote["profit"]) if _cs_on else 0.0) + _ac_gp
            _lv = (float(lease_value) if (_tele_any and is_lease) else 0.0) + (float(ac_quote["funded"]) if (ac_active and not ac_quote["is_cash"]) else 0.0)
            g1, g2, g3, g4 = st.columns(4)
            g1.markdown(_mcard("Total lease value", f"£{_lv:,.0f}", "Telephony + air conditioning leases"), unsafe_allow_html=True)
            g2.markdown(_mcard("Total gross profit", f"£{_t_gp:,.0f}", "Telephony + Call Scope + air conditioning", col="var(--good)", border="var(--good)"), unsafe_allow_html=True)
            g3.markdown(_mcard("Total units", f"{_t_units:.2f}", f"Telephony {float(commission_units or 0):.2f} · Call Scope {_cs_units:.2f} · Air con {_ac_units:.2f}", col="var(--accent)", border="var(--accent)"), unsafe_allow_html=True)
            g4.markdown(_mcard("Est. commission", f"£{float(commission) + (_cs_units + _ac_units) * commission_per_unit:,.0f}", "At the rate for this deal", col="var(--accent)", border="var(--accent)"), unsafe_allow_html=True)


# ─── END OF RUN: hero, live summary, sign out ───────────────────────────────
# Sidebar rental + units: exactly the numbers used in the Consultant view
with _units_ph:
    _is_override = _eff_target > 0 and abs(_desired_rental - base_rental) > 0.01
    _disc_note = f"  ·  after discount" if (svc_disc_pct + bb_disc_pct + cs_disc_pct) > 0 else ""
    if is_inhouse:
        st.caption(f"{'Override' if _is_override else 'Calculated'} system rental: £{hw_monthly_spread:,.2f}/mo  ·  {commission_units:.2f} units{_disc_note}")
        if _sr_ov is not None:
            st.caption(":orange[An admin price is set for this deal (Admin - Per-Deal Overrides).]")
    else:
        st.caption(f"{'Override' if _is_override else 'Calculated'}: £{_desired_rental:,.2f}/mo  ·  "
                   f"{commission_units:.2f} units{_disc_note}")
    if is_lease and lease_value > 0:
        st.caption(f"Max termination: £{max_termination:,.0f}")
        if termination_over:
            st.caption(f":orange[Buyout is {termination_over_pct:.0f}% over the maximum]")
        if safe_buyout_limited:
            st.caption(f":orange[At this rental the safe buyout is £{safe_buyout:,.0f} - above that, lease profit goes negative]")
        if rental_short_of_buyout > 0:
            st.caption(f":orange[Target rental is £{rental_short_of_buyout:,.2f}/mo below what covers the buyout "
                       f"(£{_rental_to_cover:,.2f}/mo) - we're absorbing it]")
        if lease_profit_negative:
            st.caption(f":orange[Lease profit is -£{abs(_adjusted_gp):,.0f} at this rental and buyout]")
with _cs_units_ph:
    if cs_active:
        _csu = float(cs_quote.get("profit", 0) or 0) / float(commission_unit_size or 1000)
        st.caption(f"{'Target' if float(st.session_state.get('cs_target_rental') or 0) > 0 else 'Calculated'}: £{cs_quote['monthly_total']:,.2f}/mo  ·  {_csu:.2f} units")
        if cs_target_note:
            st.caption(f":orange[Target is {cs_target_note}]")
    else:
        st.caption("Pick Call Scope services to use this.")
with _ac_units_ph:
    if ac_active:
        _acu = (ac_quote["cash_gp"] if ac_quote["is_cash"] else ac_quote["gp"]) / float(commission_unit_size or 1000)
        _ac_t = float(st.session_state.get("ac_desired_rental") or 0) > 0 and not ac_quote["is_cash"]
        st.caption(f"{'Target' if _ac_t else 'Calculated'}: £{(ac_quote['cash_price'] if ac_quote['is_cash'] else ac_quote['rental']):,.2f}{'' if ac_quote['is_cash'] else '/mo'}  ·  {_acu:.2f} units")
    else:
        st.caption("Pick air conditioning to use this.")
with _tot_units_ph:
    _tu = float(commission_units or 0)
    _tparts = [f"Telephony {_tu:.2f}"]
    if cs_active:
        _cu = float(cs_quote.get("profit", 0) or 0) / float(commission_unit_size or 1000)
        _tu += _cu; _tparts.append(f"Call Scope {_cu:.2f}")
    if ac_active:
        _au = (ac_quote["cash_gp"] if ac_quote["is_cash"] else ac_quote["gp"]) / float(commission_unit_size or 1000)
        _tu += _au; _tparts.append(f"Air con {_au:.2f}")
    st.markdown(f"**Total units: {_tu:.2f}**")
    if len(_tparts) > 1:
        st.caption("  ·  ".join(_tparts))
try:
    _n_handsets = sum(desktop_quantities.values()) + sum(q for n, q in cordless_quantities.items() if _is_user_handset(n))
    _n_hw = (_n_handsets + sum(headset_quantities.values())
             + sum(q for q in other_quantities.values() if q))
    _n_routers = sum(router_quantities.values()) if add_router else 0
    _n_bb = (0 if bb_provider == "None / Customer Supplied" else 1) + extra_bb_count
    _svc_mo = float(svc.get("total_sell", 0) or 0)
    _has_customer, _has_hw, _has_svc = bool(comp_name), (_n_hw + _n_routers + printer_count) > 0, _svc_mo > 0
except Exception:
    _n_handsets = _n_hw = _n_routers = _n_bb = 0
    _svc_mo, _has_customer, _has_hw, _has_svc = 0.0, bool(st.session_state.get("q_comp_name")), False, False

# Hero + stepper
_steps = [("Customer", _has_customer), ("Hardware", _has_hw), ("Services", _has_svc), ("Paperwork", False)]
_active = next((i for i, (_, d) in enumerate(_steps) if not d), len(_steps) - 1)
_step_html = []
for _i, (_lbl, _done) in enumerate(_steps):
    _cls = "done" if _done else ("active" if _i == _active else "")
    _num = "&#10003;" if _done else str(_i + 1)
    _step_html.append(f'<div class="pe-step {_cls}"><div class="num">{_num}</div>{_lbl}</div>')
_eyebrow = f"Quoting for {comp_name}" if comp_name else "New quote"
render_html(
    f'<div class="pe-hero"><div>'
    f'<div class="pe-eyebrow"><span class="dot"></span>{esc(_eyebrow)}</div>'
    f'<div class="pe-title">{esc(_CO)} <span>quote builder</span></div>'
    f'<div class="pe-sub">Build the system, price the deal and produce the full paperwork pack.</div>'
    f'</div><div class="pe-stepper">' + '<div class="pe-step-sep"></div>'.join(_step_html) + '</div></div>',
    target=_hero_ph)

# Live summary (customer-safe: no margins or commission)
def _cs_summary_html():
    q = cs_quote
    _kst = 'style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"'
    rows = "".join(f'<div class="pe-sum-row"><span class="k" {_kst}>{esc(l["name"].replace("AI CRM Integration", "AI CRM"))}'
                   + (f' x{l["qty"]}' if l["qty"] > 1 else "")
                   + f'</span><span class="v" style="flex:none">£{l["total"]:,.2f}/mo</span></div>' for l in q["lines"])
    if q["setup"]:
        rows += ('<div class="pe-sum-row"><span class="k">One-off set-up</span><span class="v">'
                 + ("Waived" if q["setup_mode"] == "waived" else f'£{q["setup_total"]:,.2f}') + '</span></div>')
    if q["discount"] > 0:
        rows += f'<div class="pe-sum-row"><span class="k">Discount</span><span class="v">{q["discount"]:g}% ({q["style"]})</span></div>'
    if q["years"] > 1 and q["discount"] > 0 and q["style"] == "stepped":
        for r in q["schedule"]:
            rows += f'<div class="pe-sum-row"><span class="k">Year {r["year"]}</span><span class="v">£{r["monthly"]:,.2f}/mo</span></div>'
    chips = []
    if cs_crm_missing:
        chips.append(chip("Customer's CRM needed", "warn"))
    return (f'<div class="pe-sum-head"><div class="t">Call Scope summary</div>{chip(str(q["term"]) + " months", "accent")}</div>'
            f'<div class="pe-sum-total"><div class="l">Call Scope monthly' + (" (year 1)" if q["discount"] > 0 and q["style"] == "stepped" and q["years"] > 1 else "")
            + f'</div><div class="v">£{q["monthly_total"]:,.2f} <small>+ VAT</small></div></div>'
            f'<div class="pe-sum-rows">{rows}</div>' + (f'<div class="pe-sum-foot">{"".join(chips)}</div>' if chips else "")
            + '<div class="pe-sum-foot" style="opacity:.75;font-size:.72rem">Separate agreement - its own paperwork, terms and Direct Debit.</div>')


def _ac_summary_html():
    q = ac_quote
    _co = st_company()
    rows = [("Air conditioning units", str(q["n_units"]))]
    if q["is_cash"]:
        rows.append(("Cash price", f"£{q['cash_price']:,.2f}"))
    else:
        rows.append(("Agreement", f"{q['term']} months"))
    rows.append(("Support after year 1", f"£{q['support']:,.2f}/yr"))
    rows_h = "".join(f'<div class="pe-sum-row"><span class="k">{esc(k)}</span><span class="v">{esc(v)}</span></div>' for k, v in rows)
    chips = []
    big = f"£{q['cash_price']:,.2f} <small>+ VAT</small>" if q["is_cash"] else f"£{q['rental']:,.2f} <small>+ VAT / month</small>"
    return (f'<div class="pe-sum-head"><div class="t">{esc(_co["trading"])} summary</div>{chip("Cash" if q["is_cash"] else str(q["term"]) + " months", "accent")}</div>'
            f'<div class="pe-sum-total"><div class="l">{"Air conditioning (one-off)" if q["is_cash"] else "Air conditioning rental"}</div><div class="v">{big}</div></div>'
            f'<div class="pe-sum-rows">{rows_h}</div>' + (f'<div class="pe-sum-foot">{"".join(chips)}</div>' if chips else "")
            + '<div class="pe-sum-foot" style="opacity:.75;font-size:.72rem">Separate agreement - its own paperwork, terms and Direct Debit.</div>')


with _sum_card_cs:
    if cs_active:
        render_html(_cs_summary_html())
with _sum_card_ac:
    if ac_active:
        render_html(_ac_summary_html())
with _sum_card:
    if not (_has_hw or _has_svc):
        render_html(
            '<div class="pe-empty"><div class="ic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/>'
            '<line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="12" y2="14"/></svg></div>'
            '<div class="t">Nothing priced yet</div><ol>'
            '<li>Add the customer in the sidebar</li>'
            '<li>Pick phones and hardware</li>'
            '<li>Choose broadband and services</li></ol></div>')
    else:
        _term_lbl = LEASE_TERM_LABELS.get(lease_term, "") if is_spread else "Upfront purchase"
        _rows = []
        if is_spread:
            _rows.append(("System rental" if is_inhouse else "Hardware lease", f"£{hw_monthly_spread:,.2f}/mo"))
        else:
            _rows.append(("Hardware (one-off)", f"£{upfront:,.2f}"))
        if printer_rows:
            _rows.append(("Printers (lease + est. prints)", f"£{printer_monthly + printer_print_est_mo:,.2f}/mo"))
        _rows += [("Services", f"£{_svc_mo:,.2f}/mo"),
                  ("Handsets", str(_n_handsets)),
                  ("Broadband lines", str(_n_bb)),
                  ("Routers", str(_n_routers)),
                  ("User licences", str(total_voice_channels))]
        _chips = []
        try:
            _cur = float(current_total or 0)
            if _cur > 0:
                _diff = _cur - total_mo
                _chips.append(chip(f"Saving £{_diff * 12:,.0f}/yr", "good") if _diff >= 0
                              else chip(f"£{abs(_diff) / 30.44:,.2f}/day investment", "accent"))
        except Exception:
            pass
        if _eff_target > 0:
            _chips.append(chip("Rental adjusted", "warn"))
        render_html(
            f'<div class="pe-sum-head"><div class="t">Telephony summary</div>{chip(_term_lbl, "accent")}</div>'
            f'<div class="pe-sum-total"><div class="l">Total monthly</div>'
            f'<div class="v">£{total_mo:,.2f} <small>+ VAT</small></div></div>'
            f'<div class="pe-sum-rows">'
            + "".join(f'<div class="pe-sum-row"><span class="k">{k}</span><span class="v">{v}</span></div>'
                      for k, v in _rows)
            + '</div>' + (f'<div class="pe-sum-foot">{"".join(_chips)}</div>' if _chips else ""))

with st.sidebar:
    st.markdown("")
    _cu = st.session_state.get("current_user")
    if _cu:
        st.caption(f"Signed in as {_cu['name'] or _cu['email']}" + (" (admin)" if _cu["role"] == "admin" else ""))
    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    if st.button("Log out", key="btn_logout", **FULL_WIDTH):
        for _k in ("app_authenticated", "admin_unlocked", "consultant_unlocked"):
            st.session_state[_k] = False
        st.session_state.pop("current_user", None)
        st.rerun()
