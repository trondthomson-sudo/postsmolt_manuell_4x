"""
streamlit_app.py - postsmolt, MANUELT TIDSSTYRT (bruker-definert oppskrift, 3 tanker)
-----------------------------------------------------------------------------------
Tredje alternativ, ved siden av postsmolt_kalender/ (fast, delt syklus,
auto-optimalisert) og postsmolt_individuell/ (individuelt tidsstyrt per
kohort, men fortsatt automatisk kappet mot et syklus-tak).

Her styrer DU alt av timing manuelt for én "mal-kohort" - modellen gjentar
deretter akkurat den samme oppskriften automatisk for hver nye kohort.
Leveringsvekten beregnes fortsatt av samme vekstmotor (Skretting SGR/FCR +
temperaturprofil + RGI) som de to andre modellene - kun TIDSPUNKTENE er
manuelle. Se scheduler_manuell.py sin docstring for hele resonnementet.

Run:  python -m streamlit run streamlit_app.py
"""
import io
from datetime import date

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

import config as default_config
from growth_tables import GrowthTables
from scheduler_manuell import build_manual_schedule, week_label
from excel_export import write_excel
from formatting import fmt_int, fmt_float, parse_number

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "Mai", "Jun",
               "Jul", "Aug", "Sep", "Okt", "Nov", "Des"]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # ikke skuddår - ubetydelig avvik
NORW_MONTHS = ["jan", "feb", "mar", "apr", "mai", "jun",
               "jul", "aug", "sep", "okt", "nov", "des"]

TANK_COLORS = {"Tank 1": "#E8623D", "Tank 2": "#2F8F7A", "Tank 3": "#6E5AA6"}
LINESTYLES = ["-", (0, (6, 2)), (0, (1, 1.3))]

# ---- Fargekoder for kalender-illustrasjonen - matcher excel_export.py ----
ILLUSTRATION_FILL_TANK1 = "#E3EFE1"
ILLUSTRATION_FILL_TANK2 = "#DCEAF5"
ILLUSTRATION_FILL_TANK3 = "#FBE9DD"
ILLUSTRATION_FILL_MISC = "#FBF3D9"
ILLUSTRATION_FILL_CLEAN = "#C9C9C9"
ILLUSTRATION_FILL_COLLISION = "#F0B0B0"
ILLUSTRATION_FILL_HEADER = "#1F3B57"
ILLUSTRATION_HEADER_ROWS = {"Kalenderuke", "Dato"}
ILLUSTRATION_YEAR_BORDER = "4px solid #14213D"


def _illustration_row_color(label: str) -> str | None:
    if label.startswith("Tank 1 - "):
        return ILLUSTRATION_FILL_TANK1
    if label.startswith("Tank 2 - "):
        return ILLUSTRATION_FILL_TANK2
    if label.startswith("Tank 3 - "):
        return ILLUSTRATION_FILL_TANK3
    if label in ("Overføring", "Levering", "Levert WFE (t)", "Akkumulert i aret (t)",
                 "Akkumulert i året (t)"):
        return ILLUSTRATION_FILL_MISC
    return None


def _illustration_fmt_cell(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        try:
            return f"{v:,.1f}".replace(",", " ")
        except Exception:
            return str(v)
    return "" if v is None else str(v)


def _illustration_style_row(row):
    label = row.name
    is_header = label in ILLUSTRATION_HEADER_ROWS
    is_status = label.endswith("status")
    is_kohort = label.endswith("kohort")
    base_bg = _illustration_row_color(label)
    styles = []
    for val in row:
        css = ["white-space: nowrap", "padding: 2px 7px", "border: 1px solid #d9d9d9", "font-size: 12px"]
        if is_header:
            css += [f"background-color: {ILLUSTRATION_FILL_HEADER}", "color: white", "font-weight: bold"]
        elif is_status and val == "Rengjoring (kollisjon)":
            css += [f"background-color: {ILLUSTRATION_FILL_COLLISION}", "font-weight: bold", "color: #7A1F1F"]
        elif is_status and val == "Rengjoring":
            css += [f"background-color: {ILLUSTRATION_FILL_CLEAN}", "font-weight: bold"]
        else:
            if base_bg:
                css.append(f"background-color: {base_bg}")
            if is_status or (is_kohort and val):
                css.append("font-weight: bold")
        styles.append(";".join(css))
    return styles


def _illustration_boundary_style_row(row, boundary_cols):
    return [f"border-left: {ILLUSTRATION_YEAR_BORDER}" if c in boundary_cols else "" for c in row.index]


def render_calendar_illustration(df_to_show: pd.DataFrame):
    """Fargekodet HTML-gjengivelse av kalenderen (felt = rader, uker = kolonner) -
    samme fargespråk som Excel-eksporten (excel_export.py), men direkte synlig
    i appen uten nedlasting. Tegner en fet strek der kalenderåret skifter."""
    cols = list(df_to_show.columns)
    boundary_cols = set()
    if "Dato" in df_to_show.index:
        dato_row = df_to_show.loc["Dato"]
        prev_year = None
        for c in cols:
            try:
                y = pd.Timestamp(dato_row[c]).year
            except Exception:
                y = None
            if y is not None:
                if prev_year is not None and y != prev_year:
                    boundary_cols.add(c)
                prev_year = y
    boundary_positions = [i for i, c in enumerate(cols) if c in boundary_cols]

    styler = (
        df_to_show.style
        .apply(_illustration_style_row, axis=1)
        .apply(_illustration_boundary_style_row, axis=1, boundary_cols=boundary_cols)
        .format(_illustration_fmt_cell)
        .set_table_styles([
            {"selector": "th.col_heading", "props": [
                ("background-color", ILLUSTRATION_FILL_HEADER), ("color", "white"),
                ("font-weight", "bold"), ("padding", "3px 8px"), ("white-space", "nowrap"),
                ("position", "sticky"), ("top", "0"), ("z-index", "2"),
            ]},
            {"selector": "th.row_heading", "props": [
                ("background-color", "#f2f2f2"), ("font-weight", "bold"),
                ("padding", "3px 10px"), ("white-space", "nowrap"), ("text-align", "left"),
                ("position", "sticky"), ("left", "0"), ("z-index", "1"),
            ]},
            {"selector": "th.blank", "props": [
                ("background-color", ILLUSTRATION_FILL_HEADER),
                ("position", "sticky"), ("top", "0"), ("left", "0"), ("z-index", "3"),
            ]},
            {"selector": "table", "props": [("border-collapse", "collapse")]},
        ] + [
            {"selector": f"th.col_heading.level0.col{pos}", "props": [("border-left", ILLUSTRATION_YEAR_BORDER)]}
            for pos in boundary_positions
        ])
    )
    html = styler.to_html()
    st.markdown(
        f'<div style="overflow:auto; max-height:640px; border:1px solid #d9d9d9;">{html}</div>',
        unsafe_allow_html=True,
    )

gt = GrowthTables()


def _no_date(d):
    return f"{d.day}. {NORW_MONTHS[d.month - 1]} {d.year}"


@st.cache_data(show_spinner="Beregner manuell oppskrift-rotasjon...")
def _cached_build(tank_volume_m3, n_growout_tanks, split_ratios, start_weight_kg,
                   n_batches_in_rotation, batch_smolt_counts, batch_tank1_growth_weeks,
                   batch_growout_weeks, batch_tank1_cleaning_weeks, batch_growout_cleaning_weeks,
                   max_density_kg_m3, annual_mortality_pct, rgi_pct, monthly_temperatures_c,
                   start_iso_year, start_iso_week, n_years_to_run):
    import types
    cfg = types.SimpleNamespace(
        TANK_VOLUME_M3=tank_volume_m3, N_GROWOUT_TANKS=n_growout_tanks,
        SPLIT_RATIOS=list(split_ratios), START_WEIGHT_KG=start_weight_kg,
        N_BATCHES_IN_ROTATION=n_batches_in_rotation,
        BATCH_SMOLT_COUNTS=list(batch_smolt_counts),
        BATCH_TANK1_GROWTH_WEEKS=list(batch_tank1_growth_weeks),
        BATCH_GROWOUT_WEEKS=list(batch_growout_weeks),
        BATCH_TANK1_CLEANING_WEEKS=list(batch_tank1_cleaning_weeks),
        BATCH_GROWOUT_CLEANING_WEEKS=list(batch_growout_cleaning_weeks),
        MAX_DENSITY_KG_M3=max_density_kg_m3,
        ANNUAL_MORTALITY_PCT=annual_mortality_pct, RGI_PCT=rgi_pct,
        MONTHLY_TEMPERATURES_C=list(monthly_temperatures_c),
        START_ISO_YEAR=start_iso_year, START_ISO_WEEK=start_iso_week,
        N_YEARS_TO_RUN=n_years_to_run,
    )
    df, gens, meta = build_manual_schedule(cfg, growth_tables=gt)
    return df, gens, meta, cfg


def _auto_format_number_input(label, key, default_value, help_text=None, min_value=1000.0):
    """Text-input som viser tusenskiller (mellomrom) - reformateres til
    '2 400 000'-stil sa snart feltet mister fokus (Streamlit sin on_change)."""
    if key not in st.session_state:
        st.session_state[key] = fmt_int(default_value)

    def _reformat():
        val = max(min_value, parse_number(st.session_state[key], default=default_value))
        st.session_state[key] = fmt_int(val)

    st.text_input(label, key=key, on_change=_reformat, help=help_text)
    return max(min_value, parse_number(st.session_state[key], default=default_value))


st.set_page_config(page_title="Hexacage - postsmolt, manuell modell (4x/år)", layout="wide")
st.title("Hexacage produksjonsplan - manuelt tidsstyrt postsmolt-modell (3 tanker, 4x runder/år default)")
st.caption(
    "Her styrer du selv timingen for en 'mal-kohort' - når den settes inn, "
    "hvor lenge den står i hver tank, når tankene vaskes - og modellen "
    "gjentar akkurat den samme oppskriften automatisk for hver nye kohort. "
    "Leveringsvekten beregnes fortsatt med samme vekstmotor og "
    "temperaturprofil som de to andre modellene - kun tidspunktene er "
    "manuelle her, i motsetning til de to andre scenariene som "
    "auto-optimaliserer syklusen. Bruk denne som en manuell "
    "sammenligningsbasis mot de to andre."
)


# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("Manuell oppskrift-rotasjon (gjentas automatisk)")
    st.caption(
        "Definer én eller flere oppskrifter - modellen setter dem automatisk "
        "inn i tur og orden (1, 2, 3, ..., 1, 2, 3, ...) så snart tank 1 er "
        "ledig igjen, gjennom hele kjøreperioden. Bruk flere oppskrifter for "
        "å f.eks. sette inn flere smolt eller lengre veksttid på vinter-batchen "
        "for å kompensere for kaldere vann og treffe tetthetstaket bedre."
    )

    c1, c2 = st.columns(2)
    start_iso_year = c1.number_input(
        "Startår kohort 1 (ISO)", min_value=2020, max_value=2100,
        value=int(default_config.START_ISO_YEAR), step=1,
    )
    start_iso_week = c2.number_input(
        "Startuke kohort 1 (ISO)", min_value=1, max_value=53,
        value=int(default_config.START_ISO_WEEK), step=1,
    )

    start_weight_g = st.number_input(
        "Smoltvekt ved utsett (g) - felles for alle oppskrifter", min_value=10.0, max_value=2000.0,
        value=float(default_config.START_WEIGHT_KG * 1000), step=10.0,
    )

    n_batches_in_rotation = st.number_input(
        "Antall ulike oppskrifter i rotasjonen", min_value=1, max_value=4,
        value=int(default_config.N_BATCHES_IN_ROTATION), step=1,
        help="F.eks. 3 hvis du vil ha én egen oppskrift per runde i året "
             "(vinter-, vår- og sommer-batch), eller 1 for samme oppskrift hele året.",
    )
    n_batches_in_rotation = int(n_batches_in_rotation)

    default_smolt = list(default_config.BATCH_SMOLT_COUNTS)
    default_growth = list(default_config.BATCH_TANK1_GROWTH_WEEKS)
    default_growout = list(default_config.BATCH_GROWOUT_WEEKS)
    default_clean = list(default_config.BATCH_TANK1_CLEANING_WEEKS)
    default_growout_clean = list(default_config.BATCH_GROWOUT_CLEANING_WEEKS)

    batch_smolt_counts, batch_tank1_growth_weeks = [], []
    batch_growout_weeks, batch_tank1_cleaning_weeks = [], []
    batch_growout_cleaning_weeks = []
    for i in range(n_batches_in_rotation):
        st.markdown(f"**Oppskrift {i + 1}**")
        d_smolt = default_smolt[i % len(default_smolt)]
        d_growth = default_growth[i % len(default_growth)]
        d_growout = default_growout[i % len(default_growout)]
        d_clean = default_clean[i % len(default_clean)]
        d_growout_clean = default_growout_clean[i % len(default_growout_clean)]

        smolt_i = _auto_format_number_input(
            f"Antall smolt satt inn (tank 1) - oppskrift {i + 1}",
            key=f"smolt_batch_{i}", default_value=float(d_smolt),
            help_text="Skriv tall med eller uten mellomrom, f.eks. 2 400 000 eller 2400000.",
        )
        batch_smolt_counts.append(int(smolt_i))
        st.caption(f"= {fmt_int(int(smolt_i))} smolt")

        bc1, bc2 = st.columns(2)
        growth_i = bc1.number_input(
            "Uker i tank 1", min_value=1, max_value=52,
            value=int(d_growth), step=1, key=f"growth_batch_{i}",
        )
        growout_i = bc2.number_input(
            "Uker i veksttank", min_value=1, max_value=52,
            value=int(d_growout), step=1, key=f"growout_batch_{i}",
        )
        bc3, bc4 = st.columns(2)
        clean_i = bc3.number_input(
            "Vask tank 1", min_value=1, max_value=5,
            value=max(1, min(5, int(d_clean))), step=1, key=f"clean_batch_{i}",
            help="Vasketid for tank 1 etter denne oppskriften er overført til "
                 "veksttank - fleksibel 1-5 uker, slik at du kan justere summen "
                 "for hele rotasjonen til å treffe akkurat 52 uker.",
        )
        growout_clean_i = bc4.number_input(
            "Vask veksttank", min_value=1, max_value=5,
            value=max(1, min(5, int(d_growout_clean))), step=1, key=f"growout_clean_batch_{i}",
            help="Vasketid for veksttank (tank 2/3) etter denne oppskriften er "
                 "levert - individuell per oppskrift, slik at du kan dytte "
                 "produksjonen frem/tilbake i tid uten å miste fleksibilitet.",
        )
        batch_tank1_growth_weeks.append(int(growth_i))
        batch_growout_weeks.append(int(growout_i))
        batch_tank1_cleaning_weeks.append(int(clean_i))
        batch_growout_cleaning_weeks.append(int(growout_clean_i))

    st.divider()

    full_rotasjon_uker = sum(
        batch_tank1_growth_weeks[i] + batch_tank1_cleaning_weeks[i]
        for i in range(n_batches_in_rotation)
    )
    if full_rotasjon_uker == 52:
        st.success(
            f"Full rotasjon (tank 1, alle {n_batches_in_rotation} oppskrifter): "
            f"**{full_rotasjon_uker} uker** - treffer akkurat 52 uker. "
            f"Produksjonsplanen gjentar seg på nøyaktig samme kalenderuker hvert år."
        )
    else:
        avvik = full_rotasjon_uker - 52
        st.caption(
            f"Full rotasjon (tank 1, alle {n_batches_in_rotation} oppskrifter): "
            f"**{full_rotasjon_uker} uker** - {abs(avvik)} uker "
            f"{'mer' if avvik > 0 else 'mindre'} enn 52. Rotasjonen forskyver "
            f"seg da {abs(avvik)} uke(r) per år i kalenderen. Juster "
            f"vasketiden (1-5 uker) per oppskrift over for å treffe 52 uker "
            f"eksakt, hvis du vil ha en 'recurring' plan."
        )

    recipe_info_placeholder = st.empty()

    st.divider()
    st.header("Tetthetstak")
    max_density = st.number_input(
        "Tetthetstak (kg/m3) - varselnivå", min_value=10.0, max_value=100.0,
        value=float(default_config.MAX_DENSITY_KG_M3), step=1.0,
        help="Modellen justerer ikke timingen for å holde seg under dette "
             "taket - den bare varsler hvis en kohort overstiger det.",
    )

    st.divider()
    st.header("Tank / lokalitet")
    tank_volume_m3 = _auto_format_number_input(
        "Tankvolum (m3, alle like)", key="tank_volume_text",
        default_value=float(default_config.TANK_VOLUME_M3), min_value=100.0,
        help_text="Skriv tall med eller uten mellomrom, f.eks. 20 000 eller 20000.",
    )
    st.caption(f"= {fmt_int(tank_volume_m3)} m3")
    st.caption("3 tanker totalt: tank 1 (nursery) + tank 2/3 (veksttank, 50/50-splitt).")
    n_growout_tanks = default_config.N_GROWOUT_TANKS
    split_ratios = default_config.SPLIT_RATIOS

    st.divider()
    st.header("Dødelighet og vekstytelse")
    annual_mortality_pct = st.number_input(
        "Dødelighet (%/år)", min_value=0.0, max_value=50.0,
        value=float(default_config.ANNUAL_MORTALITY_PCT), step=0.1, format="%.2f",
    )
    rgi_pct = st.slider(
        "Relative Growth Index (RGI, %)", min_value=80, max_value=120,
        value=int(default_config.RGI_PCT), step=1,
        help="Vekstrate som % av Skretting-tabellens egen referanse-SGR.",
    )

    st.divider()
    st.header("Kalender")
    n_years_to_run = st.slider(
        "Antall år å kjøre", min_value=1, max_value=5,
        value=int(default_config.N_YEARS_TO_RUN), step=1,
    )

    st.divider()
    st.header("Månedlig sjøtemperatur (C)")
    temp_profile_names = list(default_config.TEMPERATURE_PROFILES.keys())

    def _apply_temp_profile():
        chosen = st.session_state["temp_profile_choice"]
        profile = default_config.TEMPERATURE_PROFILES[chosen]
        for i, m in enumerate(MONTH_NAMES):
            st.session_state[f"temp_{m}"] = profile[i]

    st.radio(
        "Temperaturprofil (utgangspunkt - alle måneder er redigerbare under)",
        temp_profile_names,
        index=temp_profile_names.index(default_config.DEFAULT_TEMPERATURE_PROFILE),
        key="temp_profile_choice",
        on_change=_apply_temp_profile,
    )

    temp_cols = st.columns(4)
    monthly_temps = []
    for i, m in enumerate(MONTH_NAMES):
        with temp_cols[i % 4]:
            monthly_temps.append(
                st.number_input(m, key=f"temp_{m}",
                                 value=float(default_config.MONTHLY_TEMPERATURES_C[i]),
                                 step=0.5, format="%.1f")
            )
    gradsum_dagvektet = sum(t * d for t, d in zip(monthly_temps, DAYS_IN_MONTH))
    gradsum_enkel = sum(monthly_temps)
    st.caption(
        f"Total gradsum for året: **{fmt_float(gradsum_dagvektet, 0)} °C-dager** "
        f"(sum av hver månedstemperatur × antall dager i måneden). "
        f"Enkel sum av de 12 månedsverdiene: {fmt_float(gradsum_enkel, 1)} °C."
    )

# ----------------------------------------------------------------------
# RUN THE MODEL
# ----------------------------------------------------------------------
df, gens, meta, cfg = _cached_build(
    tank_volume_m3, n_growout_tanks, tuple(split_ratios), start_weight_g / 1000,
    n_batches_in_rotation, tuple(batch_smolt_counts), tuple(batch_tank1_growth_weeks),
    tuple(batch_growout_weeks), tuple(batch_tank1_cleaning_weeks), tuple(batch_growout_cleaning_weeks),
    max_density, annual_mortality_pct, rgi_pct, tuple(monthly_temps),
    int(start_iso_year), int(start_iso_week), int(n_years_to_run),
)

complete_gens = {gid: info for gid, info in gens.items() if info["growout_final_weight_kg"]}
year2 = cfg.START_ISO_YEAR + 1
year3 = cfg.START_ISO_YEAR + 2

# ---- Kollisjonsvarsel for rotasjonen (fylles her, øverst i sidepanelet) ----
_recipe_lines = [
    f"Oppskrift {i+1}: {fmt_int(meta['batch_smolt_counts'][i])} smolt, "
    f"{meta['batch_tank1_growth_weeks'][i]} uker tank 1 + {meta['batch_tank1_cleaning_weeks'][i]} uker vask "
    f"+ {meta['batch_growout_weeks'][i]} uker veksttank + {meta['batch_growout_cleaning_weeks'][i]} uker vask veksttank"
    for i in range(meta["n_batches_in_rotation"])
]
if meta["kollisjon_i_oppskriften"]:
    recipe_info_placeholder.warning(
        "Denne rotasjonen kolliderer for minst én oppskrift: veksttankene "
        "rekker ikke bli levert og vasket før neste overføring fra tank 1 "
        "skal skje - se 'Kollisjon?'-kolonnen i kohort-sammendraget under.\n\n"
        + "  \n".join(_recipe_lines)
    )
else:
    recipe_info_placeholder.caption(
        "Rotasjon uten kollisjon:  \n" + "  \n".join(_recipe_lines)
    )


# ----------------------------------------------------------------------
# METRICS
# ----------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Oppskrifter i rotasjon", f"{meta['n_batches_in_rotation']}")
col2.metric("Full rotasjon (tank 1)", f"{meta['full_rotasjon_uker']} uker",
            delta=f"{meta['full_rotasjon_uker'] - 52:+d} vs. 52 uker", delta_color="inverse")
col3.metric("Kohorter generert", f"{len(complete_gens)}")
col4.metric("Kollisjon i rotasjonen?", "Ja" if meta["kollisjon_i_oppskriften"] else "Nei")

n_kollisjon = sum(1 for info in complete_gens.values() if info.get("kollisjon"))
if n_kollisjon:
    st.warning(
        f"{n_kollisjon} av {len(complete_gens)} kohorter har kollisjon: neste "
        f"overføring fra tank 1 skjer før veksttankene fra forrige kohort er "
        f"levert OG vasket. Illustrasjonen under viser da nyeste kohort i de "
        f"kolonnene - juster antall uker i sidepanelet for å unngå dette."
    )
else:
    st.caption("Ingen kollisjon: veksttankene er levert og vasket i god tid før neste overføring, for alle kohorter.")

n_over_tak = sum(1 for info in complete_gens.values() if info.get("tetthet_over_tak"))
if n_over_tak:
    st.warning(
        f"{n_over_tak} av {len(complete_gens)} kohorter overstiger tetthetstaket "
        f"({fmt_int(max_density)} kg/m³) - se 'Maks tetthet'-kolonnen under. Reduser "
        f"smoltantallet for aktuell oppskrift i sidepanelet hvis du vil unngå dette."
    )
else:
    st.caption(f"Alle kohorter holder seg under tetthetstaket ({fmt_int(max_density)} kg/m³).")


# ----------------------------------------------------------------------
# KOHORT-SAMMENDRAG
# ----------------------------------------------------------------------
st.subheader("Kohort-sammendrag")

cohort_rows_all = []
for gid, info in complete_gens.items():
    lbl_start, _ = week_label(info["tank1_start_week"], cfg.START_ISO_YEAR, cfg.START_ISO_WEEK)
    lbl_transfer, _ = week_label(info["transfer_week"], cfg.START_ISO_YEAR, cfg.START_ISO_WEEK)
    lbl_delivery, d_delivery = week_label(info["delivery_week"], cfg.START_ISO_YEAR, cfg.START_ISO_WEEK)
    cohort_rows_all.append({
        "Kohort": gid,
        "Oppskrift": info["batch"],
        "År (levering)": d_delivery.isocalendar()[0],
        "Tank 1 start": lbl_start,
        "Overføring": lbl_transfer,
        "Levering (uke)": lbl_delivery,
        "Leveringsdato": _no_date(d_delivery),
        "Tank1-uker": info["tank1_growth_weeks"],
        "Vask tank1-uker": info["tank1_cleaning_weeks"],
        "Veksttank-uker": info["growout_weeks"],
        "Vask veksttank-uker": info["growout_cleaning_weeks"],
        "Smoltantall": info["stocked_tank1"],
        "Smoltvekt inn (g)": round(cfg.START_WEIGHT_KG * 1000),
        "Splittvekt (g)": round(info["split_weight_kg"] * 1000),
        "Leveringsvekt (g)": round(info["growout_final_weight_kg"] * 1000),
        "Maks tetthet (kg/m³)": round(info.get("max_density_kg_m3", 0.0), 1),
        "Over tak?": "Ja" if info.get("tetthet_over_tak") else "",
        "Kollisjon?": "Ja" if info.get("kollisjon") else "",
        "Levert (t)": round(info["delivered_biomass_kg"] / 1000),
    })
cohort_df_all = pd.DataFrame(cohort_rows_all)

years_avail = sorted(cohort_df_all["År (levering)"].unique())
default_year = year2 if year2 in years_avail else years_avail[0]
year_filter = st.selectbox(
    "Vis kohorter med levering i år:",
    options=["Alle år"] + years_avail,
    index=(years_avail.index(default_year) + 1),
    help=f"Standard: år {year2}, det første normaldriftsåret.",
)
if year_filter == "Alle år":
    cohort_df = cohort_df_all
    shown_gids = cohort_df_all["Kohort"].tolist()
else:
    cohort_df = cohort_df_all[cohort_df_all["År (levering)"] == year_filter].drop(columns=["År (levering)"])
    shown_gids = cohort_df["Kohort"].tolist()

cohort_df_display = cohort_df.copy()
if "Smoltantall" in cohort_df_display.columns:
    cohort_df_display["Smoltantall"] = cohort_df_display["Smoltantall"].apply(fmt_int)
st.dataframe(cohort_df_display, hide_index=True, use_container_width=True)

# ---- Totalt + vektet snittvekt + netto tilvekst for de viste kohortene ----
total_delivered_kg = sum(complete_gens[gid]["delivered_biomass_kg"] for gid in shown_gids)
total_delivered_count = sum(
    complete_gens[gid]["delivered_biomass_kg"] / complete_gens[gid]["growout_final_weight_kg"]
    for gid in shown_gids
)
weighted_avg_g = (total_delivered_kg / total_delivered_count) * 1000 if total_delivered_count else 0.0

# Netto tilvekst = tonn levert til kunde MINUS tonn smolt som kom inn (tank 1)
# for de samme kohortene - dvs. hvor mye biomasse anlegget faktisk har lagt
# på, uavhengig av hvor mange fisk det var.
total_smolt_input_kg = sum(
    complete_gens[gid]["stocked_tank1"] * cfg.START_WEIGHT_KG for gid in shown_gids
)
net_growth_t = (total_delivered_kg - total_smolt_input_kg) / 1000

ct1, ct2, ct3 = st.columns(3)
ct1.metric("Totalt levert", f"{fmt_int(round(total_delivered_kg / 1000))} t")
ct2.metric("Snittvekt levering (vektet)", f"{fmt_int(round(weighted_avg_g))} g")
ct3.metric(
    "Netto tilvekst", f"{fmt_int(round(net_growth_t))} t",
    help=f"Levert ({fmt_int(round(total_delivered_kg/1000))} t) - smolt inn "
         f"({fmt_int(round(total_smolt_input_kg/1000))} t).",
)

# ---- Annual totals ----
dato_row = df.loc["Dato"]
wfe_row = df.loc["Levert WFE (t)"]
totals_by_year, deliveries_by_year = {}, {}
for col in df.columns:
    d = date.fromisoformat(dato_row[col])
    y = d.isocalendar()[0]
    totals_by_year[y] = totals_by_year.get(y, 0.0) + wfe_row[col]
for gid, info in complete_gens.items():
    _, d = week_label(info["delivery_week"], cfg.START_ISO_YEAR, cfg.START_ISO_WEEK)
    y = d.isocalendar()[0]
    deliveries_by_year.setdefault(y, []).append(gid)

st.subheader("Årlig levert postsmolt")
annual_rows = [
    {"År": y, "Leveringer": len(deliveries_by_year.get(y, [])),
     "Kohorter": ", ".join(deliveries_by_year.get(y, [])),
     "Levert (t)": round(totals_by_year[y])}
    for y in sorted(totals_by_year)
]
st.dataframe(pd.DataFrame(annual_rows), hide_index=True, use_container_width=True)


# ----------------------------------------------------------------------
# PERIODE-VALG FOR GRAFENE/TABELLEN UNDER
# ----------------------------------------------------------------------
st.subheader("Grafer")
iso_years_all = pd.to_datetime(df.loc["Dato"]).dt.isocalendar().year

view_options = [
    f"Alle simulerte år (år {cfg.START_ISO_YEAR}–{year3}+)",
    f"Kun år {year2} (første normaldriftsår)",
    f"Kun år {year3} (for sammenligning mot år {year2})",
]
view_mode = st.radio("Periode", view_options, horizontal=True)

if view_mode == view_options[1]:
    cols_to_show = df.columns[(iso_years_all == year2).to_numpy()]
elif view_mode == view_options[2]:
    cols_to_show = df.columns[(iso_years_all == year3).to_numpy()]
else:
    mask = (iso_years_all <= year3).to_numpy()
    cols_to_show = df.columns[mask]

sub_df = df[cols_to_show]
dates_x = pd.to_datetime(sub_df.loc["Dato"])
tank_labels = ["Tank 1"] + [f"Tank {i+2}" for i in range(n_growout_tanks)]

if view_mode == view_options[0]:
    shade_years = {y for y in sorted(dates_x.dt.year.unique()) if y != cfg.START_ISO_YEAR}
else:
    shade_years = set()


def _mark_full_years(ax):
    years_present = sorted(dates_x.dt.year.unique())
    for y in years_present:
        boundary = pd.Timestamp(year=y, month=1, day=1)
        if dates_x.min() < boundary < dates_x.max():
            ax.axvline(boundary, color="#888888", linestyle="--", linewidth=1, alpha=0.6)
    ylo, yhi = ax.get_ylim()
    for y in years_present:
        if y not in shade_years:
            continue
        seg_start = max(pd.Timestamp(year=y, month=1, day=1), dates_x.min())
        seg_end = min(pd.Timestamp(year=y + 1, month=1, day=1), dates_x.max())
        ax.axvspan(seg_start, seg_end, color="#2F8F7A", alpha=0.08, zorder=0)
        mid = seg_start + (seg_end - seg_start) / 2
        ax.text(mid, yhi * 0.97, f"År {y} (normaldrift)", ha="center", va="top",
                fontsize=9, color="#2F8F7A", fontweight="bold")


# ---- 1. Biomasse per tank ----
biomass_series = [sub_df.loc[f"{t} - biomasse (t)"].astype(float) for t in tank_labels]
fig1, ax1 = plt.subplots(figsize=(12, 4.2))
ax1.stackplot(
    dates_x, *biomass_series, labels=tank_labels,
    colors=[TANK_COLORS.get(t, "#888888") for t in tank_labels], alpha=0.85,
)
ax1.set_ylabel("Biomasse (t)")
ax1.set_title("Ståande biomasse per tank")
ax1.legend(loc="upper left")
ax1.grid(alpha=0.3)
_mark_full_years(ax1)
fig1.autofmt_xdate()
st.pyplot(fig1)
st.caption(
    "Tank 2 og tank 3 er ofte tallmessig identiske (samme 50/50-splitt, "
    "samme veksttid) - de tegnes derfor med ulikt strekmønster i "
    "linjegrafene under, ellers ville tank 3 skjule tank 2."
)

# ---- 2. Tetthet per tank (kg/m3), med valgt tetthetstak ----
fig2, ax2 = plt.subplots(figsize=(12, 3.6))
for i, t in enumerate(tank_labels):
    dens = pd.to_numeric(sub_df.loc[f"{t} - tetthet (kg/m3)"], errors="coerce")
    ax2.plot(dates_x, dens, label=t, color=TANK_COLORS.get(t, "#888888"),
              linewidth=2.4, linestyle=LINESTYLES[i % len(LINESTYLES)])
ax2.axhline(max_density, color="#C0392B", linestyle="--", linewidth=1.5,
            label=f"{fmt_float(max_density,0)} kg/m³ (tak)")
ax2.set_ylabel("Tetthet (kg/m³)")
ax2.set_title("Tetthet per tank")
ax2.legend(loc="upper left", ncol=len(tank_labels) + 1, fontsize=8)
ax2.grid(alpha=0.3)
_mark_full_years(ax2)
fig2.autofmt_xdate()
st.pyplot(fig2)

max_dens_overall = max(
    pd.to_numeric(sub_df.loc[f"{t} - tetthet (kg/m3)"], errors="coerce").max() for t in tank_labels
)
if max_dens_overall >= max_density:
    st.warning(f"Høyeste tetthet i valgt periode er {fmt_float(max_dens_overall,1)} kg/m³ - over taket ({fmt_float(max_density,0)} kg/m³).")
else:
    st.caption(f"Høyeste tetthet i valgt periode: {fmt_float(max_dens_overall,1)} kg/m³ - under taket ({fmt_float(max_density,0)} kg/m³) i alle tanker.")

# ---- 3. Fiskestørrelse per tank (g) ----
fig3, ax3 = plt.subplots(figsize=(12, 3.6))
for i, t in enumerate(tank_labels):
    vekt = pd.to_numeric(sub_df.loc[f"{t} - vekt (g)"], errors="coerce")
    ax3.plot(dates_x, vekt, label=t, color=TANK_COLORS.get(t, "#888888"),
              linewidth=2.4, linestyle=LINESTYLES[i % len(LINESTYLES)])
    # Merk sluttvekten (siste uke med fisk i tanken, rett før neste
    # rengjørings-/ledig-brudd) på slutten av hver sammenhengende
    # vekstperiode ("runde") i valgt periode.
    is_valid = vekt.notna()
    segment_end = is_valid & ~is_valid.shift(-1, fill_value=False)
    for idx in vekt.index[segment_end]:
        y_val = vekt.loc[idx]
        ax3.annotate(
            f"{y_val:,.0f} g".replace(",", " "),
            xy=(dates_x.loc[idx], y_val),
            xytext=(0, 5 + 11 * i), textcoords="offset points",
            ha="center", fontsize=7.5, fontweight="bold",
            color=TANK_COLORS.get(t, "#888888"),
        )
ax3.set_ylabel("Fiskevekt (g)")
ax3.set_title("Fiskestørrelse per tank")
ax3.legend(loc="upper left")
ax3.grid(alpha=0.3)
_mark_full_years(ax3)
fig3.autofmt_xdate()
st.pyplot(fig3)
st.caption(
    "Linjene brytes i rengjørings-/ledig-uker (ingen fisk i tanken da). "
    "Sluttvekten for hver runde (siste uke før bruddet) er merket med "
    "tall rett over kurven. Leveringsvekten er her et RESULTAT av antall "
    "uker du har satt i sidepanelet (ikke en målvekt modellen styrer mot) "
    "- sammenlign mot de to andre scenariene for å se hva en fast, "
    "manuell oppskrift gir av leveringsvekt gjennom sesongene."
)


# ----------------------------------------------------------------------
# RULLERENDE UKEKALENDER - fargekodet illustrasjon (samme oppsett som
# Excel-eksporten: felt som rader, uker som kolonner, farge per tank)
# ----------------------------------------------------------------------
st.subheader("Rullerende ukekalender - illustrasjon")
st.caption(
    "Viser samme periode som valgt under 'Grafer' over. Grønn = tank 1, "
    "blå/oransje = tank 2/3, gul = overføring/levering/WFE, grå = "
    "rengjøring (også veksttankenes idriftsettelsesvask helt i starten, før "
    "aller første overføring). Rødlig 'Rengjoring (kollisjon)' i tank 2/3 "
    "betyr at neste kohort ankommer FØR den konfigurerte vasketiden for "
    "veksttank rekker å bli fullført - tanken vises da bare tom så lenge det "
    "faktisk er ledig (kortere enn du har satt i sidepanelet), se "
    "'Kollisjon?'-kolonnen i kohort-sammendraget. Rull sidelengs/nedover i "
    "tabellen for å se flere uker."
)
render_calendar_illustration(sub_df)

with st.expander("Full ukekalender (enkel tabell, transponert - en rad per uke, sorterbar)"):
    st.dataframe(sub_df.T, use_container_width=True)


# ----------------------------------------------------------------------
# DOWNLOADS
# ----------------------------------------------------------------------
st.subheader("Last ned")
c1, c2 = st.columns(2)
c1.download_button(
    "Last ned full kalender (CSV)",
    df.to_csv().encode("utf-8"),
    "postsmolt_manuell.csv", "text/csv",
)

excel_buffer = io.BytesIO()
excel_max_weeks = min(104, df.shape[1])
write_excel(
    df, excel_buffer, max_weeks=excel_max_weeks,
    title=f"Postsmolt - manuell modell - {cfg.START_ISO_YEAR} og {cfg.START_ISO_YEAR + 1}",
)
excel_buffer.seek(0)
c2.download_button(
    "Last ned fargekodet Excel-kalender (år 1+2)",
    excel_buffer, "postsmolt_manuell.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
