import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.app import analytics_sql, services


class QuantileTests(unittest.TestCase):
    def test_exact_quantiles_and_disk_fallback_match_numpy(self):
        rng = np.random.default_rng(42)
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE numbers (g TEXT, a REAL, b REAL)')
            groups = {str(n): rng.integers(1, 100, (n, 2)).astype(float) for n in (1, 2, 3, 4, 7, 32, 101)}
            for key, values in groups.items():
                connection.executemany('INSERT INTO numbers VALUES (?, ?, ?)', [(key, *row) for row in values])
            for budget in (32 * 1024 * 1024, 1):
                with self.subTest(buffer_bytes=budget), patch.object(analytics_sql, 'NUMERIC_BUFFER_BYTES', budget):
                    actual = analytics_sql.distributions(connection, 'numbers', ('a', 'b'), 'g')
                    for key, values in groups.items():
                        np.testing.assert_allclose(actual[key], np.quantile(values, [.25, .5, .75], axis=0).T)

    def test_empty_distributions(self):
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE numbers (a REAL)')
            self.assertEqual(analytics_sql.quantiles(connection, 'numbers', 'a'), {})


class DownloadTests(unittest.TestCase):
    def test_streams_with_bounded_reads_and_atomic_replacement(self):
        class BoundedResponse(io.BytesIO):
            def read(self, size=-1):
                if not 0 < size <= 1024 * 1024:
                    raise AssertionError('Unbounded download read')
                return super().read(size)

        body = b'x' * (3 * 1024 * 1024 + 19)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dashboard.sqlite'
            with patch('urllib.request.urlopen', return_value=BoundedResponse(body)):
                services._download_file('https://example.com/database', path)
            self.assertEqual(path.read_bytes(), body)
            self.assertFalse(path.with_suffix('.sqlite.download').exists())

    def test_failed_download_preserves_existing_file_and_cleans_partial(self):
        class BrokenResponse(io.BytesIO):
            def read(self, size=-1):
                raise OSError('Interrupted download')

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dashboard.sqlite'
            path.write_bytes(b'existing')
            with patch('urllib.request.urlopen', return_value=BrokenResponse()), self.assertRaises(OSError):
                services._download_file('https://example.com/database', path)
            self.assertEqual(path.read_bytes(), b'existing')
            self.assertFalse(path.with_suffix('.sqlite.download').exists())

    def test_missing_database_does_not_start_raw_data_preparation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(services, 'DASHBOARD_DB_PATH', Path(directory) / 'missing.sqlite'), patch.dict('os.environ', {'DASHBOARD_DB_URL': ''}):
            services.database_path.__wrapped__.cache_clear()
            with self.assertRaisesRegex(FileNotFoundError, 'offline'):
                services.database_path()
            services.database_path.__wrapped__.cache_clear()


class CacheTests(unittest.TestCase):
    def test_parallel_identical_filters_compute_once_and_cache_only_responses(self):
        services._market_summary_cached.cache_clear()
        with patch.object(services, '_prepared_market_summaries', return_value={}), patch.object(services, '_connect') as connect, patch.object(services, 'summarize', return_value=({'metrics': {}}, [])) as summarize:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: services.overview([2025, 2024, 2025], ['land', 'villa']), range(12)))
            services.overview([2024, 2025], ['villa', 'land'])
            self.assertEqual(summarize.call_count, 1)
            self.assertEqual(connect.call_count, 1)
        services._market_summary_cached.cache_clear()


class PreparedArtifactTests(unittest.TestCase):
    def test_prepared_results_avoid_query_and_changed_data_invalidates_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'database.sqlite'
            database.write_bytes(b'test data')
            overview = {'metrics': {'transactions': 123}}
            with patch.object(services, 'DATA_DIR', root), patch.object(services, 'database_path', return_value=database):
                (root / 'market_summaries.json').write_text(json.dumps({
                    'signature': services.signature(database),
                    'summaries': [{'years': [], 'overview': overview, 'areas': []}],
                }))
                services._prepared_market_summaries.cache_clear()
                services._market_summary_cached.cache_clear()
                with patch.object(services, '_connect', side_effect=AssertionError('Unexpected scan')):
                    self.assertEqual(services.overview(), overview)
                database.write_bytes(b'changed data')
                services._prepared_market_summaries.cache_clear()
                self.assertEqual(services._prepared_market_summaries(), {})
                (root / 'market_summaries.json').write_text('{incomplete')
                services._prepared_market_summaries.cache_clear()
                self.assertEqual(services._prepared_market_summaries(), {})
        services._prepared_market_summaries.cache_clear()
        services._market_summary_cached.cache_clear()
