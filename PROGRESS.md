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

## Završetak praktičnog dela — plan u `../PLAN_ZAVRSETKA.md` (2026-10-26)

### Korak 1 — Blizina destinaciji u skoru preporuke ✅

- `backend/recommender.py`: `closeness` sada meri udaljenost parkinga od **destinacije** (hodanje), a ne od polaska, kako je bilo od prvog commita. Stara verzija je mogla da preporuči parking blizu polaska, a daleko od cilja, jer je destinacija uticala samo preko opcionog radius filtera. Udaljenost od polaska se i dalje koristi za ETA, tj. za horizont predikcije. Ponderi su nepromenjeni (0.55/0.3/0.15).
- `frontend/app/page.tsx`: uklonjen razlog „Vrlo blizu početne tačke”, jer više ne odgovara skoru.
- Provera: subota 14.10.2017 u 11h, polazak zapadno od grada, destinacija The Forum. Prva preporuka je Rose Lane (predviđeno 37%, 0,74 km hoda). The Forum je najbliži (0,12 km), ali je predviđeno 82%, pa je niže rangiran.
- Uočeno za rad: P&R parkinzi dobijaju „hodanje” od ~4,8 km, a u stvarnosti se do centra ide autobusom. Ovo je ograničenje modela udaljenosti i ide u diskusiju.

### Korak 2 — Demo režim: izbor datuma i „predikcija vs stvarnost” ✅

Backend (`backend/main.py`, `backend/predictor.py`):
- `POST /simulation/reset?start_time=`: skok na trenutak u test periodu (zaokružen na 30 min, sat ostaje pauziran). Van test perioda vraća 400.
- `/simulation/state` sada vraća i `test_start` i `test_end`, da bi UI ograničio izbor datuma.
- `GET /compare?park_id=&date=&from_time=`: retrospektivno poređenje za jedan dan iz test perioda. Vraća stvarnu krivu, prognozu napravljenu u `from_time` za ostatak dana, liniju „sat unapred” (za svaki slot predikcija napravljena sat ranije), tipičnu krivu za taj dan u nedelji iz treninga i MAE za svaku od njih. Endpoint namerno vidi ceo dan i zato je odvojen od živog `/state`. Same predikcije i dalje vide samo podatke do svog trenutka.
- `predictor.predict_rates()`: batch predikcija, ceo dan jednim pozivom modela.

Frontend:
- `CompareChart.tsx` (nov): SVG grafik sa osama, iste boje kao `Sparkline`; linije se prekidaju na rupama u podacima.
- `page.tsx`: izbor datuma i vremena („Postavi vreme”) i panel „Predikcija vs stvarnost”. Klik na marker bira parking. Stvarni podaci posle „sada” su skriveni dok se ne klikne „Otkrij stvarnost”, kada se prikazuje i MAE za dan. Linija „sat unapred” je opciona.

Testirano u browseru (backend :8000, frontend :3000): skok na datum, otkrivanje, linija sat unapred, izbor parkinga klikom na marker. Bez grešaka u konzoli. Lint: i dalje samo 4 stare `set-state-in-effect` greške.

**Nalazi bitni za rad i odbranu:**
- **Dani za demo:** subota 18.11.2017 (model bolji od tipične krive na sva 4 gradska parkinga; Castle Quarter 1: 1,18 naspram 6,59 p.p.) i utorak 17.10.2017 (Chantry Place 3,28 naspram 9,83).
- **Ne koristiti 14.10.2017 za demo.** Prethodne subote (7.10.) nema podataka (rupa u CSV-u), pa je `y_lastweek` prazan za ceo dan i model je znatno lošiji od tipične krive (Chantry Place 9,18 naspram 1,48 p.p.). Ovo je dobar primer za diskusiju o **otpornosti na nedostajuće podatke**: model je u treningu retko video prazan `y_lastweek`.
- **Model naspram baseline-ova na celom test periodu:** tipična kriva (prosek dana u nedelji i slota) ima MAE 6,92 p.p., a „isto vreme pre nedelju dana” 5,55 p.p. Model je bolji od tipične krive na svim horizontima (najviše 5,94). ~~Od baseline-a „pre nedelju dana” je bolji do oko 4 h, a na dužim horizontima praktično izjednačen.~~ **ISPRAVLJENO u koraku 4:** ovaj zaključak je bio pogrešan, jer je MAE modela po horizontu poređen sa jednim ukupnim brojem za baseline, izračunatim na drugim redovima. Na istim redovima model je bolji od „pre nedelju dana” na **svakom** horizontu; prednost se smanjuje sa ~2,9 p.p. (30 min) na ~0,6–1 p.p. (4–15 h).

### Korak 3 — Evaluacija preporuke (`ml/eval_recommender.py`) ✅

**Postavka:** 2000 simuliranih vozača u test periodu (pon–sub, 08:00–19:30). Polazak je 3–8 km od centra Norwicha, destinacija u krugu od 1,2 km oko centra. Svaki vozač se gleda za 4 „vremena planiranja” (kreće odmah, za 1 h, 2 h, 4 h). Ishod se meri na **stvarnoj** zauzetosti u trenutku dolaska; „pun” je ≥95% (u CSV-u i ≥90%).

**Strategije:** najbliži destinaciji (bez sistema), nasumično, naša formula sa naivnom prognozom („ostaje kao sada”), naša formula sa XGBoost-om (ono što API radi) i naša formula sa savršenom prognozom (oracle). Tri „pametne” strategije koriste **istu** funkciju bodovanja kao API. Zato je bodovanje izdvojeno u `recommender.score_candidates()`; refaktorisanje je provereno, API daje identičan rezultat.

**Rezultati** (podrazumevani ponderi 0.55/0.3/0.15; `ml/output/eval_recommender_strategije.csv`):

| Strategija | Pun pri dolasku, polazak odmah | Pun, planiranje 4 h | Hodanje |
|---|---|---|---|
| Najbliži destinaciji | 19,3% | 15,4% | 0,49 km |
| Preporuka, naivna prognoza | 0,0% | 8,2% | ~0,95 km |
| **Preporuka, XGBoost** | **0,0%** | **0,0%** | ~0,92 km |
| Preporuka, savršena prognoza | 0,0% | 0,0% | ~1,0 km |

Scenario „samo gradski parkinzi” (bez P&R, realno hodanje): najbliži 19,3%, naivna 2,3% → 9,8% (4 h), XGBoost 2,6% → 2,9%, oracle 2,3% → 3,1%; hodanje 0,49 naspram ~0,68 km.

**Subota 11–16h** (najteži slučaj, `eval_recommender_subota_vrhunac.csv`): najbliži parking je pun u **70%** slučajeva. Preporuka spušta to na 0% (uz 18% upućivanja na P&R). Kad su dozvoljeni samo gradski parkinzi, pada na 11,9%, isto kao oracle. Toliko ostaje i uz savršenu prognozu: tada su puni svi gradski parkinzi i nema boljeg izbora.

*Brojevi su ažurirani 2026-10-28: kandidata je **14 umesto 9** (8 gradskih + 6 P&R, koordinate iz NCC feeda; B&Q Boundary Road se ne preporučuje). Sa 9 kandidata je bilo: najbliži 17,5%; samo gradski, XGBoost 1,8% → 2,4%; subota 85%, odnosno 0% (14% na P&R) i 7,5% samo gradski; hodanje +120–340 m. Sa više gradskih parkinga najbliži je bliži (0,49 km) i češće pun (19,3%). Scenario „samo gradski” je nešto teži, jer su novi gradski parkinzi (St Andrew's, St Giles, John Lewis) takođe često puni. Zaključci ostaju isti. Ranije ažuriranje (2026-10-27, zamena za `y_lastweek` iz koraka 5) menjalo je samo strategiju „XGBoost”, za najviše 1,5 p.p.*

**Zaključci za rad:**
1. **Preporuka radi:** rizik dolaska na pun parking pada sa 19,3% na 0–3%, uz ~190–460 m više hodanja.
2. **Vrednost ML prognoze raste sa vremenom planiranja.** Za polazak odmah (horizont 30 min) naivna prognoza je jednako dobra kao model. Kad vozač planira 2–4 h unapred, naivna prognoza dovodi na pun parking u 2,7–9,8% slučajeva, a model ostaje na 0–2,9%.
3. **Model je praktično na nivou savršene prognoze.** Kvalitet predikcije više nije usko grlo; preostali neuspesi su situacije kada su svi gradski parkinzi puni.
4. **Oracle je ponekad malo lošiji od modela.** Formula tretira dostupnost linearno (96% i 100% zauzetosti se jedva razlikuju), iako je pun parking zapravo neuspeh. Ideja za poboljšanje ili diskusiju: nelinearna kazna kad je predviđena zauzetost blizu kapaciteta, uz korišćenje MAE kao nesigurnosti.
5. **Osetljivost pondera** (`eval_recommender_osetljivost.csv/.png`, w3 = 0, w2 = 1 − w1). Za gradske parkinge, pri w1 ≥ 0,7 rizik pada ispod 1% uz ~730 m hodanja. Kad su u igri i P&R, pri w1 > 0,6 sistem šalje 23–87% vozača na P&R. Trenutni ponderi (0.55/0.3/0.15) su u dobroj tački: 0% punih, ~0,95 km hodanja, ~3% na P&R. Pri planiranju 2 h unapred kriva modela je skoro na krivoj oracle-a, a naivna ostaje na ~2% i pri w1 = 1.

*Napomena (2026-11-05): brojevi u ovom odeljku su sa starim trećim članom (heuristika „saobraćaj”). Od koraka 6a treći član je vreme vožnje do parkinga, a CSV-ovi i grafici u `ml/output/` su ponovo izračunati. Nove brojeve i poređenje vidi u koraku 6a. Glavna razlika: preporuka češće bira P&R (2,8% → 13,4%), ali onaj koji je vozaču usput. Konačni brojevi za rad biće iz koraka 6b (ponderi izabrani na oktobru, rezultati na novembru i decembru).*

**Grafici za rad:** `ml/output/eval_recommender_po_planiranju.png` (pun parking naspram vremena planiranja) i `ml/output/eval_recommender_osetljivost.png` (kompromis rizik/hodanje). Boje su iz validirane palete (dataviz validator: PASS; aqua ima nizak kontrast, pa ima direktne oznake i šuplje markere).

**Ograničenja (za rad):** nedelja je izostavljena (P&R ne rade); kandidati su 14 parkinga (B&Q Boundary Road se ne preporučuje; do 2026-10-28 bilo ih je 9); ETA ide po pravoj liniji pri 30 km/h; „hodanje” do P&R je zapravo vožnja autobusom (zato postoji scenario „samo gradski”); ~~w3 (saobraćaj) je heuristika~~ od koraka 6a treći član je vreme vožnje do parkinga, procenjeno po pravoj liniji. Vožnje sa manje od 2 kandidata su izbačene (n ≈ 1906 po vremenu planiranja, 1720 za 4 h, jer kasni dolasci padaju posle kraja merenja).

### Korak 4 — Poređenje modela (`ml/compare_models.py`) ✅

Svi modeli koriste isti trening skup (2.007.700 redova, svih 31 horizonata), isti test (373.315 redova, 1.10.–5.12.2017), iste ulaze i istu hronološku podelu. XGBoost je **model koji aplikacija stvarno koristi** (`ml/model_norfolk.joblib`), bez novog treninga.

| Model | MAE | RMSE | 30 min | 2 h | 4 h | 8 h | 15 h | Trening | Predikcija po redu |
|---|---|---|---|---|---|---|---|---|---|
| **XGBoost** | **4,83** | **7,90** | **2,87** | **4,29** | **5,07** | **5,71** | 4,36 | (ranije) | 16 µs |
| Random Forest | 4,92 | 8,21 | 3,35 | 4,48 | 5,08 | 5,75 | **4,19** | 29 s | 4 µs |
| HistGradientBoosting | 5,00 | 8,08 | 3,17 | 4,51 | 5,22 | 5,85 | 4,48 | 47 s | 13 µs |
| Pre nedelju dana (baseline) | 6,61 | 11,92 | 5,62 | 6,17 | 6,65 | 7,19 | 5,68 | – | – |
| Ridge (linearni) | 6,88 | 9,90 | 6,12 | 6,34 | 6,80 | 7,17 | 7,14 | 18 s | 2 µs |
| Tipična kriva (baseline) | 7,36 | 11,45 | 7,02 | 7,12 | 6,83 | 6,44 | 9,30 | – | – |
| Poslednja vrednost (baseline) | 25,89 | 34,49 | 5,07 | 18,26 | 28,21 | 33,74 | 34,17 | – | – |

(MAE/RMSE u p.p. zauzetosti; pun opseg horizonata u `ml/output/poredjenje_modela_po_horizontu.csv`, grafik `ml/output/poredjenje_modela.png`.)

Napomene o postavci:
- „Pre nedelju dana” koristi poslednju vrednost tamo gde podatak od pre nedelju dana fali (~3% redova).
- Random Forest: svako stablo vidi 10% trening skupa (`max_samples=0.1`) zbog vremena.
- HistGradientBoosting ima isti budžet kao XGBoost (400 iteracija, korak 0,05, dubina 6).
- Nijedan model nije posebno podešavan; XGBoost parametri su iz referentnog eksperimenta.

**XGBoost naspram „pre nedelju dana” na istim redovima** (samo gde postoji `y_lastweek`, 96,7% test skupa):

| Horizont | XGBoost | Pre nedelju dana |
|---|---|---|
| 30 min | 2,77 | 5,65 |
| 2 h | 4,19 | 5,82 |
| 4 h | 4,93 | 5,97 |
| 8 h | 5,59 | 6,38 |
| 10 h | 5,80 | 6,71 |
| 15 h | 4,19 | 4,79 |

**Zaključci za rad („zašto XGBoost?”):**
1. **Modeli sa stablima su jasno najbolji.** XGBoost, Random Forest i HistGradientBoosting su na 4,8–5,0 p.p. ukupno. Linearni Ridge (6,88) je lošiji čak i od prostog „pre nedelju dana” (6,61): ne može da modeluje da značaj trenutne zauzetosti zavisi od horizonta (na 30 min je presudna, na 8 h skoro nebitna). Nelinearan model je zato neophodan.
2. **XGBoost je najbolji na kratkim horizontima,** a oni su najvažniji za aplikaciju (dolazak je obično za 10–30 min). Na 30 min greši 2,87 p.p., naspram 3,17 (HGB) i 3,35 (RF), što je 10–15% manje. Na dugim horizontima (12–15 h) Random Forest je neznatno bolji (4,19 naspram 4,36), a u sredini su praktično izjednačeni.
3. **Izbor između modela sa stablima nije presudan; presudni su ulazi (lag feature-i) i to što je model nelinearan.** Ovo je pošten zaključak za rad: XGBoost je izabran zbog najmanje ukupne greške i najbolje kratkoročne prognoze, uz ugrađenu podršku za kategorije i nedostajuće vrednosti.
4. **Brzina nije problem ni za jedan model:** predikcija traje 2–16 µs po redu, a za 15 parkinga ispod 1 ms. Ovo je argument i za odgovor „kako bi radilo u realnom vremenu”.
5. **Otpornost (za korak 5):** u ~3% redova bez `y_lastweek` greška XGBoost-a je otprilike dvostruka (30 min: 5,83 naspram 2,77; 4 h: 9,52 naspram 4,93). To objašnjava loš 14.10.2017 iz koraka 2.

### Korak 5 — Analiza modela (`ml/analyze_model.py`) ✅

Ista podela kao u koraku 4 (trening pre 1.10.2017, test 1.10.–5.12.2017, svih 31 horizonata). Delovi „doprinos”, „greške” i „nedostajući” koriste model iz aplikacije. Ablacija, dužina treninga i specijalizovani modeli treniraju nove modele sa **istim hiperparametrima**, pročitanim iz sačuvanog modela. Ponovni trening punog modela daje 4,85 umesto 4,83, jer se trenira sa 8 niti umesto 2 i menja se redosled sabiranja. Razlike ispod ~0,05 p.p. zato nisu značajne. Izlazi su u `ml/output/analiza_*.csv` i `analiza_*.png`. Ceo skript traje ~10 min, a delovi mogu i zasebno (`python ml/analyze_model.py doprinos greske ...`).

**1. Doprinos ulaza (SHAP), `analiza_doprinos.png`.** Mera je prosečna |SHAP| vrednost, odnosno za koliko p.p. ulaz u proseku pomera predikciju u odnosu na prosek. Računata je iz samog XGBoost-a (`pred_contribs=True`), bez dodatne biblioteke, na 15.000 test redova po grupi horizonata.

| Ulaz | do 2 h | 2–8 h | preko 8 h |
|---|---|---|---|
| `y_lastweek` (isti termin pre 7 dana) | 10,44 | 11,23 | 12,15 |
| `y_yesterday` (isti termin juče) | 6,14 | 6,67 | 7,31 |
| `hour` | 3,77 | 3,80 | 4,18 |
| `carpark` | 3,39 | 3,76 | 3,62 |
| `y_t` (zauzetost sada) | 4,09 | 2,52 | 2,21 |
| `delta` | 2,00 | 1,40 | 0,96 |
| `dow` | 1,89 | 1,96 | 2,16 |
| `horizon_minutes` | 1,51 | 0,82 | 1,50 |
| ostali (`y_t1`, `y_t2`, `weekend`, `capacity`, `holiday`) | < 0,6 | < 0,5 | < 0,5 |

**2. Ablacija, `analiza_ablacija.png`.** Model je ponovo treniran bez grupe ulaza. Vrednosti su MAE u p.p.

| Varijanta | Ukupno | 30 min | 2 h | 4 h | 8 h | 15 h |
|---|---|---|---|---|---|---|
| Pun model | **4,85** | **2,87** | **4,32** | **5,07** | 5,73 | 4,40 |
| Bez trenutnog stanja (`y_t`, `y_t1`, `y_t2`, `delta`) | 5,20 | 4,93 | 5,06 | 5,19 | 5,65 | 4,12 |
| Bez istog termina ranije (`y_yesterday`, `y_lastweek`) | 5,82 | 3,09 | 4,96 | 6,24 | 6,38 | 6,96 |
| Samo kalendar i parking (bez svih lag ulaza) | 6,94 | 7,05 | 7,12 | 6,89 | 6,61 | 6,96 |
| Bez identiteta parkinga (`carpark`, `capacity`) | 5,13 | 2,84 | 4,58 | 5,40 | 6,05 | 4,55 |
| Bez praznika | 4,85 | 2,85 | 4,31 | 5,08 | 5,72 | 4,39 |

**Zaključci 1+2 (SHAP i ablacija se dopunjuju):**
- SHAP pokazuje *šta model koristi*, a ablacija *šta je nezamenljivo*. `y_lastweek` je najkorišćeniji ulaz na svim horizontima: daje „nivo” za taj parking i termin. Ipak, bez `y_lastweek`/`y_yesterday` greška na 30 min raste samo sa 2,87 na 3,09, jer tada isti podatak nosi trenutna zauzetost. Ulazi su delimično zamenljivi.
- **Trenutno stanje je presudno za kratke horizonte.** Bez njega greška na 30 min skače sa 2,87 na 4,93. Već oko 6 h unapred prestaje da pomaže, a na 12–15 h model bez njega je čak malo bolji (4,12 naspram 4,40). To je mali šum, i jedan od znakova da jedan model za sve horizonte ima cenu (vidi tačku 6).
- **Istorija istog termina je presudna za duge horizonte.** Bez nje greška na 15 h raste sa 4,40 na 6,96.
- **Samo kalendar i parking** (kao stari Birmingham model iz seminarskog) daje ~7 p.p. na svim horizontima, isto kao „tipična kriva” (7,36). Bez lag ulaza model ne može bolje od proseka.
- **Identitet parkinga skoro nije potreban** (4,85 → 5,13), jer lag ulazi već nose karakter parkinga. Ovo je važno za skalabilnost (korak 7): model bez `carpark` bi mogao da se primeni i na parking koji nije video u treningu.
- **Praznik:** test period (oktobar–decembar 2017) nema nijedan praznik, pa uticaj ne može da se izmeri. To ostaje kao ograničenje evaluacije.

**3. Greška po parkingu, tipu, dobu dana i popunjenosti, `analiza_greske.png`.**
- Po tipu: Park & Ride 2,36 p.p. (prosečno 28% pun, 6 parkinga), grad 6,35 (52%, 8 parkinga), ostalo (B&Q Boundary Road) 0,97 (20%). Gradski parkinzi su teži jer su puniji i promenljiviji. *Ažurirano 2026-10-28, kad su svi parkinzi dobili tip iz NCC feeda. Ranije je 6 parkinga bilo „nepoznat tip” (4,16), a sada su raspoređeni po tipovima. Novi gradski (John Lewis, St Giles, St Andrew's) i novi P&R (Airport, Postwick) imaju greške tipične za svoj tip, što potvrđuje uparivanje.*
- Najteži parking je **CPN0009 The Forum** (10,83; na 30 min 6,20), zatim CPN0006 St Giles (8,05) i CPN0005 Castle Quarter 2 (7,78). Najlakši je C06391 B&Q Boundary Road (0,97; skoro uvek prazan).
- Po dobu dana gradski parkinzi su najteži **uveče (18–21 h, do 9,2 p.p.)** i u **jutarnjem punjenju (9–10 h)**. Ovo važi i na fiksnom horizontu od 1 h (19 h: 6,4 p.p., 9 h: 5,0, naspram 12 h: 3,1), pa nije posledica mešanja horizonata. Prelazi (punjenje i pražnjenje) su teški, a stabilni periodi laki. Verovatan uzrok, nepotvrđen, su večernji događaji i izlasci u centru, kojih nema u podacima. Po danu je najteža nedelja (6,15), a ostali dani su 4,2–5,0.
- Po stvarnoj popunjenosti: ispod 50% greška je 3,80, za 50–80% je 6,05, za **80–95% je 7,69** (najveća), a za ≥ 95% je 6,09. Kada je parking stvarno ≥ 95% pun, model predviđa ≥ 90% u **76%** slučajeva. Za preporuku je opseg 80–95% najrizičniji, što je argument za nelinearnu dostupnost (opciona stavka iz koraka 3).

**4. Nedostajući podaci i zamena (fallback).**

Prirodne rupe u testu:

| Redovi | Udeo | MAE model | MAE tipična kriva |
|---|---|---|---|
| svi ulazi postoje | 80,2% | 4,82 | 7,44 |
| fali `y_lastweek` | 3,3% | 8,27 | 8,56 |
| fali `y_yesterday` | 5,5% | 2,77 | 6,38 |
| fali `y_t1` ili `y_t2` | 12,6% | 4,94 | 7,09 |

Veštačko brisanje (redovi gde sve postoji, uklanja se jedan ulaz):

| Varijanta | MAE |
|---|---|
| ništa ne fali | 4,82 |
| fali `y_lastweek` | 6,53 |
| fali `y_yesterday` | 6,25 |
| fale oba | 9,44 |
| fale `y_t1`, `y_t2` | 6,10 |

Zaključak: rupa u `y_lastweek` je sama po sebi skupa, ne samo zato što su ti dani teži. Pri veštačkom brisanju na „normalnim” danima greška raste sa 4,82 na 6,53. Tipična kriva je na prirodnim rupama samo malo lošija nego inače (8,56 naspram 7,44), a model mnogo (8,27 naspram 4,82).

Zamena za `y_lastweek` koji fali (samo pri predikciji, model se ne trenira ponovo):

| Zamena | Prirodne rupe | Veštački obrisano |
|---|---|---|
| bez zamene (NaN) | 8,27 | 6,53 |
| **isti termin 14 dana ranije** | **5,82** | 5,06 |
| tipična vrednost (prosek iz treninga) | 6,14 | 5,47 |
| 14 dana, pa tipična | 5,94 | 4,99 |
| (stvarna vrednost, gornja granica) | – | 4,82 |

Vrednost od pre 14 dana postoji u 93,9% slučajeva kada `y_lastweek` fali. Na celom testu zamena smanjuje grešku sa 4,83 na **4,75**, a za demo dan **14.10.2017 sa 7,90 na 4,44**. **Uvedeno u aplikaciju:** `backend/predictor.py` (`_same_slot_last_week`, `LASTWEEK_FALLBACK_DAYS = 14`). Ako ni od pre 14 dana nema podatka, ostaje NaN kao i ranije. Lanac „14 dana, pa tipična” nije uveden: na prirodnim rupama nije bolji, a zahteva tabelu tipičnih vrednosti u backendu.

U demo prikazu (`/compare`, 14.10.2017, „sada” = 10:00) greška prognoze je bez zamene i sa zamenom: CPN0005 15,22 → 7,75; CPN0007 12,87 → 7,73; CPN0009 11,65 → 7,67; CPN0017 9,18 → 1,41 p.p. Evaluacija preporuke iz koraka 3 je zbog izmene ponovo pokrenuta, a brojevi u tom odeljku su ažurirani.

**5. Dužina trening skupa.** Isti model je treniran na poslednjih N pre 1.10.2017.

| Trening | Redova | Ukupno | 30 min | 2 h | 8 h |
|---|---|---|---|---|---|
| 2 nedelje | 83.052 | 5,94 | 5,12 | 5,67 | 6,27 |
| 1 mesec | 177.934 | 5,44 | 4,36 | 5,13 | 6,02 |
| 3 meseca | 524.078 | 5,19 | 3,36 | 4,70 | 5,97 |
| 6 meseci | 1.065.905 | 5,09 | 3,21 | 4,59 | 5,93 |
| ~11 meseci (sve) | 2.007.700 | 4,85 | 2,87 | 4,32 | 5,73 |

Greška monotono pada i još ne staje između 6 i 11 meseci, pa bi više podataka verovatno još pomoglo. Jedan model za sve horizonte traži više podataka od specijalizovanog. Referentni eksperiment (specijalizovan model, samo 30 min) je sa 2 nedelje imao 2,21, a jedan model sa 2 nedelje ima 5,12. Ovo je argument zašto prelazak sa Birminghama (u projektu samo 7 dana podataka, 13.–19.12.2016) na Norfolk (~13 meseci) nije bio samo kozmetički.

**6. Jedan model naspram specijalizovanih** (isti test redovi, `analiza_specijalizovani.csv`):

| Horizont | Specijalizovan model | Jedan model (aplikacija) |
|---|---|---|
| 30 min | 1,63 | 2,87 |
| 1 h | 2,62 | 3,45 |
| 2 h | 3,86 | 4,29 |

Brojevi iz redizajna (2026-10-17) su potvrđeni. Cena fleksibilnosti je najveća baš na najkraćem horizontu (+76% na 30 min). Jedan model kapacitet od 400 stabala dubine 6 deli na 31 horizont, a 30-min redovi su samo 1/31 treninga. Ablacija pokazuje isti efekat sa druge strane: na dugim horizontima trenutno stanje već smeta. **Moguće poboljšanje (nije urađeno):** hibrid, odnosno specijalizovani modeli za 30 min do 2 h i jedan model za ostale horizonte. Za rad je dovoljno navesti tradeoff i hibrid kao budući rad.

### Korak 6 — Vreme vožnje umesto saobraćaja (u toku: 6a ✅, 6b–6d preostaju)

**Odluka mentora (4.11.2026):** saobraćaj ostaje budući rad, a treći član formule postaje vreme vožnje od polaska do parkinga. Argument za rad, rečima mentora: cilj treće komponente nije merenje saobraćaja, već procena troška dolaska do parkinga; vreme vožnje je direktnija mera tog troška i prirodno obuhvata saobraćaj kada takvi podaci postanu dostupni. Evaluacija sa 2000 vožnji je dovoljna; u radu je opisati kao **offline replay eksperiment** koji meri efikasnost algoritma preporuke (da li vozača upućuje na parking sa slobodnim mestima), a ne zadovoljstvo korisnika. Plan: 6a vreme vožnje u formuli, 6b izbor pondera na validacionom periodu, 6c prag punog parkinga (85/90/95%), 6d dokumentacija.

#### 6a — Vreme vožnje kao treći član ✅ (2026-11-05)

`skor = w1·dostupnost + w2·blizina_cilju − w3·vreme_vožnje`, ponderi i dalje 0.55/0.3/0.15 (biraju se u 6b).

- `backend/recommender.py`: heuristika `_traffic_density_score` je obrisana. `vreme_vožnje = eta_minutes / najduža_vožnja_među_kandidatima` (0–1), isto normalizovano kao blizina. Koristi se već postojeća procena dolaska (prava linija, 30 km/h), pa podaci o saobraćaju bi kasnije menjali samo `eta_minutes`. `score_candidates()` više ne prima sat, jer ga je koristila samo heuristika. U odgovoru API-ja `score_components.traffic` je postalo `drive_time`, a `w3_traffic` je postalo `w3_drive_time`.
- `ml/eval_recommender.py`: kandidati nose `eta_minutes`, a tabele imaju i `voznja_min`.
- Frontend: u bloku „Zašto?” i u formuli ispod preporuka „Saobraćaj” je postalo „Vreme vožnje”. Provereno u browseru (Bowthorpe → centar, sub 18.11.2017 10:00): „Vreme vožnje − 52% × 0.15”, bez grešaka u konzoli; `tsc` prolazi.

**Rezultati** (isti 2000 vozača, XGBoost, ceo test period; `ml/output/eval_recommender_*.csv`):

| | Staro (heuristika „saobraćaj”) | Novo (vreme vožnje) |
|---|---|---|
| Pun pri dolasku, svi parkinzi (polazak odmah / 4 h) | 0,0% / 0,0% | 0,0% / 0,0% |
| Pun pri dolasku, samo gradski (polazak odmah / 4 h) | 2,6% / 2,9% | **2,2% / 2,4%** |
| Upućeno na P&R, svi parkinzi | 2,8% | 13,4% |
| od toga P&R na suprotnoj strani grada | **61%** | **14,5%** |
| Prosečna vožnja do izabranog P&R | 6,0 km | 3,1 km |
| Prosečna vožnja do izabranog parkinga | 5,53 km | 5,16 km |
| Subota 11–16 h: na P&R / od toga suprotna strana | 18% / 58% | 40% / 23% |
| Subota 11–16 h, samo gradski: pun pri dolasku | 11,9% | 10,4% |

„Suprotna strana grada” znači da je vožnja od polaska do P&R duža od vožnje do samog centra, tj. vozač bi prošao pored centra da bi stigao do P&R (skript za ovo merenje je pomoćni, van repoa; isti vozači, polazak odmah).

**Zaključci:**
1. **Problem zbog kog je izmena uvedena je rešen.** Ranije je sistem retko slao na P&R, ali kad je slao, 61% puta je to bio P&R na suprotnoj strani grada (prosečno 6 km vožnje). Sada je to 14,5% (3,1 km). Vozač se šalje na P&R koji mu je usput.
2. **Više upućivanja na P&R (2,8% → 13,4%).** Stara heuristika je u stvari bila dodatna kazna za udaljenost od cilja, pa je odvraćala od svih P&R. Sada se P&R bira kad je usput i kad je centar pun (subota 40%, a radnim danom ujutru ih nema u vrhu). Da li je ovaj udeo „previše”, zavisi od kriterijuma izbora pondera. To je pitanje za 6b, ne za formulu.
3. **Za gradske parkinge izmena malo pomaže** (2,6% → 2,2%), jer je vožnja do svih parkinga u centru skoro ista. Tu i dalje odlučuju dostupnost i blizina cilju. Hodanje je isto (~0,69 km).
4. **Ograničenje primera iz dokumenta za mentora.** U primeru Bowthorpe → centar (sub 18.11.2017 10:00) Thickthorn se popeo sa 13. na 7. mesto, ali je Sprowston i dalje ispred njega (2. mesto). Razlog nije vreme vožnje, nego dostupnost: Sprowston je predviđen na 18%, a Thickthorn na 43%. Oba imaju dosta mesta, ali linearna dostupnost tu razliku od 25 p.p. vrednuje više nego 8 minuta kraće vožnje. Rečenica iz dokumenta („prednost bi dobio Thickthorn”) važi samo kad su oba parkinga podjednako slobodna. Pri istoj dostupnosti Thickthorn pobeđuje, ali tesno (razlika u skoru 0,013). Ovo je argument za 6b (koliko težine dati vremenu vožnje), a možda i za nelinearnu dostupnost (vidi korak 3, zaključak 4).

#### Istorija (pre odluke mentora)

Analiza (2026-10-27) je pokazala da heuristika za saobraćaj ne meri saobraćaj. Deo za vršne sate je isti za sve kandidate u istom trenutku, pa ne menja redosled. Deo za udaljenost (`min(0.35, d/10)`) je apsolutna kazna za udaljenost, koja odvraća sistem od P&R parkinga. Izmereno na istih 2000 vozača (XGBoost, polazak odmah):

| Varijanta | Pun pri dolasku (samo gradski) | Na P&R (svi parkinzi) | Subota 11–16 h: na P&R / pun (gradski) |
|---|---|---|---|
| sada: 0.55/0.3/0.15 + heuristika | 2,6% | 2,8% | 18% / 11,9% |
| w3 = 0, ponderi 0.6/0.4 | 4,0% | 4,0% | 19% / 19,4% |
| w3 = 0, ponderi 0.55/0.3 | 2,3% | 10,8% | 37% / 11,2% |
| **vreme vožnje, 0.55/0.3/0.15 (uvedeno u 6a)** | 2,2% | 13,4% | 40% / 10,4% |

*Ažurirano 2026-10-28: tabela je izračunata sa 14 kandidata (svi parkinzi sa koordinatama iz NCC feeda, bez B&Q Boundary Road). Sa 9 kandidata je bilo: sada 1,8% / 2,2% / 14% / 7,5%; 0.6/0.4 3,0% / 2,9% / 15% / 11,9%; 0.55/0.3 1,6% / 8,8% / 30% / 6,7%. Sa više parkinga, izbacivanje heuristike više košta (subota, samo gradski: 11,9% → 19,4% uz 0.6/0.4).*

Primećena je još jedna slabost: skor ne kažnjava udaljenost od polaska. Vozaču sa zapada se nude P&R na suprotnim stranama grada (Sprowston, Postwick), umesto Costessey-ja i Thickthorn-a koji su mu na putu. Kandidat za treći član umesto „saobraćaja” je **vreme vožnje do parkinga** (već se računa kao ETA, a sa pravim saobraćajem bi postalo tačnije). ~~Još nije izmereno.~~ Izmereno i uvedeno u 6a.

Istorijski podaci o saobraćaju za ulice u centru Norwicha (2016–2017, 30 min) nisu nađeni besplatno. Za ulazne puteve (A47, A11) postoji National Highways WebTRIS. Pitanje i opcije su u `../ZA_MENTORA.md`.

### Korak 8 — Higijena projekta ✅

- `CLAUDE.md` je prepisan za trenutni sistem (Norfolk, simulator, jedan model, evaluacija, dokumenti van repoa), uz zadržana pravila rada.
- `README.md`:
  - ispravljena struktura (`MASTER_PLAN.md` i `reference/` su van repoa) i dodati novi fajlovi;
  - dodati endpointi `/simulation/reset` i `/compare`, kao i odeljak „Evaluacija i analiza” sa komandama;
  - dodati demo režim u frontendu i izvor podataka (GitLab link);
  - ispravljen navod o OSRM-u: utiče samo na prikaz rute, ne i na preporuku;
  - obrazloženje za 6 parkinga bez koordinata;
  - nova ograničenja (saobraćaj čeka mentora, evaluacija simulacijom, test bez praznika).
- Reprodukovanost: model je u repou, pa za pokretanje aplikacije nije potreban trening. Komande iz README-a (`npm run backend`, `npm run frontend`, `python ml/...`) su proverene.
- Sitne popravke frontenda, uočene pri demo prolazu (scenario iz `../ZA_MENTORA.md`):
  1. legenda mape se sklanja dok je otvoren popup parkinga, jer ga je prekrivala;
  2. „Raspodela skora” je zamenjena „Delovima skora”: sada prikazuje stvarne komponente iz backenda (`score_components`, dostupnost / blizina cilju / saobraćaj, uz pondere). Stare trake „Vožnja” i „Hodanje” su se računale u frontendu sa proizvoljnim granicama (2 km / 1 km), skoro uvek su bile 0%, a „vožnja” uopšte ne ulazi u skor;
  3. liste preporuka i parkinga uz rutu prikazuju ime parkinga umesto šifre, a dodato je i „Hodanje do cilja”;
  4. dan u nedelji se ispisuje latinicom (`sr-Latn-RS` umesto `sr-RS`).

### UI redesign frontenda (grana `ui-redesign`, 2026-10-27)

Promenjen je samo prezentacioni sloj. Pozivi ka backendu, parametri, polling (3 s), logika preporuke i rute ostali su isti.
- Bootstrap je zamenjen Tailwind-om v4 (design tokeni u `globals.css`), a ikonice su iz `lucide-react`.
- Status zauzetosti se prikazuje bojom, ikonom i tekstom; pragovi su isti (< 50 / 50–80 / ≥ 80 %).
- Marker parkinga na mapi je pilula sa procentom.
- Preporuka #1 je istaknuta i ima blok „Zašto?“ sa delovima skora i formulom skora.
- Dodata su stanja učitavanja i prazna stanja; responsive prikaz je proveren na 390 px.
- Detalji, inventar funkcionalnosti i checklista za ručnu proveru su u `frontend/UI_REDESIGN_PLAN.md`.

### Svih 15 parkinga na mapi: koordinate iz zvaničnog NCC feeda (2026-10-28)

**Problem:** dataset ima samo šifre parkinga. Do sada je 9 šifri bilo upareno poređenjem kapaciteta sa današnjim spiskom, a koordinate su bile iz poštanskog broja (postcodes.io). Za 6 šifri (CPN0003, CPN0006, CPN0008, CPN0011, CPN0013, C06391) uparivanje nije bilo sigurno, pa nisu bile na mapi ni u preporuci.

**Rešenje:** šifre potiču iz Norfolk County Council live car park feeda (DATEX II, `https://datex.norfolk.cdmf.info/carparks/content.xml`, nađen preko paketa `live-parking-norwich` i data.gov.uk). Feed danas ne odgovara (timeout), ali ga je Wayback Machine arhivirao 6.3.2016, 1.9.2018. i 4.8.2024. Feed za svaku šifru daje ime, kapacitet i koordinate. Sva tri snimka daju isto uparivanje, a kapaciteti se poklapaju sa Norfolk.csv.

| Šifra | Parking | Tip |
|---|---|---|
| CPN0003 | John Lewis, Ber Street | grad |
| CPN0006 | St Giles, St Giles Street | grad |
| CPN0008 | St Andrew's, Duke Street | grad |
| CPN0011 | Airport Park & Ride | Park & Ride |
| CPN0013 | Postwick Park & Ride | Park & Ride |
| C06391 | B&Q Boundary Road (parking prodavnice) | ostalo |

Dve ranije pretpostavke iz `MASTER_PLAN.md` su bile pogrešne (CPN0011 nije John Lewis, CPN0013 nije Airport). Pravilo „ne izmišljati koordinate” se pokazalo opravdanim. Isključeni parkinzi su CPN0001 = Anglia Square, CPN0002 = St Stephens i CPN0010 = Riverside.

**Izmene:**
- `data/carparks_norfolk.json` ima svih 15 parkinga: ime, ime iz feeda, tip i koordinate iz feeda. Za postojećih 9 koordinate su zamenjene feedom; ranije koordinate iz poštanskog broja odstupale su 11–680 m. Skripta za generisanje je jednokratna (scratch), a izvor je opisan u `_comment`.
- `backend/recommender.py` ima novu konstantu `RECOMMENDABLE_TYPES = {"grad", "Park & Ride"}`. B&Q (parking prodavnice za kupce, 3,6 km od centra, bez autobusa) se vidi na mapi i ulazi u model, ali se ne preporučuje (odluka korisnika). Evaluacija koristi isti filter.
- `ml/eval_recommender.py`: udeo „na P&R” sada broji samo tip „Park & Ride”, a ne „sve što nije grad”.
- `ml/analyze_model.py`: tip „ostalo” u grafiku greške.
- Model se ne menja, jer je već koristio svih 15 parkinga (MAE 4,83 ostaje). Ponovo su pokrenute evaluacija preporuke (korak 3), poređenje opcija za saobraćaj (korak 6) i greška po tipu (korak 5), pa su brojevi u tim odeljcima ažurirani.

**Provera tipova:** novi gradski parkinzi imaju greške tipične za grad (St Giles 8,05, John Lewis 5,68, St Andrew's 4,43), a novi P&R greške tipične za P&R (Airport 2,75, Postwick 2,42). Ponašanje u podacima se slaže sa uparivanjem iz feeda.
