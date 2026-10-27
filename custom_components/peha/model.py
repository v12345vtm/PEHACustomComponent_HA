# Peha PHC-integratie, versie 1.1.0
"""Modules en het omrekenen van het PHC-nummer naar het adres op de bus."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import (
    INGANG_MAX,
    NUMMER_MAX,
    NUMMER_MIN,
    RELAIS_KANALEN,
    ROLLUIK_KANALEN,
    TYPE_INGANG,
    TYPE_NAMEN,
    TYPE_RELAIS,
    TYPE_ROLLUIK,
)

KANALEN = {TYPE_RELAIS: RELAIS_KANALEN, TYPE_ROLLUIK: ROLLUIK_KANALEN, TYPE_INGANG: INGANG_MAX}


def module_adres(module_type: str, nummer: int) -> int:
    """Relais en rolluik: 0x40 + nummer. Ingangen: nummer.

    Voorbeelden uit de flow: relais 0 = 0x40, rolluik 2 = 0x42, ingang 1 = 0x01.
    """
    if not NUMMER_MIN <= nummer <= NUMMER_MAX:
        raise ValueError(f"nummer {nummer} valt buiten 0 t/m 31")
    if module_type in (TYPE_RELAIS, TYPE_ROLLUIK):
        return 0x40 + nummer
    if module_type == TYPE_INGANG:
        return nummer
    raise ValueError(f"onbekend moduletype: {module_type}")


@dataclass(frozen=True)
class Module:
    """Eén module zoals de gebruiker die heeft toegevoegd."""

    type: str
    nummer: int
    naam: str = ""
    looptijden: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        module_adres(self.type, self.nummer)  # gooit een fout bij een ongeldig type of nummer
        if len(self.looptijden) != ROLLUIK_KANALEN:
            raise ValueError("er moeten precies 4 looptijden zijn")

    @property
    def adres(self) -> int:
        return module_adres(self.type, self.nummer)

    @property
    def kanalen(self) -> int:
        return KANALEN[self.type]

    @property
    def weergavenaam(self) -> str:
        return self.naam or f"{TYPE_NAMEN[self.type]} {self.nummer}"

    def looptijd(self, kanaal: int) -> float:
        """Looptijd in seconden voor een rolluikkanaal. 0 betekent: lopen tot stop."""
        return self.looptijden[kanaal] if self.type == TYPE_ROLLUIK else 0.0

    def naar_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "nummer": self.nummer,
            "naam": self.naam,
            "looptijden": list(self.looptijden),
        }

    @classmethod
    def van_dict(cls, data: dict[str, Any]) -> Module:
        if "looptijden" in data:
            tijden = [float(t or 0) for t in data["looptijden"]]
        else:  # versie 1.1.0 had één looptijd voor alle kanalen
            tijden = [float(data.get("looptijd") or 0)] * ROLLUIK_KANALEN
        tijden = (tijden + [0.0] * ROLLUIK_KANALEN)[:ROLLUIK_KANALEN]
        return cls(
            type=str(data["type"]),
            nummer=int(data["nummer"]),
            naam=str(data.get("naam") or ""),
            looptijden=tuple(tijden),
        )
