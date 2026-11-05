# Lyöntianalyysin validointi: MIT-BIH ja INCART

🇬🇧 [In English](VALIDATION.en.md)

Tämä sivu kertoo, miten OpenHolterin lyönti- ja lisälyöntianalyysi on testattu, millä datalla ja millä tuloksella.
Myös heikot kohdat on kerrottu, ja myös ne kohdat, joissa uusi versio on vanhaa huonompi. Testin voi ajaa itse
uudelleen, ja tuloksen pitäisi olla bitilleen sama.

**Uusin versio:** analyysiversio 6 (`openholter/beats.py`), testattu 5.11.2026, ks. [Analyysiversio 6](#analyysiversio-6-uusin). Analyysiversio 5 testattiin 3.11.2026.
Edellisen version (analyysiversio 4) tulokset ovat [alempana ennallaan](#analyysiversio-4-aiempi-tulos-ennallaan).

**Raakatulokset ja tallennekohtaiset taulukot** (`docs/validation/`):

| Aineisto | v5 | v4 |
|---|---|---|
| MIT-BIH (myös DS1/DS2 erikseen) | [`mitdb-v5-results.json`](validation/mitdb-v5-results.json) · [`mitdb-v5-records.md`](validation/mitdb-v5-records.md) | [`mitdb-v4-results.json`](validation/mitdb-v4-results.json) · [`mitdb-v4-records.md`](validation/mitdb-v4-records.md) |
| INCART | [`incartdb-v5-results.json`](validation/incartdb-v5-results.json) · [`incartdb-v5-records.md`](validation/incartdb-v5-records.md) | [`incartdb-v4-results.json`](validation/incartdb-v4-results.json) · [`incartdb-v4-records.md`](validation/incartdb-v4-records.md) |

> OpenHolter ei ole lääkinnällinen laite. Validointi kertoo algoritmin suorituskyvystä tunnetussa
> tutkimusaineistossa, ei siitä, sopiiko se diagnoosiin. Se ei sovi.

## Analyysiversio 6 (uusin)

Versio 6 tehtiin, koska v5:n SVES ei yleistynyt ja QRS-tunnistus rajoitti kaikkea muuta. Alla olevat v5:n ja v4:n
osiot ovat ennallaan.

### Tulokset

Parametrit säädettiin vain DS1:llä ja lukittiin. Sen jälkeen kaikki aineistot ajettiin kerran, eikä mitään muutettu.
**Puhdas testi ovat vain SVDB ja AFDB**, koska ne ladattiin tätä kierrosta varten ja avattiin vasta lukituksen jälkeen. DS2:n ja
INCARTin tuloksia nähtiin v5:ssä, ja niistä selvinneet syyt ohjasivat v6:n suunnittelua, vaikka numeroita ei
säädetty niillä. Niiden parannus on siksi todennäköisesti optimistinen. Luvut ovat Se / +P prosentteina.

| Aineisto | QRS v5 → v6 | VES v5 → v6 | SVES v5 → v6 |
|---|---:|---:|---:|
| **SVDB, 78 tallennetta (puhdas testi)** | 99,2 / 99,9 → **99,9 / 99,4** | 61,9 / 82,2 → **59,6 / 79,5** | 49,4 / 76,6 → **53,6 / 75,1** |
| DS2 (nähty) | 97,9 / 99,9 → 99,9 / 99,7 | 70,6 / 93,1 → 82,6 / 91,8 | 10,9 / 43,4 → 12,7 / 48,2 |
| INCART (nähty) | 95,3 / 99,6 → 99,8 / 99,0 | 59,3 / 89,7 → 78,1 / 89,9 | 70,1 / 57,1 → 87,6 / 66,3 |
| DS1 (säätödata, optimistinen) | 97,3 / 99,9 → 99,8 / 99,8 | 65,8 / 92,0 → 82,2 / 90,0 | 70,4 / 83,6 → 74,1 / 82,1 |
| MIT-BIH kaikki | 97,4 / 99,9 → 99,9 / 99,7 | 68,0 / 92,5 → 82,4 / 90,8 | 30,4 / 68,3 → 32,9 / 69,4 |

Yksittäiset lisälyönnit (molemmat naapurit normaaleja), herkkyys; löydetyksi lasketaan mikä tahansa lisälyöntimerkintä:

| Aineisto | VES kaikki yksittäiset | VES tyypillinen | SVES kaikki yksittäiset | SVES tyypillinen |
|---|---:|---:|---:|---:|
| SVDB (puhdas testi) | 74,2 → 74,0 | 89,4 → 88,5 | 52,7 → **71,5** | 63,1 → **90,8** |
| MIT-BIH kaikki | 76,1 → 90,9 | 79,4 → 96,0 | 61,6 → 73,3 | 72,8 → 90,0 |
| INCART (nähty) | 65,7 → 85,7 | 73,7 → 92,3 | 77,1 → 95,7 | 79,5 → 98,0 |

Eteisvärinä ja epäsäännöllinen rytmi:

| Aineisto ja mittari | v5 | v6 |
|---|---:|---:|
| **AFDB, 23 tallennetta, 233 h, sekunneittain (puhdas testi): Se / +P** | 83,3 / 95,2 | **80,9 / 99,1** |
| AFDB: ei-eteisvärinäajasta oikein luokiteltu (spesifisyys) | 97,1 | 99,5 |
| AFDB: tallenteita, joista löytyi vähintään puolet eteisvärinästä | 21 / 23 | 18 / 23 |
| MIT-BIH kaikki, lyönneittäin: Se / +P | 82,4 / 87,1 | 93,4 / 75,6 |
| INCART, lyönneittäin: Se / +P (2 eteisvärinätallennetta) | 0 / 0 | 27,6 / 44,7 |
| SVDB: tallenteita, joissa ilmoitettiin jakso (ei rytmimerkintöjä, joten oikeellisuutta ei voi arvioida) | 25 | 13 |

Sarjat Se / +P: SVDB 26,6 / 45,3 → 28,0 / 41,5; DS2 2,4 / 57,1 → 5,3 / 39,1; INCART 24,1 / 33,6 → 57,2 / 51,3.
Tallennekohtaiset taulukot ovat tiedostoissa
`docs/validation/{mitdb,incartdb,svdb,afdb}-v6-*` ja `{svdb,afdb}-v5-*` (v5 on ajettu uusilla aineistoilla vertailuksi).

### Tulkinta

- **Lyöntien tunnistus on nyt hyvällä tasolla** kaikissa aineistoissa (Se 99,8–99,9 %). Vääriä tunnistuksia on hieman
  enemmän kuin ennen, varsinkin INCARTissa (+P 99,0 %).
- **Tyypilliset yksittäiset SVES-lyönnit parantuivat puhtaassa testissä selvästi** (63 → 91 %), kun taas koko SVES-luku
  parani vain vähän. Tavalliselle käyttäjälle tämä on tärkein parannus.
- **Eteisvärinän väärät hälytykset vähenivät puhtaassa testissä** (+P 95 → 99 %, spesifisyys 97,1 → 99,5 %). Hintana
  herkkyys laski hieman, ja yli puolet eteisvärinästä jää löytymättä viidessä tallenteessa 23:sta.
- **VES ei parantunut puhtaassa testissä**, vaan heikkeni hieman (61,9 / 82,2 → 59,6 / 79,5). Muissa aineistoissa parannus oli suuri
  (MIT-BIH 68 → 82 %). SVDB:n heikompi tulos näyttää, että VES-parannus ei yleisty kaikkeen dataan.

SVES- ja VES-määriä pitää edelleen pitää suuntaa antavina. Lukuihin ei pidä perustaa hoitopäätöksiä.

### Mitä muutettiin

1. **QRS-tunnistin.** v5:n kynnys oli kiinteä 8 sekunnin lohkossa, joten yksi korkea lyönti nosti sen niin, että viereiset
   lyönnit ja leveät VES-lyönnit jäivät alle. v6:n kynnys seuraa viimeisiä lyöntejä (kynnys = kohinataso + 0,4 ×
   (signaalitaso − kohinataso); signaalitaso on 8 viime huipun mediaani). Lisäksi on Pan–Tompkins-tyyppinen
   takaisinhaku (jos väli kasvaa yli 1,5-kertaiseksi, korkein hylätty huippu tarkistetaan puolikkaalla kynnyksellä) ja
   T-aallon hylkäys (420 ms:n sisällä alle puolet edellisen huipusta).
2. **Eteisvärinä vaatii P-aallon puuttumisen.** Pelkkä epäsäännöllisyys sekoitti tiheät eteislisälyönnit eteisvärinään.
   v6 keskiarvoistaa lähilyöntien −240…−60 ms:n jaksot kahdessa puoliskossa. Toistuva P-aalto saa puoliskot
   samanlaisiksi. P-aalto katsotaan näkyväksi, kun niiden korrelaatio on vähintään 0,75 ja korkeus vähintään 5 % QRS:stä.
   Eteisvärinäjakso syntyy vain, jos P-aaltoa ei näy ja epäsäännöllisyys ylittää 0,05 (v5:ssä pelkkä raja 0,10).
3. **Säätö ja testaus.** Säädettiin DS1:llä. Kokeiltiin noin 40 muunnelmaa. Mallin laajempi ikkuna kokeiltiin mutta ei otettu käyttöön.
   Lisäksi lisättiin SVDB:n ja AFDB:n lukijat ja simulaattoritesti tiheille eteislisälyönneille.

Analyysin tuloskentät ovat samat kuin v5:ssä, joten käyttöliittymä ei vaadi muutoksia.

### Tunnetut heikkoudet

- **Yksi virhe voi hylätä koko sarjan.** Tallenteessa 865 (SVDB) noin 1 000 lyönnin sarja jäi v6:ssa kokonaan
  merkitsemättä, kun v5 löysi sen: SVES-löydöt putosivat 1 740:stä 677:ään. Tämä yksi tallenne laski SVDB:n koko
  SVES-herkkyyttä noin 10,6 prosenttiyksikköä. Sääntö hyväksyy jonon kokonaisuutena. Tarkkaa laukaisijaa ei ole selvitetty.
- **Vääriä eteisvärinäjaksoja MIT-BIH:ssä:** +P laski 87:stä 76 %:iin, esimerkiksi tallenteessa 200 on 819 lyöntiä
  jaksoissa ilman eteisvärinää. Tallenteessa 222 SVES-väärät lisääntyivät (9 → 71).
- **INCARTin eteisvärinä:** tallenteista I49 ja I50 löytyy vain osa (Se 28 %).
- **Tallenteet, joissa eteislyönti on vallitseva rytmi** (MIT 232, SVDB 822), jäävät lähes kokonaan löytymättä.
- **Vääriä VES-merkintöjä lisää** erityisesti kohinaisissa tallenteissa (INCART I54 156 → 267, I01 273 → 337).
- **Eteisvärinän tunnistus on testattu vain Holter-kytkennöillä.** P-aallon
  korkeus H10:n rintakytkennässä voi olla erilainen, joten raja 5 % pitää tarkistaa oikealla H10-datalla.
- **Koskemattomia aineistoja ei enää ole.** Myös SVDB ja AFDB on nyt nähty. Seuraava kierros tarvitsee uuden testiaineiston.

## Yhteenveto: v5 verrattuna v4:ään

Analyysiversiota 5 säädettiin **vain** MIT-BIH:n puoliskolla DS1. DS2 ja INCART ajettiin vasta, kun kaikki
parametrit oli lukittu, eikä mitään muutettu niiden tulosten nähtyä. DS2- ja INCART-sarakkeet ovat siis
oikea testitulos, DS1-sarake ei ole.

| Mittari | v4 MIT-BIH | v5 DS1 *(säätödata)* | v5 DS2 *(testi)* | v5 MIT-BIH kaikki | v4 INCART | v5 INCART *(testi)* |
|---|---:|---:|---:|---:|---:|---:|
| QRS Se / +P | 97,4 / 99,9 | 97,3 / 99,9 | 97,9 / 99,9 | 97,4 / 99,9 | 95,3 / 99,6 | 95,3 / 99,6 |
| VES Se | 49,0 | 65,8 | **70,6** | **68,0** | 49,2 | **59,3** |
| VES +P | 93,1 | 92,0 | 93,1 | 92,5 | 95,2 | 89,7 |
| SVES Se | 20,4 | 70,4 | **10,9** | 30,4 | 83,3 | **70,1** |
| SVES +P | 40,0 | 83,6 | **43,4** | 68,3 | 66,5 | **57,1** |
| Kaikki lisälyönnit Se / +P | 43,1 / 82,9 | 68,5 / 93,7 | 51,2 / 90,1 | 59,6 / 92,1 | 54,8 / 94,0 | 62,6 / 88,0 |
| Epäsäännöllinen rytmi (eteisvärinä), lyöntejä Se / +P | – | 99,5 / 87,0 | 75,9 / 87,2 | 82,4 / 87,1 | – | 0 / 0 * |
| Sarjat (≥ 3 peräkkäistä) Se / +P | – | 44,3 / 65,9 | 2,4 / 57,1 | 13,4 / 64,6 | – | 24,1 / 33,6 |

Kaikki luvut prosentteja. Se = herkkyys (kuinka suuri osa oikeista löytyi), +P = osuvuus (kuinka suuri osa
merkinnöistä oli oikeita). v4:n INCART-tulos on ajettu nyt jälkikäteen v4:n koodilla samalla validointikoodilla
vertailua varten. \* INCARTin kaksi eteisvärinätallennetta jäivät kokonaan tunnistamatta, ja 12 muussa
tallenteessa ohjelma ilmoitti epäsäännöllisen rytmin jakson, jota viitteessä ei ole (ks. alla).

**Tulkinta lyhyesti.**

- **VES (kammiolisälyönnit) paranivat kaikissa aineistoissa.** Herkkyys nousi MIT-BIH:ssä 49 %:sta 68 %:iin ja
  INCARTissa 49 %:sta 59 %:iin. Syy on lähinnä se, että lyönnin muoto tarkistetaan nyt kaikista lyönneistä, ei vain
  ennenaikaisista. Hinta on osuvuudessa: INCARTissa osuvuus laski 95 %:sta 90 %:iin, MIT-BIH:ssä 93,1 %:sta 92,5 %:iin.
- **SVES (eteisperäiset lisälyönnit): tulos on ristiriitainen, eikä v5 ole selvästi parempi.**
  Säätödatassa (DS1) parannus oli suuri (Se 29 → 70 %, +P 46 → 84 %), mutta **se ei siirtynyt testidataan.**
  DS2:ssa osuvuus parani (36 → 43 %), mutta herkkyys heikkeni (16 → 11 %). INCARTissa sekä herkkyys
  (83 → 70 %) että osuvuus (66 → 57 %) heikkenivät. Tämä on tyypillinen ylisovittamisen merkki: DS1:llä
  hyvältä näyttänyt sääntö ei yleisty. Syyt on eritelty [alempana](#missä-v5-on-huonompi-kuin-v4).
- **Eteisvärinän tunnistus** toimii MIT-BIH:ssä kohtuullisesti (82 % eteisvärinälyönneistä tunnistettiin,
  87 % ilmoitetusta oli oikeaa eteisvärinää tai -lepatusta), mutta INCARTissa se epäonnistui täysin.
- **Sarjojen** (≥ 3 peräkkäistä lisälyöntiä) raportointi on uusi ja vielä heikko: suurin osa viitteen sarjoista
  jää löytymättä.

SVES-lukuihin ei edelleenkään pidä luottaa. VES-luvut ovat suuntaa antavia.

## Mitä versiossa 5 muutettiin ja miksi

v4:n validointi osoitti viisi pääongelmaa (ks. [v4:n tulokset](#analyysiversio-4-aiempi-tulos-ennallaan)).
Jokaiseen tehtiin muutos. QRS-tunnistus ja häiriöiden hylkäys ovat ennallaan.

1. **(a) Epäsäännöllinen rytmi ja eteisvärinä.** v4:ssä suurin osa vääristä SVES-merkinnöistä tuli
   eteisvärinätallenteista, koska epäsäännöllisessä rytmissä normaalitkin lyönnit näyttävät ennenaikaisilta.
   v5 laskee jokaiselle lyönnille rytmin epäsäännöllisyyden 31 sykevälin ikkunasta: peräkkäisten välien
   erotuksen mediaani suhteessa paikalliseen mediaaniväliin. Mukaan otetaan vain normaalimuotoisten lyöntien
   välit, ja erotus lasketaan viiveillä 1, 2 ja 3 ja näistä pienin. Näin bigeminia (joka toinen lyönti lisälyönti)
   ja trigeminia eivät näytä epäsäännölliseltä, koska niissä kuvio toistuu. Kun arvo on yli 0,10 vähintään
   30 sekunnin ajan, jakso raportoidaan omana löydöksenään (`af_episodes`, "epäsäännöllinen rytmi, sopii
   eteisvärinään"). Jaksoa levennetään 10 s kummastakin päästä, koska liukuva mediaani ylittää rajan vasta,
   kun puolet ikkunasta on epäsäännöllistä. **Jakson aikana SVES-merkintöjä ei tehdä.** VES-merkinnät tehdään
   edelleen lyönnin muodon perusteella.
2. **(b) Ennenaikaisuuden raja seuraa paikallista vaihtelua.** v4 vaati aina 20 % lyhyemmän välin. v5 laskee
   sykevälin ja viitearvon suhteen paikallisen hajonnan (mediaanipoikkeama, MAD, 31 lyöntiä; VES-lyönnit ja niitä
   seuraavat lyönnit jätetään pois, etteivät ne kasvata hajontaa). Vaadittu ennenaikaisuus on 3 × hajonta,
   kuitenkin vähintään 12 % ja enintään 20 %. Tasaisessa rytmissä 12 % ennenaikainen lyönti riittää.
   Vaihtelevassa rytmissä vaaditaan 20 % kuten ennenkin. Lisäksi SVES:n välin on lyhennyttävä
   äkillisesti: alle 90 % edeltävästä välistä, jottei sinusrytmin vähittäinen kiihtyminen näytä lisälyönniltä.
3. **(c) SVES ei vaadi täyttä taukoa.** Eteisperäinen lisälyönti yleensä "nollaa" sinussolmukkeen, joten sitä
   seuraava väli on vain normaalin mittainen, ei pidempi. v4 vaati yli 105 %:n tauon. v5 vaatii, että
   seuraava väli on vähintään yhtä pitkä kuin ennenaikainen väli ja vähintään 85 % viitearvosta. Jälkimmäinen
   ehto torjuu tilanteen, jossa ylimääräinen tunnistus (esim. T-aalto) jakaa yhden välin kahtia.
   Ennenaikaiselta VES:ltä vaaditaan seuraavaksi väliksi vähintään 95 % viitearvosta.
4. **(d) Sarjat.** Peräkkäiset ennenaikaiset lyönnit käsitellään yhtenä jonona. Viitearvo lukitaan jonon alussa,
   ja se on suurempi kahdesta: keskitetty mediaani tai pelkästään edeltävien lyöntien mediaani. Muuten pitkä
   takykardia vetäisi oman viitearvonsa alas eikä näyttäisi ennenaikaiselta. Vähintään 3 lyönnin jono
   raportoidaan sarjana (`runs`), jos sen syke on yli 100/min (SVT/VT:n tavallinen määritelmä). Hitaampi
   "sarja" on todennäköisemmin perusrytmin muutos, joten siitä merkitään vain lyönnit, jotka ovat muotonsa
   perusteella selvästi VES-lyöntejä. Jos jonossa on sekä VES- että SVES-muotoisia lyöntejä, normaalimuotoiset
   jätetään pois. Poikkeus on jono, jossa SVES-muotoisia on yli kaksinkertainen määrä VES-muotoisiin
   verrattuna: silloin lievästi poikkeava lyönti tulkitaan aberroituneeksi SVES:ksi.
5. **(e) VES pelkän muodon perusteella.** v4 tarkisti lyönnin muodon vain ennenaikaisista lyönneistä, joten
   myöhään tuleva VES (tavallinen hitaalla sykkeellä) jäi löytymättä. v5 vertaa jokaista lyöntiä lähistön
   normaalilyöntien mediaanimalliin (±40 lyöntiä, kaksi kierrosta). Lyönti on VES myös ilman ennenaikaisuutta,
   jos sen korrelaatio malliin on alle 0,70 parhaallakin ±40 ms:n siirrolla ja QRS on vähintään 40 ms leveämpi
   tai 1,5 × suurempi. Lyönti on VES myös, jos korrelaatio R-huipun kohdalla on negatiivinen, parhaalla
   siirrolla alle 0,80 ja QRS on leveämpi. Lisäksi molempien naapurilyöntien on sovittava malliin. Siirto
   tarvitaan, koska tunnistin asettaa lyönnin kohdan suurimpaan heilahdukseen, joka RS-muotoisessa
   kompleksissa voi olla joko R- tai S-aalto. Ilman siirtoa normaalit lyönnit näyttivät tallenteessa 215
   "erimuotoisilta" (noin 100 väärää VES-merkintää kehitysvaiheessa). Naapuriehto torjuu tilanteet, joissa malli tai signaali on
   paikallisesti pielessä.

Uudet kentät analyysin tuloksessa (`analysis-v5.json`, `ectopy`): `af_episodes`, `af_seconds`, `runs` ja
`ves_morphology_only`. Lisäksi jokaisella lisälyönnillä (`details`) on kentät `premature`, `run` ja `in_af`.

## Ylisovittamisen välttäminen: miten säädettiin

- **Jako.** MIT-BIH jaettiin de Chazalin ym. (2004) vakiintuneeseen opetus- ja testipuoliskoon. Tahdistetut
  tallenteet 102, 104, 107 ja 217 eivät kuulu kumpaankaan.
  DS1 (säätö): 101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215,
  220, 223, 230. DS2 (testi): 100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219,
  221, 222, 228, 231, 232, 233, 234. INCART on kokonaan testidataa.
- **Mitä DS1:llä tehtiin.** Kaikki säännöt ja raja-arvot kehitettiin katsomalla DS1:n virheitä
  tallennekohtaisesti (eniten 106, 119, 124, 201, 203, 208, 209, 215 ja 223). Noin 40 parametrimuunnelmaa kokeiltiin
  DS1:llä yksi kerrallaan tai pieninä yhdistelminä. Tämä on säätämistä, ja siksi DS1:n tulos on optimistinen.
- **Lukitus.** Parametrit lukittiin (`openholter/beats.py`, kohta "v5 parameters"). Lukituksen jälkeen tehtiin
  yksi muutos ennen kuin testidataa ajettiin: eteisvärinäjakson levennys 10 s. Sen aiheutti simulaattoritesti,
  ja se tarkistettiin vain DS1:llä. Tämän jälkeen DS2, koko MIT-BIH ja INCART ajettiin kerran, eikä koodia
  muutettu tulosten perusteella. Ainoa myöhempi koodimuutos oli kehitysaikaisen diagnostiikkakoukun
  poistaminen, ja tulokset tarkistettiin bitilleen samoiksi.
- **Heikkous jaossa.** DS1:ssä on vain kaksi eteisvärinätallennetta (201, 203). Eteisvärinän tunnistuksen raja
  saatiin siis hyvin pienestä aineistosta, mikä näkyy testituloksessa.

## Tulokset yksityiskohtaisesti (v5)

### MIT-BIH

| | DS1 *(säätö)* | DS2 *(testi)* | Kaikki 44 |
|---|---:|---:|---:|
| VES viitelyöntejä | 3 109 | 2 587 | 5 696 |
| VES Se / +P | 65,8 / 92,0 | 70,6 / 93,1 | 68,0 / 92,5 |
| SVES viitelyöntejä | 760 | 1 556 | 2 316 |
| SVES Se / +P | 70,4 / 83,6 | 10,9 / 43,4 | 30,4 / 68,3 |
| Ilman eteisvärinätallenteita: VES Se / +P | 64,7 / 95,1 | 72,2 / 95,5 | 68,0 / 95,3 |
| Ilman eteisvärinätallenteita: SVES Se / +P | 83,8 / 84,3 | 7,7 / 42,7 | 33,1 / 73,3 |
| VES, tyypillinen yksittäinen Se | 80,7 | 78,4 | 79,4 (v4: 76,0) |
| SVES, tyypillinen yksittäinen Se | 76,9 | 66,7 | 72,8 (v4: **81,8**) |
| VES, kaikki yksittäiset Se | 76,8 | 75,6 | 76,1 (v4: 56,5) |
| SVES, kaikki yksittäiset Se | 70,3 | 50,9 | 61,6 (v4: 55,7) |

*Tyypillinen yksittäinen* tarkoittaa samaa kuin v4:ssä: molemmat naapurit ovat normaaleja lyöntejä, edeltävä väli
on alle 80 % ja seuraava yli 105 % paikallisesta mediaanista. Alaryhmissä löydetyksi lasketaan mikä tahansa
lisälyöntimerkintä.

**DS2:n SVES-luku on tallenteen 232 hallitsema.** Siinä on 1 121 DS2:n 1 556 SVES-lyönnistä. Tallenteessa on
sairas sinus -oireyhtymä, ja eteisperäiset lyönnit ovat lähes koko ajan vallitseva rytmi. Ne eivät ole ennenaikaisia
suhteessa mihinkään, joten kumpikaan versio ei löydä niitä (v4 39, v5 33). Ilman tallennetta 232 DS2:n SVES on:
**v4 Se 49,7 % / +P 32,3 %, v5 Se 31,5 % / +P 38,2 %.** Myös näin laskettuna v5:n herkkyys on selvästi huonompi.

Ristiintaulukko, kaikki 44 ei-tahdistettua MIT-BIH-tallennetta (v5; suluissa v4):

| Viite ↓ / OpenHolter → | VES | SVES | ei merkintää |
|---|---:|---:|---:|
| N (normaali) | 188 (121) | 150 (538) | 71 526 |
| S (SVES) | 44 (39) | 705 (472) | 1 567 |
| V (VES) | 3 874 (2 789) | 149 (156) | 1 673 |
| F (fuusio) | 28 (3) | 8 (3) | 576 |
| Q | 3 (2) | 1 (0) | 11 |
| ei viitelyöntiä | 52 (42) | 19 (10) | |

Pelkän muodon perusteella (ilman ennenaikaisuutta) löytyi MIT-BIH:ssä 465 VES-merkintää. Niistä 429 oli oikeita
VES-lyöntejä, 24 normaaleja, 5 fuusiolyöntejä ja 7 muita.

### INCART

[St Petersburg INCART 12-lead Arrhythmia Database](https://physionet.org/content/incartdb/1.0.0/): 75 puolen tunnin
12-kytkentäistä tallennetta 32 potilaalta, 257 Hz. Käytettiin kytkentää II, joka näytteistettiin 257 → 130 Hz.

| | v4 | v5 |
|---|---:|---:|
| QRS Se / +P (141 828 lyöntiä) | 95,3 / 99,6 | 95,3 / 99,6 |
| VES Se / +P (16 317 viitelyöntiä) | 49,2 / 95,2 | 59,3 / 89,7 |
| SVES Se / +P (1 599 viitelyöntiä) | 83,3 / 66,5 | 70,1 / 57,1 |
| Kaikki lisälyönnit Se / +P | 54,8 / 94,0 | 62,6 / 88,0 |
| VES, tyypillinen yksittäinen Se | 71,3 | 73,7 |
| SVES, tyypillinen yksittäinen Se | 97,4 | 79,5 |
| Sarjat Se / +P (145 viitesarjaa, joista 134 VES-sarjoja) | – | 24,1 / 33,6 |

INCARTin SVES-lyönneistä 957 (60 %) on kahdessa saman potilaan tallenteessa, I33 ja I34. Niissä noin kolmannes
lyönneistä on eteislisälyöntejä. Siksi INCARTin SVES-luku kertoo pitkälti näiden kahden tallenteen tuloksen.

### Epäsäännöllinen rytmi (eteisvärinä)

Mittarina on viitelyönnit, jotka osuvat kardiologien eteisvärinä- tai eteislepatusjaksoon (rytmimerkinnät
`(AFIB` ja `(AFL`), verrattuna lyönteihin, jotka osuvat ohjelman ilmoittamaan jaksoon.

| | Viitteen eteisvärinätallenteita | Tunnistettu lyönneistä (Se) | Ilmoitetusta oikeaa (+P) | Jaksoja tallenteissa, joissa viitteessä ei eteisvärinää |
|---|---:|---:|---:|---|
| MIT-BIH DS1 | 2 (201, 203) | 99,5 % | 87,0 % | 1 tallenne (207: yksi 66 s jakso, johon ei osu yhtään viitelyöntiä)* |
| MIT-BIH DS2 | 5 (202, 210, 219, 221, 222) | 75,9 % | 87,2 % | ei yhtään |
| INCART | 2 (I49, I50) | **0 %** | **0 %** | 12 tallennetta, yhteensä 38 min |

\* Todennäköisesti tallenteen kammiolepatusjakson kohdalla. Tallennekohtaiset luvut ovat taulukossa
[`mitdb-v5-records.md`](validation/mitdb-v5-records.md).

- MIT-BIH:ssä osa "vääristä" eteisvärinälyönneistä on muuta epäsäännöllistä eteisrytmiä, esimerkiksi
  tallenteiden 201 ja 222 eteistakykardiaa ja nodaalirytmiä. Juuri niissä SVES-merkintä olisi kuitenkin
  oikein, joten SVES-herkkyys kärsii (202: v4 37 → v5 12 löydettyä, 222: 126 → 59).
- INCARTin kahdessa eteisvärinätallenteessa kammiovaste on poikkeuksellisen tasainen.
  Epäsäännöllisyysluku jäi mediaaniltaan 0,04:ään, kun raja on 0,10. Siksi niitä ei tunnistettu.
- INCARTissa väärät jaksot tulevat tallenteista, joissa on hyvin tiheästi lisälyöntejä tai sarjoja (I33, I34,
  I42, I47 ja I31). Tiheät eteislisälyönnit tekevät rytmistä aidosti epäsäännöllisen, ja v5 tulkitsee sen
  eteisvärinäksi. Silloin tallenteiden I33 ja I34 SVES-lyönnit jäävät merkitsemättä (v4 915, v5 659 löydettyä).

### Sarjat

Viitesarja tarkoittaa vähintään kolmea peräkkäistä S- tai V-lyöntiä. Ohjelman sarja on löydetty, jos se osuu
ajallisesti viitesarjaan (±150 ms).

| | Viitesarjoja (S / V / sekalaiset) | Löydetty Se | Ohjelman sarjoista oikeita (+P) |
|---|---:|---:|---:|
| MIT-BIH DS1 | 61 (20 / 32 / 9) | 44,3 % (S 85 %, V 31 %) | 65,9 % |
| MIT-BIH DS2 | 170 (153 / 16 / 1) | 2,4 % (S 0 %, V 25 %) | 57,1 % |
| INCART | 145 (9 / 134 / 2) | 24,1 % (S 33 %, V 23 %) | 33,6 % |

DS2:n S-sarjoista suurin osa on tallenteessa 232 (ks. yllä). Lisäksi tallenteen 222 eteistakykardiat osuvat
epäsäännöllisen rytmin jaksoihin. VES-sarjat jäävät usein löytymättä, koska kammiotakykardiassa lyönnit
muistuttavat toisiaan. Silloin paikallinen "normaalimalli" sekoittuu, tai sarja on hitaampi kuin 100/min
(kiihtynyt idioventrikulaarinen rytmi, esim. tallenne 124).

### Ablaatio: mitä eteisvärinäjaksojen SVES-esto tekee

Alla on sama v5 ilman eteisvärinäjaksojen SVES-estoa (`AF_THR` asetettu niin suureksi, ettei jaksoja synny).
**Tämä on raportointia, ei valinta.** Version valitseminen tämän taulukon perusteella olisi säätämistä
testidatalla, eikä sitä ole tehty.

| SVES Se / +P | v5 | v5 ilman estoa | v4 |
|---|---:|---:|---:|
| MIT-BIH DS1 | 70,4 / 83,6 | 72,6 / 53,8 | 28,6 / 46,0 |
| MIT-BIH DS2 | 10,9 / 43,4 | 19,2 / 28,2 | 16,4 / 36,1 |
| INCART | 70,1 / 57,1 | 87,3 / 58,8 | 83,3 / 66,5 |

Esto parantaa osuvuutta MIT-BIH:ssä paljon, mutta INCARTissa se vain heikentää herkkyyttä. Muut v5:n
SVES-muutokset ((b), (c) ja (d)) nostavat herkkyyttä kaikissa aineistoissa, mutta laskevat osuvuutta
INCARTissa (66,5 → 58,8 %). VES-tuloksiin esto ei käytännössä vaikuta.

### Missä v5 on huonompi kuin v4

- **SVES-herkkyys DS2:ssa** (16,4 → 10,9 %; ilman tallennetta 232 49,7 → 31,5 %) ja **INCARTissa**
  (83,3 → 70,1 %). Pääsyy on eteisvärinäjaksojen SVES-esto tallenteissa, joissa on eteistakykardiaa,
  eteislepatusta tai hyvin tiheitä eteislisälyöntejä (MIT 202, 222; INCART I33, I34).
- **SVES-osuvuus INCARTissa** (66,5 → 57,1 %). Uusia vääriä SVES-merkintöjä tulee mm. tallenteista I35 (118, kammioparit ja
  fuusiolyönnit takykardiassa), I42 (220), I62, I67 ja I06–I07.
- **VES-osuvuus INCARTissa** (95,2 → 89,7 %) ja hieman MIT-BIH:ssä (93,1 → 92,5 %). Pelkän muodon perusteella
  merkittyjä normaaleja lyöntejä oli INCARTissa 176. Vääriä VES-merkintöjä tuli eniten lisää tallenteissa
  I01 (80 → 273), I54 (42 → 156), I04 (13 → 57), I03 (10 → 50) ja I40 (6 → 34).
- **SVES, tyypillinen yksittäinen** (MIT 81,8 → 72,8 %, INCART 97,4 → 79,5 %). Äkillisyysvaatimus, sarjasääntöjen
  sekalaisten jonojen käsittely ja eteisvärinäesto karsivat myös osan "helpoista" SVES-lyönneistä.
- **Eteisvärinän tunnistus ei yleistynyt INCARTiin** (0 % kahdessa eteisvärinätallenteessa, vääriä jaksoja 12
  tallenteessa).

**Johtopäätös.** VES-tunnistuksen muutokset (e) ja (b) näyttävät yleistyvän. SVES-muutokset eivät yleistyneet
testidataan. Jatkokehitys pitäisi tehdä uudella säätöaineistolla, ja tulos pitää varmistaa vielä kolmannella,
ennalta koskemattomalla aineistolla. Testidatana käytettyjä DS2:ta ja INCARTia ei voi enää käyttää puhtaana
testinä, jos parametreja säädetään niiden perusteella.

## Aineistot

**[MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/)** (Moody & Mark 2001), PhysioNet,
lisenssi Open Data Commons Attribution 1.0. Aineisto on rytmihäiriöanalyysin vakiotestiaineisto.

- 48 puolen tunnin kaksikanavaista Holter-nauhoitusta 47 henkilöltä (Beth Israel Hospital, 1975–79).
- 360 Hz, 11 bittiä, noin 110 000 lyöntiä, joista jokaisen on luokitellut kaksi kardiologia toisistaan riippumatta.
- Aineistoon on tarkoituksella valittu paljon rytmihäiriöitä, joten se on vaikeampi kuin tavallisen terveen ihmisen tallenne.

**[St Petersburg INCART 12-lead Arrhythmia Database](https://physionet.org/content/incartdb/1.0.0/)**
(Tihonenko ym. 2008), PhysioNet, lisenssi Open Data Commons Attribution 1.0.

- 75 puolen tunnin otetta 32 potilaan Holter-tallenteista. Potilaat olivat sepelvaltimotaudin tutkimuksissa.
- 12 kytkentää, 257 Hz, WFDB-signaalimuoto 16. Lyöntimerkinnät on tehty automaattisesti ja korjattu käsin.
- Eteisvärinä on vain kahdessa tallenteessa, SVES-lyönnit keskittyvät muutamaan tallenteeseen.

Kumpaakaan aineistoa ei ole jaettu OpenHolterin mukana. Ne ladataan PhysioNetistä, ja tiedostot tarkistetaan
PhysioNetin `SHA256SUMS.txt`-tiedostoa vasten (MIT-BIH: 704 tiedostoa, INCART: 230 tiedostoa, kaikki täsmäsivät).
INCARTin `SHA256SUMS.txt`:ssä tiiviste ja nimi erotetaan yhdellä välilyönnillä, joten `shasum -c` ei lue sitä
suoraan (ks. [Aja itse](#aja-itse)).

**[MIT-BIH Supraventricular Arrhythmia Database](https://physionet.org/content/svdb/1.0.0/)** (SVDB; Greenwald ym. 1990):
78 puolen tunnin kaksikanavaista tallennetta, 128 Hz, ensimmäinen kanava, samat EC57-säännöt.
**[MIT-BIH Atrial Fibrillation Database](https://physionet.org/content/afdb/1.0.0/)** (AFDB; Moody & Mark 1983): 23
noin 10 tunnin tallennetta, 250 Hz, ensimmäinen kanava. Lyöntimerkinnät eivät ole tarkastettuja, joten vain rytmi
pisteytetään sekunneittain merkintöjä `(AFIB` ja `(AFL` vasten, ensimmäinen ja viimeinen minuutti pois. Molempien
lisenssi on Open Data Commons Attribution 1.0, ja tiedostot täsmäsivät `SHA256SUMS.txt`:ään (416 ja 155 tiedostoa).

## Menetelmä

Testi noudattaa standardia **ANSI/AAMI EC57** (rytmihäiriöalgoritmien testaus) samoin kuin v4:ssä:

1. **Signaali.** MIT-BIH: ensimmäinen kanava (MLII 44 tallenteessa, V5 tallenteissa 102 ja 104). INCART:
   kytkentä II. Signaali muunnetaan mikrovolteiksi otsaketiedoston vahvistuksella ja nollatasolla. Se
   näytteistetään 130 Hz:iin (Polar H10:n taajuus) FFT-menetelmällä. Analyysi ajetaan **täsmälleen samalla
   koodilla kuin oikeille tallenteille**. Tallennekohtaisia asetuksia ei ole.
2. **Viite.** Kardiologien lyöntimerkinnät ryhmitellään EC57:n luokkiin:
   N (N, L, R, e, j), S eli SVES (A, a, J, S), V eli VES (V, E), F (fuusio) ja Q (tahdistettu, luokittelematon).
3. **Vertailu.** Löydös vastaa viitelyöntiä, jos ne ovat enintään 150 ms:n päässä toisistaan, yksi yhteen.
   Vertailu alkaa 5 minuutin kohdalta (EC57). Viimeinen minuutti jätetään pois, koska sovellus jättää sen aina
   huomiotta (vyön riisuminen). Kammiovärinä- ja -lepatusjaksot jätetään pois QRS-tilastosta (EC57).
4. **Tahdistetut tallenteet** (MIT-BIH 102, 104, 107, 217) ovat mukana QRS-tilastossa mutta eivät
   lisälyöntitilastoissa (EC57). INCARTissa ei ole tahdistettuja tallenteita.
5. **Lukujen laskenta.** Kaikki on laskettu kaikkien lyöntien yhteismäärästä ("gross"), ei tallenteiden keskiarvona.
   Herkkyys Se = TP / (TP + FN), osuvuus +P = TP / (TP + FP). VES- ja SVES-osuvuuden nimittäjässä ovat kaikki
   ohjelman VES- tai SVES-merkinnät, myös fuusiolyönteihin osuneet (sama tapa kuin v4:ssä).
6. **Epäsäännöllinen rytmi ja sarjat** eivät ole EC57:n mittareita. Ne on määritelty tässä itse, ks. kappaleet yllä.
   Kammiolepatusjaksoihin osuvat ohjelman sarjat lasketaan mukaan sellaisinaan (tallenne 207).

Lukijan ja pisteytyksen koodi on tiedostossa [`openholter/validation.py`](../openholter/validation.py).
WFDB-tiedostomuodot (otsake, signaalimuodot 212 ja 16, MIT-merkinnät) luetaan omalla noin 70 rivin koodilla,
joten tuloksen ja datan välissä ei ole kolmannen osapuolen kirjastoa.

## Rajoitukset

- **Eri laite, eri kytkentä.** MIT-BIH ja INCART on nauhoitettu Holter-laitteilla raajakytkennöillä (MLII, II).
  Polar H10 mittaa rinnan poikki yhdellä kytkennällä. QRS:n muoto ja signaalin laatu eroavat, joten tulos kertoo
  algoritmista eikä suoraan siitä, miten se toimii H10:n kanssa.
- **Rytmihäiriöpainotteiset aineistot.** Tavallisella terveellä ihmisellä, jolla on satunnaisia yksittäisiä
  lisälyöntejä, tilanne vastaa lähinnä "tyypillinen yksittäinen" -lukuja.
- **Pienet osa-aineistot.** SVES-lyönnit ja eteisvärinä keskittyvät muutamaan tallenteeseen (MIT 232, 222, 202;
  INCART I33, I34, I49, I50). Yksittäinen tallenne voi muuttaa kokonaislukua kymmeniä prosenttiyksiköitä.
- **Testidata on nyt käytetty.** DS2 ja INCART olivat koskemattomia v5:n säätöön asti. Jos niiden tuloksia
  käytetään jatkokehitykseen, ne eivät enää ole puhtaita testiaineistoja.
- **Simulaattoritesti** (`tests/test_pipeline.py`) varmistaa, että uudet säännöt toimivat niille tehdyissä
  tapauksissa. Testissä on SVES ilman taukoa, SVT-sarja, eteisvärinäjakso ja myöhäinen VES. Testi ei kerro
  tarkkuudesta oikealla datalla.

## Analyysiversio 4 (aiempi tulos, ennallaan)

Alla on versiolle 4 julkaistu tulos sellaisenaan (testattu 3.11.2026, koko MIT-BIH, ei DS1/DS2-jakoa).
Raakatulokset: [`mitdb-v4-results.json`](validation/mitdb-v4-results.json),
[`mitdb-v4-records.md`](validation/mitdb-v4-records.md).

### Yhteenveto

| Mittari | Tulos | Mitä se tarkoittaa |
|---|---:|---|
| QRS-tunnistus, herkkyys (Se) | **97,4 %** | 97,4 % kaikista sydämenlyönneistä löytyi |
| QRS-tunnistus, osuvuus (+P) | **99,9 %** | löydetyistä lyönneistä 99,9 % oli oikeita |
| VES, osuvuus (+P) | **93,1 %** | kun ohjelma sanoo "VES", se on 93 %:ssa oikeassa |
| VES, herkkyys (Se) | **49,0 %** | puolet kaikista VES-lyönneistä löytyy |
| VES, tyypillinen yksittäinen* | **76,0 %** | VES, jota seuraa tauko normaalissa rytmissä |
| SVES, osuvuus (+P) | **40,0 %** | SVES-merkinnöistä suurin osa on vääriä hälytyksiä |
| SVES, herkkyys (Se) | **20,4 %** | |
| SVES, tyypillinen yksittäinen* | **81,8 %** | |

\* *Tyypillinen yksittäinen:* molemmat naapurit normaaleja lyöntejä, edeltävä väli alle 80 % ja seuraava yli
105 % paikallisesta mediaanista. Tämä on juuri se kuvio, jota menetelmä etsii. Alaryhmissä lasketaan löydetyksi
mikä tahansa lisälyöntimerkintä (VES tai SVES).

**Tulkinta lyhyesti.** Lyönnit löytyvät luotettavasti. Kun ohjelma merkitsee lyönnin kammioperäiseksi
lisälyönniksi (VES), merkintä on yleensä oikea. Ilman eteisvärinää osuvuus on 97,3 %. Ohjelma kuitenkin **alilaskee**: noin puolet
VES-lyönneistä jää löytymättä, koska menetelmä etsii vain ennenaikaista lyöntiä, jota seuraa tauko.
SVES-tunnistus on heikko, eikä sen lukuihin pidä luottaa.

### Aineisto

[MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/) (Moody & Mark 2001), PhysioNet,
lisenssi Open Data Commons Attribution 1.0. Aineisto on rytmihäiriöanalyysin vakiotestiaineisto.

- 48 puolen tunnin kaksikanavaista Holter-nauhoitusta 47 henkilöltä (Beth Israel Hospital, 1975–79).
- 360 Hz, 11 bittiä, noin 110 000 lyöntiä, joista jokaisen on luokitellut kaksi kardiologia toisistaan riippumatta.
- Aineistoon on tarkoituksella valittu paljon rytmihäiriöitä, joten se on vaikeampi kuin tavallisen terveen ihmisen tallenne.

Aineistoa ei ole jaettu OpenHolterin mukana. Se ladataan PhysioNetistä, ja tiedostot tarkistetaan PhysioNetin
`SHA256SUMS.txt`-tiedostoa vasten (704 tiedostoa, kaikki täsmäsivät).

### Menetelmä

Testi noudattaa standardia **ANSI/AAMI EC57** (rytmihäiriöalgoritmien testaus) seuraavin osin:

1. **Signaali.** Ensimmäinen kanava (MLII 44 tallenteessa, V5 tallenteissa 102 ja 104) muunnetaan mikrovolteiksi
   otsaketiedoston vahvistuksella ja nollatasolla. Se näytteistetään 360 → 130 Hz:iin (Polar H10:n taajuus)
   FFT-menetelmällä. Analyysi ajetaan **täsmälleen samalla koodilla kuin oikeille tallenteille**. Mitään ei
   ole säädetty tallennekohtaisesti, eikä algoritmia ole muutettu tämän testin tuloksen perusteella.
2. **Viite.** Kardiologien lyöntimerkinnät ryhmitellään EC57:n luokkiin:
   N (N, L, R, e, j), S eli SVES (A, a, J, S), V eli VES (V, E), F (fuusio) ja Q (tahdistettu, luokittelematon).
3. **Vertailu.** Löydös vastaa viitelyöntiä, jos ne ovat enintään 150 ms:n päässä toisistaan, yksi yhteen.
   Vertailu alkaa 5 minuutin kohdalta (EC57). Viimeinen minuutti jätetään pois, koska sovellus jättää sen aina
   huomiotta (vyön riisuminen). Kammiovärinä- ja -lepatusjaksot jätetään pois QRS-tilastosta (EC57).
4. **Tahdistetut tallenteet** (102, 104, 107, 217) ovat mukana QRS-tilastossa mutta eivät lisälyöntitilastoissa (EC57).
5. **Lukujen laskenta.** Kaikki on laskettu kaikkien lyöntien yhteismäärästä ("gross"), ei tallenteiden keskiarvona.
   Herkkyys Se = TP / (TP + FN), osuvuus +P = TP / (TP + FP).

Lukijan ja pisteytyksen koodi on tiedostossa [`openholter/validation.py`](../openholter/validation.py).
WFDB-tiedostomuodot luetaan omalla noin 60 rivin koodilla, joten tuloksen ja datan välissä ei ole
kolmannen osapuolen kirjastoa.

### Tulokset yksityiskohtaisesti

#### QRS-tunnistus (48 tallennetta)

| | Viitelyöntejä | Löydetty (TP) | Puuttui (FN) | Ylimääräinen (FP) | Se | +P |
|---|---:|---:|---:|---:|---:|---:|
| Kaikki | 87 521 | 85 240 | 2 281 | 68 | 97,4 % | 99,9 % |
| Ilman eteisvärinää/-lepatusta | 72 352 | 70 772 | 1 580 | 55 | 97,8 % | 99,9 % |

Häiriönä hylätyistä lyönneistä huolimatta analyysiin jää 97,3 % viitelyönneistä.
Heikoimmat tallenteet ovat 228 (71 %), 104 (83 %, tahdistettu, V5) ja 203 (85 %, monimuotoiset VES-lyönnit
ja kammiotakykardia). Niissä on matalia tai hyvin vaihtelevan muotoisia QRS-komplekseja, jotka 130 Hz:n kaistalla
ja kiinteällä kynnyksellä jäävät havaitsematta. Tunnetut algoritmit pääsevät tässä aineistossa yli 99 %:n
herkkyyteen täydellä 360 Hz:n näytteistyksellä, joten parannettavaa on.

#### Lisälyönnit (44 tallennetta, ei tahdistettuja)

Ristiintaulukko: rivit ovat kardiologin luokka, sarakkeet OpenHolterin merkintä.

| Viite ↓ / OpenHolter → | VES | SVES | ei merkintää |
|---|---:|---:|---:|
| N (normaali) | 121 | 538 | 71 205 |
| S (SVES) | 39 | 472 | 1 805 |
| V (VES) | 2 789 | 156 | 2 751 |
| F (fuusio) | 3 | 3 | 606 |
| Q | 2 | 0 | 13 |
| ei viitelyöntiä | 42 | 10 | |

| | Se | +P | Se, tyypillinen yksittäinen | Se, kaikki yksittäiset |
|---|---:|---:|---:|---:|
| VES | 49,0 % | 93,1 % | 76,0 % (2 783 lyöntiä) | 56,5 % (4 151) |
| SVES | 20,4 % | 40,0 % | 81,8 % (378) | 55,7 % (632) |
| Kaikki lisälyönnit (V + S) | 43,1 % | 82,9 % | | |
| Ilman eteisvärinää: VES | 50,1 % | **97,3 %** | | |
| Ilman eteisvärinää: kaikki | 42,5 % | **96,9 %** | | |

VES-lyönneistä 156 (2,7 %) merkittiin SVES:ksi ja SVES-lyönneistä 39 VES:ksi.

#### Miksi lyöntejä jää löytymättä

Lyönnit, joita ohjelma ei merkinnyt lisälyönniksi lainkaan (VES 2 751, SVES 1 802), jakautuvat näin:

| Syy | VES | SVES |
|---|---:|---:|
| Ei ennenaikainen (alle 20 % lyhyempi väli) | 874 | 149 |
| Osa sarjaa (pari, kolmikko, takykardia tai bigeminia fuusiolyöntien kanssa) | 676 | 1 480 |
| QRS jäi kokonaan havaitsematta | 703 | 105 |
| Muu (esim. viitearvo vääristynyt, kohina) | 366 | 21 |
| Ei taukoa jälkeen (interpoloitu lyönti) | 95 | 47 |
| Hylätty häiriönä | 37 | 0 |

*(Luvut on laskettu viitemerkintöjen rytmistä erillisellä analyysillä. Ne ovat suuntaa antavia, eivät osa
EC57-raporttia.)*

- **Ennenaikaisuuteen perustuva menetelmä** ei näe VES-lyöntiä, joka tulee lähes normaalin välin jälkeen.
  Sellainen on tavallinen hitaalla sykkeellä. Lyönnin muoto (leveä QRS) paljastaisi sen.
- **Sarjat:** tallenteessa 232 on yli tuhat peräkkäistä eteisperäistä lyöntiä. Pitkät sarjat ja takykardiat
  eivät näytä yksittäiseltä lisälyönniltä, eikä ohjelma tällä hetkellä raportoi niitä.
- **Eteisvärinä:** epäsäännöllinen rytmi saa normaalitkin lyönnit näyttämään ennenaikaisilta. Suurin osa
  väärien SVES-merkintöjen kertymästä tulee eteisvärinätallenteista (201, 202, 203, 219, 222).
  Eteisvärinää ohjelma ei tunnista eikä raportoi.

### Rajoitukset

- **Eri laite, eri kytkentä.** MIT-BIH on nauhoitettu Holter-laitteella raajakytkennällä (MLII). Polar H10 mittaa
  rinnan poikki yhdellä kytkennällä. QRS:n muoto ja signaalin laatu eroavat, joten tulos kertoo algoritmista
  eikä suoraan siitä, miten se toimii H10:n kanssa.
- **Rytmihäiriöpainotteinen aineisto.** Tavallisella terveellä ihmisellä, jolla on satunnaisia yksittäisiä
  lisälyöntejä, tilanne vastaa lähinnä "tyypillinen yksittäinen" -lukuja.
- **Yksi aineisto.** Koska algoritmia ei ole säädetty tällä aineistolla, tulos ei ole ylisovitettu. Jos
  algoritmia jatkossa parannetaan tämän testin perusteella, tulos pitää varmistaa myös toisella aineistolla
  (esim. [INCART](https://physionet.org/content/incartdb/1.0.0/)) tai MIT-BIH:n vakiintuneella
  opetus/testi-jaolla (de Chazal ym. 2004), ja molemmat tulokset julkaistaan.
- **Simulaattoritesti** (`tests/test_pipeline.py`) antaa lähes 100 %:n tulokset, koska simuloidut lisälyönnit ovat
  juuri sitä tyyppiä, jota menetelmä etsii. Siksi tämä testi oikealla datalla on tarpeen.
## Aja itse

```bash
# 1. lataa MIT-BIH (77 Mt) ja tarkista
curl -LO https://physionet.org/static/published-projects/mitdb/mit-bih-arrhythmia-database-1.0.0.zip
unzip mit-bih-arrhythmia-database-1.0.0.zip
cd mit-bih-arrhythmia-database-1.0.0 && shasum -a 256 -c SHA256SUMS.txt && cd ..

# 2. lataa INCART (564 Mt) ja tarkista (tiedostossa yksi välilyönti tiivisteen ja nimen välissä)
curl -L -o incartdb.zip https://physionet.org/static/published-projects/incartdb/st-petersburg-incart-12-lead-arrhythmia-database-1.0.0.zip
unzip incartdb.zip -d incartdb
cd incartdb/files && sed 's/ /  /' SHA256SUMS.txt | shasum -a 256 -c - && cd ../..

# 3. lataa SVDB (55 Mt) ja AFDB (461 Mt) samalla tavalla (tiedostossa yksi välilyönti tiivisteen ja nimen välissä)
curl -LO https://physionet.org/static/published-projects/svdb/mit-bih-supraventricular-arrhythmia-database-1.0.0.zip
unzip mit-bih-supraventricular-arrhythmia-database-1.0.0.zip
curl -L -o afdb.zip https://physionet.org/static/published-projects/afdb/mit-bih-atrial-fibrillation-database-1.0.0.zip
unzip afdb.zip -d afdb

# 4. aja validointi (muutama minuutti, AFDB:ssä 233 tuntia)
python -m openholter validate --mitdb mit-bih-arrhythmia-database-1.0.0 --incartdb incartdb/files \
  --svdb mit-bih-supraventricular-arrhythmia-database-1.0.0 --afdb afdb/files --out docs/validation
```

Komento kirjoittaa tiedostot `docs/validation/<aineisto>-v<analyysiversio>-results.json` ja `-records.md`.
MIT-BIH:n JSON sisältää kokonaistuloksen (`summary`) sekä DS1:n ja DS2:n erikseen (`summary_ds1`, `summary_ds2`).

Jos muutat analyysia, aja validointi uudelleen ja liitä muuttuneet tiedostot `docs/validation/`
pull requestiin, myös silloin, kun tulos heikkenee. Säädä vain DS1:llä ja kerro, mitä säädit.

## Lähteet

- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. *IEEE Eng Med Biol* 20(3):45–50 (2001).
- Tihonenko V, Khaustov A, Ivanov S, Rivin A, Yakushenko E. St Petersburg INCART 12-lead Arrhythmia Database.
  PhysioNet (2008). doi:10.13026/C2V88N.
- Greenwald SD, Patil RS, Mark RG. Improved detection and classification of arrhythmias in noise-corrupted
  electrocardiograms using contextual information. *Computers in Cardiology* 17:461–464 (1990). (SVDB)
- Moody GB, Mark RG. A new method for detecting atrial fibrillation using R-R intervals.
  *Computers in Cardiology* 10:227–230 (1983). (AFDB)
- Goldberger AL ym. PhysioBank, PhysioToolkit, and PhysioNet. *Circulation* 101(23):e215–e220 (2000).
- ANSI/AAMI EC57: Testing and reporting performance results of cardiac rhythm and ST segment measurement algorithms.
- de Chazal P, O'Dwyer M, Reilly RB. Automatic classification of heartbeats using ECG morphology and heartbeat
  interval features. *IEEE Trans Biomed Eng* 51(7):1196–1206 (2004).
- Pan J, Tompkins WJ. A real-time QRS detection algorithm. *IEEE Trans Biomed Eng* 32(3):230–236 (1985).
