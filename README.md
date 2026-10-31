# Peha PHC for Home Assistant

Dutch version: see the bottom of this page.

Home Assistant integration for the Peha PHC bus. Control relays, roller shutters and virtual buttons from Home Assistant, and see the inputs and the bus traffic.

> **Test version 0.1.5.** This integration is new and looking for testers with a real Peha PHC installation. Please read the warning below first.

## Warning

This integration controls real relays and roller shutters. It is not a safety system. Make sure your installation can always be operated manually, and use the integration at your own risk.

## What can the integration do?

- **Relay module (AMD):** 8 switches, each channel on or off.
- **Roller shutter module (JRM):** 4 covers with open, close and stop, and a run time per channel.
- **Input module (IMD):** 16 binary sensors, and an event for every input action.
- **Virtual buttons:** a click on an input, with the functions from the Node-RED flow.
- **Port switches:** the USB cable and the bus dongle can be closed independently, for example to use Node-RED again.
- **Log sensors:** all sent packets and all processed bus packets.

## Requirements

- Home Assistant, a recent version. The minimum version has not been determined yet.
- A Peha PHC installation with an STM control unit, connected with a USB cable.
- An RS485 bus dongle with USB, connected to the Peha bus.
- Both USB devices on the same Home Assistant host. Home Assistant needs access to the ports. On Linux this is usually the `dialout` group.
- Node-RED must not use the ports at the same time.

## Wiring

![Peha PHC wiring](https://i.imgur.com/602oKcF.png)

- The USB cable goes to the STM control unit. By default this is `/dev/ttyACM0`. Commands are sent here, with C0/C1 framing.
- The RS485 bus dongle goes to the Peha bus. By default this is `/dev/ttyUSB0`. Raw bus data comes from here.
- Both ports use 19200 baud, 8 data bits, no parity and 2 stop bits.
- Preferably use the stable names under `/dev/serial/by-id/`. The names `ttyACM0` and `ttyUSB0` can swap order after a restart.

The wiring of the bus and the control unit is shown in the photo above.

## Installation

1. Copy the folder `custom_components/peha_phc` to the `custom_components` folder of Home Assistant. You can also add this repository in HACS as a custom repository of type integration.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and choose **Peha PHC**.
4. Enter the ports. The defaults are `/dev/ttyACM0` for the USB cable and `/dev/ttyUSB0` for the bus dongle. If the connection fails, you get a message. Then check the path and whether Node-RED uses the port.

Already running version 0.1.0 or newer? Then only replace the folder and restart Home Assistant. Existing entities keep their id.

Optional blueprint: copy `blueprints/automation/peha/knop_lamp_dimmen.yaml` to `config/blueprints/automation/peha/` in your Home Assistant configuration folder, then reload the automations or restart Home Assistant.

## Adding modules

Go to **Devices & services → Peha PHC → Configure**. For each module you only enter the PHC number and a name.

| Module | Count | Bus address |
|---|---|---|
| Input (IMD) | 16 inputs | `0x00` + PHC number |
| Relay (AMD) | 8 channels | `0x40` + PHC number |
| Roller shutter (JRM) | 4 channels | `0x40` + PHC number |

The PHC number is the number you set on the module, from 0 to 31. Relays and roller shutters share the address range `0x40` to `0x5F`, so one number can only be one output module. The integration checks this when you add a module.

You add a virtual button in the same way. Choose the PHC number of the input module, the channel (0 to 15), the function and a name.

## Entities

Entity names are in Dutch, as they appear in Home Assistant.

**Hub (Peha PHC)**

- *Poort USB-kabel (STM)* and *Poort busdongle (RS485)*: switches, on by default. Off closes the port for real, and the state is kept after a restart.
- *Verstuurde pakketten (USB-kabel)*: sensor with the C0 ... C1 packets sent to the STM.
- *Verwerkte bus-pakketten*: sensor with the lines the parser has processed.

The two log sensors have an attribute `pakketten` (a list, as JSON) and an attribute `tekst` (the same lines as plain text).

**Relay module**

- *Kanaal 0* through *Kanaal 7*: switches.
- *Status*: sensor with eight characters. The position shows the channel, for example `00000000`.
- *Status opvragen* (request status): button.
- *Laatste bus-data* (last bus data): diagnostic sensor.

**Roller shutter module**

- *Kanaal 0* through *Kanaal 3*: covers, with the attribute `status`.
- *Looptijd kanaal 0* through *3* (run time): sliders from 3 to 180 seconds. Default 20, 25, 30 and 16 seconds.
- *Kanaal N status*: sensor showing open, closed, halted, opening, closing or unknown.
- *Kanaal N omhoog* (up) and *Kanaal N omlaag* (down): buttons that always send a command.
- *Status*, *Status opvragen* and *Laatste bus-data*.

**Input module**

- *Ingang 0* through *Ingang 15* (input): binary sensors.
- *Status*: sensor in the form `inputs,LEDs`, two times 16 characters.
- *Status opvragen* and *Laatste bus-data*.
- *Laatste knop-event*: the simplified event of the last button action, for example `01.12.2`.
- *Event 00* through *Event 15*: diagnostic sensors with the last numeric event per button. Off by default.

**Virtual button**

- One button per virtual input. One click sends one command.

## Virtual functions

| Function | Meaning | Code |
|---|---|---|
| `kort` | On > 0 seconds | `0x02` |
| `uit_lt_1` | Off < 1 second | `0x03` |
| `lang` | On > 1 second | `0x04` |
| `uit_gt_1` | Off > 1 second | `0x05` |
| `extra_lang` | On > 2 seconds | `0x06` |

## Roller shutters

- A command always goes to the module, also during a movement.
- At rest the cover is `unknown`, so the buttons stay enabled. During a movement it is `opening` or `closing`.
- The actual status is in the attribute `status` and in the sensor *Kanaal N status*.
- A stop during a movement gives `halted`. Home Assistant has no such state for covers.
- If no end message arrives, a fallback closes the movement after the run time plus 5 seconds.
- After a restart, the integration restores the last known status from the sensor.

## Inputs and the status request

An input button sends several events in a row. A short press, released within one second, gives `kort_ingedrukt` followed by `kort_losgelaten`. A long press gives `kort_ingedrukt`, then `lang_ingedrukt` after more than one second, and possibly `extra_lang_ingedrukt` after more than two seconds. Releasing gives `lang_losgelaten`.

The integration requests the status of the input module only after the button is released, after 1.5 seconds. While the button is pressed it requests nothing, because the module still reports "high" at that moment, and that reply can stay wrong after the release. If no release event arrives, the integration still requests the status after 10 seconds. Both times are set in `const.py`.

## Input events at a glance

An input button sends its events on the bus. They do not always arrive in the same order, and sometimes an event does not arrive at all. The integration therefore keeps the last event it actually received, and requests the status of the module again after the button is released.

Each input module gets two kinds of extra entities:

- *Laatste knop-event* (last button event): the simplified event of the last button action, for example `01.12.2`. That means module 01, button 12, event 2. The attributes `knop`, `code`, `naam`, `actie` and `tijd` give the details.
- *Event 00* through *Event 15*: the last numeric event per button. These diagnostic sensors are off by default. Enable them in the entity settings if you want to use them.

| Code | Name | Meaning |
|---|---|---|
| 2 | `inflank` | Button pressed |
| 3 | `kort_uitflank` | Released within 1 second |
| 4 | `lang` | Pressed longer than 1 second |
| 5 | `lang_uitflank` | Released after longer than 1 second |
| 6 | `lang_zeerlang` | Pressed longer than 2 seconds |
| 7 | `losgelaten` | Released |

The event `peha_phc_ingang` now also contains the field `event`, for example `01.12.2`. You can filter on it in an automation.

Note: a sensor trigger reacts to a change of value. If two identical events follow each other without a change in between, the sensor trigger can fire one time less. The event trigger on `peha_phc_ingang` reacts to every event.

## Blueprint: dim any light with a Peha button

The Peha dimmer modules are old and cannot always dim LED lamps. With this blueprint, a Peha button controls any dimmable light in Home Assistant instead: a smart lamp or a dimmer from another brand, as long as Home Assistant shows it as a `light` entity with brightness.

The blueprint is `blueprints/automation/peha/knop_lamp_dimmen.yaml` (version 0.1.1). It works like this:

- A short press (event 3, released within one second) toggles the light.
- A long press (event 4, after one second) dims the light for as long as the button is held. Releasing (event 5) stops the dimming, and so do events 3 and 7.
- The inputs are: the button (the `Event NN` sensor), the light, the time from 0 to 100 percent, the direction (automatic, up or down), and a safety timeout for when a release event is missing.

Create one automation per button and light from the blueprint. With the direction set to automatic, the light dims down when it is above 50 percent, and up otherwise.

Limitations: the speed is approximate, because a new brightness step is set every 0.3 seconds. A light that only switches on and off is not dimmed; a short press still toggles it. If a release event is missing, the dimming continues until the safety timeout.

## Ethernet module and ethernet buttons

Besides the USB cable and the bus dongle, you can add an ethernet module. The integration reaches it over IP and sends it input events over HTTP, one request per press. Open the options of the integration (**Configure**) and choose **Add ethernet module** to add the module: its IP address (default `192.168.1.2`), its STM number (default 0) and a name.

Then choose **Add ethernet button** to add one or more ethernet buttons. Pick the ethernet module, the PHC number of the input module (`MOD`), the channel (`CHA`, 0 to 15), the function (`EVT`) and a name. Each press sends one request, for example:

`http://192.168.1.2:80/postEvent.html?action=input&STM=0&MOD=3&CHA=0&EVT=2`

The functions are the same as for virtual buttons (see [Virtual functions](#virtual-functions)): `kort` is EVT 2, `uit_lt_1` is 3, `lang` is 4, `uit_gt_1` is 5 and `extra_lang` is 6.

- `STM` is the STM number of the ethernet module, taken from that module's settings.
- `MOD` is the PHC number of the input module, the same number you use on the bus. Check that the ethernet module uses that number too.
- The integration sends the same request as curl does: a GET with only Host, User-Agent and Accept. It does not read the status back from the ethernet module and does not check the module at startup. If the module closes the connection without an HTTP reply, that counts as an acknowledgement: the press shows no error, and the send log shows `ACK 0_0_0_EVT2 (geen HTTP-antwoord)`. If the module cannot be reached, or does not answer within 5 seconds, the press shows an error in Home Assistant.
- The protocol has no password, so keep the ethernet module on a trusted network.
- The device of an ethernet module appears as soon as it has at least one ethernet button.
- Removing an ethernet module with **Remove module** also removes its ethernet buttons.

## Events and services

When an input action happens, the integration fires the event `peha_phc_ingang`. It contains the fields `module`, `adres`, `naam`, `kanaal`, `actie` and `event`. The action is `kort_ingedrukt`, `kort_losgelaten`, `lang_ingedrukt`, `lang_losgelaten`, `extra_lang_ingedrukt` or `losgelaten`.

There are two services:

- `peha_phc.stuur_commando` sends a raw command, with the fields `adres` and `data` in hex. Useful for testing.
- `peha_phc.virtuele_ingang` sends a virtual function, with the fields `adres` (the PHC number), `kanaal` and `functie`. The function can be the key (`kort`), the name (`aan > 0 seconden`) or the number (`2`), as in the Node-RED flow.

## Logs and troubleshooting

For more detail, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.peha_phc: debug
```

Common messages:

- **Port not available:** check the path, the permissions, and whether Node-RED uses the port.
- **Module unavailable:** one of the ports is off or not connected.
- **Bus address not configured:** traffic arrives from a PHC number you have not added yet.

## Known limitations and assumptions

- Roller shutters: I read the timer events as the end of the movement in the last chosen direction. This still needs to be confirmed on real hardware.
- A virtual button sends one command, without a release and without a wait time.
- Not all PHC versions and module versions have been tested. Tell us if your installation differs.
- Without a release event the integration requests the status after 10 seconds. If you want that faster, set `HOLD_TIMEOUT` in `const.py` to 2.5. That is less safe, because a status request is then also sent while the button is still held.

## Testing and feedback

We are looking for testers with a Peha PHC installation. These are the things I would like to see tested:

- relays on and off, and the status sensor
- roller shutters up, down and stop, and the sensor *Kanaal N status*
- inputs: a button press gives an event, and the status is correct after the automatic status request
- virtual buttons
- a restart of Home Assistant: do the port switches and the roller shutter status stay correct?

Report problems via [GitHub Issues](https://github.com/v12345vtm/PEHACustomComponent_HA/issues). Include the version of the integration and of Home Assistant, your module list, and the text of the two log sensors.

## Development

Run the protocol and state tests without Home Assistant:

```bash
python3 -m unittest discover -s tests -v
```

Changes per version are in [CHANGELOG.md](CHANGELOG.md). The integration is based on the Node-RED flow for the PHC bus.


# Support / Donatie


If this has helped you, a small contribution or a coffee is greatly appreciated! 
👉 [Support via PayPal](https://www.paypal.me/v12345vtm/3)









# Peha PHC voor Home Assistant (Nederlands)

English version: see the top of this page.

Home Assistant-integratie voor de Peha PHC-bus. Je bedient relais, rolluiken en virtuele knoppen vanuit Home Assistant, en je ziet de ingangen en het verkeer op de bus.

> **Testversie 0.1.5.** Deze integratie is nieuw en zoekt testers met een echte Peha PHC-installatie. Lees eerst de waarschuwing hieronder.

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

Blauwdruk (optioneel): kopieer `blueprints/automation/peha/knop_lamp_dimmen.yaml` naar `config/blueprints/automation/peha/` in je Home Assistant-configuratiemap, en herlaad daarna de automatiseringen of herstart Home Assistant.

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
- *Laatste knop-event*: het vereenvoudigde event van de laatste knopactie, bijvoorbeeld `01.12.2`.
- *Event 00* tot en met *Event 15*: diagnosesensoren met het laatste numerieke event per knop. Standaard uitgeschakeld.

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

## Ingangsevents in het kort

Een ingangsknop stuurt zijn events op de bus. Die komen niet altijd in dezelfde volgorde binnen, en soms komt er een event helemaal niet door. De integratie houdt daarom het laatste event bij dat echt is ontvangen, en vraagt na het loslaten de status van de module opnieuw op.

Per ingangsmodule zijn er twee soorten extra entiteiten:

- *Laatste knop-event*: het vereenvoudigde event van de laatste knopactie, bijvoorbeeld `01.12.2`. Dat betekent module 01, knop 12, event 2. De attributen `knop`, `code`, `naam`, `actie` en `tijd` geven de details.
- *Event 00* tot en met *Event 15*: het laatste numerieke event per knop. Deze diagnosesensoren staan standaard uit. Zet ze aan via de entiteitsinstellingen als je ze wilt gebruiken.

| Code | Naam | Betekenis |
|---|---|---|
| 2 | `inflank` | Knop ingedrukt |
| 3 | `kort_uitflank` | Losgelaten binnen 1 seconde |
| 4 | `lang` | Langer dan 1 seconde ingedrukt |
| 5 | `lang_uitflank` | Losgelaten na langer dan 1 seconde |
| 6 | `lang_zeerlang` | Langer dan 2 seconden ingedrukt |
| 7 | `losgelaten` | Losgelaten |

Het event `peha_phc_ingang` bevat nu ook het veld `event`, bijvoorbeeld `01.12.2`. Daarop kun je in een automatisering filteren.

Let op: een sensor-trigger reageert op een verandering van de waarde. Komen er twee gelijke events achter elkaar zonder tussenstand, dan kan de sensor-trigger één keer minder afgaan. De event-trigger op `peha_phc_ingang` reageert op elk event.

## Blauwdruk: een dimbare lamp bedienen met een Peha-knop

De dimmermodules van Peha zijn oud en kunnen niet altijd LED-lampen dimmen. Met deze blauwdruk bedient een Peha-knop daarom elke dimbare lamp in Home Assistant: een slimme lamp of een dimmer van een ander merk, zolang Home Assistant die als `light`-entiteit met helderheid toont.

De blauwdruk is `blueprints/automation/peha/knop_lamp_dimmen.yaml` (versie 0.1.1). Zo werkt hij:

- Kort indrukken (event 3, losgelaten binnen een seconde) schakelt de lamp om.
- Lang indrukken (event 4, na een seconde) dimt de lamp zolang de knop ingedrukt blijft. Loslaten (event 5) stopt het dimmen, en events 3 en 7 doen dat ook.
- De invoer is: de knop (de sensor `Event NN`), de lamp, de tijd van 0 naar 100 procent, de richting (automatisch, omhoog of omlaag) en een veiligheidstijd voor als een loslaat-event ontbreekt.

Maak per knop en lamp een eigen automatisering vanuit de blauwdruk. Bij richting automatisch dimt de lamp omlaag als hij boven de 50 procent staat, en anders omhoog.

Beperkingen: de snelheid is een benadering, want er wordt elke 0,3 seconde een nieuwe helderheid ingesteld. Een lamp die alleen aan en uit kan, wordt niet gedimd; kort indrukken schakelt hem wel om. Ontbreekt een loslaat-event, dan dimt de lamp door tot de veiligheidstijd.

## Ethernetmodule en ethernet knoppen

Naast de USB-kabel en de busdongle kun je een ethernetmodule toevoegen. De integratie bereikt die via IP en stuurt de invoer over HTTP, één verzoek per druk. Open de opties van de integratie (**Configureren**) en kies **Ethernetmodule toevoegen** om de module toe te voegen: het IP-adres (standaard `192.168.1.2`), het STM-nummer (standaard 0) en een naam.

Kies daarna **Ethernet knop toevoegen** om één of meer ethernet knoppen toe te voegen. Kies de ethernetmodule, het PHC-nummer van de ingangsmodule (`MOD`), het kanaal (`CHA`, 0 t/m 15), de functie (`EVT`) en een naam. Elke druk stuurt één verzoek, bijvoorbeeld:

`http://192.168.1.2:80/postEvent.html?action=input&STM=0&MOD=3&CHA=0&EVT=2`

De functies zijn dezelfde als bij de virtuele knoppen (zie [Virtuele functies](#virtuele-functies)): `kort` is EVT 2, `uit_lt_1` is 3, `lang` is 4, `uit_gt_1` is 5 en `extra_lang` is 6.

- `STM` is het STM-nummer van de ethernetmodule en komt uit de instellingen van die module.
- `MOD` is het PHC-nummer van de ingangsmodule, hetzelfde nummer als op de bus. Controleer of de ethernetmodule dat nummer ook gebruikt.
- De integratie stuurt dezelfde aanvraag als curl: een GET met alleen Host, User-Agent en Accept. Ze leest de status niet terug van de ethernetmodule en controleert de module ook niet bij het opstarten. Sluit de module de verbinding zonder HTTP-antwoord, dan telt dat als bevestiging: de knop geeft geen foutmelding en het verzendlog toont `ACK 0_0_0_EVT2 (geen HTTP-antwoord)`. Als de module niet bereikbaar is, of niet binnen 5 seconden antwoordt, verschijnt bij het indrukken een foutmelding in Home Assistant.
- Het protocol heeft geen wachtwoord. Hou de ethernetmodule daarom op een vertrouwd netwerk.
- Het apparaat van een ethernetmodule verschijnt zodra er minstens één ethernet knop is.
- Als je een ethernetmodule verwijdert via **Module verwijderen**, worden zijn ethernet knoppen ook verwijderd.

## Events en services

Bij elke ingangsactie vuurt de integratie het event `peha_phc_ingang` af. Het bevat de velden `module`, `adres`, `naam`, `kanaal`, `actie` en `event`. De actie is `kort_ingedrukt`, `kort_losgelaten`, `lang_ingedrukt`, `lang_losgelaten`, `extra_lang_ingedrukt` of `losgelaten`.

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
- Zonder loslaat-event vraagt de integratie na 10 seconden de status op. Wil je dat sneller, zet dan `HOLD_TIMEOUT` in `const.py` op 2.5. Dat is minder veilig, want dan komt er ook tijdens het vasthouden een statusopvraag.

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


#Support
Als dit je geholpen heeft, is een kleine bijdrage of een kopje koffie altijd welkom! 
👉 [Steun via PayPal](https://www.paypal.me/v12345vtm/3)
