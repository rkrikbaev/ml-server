import argparse
import pandas as pd
from pathlib import Path
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_dirpath', type=Path)
    parser.add_argument('output_dirpath', type=Path)
    parser.add_argument('--start_index', type=int, default=0, help='Start index of TI number, inclusive')
    parser.add_argument('--end_index', type=int, default=None, help='End index of TI number, inclusive')
    return parser.parse_args()


def read_ti(filepath):
    df = pd.read_excel(filepath, sheet_name=0, header=2)
    df['name'] = df['TI Name'].iloc[0]
    df['number'] = df['TI Number'].iloc[0]
    df = df.iloc[2:].rename(columns={'TI Name': 'value'}).drop(columns=['TI Number'])
    if df['value'].isna().all():    
        df['value'] = df.iloc[:, -3]
    df['value'] = df['value'].mask(df['value'].lt(-2147483647))
    df['value'] = df['value'].mask(df['value'].gt(2147483647 - 1))
    df.loc[~df['Date'].str.contains(' '), 'Date'] = df.loc[~df['Date'].str.contains(' '), 'Date'] + ' 00:00:00'
    df['dt'] = pd.to_datetime(df['Date'], format='%d.%m.%Y %H:%M:%S')
    df = df.drop(columns=['Date', 'Time'])
    df = df.set_index('dt')
    df = df[['value', 'name', 'number']]
    return df


def main(args):
    args.output_dirpath.mkdir(exist_ok=True, parents=True)

    filepaths = []
    for filepath in sorted(list(args.input_dirpath.glob('*.xlsx'))):
        number = int(filepath.stem.split('_')[-1])
        if number < args.start_index:
            continue
        if args.end_index is not None and number > args.end_index:
            continue
        filepaths.append(filepath)
    
    for ti_filepath in tqdm(filepaths, total=len(filepaths)):
        parquet_filepath = args.output_dirpath / ti_filepath.relative_to(args.input_dirpath).with_suffix('.parquet')
        if parquet_filepath.exists():
            continue
        df = read_ti(ti_filepath)
        df.to_parquet(parquet_filepath)


if __name__ == '__main__':
    args = parse_args()
    main(args)
