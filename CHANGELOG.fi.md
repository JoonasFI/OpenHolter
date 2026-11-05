# Muutosloki

🇬🇧 [In English](CHANGELOG.md)

OpenHolterilla on kaksi versionumeroa: **sovellusversio** (alla) ja **analyysiversio**, joka muuttuu, kun lyöntianalyysin tulokset voivat muuttua.
Tallenteet analysoidaan aina raakadatasta, joten uusi analyysiversio koskee myös vanhoja tallenteita.

Luvut ovat herkkyys / osuvuus. Heikentyneet tulokset kerrotaan yhtä tarkasti kuin parantuneet. Menetelmä ja tallennekohtaiset taulukot: [docs/VALIDATION.md](docs/VALIDATION.md).

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
