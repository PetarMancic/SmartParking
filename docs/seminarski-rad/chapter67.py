# -*- coding: utf-8 -*-
"""Poglavlja 6 (Zakljucak) i 7 (Literatura)."""

from docx.shared import Pt


def build_chapter6(doc, H):
    h1, p, bullets = H["h1"], H["p"], H["bullets"]

    h1(doc, "6. Zaključak")

    p(doc, "Doprinosi ovog rada mogu se sumirati u četiri tačke:")

    bullets(doc, [
        "Kompletan, funkcionalan end-to-end sistem — od sirovih senzorskih podataka do "
        "interaktivnog korisničkog interfejsa — implementiran i verifikovan nad stvarnim, "
        "javno dostupnim datasetom (Poglavlje 5).",
        "Kvantitativna potvrda da XGBoost regresija, korišćenjem isključivo vremenskih obeležja "
        "i identiteta parkinga, značajno nadmašuje i naivan baseline i klasičnu linearnu "
        "regresiju, uz rezultat uporediv sa random forest modelom (Poglavlje 5.3).",
        "Eksplicitno, transparentno arhitektonsko razdvajanje predikcije (učenje) od preporuke "
        "(odlučivanje), sa demonstracijom kako se preporuka menja u zavisnosti od vremena i od "
        "izbora pondera, bez ponovnog treniranja modela (Poglavlje 5.5, 5.7.3).",
        "Sistematska identifikacija i dokumentovanje ograničenja sistema — fiktivne koordinate, "
        "simulirani saobraćaj, neujednačena tačnost predikcije po parkingu, i ekstrapolacija van "
        "opsega merenja (Poglavlje 5.7.4, 5.7.5) — kao konkretna, izvodljiva osnova za dalji rad.",
    ])

    p(doc, (
        "U okviru ovog rada razvijen je proof-of-concept sistem koji povezuje ceo lanac obrade "
        "podataka o zauzetosti parkinga u pametnim gradovima: od sirovih senzorskih podataka, "
        "preko predikcije buduće dostupnosti mašinskim učenjem, do preporuke konkretne lokacije "
        "korisniku i njenog prikaza na interaktivnoj mapi. Sve pet planiranih faza — priprema "
        "podataka, model za predikciju, backend API, modul za preporuku i frontend — su u "
        "potpunosti implementirane i funkcionišu end-to-end."
    ))

    p(doc, (
        "Ključni kvantitativni rezultat rada jeste da XGBoost model, treniran isključivo na "
        "vremenskim obeležjima i identitetu parkinga, gotovo prepolovljuje grešku predikcije u "
        "odnosu na naivan baseline (RMSE sa 24,33 na 12,65; MAE sa 20,22 na 9,46), što potvrđuje "
        "da istorijski podaci o zauzetosti sadrže dovoljno pravilnosti da se buduća dostupnost "
        "parking mesta može pouzdano proceniti bez dodatnih spoljašnjih izvora podataka."
    ))

    p(doc, (
        "Ključni arhitekturni rezultat jeste uspešna demonstracija principa razdvajanja predikcije "
        "od preporuke: modul za rangiranje parkinga (`recommender.py`) ostaje potpuno "
        "nezavisan od modela mašinskog učenja, implementiran kao transparentna, objašnjiva "
        "formula sa lako izmenljivim ponderima. Ovakav dizajn omogućava da se ponašanje sistema "
        "prilagođava (npr. veći značaj blizini u odnosu na dostupnost) bez ikakvog ponovnog "
        "treniranja modela, a svaka preporuka može biti objašnjena korisniku kroz razložene "
        "komponente skora — što predstavlja bitnu prednost u odnosu na pristupe zasnovane na "
        "„crnoj kutiji”."
    ))

    p(doc, "Rad svesno ostavlja nekoliko ograničenja, dokumentovanih tokom celog teksta:")

    bullets(doc, [
        "Geografske koordinate parkinga su fiktivne — dataset ih ne sadrži, pa su ručno "
        "dodeljene isključivo radi demonstracije mape i računanja udaljenosti.",
        "Saobraćajna komponenta skora je pojednostavljena simulacija zasnovana na dobu dana i "
        "blizini destinaciji, a ne stvaran podatak o zagušenju.",
        "Dataset pokriva samo jednu nedelju (13–19.12.2016), 29 parkinga u jednom gradu, i samo "
        "prozor merenja od ~08:00 do ~16:30 — model je pouzdan isključivo unutar tog opsega.",
        "Sistem nema bazu podataka, autentifikaciju ni automatizovane testove — u skladu sa "
        "prirodom proof-of-concept rada, čiji je fokus na ispravnosti celog lanca, a ne na "
        "produkcionoj spremnosti.",
    ])

    p(doc, (
        "Ova ograničenja ujedno definišu prirodne pravce daljeg razvoja, planirane za master rad. "
        "Saobraćajna komponenta bi bila zamenjena stvarnim podacima (npr. iz javnog API-ja za "
        "saobraćaj ili iz senzorskih tokova), umesto trenutne konstante/simulacije. Predikcioni "
        "deo sistema bio bi proširen poređenjem XGBoost pristupa sa sekvencijalnim modelima "
        "dubokog učenja — LSTM i GRU mrežama — koje eksplicitno modeluju vremensku zavisnost "
        "između uzastopnih merenja, za razliku od trenutnog pristupa koji svaki trenutak tretira "
        "nezavisno. Konvolutivne neuronske mreže (CNN) namerno nisu razmatrane ni za predikciju "
        "ni za dalji rad, jer ne odgovaraju prirodi tabelarnih, ne-prostornih podataka kakvi su "
        "korišćeni u ovom radu. Dodatno, sistem bi mogao biti proširen na veći broj gradova i "
        "duži vremenski period, čime bi se omogućila robusnija evaluacija generalizacije modela."
    ))

    p(doc, (
        "Sa stanovišta praktične primenljivosti, sistem u trenutnom obliku nije spreman za "
        "produkcionu upotrebu, niti je to bio njegov cilj. Pre bilo kakvog stvarnog uvođenja bilo "
        "bi potrebno: zameniti fiktivne koordinate stvarnim GPS pozicijama parkinga (Poglavlje "
        "5.4); uvesti mehanizam za periodično ponovno treniranje modela na svežim podacima, jer "
        "je trenutni model statičan i vezan za jednu nedelju iz 2016. godine; i dodati osnovnu "
        "otpornost na greške na nivou API-ja (npr. ograničavanje broja zahteva, praćenje "
        "dostupnosti servisa), što u proof-of-concept fazi namerno nije prioritet. Ovi koraci ne "
        "menjaju osnovnu arhitekturu opisanu u ovom radu — oni je nadograđuju."
    ))

    p(doc, (
        "Zaključno, rad pokazuje da je već sa relativno jednostavnim, dobro odabranim alatima — "
        "gradijentnim pojačavanjem stabala za predikciju i ponderisanim rangiranjem za odlučivanje "
        "— moguće izgraditi funkcionalan, razumljiv i lako proširiv sistem za preporuku parking "
        "mesta, koji predstavlja solidnu osnovu za dalje istraživanje u okviru master rada."
    ))


def build_chapter7(doc, H):
    h1, p = H["h1"], H["p"]

    h1(doc, "7. Literatura")

    refs = [
        "D. C. Shoup, „Cruising for parking,“ Transport Policy, vol. 13, no. 6, pp. 479–486, 2006.",
        "F. M. Awan, Y. Saleem, R. Minerva, and N. Crespi, „A Comparative Analysis of "
        "Machine/Deep Learning Models for Parking Space Availability Prediction,“ Sensors, "
        "vol. 20, no. 1, p. 322, 2020.",
        "S. Dahiya et al., „Machine Learning-Based Prediction of Parking Space Availability "
        "in IoT-Enabled Smart Parking Management Systems,“ Journal of Advanced Transportation, "
        "vol. 2024, Article ID 8474973, 2024.",
        "D. H. Stolfi, E. Alba, and X. Yao, „Predicting Car Park Occupancy Rates in Smart "
        "Cities,“ in Smart Cities (Smart-CT 2017), Lecture Notes in Computer Science, vol. "
        "10268, Springer, 2017, pp. 107–117.",
        "UCI Machine Learning Repository, „Parking Birmingham Data Set,“ "
        "https://archive.ics.uci.edu/ml/datasets/Parking+Birmingham (pristupljeno avgust 2026).",
        "S. C. K. Tekouabou, E. A. Alaoui, W. Cherif, and H. Silkan, „Improving parking "
        "availability prediction in Smart Cities with IoT and ensemble-based model,“ Journal "
        "of King Saud University – Computer and Information Sciences, 2020.",
        "T. Chen and C. Guestrin, „XGBoost: A Scalable Tree Boosting System,“ in Proc. "
        "22nd ACM SIGKDD Int. Conf. on Knowledge Discovery and Data Mining (KDD ’16), 2016, "
        "pp. 785–794.",
        "F. Pedregosa et al., „Scikit-learn: Machine Learning in Python,“ Journal of "
        "Machine Learning Research, vol. 12, pp. 2825–2830, 2011.",
        "W. McKinney, „Data Structures for Statistical Computing in Python,“ in Proc. 9th "
        "Python in Science Conference (SciPy 2010), 2010, pp. 56–61.",
        "FastAPI — zvanična dokumentacija, https://fastapi.tiangolo.com/ (pristupljeno "
        "avgust 2026).",
        "Next.js — zvanična dokumentacija, https://nextjs.org/docs (pristupljeno avgust "
        "2026).",
        "Leaflet — zvanična dokumentacija, https://leafletjs.com/ (pristupljeno avgust "
        "2026).",
        "R. W. Sinnott, „Virtues of the Haversine,“ Sky and Telescope, vol. 68, no. 2, "
        "p. 159, 1984.",
    ]

    for i, ref in enumerate(refs, start=1):
        para = doc.add_paragraph()
        para.paragraph_format.space_after = Pt(6)
        run = para.add_run(f"[{i}] {ref}")
        run.font.size = Pt(11)
