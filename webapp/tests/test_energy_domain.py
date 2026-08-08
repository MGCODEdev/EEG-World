import math
import unittest

from services.energy_domain import (
    EnergyDomainError,
    average_interval_power_kw,
    community_feed_kwh,
    historical_balance,
    is_estimated_quality,
    residual_grid_consumption_kwh,
    self_sufficiency_percent,
)


class EnergyDomainTests(unittest.TestCase):
    def test_quarter_hour_energy_becomes_average_interval_power(self):
        self.assertEqual(average_interval_power_kw(1.0, 15), 4.0)
        self.assertEqual(average_interval_power_kw(0.25, 15), 1.0)

    def test_power_rejects_invalid_energy_and_interval(self):
        for value in (-1, math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(EnergyDomainError):
                average_interval_power_kw(value, 15)
        for minutes in (0, -15, 15.0):
            with self.subTest(minutes=minutes), self.assertRaises(EnergyDomainError):
                average_interval_power_kw(1, minutes)

    def test_residual_grid_is_difference_not_sum(self):
        self.assertEqual(residual_grid_consumption_kwh(10, 3), 7)

    def test_coverage_cannot_exceed_measured_consumption(self):
        with self.assertRaises(EnergyDomainError):
            residual_grid_consumption_kwh(2, 3)
        with self.assertRaises(EnergyDomainError):
            self_sufficiency_percent(3, 2)

    def test_community_feed_is_participation_generation_minus_residual(self):
        self.assertEqual(community_feed_kwh(8, 2.5), 5.5)
        with self.assertRaises(EnergyDomainError):
            community_feed_kwh(2, 2.5)

    def test_self_sufficiency_uses_measured_consumption_as_denominator(self):
        self.assertEqual(self_sufficiency_percent(2.5, 10), 25)
        self.assertIsNone(self_sufficiency_percent(0, 0))

    def test_quality_classification(self):
        self.assertFalse(is_estimated_quality("L1"))
        self.assertTrue(is_estimated_quality("L2"))
        self.assertTrue(is_estimated_quality("l3"))
        self.assertFalse(is_estimated_quality(None))

    def test_historical_balance_reconciles_both_sides(self):
        balance = historical_balance(
            measured_consumption_kwh=12,
            self_coverage_kwh=3,
            participation_generation_kwh=8,
            residual_public_feed_kwh=5,
        )
        self.assertEqual(balance.residual_grid_kwh, 9)
        self.assertEqual(balance.community_feed_kwh, 3)
        self.assertEqual(balance.self_sufficiency_percent, 25)


if __name__ == "__main__":
    unittest.main()
