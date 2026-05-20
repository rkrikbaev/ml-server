import argparse
import shutil
import pandas as pd
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description='Convert OIK TI parquet files to structure directory.')
    parser.add_argument('ti_parquet_dirpath', type=Path, help='Path to the directory containing TI parquet files.')
    parser.add_argument('structure_dirpath', type=Path, help='Path to the structure directory to save converted files.')
    parser.add_argument('mapping_file', type=Path, help='Path to the CSV file mapping model paths to OIK NDC TI numbers.')
    return parser.parse_args()


def main(args):
    df_mapping = pd.read_csv(args.mapping_file)

    def convert(row, col):
        if col not in row or pd.isna(row[col]):
            return None

        model_path = Path(row['model_path'])
        oik_ndc_ti_number = int(row[col])

        source_file = args.ti_parquet_dirpath / f'ТИ_{oik_ndc_ti_number}.parquet'
        target_dir = args.structure_dirpath / model_path.relative_to('/')
        target_file = target_dir / f'{"values" if col == "oik_ndc_ti_number" else "plan"}.parquet'

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(source_file, target_file)
        print(f'Copied {source_file} to {target_file} as part of column {col}')

    for _, row in df_mapping.iterrows():
        convert(row, 'oik_ndc_ti_number')
        convert(row, 'oik_ndc_plan_ti_number')

if __name__ == '__main__':
    args = parse_args()
    main(args)
