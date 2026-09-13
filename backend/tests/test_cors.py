"""The production browser must be able to read API responses and POST valuations."""
import unittest

from fastapi.testclient import TestClient
from backend.app.main import app


class CorsTests(unittest.TestCase):
    def test_production_origin_can_read_api(self):
        origin = 'https://dubai-roi-analysis.vercel.app'
        with TestClient(app) as client:
            response = client.get('/health', headers={'Origin': origin})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('access-control-allow-origin'), origin)

    def test_production_valuation_preflight(self):
        origin = 'https://dubai-roi-analysis.vercel.app'
        with TestClient(app) as client:
            response = client.options('/predict/price', headers={
                'Origin': origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('access-control-allow-origin'), origin)

    def test_unrelated_origin_is_not_allowed(self):
        with TestClient(app) as client:
            response = client.get('/health', headers={'Origin': 'https://unrelated.vercel.app'})
        self.assertNotIn('access-control-allow-origin', response.headers)
