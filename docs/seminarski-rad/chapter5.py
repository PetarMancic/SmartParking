# -*- coding: utf-8 -*-
"""Poglavlje 5 - Implementacija sistema (najveci deo seminarskog rada)."""


def build_chapter5(doc, H):
    h1, h2, h3 = H["h1"], H["h2"], H["h3"]
    p, bullets, formula = H["p"], H["bullets"], H["formula"]
    code_block, figure, table_grid = H["code_block"], H["figure"], H["table_grid"]

    h1(doc, "5. Implementacija sistema")

    p(doc, (
        "U ovom poglavlju detaljno je opisana implementacija svake celine sistema, sa isečcima "
        "stvarnog izvornog koda, primerima ulazno-izlaznih podataka i grafičkim prikazom "
        "rezultata. Struktura poglavlja prati redosled kojim podaci prolaze kroz sistem: priprema "
        "podataka → model za predikciju → backend API → modul za preporuku → frontend → analiza "
        "rezultata."
    ))

    # ------------------------------------------------------------------
    h2(doc, "5.1. Arhitektura sistema")

    p(doc, (
        "Sistem je organizovan kao lanac od četiri nezavisna modula, svaki odgovoran za tačno "
        "jednu odgovornost, povezanih jednostavnim, dobro definisanim interfejsima (fajl na "
        "disku i REST API):"
    ))

    fig_arch = figure(doc, "architecture_flow.png", "Arhitekturni tok sistema — od sirovih podataka do korisničkog interfejsa.")

    bullets(doc, [
        "data/parking.csv → ml/train.py: sirovi podaci se koriste za treniranje XGBoost modela.",
        "ml/train.py → ml/model.joblib: istrenirani model, enkoder parkinga i lista feature-a "
        "serijalizuju se na disk kao jedan paket.",
        "ml/model.joblib → backend/: FastAPI backend učitava model jednom, pri startu servera "
        "(backend/predictor.py), i koristi ga za svaki zahtev za predikciju.",
        "backend/ → frontend/: Next.js aplikacija poziva REST endpointe (/parks, /predict, "
        "/recommend) i prikazuje rezultate na interaktivnoj mapi.",
    ])

    p(doc, (
        "Ova modularnost ima direktnu praktičnu posledicu: model se može ponovo istrenirati "
        "(npr. na novijim podacima) bez ijedne izmene u backend ili frontend kodu, sve dok "
        "format ulaznih feature-a ostane isti — jedini deo koji „zna” za detalje modela je "
        "`predictor.py`. Isto tako, ponderi u modulu za preporuku (Poglavlje 5.5) mogu se menjati "
        "bez ponovnog treniranja modela, jer su predikcija i preporuka potpuno razdvojene "
        "(Poglavlje 2)."
    ))

    # ------------------------------------------------------------------
    h2(doc, "5.2. Priprema podataka i EDA (Faza 1)")

    p(doc, (
        "Skripta `ml/explore.py` učitava dataset, parsira vremensku oznaku i izvlači vremenske "
        "feature-e potrebne i za deskriptivnu analizu i, kasnije, za sam model:"
    ))

    code_block(doc, '''
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"])
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df["Hour"] = df["LastUpdated"].dt.hour
    df["Minute"] = df["LastUpdated"].dt.minute
    df["DayOfWeekNum"] = df["LastUpdated"].dt.dayofweek  # 0 = ponedeljak
    df["IsWeekend"] = df["DayOfWeekNum"].isin([5, 6])
    return df
'''.strip("\n"))

    p(doc, (
        "Vredi primetiti da se `IsWeekend` (binarna oznaka radni dan/vikend) računa isključivo za "
        "potrebe deskriptivne statistike u ovoj fazi — finalni model za predikciju (Poglavlje 5.3) "
        "koristi direktno `DayOfWeekNum` (0–6), čime se modelu omogućava da nauči finije razlike "
        "između pojedinačnih dana (npr. ponedeljak nasuprot petku), a ne samo grubu podelu na "
        "radni dan i vikend."
    ))

    p(doc, "Pokretanjem skripte dobija se sledeća osnovna statistika nad datasetom:")

    table_grid(
        doc,
        headers=["Statistika", "Vrednost"],
        rows=[
            ["Broj redova", "3.352"],
            ["Broj različitih parkinga", "29"],
            ["Period merenja", "2016-12-13 07:55:51 → 2016-12-19 16:30:35"],
            ["OccupancyRate — prosek / std", "53,14 % / 26,02 %"],
            ["OccupancyRate — min / max", "0,69 % / 100,0 %"],
            ["Capacity — prosek (min–max)", "1.361 (220–4.675)"],
            ["Prosečna popunjenost, ponedeljak (najveća)", "60,86 %"],
            ["Prosečna popunjenost, nedelja (najmanja)", "41,38 %"],
            ["Prosečna popunjenost — radni dan / vikend", "55,97 % / 45,69 %"],
        ],
        caption="Osnovna deskriptivna statistika dataset-a, ispisana skriptom ml/explore.py.",
    )

    fig_dow = figure(doc, "day_of_week.png", "Prosečna popunjenost po danu u nedelji, svi parkinzi zajedno (radni dani tamnoplavo, vikend svetloplavo).")

    p(doc, (
        f"Podaci na Slici {fig_dow} pokazuju blagi, ali dosledan pad popunjenosti od ponedeljka "
        "ka nedelji, i jasnu razliku između radnih dana i vikenda (~10 procentnih poena) — što "
        "odgovara očekivanom obrascu korišćenja parkinga u poslovnom centru grada (veći priliv "
        "vozila radnim danima, zbog posla i kupovine)."
    ))

    p(doc, (
        "Za nekoliko reprezentativnih parkinga (BHMBCCMKT01, Broad Street, BHMEURBRD01, Bull "
        "Ring) nacrtana je dnevna kriva punjenja — prosečna popunjenost po satu u danu:"
    ))

    code_block(doc, '''
def plot_daily_curves(df: pd.DataFrame) -> None:
    for park in available_parks:
        park_df = df[df["SystemCodeNumber"] == park]
        hourly_avg = park_df.groupby("Hour")["OccupancyRate"].mean()
        ax.plot(hourly_avg.index, hourly_avg.values, marker="o", label=park)
'''.strip("\n"))

    fig_daily = figure(doc, "daily_curve.png", "Dnevna kriva punjenja za četiri reprezentativna parkinga (ml/explore.py).")

    p(doc, (
        f"Slika {fig_daily} jasno pokazuje da zauzetost ima predvidiv dnevni obrazac: nisko u "
        "ranim jutarnjim satima, rast tokom prepodneva, i zadržavanje na visokom nivou tokom "
        "sredine dana. Ovaj nalaz direktno opravdava odluku da se predikcija zauzetosti (Poglavlje "
        "5.3) zasniva pretežno na vremenskim obeležjima — obrazac je dovoljno pravilan da ga model "
        "mašinskog učenja može naučiti isključivo iz istorijskih podataka o vremenu, bez potrebe "
        "za spoljašnjim izvorima podataka."
    ))

    fig_hist = figure(doc, "occupancy_histogram.png", "Raspodela vrednosti OccupancyRate u celom datasetu.")

    p(doc, (
        f"Histogram na Slici {fig_hist} dodatno potvrđuje da je raspodela popunjenosti u "
        "datasetu relativno ravnomerna, sa blagim grupisanjem oko proseka (53,14 %) i primetnim "
        "brojem merenja u oba ekstrema (skoro prazni i skoro puni parkinzi) — što je povoljno za "
        "treniranje regresionog modela, jer izbegava jak disbalans ka jednoj vrednosti koji bi "
        "model naveo da uči trivijalno rešenje (npr. da uvek predviđa vrednost blizu proseka)."
    ))

    fig_cap = figure(doc, "capacity_vs_occupancy.png", "Odnos kapaciteta parkinga i njegove prosečne popunjenosti (svaka tačka je jedan od 29 parkinga).")

    p(doc, (
        f"Na Slici {fig_cap} ispitan je odnos između kapaciteta parkinga i njegove prosečne "
        "popunjenosti tokom celog perioda merenja. Korelacija je slaba i blago negativna "
        "(r ≈ −0,15) — veći parkinzi imaju tendenciju da budu, u proseku, nešto manje popunjeni u "
        "relativnom (procentualnom) smislu, ali veza nije dovoljno jaka da bi se kapacitet sam po "
        "sebi mogao koristiti kao pouzdan prediktor popunjenosti. Ovaj nalaz dodatno opravdava "
        "uključivanje kapaciteta kao pomoćnog, a ne dominantnog feature-a u modelu (Poglavlje "
        "5.3), uz identitet parkinga i vreme kao glavne izvore prediktivne moći (videti i kasniju "
        "analizu značaja feature-a, Poglavlje 5.3)."
    ))

    # ------------------------------------------------------------------
    h2(doc, "5.3. Model za predikciju (Faza 2)")

    p(doc, (
        "Skripta `ml/train.py` implementira ceo tok treniranja: pripremu feature-a, hronološku "
        "podelu na trening i test skup, treniranje XGBoost modela, evaluaciju i čuvanje modela na "
        "disk."
    ))

    h3(doc, "Priprema feature-a i podela podataka")

    code_block(doc, '''
FEATURE_COLUMNS = ["Hour", "Minute", "DayOfWeekNum", "ParkEncoded", "Capacity"]
TARGET_COLUMN = "OccupancyRate"


def load_and_prepare_data() -> tuple[pd.DataFrame, LabelEncoder]:
    df = pd.read_csv(DATA_PATH)
    df["LastUpdated"] = pd.to_datetime(df["LastUpdated"])
    df = df.sort_values("LastUpdated").reset_index(drop=True)

    df["Hour"] = df["LastUpdated"].dt.hour
    df["Minute"] = df["LastUpdated"].dt.minute
    df["DayOfWeekNum"] = df["LastUpdated"].dt.dayofweek

    park_encoder = LabelEncoder()
    df["ParkEncoded"] = park_encoder.fit_transform(df["SystemCodeNumber"])

    return df, park_encoder


def chronological_split(df: pd.DataFrame, test_fraction: float = 0.2):
    split_index = int(len(df) * (1 - test_fraction))
    train_df = df.iloc[:split_index]
    test_df = df.iloc[split_index:]
    return train_df, test_df
'''.strip("\n"))

    p(doc, (
        "Identifikator parkinga (SystemCodeNumber, tekstualna vrednost poput „BHMBCCMKT01”) "
        "enkodovan je pomoću scikit-learn LabelEncoder-a u celobrojnu vrednost (ParkEncoded), što "
        "modelu omogućava da nauči zaseban obrazac ponašanja za svaki od 29 parkinga, zajedno sa "
        "opštim vremenskim obrascem. Enkoder se čuva zajedno sa modelom (videti dole), jer isti "
        "mapiranje mora biti korišćeno i pri predikciji."
    ))

    h3(doc, "Treniranje i evaluacija")

    code_block(doc, '''
# Baseline: uvek predvidja prosecnu popunjenost iz trening skupa
baseline_pred = np.full(len(y_test), y_train.mean())
evaluate(y_test, baseline_pred, "Baseline (prosek)")

model = XGBRegressor(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.1,
    random_state=42,
)
model.fit(X_train, y_train)

test_pred = model.predict(X_test)
evaluate(y_test, test_pred, "XGBoost (test)")

joblib.dump(
    {"model": model, "park_encoder": park_encoder, "features": FEATURE_COLUMNS},
    MODEL_PATH,
)
'''.strip("\n"))

    p(doc, (
        "Model i enkoder se čuvaju zajedno u jednom `joblib` paketu, zajedno sa spiskom imena "
        "feature-a u tačnom redosledu koji model očekuje. Ovo je namerna odluka koja obezbeđuje "
        "da backend (Poglavlje 5.4) pri učitavanju modela ne mora da poznaje detalje treniranja — "
        "dovoljno je da složi ulazni red podataka po istom redosledu feature-a, čime se izbegava "
        "čitava klasa grešaka tipa „mismatch” između trening i produkcionog okruženja."
    ))

    p(doc, "Hiperparametri XGBoost modela zadati su eksplicitno, bez automatizovane pretrage:")

    table_grid(
        doc,
        headers=["Hiperparametar", "Vrednost", "Obrazloženje"],
        rows=[
            ["n_estimators", "200", "Dovoljan broj stabala za stabilnu konvergenciju bez prekomernog usporavanja treniranja na ~2.680 trening redova."],
            ["max_depth", "4", "Plitka stabla smanjuju rizik od preprilagođavanja (overfitting) na relativno malom datasetu."],
            ["learning_rate", "0,1", "Standardna, umerena vrednost — dovoljno mala za stabilno učenje uz 200 stabala."],
            ["random_state", "42", "Fiksirano radi ponovljivosti rezultata između pokretanja."],
        ],
        caption="Hiperparametri XGBRegressor korišćeni u ml/train.py.",
    )

    p(doc, (
        "Pošto je dataset relativno mali (3.352 reda), formalna pretraga hiperparametara "
        "(grid/random search) nije sprovedena u okviru ovog proof-of-concept rada — vrednosti su "
        "odabrane na osnovu uobičajenih podrazumevanih preporuka za XGBoost nad manjim tabelarnim "
        "skupovima podataka [6] i potvrđene kroz posmatranje evaluacije na test skupu. "
        "Sistematska pretraga hiperparametara ostaje mogući pravac za produbljivanje u budućem "
        "radu."
    ))

    table_grid(
        doc,
        headers=["Model", "RMSE", "MAE"],
        rows=[
            ["Baseline (prosek trening skupa)", "24,33", "20,22"],
            ["XGBoost (test skup)", "12,65", "9,46"],
        ],
        caption="Evaluacija na hronološkom test skupu (poslednjih 20% vremenske ose): baseline vs. XGBoost.",
    )

    fig_rmse = figure(doc, "rmse_mae_comparison.png", "Poređenje greške (RMSE i MAE) baseline modela i XGBoost modela na test skupu.")

    p(doc, (
        f"Kao što se vidi na Slici {fig_rmse}, XGBoost model gotovo prepolovljuje obe metrike "
        "greške u odnosu na baseline (RMSE sa 24,33 na 12,65; MAE sa 20,22 na 9,46), što je jak "
        "pokazatelj da model uspešno uči stvaran vremenski obrazac zauzetosti, a ne samo "
        "reprodukuje prosečnu vrednost."
    ))

    fig_imp = figure(doc, "feature_importance.png", "Značaj pojedinačnih feature-a u istreniranom XGBoost modelu.")

    p(doc, (
        f"Analiza značaja feature-a (Slika {fig_imp}) pokazuje koliko svaki ulazni podatak "
        "doprinosi odlukama modela. Identitet parkinga (ParkEncoded) i sat u danu (Hour) "
        "očekivano nose najveći deo objašnjive snage modela — što je u skladu sa uočenim dnevnim "
        "obrascem (Poglavlje 5.2) i činjenicom da različiti parkinzi imaju sistematski različite "
        "nivoe popunjenosti (npr. zbog lokacije ili kapaciteta)."
    ))

    fig_scatter = figure(doc, "predicted_vs_actual.png", "Predviđena vs. stvarna popunjenost na test skupu — tačke bliže isprekidanoj liniji predstavljaju preciznije predikcije.")

    p(doc, (
        f"Grafik predviđeno-naspram-stvarno (Slika {fig_scatter}) potvrđuje da se većina tačaka "
        "grupiše oko idealne dijagonale, sa nešto većim rasipanjem u srednjem opsegu popunjenosti "
        "(30–70%), gde je varijabilnost ponašanja korisnika prirodno najveća — ekstremne vrednosti "
        "(skoro prazan ili skoro pun parking) model predviđa nešto pouzdanije."
    ))

    h3(doc, "Poređenje sa drugim modelima")

    p(doc, (
        "Da bi se opravdao izbor baš XGBoost-a (Poglavlje 4), nad istim feature-ima i istom "
        "hronološkom podelom podataka istrenirana su dodatno još dva standardna modela: obična "
        "linearna regresija (kao jednostavan, linearan referentni model) i random forest "
        "regresija (drugi, nezavisan ansambl stabala odlučivanja, radi provere da li je razlika u "
        "odnosu na baseline specifična baš za gradijentno pojačavanje ili važi za stabla "
        "odlučivanja uopšte)."
    ))

    fig_cmp = figure(doc, "model_comparison.png", "Poređenje RMSE i MAE četiri modela na istom test skupu: baseline, linearna regresija, random forest, XGBoost.")

    table_grid(
        doc,
        headers=["Model", "RMSE", "MAE"],
        rows=[
            ["Baseline (prosek)", "24,33", "20,22"],
            ["Linearna regresija", "20,34", "16,65"],
            ["Random Forest (200 stabala, max_depth=8)", "13,37", "10,12"],
            ["XGBoost (200 stabala, max_depth=4)", "12,65", "9,46"],
        ],
        caption="Poređenje četiri modela na istom hronološkom test skupu.",
    )

    p(doc, (
        f"Kao što se vidi na Slici {fig_cmp} i u tabeli, linearna regresija poboljšava rezultat u "
        "odnosu na baseline (RMSE 20,34 naspram 24,33), ali znatno zaostaje za oba pristupa "
        "zasnovana na stablima odlučivanja — očekivano, jer je odnos između ulaznih feature-a "
        "(posebno identiteta parkinga) i popunjenosti izrazito nelinearan, a linearna regresija po "
        "definiciji ne može da modeluje takve interakcije bez ručnog inženjeringa dodatnih "
        "feature-a. Random Forest dostiže rezultat vrlo blizak XGBoost-u (RMSE 13,37 naspram "
        "12,65), što potvrđuje da su modeli zasnovani na stablima generalno pogodni za ovaj tip "
        "podataka [2], dok XGBoost ostaje neznatno precizniji uz brže treniranje, što ga čini "
        "konačnim izborom za sistem opisan u ovom radu."
    ))

    # ------------------------------------------------------------------
    h2(doc, "5.4. Backend / REST API (Faza 3)")

    p(doc, (
        "FastAPI aplikacija (`backend/main.py`) izlaže predikciju i preporuku kao REST endpointe. "
        "Backend je organizovan u tri modula sa jasno razdvojenim odgovornostima: `predictor.py` "
        "(učitavanje modela i predikcija), `parks.py` (metapodaci o parkinzima) i "
        "`recommender.py` (rangiranje, Poglavlje 5.5)."
    ))

    h3(doc, "predictor.py — učitavanje modela i predikcija")

    code_block(doc, '''
_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
_park_encoder = _bundle["park_encoder"]
_features = _bundle["features"]


def predict_occupancy_rate(park_id: str, hour: int, minute: int, day, capacity: float) -> float:
    if park_id not in known_park_ids():
        raise ValueError(f"Nepoznat park_id: {park_id}")

    day_num = parse_day(day)
    park_encoded = _park_encoder.transform([park_id])[0]

    row = pd.DataFrame([{
        "Hour": hour, "Minute": minute, "DayOfWeekNum": day_num,
        "ParkEncoded": park_encoded, "Capacity": capacity,
    }])[_features]

    prediction = float(_model.predict(row)[0])
    return min(max(prediction, 0.0), 100.0)
'''.strip("\n"))

    p(doc, (
        "Model se učitava tačno jednom, na nivou modula (pri startu servera), a ne pri svakom "
        "zahtevu — što je bitno za performanse, jer je deserijalizacija XGBoost modela znatno "
        "sporija od same predikcije. Funkcija `parse_day` prihvata dan zadat i kao broj (0–6) i "
        "kao skraćeno ime (Mon, tue, WED...), radi praktičnosti pri pozivanju API-ja. Predviđena "
        "vrednost se na kraju ograničava (clip) na fizički smislen opseg [0, 100], jer regresioni "
        "model teorijski može vratiti i vrednost van tog opsega."
    ))

    h3(doc, "main.py — endpointi")

    code_block(doc, '''
@app.get("/predict")
def predict(park_id: str, hour: int, day: str):
    park = parks_module.get_park(park_id)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Nepoznat park_id: {park_id}")

    occupancy_rate = predictor.predict_occupancy_rate(
        park_id=park_id, hour=hour, minute=0, day=day, capacity=park["capacity"]
    )

    return {
        "park_id": park_id,
        "hour": hour,
        "day": day,
        "predicted_occupancy_rate": round(occupancy_rate, 2),
        "predicted_available_spots": round(park["capacity"] * (1 - occupancy_rate / 100)),
        "availability_score": round(1 - occupancy_rate / 100, 4),
    }
'''.strip("\n"))

    p(doc, "Primer stvarnog odgovora za `GET /predict?park_id=BHMBCCMKT01&hour=9&day=Mon`:")

    code_block(doc, '''
{
  "park_id": "BHMBCCMKT01",
  "hour": 9,
  "day": "Mon",
  "predicted_occupancy_rate": 6.32,
  "predicted_available_spots": 605,
  "availability_score": 0.9368
}
'''.strip("\n"))

    table_grid(
        doc,
        headers=["Endpoint", "Parametri", "Vraća"],
        rows=[
            ["GET /parks", "—", "Lista svih 29 parkinga: park_id, capacity, lat, lng."],
            ["GET /predict", "park_id, hour, day", "Predviđena popunjenost i dostupnost za jedan parking i trenutak."],
            ["GET /predict_current", "park_id?, hour?, day?", "Kao gore, ali za trenutni sat/dan ako nisu zadati, i za sve parkinge odjednom ako park_id izostane."],
            ["GET /recommend", "origin_lat/lng, dest_lat/lng, hour, day, top_n?, radius?", "Rangirana top-N lista preporuka sa razloženim skorom (Poglavlje 5.5)."],
        ],
        caption="Pregled svih REST endpointa izloženih u backend/main.py.",
    )

    p(doc, "Primer odgovora za `GET /parks` (skraćeno, prva dva elementa liste):")

    code_block(doc, '''
[
  {"park_id": "BHMBCCMKT01", "capacity": 577, "lat": 52.4804, "lng": -1.8933},
  {"park_id": "BHMBCCPST01", "capacity": 317, "lat": 52.478, "lng": -1.899}
]
'''.strip("\n"))

    p(doc, (
        "Endpoint `/predict_current` koristi frontend za prikaz kartice „najbolji parking po "
        "modelu” (Poglavlje 5.6), dok `/recommend` predstavlja glavni endpoint modula za "
        "preporuku, detaljno opisan u Poglavlju 5.5. Ceo API je automatski dokumentovan i "
        "testabilan preko Swagger interfejsa na `/docs`, zahvaljujući FastAPI-jevoj integraciji sa "
        "OpenAPI specifikacijom — što je bilo od velike koristi tokom ručnog testiranja svakog "
        "endpointa pre povezivanja sa frontendom."
    ))

    h3(doc, "parks.py — koordinate i kapacitet")

    p(doc, (
        "Dataset ne sadrži geografske koordinate parkinga, pa su one ručno dodeljene i eksplicitno "
        "dokumentovane kao fiktivne, raspoređene oko centra Birminghama:"
    ))

    code_block(doc, '''
# NAPOMENA O KOORDINATAMA: dataset (data/parking.csv) ne sadrzi geografske
# koordinate. Koordinate ispod su RUCNO DODELJENE / FIKTIVNE priblizne lokacije
# rasporedjene oko centra Birminghama (52.4796, -1.8998) - koriste se samo za
# demo mapu i racunanje udaljenosti u ovom PoC-u, ne predstavljaju stvarne GPS
# pozicije ovih parkinga. Kapacitet se cita direktno iz dataseta (stvaran podatak).

FICTIONAL_COORDINATES = {
    "BHMBCCMKT01": (52.4804, -1.8933),
    "Broad Street": (52.4778, -1.9160),
    "Bull Ring": (52.4772, -1.8931),
    ...
}
'''.strip("\n"))

    p(doc, "Radi potpunosti, u nastavku je dat kompletan spisak svih 29 parkinga iz dataseta sa njihovim stvarnim kapacitetom (kolona Capacity), sortiran opadajuće:")

    table_grid(
        doc,
        headers=["SystemCodeNumber", "Kapacitet", "SystemCodeNumber", "Kapacitet"],
        rows=[
            ["Others-CCCPS133", "4.675", "BHMBRCBRG03", "849"],
            ["Others-CCCPS135a", "3.883", "NIA South", "788"],
            ["Others-CCCPS98", "3.103", "BHMNCPLDH01", "720"],
            ["Bull Ring", "3.053", "Broad Street", "690"],
            ["Others-CCCPS202", "2.937", "BHMMBMMBX01", "687"],
            ["Others-CCCPS119a", "2.803", "BHMNCPRAN01", "600"],
            ["Others-CCCPS105a", "2.009", "BHMBCCMKT01", "577"],
            ["Shopping", "1.920", "BHMNCPNHS01", "500"],
            ["Others-CCCPS8", "1.322", "BHMBRTARC01", "496"],
            ["NIA Car Parks", "1.268", "BHMNCPNST01", "485"],
            ["BHMNCPHST01", "1.200", "BHMEURBRD01", "470"],
            ["BHMBRCBRG02", "1.194", "BHMNCPPLS01", "450"],
            ["BHMBRCBRG01", "1.010", "BHMBCCTHL01", "387"],
            ["BHMBCCSNH01", "863", "BHMBCCPST01", "317"],
            ["", "", "BHMEURBRD02", "220"],
        ],
        caption="Kompletan spisak svih 29 parkinga u data/parking.csv i njihov stvaran kapacitet.",
    )

    p(doc, (
        "Kapacitet parkinga, za razliku od koordinata, čita se direktno iz stvarnog dataseta "
        "(`Capacity` kolona), grupisano po `SystemCodeNumber` — jedini fiktivni deo sistema su, "
        "dakle, geografske pozicije, dok su sva merenja zauzetosti i kapaciteta autentična."
    ))

    h3(doc, "Ručno testiranje API-ja preko komandne linije")

    p(doc, (
        "Pored Swagger UI-ja, endpointi su tokom razvoja povremeno testirani i direktno preko "
        "komandne linije, radi brze provere bez otvaranja pregledača:"
    ))

    code_block(doc, '''
curl "http://127.0.0.1:8000/parks"

curl "http://127.0.0.1:8000/predict?park_id=BHMBCCMKT01&hour=9&day=Mon"

curl "http://127.0.0.1:8000/recommend?origin_lat=52.4796&origin_lng=-1.8998&\\
dest_lat=52.4772&dest_lng=-1.8931&hour=9&day=Mon&top_n=5"
'''.strip("\n"))

    # ------------------------------------------------------------------
    h2(doc, "5.5. Modul za preporuku (Faza 4)")

    p(doc, (
        "`backend/recommender.py` implementira ponderisano rangiranje opisano u Poglavlju 3.3. "
        "Za svaki kandidatski parking računaju se tri komponente skora, koje se zatim kombinuju "
        "linearno:"
    ))

    code_block(doc, '''
W1_PREDICTED_AVAILABILITY = 0.55
W2_PROXIMITY = 0.3
W3_TRAFFIC = 0.15


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    earth_radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def _traffic_density_score(distance_km: float, hour: int) -> float:
    peak_hour_penalty = 0.25 if (7 <= hour <= 9 or 16 <= hour <= 19) else 0.0
    proximity_penalty = min(0.35, distance_km / 10.0)
    return min(1.0, peak_hour_penalty + proximity_penalty)
'''.strip("\n"))

    p(doc, (
        "Rastojanje se računa haversine formulom — standardnim, u navigaciji i geoinformatici "
        "široko korišćenim izrazom za rastojanje između dve tačke na sferi zadate geografskom "
        "širinom i dužinom [13]. Simulirani „saobraćaj” raste sa blizinom destinacije "
        "(pretpostavka: gušće gradsko jezgro = više saobraćaja) i dodatno se penalizuje u "
        "jutarnjem (7–9h) i popodnevnom (16–19h) špicu — jednostavan, ali transparentan "
        "zamenski signal za stvarne podatke o saobraćaju, koji dataset ne sadrži."
    ))

    p(doc, "Konačni skor kombinuje sve tri komponente:")

    code_block(doc, '''
predicted_availability = 1 - candidate["predicted_occupancy_rate"] / 100
closeness = 1 - (candidate["distance_to_origin_km"] / max_drive_distance_km)
traffic = _traffic_density_score(candidate["distance_to_destination_km"], hour)

score = (
    W1_PREDICTED_AVAILABILITY * predicted_availability
    + W2_PROXIMITY * closeness
    - W3_TRAFFIC * traffic
)
'''.strip("\n"))

    p(doc, (
        "Vredi napomenuti jednu suptilnu, ali namernu implementacionu odluku: komponenta "
        "„blizina” (closeness) računa se u odnosu na polaznu tačku korisnika (origin), a ne "
        "direktno u odnosu na destinaciju — jer se sistem, u konačnoj verziji frontenda "
        "(Poglavlje 5.6), koristi za preporuku parkinga na putu ka destinaciji, a ne isključivo u "
        "njenoj neposrednoj blizini. Blizina destinaciji se, umesto toga, koristi kao ulaz u "
        "procenu saobraćaja i kao opcioni filter radijusa (`radius` parametar u `/recommend`)."
    ))

    p(doc, (
        "Kao ilustraciju, u nastavku je prikazan stvaran izlaz sistema za dva vremenska trenutka "
        "istog dana (ponedeljak), za istu polaznu tačku (centar Birminghama) i istu destinaciju "
        "(Bull Ring), dobijen direktnim pozivom `recommender.recommend_parks(...)`:"
    ))

    table_grid(
        doc,
        headers=["#", "Parking", "Zauzetost", "Dostupnost", "Vožnja (km)", "Šetnja (km)", "Skor"],
        rows=[
            ["1", "BHMBCCPST01", "13,85 %", "0,8615", "0,19", "0,41", "0,6895"],
            ["2", "BHMBCCMKT01", "6,32 %", "0,9368", "0,45", "0,36", "0,6759"],
            ["3", "Bull Ring", "17,47 %", "0,8253", "0,53", "0,00", "0,6028"],
            ["4", "Others-CCCPS119a", "13,86 %", "0,8614", "0,72", "1,18", "0,5643"],
            ["5", "BHMNCPHST01", "30,92 %", "0,6908", "0,40", "0,19", "0,5539"],
        ],
        caption="Top 5 preporuka za sat 09h (jutro), ponedeljak — stvaran izlaz recommend_parks().",
    )

    table_grid(
        doc,
        headers=["#", "Parking", "Zauzetost", "Dostupnost", "Vožnja (km)", "Šetnja (km)", "Skor"],
        rows=[
            ["1", "BHMBCCMKT01", "34,27 %", "0,6573", "0,45", "0,36", "0,5597"],
            ["2", "BHMBCCPST01", "49,65 %", "0,5035", "0,19", "0,41", "0,5301"],
            ["3", "Others-CCCPS119a", "27,20 %", "0,7280", "0,72", "1,18", "0,5284"],
            ["4", "NIA Car Parks", "20,53 %", "0,7947", "0,98", "1,47", "0,5050"],
            ["5", "BHMNCPPLS01", "33,95 %", "0,6605", "0,86", "1,09", "0,4626"],
        ],
        caption="Iste polazne postavke, ali za sat 14h (popodne) — poredak se menja u odnosu na prethodnu tabelu.",
    )

    p(doc, (
        "Poređenje dve tabele ilustruje kako sistem reaguje na promenu vremena: u 9h, "
        "BHMBCCPST01 osvaja prvo mesto zahvaljujući vrlo visokoj predviđenoj dostupnosti (86,15 "
        "%) i maloj udaljenosti, uprkos umerenoj kazni za jutarnji špic. U 14h, popunjenost svih "
        "parkinga raste (u skladu sa dnevnom krivom iz Poglavlja 5.2) — BHMBCCPST01 gubi gotovo "
        "polovinu svoje dostupnosti (sa 86,15 % na 50,35 %) i pada na drugo mesto, dok "
        "BHMBCCMKT01, čija dostupnost opada sporije, preuzima vrh liste iako je u oba slučaja "
        "fizički na istoj lokaciji. Ovakvo ponašanje pokazuje da sistem zaista reaguje na "
        "predviđenu, a ne trenutnu, zauzetost — što je i bio osnovni cilj definisan u Poglavlju 1."
    ))

    # ------------------------------------------------------------------
    h2(doc, "5.6. Frontend (Faza 5)")

    p(doc, (
        "Frontend je Next.js aplikacija (App Router) sa jednom glavnom stranicom "
        "(`frontend/app/page.tsx`) i klijentskom komponentom karte (`ParkingMap.tsx`), učitanom "
        "dinamički bez server-side renderovanja (`ssr: false`) — Leaflet zahteva pristup "
        "`window` objektu i ne može se renderovati na serveru."
    ))

    p(doc, "Stanje aplikacije (`page.tsx`) organizovano je oko sledećih ključnih React state promenljivih:")

    table_grid(
        doc,
        headers=["State promenljiva", "Uloga"],
        rows=[
            ["parks", "Lista svih parkinga, učitana jednom pri pokretanju sa GET /parks."],
            ["currentLocation / destination", "Polazna tačka i destinacija, postavljene klikom na mapu."],
            ["hour / day", "Trenutno izabrani sat i dan, ulazni parametri za predikciju i preporuku."],
            ["recommendations", "Rezultat poslednjeg poziva GET /recommend — lista prikazana u bočnom panelu."],
            ["route / routeParkings", "Geometrija vozne rute (OSRM) i parkinzi pronađeni duž te rute."],
            ["startPlace / destinationPlace", "Čitljive adrese dobijene reverznim geokodiranjem (Nominatim)."],
        ],
        caption="Ključne state promenljive u frontend/app/page.tsx.",
    )

    p(doc, (
        "Korisnička interakcija je organizovana oko dva klika na mapu: prvi klik postavlja "
        "polaznu tačku, drugi klik postavlja destinaciju, nakon čega se automatski pozivaju "
        "`/recommend` (za listu preporuka) i spoljašnji OSRM servis (za stvarnu voznu rutu):"
    ))

    code_block(doc, '''
const handleMapClick = (lat: number, lng: number) => {
  if (!currentLocation) {
    setCurrentLocation({ lat, lng });
    return;
  }
  if (!destination) {
    setDestination({ lat, lng });
    return;
  }
  // treci klik pocinje novi izbor
  setCurrentLocation({ lat, lng });
  setDestination(null);
};
'''.strip("\n"))

    code_block(doc, '''
useEffect(() => {
  if (!currentLocation || !destination) return;

  const params = new URLSearchParams({
    origin_lat: String(currentLocation.lat),
    origin_lng: String(currentLocation.lng),
    dest_lat: String(destination.lat),
    dest_lng: String(destination.lng),
    hour: String(hour),
    day,
  });

  fetch(`${API_URL}/recommend?${params}`)
    .then((res) => res.json())
    .then(setRecommendations);
}, [currentLocation, destination, hour, day, radiusMeters]);
'''.strip("\n"))

    p(doc, (
        "Markeri na mapi su bojom kodirani (`ParkingMap.tsx`): plava tačka za polaznu lokaciju, "
        "crvena za destinaciju, zelena za preporučene parkinge, uz ljubičasti krug koji "
        "opciono prikazuje radijus pretrage oko destinacije. Za svaki marker prikazuje se "
        "popup sa detaljima (predviđena popunjenost, udaljenost od polazne tačke i "
        "destinacije)."
    ))

    code_block(doc, '''
function createDotIcon(color: string, size = 16) {
  return L.divIcon({
    className: "",
    html: `<div style="background:${color};width:${size}px;height:${size}px;
           border-radius:50%;border:2px solid white;
           box-shadow:0 0 3px rgba(0,0,0,0.6);"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const PARK_ICON = createDotIcon("#3b82f6");        // plavo - obican parking
const RECOMMENDED_ICON = createDotIcon("#22c55e", 20); // zeleno - preporuceno
const DESTINATION_ICON = createDotIcon("#ef4444", 20); // crveno - destinacija
const START_ICON = createDotIcon("#0ea5e9", 20);       // svetloplavo - pocetak
'''.strip("\n"))

    table_grid(
        doc,
        headers=["Boja markera", "Značenje"],
        rows=[
            ["Plava (svetlija)", "Polazna lokacija korisnika"],
            ["Crvena", "Izabrana destinacija"],
            ["Zelena", "Preporučeni parking (u top-N listi ili duž rute)"],
            ["Plava (obična tačka)", "Ostali, nepreporučeni parkinzi"],
            ["Ljubičasti krug", "Opcioni radijus pretrage oko destinacije"],
        ],
        caption="Legenda boja markera na mapi (ParkingMap.tsx), identična legendi prikazanoj u samoj aplikaciji.",
    )

    p(doc, (
        "Za svaku preporuku u bočnoj listi prikazuje se i razlaganje skora na tri komponente "
        "(dostupnost, vožnja, šetnja) u vidu horizontalnih traka, direktno preslikanih iz "
        "`score_components` polja koje vraća `/recommend` endpoint (Poglavlje 5.5) — korisnik "
        "tako može da vidi zašto je baš taj parking predložen, u skladu sa principom "
        "objašnjivosti preporuke iz Poglavlja 2."
    ))

    p(doc, (
        "Pored preporuke, aplikacija prikazuje i čitljivu adresu izabranih tačaka, umesto samih "
        "koordinata. Nakon svakog klika na mapu, koordinate se šalju Nominatim servisu "
        "(`fetchPlaceLabel`), koji vraća strukturiran opis lokacije (ulica, naselje, grad); "
        "rezultat se raščlanjuje i prikazuje u karticama „Početna tačka” i „Destinacija” iznad "
        "mape. Ukoliko servis nije dostupan ili zahtev ne uspe, aplikacija ne prekida rad — "
        "prikazuje se podrazumevani tekst „Nepoznata lokacija”, čime se izbegava da privremeni "
        "problem sa spoljašnjim servisom obori celu interakciju korisnika sa mapom i "
        "preporukama."
    ))

    p(doc, (
        "[SCREENSHOT: ovde umetnuti snimak ekrana pokrenute aplikacije — mapa sa markerima, "
        "izabranom polaznom tačkom i destinacijom, i bočnom listom preporuka sa razlaganjem "
        "skora. Snimak se pravi ručno: `npm run dev` u `frontend/`, otvoriti "
        "http://localhost:3000, kliknuti dve tačke na mapi, i uslikati prozor pregledača.]"
    ), italic=True)

    # ------------------------------------------------------------------
    h2(doc, "5.7. Analiza rezultata i primer korišćenja")

    h3(doc, "5.7.1. Ručno testiranje sistema")

    p(doc, (
        "Pošto projekat, u skladu sa svojim proof-of-concept obimom, namerno ne uključuje "
        "automatizovane testove (Poglavlje 2), ispravnost svakog dela sistema je pre integracije "
        "sa frontendom proverena ručno, kroz Swagger UI (`/docs`) generisan od strane FastAPI-ja "
        "(Poglavlje 5.4). Sledeća tabela sažima reprezentativne scenarije ručnog testiranja i "
        "njihov ishod:"
    ))

    table_grid(
        doc,
        headers=["Scenario", "Poziv", "Očekivano", "Rezultat"],
        rows=[
            ["Nepoznat parking", "GET /predict?park_id=NEPOSTOJI&hour=9&day=Mon", "HTTP 400/404 sa jasnom porukom", "OK — vraćeno 404 sa detaljem greške"],
            ["Granični sat (ponoć)", "GET /predict?park_id=BHMBCCMKT01&hour=0&day=Mon", "Predikcija van trening opsega (08–16h), ali bez pada servera", "OK — vraćena vrednost, model ekstrapolira"],
            ["Dan zadat imenom vs. brojem", "day=Mon i day=0", "Isti rezultat za oba zapisa", "OK — parse_day ispravno mapira oba oblika"],
            ["Prazan skup u radijusu", "GET /recommend sa vrlo malim radius parametrom", "Prazna lista, bez greške", "OK — vraćena prazna lista []"],
            ["Rangiranje po skoru", "GET /recommend za nekoliko različitih satova", "Redosled se menja u skladu sa dnevnom krivom", "OK — potvrđeno u Poglavlju 5.5 i 5.7.2"],
        ],
        caption="Reprezentativni scenariji ručnog testiranja backend API-ja preko Swagger UI (/docs).",
    )

    p(doc, (
        "Frontend je testiran manuelnim klikanjem kroz aplikaciju (pokretanjem `npm run dev` uz "
        "istovremeno pokrenut backend): provereno je da klik na mapu ispravno postavlja polaznu, "
        "pa destinacionu tačku, da se lista preporuka i vozna ruta osvežavaju pri promeni sata ili "
        "dana, i da se stanje ispravno resetuje dugmetom „Resetuj izbor”."
    ))

    h3(doc, "5.7.2. Tipičan scenario korišćenja")

    p(doc, (
        "Tipičan scenario korišćenja sistema izgleda ovako: korisnik otvara aplikaciju i vidi "
        "mapu Birminghama sa 29 plavih tačaka, po jedna za svaki parking iz dataseta. Klikom na "
        "mapu bira polaznu tačku (npr. mesto gde trenutno kreće), zatim drugim klikom bira "
        "destinaciju. Aplikacija odmah prikazuje voznu rutu (dobijenu od OSRM servisa) i, "
        "paralelno, poziva `/recommend` sa zadatim satom i danom. U roku od nekoliko stotina "
        "milisekundi, do pet zelenih markera pojavljuje se na mapi — parkinzi sa najvišim "
        "skorom — dok bočna lista prikazuje iste parkinge sortirane od najboljeg ka najgorem, "
        "sa razloženim skorom po komponentama."
    ))

    p(doc, (
        "Primer iz Poglavlja 5.5 (tabele za 9h i 14h) pokazuje najvažniji kvalitativni rezultat "
        "rada: sistem ne rangira parkinge samo po statičkim svojstvima (udaljenost, kapacitet), "
        "već stvarno menja preporuku u zavisnosti od predviđenog vremena zauzetosti — ponašanje "
        "koje bi bilo nemoguće postići bez ML komponente. Istovremeno, zahvaljujući transparentnoj "
        "formuli skora (Poglavlje 3.3), svaka promena poretka se može objasniti direktno kroz "
        "brojeve u `score_components`, bez potrebe za dodatnim alatima za interpretaciju modela."
    ))

    h3(doc, "5.7.3. Osetljivost preporuke na ponderima")

    p(doc, (
        "Pošto su ponderi w1, w2 i w3 obične konstante na vrhu `recommender.py`, njihov uticaj na "
        "konačnu preporuku moguće je proveriti eksperimentalno, bez ikakve izmene modela ili "
        "ponovnog treniranja. U nastavku je prikazan isti scenario kao u Poglavlju 5.5 (polazna "
        "tačka centar Birminghama, destinacija Bull Ring, sat 9, ponedeljak), izračunat pod tri "
        "različite kombinacije pondera:"
    ))

    table_grid(
        doc,
        headers=["Rang", "Podrazumevano (w1=0,55 w2=0,30 w3=0,15)", "Veći značaj blizini (w1=0,35 w2=0,55 w3=0,10)", "Veći značaj saobraćaju (w1=0,40 w2=0,20 w3=0,40)"],
        rows=[
            ["1.", "BHMBCCPST01 (0,6895)", "BHMBCCPST01 (0,7478)", "BHMBCCPST01 (0,4011)"],
            ["2.", "BHMBCCMKT01 (0,6759)", "BHMBCCMKT01 (0,6725)", "BHMBCCMKT01 (0,3960)"],
            ["3.", "Bull Ring (0,6028)", "BHMNCPHST01 (0,6077)", "Bull Ring (0,3544)"],
            ["4.", "Others-CCCPS119a (0,5643)", "Bull Ring (0,6056)", "BHMNCPHST01 (0,3116)"],
            ["5.", "BHMNCPHST01 (0,5539)", "Others-CCCPS119a (0,5318)", "Others-CCCPS119a (0,2945)"],
        ],
        caption="Rangiranje istih pet kandidata pod tri različite kombinacije pondera (stvaran izlaz recommend_parks() uz privremeno izmenjene konstante).",
    )

    p(doc, (
        "Prva dva mesta (BHMBCCPST01, BHMBCCMKT01) ostaju stabilna u sve tri kombinacije — oba "
        "parkinga su istovremeno blizu i imaju visoku predviđenu dostupnost, pa dominiraju "
        "nezavisno od raspodele pondera. Zanimljivija promena se dešava niže na listi: kada se "
        "poveća značaj blizine (w2 = 0,55), parking BHMNCPHST01 — koji je bliži polaznoj tački "
        "nego Bull Ring — preskače Bull Ring i penje se sa petog na treće mesto. Ovo potvrđuje da "
        "formula skora reaguje očekivano i predvidivo na promenu pondera, što je upravo svrha "
        "njihovog eksplicitnog definisanja kao lako izmenljivih konstanti (Poglavlje 3.3)."
    ))

    h3(doc, "5.7.4. Greška predikcije po pojedinačnom parkingu")

    p(doc, (
        "Agregatne metrike iz Poglavlja 5.3 (RMSE 12,65, MAE 9,46) predstavljaju prosek preko "
        "celog test skupa, ali kriju značajnu razliku u tačnosti predikcije između pojedinačnih "
        "parkinga. Grupisanjem grešaka test skupa po `SystemCodeNumber` dobija se sledeći uvid:"
    ))

    table_grid(
        doc,
        headers=["Parking", "Broj merenja (test)", "RMSE", "MAE"],
        rows=[
            ["BHMBRTARC01", "9", "2,63", "2,13"],
            ["Shopping", "26", "3,78", "2,63"],
            ["BHMBCCSNH01", "26", "4,25", "3,52"],
            ["…", "…", "…", "…"],
            ["BHMNCPPLS01", "26", "17,15", "14,87"],
            ["Others-CCCPS119a", "27", "18,64", "16,23"],
            ["BHMBCCPST01", "27", "25,47", "18,93"],
        ],
        caption="Tri parkinga sa najmanjom i tri sa najvećom greškom predikcije na test skupu (od ukupno 27 parkinga zastupljenih u test periodu).",
    )

    p(doc, (
        "Razlika je značajna — od RMSE ≈ 2,6 za najbolje predviđen parking (BHMBRTARC01) do RMSE "
        "≈ 25,5 za najteže predvidiv (BHMBCCPST01, ironično isti parking koji je u primerima iz "
        "Poglavlja 5.5 i 5.7.3 dosledno rangiran kao najbolja preporuka — što je vredno napomene "
        "kao ograničenje: sistem trenutno ne komunicira korisniku nivo pouzdanosti pojedinačne "
        "predikcije). Najverovatnije objašnjenje ovakve razlike jeste da parkinzi sa manjim brojem "
        "istorijskih merenja ili neuobičajenijim, manje ponovljivim dnevnim obrascem punjenja "
        "pružaju modelu manje signala za učenje, dok parkinzi sa stabilnim, ponovljivim obrascem "
        "(npr. Shopping, BHMBCCSNH01) bivaju predviđeni znatno preciznije. Ovo je i konkretan "
        "pravac za budući rad: dodavanje mere pouzdanosti (npr. interval predikcije) uz svaku "
        "preporuku, umesto samo jedne tačkaste vrednosti."
    ))

    h3(doc, "5.7.5. Ekstrapolacija van opsega merenja")

    p(doc, (
        "Poglavlje 2 je najavilo da dataset pokriva samo prozor od otprilike 08:00 do 16:30, i da "
        "predikcije van tog opsega treba tumačiti sa oprezom. Ovo je konkretno provereno pozivanjem "
        "`predictor.predict_occupancy_rate()` za parking BHMBCCMKT01, ponedeljak, za sva 24 sata u "
        "danu:"
    ))

    fig_extra = figure(doc, "extrapolation.png", "Predikcija modela za sve sate u danu (0–23h) za parking BHMBCCMKT01 — zelena zona označava opseg pokriven stvarnim merenjima.")

    p(doc, (
        f"Slika {fig_extra} potvrđuje očekivano ograničenje: unutar zelene zone (08–16:30h) "
        "predikcija prati očekivan dnevni obrazac (Poglavlje 5.2), dok van nje model vraća "
        "približno konstantne vrednosti — blizu nule pre 8h, i platoi na vrednosti poslednjeg "
        "poznatog sata (~20%) posle 16h. Ovo je direktna posledica prirode stabala odlučivanja: "
        "XGBoost ne ekstrapolira trend van opsega vrednosti feature-a viđenih tokom treniranja, "
        "već za ulaze van tog opsega vraća predikciju najbliže poznate grupe podataka (list "
        "stabla). U praksi to znači da bi upotreba sistema van perioda 08–16:30h zahtevala ili "
        "dataset sa punim dnevnim pokrivanjem, ili eksplicitno ograničenje korisničkog interfejsa "
        "na sate za koje model ima pouzdane podatke — što je jednostavna, ali važna preporuka za "
        "bilo koju produkcionu nadogradnju ovog proof-of-concept sistema."
    ))

    h3(doc, "5.7.6. Ograničenja")

    p(doc, (
        "Rezultati imaju i jasna ograničenja, koja proizlaze direktno iz prirode dataseta "
        "(Poglavlje 2): sistem trenutno pokriva samo 29 parkinga u jednoj nedelji decembra 2016. "
        "godine, koordinate su fiktivne, a saobraćajna komponenta skora je pojednostavljena "
        "simulacija, a ne stvaran podatak. Kao što je pokazano u Poglavlju 5.7.4, tačnost "
        "predikcije značajno varira od parkinga do parkinga, što znači da pouzdanost krajnje "
        "preporuke nije jednaka za sve lokacije, iako se to trenutno ne prikazuje korisniku. Ova "
        "ograničenja su detaljnije diskutovana u Poglavlju 6, zajedno sa pravcima za njihovo "
        "prevazilaženje u budućem radu."
    ))

    h3(doc, "5.7.7. Retrening modela u produkciji")

    p(doc, (
        "Model korišćen u ovom radu je statičan — istreniran jednom, nad jednom nedeljom "
        "istorijskih podataka (Poglavlje 5.3), i ne menja se dok se `ml/train.py` ručno ponovo ne "
        "pokrene. Za proof-of-concept ovakvog obima to je opravdano, ali svaka realna primena "
        "podrazumeva da podaci o zauzetosti pristižu kontinuirano, pa se prirodno postavlja "
        "pitanje kada i kako model treba ponovo trenirati."
    ))

    p(doc, (
        "Učestalost retreninga ne bi trebalo da prati učestalost pristizanja podataka, već brzinu "
        "promene samog obrasca ponašanja. Dnevni i nedeljni ritam popunjenosti (Poglavlje 5.2) je "
        "strukturno stabilan i ne menja se iz dana u dan, pa retrening na svaki novi merni podatak "
        "ne bi doneo praktičnu korist, a nepotrebno bi opteretio sistem. Realniji pristup je "
        "periodičan retrening (npr. nedeljno ili mesečno), ili — precesnije — retrening pokrenut "
        "detekcijom degradacije modela (drift): kada se greška modela nad svežim podacima primetno "
        "pogorša u odnosu na period kada je treniran, to je signal da se obrazac promenio (novi "
        "sadržaj u okolini parkinga, promena cene, sezona) i da je model potrebno osvežiti. Treba "
        "napomenuti i da je XGBoost, za razliku od pojedinih linearnih modela, prirodno pogodan "
        "isključivo za treniranje u paketima (batch) — svako pokretanje `ml/train.py` trenira "
        "model iznova, od nule, a ne inkrementalno nadograđuje postojeći."
    ))

    p(doc, (
        "Poseban problem je slučaj kada samo treniranje traje dugo (na znatno većem datasetu nego "
        "što je ovaj, trening bi mogao trajati satima ili danima), dok su predikcije korisnicima "
        "potrebne odmah. Rešenje za ovaj problem nije ubrzavanje treninga po svaku cenu, već "
        "arhitektonsko razdvajanje treniranja od servisiranja zahteva — princip koji je u ovom "
        "sistemu već delimično prisutan kroz podelu na `ml/train.py` (trening, van API-ja) i "
        "`backend/predictor.py` (servisiranje, koristi već gotov `model.joblib`). Realan tok bio "
        "bi:"
    ))

    bullets(doc, [
        "Trening se izvršava asinhrono, van API servera (npr. na zasebnoj mašini ili kao zakazan "
        "posao), dok API u međuvremenu nastavlja da opslužuje zahteve poslednjim važećim modelom "
        "— korisnici nikada ne čekaju da se trening završi.",
        "Novi model se pre uvođenja evaluira na istom hronološkom test skupu (Poglavlje 5.3), "
        "istom logikom (`evaluate()`), i poredi se sa metrikama trenutno aktivnog modela.",
        "Tek ako je nov model bar jednako dobar, zamenjuje se `model.joblib` (ili se čuva pod "
        "novim, verzionisanim imenom), čime se izbegava da neispravan ili lošiji model nenamerno "
        "zameni ispravan.",
    ])

    p(doc, (
        "Vredi napomenuti konkretno ograničenje trenutne implementacije: `backend/predictor.py` "
        "učitava `model.joblib` jednom, pri startu servera (na nivou modula), pa bi u sadašnjem "
        "obliku zamena modela zahtevala restart servisa da bi nova verzija stupila na snagu — u "
        "produkcionom sistemu bi ovo bilo rešeno kontrolisanim ponovnim učitavanjem ili rolling "
        "restartom instanci, bez prekida rada za korisnike. Ovakav mehanizam automatizovanog, "
        "validiranog i bezbednog retreninga nije bio predmet ovog rada, ali predstavlja prirodan i "
        "konkretan pravac nastavka u okviru master rada, nadovezan na arhitekturu koja je već "
        "postavljena razdvajanjem `train.py` i `predictor.py`."
    ))
