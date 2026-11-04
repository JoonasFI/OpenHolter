# OpenHolter

**Avoimen lähdekoodin EKG-tallennin Polar H10 -sykevyölle: jokainen lyönti analysoidaan, ja jokainen tulos validoidaan avoimesti.**

🇬🇧 [In English](README.md)

![Live-näkymä](docs/screenshots/fi/live.png)

OpenHolter tekee Polar H10 -sykevyöstä ja tietokoneesta Holter-tyyppisen EKG-tallentimen.
Vyö lähettää yksikytkentäisen EKG:n (130 Hz) ja kiihtyvyysdatan Bluetoothilla. Tietokone tallentaa niin pitkään kuin haluat ja löytää
EKG:stä jokaisen sydämenlyönnin. Se merkitsee lisälyönnit (VES/SVES), kertoo, missä kehon asennossa ne tulevat,
ja tekee PDF-raportin, jossa on lääkäriä varten koko EKG. Kaikki data pysyy omalla koneella: ei pilveä, ei tiliä, ei telemetriaa.

> [!IMPORTANT]
> **Vain tutkimus- ja omaan käyttöön. Ei lääkinnällinen laite.**
>
> OpenHolter on avoimen lähdekoodin tutkimusprojekti. Sitä ei ole tarkoitettu sairauksien diagnosointiin, hoitoon,
> seurantaan tai ehkäisyyn, eivätkä sen tulokset korvaa lääkärin arviota. Älä muuta lääkitystäsi tai hoitoasi niiden perusteella.
> OpenHolter ei tunnista sydäninfarktia eikä hälytä vaarallisista rytmihäiriöistä.
>
> **Jos sinulla on sydänoireita, kuten rintakipua tai puristusta, hengenahdistusta, pyörtymistä tai huimausta, ota yhteys lääkäriin.
> Hätätilanteessa soita 112.**
>
> Raaka EKG säilyy aina kokonaan, joten automaattinen analyysi on lisäkerros, joka ei korvaa käyrän katsomista.

## Tulokset lyhyesti

Lyöntianalyysi on testattu samoin kuin kaupalliset rytmihäiriöalgoritmit: kardiologien merkitsemiä vertailuaineistoja
vastaan ANSI/AAMI EC57 -standardin mukaisesti: [MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/) ja
[St Petersburg INCART 12-lead Arrhythmia Database](https://physionet.org/content/incartdb/1.0.0/) (PhysioNet). Versio 5 säädettiin vain MIT-BIH:n puoliskolla (DS1).
Toinen puolisko (DS2) ja INCART (75 tallennetta, noin 142 000 lyöntiä) ovat koskematonta testidataa.

| Herkkyys / osuvuus | [MIT-BIH](https://physionet.org/content/mitdb/1.0.0/) (44 tallennetta) | [INCART](https://physionet.org/content/incartdb/1.0.0/) (75 tallennetta) |
|---|---:|---:|
| **Lyöntien (QRS) tunnistus** | **97,4 % / 99,9 %** | **95,3 % / 99,6 %** |
| **VES** (kammioperäiset lisälyönnit) | **68,0 % / 92,5 %** | **59,3 % / 89,7 %** |
| VES, tyypillinen yksittäinen + tauko | 79,4 % | 73,7 % |
| SVES (eteisperäiset lisälyönnit) | 30,4 % / 68,3 % | 70,1 % / 57,1 % |

- **Lyönnit löytyvät luotettavasti:** 97 % kaikista sydämenlyönneistä lähes ilman vääriä löydöksiä.
- **VES-merkintä on yleensä oikea** (noin 9/10), ja VES-lyönneistä löytyy noin kaksi kolmesta (versio 4: puolet).
  Tyypillisistä yksittäisistä, taukoon päättyvistä lisälyönneistä, jotka ovat yleisimpiä, löytyy noin 3/4.
- **SVES-tunnistus ei ole vielä luotettava**, ks. [Tunnetut heikkoudet](#tunnetut-heikkoudet-ja-seuraava-versio).

Menetelmä, tallennekohtaiset taulukot ja ohje testin toistamiseen: [docs/VALIDATION.md](docs/VALIDATION.md).
Luvut kuvaavat algoritmia vertailuaineiston Holter-tallenteilla; H10:n rintakytkentä on erilainen (ks. alla).

## Kuvakaappaukset

*Kaikki kuvat on otettu sisäänrakennetulla simulaattorilla, eivät ole oikeaa potilasdataa.*

| | |
|---|---|
| ![Tallenne](docs/screenshots/fi/recording.png) | ![Tallenteet ja trendit](docs/screenshots/fi/recordings.png) |
| **Tallenne:** asennon, sykkeen ja EKG:n aikajana, oiremerkinnät, EKG täydellä tarkkuudella VES-merkintöineen ja analyysi asennoittain. | **Tallenteet ja trendit** tallenteiden yli. |
| ![PDF-raportti](docs/screenshots/fi/pdf.png) | ![Asetukset](docs/screenshots/fi/settings.png) |
| **PDF-raportti** lääkärille: yhteenveto, EKG-liuskat 25 mm/s ja koko tallenteen EKG. | **Asetukset** selaimessa: oman vyön lukitus, automaattinen tallennus, lepotilan esto, päivittäinen analyysi, roskakori. |
| ![Asennon kalibrointi](docs/screenshots/fi/calibration.png) | ![Puhelin](docs/screenshots/fi/mobile.png) |
| **Asennon kalibrointi** 3D-hahmon avulla; puhelin toimii kaukosäätimenä. | **Puhelimessa:** tarkista signaali ja paina *Tunsin lisälyönnin*, kun tunnet sellaisen. |

## Ominaisuudet

- **Live-näkymä:** EKG, syke, RR-välit, elektrodikontakti, Bluetooth-yhteyden laatu ja 3D-hahmo asennosta.
  Mitään mitattua ei näytetä ennen kuin vyö ilmoittaa ihokontaktin.
- **Automaattinen tallennus**, kun vyö puetaan (10 s yhtäjaksoinen ihokontakti), ja pysäytys, kun se riisutaan. Voi kytkeä pois.
- **Analyysi** (kerran päivässä, ei koskaan tallennuksen aikana, tai painikkeesta): R-piikit EKG:stä, ennenaikaiset lyönnit
  VES/SVES-luokiteltuina QRS-muodon mukaan, parit, sarjat ja bigeminia, lisälyönnit asennoittain ja tunneittain, HRV (RMSSD/SDNN).
  Epäsäännöllisen rytmin jaksot (sopivat eteisvärinään) ja vähintään kolmen lisälyönnin sarjat raportoidaan (suuntaa antava).
- **Asento** kiihtyvyysanturista: ohjattu kalibrointi ja jälkikalibrointi tallenteesta.
- **Oiremerkintä:** "Tunsin lisälyönnin"; tallenteesta näkee, mitä EKG:ssä tapahtui sillä hetkellä.
- **PDF-raportti:** yhteenveto, EKG-liuskat ja koko tallenne.
- **Trendit**, **roskakori** (30 päivän säilytys) ja **asetukset** selaimessa.
- **Suomi ja englanti** käyttöliittymässä ja PDF:ssä (valinta yläpalkissa).
- **Analyysi paranee myös jälkikäteen:** se lasketaan aina raakadatasta, joten parempi versio analysoi myös vanhat tallenteet uudelleen.
- **Avoimesti validoitu** MIT-BIH- ja INCART-tietokannoilla.

## Tunnetut heikkoudet ja seuraava versio

Kerromme heikkoudet yhtä tarkasti kuin vahvuudet. Versiossa 5:

- **VES-määrä on todennäköisesti alakanttiin.** Noin kolmannes VES-lyönneistä jää edelleen löytymättä, erityisesti
  kammiotakykardioissa ja kun QRS on pieni tai epätavallisen muotoinen (MIT-BIH-tallenteet 203, 208, 228).
- **SVES-määrä voi olla väärin kumpaankin suuntaan.** SVES-merkinnöistä 30–40 % voi olla vääriä, ja moni oikea jää löytymättä.
  Versio 5 paransi SVES:ää paljon säätödatassa, mutta **ei testidatassa**: DS2:lla ja INCARTilla se on heikompi kuin versio 4.
  Syy: tiheät eteislisälyönnit ja eteistakykardiat voivat näyttää epäsäännölliseltä rytmiltä, eikä sen aikana merkitä SVES-lyöntejä.
- **Epäsäännöllisen rytmin (eteisvärinän) tunnistus on vain suuntaa antava.** MIT-BIH:ssa se löytää 82 % tällaisten jaksojen
  lyönneistä, mutta INCARTissa se ei tunnistanut kumpaakaan kahdesta eteisvärinätallenteesta ja antoi vääriä jaksoja 12 tallenteessa.
- **Eri laite, eri kytkentä.** Vertailuaineistot on nauhoitettu Holter-laitteilla raajakytkennöillä. H10 mittaa yhden
  rintakytkennän 130 Hz:llä, josta P-aaltoa ja QRS-muotoa on vaikeampi tulkita kuin 12-kytkentäisestä EKG:stä.
  Tarkkuutta itse vyön kanssa ei ole vielä mitattu vertailulaitetta vastaan.
- **Mitä tämä tarkoittaa käytännössä:** automaattiset merkinnät ohjaavat katsetta, eivät korvaa katsomista.
  Löytymättä jäänyt lisälyönti on käyrällä, sitä ei vain ole korostettu. Siksi raportissa on koko EKG, ja siksi
  oiremerkinnät ovat tärkeitä: ne osoittavat kohdat, jotka kannattaa tarkistaa.

**Suunnitelma versioon 6:**

1. **SVES ilman epäsäännöllisen rytmin ansaa:** eteisperäiset lyönnit merkitään myös epäsäännöllisillä jaksoilla, kun niissä
   on toistuva kuvio, ja eteisperäiset sarjat ja takykardiat raportoidaan erikseen sen sijaan, että ne estäisivät merkinnät.
2. **Parempi eteisvärinän tunnistus:** epäsäännöllisyys yhdistetään entropiatyyppisiin mittareihin ja toistuvan kuvion puuttumiseen,
   ja validointi tehdään INCARTin lisäksi eteisvärinään erikoistuneella aineistolla (MIT-BIH Atrial Fibrillation Database).
3. **Vähemmän löytymättömiä VES-lyöntejä:** useita lyöntimalleja tallennetta kohden yhden sijaan sekä parempi pienten ja leveiden
   QRS-kompleksien ja kammioperäisten sarjojen tunnistus.
4. **Validointi itse vyöllä:** H10 puettuna samaan aikaan kliinisen Holterin kanssa ja tulosten vertailu lyönti lyönniltä.
5. **Samat säännöt kuin nyt:** säätö vain DS1:llä, testidata ajetaan kerran parametrien lukitsemisen jälkeen, ja kaikki tulokset
   julkaistaan, myös heikentyneet.

Apu kaikissa näissä on erittäin tervetullutta, ks. [CONTRIBUTING.fi.md](CONTRIBUTING.fi.md).

## Rakenne

```
openholter/
  pmd.py         Polar PMD -protokolla: komennot, kehysten purku (ECG int24 µV, ACC int16 mG), HR-mittaus
  collector.py   bleak-yhteys, uudelleenyhdistäminen, vahtikoira, istunnot, ihokontakti, jatkaminen kaatumisen jälkeen
  storage.py     istuntohakemistot, tunneittain vaihtuvat gzip-tiedostot, metatiedot JSONina
  sessions.py    tallenteen purku aikalinjaksi, harvennus, yhteenvedot
  beats.py       R-piikit ja lisälyöntien luokittelu EKG:stä
  analysis.py    analyysiprosessi: asento, lisälyönnit, HRV, asennoittain ja tunneittain
  posture.py     kalibrointi ja asentojen luokittelu
  report.py      PDF-raportti (reportlab)
  validation.py  MIT-BIH-validointi (omat WFDB-lukijat)
  live.py        live-puskurit ja WebSocket-jakelu
  server.py      FastAPI + basic auth
  i18n.py        palvelimen kieli (virheilmoitukset, PDF)
  power.py       lepotilan esto macOS:ssä, Windowsissa ja Linuxissa
  simulator.py   synteettinen H10 kehitystä varten (sama tavuformaatti kuin oikealla vyöllä)
  static/        käyttöliittymä (ei käännösvaihetta, ei CDN:ää); i18n.js + i18n-en.js kieliä varten
scripts/         deploy, LaunchAgentin asennus ja poisto, Blender-skripti 3D-hahmolle
tests/           protokollan, tallennuksen, analyysin ja raportin testit
docs/            validointiraportti ja tulokset
```

Yksi prosessi ajaa sekä keräintä että web-palvelinta samassa asyncio-silmukassa.
Analyysit ja PDF:t ajetaan erillisessä matalan prioriteetin prosessissa.

### Tallennusformaatti

```
~/openholter-data/
  config.json
  logs/openholter.log                kierrätetään, 5 × 5 Mt
  calibrations/                      jokainen asentokalibrointi omana tiedostonaan
  sessions/2026-10-28_231900/
    meta.json                        aloitus/lopetus, laite, asetukset, yhteysjaksot ja katkot, tapahtumat
    chunk-0000.rec.gz                tunti kerrallaan, raa'at BLE-notifikaatiot + aikaleimat
    cache/                           johdettua dataa, voi poistaa milloin tahansa
```

Jokainen tietue sisältää kellonajan (`time.time_ns`), monotonisen ajan ja raa'an
PMD- tai HR-notifikaation sellaisenaan. Näytteiden välinen ajoitus otetaan H10:n omasta
kellosta (~130,0x Hz). Kellonaika sovitetaan siihen yhteysjaksoittain ajelmakorjattuna.
gzip-virta synkronoidaan levylle 2 s välein, joten katko hukkaa korkeintaan pari sekuntia,
ja keskeneräinenkin tiedosto on luettavissa. Datamäärä on noin 2 Mt tunnissa.

## Kehitys ilman vyötä

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
export OPENHOLTER_HOME=/tmp/openholter-dev
.venv/bin/python -m openholter simulate-night --hours 7.5      # valmis simuloitu tallenne
.venv/bin/python -m openholter run --simulate                  # live-simulaattori, http://localhost:8765
.venv/bin/python tests/test_pipeline.py
```

Simulaattori tuottaa samat tavut kuin H10, joten koko ketju jäsentimestä käyttöliittymään
ajetaan aidosti. Simuloitu tallenne sisältää asennonvaihdot, lisälyöntejä, elektrodin irtoamisen
ja Bluetooth-katkon. Lisälyöntien todelliset ajat tallentuvat tiedostoon `simulation_truth.json`.

## Asennus (macOS)

**1. Python.** Python 3.9 tai uudempi. macOS:n Command Line Tools -Python toimii, samoin python.orgin asennusohjelma.

**2. Koodi.** Aja pääkoneella:

```bash
./scripts/deploy.sh <macin-ssh-nimi>
```

Skripti kopioi koodin hakemistoon `~/openholter`, luo `.venv`:n ja asentaa riippuvuudet.

**3. Ensimmäinen testi Macin omassa Terminalissa.** Käytä näyttöä tai Näytön jakoa, älä SSH:ta.
macOS kysyy Bluetooth-luvan sovellukselta, joka käynnisti prosessin, eikä lupaa voi myöntää SSH-istunnossa:

```bash
cd ~/openholter && .venv/bin/python -m openholter doctor
.venv/bin/python -m openholter probe --seconds 20
```

Kostuta vyön elektrodit ja pue vyö. `probe` tulostaa tuetut mittaukset sekä ECG-, ACC- ja
HR-rivit. Odotettu tulos on noin 130 ECG-näytettä/s ja 50 ACC-näytettä/s.

**4. Salasana käyttöliittymälle (suositus):**

```bash
.venv/bin/python -m openholter set-password
```

Salasanasta tallennetaan vain PBKDF2-tiiviste tiedostoon `~/openholter-data/config.json` (oikeudet 600).

**5. Taustapalvelu:**

```bash
./scripts/install-launchagent.sh
```

Agentti käynnistyy kirjautuessa, ja launchd käynnistää sen uudelleen, jos prosessi kaatuu.
Kaatumisen jälkeen keskeneräinen tallenne jatkuu samana istuntona. Ota käyttöön automaattinen kirjautuminen
(Järjestelmäasetukset → Käyttäjät ja ryhmät), jotta agentti käynnistyy myös sähkökatkon jälkeen.

**6. Avaa** `http://<mac>.local:8765` kotiverkon selaimella.

### Bluetooth-oikeus

macOS kirjaa Bluetooth-luvan (TCC) sille ohjelmalle, joka on prosessista vastuussa:

| Miten ajetaan | Lupa kysytään ohjelmalta |
|---|---|
| Terminal.appissa | **Terminal** |
| LaunchAgentina | **Python-tulkki itse** (`…/Python.app`) |
| SSH:n kautta | ei voi myöntää |

`openholter doctor` tulostaa tarkan Python.app-polun ja luvan tilan. Jos LaunchAgent ei saa yhteyttä vyöhön:
Järjestelmäasetukset → Tietosuoja ja turvallisuus → Bluetooth → lisää kyseinen `Python.app` (polussa Cmd+Shift+G), ja sitten
`launchctl kickstart -k gui/$(id -u)/fi.wilska.openholter`.

### Lepotila

Oletuksena (`prevent_sleep: "always"`) sovellus pitää tietokoneen hereillä niin kauan kuin se on käynnissä
(macOS `caffeinate`, Windows `SetThreadExecutionState`, Linux `systemd-inhibit`), jotta myöhemmin puettu vyö havaitaan.
Näyttö saa sammua. Asetuksella `"recording"` lepotila estetään vain tallennuksen ajaksi.

## Asennus (Windows)

> Windows-tuki on uusi, eikä sitä ole **vielä testattu oikealla vyöllä**. Koodissa on Windows-tuki (Bluetooth Windowsin
> omalla Bluetooth LE -pinolla, lepotilan esto `SetThreadExecutionState`-kutsulla), mutta kerro, mikä toimii ja mikä ei.
> Tietokoneessa tarvitaan Bluetooth 4.0 (LE); Windows 10 tai 11.

**1. Python.** Asenna Python 3.9 tai uudempi osoitteesta [python.org](https://www.python.org/downloads/windows/).
Ruksaa asennusohjelmassa **Add python.exe to PATH**.

**2. Koodi.** Lataa koodi (GitHubissa *Code → Download ZIP* tai `git clone`) esimerkiksi kansioon `C:\OpenHolter` ja aja PowerShellissä:

```powershell
cd C:\OpenHolter
py -m venv .venv
.venv\Scripts\pip install -e .
```

**3. Ensimmäinen testi.** Kostuta elektrodit, pue vyö ja aja:

```powershell
.venv\Scripts\python -m openholter doctor
.venv\Scripts\python -m openholter probe --seconds 20
```

Odotettu tulos on noin 130 EKG-näytettä/s ja 50 ACC-näytettä/s. Windows ei kysy ohjelmilta erillistä Bluetooth-lupaa,
mutta Bluetoothin on oltava päällä (Asetukset → Bluetooth ja laitteet). Vyötä ei tarvitse parittaa.

**4. Salasana käyttöliittymälle (suositus):**

```powershell
.venv\Scripts\python -m openholter set-password
```

**5. Automaattinen käynnistys kirjautuessa** (Tehtävien ajoitus; `pythonw` toimii ilman konsoli-ikkunaa):

```powershell
schtasks /Create /TN OpenHolter /SC ONLOGON /RL LIMITED /TR "C:\OpenHolter\.venv\Scripts\pythonw.exe -m openholter run"
schtasks /Run /TN OpenHolter
```

Poisto: `schtasks /Delete /TN OpenHolter /F`. Loki on tiedostossa `%USERPROFILE%\openholter-data\logs\openholter.log`.

**6. Avaa** `http://localhost:8765` samalla koneella tai `http://<koneen-nimi>:8765` kotiverkossa.
Kun Windows Defenderin palomuuri kysyy, salli Python **vain yksityisissä verkoissa**.

Erot macOS:ään: Bluetoothin signaalinvoimakkuutta (dBm) ei näytetä Windowsissa (yhteyden laatu näytetään silti),
ja datakansio on `C:\Users\<sinä>\openholter-data`.

## Asennus (Linux)

> Linux-tuki on uusi, eikä sitä ole **vielä testattu oikealla vyöllä**. Bluetooth toimii BlueZin kautta (bleak-kirjasto)
> ja lepotilan esto `systemd-inhibit`-komennolla. Kerro, mikä toimii ja mikä ei.

**1. Paketit.** Python 3.9 tai uudempi venv-tuella sekä BlueZ (useimmissa työpöytäjakeluissa valmiina). Debian/Ubuntu:

```bash
sudo apt install python3 python3-venv bluez
systemctl status bluetooth        # pitäisi olla "active (running)"
```

**2. Koodi.** `git clone https://github.com/JoonasFI/OpenHolter.git ~/openholter` (tai toiselta koneelta SSH:n yli
`./scripts/deploy.sh <kone>`), sitten:

```bash
cd ~/openholter && python3 -m venv .venv && .venv/bin/pip install -e .
```

**3. Ensimmäinen testi.** Erillistä Bluetooth-lupaa ei tarvita, eikä vyötä tarvitse parittaa.
Kostuta elektrodit, pue vyö ja aja:

```bash
.venv/bin/python -m openholter doctor
.venv/bin/python -m openholter probe --seconds 20
```

**4. Salasana käyttöliittymälle (suositus):** `.venv/bin/python -m openholter set-password`

**5. Automaattinen käynnistys** systemd-käyttäjäpalveluna. Luo tiedosto `~/.config/systemd/user/openholter.service`:

```ini
[Unit]
Description=OpenHolter ECG recorder

[Service]
ExecStart=%h/openholter/.venv/bin/python -m openholter run
Environment=OPENHOLTER_NO_STDERR=1
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now openholter
loginctl enable-linger "$USER"     # pysyy käynnissä myös, kun et ole kirjautuneena
journalctl --user -u openholter -f # tila; lokitiedosto on ~/openholter-data/logs/openholter.log
```

**6. Avaa** `http://<kone>.local:8765` kotiverkossa. Jos palomuuri on päällä, salli portti 8765 vain kotiverkosta,
esimerkiksi `sudo ufw allow from 192.168.0.0/16 to any port 8765`.

Erot macOS:ään: Bluetoothin signaalinvoimakkuutta (dBm) ei näytetä (yhteyden laatu näytetään silti). Ilman aktiivista
työpöytäistuntoa lepotilan esto voi vaatia polkitilta lisäoikeuden; jos kone silti menee lepotilaan, poista automaattinen
lepotila järjestelmän asetuksista.

## Käyttö

- **Ennen tallennusta:** pue vyö ja katso Live-näkymästä, että *Elektrodikontakti* on *Hyvä* ja EKG-käyrä on siisti.
  Tallennus alkaa automaattisesti.
- **Tallennuksen aikana:** katkot (esim. kantaman ulkopuolella käynti) kirjataan, ja yhteys palautuu itsestään.
  Istunto päättyy, kun vyötä ei ole nähty 10 minuuttiin (`session_timeout_min`).
- **Jälkeenpäin:** *Tallenteet*-näkymässä näkyvät syke, asento ja EKG-yleiskuva, jossa häiriöt ja kontaktin puute on väritetty.
  Valitse kohta, niin EKG näytetään täydellä tarkkuudella.

## Asetukset (`~/openholter-data/config.json`, useimmat myös selaimessa)

| Avain | Oletus | |
|---|---|---|
| `device_name_prefix` | `"Polar H10"` | ensimmäinen löytyvä vyö |
| `device_address` | `null` | lukitse tiettyyn vyöhön |
| `auto_record` | `true` | tallennus alkaa, kun vyö puetaan |
| `acc_sample_rate` / `acc_range_g` | `50` / `4` | H10: 25/50/100/200 Hz, 2/4/8 G |
| `session_timeout_min` | `10` | |
| `data_timeout_s` | `15` | yhdistetään uudelleen, jos dataa ei tule |
| `prevent_sleep` | `"always"` | `always` / `recording` / `never` |
| `analysis_time` | `"12:00"` | päivittäinen analyysi päättyneille tallenteille, `""` = vain painikkeesta |
| `host` / `port` | `0.0.0.0` / `8765` | **älä avaa porttia internetiin** (ei porttiohjausta reitittimeen) |

Käyttöliittymän kieli valitaan selainkohtaisesti (FI/EN yläpalkissa).

## Vianetsintä

```bash
tail -f ~/openholter-data/logs/openholter.log
launchctl print gui/$(id -u)/fi.wilska.openholter | head -30
.venv/bin/python -m openholter doctor
```

- *Ei löydy:* H10 herää vasta, kun elektrodit ovat kosteat ja vyö on iholla. Polar Beat tai muu sovellus
  voi varata yhteyden, joten sulje se puhelimesta.
- *ECG start failed:* H10:n firmware ehkä vanha. Päivitä Polar Flow -sovelluksella.
- *Live näyttää “Ei kontaktia”:* kostuta elektrodit. Kuivalla iholla ensimmäiset minuutit ovat usein kohinaisia.

## Kääntäminen

Suomenkielinen teksti on avain. Uuden kielen saa lisättyä kopioimalla `openholter/static/i18n-en.js`-tiedoston,
kääntämällä arvot, lisäämällä kielen `LANGS`-listaan tiedostossa `i18n.js` ja lataamalla tiedoston `index.html`:ssä.
Palvelimen viestit ja PDF käyttävät funktioita `tr(fi, en)` / `T(fi, en)` tiedostoissa `openholter/i18n.py` ja `openholter/report.py`.

## Lisenssi

OpenHolter on vapaa ohjelma: sitä saa käyttää, muokata ja jakaa
[GNU Affero General Public License v3.0 tai uudemman](LICENSE) (AGPL-3.0-or-later) ehdoin.
Jos ajat muokattua versiota palveluna verkossa, myös sen lähdekoodi on annettava käyttäjien saataville.

Kolmannen osapuolen osat: three.js (MIT, ks. `openholter/static/vendor/three.LICENSE`).

**Kaupallinen lisenssi.** Jos AGPL:n ehdot eivät sovi käyttöösi (esim. suljettu tuote tai palvelu),
kaupallinen lisenssi on mahdollinen: ota yhteyttä tekijään (Joonas Wilska, joonas@wilska.fi).

Osallistuminen: ks. [CONTRIBUTING.fi.md](CONTRIBUTING.fi.md).

*OpenHolter ei ole lääkinnällinen laite eikä sitä ole tarkoitettu diagnoosiin tai hoitopäätöksiin.*
