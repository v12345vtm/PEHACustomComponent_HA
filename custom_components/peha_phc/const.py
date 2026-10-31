# const.py - Peha PHC versie 0.1.5
"""Constanten voor de Peha PHC-integratie."""

SW_VERSION = "0.1.5"
DOMAIN = "peha_phc"

# Sleutels in de config entry
CONF_STM_PORT = "stm_port"
CONF_BUS_PORT = "bus_port"
CONF_MODULES = "modules"
CONF_TYPE = "type"
CONF_PHC = "phc"
CONF_NAAM = "naam"
CONF_KANAAL = "kanaal"
CONF_FUNCTIE = "functie"
CONF_IP = "ip"
CONF_STM = "stm"
CONF_ETHERNET = "ethernet"

# Standaard poorten: USB-kabel naar de STM en de RS485-busdongle
DEFAULT_STM_PORT = "/dev/ttyACM0"
DEFAULT_BUS_PORT = "/dev/ttyUSB0"
SERIAL_OPTIONS = {"baudrate": 19200, "bytesize": 8, "parity": "N", "stopbits": 2}

# Moduletypen
MODULE_RELAIS = "relais"      # AMD: 8 uitgangen
MODULE_ROLLUIK = "rolluik"    # JRM: 4 rolluikken
MODULE_INGANG = "ingang"      # IMD: 16 ingangen
MODULE_VIRTUEEL = "virtueel"  # virtuele knop op een ingang
MODULE_ETHERNET = "ethernet"  # ethernetmodule: bereikbaar via IP
MODULE_ETHERNET_KNOP = "ethernetknop"  # knop die via de ethernetmodule een functie stuurt
BUS_TYPES = (MODULE_RELAIS, MODULE_ROLLUIK, MODULE_INGANG)  # de modules op de RS485-bus

MODULE_CODES = {MODULE_RELAIS: "AMD", MODULE_ROLLUIK: "JRM", MODULE_INGANG: "IMD"}
MODULE_LABELS = {
    MODULE_RELAIS: "Relais",
    MODULE_ROLLUIK: "Rolluik",
    MODULE_INGANG: "Ingang",
    MODULE_VIRTUEEL: "Virtuele knop",
    MODULE_ETHERNET: "Ethernetmodule",
    MODULE_ETHERNET_KNOP: "Ethernet knop",
}

AANTAL_RELAIS = 8
AANTAL_ROLLUIKEN = 4
AANTAL_INGANGEN = 16
PHC_MIN = 0
PHC_MAX = 31

# Adresmapping: ingang = 0x00 + PHC-nummer, relais/rolluik = 0x40 + PHC-nummer
ADRES_INGANG = 0x00
ADRES_UITGANG = 0x40

# Looptijd van rolluiken in seconden: standaardwaarde per kanaal (0 t/m 3)
DEFAULT_LOOPTIJDEN = (20.0, 25.0, 30.0, 16.0)
MIN_LOOPTIJD = 3
MAX_LOOPTIJD = 180
TIMER_MARGE = 5.0  # extra seconden voordat een beweging zonder eindmelding als klaar telt
# Ingangen: de statusopvraag komt pas na het loslaten; HOLD_TIMEOUT is het vangnet zonder loslaat-event
STATUS_NA_LOSLATEN = 1.5  # seconden na het loslaten van een ingangsknop
HOLD_TIMEOUT = 10.0       # seconden zonder loslaat-event, daarna alsnog de status opvragen
PRIORITEIT = 7

# Virtuele functies: sleutel -> tekst in de keuzelijst. De bijbehorende code staat in protocol.VIRTUAL_CODES.
VIRTUAL_FUNCTIES = {
    "kort": "Aan > 0 seconden",
    "uit_lt_1": "Uit < 1 seconden",
    "lang": "Aan > 1 seconden",
    "uit_gt_1": "Uit > 1 seconden",
    "extra_lang": "Aan > 2 seconden",
}

# Naam van het event dat bij elke ingangsactie wordt afgevuurd
EVENT_INGANG = "peha_phc_ingang"

# Aantal regels in de logsensoren (verstuurde en verwerkte pakketten)
LOG_LENGTE = 20

# Ethernetmodule: opdrachten gaan als HTTP-verzoek naar het IP-adres
ETHERNET_POORT = 80
ETHERNET_STANDAARD_IP = "192.168.1.2"
ETHERNET_TIMEOUT = 5.0  # seconden


def module_address(kind: str, phc: int) -> int:
    """Bus-adres op basis van moduletype en PHC-nummer."""
    if kind == MODULE_INGANG:
        return ADRES_INGANG + phc
    return ADRES_UITGANG + phc


def virtual_device_id(item: dict) -> str:
    """Identifier van een virtuele knop."""
    return f"VIRT_{item[CONF_PHC]:02d}_{item[CONF_KANAAL]:02d}_{item[CONF_FUNCTIE]}"


def module_key(item: dict) -> str:
    """Unieke sleutel van een module-configuratie (voor opties en verwijderen)."""
    if item[CONF_TYPE] == MODULE_VIRTUEEL:
        return virtual_device_id(item)
    if item[CONF_TYPE] == MODULE_ETHERNET:
        return f"ethernet_{item[CONF_IP]}"
    if item[CONF_TYPE] == MODULE_ETHERNET_KNOP:
        return f"ethernetknop_{item[CONF_ETHERNET]}_{item[CONF_PHC]}_{item[CONF_KANAAL]}_{item[CONF_FUNCTIE]}"
    return f"{item[CONF_TYPE]}_{item[CONF_PHC]}"


def ethernet_device_id(ip: str) -> str:
    """Identifier van het apparaat van een ethernetmodule, bijvoorbeeld ETH_192_168_1_2."""
    return "ETH_" + ip.replace(".", "_")
