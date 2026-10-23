# Napredak master rada — log po fazama

Trajan zapis šta je urađeno u svakoj fazi (vidi `MASTER_PLAN.md` za pun kontekst i plan).
Ažurira se na kraju svake faze, pre prelaska na sledeću.

## Faza 0 — Istraživanje projekta (bez izmena)

Pregledana postojeća struktura (`smart-parking/`, poseban git repo od korena projekta).

Nalazi:
- Aplikacija trenutno radi na **Birmingham** datasetu (`data/parking.csv`, ~1 nedelja podataka), ne na Norfolku.
- Model (`ml/train.py` → `ml/model.joblib`) predviđa "tipičnu" zauzetost iz `Hour, Minute, DayOfWeekNum, ParkEncoded, Capacity` — **bez lag feature-a, bez horizonta, bez uslovljavanja na trenutno stanje**. Suštinski različito od `reference/norfolk_xgb_eksperiment.py`.
- `backend/parks.py` — kapacitet stvaran (iz CSV-a), koordinate fiktivne (`data/park_coordinates.json`), ručno raspoređene oko Birmingema.
- `backend/recommender.py` — ponderisano rangiranje (dostupnost + blizina − lažni saobraćaj), odvojeno od predikcije, već implementirano po CLAUDE.md principu.
- API (`backend/main.py`): `/parks`, `/predict`, `/predict_current`, `/recommend` — sat/dan su ručni inputi, nema simuliranog vremena.
- Frontend (Next.js + Leaflet): klik na mapu bira start/destinaciju, poziva `/recommend` i OSRM za rutu. Nema istorije, nema predviđanja za +30/+60/+120, nema time slidera, nema prikaza pouzdanosti — ništa od poglavlja 6 još nije urađeno.
- Git: nekomitovane izmene u `frontend/app/page.tsx`, necraćeni `data/park_coordinates.json`, `docs/`, `run.py` — nisu dirani.

Predlog za faze 1–4 dat i prihvaćen (vidi chat, odgovara strukturi ispod).

## Faza 1 — Podaci i model na Norfolku ✅

Novi, paralelni pipeline uz postojeći Birmingham PoC (ništa od postojećeg nije dirano):

- **`ml/data_prep.py`** — učitavanje/čišćenje Norfolk CSV-a (`../data/raw/Norfolk.csv`, van ovog repoa), resample na 30 min, reindex na pravilnu mrežu, feature-i po horizontu (`y_t, y_t1, y_t2, delta, y_yesterday, y_lastweek, hour, dow, weekend, holiday, carpark, capacity`). Konfigurabilno po gradu (`CITY_CONFIGS`), Norfolk podrazumevan — ostali gradovi se dodaju u opcionoj fazi skalabilnosti.
- **`ml/train_norfolk.py`** — trenira XGBoost za 3 horizonta (30min/1h/2h) na celom treningu pre 1.10.2017, čuva `ml/model_norfolk_1.joblib`, `_2.joblib`, `_4.joblib` i metrike (`ml/output/norfolk_metrike.csv`, `ml/output/norfolk_mae_po_parkingu.csv`).
- **`requirements.txt`** — dodat (nije postojao).
- **README.md** — dodata sekcija o instalaciji i Norfolk pipeline-u.

Rezultati (MAE/RMSE u p.p., test 1.10–5.12.2017), poklapaju se sa referentnim eksperimentom i MASTER_PLAN.md:

| Horizont | MAE | RMSE |
|---|---|---|
| 30 min | 1.63 | 2.75 |
| 1 sat | 2.61 | 4.34 |
| 2 sata | 3.85 | 6.33 |

MAE po parkingu sačuvan po horizontu (koristi se kasnije kao "pouzdanost prognoze" na mapi).

Backend i frontend i dalje rade nepromenjeni na Birmingham PoC-u — prebacivanje na Norfolk je deo Faze 3 (simulator/API).

## Faza 2 — Koordinate za Norfolk ✅

- **`data/carparks_norfolk.json`** — novi fajl sa šifra/ime/kapacitet/lat/lon/tip/potvrđeno za svih 15 upotrebljivih Norfolk parkinga.
- **9 potvrđenih** parkinga: koordinate dobijene iz poštanskog broja preko postcodes.io API-ja (quality=1, tačan pogodak za sve): Chantry Place (CPN0017), Thickthorn P&R (CPN0016), Harford P&R (CPN0015), Castle Quarter 1/2 (CPN0004/CPN0005), Rose Lane (CPN0007), The Forum (CPN0009), Sprowston P&R (CPN0012), Costessey P&R (CPN0014).
- **6 neuparenih** (CPN0003, CPN0006, CPN0008, CPN0011, CPN0013, C06391): kandidati iz MASTER_PLAN.md (St Andrew's, John Lewis, Riverside, St Giles, St Stephens, Airport P&R) imaju kapacitete iz 2017. koji se ne poklapaju tačno sa dataset-om, pa po pravilu "ne izmišljati koordinate" ostaju `confirmed: false`, `lat/lon: null`. Dogovoreno s korisnikom (2026-10-16): ostaju nepotvrđeni za sada, odluka se donosi kasnije kad bude više informacija (npr. Norfolk County Council feed).
- `backend/parks.py` **nije dirano** — integracija koordinata u API je deo Faze 3 (Simulator i API), po MASTER_PLAN.md.

## Faza 3 — Simulator i API ✅

Dogovoreno s korisnikom (2026-10-16): backend se **odmah zamenjuje** (ne paralelni endpointi) — `main.py`, `predictor.py`, `recommender.py`, `parks.py` su prepravljeni da rade na Norfolku i simulatoru. **Posledica:** trenutni frontend (Birmingham, ručni `hour`/`day`, `/predict`) privremeno ne radi — očekivano, popravlja se u Fazi 4.

Novo/izmenjeno u `backend/`:
- **`datasource.py`** (nov) — `DataSource` ABC, `ReplaySource` (učitava Norfolk CSV jednom pri startu, `history_until(park_id, until)` nikad ne otkriva podatke sa vremenom > `until`), `LiveSource` stub.
- **`simulator.py`** (nov) — `SimulationClock`: simulirano vreme, tick = 30 min, podesiva brzina (sim-min/stvarna-sek), start/pauza/reset. Koristi `asyncio.create_task` — endpointi koji ga pokreću/pauziraju moraju biti `async def` (sync FastAPI handleri rade u threadpool-u bez event loop-a — ovo je prvo puklo u testu i popravljeno).
- **`predictor.py`** (prepravljen) — učitava sva 3 `ml/model_norfolk_<h>.joblib`, gradi feature red iz apsolutnog vremena (`y_t`/`y_t1`/`y_t2` = now/-30/-60min, `y_yesterday`/`y_lastweek` = target_time -1d/-7d, gde je `target_time = now + h*30min`). Kategorije parkinga za XGBoost `carpark` kolonu moraju biti identične trening kategorijama (dodato u bundle u `ml/train_norfolk.py`, modeli ponovo trenirani) — inače bi kategorijalni kod bio pogrešan i predikcija tiho netačna.
- **`parks.py`** (prepravljen) — kapacitet iz Norfolk CSV-a, koordinate/ime/tip iz `data/carparks_norfolk.json`.
- **`recommender.py`** (prepravljen) — ista ponderisana formula (w1=0.55/w2=0.3/w3=0.15), ali predikcija se radi za procenjeno vreme dolaska (gruba procena ETA po pravoj liniji / 30 km/h → najbliži horizont 30min/1h/2h), ne za ručno unet sat. Parkinzi bez potvrđenih koordinata se izostavljaju iz preporuke.
- **`main.py`** (prepravljen) — novi endpointi: `GET /parks`, `GET /simulation/state`, `POST /simulation/start`, `POST /simulation/pause`, `POST /simulation/speed`, `GET /state` (trenutna zauzetost + 3 horizonta + MAE po parkingu), `GET /recommend`. Stari `/predict`, `/predict_current` uklonjeni (zamenjeni sa `/state`).

Testirano ručno (uvicorn + curl): server startuje, `/parks` i `/simulation/state` radi, start/pause/resume (nastavlja od istog vremena, ne reseta), `/state` vraća plauzibilne vrednosti (npr. CPN0017 u podne 75% zauzeto → 67%/62%/51% za 30min/1h/2h — opadajući trend ka popodnevu, smisleno), `/recommend` vraća rangiranu listu sa radius filterom.

README.md i backend/ docstring-ovi ažurirani da upućuju na ovu fazu; stari Birmingham opisi u README ostavljeni kao istorijski, uz napomenu da više ne važe za trenutni kod.

## Faza 4 — Mapa ✅

Backend dobio jedan novi endpoint (`GET /history?park_id=`) da podrži sparkline u popup-u — tipična kriva za dan u nedelji (prosek iz trening perioda, pre test_start) + stvarna očitavanja od ponoći simuliranog dana do "sada". `ReplaySource.training_series()` dodat u `datasource.py` (strogo ograničeno na pre-test period, nikad ne otkriva buduće podatke).

Frontend (`frontend/app/`) prepravljen:
- **`Sparkline.tsx`** (nov) — lagan inline-SVG grafik (bez eksternih chart biblioteka, po CLAUDE.md "ne komplicirati"): siva isprekidana linija (tipično), plava puna (stvarno do sada), narandžasta isprekidana sa tačkama (prognoza 30min/1h/2h). Boje iz dataviz skill validirane palete (status/sequential/muted tonovi).
- **`ParkingMap.tsx`** — markeri svih potvrđenih parkinga sada obojeni po statusu zauzetosti (zeleno &lt;50%, žuto 50-80%, crveno &gt;80%, sivo = nema očitavanja) za izabrani "pogled" (sada/+30/+60/+120); preporučeni parkinzi dobijaju ljubičasti prsten + broj ranga (sekundarna oznaka, ne samo boja — izbegnut sudar sa statusnim bojama). Popup prikazuje trenutnu/predviđenu zauzetost, slobodna mesta, MAE ("pouzdanost") i sparkline (lenjo učitan preko `/history` tek kad se popup otvori).
- **`page.tsx`** — uklonjen ručni unos sata/dana; dodata kontrola simulacije (prikaz vremena, Start/Pauza, brzina) koja poluje `/simulation/state` i `/state` na 3s; dodat time-slider "Sada/+30min/+1h/+2h" koji menja boje markera i prikaz u panelu "Parkinzi uz rutu"; taj panel sada čita iz već učitanog `/state` (useMemo) umesto N poziva `/predict` po parkingu kao ranije. `/recommend` poziv bez hour/day (backend sam koristi simulirano vreme + ETA do parkinga).

**Ručno testirano u pravom browseru** (claude-in-chrome, uvicorn + next dev): mapa učitava i boji 9 potvrđenih parkinga; pokretanje/pauza/brzina simulacije radi i markeri se u realnom vremenu osvežavaju (uhvaćena i potvrđena kao stvarna, ne kao bug, rupa u podacima 7.10.2017 — svi parkinzi sivi taj dan, potvrđeno u sirovom CSV-u); time-slider menja boje; popup prikazuje pun sparkline (tipično+stvarno+prognoza) kad ima podataka, samo tipičnu krivu kad nema trenutnog očitavanja; ceo tok klik-start → klik-destinacija → ruta (OSRM) → "Parkinzi uz rutu" → "Top preporuke" sa rang brojevima na mapi i raspodelom skora — sve radi end-to-end, bez grešaka u konzoli.

**Napomena:** `react-hooks/set-state-in-effect` lint greške u `page.tsx` (setState unutar early-return grane efekta) postoje i u originalnom, pre-Faze-3 kodu (nisu nova regresija) — ostavljeno netaknuto, van obima ove faze.

## Redizajn — proizvoljan horizont predikcije (2026-10-17) ✅

**Ispravka pogrešnog navoda:** ranije sam tvrdio da su "3 fiksna horizonta (30min/1h/2h)" profesorov zahtev. To je **netačno** — korisnik je pokazao stvarnu mejl prepisku: profesor je rekao samo "predviđena zauzetost, istorija zauzetosti, prikaz stanja za naredni period... šta god je moguće od navedenog", bez ikakvog broja horizonata. Ona tri broja su se uvukla iz `reference/norfolk_xgb_eksperiment.py` (sopstveni eksperiment korisnika *pre* mejla profesoru) u `MASTER_PLAN.md` poglavlje 4, i ja sam to pogrešno pročitao kao propisan zahtev. Motivacija za izmenu: korisnik (kao vozač) treba da može da planira polazak u bilo koje doba dana (npr. "krećem u 17h"), ne samo +30min/+1h/+2h od trenutnog simuliranog vremena.

**Model (`ml/data_prep.py`, `ml/train_norfolk.py`):** umesto 3 odvojena modela, sada **jedan** XGBoost model kome je horizont (`horizon_minutes`) obična ulazna promenljiva. Treniran preko `HORIZON_STEPS_RANGE` = 1..31 koraka (30 min do 15.5h — pokriva ceo radni dan parkinga čak i u najgorem slučaju kad je "sada" u 08:00 a traženo vreme 23:30). Trening skup: ~2M redova (31x veći nego pre). Sačuvan kao `ml/model_norfolk.joblib` (zamenjuje stara 3 fajla, obrisana).

Cena fleksibilnosti — jedan model je nešto manje precizan po horizontu nego specijalizovani modeli iz Faze 1 (vredno pomena u radu kao tradeoff):

| Horizont | Pre (specijalizovan model) | Sad (jedan model) |
|---|---|---|
| 30 min | 1.63 p.p. | 2.87 p.p. |
| 1 sat | 2.61 p.p. | 3.45 p.p. (60min) |
| 2 sata | 3.85 p.p. | 4.29 p.p. (120min) |

MAE raste do horizonta ~540-600min (9-10h), pa opet pada ka 900-930min — artefakt doba dana na koje horizont uglavnom cilja (veliki horizonti od jutra gađaju kasno veče, manje varijabilno), ne greška.

**Backend:**
- `backend/predictor.py` — jedan model, `predict_rate(..., horizon_steps)` prima bilo koji korak 1..31 (ranije samo {1,2,4}).
- `backend/main.py` — `/state` sad prima opcioni `target_time` (ISO datetime) umesto fiksnog `predictions` rečnika sa 3 ključa. Ako je `target_time` u prošlosti/sadašnjosti → vraća **stvarno izmerenu** vrednost (`is_prediction: false`), ne predikciju — tačno ono što je korisnik tražio ("najbolje za vremena kad je senzor merio"). Ako je u budućnosti → predikcija (`is_prediction: true`), sa `horizon_minutes` i `mae`; ako je traženo vreme van treniranog opsega (>15.5h), horizont se **clamp-uje** na maksimum i `horizon_clamped: true` se vraća.
- `backend/recommender.py` — `_nearest_horizon_steps` (zaokruživanje na {1,2,4}) zamenjeno sa `_horizon_steps_for_arrival` (tačan horizont, clamp samo na gornju granicu). Dodat opcioni `departure_time` parametar — vozač može da kaže "krećem u 17h", pa se dolazak (i time horizont predikcije) računa od tog vremena, ne od simuliranog "sada".

**Frontend:**
- `ParkingMap.tsx` — `ParkState` tip promenjen (`target_time/target_occupancy_rate/is_prediction/horizon_minutes/horizon_clamped/mae` umesto `predictions`/`mae_per_horizon` rečnika). Popup jasno piše "(izmereno)" ili "(predikcija)" zavisno od `is_prediction`; sparkline sad crta **jednu** tačku prognoze (za izabrano vreme) umesto tri fiksne.
- `page.tsx` — "Pogled (mapa)" dugmad (Sada/+30/+60/+120) zamenjena **jednim padajućim menijem** "Vreme (mapa i polazak)": "Sada" + 48 opcija na 30-min mreži (00:00-23:30, ista mreža kao merenja senzora). Ista vrednost se šalje i kao `target_time` za `/state` (boje na mapi, popup) i kao `departure_time` za `/recommend` (preporuke se računaju za vreme dolaska od tog polaska) — jedan kontrol pokreće i mapu i preporuku.

**Ručno testirano u browseru:** padajući meni → menja boje markera; popup za prošlo vreme (09:00) ispravno piše "izmereno" bez MAE/prognoze; popup za buduće vreme (17:00) piše "predikcija", prikazuje MAE i jednu tačku prognoze na sparkline-u; preporuka sa izabranim 17:00 ispravno vraća `horizont 420 min` (= 7h od simuliranog 10:00) u listi preporuka. Potvrda-pre-brisanja-rute modal i dalje radi ispravno (slučajno ponovo testiran u istom prolazu). Bez grešaka u konzoli (jedna "stale" greška u Next.js overlay-u iz starog hot-reload-a, nestala posle hard refresh-a — nije stvarna greška).

## Faza 5 — Skalabilnost (opciono)

_Nije započeto — čeka potvrdu (samo ako korisnik to zatraži)._
