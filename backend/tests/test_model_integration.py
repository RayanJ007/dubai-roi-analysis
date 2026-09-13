"""Opt-in checks against the real saved model and local prepared sales data."""
import os
import unittest
from contextlib import closing

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app import services
from backend.app.main import app
from note import PRICE_MODEL_PATH, PRICE_FEATURES, load_price_model, get_price_model_categories
from note import align_price_categories, prepare_price_features, predict_prices


@unittest.skipUnless(os.getenv('RUN_MODEL_INTEGRATION') == '1', 'Requires local data and python -m backend.prepare_model')
class RealModelTests(unittest.TestCase):
    def test_binary_model_and_api_predictions_match_original_model(self):
        original = load_price_model(PRICE_MODEL_PATH)
        original.set_params(n_jobs=1)
        deployed = services.price_model()
        categories = get_price_model_categories(original)
        self.assertEqual(categories, services.price_model_categories())
        where, params = services._prediction_where()
        with closing(services._connect()) as connection:
            # Deterministic records spread across the source, not only its first rows.
            rows = pd.read_sql_query(f'SELECT {", ".join(PRICE_FEATURES)} FROM transactions WHERE {where} AND year >= 2000 AND rowid % 997 = 0 LIMIT 256', connection, params=params)
        self.assertGreaterEqual(len(rows), 100)
        features = align_price_categories(prepare_price_features(rows), categories)
        expected = predict_prices(original, features)
        np.testing.assert_array_equal(predict_prices(deployed, features), expected)
        self.assertEqual(original.get_booster().num_boosted_rounds(), deployed.get_booster().num_boosted_rounds())
        with TestClient(app) as client:
            for index in (0, len(rows) // 2, len(rows) - 1):
                payload = rows.iloc[index].to_dict()
                payload.update(year=int(payload['year']), month=int(payload['month']), has_parking=bool(payload['has_parking']))
                response = client.post('/predict/price', json=payload)
                response.raise_for_status()
                actual = response.json()
                self.assertEqual(actual['predicted_price'], float(expected[index]))
                response = client.post('/roi/calculate', json=dict(purchase_price=actual['predicted_price'], model_value=actual['predicted_price'],
                    monthly_rent=10000, annual_costs=1000, closing_cost_rate=.04, vacancy_rate=.05, appreciation_rate=.03))
                response.raise_for_status()
                self.assertAlmostEqual(response.json()['projection'][-1]['future_value'], float(expected[index]) * 1.03 ** 5)
