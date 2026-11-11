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

*Napomena (2026-11-05): brojevi u ovom odeljku su sa starim trećim članom (heuristika „saobraćaj”). Od koraka 6a treći član je vreme vožnje do parkinga, a CSV-ovi i grafici u `ml/output/` su ponovo izračunati. Nove brojeve i poređenje vidi u koraku 6a. Glavna razlika: preporuka češće bira P&R (2,8% → 13,4%), ali onaj koji je vozaču usput. Konačni brojevi za rad su iz koraka 6b (ponderi izabrani na oktobru, rezultati na novembru i decembru, fiksna normalizacija). Analiza osetljivosti iz zaključka 5 (w1/w2, na test periodu) je uklonjena iz koda i zamenjena izborom pondera u 6b.*

**Grafici za rad:** `ml/output/eval_recommender_po_planiranju.png` (pun parking naspram vremena planiranja) i ~~`ml/output/eval_recommender_osetljivost.png` (kompromis rizik/hodanje)~~ `ml/output/izbor_pondera.png` (kompromis rizik / vreme do cilja za svih 231 kombinacija pondera, korak 6b). Boje su iz validirane palete (dataviz validator: PASS; aqua ima nizak kontrast, pa ima direktne oznake i šuplje markere).

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
- Najteži parking je **CPN0009 The Forum** (10,83; na 30 min 6,20), zatim CPN0006 St Giles (8,05) i CPN0005 Castle Quarter 2 (7,78). Najlakši je C06391 B&Q Boundary Road (0,97; ~~skoro uvek prazan~~).

  **ISPRAVLJENO u koraku 7 (2026-11-06):** B&Q nije „skoro uvek prazan” (prosečno ~130 vozila od 585 mesta). Njegovi podaci su velikim delom **kopija prethodne nedelje**: u 210 od ~400 dana bar 90% termina ima tačno isti broj vozila kao pre 7 dana (npr. tri utorka zaredom 70, 117, 147, 158, 160, 163, 161…). Greška od 0,97 zato nije prava mera tačnosti modela. Ukupni MAE aplikacije (4,83) uključuje te lake redove. Bez kopiranih B&Q dana isti postupak daje **5,11** (korak 7), a bez B&Q uopšte 5,20. Preporuka (koraci 3 i 6) nije pogođena, jer se B&Q ne preporučuje.
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

### Korak 6 — Vreme vožnje umesto saobraćaja ✅ (6a–6d, 2026-11-05/06)

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

*Napomena (6b): brojevi iz 6a su sa ručnim ponderima i relativnom normalizacijom, na celom test periodu. U 6b su promenjeni i normalizacija i ponderi, pa ih ne treba koristiti u radu; konačni brojevi su u 6b.*

#### 6b — Izbor pondera na validacionom periodu ✅ (2026-11-05)

**Postavka.** Test period modela je podeljen na dva dela:
- **oktobar 2017** (2000 vozača, seme 43): samo za izbor pondera, `ml/select_weights.py`;
- **novembar i 1.–5. decembar 2017** (2000 drugih vozača, seme 42): samo za konačne brojeve, `ml/eval_recommender.py`.

Model je u oba slučaja onaj iz aplikacije, treniran pre 1.10.2017. Isprobane su sve kombinacije w1 + w2 + w3 = 1 sa korakom 0,05, ukupno 231. Bitan je samo odnos pondera, pa uslov „zbir 1” ne izostavlja nijednu.

**Pravilo izbora** je dogovoreno sa autorom i upisano u kod **pre** gledanja rezultata:
1. Zadržavaju se kombinacije čiji je udeo dolazaka na pun parking (≥ 95%) najviše 0,5 p.p. veći od najboljeg. Na ~2000 vožnji manje razlike su u granicama slučajnosti.
2. Među njima se bira kombinacija sa najkraćim prosečnim ukupnim vremenom od polaska do cilja.

Meri se XGBoost prognoza, svi parkinzi, sva vremena planiranja zajedno. Ukupno vreme je vožnja (30 km/h, prava linija), pa hodanje (5 km/h) do cilja, odnosno sa P&R čekanje autobusa (5 min) i autobus (20 km/h). **Ovo su pretpostavke, ne izmereni podaci.** Kazna za dolazak na pun parking nije uključena u vreme; to meri prvi korak pravila.

**Prvi pokušaj i otkrivena mana (iskreno, za rad).** Prvi izbor, sa relativnom normalizacijom iz 6a (blizina i vožnja deljene najudaljenijim kandidatom u listi), dao je 0,30 / 0,65 / 0,05. Na novembru i decembru on je radio dobro sa svim parkinzima: 0,7% punih, 20,3 min, bez P&R. U scenariju „samo gradski” bio je, međutim, skoro beskoristan: **16,6% punih**, naspram 21,5% bez sistema i 3,0% sa ručnim ponderima.

Uzrok je **relativna normalizacija**. Sa P&R u listi najudaljeniji kandidat je ~7 km od cilja, pa je 300 m razlike u hodanju malo. Bez P&R najudaljeniji je ~1,5 km, pa je istih 300 m mnogo. Isti ponderi su zato davali različit izbor između dva ista parkinga, u zavisnosti od toga koji su još parkinzi u listi. U aplikaciji se to dešava kad filter „radius” izbaci P&R. U teoriji višekriterijumskog odlučivanja ovo je poznat problem relativne normalizacije (*rank reversal*).

**Ispravka:** fiksne skale, `blizina = 1 − hodanje/10 km`, `vreme_vožnje = vožnja/30 min` (`WALK_SCALE_KM`, `DRIVE_SCALE_MIN` u `backend/recommender.py`). Zatim je izbor ponovljen na oktobru po **istom** pravilu, uz informativni prikaz scenarija „samo gradski”, i jednom ponovo izmeren na novembru i decembru.

**Napomena o poštenosti:** novembar i decembar su tako pogledani **dva puta**. Ispravka ima strukturni razlog (rang dva parkinga ne sme da zavisi od trećeg) i pravilo izbora nije menjano, ali to treba navesti u radu. Rezultati prvog pokušaja su sačuvani van repoa.

**Izbor na oktobru** (`ml/output/izbor_pondera.csv`, `izbor_pondera_pareto.csv`, grafik `izbor_pondera.png`):

| Ponderi (w1 / w2 / w3) | Pun pri dolasku | Vreme do cilja | Na P&R | Samo gradski: pun |
|---|---|---|---|---|
| **izabrano pravilom: 0,15 / 0,40 / 0,45** | 0,40% | 19,83 min | 9,1% | 0,57% |
| drugo najbolje: 0,20 / 0,60 / 0,20 | 0,39% | 19,89 min | 0,0% | 0,39% |
| treće: 0,25 / 0,75 / 0,00 | 0,32% | 19,96 min | 0,0% | 0,32% |
| ručno (pre 6b): 0,55 / 0,30 / 0,15 | 0,00% | 22,33 min | 30,2% | 0,03% |

**Provera pretpostavki** (`izbor_pondera_provera.csv`). Uz sporiji autobus (10 min čekanja, i 15 km/h) bira se 0,20 / 0,60 / 0,20 (0% na P&R). Uz vrlo brz autobus (3 min, 25 km/h) bira se 0,15 / 0,30 / 0,55, sa 43% na P&R. Uz strožu toleranciju (0,25 p.p.) bira se 0,25 / 0,65 / 0,10, a uz blažu (1 p.p.) 0,20 / 0,80 / 0,00. Vektorizovano bodovanje u skriptu daje isti izbor kao `recommender.score_candidates` u 7414/7414 odluka.

**Konačni rezultati, novembar–decembar** (`ml/output/eval_recommender_strategije.csv`, `eval_recommender_subota_vrhunac.csv`). Ponderi 0,15 / 0,40 / 0,45; „ručni” znači 0,55 / 0,30 / 0,15 u istoj formuli; „pre 6b” je sistem iz 6a (ručni ponderi, relativna normalizacija), izmeren na istim vozačima u prvom pokušaju.

| Strategija | Pun pri dolasku: odmah / 2 h / 4 h | Vreme do cilja | Na P&R |
|---|---|---|---|
| Najbliži destinaciji (bez sistema) | 21,5% / 21,5% / 16,6% | 16,9 min | 0% |
| Preporuka, naivna prognoza | 0,7% / 6,0% / 9,2% | 19,9 min | 7–9% |
| **Preporuka, XGBoost (aplikacija)** | **0,8% / 0,7% / 0,6%** | **20,0 min** | 9,5% |
| Preporuka, savršena prognoza | 0,8% / 1,0% / 0,8% | 20,0 min | 9,5% |
| Preporuka, XGBoost, ručni ponderi | 0,0% / 0,0% / 0,0% | 22,7 min | 30% |
| Preporuka, XGBoost, pre 6b | 0,0% / 0,0% / 0,0% | 21,7 min | 12% |

Samo gradski parkinzi: XGBoost 1,1% / 0,9% / 0,9% (20,3 min); ručni ponderi 0%; pre 6b 3,0% / 2,8% / 1,9%; najbliži 21,5%.

Subota 11–16 h (138 vožnji): najbliži 68% punih. XGBoost 5,1% (polazak odmah) → 0% (4 h), 21,5 min, 20% na P&R. Ručni ponderi 0%, ali 27,8 min i 83% na P&R. Pre 6b 0%, 23,5 min, 42% na P&R. Samo gradski, subota: XGBoost 6,5%, pre 6b 13,0%.

**Zaključci za rad:**
1. **Kako su određeni ponderi:** pravilom zapisanim unapred, na posebnom validacionom periodu (oktobar), a mereni su na periodu koji izbor nije video (novembar–decembar). Na oktobru je izabrana kombinacija imala 0,40% punih, a na novembru i decembru 0,6–0,9%. Novembar i decembar su teži period (najbliži parking pun u 21,5% slučajeva, praznična kupovina), pa je mali pad očekivan.
2. **Da li bi druga kombinacija bila bolja:** oko izabrane postoji **ravan deo**. Tri najbolje kombinacije se razlikuju za manje od 0,1 p.p. rizika i ~8 sekundi vremena, pa tačne vrednosti pondera nisu presudne. Presudno je da dostupnost ima dovoljnu težinu u odnosu na blizinu (uz w1 = 0 i jaku blizinu rizik je do 16%, skoro kao bez sistema; uz w1 = 0,05 do 11%) i da normalizacija bude fiksna. Pareto kriva (`izbor_pondera.png`) pokazuje kompromis: manje rizika košta više vremena, ručni ponderi su na ravnom delu, ali ~2,5 min sporiji jer šalju 30% vozača na P&R.
3. **Šta je pravilo izabralo, u rečima:** sistem daje prednost kraćem putu i prihvata mali rizik (< 1%). Ručni ponderi su potpuno izbegavali rizik slanjem vozača na P&R, što košta 2,7 min po vožnji, a subotom 6 min i 83% vozača u autobusu. Da li je bolji 0% rizika ili kraći put je vrednosni izbor. Pravilo ga čini eksplicitnim (tolerancija 0,5 p.p.), a provera pokazuje šta bi izabrala stroža tolerancija.
4. **Ponderi se ne čitaju kao „važnost” komponenti**, jer zavise od skale. Bolje je preko kompromisa: 1 km manje hodanja (0,04 skora) vredi koliko i 27 p.p. zauzetosti, a 1 min kraće vožnje (0,015) koliko i 10 p.p. Zbog toga je w3 = 0,45 najveći broj, iako vožnja ne „preovlađuje”.
5. **Vrednost ML prognoze i dalje raste sa vremenom planiranja:** za polazak odmah naivna prognoza je jednako dobra (0,7% naspram 0,8%), ali za 2–4 h unapred naivna dovodi na pun parking u 6–9% slučajeva, a XGBoost u 0,6–0,7%. XGBoost je na nivou savršene prognoze.
6. **Poređenje sa najbližim parkingom po vremenu nije fer,** jer vreme ne uključuje traženje novog mesta kad je parking pun. Najbliži je pun u 21,5% slučajeva; uz pretpostavljenih 15 min za traženje, njegovo očekivano vreme bi bilo ~20 min, isto kao uz preporuku.
7. **Ograničenje:** izbor zavisi od pretpostavki o P&R autobusu. Uz sporiji autobus P&R se praktično ne preporučuje, a uz vrlo brz šalje se 43% vozača. Pravi red vožnje P&R autobusa u Norwichu bi ovo preciziralo (budući rad).

#### 6c — Prag „punog” parkinga (85 / 90 / 95%) ✅ (2026-11-06)

Pitanje komisije koje mentor očekuje: zašto je „pun” definisan kao ≥ 95%. Provereno je na tri načina. Evaluacija sada meri sva tri praga (`FULL_THRESHOLDS` u `ml/eval_recommender.py`, kolone `pun_85_pct`, `pun_90_pct`, `pun_95_pct`), a izbor pondera je ponovljen sa pragom od 90% i 85% u pravilu (`izbor_pondera_provera.csv`). Glavni izbor (prag 95%) ponovljen je i dao je identičan rezultat, pa je skript ponovljiv.

**1. Zašto ne 100%: šta kažu podaci** (sirova očitavanja u test periodu 1.10.–5.12.2017, pomoćni skript van repoa):

| Tip | ≥ 85% | ≥ 90% | ≥ 95% | ≥ 100% |
|---|---|---|---|---|
| gradski (28.459 očitavanja) | 23,3% | 19,0% | 14,4% | 3,4% |
| Park & Ride (15.500) | 0,9% | 0,4% | 0,05% | 0% |

Gradski parking se retko prijavi kao potpuno pun. Mesta se stalno oslobađaju i zauzimaju, a neka ostaju neiskorišćena. Castle Quarter 2 (80 mesta) nikad nije prešao 98,8%, a Rose Lane ni 87,2%. Prag od 100% bi propustio većinu situacija u kojima je parking praktično pun. Na 95% gradskom parkingu ostaje 4–52 slobodnih mesta, zavisno od kapaciteta (80–1047), i njih vozač mora da traži. Prag od 85% je često citirana ciljna zauzetost iz literature o parkiranju (Shoup), kada je mesto još lako naći; to je stroža definicija „punog”.

**2. Konačni rezultati na sva tri praga** (novembar–decembar, svi parkinzi; `eval_recommender_strategije.csv`):

| Strategija | Polazak odmah: 95 / 90 / 85% | Planiranje 4 h: 95 / 90 / 85% |
|---|---|---|
| Najbliži destinaciji (bez sistema) | 21,5 / 27,8 / 33,9% | 16,6 / 21,6 / 26,1% |
| Preporuka, naivna prognoza | 0,7 / 1,4 / 1,9% | 9,2 / 12,0 / 15,3% |
| **Preporuka, XGBoost** | **0,8 / 1,1 / 1,7%** | **0,6 / 1,2 / 2,3%** |
| Preporuka, savršena prognoza | 0,8 / 1,1 / 1,7% | 0,8 / 1,2 / 2,1% |

Samo gradski, XGBoost: 1,1 / 1,5 / 2,1% (odmah), 0,9 / 1,5 / 2,7% (4 h); najbliži isto kao gore. Subota 11–16 h, XGBoost: 5,1% na sva tri praga (odmah), a najbliži 68 / 73 / 75%.

**3. Da li bi se ponderi promenili** (pravilo na oktobru, isti postupak, samo drugi prag u prvom koraku):

| Prag u pravilu | Izabrani ponderi | Pun (95%) | Vreme do cilja | Na P&R |
|---|---|---|---|---|
| **95% (glavni)** | **0,15 / 0,40 / 0,45** | 0,40% | 19,83 min | 9,1% |
| 90% | 0,20 / 0,55 / 0,25 | 0,34% | 20,02 min | 0,1% |
| 85% | 0,25 / 0,65 / 0,10 | 0,24% | 20,18 min | 0,0% |

**Zaključci za rad („zašto 95%?”):**
1. **Zaključci ne zavise od praga.** Na svakom pragu redosled strategija je isti: bez sistema 17–34% punih, uz preporuku sa XGBoost-om 0,6–2,3%, odnosno 12–26 puta manje (zavisno od praga i vremena planiranja). XGBoost je na nivou savršene prognoze, a prednost nad naivnom prognozom raste sa vremenom planiranja (4 h: 2,3% naspram 15,3% na pragu od 85%).
2. **Stroži prag daje veće brojeve za sve strategije**, ali sistem i dalje vozača skoro uvek šalje na parking sa bar 15% slobodnih mesta (~98% vožnji).
3. **95% je izabran kao „praktično pun”**: parkinzi u podacima retko dostignu 100%, a na 95% ostaje premalo mesta da bi se lako našlo.
4. **Ponderi se pomeraju malo** i ostaju u istom ravnom delu iz 6b. Uz stroži prag pravilo daje nešto više težine dostupnosti i blizini, a manje vremenu vožnje, i tada P&R praktično nestaje (uz manji w3 P&R gubi prednost kraće vožnje). Vreme do cilja raste za najviše 0,35 min. Izbor praga nije presudan za sistem.

#### 6d — Dokumentacija ✅ (2026-11-06)

`README.md`, `CLAUDE.md` i ovaj fajl su usklađeni sa formulom (vreme vožnje, fiksne skale), izabranim ponderima i podelom oktobar / novembar–decembar. Stari opisi „saobraćaja” su ispravljeni tamo gde opisuju trenutni sistem, a ostavljeni u unosima istorije. Ugovor API-ja u `frontend/UI_REDESIGN_PLAN.md` ima nova imena polja (`drive_time`, `w3_drive_time`).

**Pitanja komisije koja je mentor naveo i gde su odgovori:**

| Pitanje | Odgovor |
|---|---|
| Kako su određeni ponderi? | 6b: pravilom zapisanim unapred, na oktobru, mereni na novembru i decembru |
| Da li bi druga kombinacija bila bolja? | 6b: Pareto kriva i ravan deo (najbolje tri se razlikuju za < 0,1 p.p. i ~8 s) |
| Zašto prag 95%? | 6c: parkinzi retko dostignu 100%; zaključci isti na 85 / 90 / 95% |
| Koliko rezultati zavise od Norwicha? | korak 7 (još nije urađen) |
| Da li bi model radio u drugom gradu? | korak 7 (još nije urađen) |

**Šta u radu navesti kao ograničenja preporuke:** pretpostavke o hodanju i P&R autobusu (izbor pondera od njih zavisi); vreme vožnje po pravoj liniji pri 30 km/h; novembar i decembar su pogledani dva puta (6b, ispravka normalizacije); nedelja izostavljena; evaluacija meri efikasnost algoritma, ne zadovoljstvo korisnika.

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

### Korak 7 — Model predikcije u drugim gradovima ✅ (2026-11-06)

Odgovor na dva pitanja komisije koja mentor očekuje: *koliko rezultati zavise od Norwicha* i *da li bi model radio u drugom gradu*. Proverava se samo **model predikcije**; za parkinge u drugim gradovima nema koordinata, pa nema ni preporuke. Skript `ml/other_cities.py` (~20 min), izlazi `ml/output/gradovi_tacnost.csv`, `gradovi_po_horizontu.csv/.png`, `gradovi_prenos.png`, `gradovi_performanse.csv`.

**Postavka.**
- Isti postupak u svakom gradu: isti ulazi, isti hiperparametri (iz Norfolk modela, bez podešavanja po gradu), hronološka podela (test = poslednja ~2 meseca upotrebljivog perioda, `CITY_CONFIGS` u `ml/data_prep.py`). Upotrebljivi parkinzi i periodi su iz `MASTER_PLAN.md`, poglavlje 3.
- Isti zadatak svuda: prognoza za ciljno vreme **08–23 h** (dnevni opseg merenja u Norfolku). Noćna merenja (Glasgow, Nottingham) mogu biti ulaz, ali se ne predviđaju.
- **Prenos:** model treniran samo na Norfolku, bez identiteta parkinga (`carpark`, `capacity`, jer su šifre u drugom gradu nepoznate), primenjen na drugi grad bez ponovnog treninga. Upoređuje se sa modelom tog grada sa istim ulazima. Norfolk model za grad X treniran je samo na podacima pre test perioda grada X (Birmingham: pre 1.3.2017, Glasgow: pre 1.6.2017, Nottingham: pre 1.10.2017), da ni preko drugog grada ne vidi isti kalendarski period.

| Grad | Parkinga | Trening | Test | Test redova |
|---|---|---|---|---|
| Norfolk (Norwich) | 15 | 26.10.2016–30.9.2017 | 1.10.–5.12.2017 | 352.905 |
| Birmingham | 29 | 4.10.2016–28.2.2017 | 1.3.–28.4.2017 | 141.346 |
| Glasgow | 8 | 26.10.2016–31.5.2017 | 1.6.–7.8.2017 | 347.183 |
| Nottingham | 11 | 26.10.2016–30.9.2017 (rupa 16.5.–3.7.) | 1.10.–28.11.2017 | 276.984 |

**Nalaz o kvalitetu podataka: kopirane nedelje.** Prvo pokretanje (bez čišćenja) dalo je neobičan rezultat: u Nottinghamu model nije bio bolji od pravila „pre nedelju dana” (4,20 naspram 4,14 p.p.). Hipoteza da su krivi parkinzi kojima se nivo promenio pokazala se **netačnom**: na njima je model bio bolji (7,87 naspram 9,35). Pravilo je pobeđivalo na parkinzima gde mu je greška bila skoro nula (RYLCT 0,00, SB1-1 0,03, PRLMNT 0,10 p.p.). Provera je pokazala da je u Nottinghamovom testu broj zauzetih mesta u 85–100% 30-min termina **tačno isti kao pre 7 dana** (PRLMNT, RYLCT, SB1-1: 99,9%; 211, PHNXPR, 212: 84–87%), dok je u Birminghamu i Glasgowu to 0–8%. To nije stvarno merenje, nego kopija prethodne nedelje (verovatno popunjavanje rupa kod izvora). Isto važi za B&Q Boundary Road u Norfolku (vidi ispravku u koraku 5). Kriterijumi „upotrebljivog parkinga” iz `MASTER_PLAN.md` ovo nisu hvatali.

**Čišćenje** (isto za sva četiri grada, samo u ovom eksperimentu; aplikacija se ne menja): dan parkinga u kom je bar 90% termina 08–23 h tačna kopija istog termina pre 7 dana tretira se kao nedostajući podatak (ne ulazi ni u trening, ni u test, ni kao ulaz). Dani sa promenom manjom od 3 vozila (npr. P&R nedeljom, 0 ceo dan) ne računaju se kao kopija. Uklonjeno: Norfolk 210 od 5774 dana parkinga (3,6%, svi B&Q), Birmingham 0, Glasgow 0, Nottingham 995 od 3718 (26,8%, 7 od 11 parkinga). Posle čišćenja Nottinghamov test čine uglavnom C11001, C11004, C11005, C11006 i deo FRSTPR, 211, 212 i PHNXPR; PRLMNT, RYLCT i SB1-1 skoro da nemaju test podataka. Rezultati prvog pokretanja su sačuvani van repoa.

**1. Sopstveni model svakog grada** (MAE u p.p., ciljno vreme 08–23 h):

| Grad | Ukupno | 30 min | 2 h | 4 h | 8 h | Pre nedelju dana | Tipična kriva | Bolji od najboljeg pravila |
|---|---|---|---|---|---|---|---|---|
| Norfolk | 5,11 | 3,01 | 4,48 | 5,33 | 6,05 | 7,07 | 7,68 | 28% |
| Birmingham | 3,77 | 2,30 | 3,35 | 4,39 | 5,15 | 8,64 | 8,37 | 55% |
| Glasgow | 4,94 | 3,66 | 4,25 | 4,79 | 5,18 | 8,27 | 8,20 | 40% |
| Nottingham | 6,41 | 4,15 | 5,22 | 6,24 | 6,79 | 9,05 | 12,44 | 29% |

Norfolk je ovde 5,11, a ne 4,83 kao u aplikaciji, jer su uklonjeni kopirani B&Q dani (bez čišćenja isti skript daje 4,85, kao ponovni trening u koraku 5). Model je bolji od oba pravila **u svakom gradu i na svakom horizontu** (`gradovi_po_horizontu.csv`).

**2. Prenos Norfolk modela bez ponovnog treninga** (MAE u p.p.; `gradovi_prenos.png`):

| Grad | Sopstveni | Sopstveni bez identiteta | **Norfolk model** | Pre nedelju dana | 30 min: sopstveni bez id. / Norfolk | 4 h: sopstveni bez id. / Norfolk |
|---|---|---|---|---|---|---|
| Birmingham | 3,77 | 4,51 | **7,34** | 8,64 | 2,34 / 5,27 | 5,34 / 8,10 |
| Glasgow | 4,94 | 5,16 | **6,38** | 8,27 | 3,52 / 3,76 | 5,08 / 6,62 |
| Nottingham | 6,41 | 6,63 | **8,59** | 9,05 | 3,88 / 4,05 | 6,50 / 8,04 |

**3. Performanse** (`gradovi_performanse.csv`): trening jednog modela traje 9–70 s po gradu (8 niti, 0,3–2,2 miliona redova). Predikcija jednog „ticka” traje 3–5 ms za 15–63 parkinga (jedan horizont, kao boje na mapi) i 6–14 ms za 15–63 parkinga × 31 horizont. Rad u realnom vremenu nije problem ni sa 63 parkinga.

**Zaključci za rad:**
1. **„Da li bi model radio u drugom gradu?” Da, ako se trenira na podacima tog grada.** Isti postupak, bez ikakvog podešavanja, daje MAE 3,8–6,4 p.p. u sva četiri grada i 28–55% je bolji od najboljeg jednostavnog pravila, na svakom horizontu. Nalaz da trenutno stanje odlučuje na kratkim, a istorija istog termina na dugim horizontima važi svuda (u svim gradovima greška raste sa horizontom do ~8–10 h).
2. **„Koliko zavisi od Norwicha?” Postupak ne zavisi, naučeni model delimično zavisi.** Norfolk model bez ponovnog treninga je u drugim gradovima 1,2–2,8 p.p. lošiji od lokalnog modela sa istim ulazima, ali je i dalje bolji od pravila „pre nedelju dana” (Birmingham 7,3 naspram 8,6; Glasgow 6,4 naspram 8,3; Nottingham 8,6 naspram 9,0).
3. **Kratkoročna dinamika se prenosi, dnevni ritam grada ne.** Na 30 min Norfolk model je u Glasgowu i Nottinghamu skoro jednak lokalnom (+0,2 p.p.): kako se parking puni i prazni iz trenutnog stanja je slično svuda. Na 4 h razlika je 1,5–2,8 p.p., jer se svaki grad puni i prazni u svoje vreme. Izuzetak je Birmingham, gde je prenos loš i na 30 min (5,27 naspram 2,34). Verovatan, ali neprovereni uzrok je drugačiji režim merenja (samo ~08–16:30, jedno očitavanje na 30 min) i drugačiji jutarnji ritam.
4. **Praktična posledica za novi grad:** model bi trebalo trenirati na lokalnim podacima. Prema koraku 5 (dužina treninga), već 1 mesec podataka daje 5,44 p.p. na Norfolku, a 3 meseca 5,19. Do tada Norfolk model može da služi kao početno rešenje, bolje od jednostavnih pravila.
5. **Kvalitet podataka** je važan nalaz sam po sebi: deo javno objavljenih „merenja” je kopija prethodne nedelje. Bez provere bi pravilo „pre nedelju dana” izgledalo kao jednako dobro kao model, a greška modela na B&Q kao gotovo nula. U radu treba opisati i pravilo čišćenja.
6. **Ograničenja:** praznici su engleski i za Glasgow (škotski se delimično razlikuju; uticaj praznika u koraku 5 nije bio merljiv); Birmingham meri samo danju, pa ima malo dugih horizonata; posle čišćenja Nottinghamov test se uglavnom zasniva na 4–5 parkinga; hiperparametri nisu podešavani po gradu, pa su rezultati drugih gradova pre donja nego gornja granica.

### Korak 9 — Pisani rad (u toku)

- Struktura rada (11 poglavlja, ~60 strana) poslata mentoru; pravila fakulteta su u `../PRAVILA_PISANJA.md`, a Word fajl rada u `C:\FAX\Master rad\` (vidi `../PLAN_ZAVRSETKA.md`, korak 9).
- `ml/thesis_figures.py`: slike za rad koje ne pravi nijedan eksperiment, bez naslova u samoj slici (naslov ide u natpis ispod slike). Za potpoglavlje 3.1:
  - `rad_3_1_nedeljni_tok.png`: The Forum i Thickthorn, 11.–17.9.2017. The Forum je radnim danom (pon–sre) na vrhu 74–82%, a od četvrtka do nedelje 100%; Thickthorn radnim danom ~68–77%, subotom 46%, nedeljom ne radi.
  - `rad_3_2_autokorelacija.png`: prosečna autokorelacija po tipu (8 gradskih, 6 P&R; trening podaci; B&Q izostavljen zbog kopiranih podataka; pomaci sa manje od 1000 parova merenja izostavljeni). Gradski / P&R: 30 min 0,96 / 0,98; 12 h −0,28 / −0,04; 1 dan 0,75 / 0,77; 3 dana 0,64 / 0,48; **7 dana 0,86 / 0,85**; 14 dana 0,83 / 0,83. Isti dan pre nedelju dana je sličniji od juče, što opravdava ulaze `y_yesterday` i `y_lastweek`.
  - `rad_3_3_primer_za_ucenje.png` (potpoglavlje 3.2): šema jednog primera za učenje (ulazi poznati u trenutku t, kalendar ciljnog trenutka i horizont; izlaz y(t + h)).
  - Sve slike za rad su široke 16 cm (širina teksta), da natpisi od 8–9 pt ostanu čitljivi na papiru.
- Za potpoglavlje 4.1 (`ml/thesis_figures.py`, `tree_figures`): `rad_4_1_malo_stablo.png`, stablo dubine 2 (500 hilj. trening primera, ulazi zauzetost sada, pre 7 dana i horizont); sva tri pitanja su o zauzetosti pre 7 dana, listovi 12 / 35 / 60 / 87%. `rad_4_2_dubina_stabla.png` + `.csv`: jedno stablo (svi ulazi) po dubini, trening / test MAE: dubina 1: 15,34 / 14,83; 6: 6,90 / 6,68; **12: 4,80 / 5,90 (najmanja greška na testu)**; 25: 0,47 / 7,03. XGBoost (400 stabala dubine 6): 4,83, bolji od najboljeg pojedinačnog stabla.
- Za potpoglavlje 4.2: `rad_4_3_broj_stabala.png` + `.csv`, MAE na testu kada se usrednji prvih B stabala (podešavanja kao u koraku 4). Random Forest: 1 stablo 6,63, 10 stabala 5,13, **100 stabala 4,92** (isto kao korak 4). Bagging (svi ulazi po podeli): 6,63 / 5,28 / 5,12. Random Forest je bolji od baginga za 0,2 p.p.; oba prestižu najbolje pojedinačno stablo (5,90) već sa 2–3 stabla; XGBoost 4,83.
- Za potpoglavlje 4.3: `rad_4_4_boosting_iteracije.png` + `.csv`, XGBoost sa parametrima modela iz aplikacije do 800 stabala (8 niti). Trening / test MAE: 1 stablo 24,91 / 24,45; 50: 6,53 / 6,52; 100: 5,24 / 5,37; **400: 4,41 / 4,86** (model u aplikaciji); 800: 4,04 / 4,73. **Nalaz:** greška na testu i posle 400 stabala blago opada, pa bi model sa više stabala bio malo tačniji (~0,1 p.p.). Broj stabala nije biran na validacionom skupu (parametri su iz referentnog eksperimenta); izbor prema ovoj krivoj bio bi podešavanje na testu, pa se model ne menja. Moguće poboljšanje za budući rad: broj stabala izabrati na validacionom periodu.
- Za potpoglavlje 4.5: `rad_4_5_linearni_koeficijenti.png` + `.csv`, obična linearna regresija sa tri ulaza (zauzetost sada, juče, pre 7 dana) posebno po horizontu i jedna za sve. Koeficijent uz zauzetost sada: 30 min 0,74; 2 h 0,18; 8 h 0,04; 15 h 0,02; jedan model 0,07. MAE na testu: 30 min jedan model 5,74 naspram posebnog 4,32; 8 h 7,17 naspram 7,09; ukupno 6,57 naspram 6,38. Linearni model ne može da nauči da uticaj trenutnog stanja zavisi od horizonta.
- Za potpoglavlje 4.6 slike su ponovo nacrtane u širini teksta iz sačuvanih rezultata koraka 5 (bez novog treniranja): `rad_4_6_shap.png` (prosečan |SHAP| po grupi horizonata, iz `analiza_doprinos.csv`) i `rad_4_7_ablacija.png` (MAE po horizontu bez grupa ulaza, iz `analiza_ablacija_po_horizontu.csv`).
- Poglavlje 6 (Podaci): `rad_6_1_lokacije.png` (položaj 15 parkinga u km od centra; P&R na 4–7 km, 8 gradskih u krugu od ~600 m), `rad_6_2_kopirane_nedelje.png` (tri uzastopna utorka 10/17/24.10.2017: B&Q se poklapa, The Forum ne), `rad_6_tabela_parkinga.csv` (tabela 6.2; prosečna zauzetost gradskih 29–75%, P&R 24–39%, B&Q 21,6%; B&Q ima 404 dana merenja, od toga 210 kopiranih). Nacrt poglavlja 6 je ubačen u Word (tabele 6.1 i 6.2, slike 6.1 i 6.2, formula 6.1).
- U Word fajl su ubačeni nacrti potpoglavlja 3.1–3.4 (celo poglavlje 3) i 4.1–4.6 (celo poglavlje 4), zatim celo poglavlje 5 (5.1–5.5, tabela 5.1: primer promene ranga A/B sa i bez P&R u listi, relativna naspram fiksne normalizacije); teorijski deo (pogl. 3–5, ~17 strana) je kompletan nacrt: tekst, slike 3.1–3.4 i 4.1–4.7, formule 3.1–3.6, 4.1–4.9 i 5.1–5.3, tabela 4.1 (parametri XGBoost-a: 400 stabala, η 0,05, dubina 6, subsample i colsample 0,8, λ 1, γ 0, histogram 256 intervala, početna prognoza 0,42), reference [9]–[17]. Nacrt autor prilagođava svojim rečima.
- **Nasumična naspram hronološke podele** (`python ml/analyze_model.py podela`, `ml/output/analiza_podela.csv`; za potpoglavlje 3.3). Isti model i parametri. Hronološki (trening do 30.9.2017, test okt.–dec.): MAE **4,85**. Nasumično 84/16 unutar perioda pre oktobra: provera na nasumičnih 16% daje **4,41**, a isti model na okt.–dec. **4,84**. Nasumična podela precenjuje tačnost za ~9% (na 30 min 2,69 naspram 2,87; na 8 h 5,01 naspram 5,71). Sam model nije lošiji (4,84 ≈ 4,85), samo je procena optimistična. Deo razlike može poticati i od toga što je period okt.–dec. teži od proseka godine; efekat nije razdvojen.
- `rad_3_4_podela_podataka.png` (potpoglavlje 3.3): vremenska linija podele (model: trening do 30.9.2017 / test; preporuka: validacija okt. / test nov.–dec.).
- Poglavlje 7 (Model predikcije): slike su ponovo nacrtane iz sačuvanih rezultata koraka 4, 5 i 7 (bez novog treniranja):
  - `rad_7_1_poredjenje_modela.png` (iz `poredjenje_modela_po_horizontu.csv`; „poslednja vrednost” nije prikazana, jer dostiže 34 p.p.);
  - `rad_7_2_greske.png` (iz `analiza_greska_po_satu.csv` i `analiza_greska_po_popunjenosti.csv`);
  - `rad_7_3_gradovi.png` i `rad_7_4_prenos.png` (iz `gradovi_po_horizontu.csv` i `gradovi_tacnost.csv`).
  
  Nacrt poglavlja 7 (7.1–7.6) je ubačen u Word: tabele 7.1–7.6 (ulazi, poređenje modela, dužina treninga, jedan naspram specijalizovanih modela, zamena za `y_lastweek`, gradovi) i slike 7.1–7.4. U tekstu je navedeno da ponovni trening daje 4,85 umesto 4,83 (razlika od broja niti). Sve tabele u Word fajlu podešene su da se ne lome preko strane.
- Poglavlje 8 (Sistem preporuke):
  - `rad_8_1_delovi_skora.png`: šema tri dela skora;
  - `rad_8_2_izbor_pondera.png`: izbor pondera iz `izbor_pondera.csv` i `izbor_pondera_pareto.csv`, ceo raspon i uvećana oblast oko izabrane kombinacije.

  Nacrt 8.1–8.4 je ubačen u Word: formule 8.1–8.5, tabele 8.1–8.3, slike 8.1 i 8.2.
  - **Tabela 8.1** je primer iz demo režima: Bowthorpe → centar, sub 18.11.2017. 10 h, konačni ponderi, `recommend_parks` iz backenda.
    - Rose Lane je prvi (predviđeno 27,8%, stvarno 23,4%).
    - The Forum je treći iako je predviđen kao 100% pun, jer linearni skor dozvoljava da blizina nadoknadi nultu dostupnost. To je navedeno kao mogući budući rad: označiti ili izostaviti parkinge predviđene kao pune.
    - Costessey P&R nema merenje od 17.11. u 19 h, pa nije kandidat.
    - Thickthorn (7,6 min vožnje) je ispred Sprowstona i Postwicka (17 i 22 min).
  - Iz `izbor_pondera.csv`: prvi korak pravila prolazi 168 od 231 kombinacije. Ručni ponderi 0,55 / 0,30 / 0,15 nisu na Pareto frontu: 0,45 / 0,35 / 0,20 takođe ima 0% punih, a kraća je za 1,07 min (21,26 naspram 22,33).
- Poglavlje 9 (Arhitektura i implementacija):
  - `rad_9_1_arhitektura.png` (`plot_architecture`): dijagram tri dela sistema.
  - Snimci ekrana `rad_9_2_aplikacija.jpg`, `rad_9_3_preporuke.png`, `rad_9_4_predikcija_stvarnost.png`:
    - Chrome bez prozora, sa privremenim profilom, preko DevTools protokola (pomoćni skript van repoa, 1440×900, dvostruka rezolucija).
    - Scenario kao u tabeli 8.1: sub 18.11.2017. 10 h, Bowthorpe → centar.
    - Lista preporuka u aplikaciji poklapa se sa tabelom 8.1 (Rose Lane 27,79%, skor 0,31).
    - Kartica „Predikcija vs stvarnost” za Rose Lane: MAE za taj dan 12,46 (prognoza iz 10 h), 17,61 (tipična kriva), 4,62 (sat unapred).
    - Stari snimci iz `C:\FAX\Master rad\` (28.10.) nisu korišćeni, jer prikazuju „Saobraćaj” i ponderе pre koraka 6.
  - Nacrt 9.1–9.5 je ubačen u Word: tabele 9.1–9.4 (tehnologije, endpointi, vreme prognoze, vreme odgovora API-ja) i slike 9.1–9.4.
  - **Ispravka backenda (performanse):** `backend/parks.py` je u `load_parks()` na svaki API zahtev ponovo čitao ceo `Norfolk.csv` da bi dobio kapacitete. Svaki odgovor je zato trajao ~0,5 s, a frontend osvežava podatke na 3 s. Sada se kapaciteti čitaju jednom (`_capacities`, `lru_cache`); `load_parks()` i dalje vraća novu listu na svaki poziv.
    - Medijana vremena odgovora, pre → posle izmene (lokalno, 20–30 zahteva):

      | Zahtev | Pre | Posle |
      |---|---|---|
      | `/state` | 551 ms | 16 ms |
      | `/state` sa prognozom | 600 ms | 74 ms |
      | `/recommend` | 606 ms | 68 ms |
      | `/history` | 585 ms | 24 ms |
      | `/compare` | 682 ms | 153 ms |
    - Preporuka za primer iz tabele 8.1 je identična pre i posle izmene.
  - README: ispravljen zastareo navod da provera u drugim gradovima „nije rađena”.
- Poglavlje 10 (Evaluacija preporuke i diskusija):
  - `rad_10_1_pun_po_planiranju.png` (`plot_recommendation_by_lead`, iz `eval_recommender_strategije.csv`): ista slika kao `eval_recommender_po_planiranju.png`, u širini teksta i sa decimalnim zarezom.
  - Nacrt 10.1–10.5 je ubačen u Word: tabele 10.1–10.5 (strategije, rezultati, subota, pragovi, izbor pondera uz druge pretpostavke) i slika 10.1.
  - **Napomena mentora:** cilj rada je da model predvidi zauzetost i predloži parking, a ne zadovoljstvo korisnika. To je istaknuto u prvom pasusu 10.1 i ponovljeno u 10.5. Jedna rečenica o cilju preporuke dodata je na početak 8.1. Isto treba napisati i u Uvodu i poglavlju 2.
  - **Novi navodi iz postojećih rezultata:**
    - Preporuka sa XGBoost-om smanjuje dolazak na pun parking 25–32 puta (prag 95%), odnosno 12–26 puta na sva tri praga.
    - Razlika XGBoost-a i savršene prognoze je < 0,4 p.p. na svakom vremenu planiranja. U ovoj postavci tačniji model ne bi mnogo popravio preporuku.
    - Ni savršena prognoza nema 0% punih (~0,8%), jer linearni skor ponekad bira pun parking vrlo blizu cilja (kao The Forum u tabeli 8.1).
    - Uz pretpostavljenih 15 min traženja mesta očekivano vreme vozača bez sistema je ~20,1 min (16,92 + 0,215 · 15), isto kao uz preporuku.
  - Uklonjen je raniji navod da su novembar i decembar „teži” od oktobra: za oktobar nema broja za strategiju „najbliži”, pa navod nije potkrepljen. Pad sa 0,40% (oktobar) na 0,6–0,9% (nov.–dec.) opisan je kao očekivan pri prelasku na podatke koje izbor pondera nije video.
- Poglavlje 2 (Definicija problema i pregled oblasti):
  - Nacrt 2.1–2.6 je ubačen u Word, sa formulom 2.1 (preporuka = parking sa najvećim skorom). Cilj rada (predikcija i preporuka slobodnog parkinga, ne zadovoljstvo korisnika) naveden je i u 2.1.
  - **Nove reference [18]–[24]**, sve proverene preko IEEE Xplore, DBLP, RePEc, Crossref i kataloga biblioteka:
    - Shoup 2006, „Cruising for Parking”;
    - Rajabioun i Ioannou 2015;
    - Zheng, Rajasegarar i Leckie 2015;
    - Vlahogianni i saradnici 2016;
    - Camero i saradnici 2019;
    - Geng i Cassandras 2013;
    - Shin i Jun 2014.

    Dopunjeni su bibliografski podaci referenci [1], [6] i [7]. Ostale reference još nemaju volumen i strane (provera svih referenci je u planu).
  - Cifra „30% saobraćaja kruži tražeći parking” namerno nije korišćena: to je prosek malog broja studija, a novija istraživanja ga smatraju precenjenim. U radu je raspon iz Shoupovog pregleda (3,5–14 min, 8–74% vozila).
  - Pomoćne skripte za pisanje rada, rezervne kopije i rezultati koji se navode kao „van repoa” premešteni su iz privremenog foldera sesije u `../pisanje_rada/` (uputstvo u `README.txt`). Novo: `keep_headings.py` sprečava da naslov ostane sam na dnu strane.
- Poglavlje 1 (Uvod), 11.11.2026: jedna strana (pravilo fakulteta: najviše 2).
  - Redosled pasusa: problem (kruženje, Shoup [18]; table pokazuju trenutno, a ne buduće stanje), cilj rada, šta je urađeno (brojevi iz pogl. 7 i 10), doprinos (upućuje na 2.6), organizacija rada po poglavljima.
  - Cilj rada (efikasnost preporuke, ne zadovoljstvo korisnika) ima poseban pasus.
  - Skripta `insert_1.py`; `Section` u `thesis_insert.py` sada prima i naslov poglavlja (`heading_style="Heading 1"`).
- Poglavlje 11 (Zaključak), 11.11.2026: jedna strana (pravilo fakulteta: najviše 1).
  - Četiri pasusa: šta je urađeno i cilj (efikasnost, ne zadovoljstvo korisnika), glavni rezultati, moguća primena, budući rad.
  - Budući rad pokriva sva mesta u tekstu koja upućuju na poglavlje 11:
    - saobraćaj i mreža puteva (8.2);
    - pravi senzori i rad uživo;
    - studija sa korisnicima i povratni efekat;
    - izostavljanje parkinga predviđenih kao puni ili nelinearna dostupnost (8.1, 10.5);
    - red vožnje P&R autobusa (10.4);
    - posebni modeli za najkraće horizonte (7.4);
    - broj stabala izabran na validacionom periodu (4.3);
    - LSTM i GRU.
  - Skripta `insert_11.py`.
- Sažetak i Abstract (UK English), 11.11.2026:
  - Po jedna strana (Sažetak 385 reči, Abstract 467), sa ključnim rečima na istoj strani.
  - Sadržaj po uputstvu: šta je urađeno, kojim metodama, glavni brojevi i doprinosi, bez opštih fraza. Prvi pasus navodi cilj: meri se efikasnost preporuke, ne zadovoljstvo korisnika.
  - Ključne reči: pametni grad, predikcija zauzetosti parkinga, XGBoost, sistem preporuke, višekriterijumsko rangiranje, offline evaluacija. Abstract koristi britanske izraze („car park”, „analysed”, „normalised”).
  - Tekst je običnim slovima, jer je u šablonu kurzivom samo napomena. Skripta `insert_sazetak.py`.
  - Spisak skraćenica ne sadrži DATEX II, GRU, OSRM, SAW i SVG, iako se koriste u tekstu (rešeno ispod).
- Literatura i skraćenice, 11.11.2026 (`../pisanje_rada/skripte/references.py`, `abbreviations.py`):
  - Svih 24 referenci ima pune bibliografske podatke (časopis, volumen, broj, strane, godina; za knjige izdavač i mesto), proverene u izvorima (IEEE Xplore, ACM, Project Euclid, Springer, DBLP, RePEc, katalozi biblioteka).
    - Kaufman i saradnici: broj članka nije potvrđen, pa nije naveden.
    - Hyndman i Athanasopoulos: mesto izdanja nije potvrđeno, pa nije navedeno; dodat je link https://otexts.com/fpp3/.
  - Prenumeracija redom prvog navođenja: svih 45 navoda u tekstu promenjeno je po istoj tabeli, a spisak je preuređen istim redom. Sada je [1] Shoup 2006 (prvi navod u Uvodu), a [24] Shani i Gunawardana. Provereno: prvo navođenje ide 1, 2, …, 24, i svaka referenca je navedena bar jednom.
  - Spisak skraćenica: dodate DATEX II, GRU, OSRM, SAW i SVG; izbačene CSV, ETA i NCC, koje se u radu ne koriste. Spisak ima 16 skraćenica, abecedno.
- Dodatak 1 uklonjen (odluka autora, 11.11.2026), zajedno sa pominjanjem u Uvodu (`remove_appendix.py`). Rad ima 56 strana.
- Decimalni zarez na slikama (11.11.2026):
  - `ml/thesis_figures.py`: `_save` sada automatske oznake na osama piše sa zarezom (`_use_decimal_comma`), kao u tekstu. Ručni natpisi su već imali zarez.
  - Slike 4.2 i 4.3 crtaju se iz svojih CSV-ova (`draw_tree_depth`, `draw_forest_size`, kao 4.4), pa se ne treniraju ponovo i brojevi ostaju isti.
  - Nova komanda `python ml/thesis_figures.py bez_treninga` (~40 s) crta sve slike iz podataka i sačuvanih rezultata. `main()` uz to ponovo trenira modele za slike 4.1–4.4.
  - Promenile su se samo slike sa decimalnim oznakama: 3.2, 4.2, 4.3, 4.4, 4.5 i 6.1. Zamenjene su u Word-u (`../pisanje_rada/skripte/zameni_slike.py`). Ostalih 18 slika u radu identično je fajlovima, dakle nijedna nije zastarela.
- **Nacrt rada je kompletan** (11.11.2026). Automatska provera celog rada:
  - slike (24), tabele (22) i formule (25) numerisane su bez preskoka i duplikata po poglavljima;
  - svaka slika i tabela pomenuta je u tekstu;
  - nema zaostalih žutih napomena.

  Ostaje autoru:
  - polja na naslovnoj strani (studijski program, broj indeksa, mesec i godina, zadatak, komisija);
  - čitanje i prepravka teksta svojim rečima;
  - slanje mentoru.

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
