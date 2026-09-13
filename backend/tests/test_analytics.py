"""Deterministic API regressions; no production data or models required."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app import services


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite"
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE transactions (instance_date TEXT, year INTEGER, area_name_en TEXT, property_type_en TEXT, reg_type_en TEXT, actual_worth REAL, procedure_area REAL, trans_group_en TEXT)")
            connection.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                ("2024-01-01", 2024, "business bay", "building", "existing properties", 1000000, 100, "sales"),
                ("2025-01-01", 2025, "business bay", "land", "existing properties", 2000000, 200, "sales"),
                ("2025-02-01", 2025, "dubai marina", "land", "off-plan properties", 3000000, 150, "sales"),
                ("2025-02-01", 2025, "dubai marina", "villa", "existing properties", 4000000, 200, "sales"),
                ("2025-02-01", 2025, "business bay", "building", "existing properties", 9000000, 100, "mortgages"),
            ])
        connection.close()
        self.database_patch = patch.object(services, "database_path", return_value=self.db)
        self.database_patch.start()
        services._market_summary_cached.cache_clear()
        services.options.__wrapped__.cache_clear()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        services._market_summary_cached.cache_clear()
        services.options.__wrapped__.cache_clear()
        self.database_patch.stop()
        self.temp.cleanup()

    def test_multi_year_type_area_intersection_and_sales_only(self):
        params = [("years", 2024), ("years", 2025), ("property_types", "building"), ("property_types", "land"), ("areas", "business bay"), ("areas", "dubai marina")]
        response = self.client.get("/market/overview", params=params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["metrics"]["transactions"], 3)
        self.assertEqual(data["metrics"]["median_price"], 2000000)
        self.assertEqual(data["metrics"]["off_plan_share"], 1 / 3)
        self.assertEqual(sum(m["transactions"] for m in data["monthly"]), 3)
        self.assertEqual(sum(b["transactions"] for b in data["price_bands"]), 3)

    def test_price_bounds_are_inclusive(self):
        response = self.client.get("/market/overview", params={"min_price": 2000000, "max_price": 3000000})
        self.assertEqual(response.json()["metrics"]["transactions"], 2)
        self.assertEqual(self.client.get("/market/overview", params={"min_price": 3, "max_price": 2}).status_code, 422)

    def test_threshold_applies_to_areas_and_discover_but_not_overview(self):
        self.assertEqual(len(self.client.get("/market/areas", params={"min_transactions": 3}).json()), 0)
        self.assertEqual(len(self.client.get("/opportunities", params={"min_transactions": 3}).json()), 0)
        self.assertEqual(self.client.get("/market/overview", params={"min_transactions": 3}).json()["metrics"]["transactions"], 4)
        self.assertEqual(self.client.get("/market/areas", params={"min_transactions": -1}).status_code, 422)

    def test_empty_year_and_no_matching_area_are_empty_not_global(self):
        self.assertEqual(self.client.get("/market/overview", params={"years": 1991}).json()["metrics"]["transactions"], 0)
        self.assertEqual(self.client.get("/market/areas", params={"areas": "not in data"}).json(), [])

    def test_area_shares_and_normalized_scores(self):
        areas = self.client.get("/market/areas", params={"min_transactions": 1}).json()
        self.assertAlmostEqual(sum(a["market_share"] for a in areas), 1)
        self.assertEqual(areas[0]["price_p25"], 1250000)
        scores = self.client.get("/opportunities", params={"min_transactions": 1}).json()
        self.assertTrue(all(0 <= a["value_score"] <= 100 for a in scores))

    def test_roi_recovers_all_purchase_and_sale_costs(self):
        response = self.client.post("/roi/calculate", json={"purchase_price": 1000000, "monthly_rent": 0, "annual_costs": 0, "appreciation_rate": 0, "holding_years": 5, "closing_cost_rate": .04, "selling_cost_rate": .02})
        data = response.json()
        self.assertEqual(data["projection"][-1]["net_profit"], -60000)
        self.assertAlmostEqual(data["one_year_roi"], -60000 / 1040000)
        self.assertAlmostEqual(data["break_even_sale_price"], 1040000 / .98)

    def test_model_baseline_and_vacancy_flow_through_exit(self):
        response = self.client.post("/roi/calculate", json={"purchase_price": 900000, "model_value": 1000000, "monthly_rent": 10000, "annual_costs": 20000, "vacancy_rate": .1, "appreciation_rate": .1, "holding_years": 2, "closing_cost_rate": 0, "selling_cost_rate": 0})
        data = response.json()
        self.assertAlmostEqual(data["projection"][-1]["future_value"], 1210000)
        self.assertAlmostEqual(data["projection"][-1]["net_profit"], 486000)
        self.assertEqual(data["annual_net_income"], 88000)

    def test_invalid_roi_is_rejected(self):
        for invalid in [{"holding_years": 0}, {"holding_years": 1.5}, {"vacancy_rate": .9}, {"selling_cost_rate": -1}]:
            self.assertEqual(self.client.post("/roi/calculate", json={"purchase_price": 1, "monthly_rent": 0, **invalid}).status_code, 422)

    def test_comparables_exclude_mortgages_future_dates_and_different_sizes(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("ALTER TABLE transactions ADD COLUMN property_sub_type_en TEXT DEFAULT 'flat'")
            connection.execute("ALTER TABLE transactions ADD COLUMN rooms_en TEXT DEFAULT '1 b/r'")
            # Same profile, but after the reference month: must not leak into evidence.
            connection.execute("INSERT INTO transactions VALUES ('2025-02-01',2025,'business bay','building','existing properties',7000000,100,'sales','flat','1 b/r')")
        connection.close()
        payload = dict(procedure_name_en="sell", property_type_en="building", property_sub_type_en="flat", property_usage_en="residential", reg_type_en="existing properties", area_name_en="business bay", rooms_en="1 b/r", procedure_area=100, year=2025, month=1, asking_price=1100000)
        with patch.object(services, "_infer_advertised_area", return_value="business bay"), patch.object(services, "price_model", return_value=None), patch.object(services, "price_model_categories", return_value={}), patch.object(services, "predict_prices", return_value=[1000000]):
            data = self.client.post("/predict/price", json=payload).json()
        self.assertEqual(data["similar_count"], 1)
        self.assertIsNone(data["similar_p25"])
        self.assertIsNone(data["similar_median_price"])
        self.assertAlmostEqual(data["asking_vs_model"], .1)


if __name__ == "__main__":
    unittest.main()
