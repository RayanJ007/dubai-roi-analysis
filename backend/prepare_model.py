"""Build the deployment model without retraining, pruning, or changing precision.

Run during the Render build, not inside the memory-limited web process.
XGBoost's UBJSON representation avoids the large text-JSON parsing spike.
"""
from pathlib import Path

from note import PRICE_MODEL_PATH, get_price_model_categories, load_price_model


def main():
    destination = PRICE_MODEL_PATH.with_suffix('.ubj')
    temporary = Path(str(destination) + '.tmp.ubj')
    model = load_price_model(PRICE_MODEL_PATH)
    try:
        model.save_model(temporary)
        restored = load_price_model(temporary)
        if model.get_booster().num_boosted_rounds() != restored.get_booster().num_boosted_rounds():
            raise RuntimeError('Converted model has different trees')
        if get_price_model_categories(model) != get_price_model_categories(restored):
            raise RuntimeError('Converted model has different feature categories')
        # Compare complete binary model state, including trees and model attributes.
        if model.get_booster().save_raw(raw_format='ubj') != restored.get_booster().save_raw(raw_format='ubj'):
            raise RuntimeError('Converted model failed lossless round-trip verification')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Verified lossless model: {destination.name} ({destination.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
