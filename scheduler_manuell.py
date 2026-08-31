"""
scheduler_manuell.py - postsmolt, MANUELT TIDSSTYRT (bruker-definert oppskrift)
------------------------------------------------------------------------------
Tredje variant, ved siden av postsmolt_kalender/ (fast, delt syklus, auto-
optimalisert) og postsmolt_individuell/ (individuelt tidsstyrt per kohort,
men fortsatt automatisk kappet mot et syklus-tak).

Her styrer DU alt av timing manuelt - og i stedet for ÉN "mal-kohort" som
gjentas identisk hele året, kan du definere FLERE ulike oppskrifter i en
rotasjon (typisk 3 eller 4, én per runde i året), hver med sitt eget:

  - Antall smolt satt inn i tank 1 (kompenser f.eks. for en kald
    vinter-batch ved å sette inn flere smolt der)
  - Antall uker kohorten star i tank 1 for splitt til tank 2/3
  - Antall uker kohorten star i tank 2/3 (veksttank) for salg
  - Antall uker vask av tank 1 OG antall uker vask av veksttank - begge
    individuelle per oppskrift, slik at du kan flekse timingen (bade for a
    treffe en 52-ukers "recurring" rotasjon, og for a bevisst dytte
    produksjon frem/tilbake i kalenderen per oppskrift)

Rotasjonen gjentas automatisk: oppskrift 1, 2, 3, ..., 1, 2, 3, ...

Selve LEVERINGSVEKTEN er fortsatt en beregnet STORRELSE (via samme
vekstmotor/temperaturprofil/RGI som de to andre modellene) - det er kun
TIDSPUNKTENE (og smoltantallet) som er manuelle her.

Kollisjonssjekk: fordi tank 2/3 sin syklus (GROWOUT_WEEKS + GROWOUT_CLEANING_WEEKS
for en gitt oppskrift) er UAVHENGIG av tank 1 sin syklus for NESTE oppskrift
i rotasjonen, kan brukeren definere en rotasjon som ikke gar opp - dvs. at en
ny kohort overfores fra tank 1 for forrige kohort er levert og tanken rukket
a bli vasket. Dette blokkeres IKKE (modellen regner videre - nyeste kohort
"vinner" cellen i illustrasjonen), men flagges eksplisitt per kohort
("kollisjon") og oppsummert i meta, slik at brukeren selv kan justere
oppskriftene.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import date, timedelta
import pandas as pd

from growth_tables import GrowthTables
from simulator import simulate_cohort, CohortResult
from temperature import monthly_profile


def monday_of_week(week_index: int, start_iso_year: int, start_iso_week: int) -> date:
    monday0 = date.fromisocalendar(start_iso_year, start_iso_week, 1)
    return monday0 + timedelta(weeks=week_index)


def week_label(week_index: int, start_iso_year: int, start_iso_week: int) -> tuple[str, date]:
    d = monday_of_week(week_index, start_iso_year, start_iso_week)
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-U{iso_week:02d}", d


def daily_mortality_rate(annual_pct: float) -> float:
    survival_frac = 1 - annual_pct / 100.0
    if survival_frac <= 0:
        return 1.0
    return 1 - survival_frac ** (1.0 / 365.0)


@dataclass
class Cohort:
    id: str
    tank: str
    start_week: int
    n_weeks: int
    result: CohortResult
    weekly_biomass_kg: list
    weekly_weight_kg: list


def build_manual_schedule(cfg, growth_tables: GrowthTables | None = None):
    """
    Returns (weekly_df, generations, meta) - samme grensesnitt som de to
    andre schedulerne.

    cfg ma ha: TANK_VOLUME_M3, N_GROWOUT_TANKS, SPLIT_RATIOS, START_WEIGHT_KG,
    N_BATCHES_IN_ROTATION, BATCH_SMOLT_COUNTS (liste, lengde >= N_BATCHES_IN_ROTATION),
    BATCH_TANK1_GROWTH_WEEKS (liste), BATCH_GROWOUT_WEEKS (liste),
    BATCH_TANK1_CLEANING_WEEKS (liste - vasketid FOR TANK 1, individuell per
    oppskrift, slik at du kan flekse rotasjonen til a treffe akkurat 52 uker
    for en "recurring" arlig produksjonsplan), BATCH_GROWOUT_CLEANING_WEEKS
    (liste - vasketid for VEKSTTANK, ogsa individuell per oppskrift, slik at
    du kan dytte produksjonen i tid per oppskrift uten a miste fleksibilitet),
    MAX_DENSITY_KG_M3, ANNUAL_MORTALITY_PCT, RGI_PCT, MONTHLY_TEMPERATURES_C,
    START_ISO_YEAR, START_ISO_WEEK, N_YEARS_TO_RUN.
    """
    gt = growth_tables or GrowthTables(fcr_csv="data/fcr_table.csv", sgr_csv="data/sgr_table.csv")
    temp_fn = monthly_profile(cfg.MONTHLY_TEMPERATURES_C)
    daily_mort = daily_mortality_rate(cfg.ANNUAL_MORTALITY_PCT)

    n_batches = max(1, int(cfg.N_BATCHES_IN_ROTATION))
    smolt_list = [int(c) for c in cfg.BATCH_SMOLT_COUNTS[:n_batches]]
    growth_weeks_list = [max(1, int(w)) for w in cfg.BATCH_TANK1_GROWTH_WEEKS[:n_batches]]
    growout_weeks_list = [max(1, int(w)) for w in cfg.BATCH_GROWOUT_WEEKS[:n_batches]]
    tank1_cleaning_list = [max(0, int(w)) for w in cfg.BATCH_TANK1_CLEANING_WEEKS[:n_batches]]
    growout_cleaning_list = [max(0, int(w)) for w in cfg.BATCH_GROWOUT_CLEANING_WEEKS[:n_batches]]

    n_weeks_total = (
        cfg.N_YEARS_TO_RUN * 52 + max(growth_weeks_list) + max(growout_weeks_list)
        + max(tank1_cleaning_list) + max(growout_cleaning_list) + 4
    )

    def simulate_growth(start_weight_kg, stocked_count, n_wk, start_week_idx):
        start_date = monday_of_week(start_week_idx, cfg.START_ISO_YEAR, cfg.START_ISO_WEEK)
        res = simulate_cohort(
            gt, start_weight_kg, stocked_count=stocked_count, duration_days=n_wk * 7,
            mortality_profile_fn=lambda d: daily_mort, start_date=start_date,
            temp_profile_fn=temp_fn, rgi_pct=cfg.RGI_PCT,
        )
        weekly_biomass, weekly_weight = [], []
        for wk in range(n_wk):
            day_idx = wk * 7 + 6
            row = res.daily.iloc[min(day_idx, len(res.daily) - 1)]
            weekly_biomass.append(row["biomass_kg"])
            weekly_weight.append(row["weight_kg"])
        return res, weekly_biomass, weekly_weight

    generations = {}
    cohorts: list[Cohort] = []

    gen_n = 0
    w = 0
    while True:
        batch_idx = gen_n % n_batches
        growth_w = growth_weeks_list[batch_idx]
        growout_w = growout_weeks_list[batch_idx]
        if w + growth_w + growout_w > n_weeks_total:
            break

        gen_n += 1
        gid = f"G{gen_n}"
        stocked_tank1 = smolt_list[batch_idx]

        # ---- Tank 1: nursery-fase, manuell varighet/smoltantall for denne oppskriften ----
        res1, wb1, ww1 = simulate_growth(cfg.START_WEIGHT_KG, stocked_tank1, growth_w, w)
        cohorts.append(Cohort(gid, "tank1", w, growth_w, res1, wb1, ww1))

        transfer_week = w + growth_w
        split_weight = res1.target_weight_kg
        survivors = res1.surviving_count
        tank1_density_kg_m3 = res1.final_biomass_kg / cfg.TANK_VOLUME_M3

        # ---- Tank 2 / tank 3: growout-fase, manuell varighet for denne oppskriften ----
        growout_infos = []
        for i, ratio in enumerate(cfg.SPLIT_RATIOS[:cfg.N_GROWOUT_TANKS]):
            tank_name = f"tank{i + 2}"
            stocked_i = round(survivors * ratio)
            if transfer_week + growout_w > n_weeks_total:
                break
            res_i, wb_i, ww_i = simulate_growth(split_weight, stocked_i, growout_w, transfer_week)
            cohorts.append(Cohort(gid, tank_name, transfer_week, growout_w, res_i, wb_i, ww_i))
            growout_infos.append(res_i)

        delivery_week = transfer_week + growout_w - 1
        delivered_biomass_kg = sum(r.final_biomass_kg for r in growout_infos)
        growout_density_kg_m3 = (
            max(r.final_biomass_kg for r in growout_infos) / cfg.TANK_VOLUME_M3
            if growout_infos else 0.0
        )

        # ---- Tetthetssjekk (advarsel - smolt-antall og timing er fast/manuelt) ----
        max_density_this_gen = max(tank1_density_kg_m3, growout_density_kg_m3)
        tetthet_over_tak = max_density_this_gen > cfg.MAX_DENSITY_KG_M3

        # ---- Kollisjonssjekk: rekker veksttankene a bli levert + vasket for
        # neste overforing (fra neste kohort i rotasjonen) kommer? ----
        tank1_cleaning_this = tank1_cleaning_list[batch_idx]
        growout_cleaning_this = growout_cleaning_list[batch_idx]
        next_batch_idx = (batch_idx + 1) % n_batches
        next_growth_w = growth_weeks_list[next_batch_idx]
        w_next = w + growth_w + tank1_cleaning_this
        next_transfer_week = w_next + next_growth_w
        growout_free_week = delivery_week + 1 + growout_cleaning_this
        kollisjon_denne = next_transfer_week < growout_free_week

        generations[gid] = {
            "tank1_start_week": w,
            "transfer_week": transfer_week,
            "delivery_week": delivery_week,
            "batch": batch_idx + 1,
            "tank1_growth_weeks": growth_w,
            "growout_weeks": growout_w,
            "tank1_cleaning_weeks": tank1_cleaning_this,
            "growout_cleaning_weeks": growout_cleaning_this,
            "stocked_tank1": stocked_tank1,
            "split_weight_kg": split_weight,
            "survivors_at_transfer": survivors,
            "growout_final_weight_kg": growout_infos[0].target_weight_kg if growout_infos else None,
            "delivered_biomass_kg": delivered_biomass_kg,
            "max_density_kg_m3": max_density_this_gen,
            "tetthet_over_tak": tetthet_over_tak,
            "kollisjon": kollisjon_denne,
        }

        w = w_next

    kollisjon_i_oppskriften = any(info["kollisjon"] for info in generations.values())

    # Full rotasjon (tank 1): summen av vekst + vask for alle oppskriftene i
    # rotasjonen. For en "recurring" arlig produksjonsplan (samme kalenderuker
    # hvert ar) bor dette treffe akkurat 52 uker.
    full_rotasjon_uker = sum(growth_weeks_list[i] + tank1_cleaning_list[i] for i in range(n_batches))

    weekly_df = _assemble_wide_table(cfg, cohorts, generations, n_weeks_total)
    return weekly_df, generations, {
        "n_batches_in_rotation": n_batches,
        "batch_smolt_counts": smolt_list,
        "batch_tank1_growth_weeks": growth_weeks_list,
        "batch_growout_weeks": growout_weeks_list,
        "batch_tank1_cleaning_weeks": tank1_cleaning_list,
        "batch_growout_cleaning_weeks": growout_cleaning_list,
        "full_rotasjon_uker": full_rotasjon_uker,
        "kollisjon_i_oppskriften": kollisjon_i_oppskriften,
    }


def _assemble_wide_table(cfg, cohorts, generations, n_weeks_total):
    labels, dates = [], []
    for w in range(n_weeks_total):
        lbl, d = week_label(w, cfg.START_ISO_YEAR, cfg.START_ISO_WEEK)
        labels.append(lbl)
        dates.append(d)

    tanks = {"tank1": {}, "tank2": {}, "tank3": {}}
    for c in cohorts:
        for i in range(c.n_weeks):
            wk = c.start_week + i
            if wk >= n_weeks_total:
                break
            tanks[c.tank][wk] = {
                "kohort": c.id, "status": "Vekst",
                "biomasse_t": c.weekly_biomass_kg[i] / 1000.0,
                "vekt_kg": c.weekly_weight_kg[i],
            }

    for gid, info in generations.items():
        tw = info["transfer_week"]
        for k in range(info["tank1_cleaning_weeks"]):
            wk = tw + k
            if wk < n_weeks_total and wk not in tanks["tank1"]:
                # kohort-feltet merkes med hvilken kohort som nettopp forlot
                # tanken (f.eks. "G2"), sa det alltid er entydig hvilken
                # oppskrifts vasketid som vises - ogsa nar vasken strekker
                # seg inn i uker som ellers ville sett "tomme" ut.
                tanks["tank1"][wk] = {"kohort": f"({gid})", "status": "Rengjoring", "biomasse_t": 0.0, "vekt_kg": None}

    # ---- Veksttank (tank 2/3): fyll HELE gapet mellom levering og neste
    # overføring med "Rengjoring" - ikke bare de konfigurerte
    # (individuelle, per-oppskrift) vasketid-ukene. Fordi tank 1 sin rytme
    # (som styrer nar neste kohort faktisk ankommer) er uavhengig av det
    # tallet, kan gapet bli lengre enn konfigurert vasketid - resten av
    # gapet er fortsatt en tank som star tom/vasket, ikke en egen "ledig,
    # ingenting skjer"-tilstand, sa det vises som fortsatt Rengjoring i
    # illustrasjonen. Den konfigurerte vasketiden brukes fortsatt som
    # MINSTEKRAV i kollisjonssjekken.
    sorted_gens = sorted(generations.items(), key=lambda kv: kv[1]["transfer_week"])
    for idx, (gid, info) in enumerate(sorted_gens):
        dw = info["delivery_week"]
        planned_clean_end = dw + 1 + info["growout_cleaning_weeks"]
        if idx + 1 < len(sorted_gens):
            next_transfer = sorted_gens[idx + 1][1]["transfer_week"]
            clean_end = max(dw + 1, next_transfer)
            # Kollisjon: den faktiske ledige tiden er kortere enn den
            # konfigurerte vasketiden for veksttank - marker cellene tydelig
            # forskjellig fra en normal, fullført vask.
            forkortet = next_transfer < planned_clean_end
        else:
            clean_end = planned_clean_end
            forkortet = False
        status_label = "Rengjoring (kollisjon)" if forkortet else "Rengjoring"
        # kohort-feltet merkes med hvilken kohort som nettopp ble levert fra
        # akkurat denne tanken (f.eks. "G2") - viktig fordi vaskeblokken ofte
        # star rett FORAN neste kohort (f.eks. "G3") i tabellen, og uten
        # denne merkingen er det lett a tro vasken tilhorer den kommende
        # kohorten/oppskriften i stedet for den som nettopp dro.
        kohort_lbl = f"({gid})"
        for tname in ("tank2", "tank3"):
            for wk in range(dw + 1, clean_end):
                if wk < n_weeks_total and wk not in tanks[tname]:
                    tanks[tname][wk] = {"kohort": kohort_lbl, "status": status_label, "biomasse_t": 0.0, "vekt_kg": None}

    # ---- Idriftsettelsesvask: fyll ogsa veksttankenes ALLER FØRSTE bruk med
    # "Rengjoring" rett før første overføring - selv om det ikke fantes noen
    # forrige kohort å vaske bort etter, klargjøres en ny tank likevel før
    # det tas i bruk, akkurat som mellom alle senere runder. Bruker samme
    # vasketid som er konfigurert for den FØRSTE oppskriften i rotasjonen.
    if sorted_gens:
        first_gid, first_info = sorted_gens[0]
        first_transfer = first_info["transfer_week"]
        commissioning_start = max(0, first_transfer - first_info["growout_cleaning_weeks"])
        kohort_lbl = f"(→{first_gid})"  # ingen kohort dro fra tanken - vask FOR forste ankomst
        for tname in ("tank2", "tank3"):
            for wk in range(commissioning_start, first_transfer):
                if wk < n_weeks_total and wk not in tanks[tname]:
                    tanks[tname][wk] = {"kohort": kohort_lbl, "status": "Rengjoring", "biomasse_t": 0.0, "vekt_kg": None}

    overforing_row, levering_row, levert_wfe_row = {}, {}, {}
    for gid, info in generations.items():
        overforing_row[info["transfer_week"]] = gid
        levering_row[info["delivery_week"]] = gid
        levert_wfe_row[info["delivery_week"]] = info["delivered_biomass_kg"] / 1000.0

    rows = []

    kalenderuke = {"felt": "Kalenderuke", **dict(zip(labels, labels))}
    dato_row = {"felt": "Dato", **{lbl: d.isoformat() for lbl, d in zip(labels, dates)}}
    rows += [kalenderuke, dato_row]

    for tname, tlabel in [("tank1", "Tank 1"), ("tank2", "Tank 2"), ("tank3", "Tank 3")]:
        koh = {"felt": f"{tlabel} - kohort"}
        stat = {"felt": f"{tlabel} - status"}
        bio = {"felt": f"{tlabel} - biomasse (t)"}
        dens = {"felt": f"{tlabel} - tetthet (kg/m3)"}
        vekt = {"felt": f"{tlabel} - vekt (g)"}
        for wk, lbl in enumerate(labels):
            cell = tanks[tname].get(wk)
            if cell is None:
                koh[lbl], stat[lbl], bio[lbl] = "", "Ledig", 0.0
                # None (ikke "") her, slik at "...- vekt (g)"-raden forblir en
                # ren tallkolonne (float/NaN) og ikke blander str og float -
                # en blandet "object"-kolonne feiler i Streamlit sin
                # dataframe->Arrow-konvertering (st.dataframe) med
                # "ArrowInvalid: Could not convert '' with type str".
                dens[lbl], vekt[lbl] = 0.0, None
            else:
                koh[lbl], stat[lbl], bio[lbl] = cell["kohort"], cell["status"], round(cell["biomasse_t"], 1)
                dens[lbl] = round(cell["biomasse_t"] * 1000 / cfg.TANK_VOLUME_M3, 1)
                vekt[lbl] = round(cell["vekt_kg"] * 1000, 1) if cell["vekt_kg"] is not None else None
        rows += [koh, stat, bio, dens, vekt]

    overf = {"felt": "Overforing"}
    lev = {"felt": "Levering"}
    wfe = {"felt": "Levert WFE (t)"}
    akk = {"felt": "Akkumulert i aret (t)"}
    cum = 0.0
    cum_year = None
    for wk, lbl in enumerate(labels):
        overf[lbl] = overforing_row.get(wk, "")
        lev[lbl] = levering_row.get(wk, "")
        wfe_val = round(levert_wfe_row.get(wk, 0.0), 1)
        wfe[lbl] = wfe_val
        iso_year = dates[wk].isocalendar()[0]
        if iso_year != cum_year:
            cum_year = iso_year
            cum = 0.0
        cum += levert_wfe_row.get(wk, 0.0)
        akk[lbl] = round(cum, 1)
    rows += [overf, lev, wfe, akk]

    return pd.DataFrame(rows).set_index("felt")
