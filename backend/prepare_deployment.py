"""Prepare the lossless model, database, and common exact market responses."""
import json
from contextlib import closing

from backend import prepare_model
from backend.app import services
from backend.app.analytics_sql import summarize
from backend.app.precomputed import signature


def main():
    prepare_model.main()
    database = services.database_path()
    years = services.options()['years']
    selections = [(), tuple(years[-1:]), tuple(years[-3:])]
    summaries = []
    for selection in dict.fromkeys(selections):
        where, params = services._market_where(years=list(selection))
        with closing(services._connect()) as connection:
            overview, areas = summarize(connection, where, params)
        summaries.append(dict(years=selection, overview=overview, areas=areas))
        print(f'Prepared exact market summary: {selection or "all years"}', flush=True)
    destination = services.DATA_DIR / 'market_summaries.json'
    temporary = destination.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(dict(signature=signature(database), summaries=summaries),
                                        allow_nan=False), encoding='utf-8')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print('Deployment artifacts ready: database, model, and verified-data summaries.', flush=True)


if __name__ == '__main__':
    main()
