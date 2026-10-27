# Peha PHC Integratie - Gebruikershandleiding

Welkom bij de Peha PHC-integratie voor Home Assistant. Deze integratie stelt je in staat om je fysieke Peha-installatie (relais, rolluiken en ingangen) rechtstreeks via Home Assistant aan te sturen en uit te lezen.

De integratie maakt gebruik van een dubbele USB-architectuur:
*   **Tx (Zenden):** Via de STM-stuureenheid (meestal `/dev/ttyACM0`). De integratie regelt de benodigde `C0 ... C1` omhulling en CRC-berekening.
*   **Rx (Ontvangen):** Via een RS485-dongle op de databus (meestal `/dev/ttyUSB0`). De integratie vangt alle bus-berichten op en vertaalt deze naar real-time Home Assistant statussen.

---

## 1. Installatie & Configuratie

1.  Kopieer de map `phc_bus` naar de map `custom_components` in je Home Assistant configuratie.
2.  Herstart Home Assistant.
3.  Ga naar **Instellingen** -> **Apparaten & Diensten** -> **Integratie toevoegen**.
4.  Zoek naar **Peha PHC**.
5.  Vul de paden naar je USB-poorten in:
    *   **STM USB Poort (Tx):** `/dev/ttyACM0` (of `COM3` op Windows).
    *   **RS485 Dongle Poort (Rx):** `/dev/ttyUSB0` (of `COM4` op Windows).
6.  Klik op **Verzenden**.

---

## 2. Modules Toevoegen

Zodra de integratie is toegevoegd, kun je je modules configureren via de knop **Configureren** op de integratiekaart.

Bij het toevoegen van een module wordt er gevraagd naar:
*   **Type:** Relais (AMD), Rolluik (JRM) of Ingang (IMD).
*   **PHC Nummer (GUI):** Het nummer dat je fysiek op de DIP-schakelaar hebt ingesteld (0 t/m 31).
*   **Naam:** Een herkenbare naam (bijvoorbeeld "Lamp Woonkamer" of "Rolluik Slaapkamer").

*De integratie rekent het GUI-nummer automatisch om naar het juiste Hex-adres op de bus (bijv. Relais 0 = `0x40`, Ingang 0 = `0x00`).*

### 2.1. Relais Toevoegen (AMD)
*   Elke relais-module heeft standaard **8 kanalen**.
*   Na het toevoegen verschijnen er 8 schakelaars in Home Assistant (Kanaal 0 t/m 7).
*   Er wordt ook een **Status** sensor en een **Status opvragen** knop aangemaakt.

### 2.2. Rolluik Toevoegen (JRM)
*   Elke rolluik-module heeft standaard **4 kanalen**.
*   Je moet per kanaal de **looptijd in seconden** opgeven (bijv. 20, 25, 30, 16). Dit is nodig om de positie te berekenen.
*   Home Assistant toont de rolluiken als `cover` entiteiten met de knoppen **Openen**, **Stoppen** en **Sluiten**.

### 2.3. Ingang Toevoegen (IMD)
*   Elke ingangs-module heeft standaard **16 kanalen** (knoppen).
*   De integratie maakt 16 `binary_sensor` entiteiten aan.
*   Bij het opstarten vraagt de integratie automatisch de status op, zodat Home Assistant weet welke knoppen ingedrukt zijn.

---

## 3. De Interface (Apparaat-info)

Als je op een module klikt in Home Assistant, zie je het volgende overzicht (zie afbeelding):

### 3.1. Bediening (Relais)
*   **Kanaal 0 t/m 7:** Dit zijn de schakelaars. Een klik zet het relais aan of uit. De status wordt direct bijgewerkt op basis van de feedback van de bus.
*   **Status opvragen:** Dit is een knop. Als je hierop klikt, stuurt de integratie een verzoek naar de bus om de huidige status van alle 8 relais op te halen.

### 3.2. Sensoren
*   **Status:** Deze sensor toont de ruwe bitmasker-status van de module (bijvoorbeeld `00000000` voor allemaal uit, of `00000100` voor kanaal 2 aan).

### 3.3. Activiteit (Logboek)
Home Assistant houdt automatisch een logboek bij van alle acties. Je ziet hier bijvoorbeeld:
*   `Kanaal 6: Aan` (om 10:09:21)
*   `Status: ??????10` (om 10:09:21)
*   `Kanaal 6: Uit` (om 10:09:19)

---

## 4. Geavanceerd gebruik

### 4.1. Virtuele Knoppen (Ingangen Simuleren)
Je kunt een fysieke knop in je huis simuleren via een automatisering of script. 
Dit doe je door de service `phc_bus.send_input_event` aan te roepen:
```yaml
service: phc_bus.send_input_event
data:
  address: 1        # Het GUI nummer van de IMD module
  channel: 15       # Het kanaal (0-15)
  function: 2       # 2 = Kort, 4 = Lang, 6 = Extra Lang
