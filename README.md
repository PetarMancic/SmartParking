# Smart Parking Recommendation (Proof of Concept)

Proof-of-concept sistem za **preporuku parking mesta u pametnim gradovima**, rađen kao
praktični deo seminarskog rada (uvod u master rad). Sistem pokriva ceo lanac end-to-end:
**podaci → predikcija zauzetosti → preporuka parkinga → prikaz na mapi**.

Ključni princip: **predikcija i preporuka su odvojeni moduli**. Predikcija (koliko će
parking biti zauzet) je ML zadatak — radi ga XGBoost model. Preporuka (koji parking
predložiti korisniku) je obično ponderisano rangiranje — namerno **ne koristi**
neuronsku mrežu, jer se kombinuju samo 2-3 interpretabilna faktora i transparentnost je
važnija od "pametnog" rešenja.

## Arhitektura

```
podaci (data/parking.csv) → ML model (ml/train.py) → ml/model.joblib
                                                            │
                                                            ▼
korisnik klikne na mapu → backend (FastAPI) → backend/predictor.py (predikcija po parkingu)
                                                            │
                                                            ▼
                                            backend/recommender.py (ponderisano rangiranje)
                                                            │
                                                            ▼
                                    frontend (Next.js + Leaflet) prikazuje top 5 na mapi
```

## Tehnološki stack

| Sloj | Tehnologija |
|---|---|
| Podaci + ML | Python 3.12, pandas, scikit-learn, XGBoost, joblib |
| Backend / API | Python, FastAPI, uvicorn |
| Frontend | Next.js (App Router), Leaflet (react-leaflet) |

## Struktura projekta

```
smart-parking/
├── CLAUDE.md
├── data/
│   └── parking.csv              # dataset (Parking Birmingham, UCI)
├── ml/
│   ├── explore.py                # Faza 1 - EDA
│   ├── train.py                  # Faza 2 - trening XGBoost modela
│   ├── model.joblib               # sacuvan istreniran model (generise train.py)
│   └── output/
│       └── daily_curve.png       # grafik dnevne krive punjenja
├── backend/
│   ├── main.py                   # FastAPI app, endpointi (Faza 3)
│   ├── predictor.py               # ucitava model.joblib, daje predikciju
│   ├── recommender.py             # ponderisano rangiranje parkinga (Faza 4)
│   └── parks.py                   # koordinate i kapacitet parkinga
└── frontend/                      # Next.js app (Faza 5)
    └── app/
        ├── page.tsx               # glavna stranica, poziva API
        └── ParkingMap.tsx         # Leaflet mapa
```

## Dataset

`data/parking.csv` — realni senzorski podaci o zauzetosti parkinga u Birmingemu
(Parking Birmingham / UCI dataset). 3352 merenja, 29 parkinga, period 13-19.12.2016,
merenja na ~30 min u intervalu ~08:00-16:30.

| Kolona | Opis |
|---|---|
| `SystemCodeNumber` | ID parkinga (29 lokacija) |
| `Capacity` | kapacitet parkinga |
| `Occupancy` | broj zauzetih mesta |
| `LastUpdated` | timestamp merenja |
| `OccupancyRate` | popunjenost u % (0-100) - **ciljna promenljiva** |
| `Date`, `Time`, `DayOfWeek` | vec izdvojeni delovi timestampa |

Dataset **nema** koordinate parkinga ni podatke o saobracaju - koordinate su rucno/
fiktivno dodeljene oko centra Birminghama (vidi `backend/parks.py`), a saobracaj je
za sada konstanta (vidi Fazu 4).

## Faza po faza - kako sistem radi

### Faza 1 - Priprema podataka i EDA (`ml/explore.py`)

Ucitava dataset, parsira `LastUpdated` u datetime i izvlaci vremenske feature-e (sat,
minut, dan u nedelji, radni dan/vikend). Ispisuje osnovnu statistiku (npr. prosecna
popunjenost ~53%, ponedeljak najprometniji dan) i crta dnevnu krivu punjenja za par
parkinga - grafik jasno pokazuje da zauzetost ima predvidiv dnevni obrazac (jutro nisko,
sredina dana visoko), sto opravdava izbor ML predikcije po vremenu.

```bash
python ml/explore.py
```

### Faza 2 - Model za predikciju (`ml/train.py`)

Trenira **XGBoost regresiju** koja predvidja `OccupancyRate` na osnovu: sata, minuta,
dana u nedelji, ID-a parkinga (enkodovan) i kapaciteta. Podela na train/test je
**hronoloska** (poslednjih 20% vremena je test) - model ne sme da "vidi" buducnost pri
treningu. Evaluacija (RMSE/MAE) poredi model sa baseline-om (prosek):

| | RMSE | MAE |
|---|---|---|
| Baseline (prosek) | 24.33 | 20.22 |
| XGBoost (test) | 12.65 | 9.46 |

Model skoro prepolovi gresku u odnosu na baseline, sto potvrdjuje da stvarno uci
vremenski obrazac. Sacuvan u `ml/model.joblib` (model + encoder parkinga + lista
feature-a).

```bash
python ml/train.py
```

### Faza 3 - Backend / API (`backend/`)

FastAPI aplikacija koja servira model i podatke kroz REST:

- `GET /parks` - lista svih parkinga (id, kapacitet, koordinate).
- `GET /predict?park_id=...&hour=...&day=...` - predvidjena popunjenost za dati
  parking i vreme.
- `GET /recommend?dest_lat=...&dest_lng=...&hour=...&day=...&top_n=5` - rangirana
  lista preporucenih parkinga (logika u Fazi 4).

`predictor.py` ucitava `model.joblib` **jednom, pri startu servera**. `parks.py` cita
stvaran kapacitet iz dataseta i dodaje fiktivne koordinate za mapu/racunanje
udaljenosti.

```bash
uvicorn backend.main:app --reload
# http://127.0.0.1:8000/docs za interaktivni Swagger UI
```

### Faza 4 - Modul za preporuku (`backend/recommender.py`)

Rangira parkinge po ponderisanom skoru (obicna formula, **ne** ML):

```
skor = w1 * predvidjena_dostupnost + w2 * blizina_destinaciji - w3 * saobracaj
```

- `predvidjena_dostupnost = 1 - (predvidjeni OccupancyRate / 100)` - iz ML modela.
- `blizina_destinaciji` - normalizovana obrnuta udaljenost (haversine formula) od
  destinacije koju je korisnik izabrao.
- `saobracaj` - **TODO za master rad**: dataset nema saobracajne podatke, trenutno
  konstanta 0.
- Ponderi `W1_PREDICTED_AVAILABILITY = 0.6`, `W2_PROXIMITY = 0.4`, `W3_TRAFFIC = 0.0`
  su konstante na vrhu fajla - lako izmenljive.

Vraca top N parkinga sortiranih po skoru, sa razlozenim komponentama (koliko je svaki
faktor doprineo) - preporuka mora biti objasnjiva, ne "crna kutija".

### Faza 5 - Frontend (`frontend/`, Next.js + Leaflet)

Minimalni UI za demonstraciju celog lanca:

- Mapa (Leaflet) centrirana na Birmingem, ucitava sve parkinge kao **plave tacke**.
- Polja za izbor sata i dana.
- Klik na mapu postavlja destinaciju (**crvena tacka**) i automatski poziva
  `/recommend`.
- Top 5 preporucenih parkinga postaju **zelene tacke** na mapi, uz listu sa
  procenjenom popunjenoscu, udaljenoscu i skorom sa desne strane.

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000
```

## Pokretanje celog sistema

Potrebna su dva terminala (backend i frontend rade istovremeno):

```bash
# Terminal 1 - backend (iz smart-parking/)
uvicorn backend.main:app --reload

# Terminal 2 - frontend (iz smart-parking/frontend/)
npm run dev
```

Zatim otvoriti `http://localhost:3000` u browseru.

## Ogranicenja (svesno, PoC)

- Koordinate parkinga su fiktivne/rucno dodeljene (dataset ih nema) - dokumentovano u
  `backend/parks.py`.
- Saobracaj nije ukljucen u skor (nema podataka u datasetu) - ostavljen kao TODO za
  master rad.
- Bez baze podataka, autentifikacije ili testova - fokus je na tome da ceo lanac radi
  end-to-end, ne na produkcionoj spremnosti.
