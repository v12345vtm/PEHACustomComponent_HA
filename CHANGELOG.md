# CHANGELOG - Peha PHC

## Blauwdruk knop_lamp_dimmen (eigen versienummer)

- 0.1.1: beschrijving aangepast: werkt met elke light-entiteit met helderheid, van welk merk ook. Een lamp die alleen aan of uit kan, wordt niet meer gedimd; kort indrukken schakelt die lamp wel om. Het dimmen stopt ook als de lamp onbeschikbaar wordt.
- 0.1.0: eerste versie. Kort indrukken schakelt om, lang indrukken dimt met instelbare looptijd en richting, en er is een veiligheidstijd voor een ontbrekend loslaat-event.

## 0.1.5

- Opgelost: de ethernet knop stuurt nu dezelfde aanvraag als curl: een GET met alleen Host, User-Agent en Accept. Eerder verschilde de aanvraag daarvan, en de lamp reageerde niet zoals met curl.
- Opgelost: sluit de ethernetmodule de verbinding zonder HTTP-antwoord, dan telt dat als bevestiging. De knop geeft dan geen foutmelding meer.
- Nieuw: het verzendlog (sensor "Verstuurde pakketten") toont per druk een regel `HTTP GET <ip>` met `ACK <stm>_<mod>_<cha>_EVT<code>`, gevolgd door de statusregel van de module of `(geen HTTP-antwoord)`.
- Foutmeldingen van de ethernet knop: "niet bereikbaar" bij een mislukte verbinding, "gaf geen antwoord" als de module niet binnen 5 seconden reageert, en de HTTP-status als die 300 of hoger is.
- Ongewijzigd ten opzichte van 0.1.4: de bus-modules, virtuele knoppen, het busprotocol en de entiteiten.

## 0.1.4

- Nieuw: ethernetmodule. Je voegt een ethernetmodule toe met IP-adres (standaard 192.168.1.2), STM-nummer (standaard 0) en een naam.
- Nieuw: ethernet knop. Elke druk stuurt één HTTP-verzoek (`postEvent.html`) met STM, MOD, CHA en EVT naar de ethernetmodule. De functies zijn dezelfde als bij de virtuele knoppen.
- Verwijderen van een ethernetmodule verwijdert ook zijn ethernet knoppen.
- Apparaten van ethernetmodules blijven bij het opstarten staan zolang de module in de configuratie staat.
- Ongewijzigd: de bus-modules, virtuele knoppen, het busprotocol en de entiteiten. Zonder ethernetmodule is de entiteitenlijst gelijk aan 0.1.3.
- Vertalingen (nl en en) en README bijgewerkt. README: Engels eerst, daarna Nederlands.

## 0.1.3

- Nieuwe sensor "Laatste knop-event" per ingangsmodule, met het vereenvoudigde event van de laatste knopactie, bijvoorbeeld `01.12.2`. De attributen `knop`, `code`, `naam`, `actie` en `tijd` geven de details.
- Zestien diagnosesensoren "Event 00" t/m "Event 15" per ingangsmodule, met het laatste numerieke event per knop. Standaard uitgeschakeld.
- Het event `peha_phc_ingang` bevat nu ook het veld `event`, bijvoorbeeld `01.12.2`.
- Ongewijzigd: de ingangslogica en de timing van de statusopvraag uit 0.1.2.
- Versie 0.1.3 in alle bestanden en op de apparaten. De README's (Nederlands en Engels) zijn bijgewerkt.

## 0.1.2

- Ingangen: de statusopvraag komt nu pas na het loslaten van de knop, na 1,5 seconde. Tijdens het indrukken vraagt de integratie niets meer. Daardoor blijft een ingang na een lange druk niet meer op "hoog" staan.
- Komt er geen loslaat-event, dan vraagt de integratie na 10 seconden alsnog de status op.
- Een verouderd antwoord op een statusopvraag wordt rechtgezet door de statusopvraag na het loslaten.
- De service `peha_phc.virtuele_ingang` accepteert ook de naam en het nummer van de functie, net als de Node-RED-flow: `aan > 0 seconden` of `2`.
- Versie 0.1.2 in alle bestanden en op de apparaten. De README's (Nederlands en Engels) zijn bijgewerkt.

## 0.1.1

- Twee poortschakelaars op het hub-apparaat: Poort USB-kabel (STM) en Poort busdongle (RS485). Ze staan standaard aan. Uit sluit de poort echt, zodat een ander programma hem kan gebruiken. De stand blijft bewaard na een herstart.
- Sensor "Verstuurde pakketten (USB-kabel)": de C0 ... C1-pakketten die naar de STM gaan, met de betekenis erbij.
- Sensor "Verwerkte bus-pakketten": de pakketten die de parser verwerkt heeft, in dezelfde vorm als de Node-RED-logregels.
- Na een ingangsevent vraagt de integratie automatisch de status van die module opnieuw op.
- Rolluiken: de cover staat in rust op onbekend, zodat de knoppen altijd aan staan. Tijdens een beweging staat hij op opening of closing. De echte status staat in het attribuut `status` en in de nieuwe sensor "Kanaal N status". Die status wordt na een herstart hersteld.
- Virtuele knoppen hebben vijf functies: Aan > 0 seconden, Uit < 1 seconden, Aan > 1 seconden, Uit > 1 seconden en Aan > 2 seconden. Een klik stuurt één commando, zonder loslaatcommando. In 0.1.0 stuurde een klik nog een indruk en een loslaatcommando.
- Het versienummer staat in alle bestanden en op de apparaten in Home Assistant.
- De repository-links staan in het manifest en in de README.

## 0.1.0

- Eerste versie: configuratie via de gebruikersinterface, relais (8 schakelaars), rolluiken (4 covers met een looptijd per kanaal), ingangen (16 binaire sensoren), statussensoren, Status opvragen en virtuele knoppen.
