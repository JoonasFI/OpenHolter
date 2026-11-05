# Osallistuminen OpenHolteriin

🇬🇧 [In English](CONTRIBUTING.md)

Kiitos, että haluat auttaa! Virheilmoitukset, parannusehdotukset ja koodi ovat tervetulleita.

## Käytännöt

- Avaa ensin issue isommista muutoksista, niin suunta sovitaan ennen kuin teet paljon työtä.
- Aja testit ennen pull requestia: `python -m pytest tests` (tai ilman pytestiä: `PYTHONPATH=. python tests/test_pipeline.py`).
- Koodin on toimittava Python 3.9:llä (macOS:n Command Line Tools -Python).
- Ei pilvipalveluja, ulkoista analytiikkaa eikä telemetriaa: data pysyy käyttäjän koneella.
- Analyysiin vaikuttavat muutokset: aja myös validointi molemmilla aineistoilla
  (`python -m openholter validate --mitdb <kansio> --incartdb <kansio> --svdb <kansio> --afdb <kansio>`, ks. `docs/VALIDATION.md`)
  ja liitä tulokset pull requestiin, myös jos ne heikkenevät. Säädä parametreja vain MIT-BIH:n DS1-puoliskolla.
  Muut aineistot ovat testidataa, ja niiden tulokset raportoidaan ilman uudelleensäätöä.

## Contributor License Agreement (CLA)

OpenHolter julkaistaan AGPL-3.0-lisenssillä, ja sille on tarjolla myös kaupallinen lisenssi (ks. README).
Jotta tämä kaksoislisensointi on mahdollista, jokainen osallistuja hyväksyy CLA:n ennen kuin koodi yhdistetään.
Hyväksyntä tehdään pull requestissa (CLA Assistant -botti pyytää sitä automaattisesti).

CLA ei siirrä tekijänoikeuttasi: omistat edelleen oman koodisi ja voit käyttää sitä miten haluat.

**Mikä CLA.** OpenHolter käyttää valmista, laajasti käytettyä
[Harmony Individual Contributor License Agreement -sopimusta, versio 1.0](https://harmonyagreements.org/docs/ha-combined-v1)
(*lisenssi*versio, ei tekijänoikeuden siirtoversio) seuraavin valinnoin:

| Pohjan kohta | OpenHolter |
|---|---|
| Versio | yksityishenkilö, tekijänoikeuden **lisenssi** (tekijänoikeus säilyy sinulla) |
| Projekti, "We/Us" | OpenHolter; Joonas Wilska (yksityinen elinkeinonharjoittaja, Suomi) |
| Ulospäin annettava lisenssi, kohta 2.3 | **Option Five**: mikä tahansa lisenssi, myös kaupallinen, kunhan kontribuutio on aina saatavilla myös projektin lisenssillä (AGPL-3.0-or-later) |
| Media-aineiston lisenssit | CC BY 4.0 |
| Sovellettava laki, kohta 6.1 | Suomi |
| Hyväksyntätapa | sähköinen hyväksyntä CLA Assistantilla GitHubissa |
| Jos et omista koko tekijänoikeutta | kerro siitä pull requestissa; työnantaja tai oikeuksien omistaja allekirjoittaa Harmonyn **Entity**-CLA:n |

Pohjan kohta 6.3 sallii oikeuksien ja velvoitteiden siirron kolmannelle osapuolelle, joka sitoutuu kirjallisesti
noudattamaan sopimusta. Näin sopimus voi siirtyä yhtiölle, jos projektia myöhemmin pyöritetään sellaisen kautta.
Oikeutesi sopimuksen nojalla pysyvät samoina.

*Täytetty sopimusteksti (CLA.md) ja CLA Assistantin käyttöönotto lisätään ennen ensimmäisen ulkopuolisen
kontribuution yhdistämistä. Harmony-pohjat on lisensoitu CC BY 3.0 -lisenssillä.*
