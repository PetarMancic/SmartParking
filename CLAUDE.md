# CLAUDE.md — Smart Parking Recommendation (Proof of Concept)

## Šta je ovo

Proof-of-concept sistem za **preporuku parking mesta u pametnim gradovima** na osnovu
analize podataka o zauzetosti parkinga. Radi se o praktičnom delu seminarskog rada koji
je uvod u master rad. **Cilj nije potpun proizvod** — cilj je da ceo lanac (podaci →
predikcija → preporuka → prikaz) radi end-to-end na minimalnom nivou.

Sistem obavlja tri stvari:
1. **Praćenje popunjenosti** — učitava i obrađuje podatke o zauzetosti parkinga kroz vreme.
2. **Predviđanje dostupnosti** — ML model procenjuje buduću zauzetost parkinga.
3. **Preporuka lokacije** — rangira parkinge kombinujući predviđenu dostupnost, blizinu
   destinaciji i (opciono) saobraćaj.

**Ključni princip: predikcija i preporuka su ODVOJENI moduli.** Predikcija je ML zadatak.
Preporuka je rangiranje po ponderisanom skoru — NE koristi neuronsku mrežu.

## Prioriteti (pročitaj pre nego što kreneš)

- Ovo je **proof of concept**, ne produkcija. Bez suvišnih edge case-ova, bez
  autentifikacije, bez baze podataka osim ako zaista zatreba. Fokus na tome da radi.
- **Gradi fazu po fazu (vidi dole). Ne generiši ceo sistem odjednom.** Na kraju svake
  faze stani, potvrdi da radi, tek onda nastavi.
- Targetirane, minimalne izmene. Kada nešto menjaš, ne diraj delove koji već rade.
- Kod treba da bude čitljiv i objašnjiv — ovo ide u seminarski rad, pa je razumljivost
  važnija od „pametnih" rešenja.

## Tehnološki stack

| Sloj | Tehnologija |
|---|---|
| Podaci + ML | Python 3.11+, pandas, scikit-learn, XGBoost, joblib |
| Backend / API | Python, FastAPI, uvicorn |
| Frontend | Next.js (App Router), Leaflet (react-leaflet) za mapu |

Backend i frontend komuniciraju preko REST (JSON). Backend servira i predikciju i preporuku.

## Struktura projekta (ciljna)

```
smart-parking/
├── CLAUDE.md
├── data/
│   └── parking.csv              # dataset (Birmingham) — već postoji, NE menjati
├── ml/
│   ├── explore.py              # EDA: vizuelizacija dnevne krive punjenja
│   ├── train.py                # trening XGBoost modela + evaluacija
│   └── model.joblib            # sačuvan istrenirani model (generiše train.py)
├── backend/
│   ├── main.py                 # FastAPI app, endpointi
│   ├── predictor.py            # učitava model.joblib, daje predikciju
│   ├── recommender.py          # ponderisano rangiranje parkinga
│   └── parks.py                # koordinate parkinga (za mapu i udaljenost)
├── frontend/                   # Next.js app
│   └── ...
└── README.md
```

## Dataset

Fajl: `data/parking.csv` (realni senzorski podaci, Parking Birmingham / UCI).
**Postoji već u projektu — koristi ga, ne generiši sintetičke podatke.**

Kolone (tačno ove):

| Kolona | Opis |
|---|---|
| `SystemCodeNumber` | ID parkinga (npr. `BHMBCCMKT01`, `Broad Street`), 29 lokacija |
| `Capacity` | kapacitet parkinga (raspon ~220–4675) |
| `Occupancy` | broj zauzetih mesta u tom trenutku |
| `LastUpdated` | timestamp merenja (npr. `2016-12-13 08:02:51`), ~svakih 30 min |
| `OccupancyRate` | stepen popunjenosti u procentima (0–100) — **ovo je ciljna promenljiva** |
| `Date` | datum (već izdvojen) |
| `Time` | vreme (već izdvojeno) |
| `DayOfWeek` | dan u nedelji (`Mon`..`Sun`, već izdvojen) |

Napomene o podacima:
- Merenja su otprilike svakih 30 min, u periodu ~08:00–16:30.
- Podaci pokazuju jasnu **dnevnu krivu punjenja** (jutro nisko, sredina dana visoko).
- Dataset NEMA podatke o saobraćaju ni koordinate parkinga — to se dodaje u kodu
  (`parks.py`) ili simulira.

## FAZE — gradi ovim redom, stani na kraju svake

### Faza 1 — Priprema podataka i EDA (`ml/explore.py`)
- Učitaj `data/parking.csv`, parsiraj `LastUpdated` u datetime.
- Izvuci feature-e: sat u danu, minut, dan u nedelji, radni dan/vikend.
- Vizuelizuj dnevnu krivu punjenja za nekoliko parkinga (matplotlib), sačuvaj kao slike.
- **Gotovo kada:** skripta se izvrši, ispiše osnovnu statistiku i sačuva grafik dnevnog
  obrasca. Stani i pokaži rezultat.

### Faza 2 — Model za predikciju (`ml/train.py`)
- Jedan model: **XGBoost regresija**, target = `OccupancyRate`.
- Feature-i: sat, minut, dan u nedelji (one-hot ili ordinal), ID parkinga (enkodovan),
  `Capacity`. Opciono: lag vrednosti zauzetosti.
- Podeli podatke na train/test (može hronološki — poslednji deo za test).
- Evaluiraj: **RMSE i MAE**, ispiši ih. Dodaj i baseline (npr. prosek) za poređenje.
- Sačuvaj model u `ml/model.joblib`.
- **Gotovo kada:** model se istrenira, evaluacija se ispiše, `model.joblib` postoji.
  Stani i pokaži metrike.

### Faza 3 — Backend / API (`backend/`)
- FastAPI app sa endpointima:
  - `GET /parks` — lista parkinga sa koordinatama i kapacitetom.
  - `GET /predict?park_id=...&hour=...&day=...` — predviđena zauzetost za dati parking/vreme.
  - `GET /recommend?dest_lat=...&dest_lng=...&hour=...&day=...` — rangirana lista
    preporučenih parkinga.
- `predictor.py` učitava `model.joblib` pri startu.
- `parks.py` drži koordinate parkinga (može ručno dodeljene približne koordinate u
  Birmingemu, ili fiktivne za demo — dokumentuj koje je).
- **Gotovo kada:** `uvicorn` pokrene server, svaki endpoint vraća smislen JSON. Stani i
  pokaži primer odgovora.

### Faza 4 — Modul za preporuku (`backend/recommender.py`)
Rangiranje po ponderisanom skoru (NE neuronska mreža):

```
skor = w1 * predvidjena_dostupnost + w2 * blizina_destinaciji - w3 * saobracaj
```

- `predvidjena_dostupnost` = 1 − (OccupancyRate/100) iz modela.
- `blizina_destinaciji` = normalizovana (obrnuta) udaljenost parkinga od destinacije.
- `saobracaj` = nije u datasetu → za sada konstanta/0 ili simulirana vrednost; ostavi
  jasan TODO i komentar da se u master radu dodaje realni saobraćaj.
- Ponderi w1, w2, w3 = konstante na vrhu fajla, lako izmenljive.
- Vrati top N (npr. 5) parkinga sortiranih po skoru.
- **Gotovo kada:** `/recommend` vraća rangiranu listu sa skorom i objašnjenjem
  komponenti. Stani i pokaži.

### Faza 5 — Frontend (`frontend/`, Next.js)
Minimalno, bez edge case-ova:
- Mapa (Leaflet) sa markerima parkinga.
- Polje/dugme za izbor destinacije (klik na mapu ILI prost input).
- Poziva `/recommend`, prikazuje top parkinge (markeri + lista sa procenjenom
  dostupnošću).
- **Gotovo kada:** aplikacija se pokrene, klik na destinaciju prikaže preporučene
  parkinge na mapi. Stani i pokaži.

## Šta NE raditi

- Ne generisati sintetičke podatke — koristi `data/parking.csv`.
- Ne koristiti CNN — pogrešan alat za tabelarne podatke. (Za master: LSTM/GRU poređenje.)
- Ne dodavati bazu, auth, Docker, testove osim ako se izričito traži.
- Ne raditi sve faze u jednom naletu.
- Ne komplikovati frontend — minimalni UI je namerno.
