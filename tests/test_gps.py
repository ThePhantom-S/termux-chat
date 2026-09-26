import unittest
import tempfile
import time
from pathlib import Path
from emergency_mesh.gps import (
    LocationManager,
    validate_coordinates,
    haversine_distance
)

class TestGPSLocation(unittest.TestCase):
    def test_validate_coordinates(self):
        self.assertTrue(validate_coordinates(13.0895, 80.2739))
        self.assertTrue(validate_coordinates("-12.34", "56.78"))
        self.assertFalse(validate_coordinates(0, 0))  # Null Island
        self.assertFalse(validate_coordinates(91, 0))  # Invalid Lat
        self.assertFalse(validate_coordinates(0, 181)) # Invalid Lon
        self.assertFalse(validate_coordinates("invalid", "coords"))

    def test_haversine_distance(self):
        # Distance between Chennai (13.0827, 80.2707) and Bengaluru (12.9716, 77.5946) ~ 290 km
        dist = haversine_distance(13.0827, 80.2707, 12.9716, 77.5946)
        self.assertIsNotNone(dist)
        self.assertAlmostEqual(dist / 1000.0, 290.0, delta=15.0)

        # Invalid inputs return None
        self.assertIsNone(haversine_distance(None, None, 10, 10))

    def test_manual_location_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir)
            lm1 = LocationManager(config_dir=config_path)

            # Initially no manual override
            self.assertIsNone(lm1.manual_override)

            # Set manual location
            success = lm1.set_manual_location(13.0, 80.0)
            self.assertTrue(success)
            self.assertIsNotNone(lm1.manual_override)
            self.assertEqual(lm1.manual_override["latitude"], 13.0)
            self.assertEqual(lm1.manual_override["longitude"], 80.0)
            self.assertEqual(lm1.manual_override["provider"], "manual")

            # Check persistent loading in a new instance
            lm2 = LocationManager(config_dir=config_path)
            self.assertIsNotNone(lm2.manual_override)
            self.assertEqual(lm2.manual_override["latitude"], 13.0)
            self.assertEqual(lm2.manual_override["longitude"], 80.0)

            # Clear manual location
            lm2.clear_manual_location()
            self.assertIsNone(lm2.manual_override)

            lm3 = LocationManager(config_dir=config_path)
            self.assertIsNone(lm3.manual_override)

    def test_ip_or_fallback_location(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = LocationManager(config_dir=Path(tmpdir))
            loc = lm.get_location_fresh()

            # Should either fetch valid IP / termux location or return cached location
            if loc:
                self.assertTrue(validate_coordinates(loc["latitude"], loc["longitude"]))
                self.assertIn(loc["provider"], ["termux-gps", "ip-geolocation", "manual"])

if __name__ == "__main__":
    unittest.main()
