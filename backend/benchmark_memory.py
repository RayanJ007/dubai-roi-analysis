"""Run real API workloads in a fresh process: python -m backend.benchmark_memory.

Needs prepared data, binary model, and dev dependencies. Measures process RSS,
not total container memory (which also includes OS/file-cache accounting).
"""
import json
import time
from contextlib import closing

import psutil
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import services
from note import PRICE_FEATURES


def main():
    process = psutil.Process()
    with TestClient(app) as client:
        for label, path, params in [
            ('full overview', '/market/overview', {}),
            ('cached area summary', '/market/areas', {}),
            ('model and prediction options', '/prediction/options', {}),
            ('latest year overview', '/market/overview', {'years': services.options()['years'][-1]}),
            ('multi-year overview', '/market/overview', {'years': services.options()['years'][-3:]}),
            ('uncached two-year overview', '/market/overview', {'years': services.options()['years'][-2:]}),
            ('cached full overview', '/market/overview', {}),
        ]:
            start = time.perf_counter()
            response = client.get(path, params=params)
            response.raise_for_status()
            if path == '/prediction/options':
                where, query_params = services._prediction_where()
                with closing(services._connect()) as connection:
                    payload = dict(connection.execute(
                        f'SELECT {", ".join(PRICE_FEATURES)} FROM transactions WHERE {where} AND year >= 2000 LIMIT 1',
                        query_params).fetchone())
                prediction = client.post('/predict/price', json=payload)
                prediction.raise_for_status()
                value = prediction.json()['predicted_price']
                client.post('/roi/calculate', json={'purchase_price': value, 'model_value': value,
                                                   'monthly_rent': 10000}).raise_for_status()
                label = 'model, options, valuation and ROI'
            memory = process.memory_info()
            if hasattr(memory, 'peak_wset'):
                peak = memory.peak_wset / 2**20
            else:
                import resource
                import sys
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (2**20 if sys.platform == 'darwin' else 1024)
            print(json.dumps(dict(workload=label, seconds=round(time.perf_counter() - start, 3),
                rss_mib=round(memory.rss / 2**20, 1), peak_rss_mib=round(peak, 1))), flush=True)


if __name__ == '__main__':
    main()
