import argparse
import numpy as np
import pandas as pd
from pathlib import Path

# 'Карагандинская область', 'Туркестанская область', 'Костанайская область', 'Восточно-Казахстанская область', 'Мангыстауская область', 'Жетысуская область', 'Павлодарская область', 'Жамбылская область', 'Акмолинский узел', 'Зап. Казахстанская область', 'Актюбинская область', 'Атырауская область', 'Кызылордская область', 'Алматинская область', 'Абайская область', 'Сев.Казахстанская область', 'Кокшетауский узел', 'Улытауская область'
REGION_NAME_MAPPING = {
    '7 Северный МЭС': '/SEVER/@regions/Pavlodar/loss/total',  # 'Павлодарская область',
    '6 Сарбайский МЭС': '/KOSTANAY/@regions/Kostanay/loss/total',  # 'Костанайская область',
    '2 Актюбинский ЭУ': '/AKTOBE/@regions/Aktobe/loss/total',  # 'Актюбинская область',
    '5 Западный МЭС': '/ZAPAD/@regions/ZAPAD/loss/total', #  'Мангыстауская область + Атырауская область'
    '2 Актюбинский МЭС: \nУральский (Зап.-Каз.)  эн / узел': '/AKTOBE/@regions/West Kazakhstan/loss/total',  # 'Зап. Казахстанская область',
    'Усть-Каменогорский э/узел': '/VOSTOK/@regions/East Kazakhstan/loss/total',  # 'Восточно-Казахстанская область',
    'Абайский\xa0 э/узел ': '/VOSTOK/@regions/Abai/loss/total',  # 'Абайская область',
    'Карагандинский э/узел': '/CENTER/@regions/Karaganda/loss/total',  # 'Карагандинская область',
    'Улытауский э/узел  ': '/CENTER/@regions/Ulytau/loss/total',  # 'Улытауская область',
    'Акмолинский\xa0 э/у': '/AKMOLA/@regions/Akmola/loss/total',  # 'Акмолинский узел',
    'Северо-Казахстанский э/узел': '/AKMOLA/@regions/North Kazakhstan/loss/total',  # 'Сев.Казахстанская область',
    'Кокшетауский э\\узел': '/AKMOLA/@regions/Kokshetau/loss/total',  # 'Кокшетауский узел',
    'Алматинский э/у': '/ALMATY/@regions/Almaty/loss/total',  # 'Алматинская область',
    'Жетысукий э/у': '/ALMATY/@regions/Zhetysu/loss/total',  # 'Жетысуская область',
    'Туркестанская\xa0 обл.': '/UZHNIY/@regions/Turkestan/loss/total',  # 'Туркестанская область',
    'Жамбылская обл.': '/UZHNIY/@regions/Zhambyl/loss/total',  # 'Жамбылская область',
    'Кзыл-Ординская обл.': '/UZHNIY/@regions/KysylOrda/loss/total',  # 'Кызылордская область',
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'input_dirpath',
        type=Path,
        help='Path to input directory'
    )
    parser.add_argument(
        'output_dirpath',
        type=Path,
        help='Path to output directory'
    )
    args = parser.parse_args()
    return args


def preprocess_losses(df: pd.DataFrame, start_time_sheet, type_) -> pd.DataFrame:
    df = df.iloc[26:, 2:28]
    hours = pd.to_datetime(df.columns[2:].str[:2], format='%H')
    df.columns = ['node_name', 'type'] + (start_time_sheet + (hours - hours[0])).to_list()
    df['node_name'] = df['node_name'].infer_objects(copy=False).ffill()
    df = df[df['node_name'].isin(REGION_NAME_MAPPING.keys()) & (df['type'] == type_)]
    # print(df['node_name'].unique())
    df['node_name'] = df['node_name'].map(REGION_NAME_MAPPING)
    df = df.groupby('node_name').sum().reset_index()
    # df['node_name'] = df['node_name'].str.split().apply(lambda x: ' '.join(x[1:]))
    df = df.drop(columns=['type'])
    df = df.set_index('node_name').T
    df = df.sort_index()
    df.loc[:, df.columns[1:]] = np.where(
        (df[df.columns[1:]] < 0).values,
        np.nan,
        df[df.columns[1:]].values
    )
    df = df.infer_objects(copy=False).ffill()
    assert set(df.columns) == set(REGION_NAME_MAPPING.values()), f'{set(df.columns) ^ set(REGION_NAME_MAPPING.values())}'

    return df


def read_data(file_infos):
    # Read data
    df_facts, df_plans = [], []
    for file_info in file_infos:
        for sheet_name_int in range(1, 32):
            sheet_name = str(sheet_name_int)

            # Check if sheet exists
            excel_file = pd.ExcelFile(file_info['filepath'], engine='pyxlsb')
            if sheet_name not in excel_file.sheet_names:
                continue

            start_time_sheet = file_info['start_time'] + pd.to_timedelta(sheet_name_int - 1, unit='D')
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=4)

            df_fact = preprocess_losses(df.copy(), start_time_sheet, 'факт')
            df_facts.append(df_fact)

            df_plan = preprocess_losses(df.copy(), start_time_sheet, 'план')
            df_plans.append(df_plan)
    df_fact = pd.concat(df_facts)
    df_plan = pd.concat(df_plans)

    # Drop duplicates
    mask_fact = ~df_fact.index.duplicated(keep='last')
    df_fact = df_fact[mask_fact]
    mask_plan = ~df_plan.index.duplicated(keep='last')
    df_plan = df_plan[mask_plan]

    # Check consistency
    assert df_fact.index.equals(df_plan.index)
    assert (df_fact.index.diff().dropna() == pd.Timedelta(hours=1)).all(), \
        f'{df_fact.index.diff().unique()}'

    # Remove last 24 hours
    df_fact = df_fact.iloc[:-24]
    df_plan = df_plan.iloc[:-24]

    # Reset index to 'ds' column
    df_fact = df_fact.reset_index().rename(columns={'index': 'ds'})

    return df_fact, df_plan


def main(args):
    file_infos = [
        {
            'filepath': args.input_dirpath / '2024' / '00 МЭС Прил  Прогноз потерь формулы за ФЕВРАЛЬ.xlsb',
            'start_time': pd.to_datetime('01-02-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / '00 МЭС Прил  Прогноз потерь формулы за МАРТ.xlsb',
            'start_time': pd.to_datetime('01-03-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / '00 МЭС Прил  Прогноз потерь формулы за АПРЕЛЬ.xlsb',
            'start_time': pd.to_datetime('01-04-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Анализ потерь план-факт формулы май 2024г.xlsb',
            'start_time': pd.to_datetime('01-05-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Анализ потерь план-факт формулы 30 дней июня.xlsb',
            'start_time': pd.to_datetime('01-06-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Анализ потерь план-факт за 31 день ИЮЛЯ.xlsb',
            'start_time': pd.to_datetime('01-07-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Потери АВГУСТ.xlsb',
            'start_time': pd.to_datetime('01-08-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'факт СЕНТЯБРЬ.xlsb',
            'start_time': pd.to_datetime('01-09-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Анализ потерь план-факт формулы октябрь.xlsb',
            'start_time': pd.to_datetime('01-10-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Ноябрь Анализ потерь план-факт формулы НУЛЕВАЯ.xlsb',
            'start_time': pd.to_datetime('01-11-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2024' / 'Декабрь Анализ потерь план-факт.xlsb',
            'start_time': pd.to_datetime('01-12-2024', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / '00 МЭС Прил  Прогноз потерь формулы за ЯНВАРЬ.xlsb',
            'start_time': pd.to_datetime('01-01-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь январь 2025.xlsb',
            'start_time': pd.to_datetime('01-01-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь февраль 2025.xlsb',
            'start_time': pd.to_datetime('01-02-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь март 2025.xlsb',
            'start_time': pd.to_datetime('01-03-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь апрель 2025.xlsb',
            'start_time': pd.to_datetime('01-04-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь мая 2025.xlsb',
            'start_time': pd.to_datetime('01-05-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь июнь 2025.xlsb',
            'start_time': pd.to_datetime('01-06-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь июль 2025.xlsb',
            'start_time': pd.to_datetime('01-07-2025', format='%d-%m-%Y')
        },
        {
            'filepath': args.input_dirpath / '2025' / 'Анализ потерь август 2025.xlsb',
            'start_time': pd.to_datetime('01-08-2025', format='%d-%m-%Y')
        },
    ]

    df, _ = read_data(file_infos)

    # Save to structure
    for col in df.columns.difference(['ds']):
        region_path = args.output_dirpath / Path(col).relative_to('/')
        region_path.mkdir(parents=True, exist_ok=True)

        output_filepath = region_path / 'values.parquet'
        df_region = df[['ds', col]] \
            .rename(columns={col: 'value', 'ds': 'dt'}) \
            .set_index('dt')
        df_region.to_parquet(output_filepath)
        print(f'Saved {output_filepath}')


if __name__ == '__main__':
    args = parse_args()
    main(args)
