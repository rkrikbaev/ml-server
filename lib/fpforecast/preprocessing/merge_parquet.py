import argparse
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_dirpaths', type=Path, nargs='+')
    parser.add_argument('output_dirpath', type=Path)
    return parser.parse_args()


def main(args):
    args.output_dirpath.mkdir(exist_ok=True, parents=True)

    filenames_to_filepaths = defaultdict(list)
    for input_dirpath in args.input_dirpaths:
        for filepath in tqdm(sorted(list(input_dirpath.glob('**/*.parquet')))):
            filenames_to_filepaths[filepath.name].append(filepath)

    for filename, filepaths in filenames_to_filepaths.items():
        dfs = []
        for filepath in filepaths:
            df = pd.read_parquet(filepath)
            dfs.append(df)
        merged_df = pd.concat(dfs).sort_index()
        merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
        output_filepath = args.output_dirpath / filename
        merged_df.to_parquet(output_filepath)
        print(f'Saved merged file to {output_filepath}')


if __name__ == '__main__':
    args = parse_args()
    main(args)
