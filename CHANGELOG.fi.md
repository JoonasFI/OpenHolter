# Muutosloki

🇬🇧 [In English](CHANGELOG.md)

OpenHolterilla on kaksi versionumeroa: **sovellusversio** (alla) ja **analyysiversio**, joka muuttuu, kun lyöntianalyysin tulokset voivat muuttua.
Tallenteet analysoidaan aina raakadatasta, joten uusi analyysiversio koskee myös vanhoja tallenteita.

Luvut ovat herkkyys / osuvuus. Heikentyneet tulokset kerrotaan yhtä tarkasti kuin parantuneet. Menetelmä ja tallennekohtaiset taulukot: [docs/VALIDATION.md](docs/VALIDATION.md).

## 0.5.0: tarkastelunäkymä

Analyysiversio on yhä 6: lisälyöntien määrät ja luokat eivät muutu.

- EKG-näkymään toisto: toista ja tauko (myös välilyönnillä), nopeudet 1×, 2×, 5×, 10× ja 30× sekä valinnainen pysähdys jokaiseen lisälyöntiin ja oiremerkintään.
- EKG-näkymän keskelle pystykatkoviiva, jonka yläpuolella näkyy tarkka kellonaika kymmenyssekunnin tarkkuudella.
- PDF-raportin EKG-liuskoihin sarjat (enintään 6, pisimmät ensin) ja parit (enintään 4, tasaisesti tallenteen ajalta).
- EKG-näkymän alareunaan asentopallo, jonka nuoli näyttää rintakehän suunnan jalkopäästä katsottuna ja kääntyy pehmeästi.
- Toistoon valinta "Hidasta havainnoissa": 1× sekunnin ennen ja jälkeen jokaisen havainnon, pehmeällä hidastuksella ja kiihdytyksellä.
- **Uusi tarkastelunäkymä** (`#/viewer`): koko tallenne yhdellä noin 15 tuuman näytöllä. Numeroidut löydökset suodattimineen ja
  siirtyminen numerolla, keskiviivan kohdan tiedot (syke, RR, lyönnin luokka, ennenaikaisuus), 3D-asento, koko yön asento-, syke- ja
  RR-kaistat (RR pisteinä tai tiheyskarttana), zoomausportaat koko yö → 10 min → 2 min → EKG, lyöntiluokat ja RR-välit EKG:ssä,
  mittain, vahvistus 5/10/20 mm/mV, analyysin yhteenvetorivi, lyöntimuodot (lyönnit ryhmiteltynä QRS-muodon mukaan),
  silmäystävällinen tila, automaattisesti piiloutuva yläpalkki ja pikanäppäimet.
- Analyysi tallentaa jokaisen lyönnin ajan omaan tiedostoonsa. Aiemmin analysoiduille tallenteille lyönnit lasketaan kerran,
  kun tallenne avataan tarkastelussa ensimmäisen kerran.
- Lyöntimuotojen rajat on säädetty tekijän omilla H10-tallenteilla (yksi yö ja neljä lyhyttä tallennetta). Ryhmittely on pelkkää esitystä
  eikä muuta analyysin lukuja tai luokkia.

## 0.4.2: lyöntitunnistin toipuu häiriöpiikeistä

- **Korjattu vakava virhe (0.4.0 ja 0.4.1):** vyön pukemisen häiriöpiikit saattoivat nostaa lyöntitunnistimen kynnyksen pysyvästi liian korkealle, jolloin tallenteen loppuosasta ei löytynyt yhtään lyöntiä. Virhe löytyi oikeasta H10-tallenteesta: 7 000 lyönnin tallenteesta löytyi nolla lyöntiä. Raakadataa virhe ei koskenut.
- Nyt taso arvioidaan uudelleen, jos lyöntiä ei ole tullut 3 sekuntiin ja viime sekunneissa näkyy QRS:n kaltainen huippu.
- Validointi: AFDB:n herkkyys 80,9 → 80,7 %. Muut julkaistut luvut pyöristyvät samoiksi. Analyysiversio on yhä 6, joten jos ajoit version 0.4.0 tai 0.4.1, poista tiedostot `sessions/*/cache/analysis-v6.json`, jotta tallenteet analysoidaan uudelleen.

## 0.4.1: pitkien taukojen analyysi nopeammaksi

- Korjattu: version 0.4.0 lyöntitunnistin hidastui jyrkästi pitkissä jaksoissa ilman lyöntejä, esimerkiksi kun vyö oli pois päältä. Taaksepäin haetaan nyt enintään 5 sekuntia.
- Tulokset eivät muuttuneet: kaikki MIT-BIH-, INCART-, SVDB- ja AFDB-validoinnin tulokset ovat samat kuin versiossa 0.4.0. Vain sovellusversio ja ajoajat eroavat, joten julkaistuja tulostiedostoja ei ajettu uudelleen. AFDB:n analyysiaika putosi 747 sekunnista 197 sekuntiin.

## 0.4.0: analyysiversio 6

Puhdas testi tarkoittaa dataa, joka avattiin vasta parametrien lukitsemisen jälkeen: SVDB (78 tallennetta) ja AFDB (23 tallennetta, 233 tuntia).

**Parani**

| | Aineisto | Versio 5 | Versio 6 |
|---|---|---:|---:|
| Lyöntien (QRS) herkkyys | MIT-BIH | 97,4 % | **99,9 %** |
| Lyöntien (QRS) herkkyys | SVDB, puhdas testi | 99,2 % | **99,9 %** |
| Tyypillinen yksittäinen SVES, herkkyys | SVDB, puhdas testi | 63,1 % | **90,8 %** |
| Eteisvärinä, osuvuus | AFDB, puhdas testi | 95,2 % | **99,1 %** |
| VES kokonaisuutena, herkkyys | MIT-BIH (nähty data, todennäköisesti optimistinen) | 68,0 % | **82,4 %** |

**Ei parantunut tai heikkeni**

| | Aineisto | Versio 5 | Versio 6 |
|---|---|---:|---:|
| VES kokonaisuutena | SVDB, puhdas testi | 61,9 / 82,2 % | 59,6 / 79,5 % |
| Lyöntien (QRS) osuvuus | SVDB, puhdas testi | 99,9 % | 99,4 % |
| Eteisvärinä, herkkyys | AFDB, puhdas testi | 83,3 % | 80,9 % |
| Tallenteita, joista löytyi vähintään puolet eteisvärinästä | AFDB, puhdas testi | 21 / 23 | 18 / 23 |
| Eteisvärinä, osuvuus | MIT-BIH, lyönneittäin | 87,1 % | 75,6 % |

SVES kokonaisuutena parani puhtaassa testissä vain vähän (49,4 / 76,6 → 53,6 / 75,1 %), joten VES- ja SVES-kokonaismäärät ovat edelleen suuntaa antavia.

**Muuttui**

- Uusi QRS-tunnistin: kynnys seuraa viimeisiä lyöntejä, pitkät välit tarkistetaan takaisinhaulla ja T-aallot hylätään.
- Eteisvärinäjakso vaatii epäsäännöllisen rytmin lisäksi sen, ettei toistuvaa P-aaltoa näy.
- Validointiin SVDB:n ja AFDB:n lukijat ja komentorivivalinnat.

**Hyvä tietää**

- Tunnistuksen raja-arvot on testattu vain Holter-tallenteilla, ei vielä oikealla H10-datalla.
- SVDB ja AFDB on nyt nähty, joten seuraava kierros tarvitsee uuden puhtaan testiaineiston.
- Hakemiston `docs/validation/` tulostiedostot ajettiin juuri ennen tämän versionumeron asettamista, joten niissä lukee `openholter_version` 0.3.0. Ne tunnistaa merkinnästä `analysis_version` 6.

## 0.3.0: ensimmäinen julkinen versio, analyysiversio 5

- Tallennus Polar H10:ltä: EKG 130 Hz, kiihtyvyys 50 Hz ja RR-välit, automaattinen käynnistys ja pysäytys.
- Lyöntianalyysi: VES ja SVES, parit, sarjat ja bigeminia, epäsäännöllisen rytmin jaksot, asento ja HRV.
- Selainkäyttöliittymä, trendit, oiremerkinnät, asennon kalibrointi, roskakori ja asetukset.
- PDF-raportti, jossa on koko EKG.
- Suomi ja englanti käyttöliittymässä ja PDF:ssä.
- Avoin validointi MIT-BIH- ja INCART-aineistoilla ANSI/AAMI EC57 -standardin mukaisesti.
