# CLAUDE.md — Smart Parking (master rad, Norfolk)

## Šta je ovo

Praktični deo **master rada** (Elektronski fakultet u Nišu, mentor prof. Petar
Rajković): sistem za **preporuku parking mesta u pametnim gradovima** na osnovu
predikcije zauzetosti, nad realnim podacima za 15 parkinga u Norfolku (Norwich, UK),
~13 meseci merenja. Projekat je počeo kao seminarski proof-of-concept na Birmingham
podacima. Taj deo je zamenjen i opisan je samo kao istorija na dnu `README.md`.

Ceo lanac radi end-to-end: **podaci → predikcija → pseudo real-time simulator →
preporuka → mapa**. Sistem radi tri stvari:
1. **Praćenje popunjenosti.** Simulator (`ReplaySource` + `SimulationClock`) pušta
   istorijske podatke hronološki, kao da stižu uživo, i nikad ne otkriva budućnost.
2. **Predviđanje dostupnosti.** Jedan XGBoost model predviđa zauzetost za bilo koji
   horizont od 30 min do 15,5 h (horizont je ulazna promenljiva).
3. **Preporuka lokacije.** Parkinzi se rangiraju po ponderisanom skoru (predviđena
   dostupnost pri dolasku, blizina destinaciji, saobraćaj).

**Ključni princip: predikcija i preporuka su ODVOJENI moduli.** Predikcija je ML
zadatak. Preporuka je rangiranje po ponderisanom skoru i NE koristi neuronsku mrežu.

## Dokumenti (pročitaj pre rada)

| Fajl | Šta je u njemu |
|---|---|
| `../MASTER_PLAN.md` | zahtevi profesora, podaci, model, koordinate, mapa (van repoa) |
| `../PLAN_ZAVRSETKA.md` | preostali koraci do kraja rada, sa štikliranjem (van repoa) |
| `../ZA_MENTORA.md` | otvorena pitanja za mentora (npr. saobraćaj) (van repoa) |
| `PROGRESS.md` | log urađenog po fazama i koracima, svi rezultati eksperimenata |
| `README.md` | arhitektura, instalacija, pokretanje, API, ograničenja |
| `frontend/AGENTS.md` | Next.js u ovom projektu ima breaking changes; pročitati pre izmena frontenda |

## Način rada

- **Korak po korak iz `../PLAN_ZAVRSETKA.md`.** Na kraju koraka: provera da radi, upis
  u `PROGRESS.md`, commit na granu `master-rad`, štikliranje u planu. Stani i pokaži
  rezultat; sledeći korak tek uz potvrdu. Ne raditi više koraka u jednom naletu.
- Targetirane, minimalne izmene. Ne diraj delove koji već rade.
- Kod treba da bude čitljiv i objašnjiv, jer ide u master rad.
- **Pošteno merenje:**
  - podela je uvek hronološka, nikad nasumična;
  - model se trenira samo na podacima pre 1.10.2017;
  - simulator i predikcija vide samo prošlost.

  Kada se neki navod u radu pokaže netačnim, ispravi ga u `PROGRESS.md`, ne briši ga
  tiho.

## Tehnološki stack

| Sloj | Tehnologija |
|---|---|
| Podaci + ML | Python 3.12, pandas, XGBoost, scikit-learn (poređenje modela), joblib, matplotlib (grafici za rad) |
| Backend / API | Python, FastAPI, uvicorn |
| Frontend | Next.js (App Router), Leaflet (react-leaflet), čist SVG za grafikone |

Backend i frontend komuniciraju preko REST (JSON).

## Struktura projekta

```
smart-parking/
├── CLAUDE.md, README.md, PROGRESS.md
├── requirements.txt, package.json     # Python zavisnosti; npm prečice (backend/frontend)
├── data/
│   ├── carparks_norfolk.json          # ime/tip/koordinate za svih 15 parkinga (iz NCC feeda)
│   └── parking.csv, park_coordinates.json   # stari Birmingham PoC (istorija)
├── ml/
│   ├── data_prep.py                   # priprema podataka (konfigurabilno po gradu)
│   ├── train_norfolk.py               # trening jednog modela → model_norfolk.joblib
│   ├── eval_recommender.py            # korak 3: evaluacija preporuke (simulirani vozači)
│   ├── compare_models.py              # korak 4: poređenje modela i baseline-ova
│   ├── analyze_model.py               # korak 5: SHAP, ablacija, greške, nedostajući podaci
│   ├── output/                        # CSV i PNG rezultati (idu u rad)
│   └── explore.py, train.py, model.joblib   # stari Birmingham PoC (istorija)
├── backend/
│   ├── main.py                        # FastAPI app, endpointi
│   ├── datasource.py                  # DataSource / ReplaySource / LiveSource (stub)
│   ├── simulator.py                   # SimulationClock (pseudo real-time sat)
│   ├── predictor.py                   # feature-i iz apsolutnog vremena, predikcija
│   ├── recommender.py                 # ponderisano rangiranje
│   └── parks.py                       # spisak parkinga (kapacitet iz CSV-a, koordinate iz JSON-a)
├── frontend/app/                      # page.tsx, ParkingMap.tsx, Sparkline.tsx, CompareChart.tsx
└── docs/seminarski-rad/               # seminarski rad (prethodnik, istorija)
```

## Podaci

- `../data/raw/Norfolk.csv` (van repoa, deljen sa ostatkom master projekta). **Koristi
  ga; ne generiši sintetičke podatke.** Izvor: Stolfi, Alba, Yao (2020), UK Open
  Government Licence (link u `../MASTER_PLAN.md`, poglavlje 3).
- Kolone: `SystemCodeNumber` (čitati kao string), `Capacity`, `Occupancy`, `LastUpdated`.
- Upotrebljivo je 15 parkinga (isključeni `CPN0001`, `CPN0002`, `CPN0010`). Period je
  26.10.2016 – 5.12.2017, merenja 08:00–23:00.
- Priprema: `rate = clip(Occupancy/Capacity, 0, 1)`, resample na pravilnu mrežu od
  30 min. Rupe se ne popunjavaju.
- Trening je pre 1.10.2017, a test 1.10.–5.12.2017 (`CITY_CONFIGS` u `ml/data_prep.py`).
- Imena, tipovi (grad / Park & Ride / ostalo) i koordinate svih 15 parkinga su u
  `data/carparks_norfolk.json`, iz zvaničnog Norfolk County Council feeda (arhiviran na
  Wayback Machine-u; obrazloženje u `README.md`). **Ne izmišljati koordinate:** parking
  bez koordinata ne ide na mapu ni u preporuku.

## Model, preporuka, evaluacija (sažetak; brojevi u `PROGRESS.md`)

- **Model:** `y_t, y_t1, y_t2, delta, y_yesterday, y_lastweek, hour, dow, weekend,
  holiday, carpark, capacity, horizon_minutes`. Greška je MAE 4,83 p.p. ukupno, a
  2,87 na 30 min. Kad `y_lastweek` fali, `backend/predictor.py` uzima isti termin
  14 dana ranije.
- **Preporuka:** `skor = w1·dostupnost + w2·blizina_destinaciji − w3·saobraćaj`
  (`backend/recommender.py`). Ponderi su konstante na vrhu fajla (0.55/0.3/0.15).
  Dostupnost se računa za procenjeno vreme dolaska. Bodovanje je u čistoj funkciji
  `score_candidates()`, koju koriste i API i evaluacija.
- **Saobraćaj (w3):** dataset ga nema. Trenutna heuristika ne meri saobraćaj (vidi
  `../ZA_MENTORA.md`, 3.1). Odluka čeka mentora (korak 6), pa do tada ne menjati.
- **Evaluacija:** `ml/eval_recommender.py` (~7 min), `ml/compare_models.py` (~3 min),
  `ml/analyze_model.py` (~10 min). Izlazi su u `ml/output/`. Posle izmene prediktora
  ili preporuke ponovo pokrenuti evaluaciju i ažurirati brojeve u `PROGRESS.md`.

## Šta NE raditi

- Ne generisati sintetičke podatke i ne izmišljati koordinate.
- Ne koristiti CNN, jer je pogrešan alat za tabelarne podatke. LSTM/GRU dolazi u obzir
  samo kao opciono poređenje.
- Ne dodavati bazu, auth, Docker ni testove, osim ako se izričito traži.
- Ne raditi više koraka plana u jednom naletu.
- Ne komplikovati frontend; minimalni UI je namerno izabran.
- Ne raditi na `main` grani; rad ide na `master-rad`.
