# UI redesign: plan (Faza 1, analiza)

Analiza je urađena na commitu `74cb53a`, grana `ui-redesign`. Faza 2 je urađena posle odobrenja (vidi 11).

## 0. Zatečeno stanje (bitno za odluke)

| Stavka | Stanje |
|---|---|
| Next.js | `16.2.12` (App Router), React `19.2.4` |
| Tailwind | **v4 je već podešen** (`@tailwindcss/postcss` u `postcss.config.mjs`, `@import "tailwindcss"` u `globals.css`, bez `tailwind.config`; tokeni idu u `@theme`) |
| Bootstrap | `bootstrap@5.3.8`, uvezen u `layout.tsx`. **Ceo markup danas koristi Bootstrap klase** (`card`, `row`, `col-*`, `btn`, `form-select`, `badge`, `progress`, `alert`, `placeholder-glow`) |
| Konflikt | Bootstrap CSS nije u `@layer`, a Tailwind v4 utilities jesu, pa **Bootstrap uvek pobeđuje** kad se klase poklope (`border`, `shadow-sm`, `rounded-*`, `small`, `container`, `placeholder`...). Mešanje dva sistema je krhko. |
| Ikonice | `lucide-react` nije instaliran |
| Dark mode | ne postoji |
| ESLint | `eslint-config-next` core-web-vitals + typescript |

## 1. Rute

| Fajl | Tip | Šta radi |
|---|---|---|
| `app/layout.tsx` | server komponenta | `<html lang="en">`, fontovi Geist/Geist Mono (`next/font/google`), uvoz Bootstrap CSS-a i `globals.css`, `metadata` (title „Smart Parking“) |
| `app/page.tsx` (`/`) | **client** (`"use client"` na vrhu) | **jedina stranica**: ceo dashboard (simulacija, izbor vremena, ruta, mapa, preporuke, poređenje predikcije i stvarnosti) |

Nema drugih ruta, `loading.tsx`, `error.tsx`, `not-found.tsx` ni route handlera.

Ostali fajlovi u `app/` nisu rute:

| Fajl | Uloga |
|---|---|
| `ParkingMap.tsx` | client, Leaflet mapa; izvozi i tipove `Park`, `ParkState`, `HistoryResponse`, `Recommendation`, `RouteParking` |
| `Sparkline.tsx` | client, SVG mini-grafik u popup-u parkinga |
| `CompareChart.tsx` | client, SVG grafik „predikcija vs stvarnost“ + `CompareLegend` |
| `occupancy.ts` | čista funkcija `displayOccupancy()`, odvojena da `page.tsx` ne bi uvukao leaflet na server |

## 2. Pozivi ka backendu (Python FastAPI, `http://127.0.0.1:8000`)

Svi pozivi su u **client komponenti `page.tsx`**, preko `fetch` u `useEffect` ili handlerima. URL je hardkodovan (`API_URL`), bez env varijable. CORS u backendu dozvoljava samo `http://localhost:3000`.

| # | Metod i URL | Parametri | Odgovor (polja koja se koriste) | Kada se zove |
|---|---|---|---|---|
| B1 | `GET /parks` | – | `Park[]`: `park_id, name, capacity, lat, lng, type, confirmed` | jednom pri mount-u |
| B2 | `GET /simulation/state` | – | `current_time, running, speed_minutes_per_second, tick_minutes, grid_start, grid_end, test_start, test_end` | **polling na 3 s** (`POLL_INTERVAL_MS = 3000`) |
| B3 | `GET /state` | opciono `target_time=YYYY-MM-DDTHH:MM:00` | `{current_time, parks: ParkState[]}`; po parkingu `current_occupancy_rate, current_available_spots, target_time, target_occupancy_rate, target_available_spots, is_prediction, horizon_minutes, horizon_clamped, mae` | **polling na 3 s**, isti interval kao B2; interval se ponovo kreira kad se promeni `targetTimeIso`. `current_time` iz odgovora frontend **ne koristi**. |
| B4 | `POST /simulation/start?speed={speed}` | `speed` iz select-a | stanje sata (kao B2) | dugme „Start“ |
| B5 | `POST /simulation/pause` | – | stanje sata | dugme „Pauza“ |
| B6 | `POST /simulation/speed?factor={n}` | 1, 2, 10, 60, 500 | stanje sata | promena brzine u select-u; greška se tiho ignoriše |
| B7 | `POST /simulation/reset?start_time={date}T{time}:00` | datum i vreme iz test perioda | stanje sata; ako je `!res.ok`, prikazuje se `detail` iz greške | dugme „Postavi vreme“ |
| B8 | `GET /compare` | `park_id, date (YYYY-MM-DD), from_time (HH:MM)` | `CompareResponse`: `park_id, name, date, day_of_week, from_time, has_reading_at_from_time, points[{time, actual, forecast, rolling_1h, typical}], mae{forecast, typical_same_slots, rolling_1h}` | kad se promeni izabrani parking, datum ili HH:MM simuliranog vremena (u praksi na svaki tik sata dok simulacija radi); `!ok` daje `null` |
| B9 | `GET /history?park_id=` | `park_id` | `HistoryResponse`: `park_id, current_time, day_of_week, typical_curve[{time, avg_occupancy_rate}], actual_today[{time, occupancy_rate}]` | pri otvaranju popup-a parkinga; keš u `historyByPark` |
| B10 | `GET /recommend` | `origin_lat, origin_lng, dest_lat, dest_lng`, opciono `radius` (m), opciono `departure_time` (= `targetTimeIso`) | `Recommendation[]` (top 5): `park_id, lat, lng, eta_minutes, horizon_minutes, predicted_occupancy_rate, availability_score, distance_to_origin_km, distance_to_destination_km, score, score_components{predicted_availability, closeness, traffic, weights{w1_predicted_availability, w2_proximity, w3_traffic}}` | kad postoje i start i cilj, i kad se promeni start, cilj, radius ili izabrano vreme |

Spoljni servisi (nisu Python, takođe se ne diraju):

| # | URL | Namena |
|---|---|---|
| E1 | `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat&lon` | naziv ulice i grada za start i cilj; pri grešci vraća „Nepoznata ulica/grad“ |
| E2 | `https://router.project-osrm.org/route/v1/driving/...?overview=full&geometries=geojson` | geometrija, dužina i trajanje rute |
| E3 | `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png` | OSM pločice mape |

## 3. Prikaz podataka o parkinzima (kako sada radi)

- **Zauzetost** (`displayOccupancy`): ako je izabrano vreme (`target_time != null`), prikazuje se `target_occupancy_rate` (izmereno za prošlost/sadašnjost, predikcija za budućnost, vidi `is_prediction`). Inače se prikazuje `current_occupancy_rate`. Vrednost je u procentima (0–100).
- **Boja statusa** (`occupancyStatusColor`): `null` je sivo `#898781` (nema očitavanja), `< 50` zeleno `#0ca30c`, `50–79.9` žuto `#fab219`, `≥ 80` crveno `#d03b3b`. **Status se danas prenosi samo bojom** (tačka od 14 px), bez teksta i ikone.
- **Mapa**: na mapi su samo parkinzi sa koordinatama (9 od 15), centar je Norwich `[52.6287, 1.2974]`, zoom 12. Preporučeni parkinzi imaju veći marker sa ljubičastim prstenom i brojem ranga. Start je plava tačka, cilj crvena. Ruta je plava polilinija. Radius je ljubičasti krug oko cilja. Kad postoje start i cilj, `fitBounds` se primenjuje na rutu (padding 50, maxZoom 15).
- **Tooltip** markera: ime parkinga, uz „(uz rutu)“ ako je parking blizu rute.
- **Popup** parkinga: ime i badge tipa, zauzetost (trenutna ili „u HH:MM (predikcija/izmereno)“), slobodna mesta, upozorenje ako je horizont odsečen (`horizon_clamped`), pouzdanost `±mae p.p.` i sparkline (tipično, stvarno, prognoza, linija „sada“) kad stigne `/history`.
- **Legenda** je gore desno preko mape i sakriva se dok je popup otvoren.
- **Preporuke** (desna kolona, „Top preporuke za cilj“): rang i ime, skor (2 decimale), predikcija pri dolasku (`~eta min`, `horizont`, `%`), hodanje do cilja (km), razlozi („Velika dostupnost“ ako je `availability_score ≥ 0.6`, „U okviru radijusa hodanja“) i tri trake delova skora (vrednost × ponder: dostupnost +, blizina +, saobraćaj −).
- **Parkinzi uz rutu**: do 5 parkinga na ≤ 2 km od rute, izvedeno lokalno iz `/state` (ime, udaljenost od rute, zauzetost u %).
- **Predikcija vs stvarnost**: grafik za izabrani parking (klik na marker; podrazumevano prvi parking sa koordinatama). Dugme „Otkrij/Sakrij stvarnost“, checkbox „Prognoza sat unapred“, upozorenje ako nema očitavanja, MAE kad je stvarnost otkrivena.
- **Osvežavanje u realnom vremenu**: polling B2 i B3 na 3 s. Simulirano vreme (`current_time`) prikazuje se formatirano (`sr-Latn-RS`). **Vreme poslednjeg osvežavanja (wall-clock) ne postoji** u podacima ni u state-u.

## 4. Interakcije

| # | Interakcija | Ponašanje |
|---|---|---|
| I1 | Klik na mapu (1.) | postavlja početnu tačku i briše grešku |
| I2 | Klik na mapu (2.) | postavlja cilj, pa se pokreću ruta (E2), preporuke (B10) i nazivi mesta (E1) |
| I3 | Klik na mapu (3.+) | otvara modal „Zameniti trenutnu rutu?“: „Otkaži“ ili „Obriši i započni novu rutu“ (klik postaje novi start, cilj i ruta se brišu) |
| I4 | „Resetuj izbor“ | briše start, cilj, rutu, preporuke i pending klik |
| I5 | Start / Pauza | B4 / B5; dugme se menja po `simState.running` |
| I6 | Brzina (1x–500x) | B6; lokalni `speed` počinje od 2 i **nije sinhronizovan** sa backendom pri učitavanju |
| I7 | Vreme (mapa i polazak) | „Sada“ ili HH:MM na 30-min mreži, vezano za simulirani datum. Menja B3 (`target_time`) i B10 (`departure_time`). |
| I8 | Radius (m) | `type=number`, `min=100 max=1000`, placeholder „npr. 500“. **Nema validacije** (min/max se ne proveravaju, vrednost ide u B10 kakva jeste), a prazno polje znači bez radiusa. Crta krug na mapi. |
| I9 | Skok na datum | `date` input ograničen na `test_start … test_end−1 dan`, plus HH:MM select i „Postavi vreme“ (B7). Resetuje „reveal“. |
| I10 | Klik na marker parkinga | otvara popup, učitava B9, bira parking za grafik poređenja (B8), sakriva legendu |
| I11 | Hover na marker | tooltip sa imenom |
| I12 | Otkrij/Sakrij stvarnost | toggle `reveal` u grafiku |
| I13 | Checkbox „sat unapred“ | toggle `showRolling` (linija + legenda + MAE) |
| I14 | Popup start/cilj markera | tekst „Početna lokacija“ / „Destinacija“ |

Filtriranja liste parkinga nema.

## 5. Stanja

| Stanje | Kako se danas prikazuje |
|---|---|
| Učitavanje parkinga/mape | nema indikatora; mapa se prikaže bez markera dok B1/B3 ne stignu. `dynamic()` nema `loading` fallback. |
| Učitavanje rute | kartica „Ruta“ prikazuje „Učitavanje rute...“ |
| Učitavanje naziva mesta | „Učitavanje...“ u karticama start/cilj |
| Učitavanje preporuka | 3 skeleton bloka (Bootstrap `placeholder-glow`) |
| Prazno (preporuke) | bez cilja: „Izaberi cilj na mapi...“; sa ciljem, a bez rezultata: „Nema parkinga u trenutnom skupu“ + savet za radius |
| Prazno (uz rutu, poređenje) | kartica se ne prikazuje |
| Greška | **jedno globalno polje `error`** (žuti `alert` u desnoj koloni); poslednja greška prepisuje prethodnu |
| Backend nedostupan | B1 javlja „Ne mogu da učitam listu parkinga. Da li backend radi na :8000?“, ali polling B2/B3 na 3 s je prepisuje porukama „Ne mogu da učitam simulacioni sat.“ / „...stanje parkinga.“. Kad se backend vrati, poruka **ostaje** dok je neka akcija ne obriše. |
| Ruta nije nađena | „Ruta nije pronađena za ove dve lokacije.“ |

Postojeće krhkosti, primećene usput. **Ne diram ih**, jer su logika, a ne prezentacija:
- `/recommend` sa HTTP greškom vraća `{detail}`, koji se upisuje u `recommendations`, pa `.map` puca.
- `/state` sa HTTP greškom tiho daje prazno stanje (svi markeri sivi).

## 6. Granice `"use client"` i browser API-ji

- `layout.tsx` je server komponenta i ostaje takva.
- `page.tsx` je client u celini (state, efekti, `fetch`, polling). Ne pomeram granicu.
- `ParkingMap.tsx` je client. `leaflet` pristupa `window`, pa se uvozi **samo** preko `dynamic(() => import("./ParkingMap"), { ssr: false })` u `page.tsx`. Tu je i uvoz `leaflet/dist/leaflet.css`. Ostaje isto.
- `occupancy.ts` je namerno odvojen od `ParkingMap.tsx` (bez leaflet importa). Ostaje.
- `Sparkline.tsx` i `CompareChart.tsx` su client, čist SVG. `Date` (lokalna vremenska zona) koristi se u `minutesOfDay`.
- Markeri su `L.divIcon` sa **inline HTML stringom**, pa Tailwind klase tu rade samo ako ih Tailwind vidi u izvornom kodu (vide se, jer su u `.tsx` fajlu). Za svaki slučaj stilove markera stavljam u `globals.css`.

## 7. Predlog redizajna

### 7.1 Princip

Jedna stranica i isti tok rada (CLAUDE.md: „minimalni UI je namerno izabran“). Menja se samo raspored, vizuelni jezik i stanja. Dashboard se deli na tri zone:

```
┌────────────────────────────────────────────────────────────────────────┐
│ ▣ Smart Parking · Norfolk   [● Sim: sub 18.11. 10:00  ▶/❚❚  2x ▾]      │  ← header (sticky)
│                             Vreme: [Sada ▾]  Skok: [datum][HH:MM][Postavi]│
├───────────────────────────────────────────────┬────────────────────────┤
│ [Start: ulica…] → [Cilj: ulica…]  [3,2 km·8 min] [Radius m] [Resetuj]  │  ← traka rute
├───────────────────────────────────────────────┼────────────────────────┤
│                                               │ ★ PREPORUKA #1          │
│                   MAPA                        │   ime · skor 0.82       │
│      (markeri = pilula sa % + ikona)          │   zašto: 3 trake + čipovi│
│                                   [Legenda]   │ #2…#5 (kompaktno)       │
│                                               ├────────────────────────┤
│                                               │ Parkinzi uz rutu        │
│                                               ├────────────────────────┤
│                                               │ Predikcija vs stvarnost │
└───────────────────────────────────────────────┴────────────────────────┘
```

- **Desktop (≥ lg)**: grid `minmax(0,1fr) 400px`. Mapa ima `calc(100vh - header)`, a bočna kolona sopstveni scroll.
- **Mobilni**: header se prelama (kontrole simulacije idu u red ispod), mapa `60vh`, kartice ispod nje u istom redosledu (preporuke prve).
- Modal za zamenu rute ostaje isti po ponašanju, uz `role="dialog"`, `aria-modal`, fokus na „Otkaži“ i zatvaranje na Esc. **Esc je mala nova interakcija i radi isto što i „Otkaži“; uključujem je samo uz tvoju potvrdu.**

### 7.2 Po zonama

| Zona | Šta se menja |
|---|---|
| Header | brend + naslov; „live“ indikator (zelena pulsirajuća tačka i tekst „Simulacija radi“ / sivo „Pauzirano“), simulirano vreme u `font-mono`, segmentno dugme Start/Pauza sa lucide ikonicama `Play`/`Pause`, select brzine. Ispod: „Vreme (mapa i polazak)“ i „Skok na datum“ sa istim pomoćnim tekstovima. |
| Traka rute | tri kompaktna „chip“ polja (Start / Cilj / Ruta) sa ikonama `MapPin`, `Flag`, `Route`, polje Radius i dugme „Resetuj izbor“ (`RotateCcw`). Kada ništa nije izabrano, uputstvo „Klikni na mapu: prvi klik je start, drugi cilj“ stoji kao istaknut hint. |
| Mapa | ista biblioteka, isti markeri i popup-i, isto ponašanje. Menja se **izgled markera** (vidi 7.4), **legenda** (kartica sa tokenima, isti sadržaj, ista logika skrivanja) i **popup** (tipografija, status badge sa tekstom, red sa ključnim brojevima). |
| Preporuke | kartica #1 je istaknuta (okvir u boji preporuke, oznaka „Preporučeno“, veći skor). Blok **„Zašto?“** prikazuje postojeće podatke: 3 trake delova skora (dostupnost / blizina / saobraćaj sa `vrednost × ponder`), čipove razloga, ETA, horizont, predviđenu zauzetost **sa status badge-om**, hodanje do cilja. #2–#5 su kompaktne kartice sa istim podacima. Skeleton u Tailwind stilu, prazna stanja sa ikonom i istim tekstom. |
| Uz rutu | lista sa status badge-om (boja + ikona + %) umesto golog broja |
| Predikcija vs stvarnost | ista kartica i kontrole; dugme reveal kao toggle (`Eye`/`EyeOff`, `aria-pressed`), legenda kao čipovi sa uzorkom linije (puna/isprekidana), MAE kao mali stat red. Boje linija ostaju iste. |
| Greške | globalni `error` se prikazuje kao banner sa ikonom `AlertTriangle` u vrhu bočne kolone (na mobilnom ispod headera), `role="alert"`. Kad poruka govori da je backend nedostupan, dodaje se objašnjenje „Pokreni backend: `npm run backend`“. To je samo dodatni tekst; logika ostaje ista. |
| Učitavanje mape | `dynamic(..., { ssr: false, loading: () => <MapSkeleton/> })`. **Opcija `loading` je jedina izmena na `dynamic()` pozivu, pa je tražim posebno** (ne menja SSR ni ponašanje). |

### 7.3 Status zauzetosti (boja + tekst + ikona)

Pragovi ostaju **isti** kao u `occupancyStatusColor` (< 50, 50–80, ≥ 80, null):

| Status | Pragovi | Boja (fill) | Tekst | Ikona (lucide) |
|---|---|---|---|---|
| free | `< 50 %` | `#0ca30c` (zadržana) | „Slobodno“ | `CircleCheck` |
| busy | `50–80 %` | `#fab219` (zadržana) | „Skoro puno“ | `CircleAlert` |
| full | `≥ 80 %` | `#d03b3b` (zadržana) | „Puno“ | `CircleX` |
| unknown | `null` | `#898781` (zadržana) | „Nema podatka“ | `CircleHelp` |

Boje markera ostaju iste (već su iz dataviz status palete), pa grafikoni i mapa ostaju konzistentni sa onim što je opisano u radu. Za tekst na svetloj pozadini koriste se tamnije varijante (`free-ink #0a6e0a`, `busy-ink #8a5a00`, `full-ink #a52a2a`) zbog kontrasta ≥ 4.5:1.

> Pitanje: „Puno“ za ≥ 80 % je strogo uzev netačno (ima još mesta). Alternativa sa istim pragovima je „Dosta mesta / Popunjava se / Skoro puno“. Biram ono što ti odobriš.

### 7.4 Markeri na mapi (samo izgled)

- Parking marker postaje **pilula sa procentom** (npr. `72%`) u boji statusa, sa belim okvirom. Status se onda čita i bez boje. Za `null` piše `–`.
- Preporučeni parking: isti marker uz ljubičasti prsten i badge ranga (kao danas, doteran).
- Start i cilj: tačke ostaju, uz mali kontrast-prsten. Ruta i krug radiusa: iste boje.
- Iz koda se ne briše nijedan marker, tooltip ni popup.

### 7.5 Design tokeni (`globals.css`, Tailwind v4 `@theme`)

```css
@theme {
  /* neutralne */
  --color-bg: #f4f6fa;          /* pozadina stranice (umesto gradijenta) */
  --color-surface: #ffffff;     /* kartice */
  --color-surface-2: #f8fafc;   /* unutrašnji blokovi, skeleton */
  --color-border: #e2e8f0;
  --color-ink: #0f172a;         /* osnovni tekst */
  --color-ink-muted: #475569;   /* sekundarni tekst (≥ 4.5:1 na beloj) */
  --color-ink-subtle: #64748b;

  /* brend / akcija */
  --color-primary: #2a78d6;     /* = boja rute i "stvarno" linije */
  --color-primary-ink: #1d5aa6;
  --color-accent: #4a3aa7;      /* = boja preporuke (prsten markera, radius) */

  /* status zauzetosti (iste kao markeri) */
  --color-free: #0ca30c;   --color-free-ink: #0a6e0a;   --color-free-soft: #e7f6e7;
  --color-busy: #fab219;   --color-busy-ink: #8a5a00;   --color-busy-soft: #fff4d6;
  --color-full: #d03b3b;   --color-full-ink: #a52a2a;   --color-full-soft: #fbe9e9;
  --color-unknown: #898781;

  /* grafikoni (postojeće) */
  --color-forecast: #eb6834;  --color-rolling: #7c5cc4;  --color-typical: #898781;

  --font-sans: var(--font-geist-sans);   /* Geist je već učitan, a body ga danas ne koristi (Arial) */
  --font-mono: var(--font-geist-mono);   /* vreme, brojevi */

  --radius-card: 0.875rem;  --radius-control: 0.5rem;  --radius-pill: 9999px;
}
```

- **Spacing**: Tailwind skala sa ritmom 4 px. Unutar kartice `p-4`, razmak između kartica `gap-3`, sekcije `gap-4`/`gap-6`.
- **Tipografija**: Geist. Naslov stranice `text-lg font-semibold`, naslov kartice `text-sm font-semibold`, labele `text-xs font-medium uppercase tracking-wide text-ink-muted`, brojevi `tabular-nums`.
- **Senke**: jedna (`shadow-sm` + `border`) za kartice, `shadow-lg` samo za modal i legendu.
- **Fokus**: `focus-visible:ring-2 ring-primary ring-offset-2` na svim kontrolama.
- **Dark mode**: **predlažem da ga ne radimo.** OSM pločice su svetle i tamni UI oko svetle mape izgleda loše. Tamne pločice bi bile novi spoljni servis, a to je promena ponašanja.

### 7.6 Pristupačnost

- Sve kontrole dobijaju `<label htmlFor>`. Danas labele „Simulacija“, „Vreme“, „Radius“ i „Skok“ nisu vezane za input.
- `aria-label` na select brzine i HH:MM skoka; `aria-pressed` na toggle-u reveal; `aria-live="polite"` samo na statusu „radi/pauzirano“ i na listi preporuka. Simulirano vreme se menja svake 3 s, pa ono nema `aria-live`, da čitač ekrana ne bi stalno čitao.
- Status uvek ima boju, tekst i ikonu.
- Kontrast teksta je ≥ 4.5:1 (zato postoje `*-ink` tokeni).
- Tastatura: redosled header → traka rute → bočna kolona. Mapa je i dalje Leaflet; markeri su dostupni tastaturom kao i danas (Leaflet ih čini fokusabilnim).

### 7.7 Komponente (samo prezentacione)

Novi folder `app/_components/` (privatni folder, prefiks `_` znači da nije ruta). Svi fajlovi su bez fetch-a i bez state logike:

- `StatusBadge.tsx`: `occupancyStatus(rate)` → `{key, label, Icon}`, sa istim pragovima. Napomena: `occupancyStatusColor` u `ParkingMap.tsx` ostaje izvor boja za markere.
- `Card.tsx` (`Card`, `CardHeader`): okvir kartice.
- `ScoreBar.tsx`: jedna traka dela skora.
- `Skeleton.tsx`, `EmptyState.tsx`, `ErrorBanner.tsx`.

`page.tsx` zadržava sav state, efekte, fetch-eve i handlere. Menja se samo JSX u `return`.

## 8. Plan implementacije (Faza 2, inkrementalno)

Posle svakog koraka idu `npm run build` i `npm run lint`, pa ručna provera u browseru.

1. **Temelj**: tokeni u `globals.css`, Geist kao osnovni font, `npm i lucide-react`, prezentacione komponente iz 7.7. Vizuelno se još ništa ne menja.
2. **Header + simulacione kontrole + skok na datum** (`page.tsx`, samo JSX)
3. **Traka rute + modal** (`page.tsx`)
4. **Bočna kolona: greška, preporuke, uz rutu** (`page.tsx`)
5. **Predikcija vs stvarnost** (`page.tsx` + `CompareLegend` izgled u `CompareChart.tsx`; SVG geometrija se ne dira)
6. **Mapa: markeri, legenda, popup, sparkline legenda** (`ParkingMap.tsx`, `Sparkline.tsx`, samo izgled)
7. **Uklanjanje Bootstrap-a** (uvoz u `layout.tsx` + zavisnost u `package.json`). Tek kad nijedna Bootstrap klasa ne ostane, i **samo uz tvoju potvrdu.**
8. Ručna provera po checklisti ispod, rezime izmena, upis u `PROGRESS.md` i commit.

Tokom koraka 2–6 Bootstrap ostaje uvezen, da ono što još nije prerađeno ne bi izgubilo stil. Zbog konflikta iz tačke 0, prerađeni delovi koriste isključivo Tailwind klase, bez mešanja u istom elementu.

## 9. Šta se NE dira

`API_URL`, svi URL-ovi i parametri (B1–B10, E1–E3), `POLL_INTERVAL_MS`, svi `useEffect`/handleri, `haversineKm`/`distanceToRouteKm`/`routeParkings`, `getRecommendationReasons`, `getScoreParts` (osim `barClass` stringa), `displayOccupancy`, pragovi statusa, tipovi i nazivi polja, `dynamic(... ssr:false)`, `MapBoundsHandler`, `ClickHandler`, centar i zoom mape, SVG geometrija grafika, `next.config.ts`, backend.

## 10. Checklista za ručno testiranje

☑ = provereno u Chrome-u posle redizajna (desktop 1334 px + iframe 390 px). ☐ = još nije prođeno ručno, a kod iza te stavke nije menjan (menjan je samo izgled).

Backend: `npm run backend` (iz root-a). Frontend: `npm run dev`.

| # | Provera | OK |
|---|---|---|
| R1 | `/` se učitava, naslov taba „Smart Parking“ |☑ |
| B1 | Na mapi se vidi 9 markera parkinga u Norwich-u |☑ |
| B2 | Simulirano vreme se menja na ~3 s dok simulacija radi |☑ |
| B3 | Boje i procenti markera se osvežavaju; uz izabrano vreme prikazuje se zauzetost za to vreme |☑ |
| B4/I5 | „Start“ pokreće sat, dugme postaje „Pauza“ | ☐ |
| B5/I5 | „Pauza“ zaustavlja sat | ☐ |
| B6/I6 | Promena brzine (npr. 60x) ubrzava sat | ☐ |
| B7/I9 | Skok na 18.11.2017 10:00 postavlja sat; datum van test perioda nije moguće izabrati; greška iz backenda se prikazuje | ☐ |
| B8 | Kartica „Predikcija vs stvarnost“ se pojavljuje za podrazumevani parking |☑ |
| B9/I10 | Klik na marker otvara popup sa zauzetošću, slobodnim mestima, pouzdanošću i sparkline-om |☑ |
| I10 | Isti klik prebacuje grafik poređenja na taj parking; legenda mape nestaje dok je popup otvoren |☑ |
| I11 | Hover na marker prikazuje ime (+ „(uz rutu)“ kad treba) | ☐ |
| I1 | Prvi klik na mapu postavlja start (plavi marker, naziv ulice u traci) |☑ |
| I2/E1/E2 | Drugi klik postavlja cilj; pojavljuju se ruta, km/min, nazivi mesta i mapa se centrira na rutu |☑ |
| B10 | Pojavljuju se do 5 preporuka sa rangom, skorom, ETA, horizontom, zauzetošću, hodanjem, razlozima i 3 trake skora; markeri imaju broj ranga |☑ |
| — | Preporuke: skeleton tokom učitavanja |☑ |
| — | Uz rutu: lista do 5 parkinga sa km od rute i % |☑ |
| I3 | Treći klik otvara modal; „Otkaži“ ne menja ništa; „Obriši i započni“ postavlja novi start |☑ |
| I4 | „Resetuj izbor“ briše start, cilj, rutu i preporuke | ☐ |
| I7 | Izbor vremena (npr. 18:00) menja markere i preporuke (polazak); „Sada“ vraća trenutno stanje | ☐ |
| — | Popup: za buduće vreme piše „(predikcija)“, za prošlo „(izmereno)“; upozorenje za horizont > ~15.5 h | ☐ |
| I8 | Radius 500 crta krug oko cilja i menja preporuke; prazno polje uklanja krug | ☐ |
| I12 | „Otkrij stvarnost“ prikazuje stvarnu liniju posle „sada“ i MAE; „Sakrij“ vraća | ☐ |
| I13 | „Sat unapred“ dodaje ljubičastu liniju, stavku legende i MAE vrednost | ☐ |
| — | Poređenje: poruka „Nema očitavanja u ovom trenutku...“ kad nema podatka | ☐ |
| I14 | Popup start/cilj markera prikazuje „Početna lokacija“ / „Destinacija“ | ☐ |
| — | Prazno stanje preporuka bez cilja i sa ciljem bez rezultata (npr. radius 100 daleko od parkinga) | ☐ |
| — | Ugašen backend: prikazuje se banner greške; posle paljenja podaci se vraćaju | ☐ |
| — | Status: svaki parking ima boju, tekst i ikonu (u legendi, popup-u, preporukama, listi uz rutu) |☑ |
| — | Tastatura: Tab prolazi kroz sve kontrole sa vidljivim fokusom | ☐ |
| — | Mobilni (≈ 390 px): nema horizontalnog scrolla, mapa je upotrebljiva, kartice su ispod |☑ |
| — | `npm run build` i `npm run lint` prolaze |☑ |

## 11. Rezime izmena (Faza 2)

Odluke: Bootstrap je uklonjen, rad je na grani `ui-redesign`, bez dark mode-a. Tekst statusa je „Dosta mesta / Popunjava se / Skoro puno / Nema podatka“, uz iste pragove.

**Zavisnosti:** uklonjen je `bootstrap`, dodat je `lucide-react`. Tailwind v4 je bio podešen i nije menjan.

**`layout.tsx`:** uklonjen je uvoz Bootstrap CSS-a, `lang="sr-Latn"`, a body koristi tokene.

**`globals.css`:** design tokeni (`@theme`), Geist kao osnovni font (pre toga Arial), izgled Leaflet popup-a i tooltip-a, CSS za marker-pilulu i pin, pulsirajuća tačka za „Simulacija radi“, `prefers-reduced-motion`.

**Novo: `app/_components/`** (privatni folder, nije ruta):
- `status.ts`: pragovi i boje statusa na jednom mestu (isti kao ranije).
- `ui.tsx`: `Card`, `StatusBadge` (boja + ikona + tekst), `InfoTile`, `Stat`, `Skeleton`, `EmptyState`, `FieldLabel`, klase za dugmad i polja.

**`page.tsx`:** promenjen je samo JSX. Pozivi, parametri, polling i handleri su isti.
- Header: brend, status simulacije, simulirano vreme, Start/Pauza, brzina. Sticky je samo na desktopu.
- Kartica kontrola: vreme, radius sa jedinicom „m“, skok na datum. Labele su vezane za polja.
- Kartica „Ruta“: tri pločice (start, cilj, ruta) i „Resetuj izbor“.
- Mapa: hint „Klikni na mapu…“ dok nema starta ili cilja, i „Učitavanje parkinga…“.
- Bočna kolona, novi redosled: greška, preporuke, uz rutu, poređenje.
  - Preporuka #1 je istaknuta. Blok „Zašto?“ prikazuje delove skora i formulu skora iz pondera koje vraća backend.
  - Zauzetost pri dolasku i lista uz rutu imaju status badge.
- Poređenje: dugme reveal sa `aria-pressed`, MAE kao stat pločice.
- Dodaci ponašanju, oba odobrena: `loading` fallback na `dynamic()` (`ssr:false` ostaje) i Esc zatvara dijalog zamene rute (isto što i „Otkaži“). Dijalog ima `role="dialog"` i fokus na „Otkaži“.
- `getScoreParts`: promenjeni su samo `barClass` stringovi (Bootstrap → Tailwind).

**`ParkingMap.tsx`:** ista biblioteka, isti markeri, popup-i, centriranje, `fitBounds` i ponašanje legende pri otvorenom popup-u.
- Marker parkinga je pilula sa procentom; preporučeni parking ima prsten i rang. Dodat je `riseOnHover`.
- Ruta ima belu „oblogu“ ispod linije, zbog čitljivosti.
- Popup: status badge, pločice zauzetosti i slobodnih mesta, skeleton dok se ne učita istorija.
- Legenda: dodata je stavka „Nema podatka“ i „Ruta“. Na mobilnom je sklopiva.
- `occupancyStatusColor` čita boje iz `status.ts`; vrednosti su iste.

**`Sparkline.tsx`, `CompareChart.tsx`:** samo legende (uzorak linije sa istim dash-om) i pozadina sparkline-a. Geometrija SVG-a nije menjana.

**Provera:**
- `npm run build` prolazi.
- `npm run lint` javlja iste 4 greške `react-hooks/set-state-in-effect` kao pre redizajna. Sve su u postojećim efektima u `page.tsx` (učitavanje naziva mesta, preporuka i rute), koji namerno nisu dirani. Nema novih grešaka ni upozorenja.

**Ostavljeno kako jeste (logika, nije prezentacija):**
- `/recommend` sa HTTP greškom ruši listu.
- Poruka o grešci ostaje i kad se backend vrati.
- Lokalni izbor brzine nije sinhronizovan sa backendom.
- Nominatim vraća naziv grada na lokalnom pismu (npr. „Норич“), jer zahtev nema `accept-language`.

### Dopuna: mapa kao centralni deo (2026-10-27)

- `main` je jedna kolona preko cele širine: kontrole i ruta (na ≥ xl jedna pored druge), pa banner greške, pa **mapa preko cele širine** (`calc(100vh - 7rem)` na desktopu), pa ispod mape preporuke (levo; #1 preko cele širine, ostale u mreži 2×2) i desno „Parkinzi uz rutu“ i „Predikcija vs stvarnost“.
- Pošto su preporuke ispod mape, na vrhu mape stoji kartica „Preporučeno: #1 … · skor“ sa dugmetom „Sve preporuke“ (link `#preporuke`, glatko skrolovanje). Dok se računa, prikazuje se „Računam preporuke…“. Na mobilnom je kartica na dnu mape.
- Hint „Klikni na mapu…“ je na desktopu na vrhu mape i prikazuje se tek kad se parkinzi učitaju.
- Header i footer su preko cele širine.
- Provereno u Chrome-u (1531 px): start → cilj → kartica #1 na mapi → „Sve preporuke“ skroluje do liste. Build je OK. Lint daje iste 4 stare greške.

### Dopuna: mobilni prikaz posle izmene rasporeda (2026-10-27)

- Na mobilnom je mapa bila tek na ~860 px, ispod dve kartice kontrola. Sada je redosled na mobilnom (CSS `order`, bez izmene markupa): header → (greška) → **mapa** → ruta → kontrole → preporuke i ostalo. Desktop je isti kao pre.
- Kartica na mapi prikazuje i prazno stanje „Nema parkinga u trenutnom skupu“ (npr. noću, kad nema očitavanja), pa korisnik na mapi vidi da nema preporuka.
- Skok „Sve preporuke“ na mobilnom koristi manji `scroll-mt` (header tamo nije sticky).
- Provereno u iframe-u od 390 px: nema horizontalnog scroll-a, mapa počinje odmah ispod headera, start → cilj → kartica #1 na dnu mape → „Sve preporuke“ skroluje do liste, a sklopiva legenda se otvara. Za test je simulacija pomerena na 18.11.2017 10:00 i ponovo pokrenuta.
