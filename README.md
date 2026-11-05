# Smart Parking Recommendation — Norfolk (master rad)

Sistem za **preporuku parking mesta u pametnim gradovima**, master rad na Elektronskom
fakultetu u Nišu. Pokriva ceo lanac end-to-end: **podaci → predikcija zauzetosti →
pseudo real-time simulator → preporuka parkinga → prikaz na mapi**, nad realnim
podacima o 15 parkinga u Norfolku (Norwich), ~13 meseci merenja (okt 2016 – dec 2017).

Ovo poglavlje opisuje **trenutno stanje sistema**. Istoriju razvoja po fazama, sve
odluke i rezultate eksperimenata vidi u `PROGRESS.md`. Zahtevi profesora su u
`../MASTER_PLAN.md`, a preostali koraci do kraja rada u `../PLAN_ZAVRSETKA.md` (oba
van ovog repoa, u folderu master rada). Stari seminarski rad (Birmingham PoC), koji je
ovome prethodio, zamenjen je i opisan je samo kao istorija na dnu ovog fajla.

Ključni princip: **predikcija i preporuka su odvojeni moduli**. Predikcija je ML zadatak
(XGBoost). Preporuka je ponderisano rangiranje — namerno ne koristi neuronsku mrežu,
jer transparentnost (koji faktor je koliko doprineo) ima prednost nad "pametnim"
rešenjem.

## Arhitektura

```
Norfolk CSV (data/raw/Norfolk.csv, van ovog repoa)
        │
        ▼
ml/data_prep.py + ml/train_norfolk.py  →  ml/model_norfolk.joblib
        │                                   (1 XGBoost model, horizont = ulazna promenljiva)
        ▼
backend/datasource.py (ReplaySource)  →  backend/simulator.py (SimulationClock)
        │  reprodukuje CSV hronološki,        pseudo real-time sat: tick 30 min,
        │  nikad ne otkriva budućnost         podesiva brzina, start/pauza
        ▼
backend/predictor.py (predikcija za bilo koje vreme na 30-min mreži)
        │
        ▼
backend/recommender.py (ponderisano rangiranje: dostupnost + blizina − saobraćaj)
        │
        ▼
FastAPI (backend/main.py)  →  frontend (Next.js + Leaflet, polling na 3s)
```

## Tehnološki stack

| Sloj | Tehnologija |
|---|---|
| Podaci + ML | Python 3.12, pandas, XGBoost, joblib; scikit-learn i matplotlib za eksperimente i grafike |
| Backend / API | Python, FastAPI, uvicorn |
| Frontend | Next.js (App Router), Leaflet (react-leaflet), čist SVG za grafikone (bez chart biblioteke) |

## Struktura projekta

```
smart-parking/
├── CLAUDE.md, README.md, PROGRESS.md  # uputstvo za rad, ovaj opis, log po fazama/koracima
├── requirements.txt, package.json     # Python zavisnosti; npm prečice (backend/frontend)
├── run.py                             # alternativa za pokretanje backenda (python run.py)
├── data/
│   ├── carparks_norfolk.json          # ime/tip/koordinate za svih 15 parkinga (iz NCC feeda)
│   └── parking.csv, park_coordinates.json  # stari Birmingham PoC - vidi dno fajla
├── ml/
│   ├── data_prep.py                   # priprema podataka (konfigurabilno po gradu)
│   ├── train_norfolk.py               # trening jednog modela, bilo koji horizont
│   ├── model_norfolk.joblib           # sačuvan model (generiše train_norfolk.py)
│   ├── eval_recommender.py            # evaluacija preporuke simulacijom vozača
│   ├── compare_models.py              # poređenje modela i baseline-ova
│   ├── analyze_model.py               # analiza modela (SHAP, ablacija, greške, rupe)
│   ├── output/                        # metrike, tabele i grafici (CSV/PNG) za rad
│   └── explore.py, train.py, model.joblib  # stari Birmingham PoC - vidi dno fajla
├── backend/
│   ├── main.py                        # FastAPI app, endpointi
│   ├── datasource.py                  # DataSource / ReplaySource / LiveSource(stub)
│   ├── simulator.py                   # SimulationClock (pseudo real-time sat)
│   ├── predictor.py                   # feature-i iz apsolutnog vremena, predikcija
│   ├── recommender.py                 # ponderisano rangiranje
│   └── parks.py                       # spisak Norfolk parkinga (koordinate + kapacitet)
├── frontend/app/
│   ├── page.tsx                       # glavna stranica - simulacija, vreme, ruta, preporuke, demo
│   ├── ParkingMap.tsx                 # Leaflet mapa, markeri, popup
│   ├── Sparkline.tsx                  # mini grafik (tipično/stvarno/prognoza)
│   └── CompareChart.tsx               # grafik „predikcija vs stvarnost” za ceo dan
└── docs/seminarski-rad/               # seminarski rad (prethodnik, istorija)
```

Van repoa, u folderu master rada (`../`): `MASTER_PLAN.md`, `PLAN_ZAVRSETKA.md`,
`data/raw/*.csv` (podaci) i `reference/norfolk_xgb_eksperiment.py` (referentni
eksperiment sa posebnim modelom po horizontu).

## Podaci

Norfolk (Norwich), UK Open Government Licence (Stolfi, Alba, Yao 2020) - CSV je van ovog
repoa, u `../data/raw/Norfolk.csv` (deljen sa ostatkom master projekta). 15 upotrebljivih
parkinga (3 isključena, zaglavljeni senzori), period 26.10.2016–5.12.2017, merenja na
~10-15 min između 08:00 i 23:00, resample-ovano na 30-min mrežu. Detalji i kriterijumi
čišćenja su u `../MASTER_PLAN.md`, poglavlje 3. Izvor CSV-a:
https://gitlab.com/dhstolfi/predicting-car-park-occupancy-rates-in-smart-cities (fajl
`Norfolk.csv` staviti u `../data/raw/`).

## Instalacija

Potrebni su Python 3.12+, Node.js i `../data/raw/Norfolk.csv` (vidi „Podaci”).
Istrenirani model (`ml/model_norfolk.joblib`) je u repou, pa trening nije potreban
za pokretanje aplikacije.

```bash
cd smart-parking
pip install -r requirements.txt   # backend + ML
cd frontend && npm install        # frontend (jednom)
```

## Pokretanje

Dva terminala, oba iz `smart-parking/`:

```bash
# Terminal 1 - backend
npm run backend
# (isto sto i: uvicorn backend.main:app --reload)

# Terminal 2 - frontend
npm run frontend
# (isto sto i: cd frontend && npm run dev)
```

Otvoriti `http://localhost:3000`. Simulacija kreće pauzirana na 1.10.2017 08:00 (početak
test perioda). Klikni **Start** u panelu „Simulacija” ili preko „Skok na datum (test
period)” izaberi bilo koji dan iz test perioda.

## Model (`ml/`)

Jedan XGBoost model kome je **horizont** (`horizon_minutes`) obična ulazna promenljiva,
ne poseban model po horizontu - ume da predvidi zauzetost za bilo koji trenutak na
30-min mreži, od 30 min do ~15.5h unapred (pokriva ceo radni dan parkinga). Feature-i:
`y_t, y_t1, y_t2, delta, y_yesterday, y_lastweek, hour, dow, weekend, holiday, carpark,
capacity, horizon_minutes` (poglavlje 4, MASTER_PLAN.md).

```bash
python ml/train_norfolk.py
```

Rezultati (MAE u p.p., test 1.10–5.12.2017):

| Horizont | MAE | RMSE |
|---|---|---|
| 30 min | 2.87 | 4.52 |
| 1 sat | 3.45 | 5.55 |
| 2 sata | 4.29 | 6.97 |

Ovo je nešto slabije od specijalizovanog modela po horizontu, što je cena
fleksibilnosti za bilo koji horizont. `../reference/norfolk_xgb_eksperiment.py`, kao i
`ml/analyze_model.py specijalizovani`, pokazuje gornju granicu tačnosti: zaseban model
po horizontu daje 1.63 / 2.62 / 3.86 za ista tri horizonta. Zašto je dizajn promenjen sa
3 fiksna horizonta na kontinualan opseg: vidi `PROGRESS.md`, sekcija „Redizajn -
proizvoljan horizont”.

Ako nema merenja u istom terminu pre 7 dana (`y_lastweek`), `backend/predictor.py`
koristi isti termin 14 dana ranije, bez ponovnog treniranja. Vidi „Evaluacija i
analiza” ispod.

## Evaluacija i analiza (`ml/`)

Svi eksperimenti koriste istu hronološku podelu (trening pre 1.10.2017, test
1.10.–5.12.2017). Rezultati (CSV i PNG) idu u `ml/output/`, a brojevi i zaključci u
`PROGRESS.md` (koraci 3–5).

```bash
python ml/eval_recommender.py   # ~7 min: preporuka na 2000 simuliranih vozača (najbliži / naivna / XGBoost / savršena prognoza)
python ml/compare_models.py     # ~3 min: XGBoost naspram Random Forest, HistGradientBoosting, Ridge i baseline-ova
python ml/analyze_model.py      # ~10 min: SHAP, ablacija, greška po parkingu/dobu dana, nedostajući podaci, dužina treninga
```

Ukratko:
- Bez sistema (najbliži parking) vozač stiže na pun parking u 19,3% slučajeva. Sa
  preporukom je to 0% (svi parkinzi), odnosno 2,6% (samo gradski). Kandidata za
  preporuku je 14 (8 gradskih i 6 Park & Ride), a B&Q Boundary Road je samo na mapi.
- XGBoost ima najmanju grešku: MAE 4,83 p.p. ukupno, 2,87 na 30 min.
- Za kratke prognoze presudna je trenutna zauzetost, a za duge stanje u isto vreme
  juče i pre nedelju dana.

## Backend / API (`backend/`)

Simulator (`datasource.py` + `simulator.py`) reprodukuje CSV hronološkim redom -
`ReplaySource.history_until(park_id, until)` nikad ne otkriva podatke sa vremenom >
`until`, pa model u svakom trenutku "zna" samo prošlost, kao pravi uživo sistem. Model
se trenira samo na podacima pre 1.10.2017; simulacija ide kroz test period.

| Endpoint | Opis |
|---|---|
| `GET /parks` | Lista Norfolk parkinga (koordinate, kapacitet, tip, potvrđeno) |
| `GET /simulation/state` | Simulirano vreme, da li sat radi, brzina |
| `POST /simulation/start?start_time=&speed=` | Pokreće sat (oba parametra opciona) |
| `POST /simulation/pause` | Pauzira sat |
| `POST /simulation/speed?factor=` | Menja brzinu (sim-minuta po stvarnoj sekundi) |
| `GET /state?park_id=&target_time=` | Trenutna zauzetost; sa `target_time` (ISO) i zauzetost za to vreme - izmereno ako je prošlost/sadašnjost, predikcija (+MAE) ako je budućnost (do ~15.5h, posle toga clamp) |
| `GET /history?park_id=` | Tipična kriva za dan u nedelji (iz treninga) + stvarni tok danas (za sparkline) |
| `GET /recommend?origin_lat=&origin_lng=&dest_lat=&dest_lng=&top_n=&radius=&departure_time=` | Rangirana lista preporuka; `departure_time` opcioni (podrazumevano "sada") |
| `POST /simulation/reset?start_time=` | Demo: skok na bilo koje vreme u test periodu (zaokruženo na 30 min); sat se pauzira |
| `GET /compare?park_id=&date=&from_time=` | Demo: za dan iz test perioda vraća stvarnu zauzetost, prognozu iz `from_time` do kraja dana, prognozu „sat unapred” i tipičnu krivu, uz MAE |

```bash
curl -X POST "http://127.0.0.1:8000/simulation/start?speed=100"
curl "http://127.0.0.1:8000/state?target_time=2017-10-10T17:00:00"
```

**Preporuka** (`recommender.py`): `skor = w1·dostupnost + w2·blizina − w3·vreme_vožnje`
(w1=0.55, w2=0.3, w3=0.15, konstante na vrhu fajla). `blizina` meri hodanje od parkinga
do destinacije, a `vreme_vožnje` vožnju od polaska do parkinga, odnosno trošak dolaska
do parkinga. Obe su normalizovane na 0–1 u odnosu na najudaljenijeg kandidata. Vreme
vožnje se procenjuje po pravoj liniji pri 30 km/h. Ista procena daje i vreme dolaska,
koje se računa od `departure_time` ako je dat, inače od simuliranog „sada”, i za njega
se pravi predikcija. Do 5.11.2026. treći član je bio heuristika „saobraćaj”, koja
zapravo nije merila saobraćaj; zamenjena je po odluci mentora (vidi „Ograničenja” i
`PROGRESS.md`). Preporučuju se samo parkinzi tipa „grad” i „Park & Ride”
(`RECOMMENDABLE_TYPES`).

## Frontend (`frontend/app/`)

- Jedan padajući meni **"Vreme (mapa i polazak)"**: "Sada" + 48 opcija na 30-min mreži
  (00:00–23:30, ista mreža kao merenja senzora). Ista vrednost pokreće i boje markera na
  mapi (`/state?target_time=`) i preporuku (`/recommend?departure_time=`).
- Markeri obojeni po statusu zauzetosti (zeleno &lt;50%, žuto 50–80%, crveno &gt;80%,
  sivo = nema očitavanja). Preporučeni parkinzi dobijaju ljubičasti prsten + broj ranga.
- Popup po parkingu: zauzetost za izabrano vreme, jasno obeležena **"(izmereno)"** ili
  **"(predikcija)"**, slobodna mesta, MAE ("pouzdanost") za predikcije, i sparkline
  (tipična kriva za dan u nedelji + stvarni tok do sada + tačka prognoze), učitan tek
  kad se popup otvori.
- Panel "Simulacija": simulirano vreme, Start/Pauza, brzina.
- Klik na mapu bira prvo početnu tačku pa destinaciju; OSRM (javni demo server) crta
  rutu; panel "Parkinzi uz rutu" i "Top preporuke za cilj" sa desne strane.
- Klik na mapu kad je ruta već izabrana ne briše je odmah - traži potvrdu (modal), da
  slučajan klik u vozilu ne izgubi već izračunatu rutu.
- **Demo režim** (za odbranu):
  - **„Skok na datum (test period)”** postavlja simulaciju na bilo koji dan i sat iz
    perioda koji model nije video.
  - Kartica **„Predikcija vs stvarnost”** za izabrani parking crta prognozu iz „sada”
    do kraja dana i tipičnu krivu. Stvarni tok posle „sada” se prikazuje tek na
    „Otkrij stvarnost”, uz MAE.

## Ograničenja (trenutna, svesna)

- **Koordinate parkinga su iz arhiviranog feeda, a ne iz živog.** Dataset sadrži samo
  šifre (`CPN00xx`, `C06391`), bez imena i lokacija. Imena i koordinate svih 15
  parkinga su uzeti iz zvaničnog Norfolk County Council live car park feeda (DATEX II,
  `datex.norfolk.cdmf.info/carparks/content.xml`), koji danas ne odgovara, ali ga je
  Wayback Machine arhivirao 2016, 2018. i 2024. Sva tri snimka daju isto uparivanje, a
  kapaciteti se poklapaju sa podacima. Do 28.10.2026. samo 9 parkinga je imalo
  koordinate (iz poštanskog broja), a 6 je bilo bez lokacije; vidi `PROGRESS.md`.
- **Saobraćaj nije u modelu ni u preporuci** (dataset ga nema, a istorijski podaci za
  ulice u centru Norwicha nisu javno dostupni). To je budući rad, po dogovoru sa
  mentorom. Treći član skora je vreme vožnje do parkinga, procenjeno po pravoj liniji
  pri 30 km/h, bez mreže puteva i saobraćaja. Sa pravim podacima o saobraćaju menjala
  bi se samo ta procena, a formula bi ostala ista.
- **Evaluacija preporuke je simulacija na istorijskim podacima** (izmišljeni vozači,
  stvarna zauzetost pri dolasku). Nedelja je izostavljena (P&R ne rade), a vreme
  dolaska je procena po pravoj liniji.
- **Test period nema nijedan praznik**, pa uticaj `holiday` ulaza nije mogao da se izmeri.
- **OSRM (javni demo ruting server)** ume da napravi netačnu ili zaobilaznu rutu u
  centru grada, jer ne zna sve zabrane skretanja. To je uočeno i potvrđeno poređenjem
  sa Google Maps za isti par tačaka. Utiče samo na prikaz rute i „Vožnja” (km/min) u
  panelu; preporuka koristi sopstvenu procenu vremena dolaska.
- **Horizont predikcije je ograničen na ~15.5h unapred** (van toga se vrednost clamp-uje
  na maksimum, uz `horizon_clamped: true` u odgovoru).
- Skalabilnost na ostale gradove (Birmingham/Glasgow/Nottingham iz istog dataset-a) je
  opciona i nije rađena - vidi `MASTER_PLAN.md`, poglavlje 8.
- Bez baze podataka, autentifikacije ili automatizovanih testova - fokus je na tome da
  ceo lanac radi end-to-end i da je pošteno (bez curenja budućnosti u predikciju).

---

## Istorijski kontekst: seminarski rad (Birmingham PoC)

Ovaj projekat je počeo kao seminarski rad - manji proof-of-concept nad Birmingham/UCI
datasetom (~1 nedelja podataka, 29 parkinga, fiktivne koordinate, ručni unos sata/dana
umesto simulatora). **U potpunosti je zamenjen** sistemom opisanim gore (Norfolk,
pseudo real-time simulator, jedan model za bilo koji horizont). Fajlovi su ostavljeni
(`data/parking.csv`, `ml/explore.py`, `ml/train.py`, `ml/model.joblib`,
`data/park_coordinates.json`) kao istorijski artefakt i nisu deo trenutnog sistema -
`backend/` ih više ne koristi.

<details>
<summary>Detalji starog PoC-a (klikni za prikaz)</summary>

`data/parking.csv` — realni senzorski podaci o zauzetosti parkinga u Birmingemu
(Parking Birmingham / UCI dataset). 3352 merenja, 29 parkinga, period 13-19.12.2016,
merenja na ~30 min u intervalu ~08:00-16:30. Dataset nema koordinate ni podatke o
saobraćaju - koordinate su ručno/fiktivno dodeljene, saobraćaj je bio konstanta 0.

Model: XGBoost regresija nad `Hour, Minute, DayOfWeekNum, ParkEncoded, Capacity` (bez
lag feature-a, bez horizonta - suštinski "tipična zauzetost za ovo vreme", ne prava
prognoza uslovljena na trenutno stanje). RMSE/MAE: baseline (prosek) 24.33/20.22,
XGBoost (test) 12.65/9.46.

API je imao `GET /predict?park_id=&hour=&day=` i `GET /predict_current` (ručni unos
sata/dana, bez simuliranog vremena) - oba uklonjena u Fazi 3 master rada, zamenjena sa
`GET /state?target_time=`.

Frontend: mapa centrirana na Birmingem, plave tačke za sve parkinge, polja za sat/dan,
klik na mapu postavlja destinaciju i poziva `/recommend`, top 5 postaju zelene tačke.

```bash
python ml/explore.py   # EDA, dnevna kriva punjenja
python ml/train.py     # trening starog Birmingham modela
```

</details>
