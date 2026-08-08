"""Fachlich validierte Berechnungen fuer historische Energieintervalle.

Das Modul verarbeitet Energiemengen abgeschlossener Intervalle. Es enthaelt
keine Live- oder Prognoselogik und greift nicht auf die Produktionsdatenbank zu.
"""

from dataclasses import dataclass
from math import isfinite


CONSUMPTION_MEASURED = "1-1:1.9.0 G.01"
CONSUMPTION_PARTICIPATION = "1-1:1.9.0 G.01T"
SELF_COVERAGE = "1-1:2.9.0 G.03"
RENEWABLE_SELF_COVERAGE = "1-1:2.9.0 G.03R"
GENERATION_MEASURED = "1-1:2.9.0 G.01"
GENERATION_PARTICIPATION = "1-1:2.9.0 G.01T"
RESIDUAL_PUBLIC_FEED = "1-1:2.9.0 P.01T"

QUALITY_ACTUAL = frozenset({"L1", "01", "02"})
QUALITY_ESTIMATED = frozenset({"L2", "L3", "03", "04"})


class EnergyDomainError(ValueError):
    """Eingangswerte ergeben keine fachlich gueltige Energiebilanz."""


def _energy(value: float, name: str) -> float:
    value = float(value)
    if not isfinite(value) or value < 0:
        raise EnergyDomainError(f"{name} muss eine endliche, nicht negative Energiemenge sein.")
    return value


def average_interval_power_kw(energy_kwh: float, interval_minutes: int) -> float:
    """Berechnet die durchschnittliche, niemals momentane Intervallleistung."""
    energy = _energy(energy_kwh, "energy_kwh")
    if not isinstance(interval_minutes, int) or interval_minutes <= 0:
        raise EnergyDomainError("interval_minutes muss eine positive ganze Zahl sein.")
    return energy / (interval_minutes / 60.0)


def residual_grid_consumption_kwh(
    measured_consumption_kwh: float,
    self_coverage_kwh: float,
) -> float:
    measured = _energy(measured_consumption_kwh, "measured_consumption_kwh")
    coverage = _energy(self_coverage_kwh, "self_coverage_kwh")
    if coverage > measured:
        raise EnergyDomainError("Eigendeckung ist groesser als der gemessene Verbrauch.")
    return measured - coverage


def community_feed_kwh(
    participation_generation_kwh: float,
    residual_public_feed_kwh: float,
) -> float:
    generation = _energy(participation_generation_kwh, "participation_generation_kwh")
    residual = _energy(residual_public_feed_kwh, "residual_public_feed_kwh")
    if residual > generation:
        raise EnergyDomainError("Restnetzauspeisung ist groesser als die beruecksichtigte Erzeugung.")
    return generation - residual


def self_sufficiency_percent(
    self_coverage_kwh: float,
    measured_consumption_kwh: float,
) -> float | None:
    coverage = _energy(self_coverage_kwh, "self_coverage_kwh")
    measured = _energy(measured_consumption_kwh, "measured_consumption_kwh")
    if measured == 0:
        if coverage != 0:
            raise EnergyDomainError("Eigendeckung ohne gemessenen Verbrauch ist ungueltig.")
        return None
    if coverage > measured:
        raise EnergyDomainError("Eigendeckung ist groesser als der gemessene Verbrauch.")
    return coverage / measured * 100.0


def is_estimated_quality(quality: str | None) -> bool:
    return str(quality or "").strip().upper() in QUALITY_ESTIMATED


@dataclass(frozen=True)
class HistoricalBalance:
    measured_consumption_kwh: float
    self_coverage_kwh: float
    residual_grid_kwh: float
    participation_generation_kwh: float
    community_feed_kwh: float
    residual_public_feed_kwh: float
    self_sufficiency_percent: float | None


def historical_balance(
    *,
    measured_consumption_kwh: float,
    self_coverage_kwh: float,
    participation_generation_kwh: float,
    residual_public_feed_kwh: float,
) -> HistoricalBalance:
    return HistoricalBalance(
        measured_consumption_kwh=_energy(measured_consumption_kwh, "measured_consumption_kwh"),
        self_coverage_kwh=_energy(self_coverage_kwh, "self_coverage_kwh"),
        residual_grid_kwh=residual_grid_consumption_kwh(
            measured_consumption_kwh, self_coverage_kwh
        ),
        participation_generation_kwh=_energy(
            participation_generation_kwh, "participation_generation_kwh"
        ),
        community_feed_kwh=community_feed_kwh(
            participation_generation_kwh, residual_public_feed_kwh
        ),
        residual_public_feed_kwh=_energy(
            residual_public_feed_kwh, "residual_public_feed_kwh"
        ),
        self_sufficiency_percent=self_sufficiency_percent(
            self_coverage_kwh, measured_consumption_kwh
        ),
    )
