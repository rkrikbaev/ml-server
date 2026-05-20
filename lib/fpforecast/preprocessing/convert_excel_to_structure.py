import argparse
import pandas as pd
import os
import logging
from tqdm import tqdm
from collections import defaultdict
from pathlib import Path


logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
logger = logging.getLogger(__name__)


KWH_START_PATHS = [
    '/AKMOLA',
    '/ALMATY',
    '/UZHNIY',
    '/SEVER/UPNK',
]


def parse_args():
    parser = argparse.ArgumentParser(description='Convert excel files to structure directory.')
    parser.add_argument('excel_dirpath', type=Path, help='Path to the data directory containing excel files.')
    parser.add_argument('structure_dirpath', type=Path, help='Path to the output data directory.')
    parser.add_argument('--output_format', type=str, choices=['csv', 'parquet'], default='csv', help='Output file format.')
    return parser.parse_args()


def main(args):
    filepaths = sorted(list(args.excel_dirpath.glob('**/*.xlsx')))
    
    df_models = defaultdict(list)
    for filepath in tqdm(filepaths):
        df = pd.read_excel(filepath)

        try:
            df['dt'] = pd.to_datetime(df['dt'])
        except Exception as e:
            df['dt'] = df['dt'].str.split(' - ').str[0]
            df['dt'] = pd.to_datetime(df['dt'], errors='coerce')

        # Drop too old data
        df = df[df['dt'] >= pd.Timestamp('2016-01-01')]

        # Force type
        df[df.columns.difference(['dt'])] = df[df.columns.difference(['dt'])].replace(',','.',regex=True).astype(float)

        # Fix missing hours in some datasets.
        # There, only dates are correct and all the time is 00:00:00.
        dates = df['dt'].dt.date
        for date, df_group in df.groupby(dates):
            if len(df_group) % 24 == 0:
                hours = df_group['dt'].dt.hour
                if all(hours == range(len(hours))):
                    continue
                else:
                    new_dts = pd.date_range(
                        start=pd.Timestamp(date),
                        periods=len(df_group),
                        freq='h'
                    )
                    df.loc[df_group.index, 'dt'] = new_dts
            elif len(df_group) == 1:
                pass
            else:
                logger.warning(f'Unexpected number of rows for date {date} in file {filepath}: {len(df_group)} rows.')

        for col in df.columns.difference(['dt']):
            df.rename(columns={col: ('/' + col) if not col.startswith('/') else col}, inplace=True)
        
        for col in df.columns.difference(['dt']):
            model_path = Path(col).relative_to('/')
            target_file = args.structure_dirpath / model_path / f'values.{args.output_format}'
            
            df_model = df[['dt', col]].set_index('dt').rename(columns={col: 'value'})

            # Handle units
            if any(col.startswith(p) for p in KWH_START_PATHS):
                # kWh -> MW
                df_model['value'] /= 1000

            df_models[target_file].append(df_model)


    for target_file, df_list in df_models.items():
        target_file.parent.mkdir(parents=True, exist_ok=True)
        df_model = pd.concat(df_list).sort_index()
        df_model = df_model[~df_model.index.duplicated(keep='last')]
        if args.output_format == 'parquet':
            df_model.to_parquet(target_file)
        else:
            df_model.to_csv(target_file)
        print(f'Saved {target_file}')


if __name__ == '__main__':
    args = parse_args()
    main(args)
