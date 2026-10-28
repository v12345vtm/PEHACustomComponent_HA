# Peha PHC voor Home Assistant

[English version](README.en.md)

Home Assistant-integratie voor de Peha PHC-bus. Je bedient relais, rolluiken en virtuele knoppen vanuit Home Assistant, en je ziet de ingangen en het verkeer op de bus.

> **Testversie 0.1.2.** Deze integratie is nieuw en zoekt testers met een echte Peha PHC-installatie. Lees eerst de waarschuwing hieronder.

## Waarschuwing

Deze integratie stuurt echte relais en rolluiken aan. Het is geen veiligheidssysteem. Zorg dat je installatie altijd handmatig bedienbaar blijft, en gebruik de integratie op eigen risico.

## Wat kan de integratie?

- **Relaismodule (AMD):** 8 schakelaars, per kanaal aan of uit.
- **Rolluikmodule (JRM):** 4 covers met open, dicht en stop, en een looptijd per kanaal.
- **Ingangsmodule (IMD):** 16 binaire sensoren, en een event bij elke ingangsactie.
- **Virtuele knoppen:** een klik op een ingang, met de functies uit de Node-RED-flow.
- **Poortschakelaars:** de USB-kabel en de busdongle zijn los van elkaar te sluiten, bijvoorbeeld om Node-RED weer te gebruiken.
- **Logsensoren:** alle verstuurde pakketten en alle verwerkte bus-pakketten.

## Vereisten

- Home Assistant, een recente versie. De minimale versie is nog niet vastgesteld.
- Een Peha PHC-installatie met een STM-stuureenheid, aangesloten met een USB-kabel.
- Een RS485-busdongle met USB, aangesloten op de Peha-bus.
- Beide USB-apparaten op dezelfde Home Assistant-machine. Home Assistant moet toegang hebben tot de poorten. Op Linux is dat meestal de groep `dialout`.
- Node-RED mag de poorten niet tegelijk gebruiken.

## Aansluiten

![Aansluitingen Peha PHC](https://i.imgur.com/602oKcF.png)

- De USB-kabel gaat naar de STM-stuureenheid. Standaard is dat `/dev/ttyACM0`. Hierheen gaan de commando's, met C0/C1-framing.
- De RS485-busdongle gaat naar de Peha-bus. Standaard is dat `/dev/ttyUSB0`. Hiervandaan komen de ruwe bus-data.
- Beide poorten werken met 19200 baud, 8 databits, geen pariteit en 2 stopbits.
- Gebruik bij voorkeur de vaste namen onder `/dev/serial/by-id/`. De namen `ttyACM0` en `ttyUSB0` kunnen na een herstart van volgorde wisselen.

De bedrading van de bus en de stuureenheid staat op de foto hierboven.

## Installeren

1. Kopieer de map `custom_components/peha_phc` naar de map `custom_components` van Home Assistant. Je kunt deze repository ook in HACS toevoegen als aangepaste repository van het type integratie.
2. Herstart Home Assistant.
3. Ga naar **Instellingen → Apparaten en diensten → Integratie toevoegen** en kies **Peha PHC**.
4. Vul de poorten in. De standaard is `/dev/ttyACM0` voor de USB-kabel en `/dev/ttyUSB0` voor de busdongle. Lukt de verbinding niet, dan krijg je een melding. Controleer dan het pad en of Node-RED de poort gebruikt.

Draai je al versie 0.1.0 of nieuwer? Dan vervang je alleen de map en herstart je Home Assistant. Bestaande entiteiten houden hun id.

## Modules toevoegen

Ga naar **Apparaten en diensten → Peha PHC → Configureren**. Per module vul je alleen het PHC-nummer en een naam in.

| Module | Aantal | Bus-adres |
|---|---|---|
| Ingang (IMD) | 16 ingangen | `0x00` + PHC-nummer |
| Relais (AMD) | 8 kanalen | `0x40` + PHC-nummer |
| Rolluik (JRM) | 4 kanalen | `0x40` + PHC-nummer |

Het PHC-nummer is het nummer dat je op de module instelt, van 0 tot en met 31. Relais en rolluik delen het adresbereik `0x40` tot en met `0x5F`, dus één nummer kan maar één uitgangsmodule zijn. De integratie controleert dat bij het toevoegen.

Een virtuele knop voeg je op dezelfde manier toe. Je kiest het PHC-nummer van de ingangsmodule, het kanaal (0 tot en met 15), de functie en een naam.

## Entiteiten

De entiteitsnamen staan in het Nederlands, zoals ze in Home Assistant verschijnen.

**Hub (Peha PHC)**

- *Poort USB-kabel (STM)* en *Poort busdongle (RS485)*: schakelaars, standaard aan. Uit sluit de poort echt, en de stand blijft bewaard na een herstart.
- *Verstuurde pakketten (USB-kabel)*: sensor met de C0 ... C1-pakketten die naar de STM gaan.
- *Verwerkte bus-pakketten*: sensor met de regels die de parser verwerkt heeft.

De twee logsensoren hebben het attribuut `pakketten` (een lijst, als JSON) en het attribuut `tekst` (dezelfde regels als gewone tekst).

**Relaismodule**

- *Kanaal 0* tot en met *Kanaal 7*: schakelaars.
- *Status*: sensor met acht tekens. De positie geeft het kanaal aan, bijvoorbeeld `00000000`.
- *Status opvragen*: knop.
- *Laatste bus-data*: diagnostische sensor.

**Rolluikmodule**

- *Kanaal 0* tot en met *Kanaal 3*: covers, met het attribuut `status`.
- *Looptijd kanaal 0* tot en met *3*: schuifregelaars van 3 tot 180 seconden. De standaard is 20, 25, 30 en 16 seconden.
- *Kanaal N status*: sensor met open, closed, halted, opening, closing of unknown.
- *Kanaal N omhoog* en *Kanaal N omlaag*: knoppen die altijd een commando sturen.
- *Status*, *Status opvragen* en *Laatste bus-data*.

**Ingangsmodule**

- *Ingang 0* tot en met *Ingang 15*: binaire sensoren.
- *Status*: sensor in de vorm `ingangen,LEDs`, met twee keer 16 tekens.
- *Status opvragen* en *Laatste bus-data*.

**Virtuele knop**

- Eén knop per virtuele ingang. Een klik stuurt één commando.

## Virtuele functies

| Functie | Betekenis | Code |
|---|---|---|
| `kort` | Aan > 0 seconden | `0x02` |
| `uit_lt_1` | Uit < 1 seconden | `0x03` |
| `lang` | Aan > 1 seconden | `0x04` |
| `uit_gt_1` | Uit > 1 seconden | `0x05` |
| `extra_lang` | Aan > 2 seconden | `0x06` |

## Rolluiken

- Een commando gaat altijd naar de module, ook tijdens een beweging.
- In rust staat de cover op `unknown`, zodat de knoppen aan blijven. Tijdens een beweging staat hij op `opening` of `closing`.
- De echte status staat in het attribuut `status` en in de sensor *Kanaal N status*.
- Een stop tijdens een beweging geeft `halted`. Home Assistant kent die status niet voor covers.
- Komt er geen eindmelding, dan sluit een vangnet de beweging af na de looptijd plus 5 seconden.
- Na een herstart herstelt de integratie de laatst bekende status uit de sensor.

## Ingangen en de statusopvraag

Een ingangsknop geeft meerdere events achter elkaar. Bij een korte druk, losgelaten binnen een seconde, komen `kort_ingedrukt` en daarna `kort_losgelaten`. Bij een lange druk komt `kort_ingedrukt`, daarna `lang_ingedrukt` na meer dan een seconde en eventueel `extra_lang_ingedrukt` na meer dan twee seconden. Loslaten geeft `lang_losgelaten`.

De integratie vraagt de status van de ingangsmodule pas op nadat de knop is losgelaten, na 1,5 seconde. Tijdens het indrukken vraagt de integratie niets, omdat de module dan nog "hoog" meldt, en dat antwoord kan na het loslaten verkeerd blijven staan. Komt er geen loslaat-event, dan vraagt de integratie na 10 seconden toch de status op. Beide tijden staan in `const.py`.

## Events en services

Bij elke ingangsactie vuurt de integratie het event `peha_phc_ingang` af. Het bevat de velden `module`, `adres`, `naam`, `kanaal` en `actie`. De actie is `kort_ingedrukt`, `kort_losgelaten`, `lang_ingedrukt`, `lang_losgelaten`, `extra_lang_ingedrukt` of `losgelaten`.

Er zijn twee services:

- `peha_phc.stuur_commando` stuurt een ruw commando, met de velden `adres` en `data` in hex. Handig om te testen.
- `peha_phc.virtuele_ingang` stuurt een virtuele functie, met de velden `adres` (het PHC-nummer), `kanaal` en `functie`. De functie mag de sleutel zijn (`kort`), de naam (`aan > 0 seconden`) of het nummer (`2`), net als in de Node-RED-flow.

## Logs en fouten zoeken

Voor meer detail zet je dit in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.peha_phc: debug
```

Veelvoorkomende meldingen:

- **Poort niet beschikbaar:** controleer het pad, de rechten en of Node-RED de poort gebruikt.
- **Module onbeschikbaar:** een van de poorten is uit of niet verbonden.
- **Bus-adres niet ingesteld:** er komt verkeer binnen van een PHC-nummer dat je nog niet hebt toegevoegd.

## Bekende beperkingen en aannames

- Rolluiken: de timer-events lees ik als het einde van de beweging in de laatst gekozen richting. Dat moet nog op echte hardware bevestigd worden.
- Een virtuele knop stuurt één commando, zonder loslaten en zonder wachttijd.
- Niet alle PHC-versies en moduleversies zijn getest. Laat het weten als jouw installatie afwijkt.

## Meewerken en testen

We zoeken testers met een Peha PHC-installatie. Dit zou ik graag getest zien:

- relais aan en uit, en de statussensor
- rolluiken omhoog, omlaag en stop, en de sensor *Kanaal N status*
- ingangen: een druk op een knop geeft een event, en de status klopt na de automatische statusopvraag
- virtuele knoppen
- een herstart van Home Assistant: blijven de poortschakelaars en de rolluikstatus kloppen?

Meld problemen via [GitHub Issues](https://github.com/v12345vtm/PEHACustomComponent_HA/issues). Voeg de versie van de integratie en van Home Assistant toe, je modulelijst en de tekst van de twee logsensoren.

## Ontwikkelen

De protocollogica en de statusovergangen testen zonder Home Assistant:

```bash
python3 -m unittest discover -s tests -v
```

Wijzigingen per versie staan in [CHANGELOG.md](CHANGELOG.md). De integratie is gebaseerd op de Node-RED-flow voor de PHC-bus.
