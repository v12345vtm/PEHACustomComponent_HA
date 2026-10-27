# Peha PHC-integratie, versie 1.1.0
"""Constanten van de Peha PHC-integratie. Zuivere Python, zonder Home Assistant."""
from __future__ import annotations

DOMAIN = "peha"
VERSIE = "1.1.0"

# Gegevens van de config-entry
CONF_NAAM = "name"
CONF_STM_POORT = "stm_poort"  # usbkabel naar de STM: hier gaan de commando's in C0/C1-frames
CONF_BUS_POORT = "bus_poort"  # bus-dongle op de RS485-databus: hier komen de ruwe frames binnen
CONF_DEMO = "demo"

# Opties van de config-entry: de modules die je hebt toegevoegd
CONF_MODULES = "modules"

STANDAARD_STM_POORT = "/dev/ttyACM0"
STANDAARD_BUS_POORT = "/dev/ttyUSB0"
BAUDRATE = 19200  # zoals in de flow: 19200 baud, 8 databits, geen pariteit, 2 stopbits

TYPE_RELAIS = "relais"
TYPE_ROLLUIK = "rolluik"
TYPE_INGANG = "ingang"
TYPE_NAMEN = {TYPE_RELAIS: "Relais", TYPE_ROLLUIK: "Rolluik", TYPE_INGANG: "Ingangen"}

RELAIS_KANALEN = 8    # een relaismodule heeft altijd 8 uitgangen
ROLLUIK_KANALEN = 4   # een rolluikmodule heeft altijd 4 kanalen
INGANG_MAX = 16       # een ingangsmodule heeft altijd 16 ingangen
LEDS_STANDAARD = 16   # tot de module laat zien hoeveel LED's hij heeft, nemen we 16
NUMMER_MIN = 0
NUMMER_MAX = 31       # 5 bits: het DIP-adres van de module
LOOPTIJD_MAX = 600    # seconden

STM_PAUZE = 0.06          # seconden tussen twee commando's naar de STM
IDLE_RESET = 0.5          # zo lang geen bytes op de bus: een halfgelezen frame weggooien
HERVERBIND_NA = 10.0      # seconden tussen pogingen om een poort opnieuw te openen
NOODSTOP_MARGE = 5.0      # rolluik met looptijd: na looptijd + marge zetten we de beweging op stil
DEFAULT_PRIORITEIT = 7    # de rolluikmodule negeert lagere prioriteiten (zie de flow)

EVENT_INGANG = "peha_ingang"


def signaal(entry_id: str, soort: str) -> str:
    """Naam van een dispatcher-signaal. soort is 'module', 'hub' of 'conn'."""
    return f"{DOMAIN}_{soort}_{entry_id}"
