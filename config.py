"""
config.py - postsmolt, MANUELT TIDSSTYRT, 4x RUNDER/AR-VARIANT (3 tanker)
------------------------------------------------------------------------------
Samme motor som postsmolt_manuell/ (se scheduler_manuell.py sin docstring for
den generelle forklaringen) - denne mappen er kun en ALTERNATIV default-
oppskrift, satt opp med 4 runder i aret i stedet for 3, slik at du kan
simulere begge alternativene side om side sammen med oppdretteren.

Fordi 52/4 = 13 uker gar opp jevnt, kan alle fire oppskriftene her dele
NOYAKTIG samme syklus-lengde (11 uker vekst + 2 uker vask = 13 uker per
runde, per tank) - ingen justering av vasketid trengs for a treffe 52 uker
eksakt, slik som i 3-runde-varianten. Det eneste som differensieres mellom
oppskriftene er SMOLTANTALLET, satt opp slik at hver runde bruker
veksttankenes tetthetstak (60 kg/m3) sa godt som mulig - kalde runder
(vinter/var) far dermed vesentlig flere smolt enn varme runder
(sommer/host), fordi fisken vokser tregere per uke da og du derfor kan
sette inn flere uten a sprenge taket.

Referanse (uniformt smoltantall 2 400 000, ingen differensiering - se
postsmolt_kalender/ROUNDS_PER_YEAR=4): leverer ~1 215 / 1 873 / 2 267 /
1 534 t i de fire rundene, altsa svaert ujevnt. Med differensieringen under
leverer alle fire rundene ~2 240-2 340 t hver - bade jevnere OG ca. 2 300 t
MER totalt per ar (~9 170 t/ar mot ~6 890 t/ar), fordi den ledige tetthets-
kapasiteten i de varme mandene na faktisk utnyttes i de kalde.
"""

# ----------------------------------------------------------------------
# 1. TANK / LOKALITET
# ----------------------------------------------------------------------
TANK_VOLUME_M3 = 20_500
N_GROWOUT_TANKS = 2
SPLIT_RATIOS = [0.5, 0.5]

# ----------------------------------------------------------------------
# 2. MANUELL OPPSKRIFT-ROTASJON (gjentas automatisk)
# ----------------------------------------------------------------------
START_WEIGHT_KG = 0.10             # smoltvekt ved utsett (100 g default), felles for alle oppskrifter

N_BATCHES_IN_ROTATION = 4          # antall ulike oppskrifter i rotasjonen (1-4) - 4x runder/ar

# Ett tall per oppskrift/batch (indeks 0 = batch 1, osv.). Batch 1 (satt inn
# uke 2, vokser gjennom jan-mar - de kaldeste manedene) og batch 4 (satt inn
# uke 41, vokser gjennom okt-des) far vesentlig flere smolt enn batch 2/3
# (satt inn hostvinter->var og var->sommer), for a kompensere for tregere
# vekst og utnytte tetthetstaket jevnt gjennom aret - se docstring over.
BATCH_SMOLT_COUNTS = [4_600_000, 3_000_000, 2_400_000, 3_500_000]
BATCH_TANK1_GROWTH_WEEKS = [11, 11, 11, 11]   # uker i tank 1 for splitt, per batch - likt for alle 4
BATCH_GROWOUT_WEEKS = [11, 11, 11, 11]        # uker i veksttank for salg, per batch - likt for alle 4

# Vasketid tank 1 - individuell per oppskrift (1-5 uker). Alle fire satt likt
# (2 uker) her, siden 4 x (11+2) = 52 uker allerede treffer eksakt - ingen
# behov for a flekse ulikt slik som i 3-runde-varianten.
BATCH_TANK1_CLEANING_WEEKS = [2, 2, 2, 2]

# Vasketid veksttank (tank 2/3) - ogsa individuell per oppskrift. Satt likt
# (2 uker) som tank 1-vasken over, som gir null kollisjon og null "dod tid"
# i veksttankene automatisk (fordi alle fire oppskriftene har identisk
# syklus-lengde - se docstring over).
BATCH_GROWOUT_CLEANING_WEEKS = [2, 2, 2, 2]

# ----------------------------------------------------------------------
# 3. TETTHET (kun et varselniva - modellen styrer ikke mot dette)
# ----------------------------------------------------------------------
MAX_DENSITY_KG_M3 = 60.0

# ----------------------------------------------------------------------
# 4. DODELIGHET
# ----------------------------------------------------------------------
ANNUAL_MORTALITY_PCT = 0.5

# ----------------------------------------------------------------------
# 5. VEKSTYTELSE / TEMPERATUR
# ----------------------------------------------------------------------
RGI_PCT = 100.0
TEMPERATURE_PROFILES = {
    "Konvensjonell dybde": [
        7.5, 6.2, 5.5, 6.3, 8.5, 12.0, 14.5, 15.0, 15.8, 13.5, 11.0, 9.0,
    ],
    "25 m under overflaten (lukket anlegg)": [
        7.10, 6.10, 5.50, 6.20, 8.50, 9.00, 10.00, 12.00, 12.00, 11.00, 9.00, 8.00,
    ],
}
DEFAULT_TEMPERATURE_PROFILE = "25 m under overflaten (lukket anlegg)"
MONTHLY_TEMPERATURES_C = TEMPERATURE_PROFILES[DEFAULT_TEMPERATURE_PROFILE]

# ----------------------------------------------------------------------
# 6. KALENDER
# ----------------------------------------------------------------------
START_ISO_YEAR = 2026
START_ISO_WEEK = 2
N_YEARS_TO_RUN = 3

# ----------------------------------------------------------------------
# 7. OUTPUT
# ----------------------------------------------------------------------
OUTPUT_DIR = "output"
