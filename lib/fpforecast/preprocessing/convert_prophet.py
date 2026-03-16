import argparse
import shutil
from prophet.serialize import model_from_json
from pathlib import Path

from fpforecast.models.prophet import ModelWithMetaInfoProphet
from fpforecast.constants import FREQ_TO_PROPHET_PARAMS


def parse_args():
    parser = argparse.ArgumentParser(description="Convert Prophet models to ModelWithMetaInfoProphet format.")
    parser.add_argument('input_dirpath', type=Path, help='Path to the input directory containing Prophet models.')
    parser.add_argument('output_dirpath', type=Path, help='Path to the output directory to save converted models.')
    return parser.parse_args()


def main(args):
    # Copy the input dir entirely to output dir
    shutil.copytree(args.input_dirpath, args.output_dirpath)

    for filepath in args.output_dirpath.glob('**/prophet_model.json'):
        print(f'Converting model at {filepath}...')
        with open(filepath, 'r') as f:
            model = model_from_json(f.read())

        parts = filepath.relative_to(args.output_dirpath).parts
        freq = parts[1]

        model_params = FREQ_TO_PROPHET_PARAMS[freq]
        if model.holidays_prior_scale is not None:
            model_params['holidays_prior_scale'] = model.holidays_prior_scale
        
        model_with_meta = ModelWithMetaInfoProphet(
            model_params=model_params,
            verbose=False,
            debug=False
        )
        model_with_meta.model = model

        model_with_meta.save_model(filepath)
        print(f'Converted and saved model to {filepath}')


if __name__ == '__main__':
    args = parse_args()
    main(args)
