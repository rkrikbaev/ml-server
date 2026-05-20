WEATHER_FORECAST_COLS = [
    'temperature',
    'wind_speed',
    'humidity',
]

FREQ_TO_PROPHET_PARAMS = {
    'h': {
        'seasonality_mode': 'additive',
        'yearly_seasonality': True,
        'weekly_seasonality': True,
        'daily_seasonality': True,
        'growth': 'flat',
    },
    'D': {
        'seasonality_mode': 'additive',
        'yearly_seasonality': True,
        'weekly_seasonality': True,
        'daily_seasonality': False,
        'growth': 'flat',
    },
    'M': {
        'seasonality_mode': 'additive',
        'yearly_seasonality': True,
        'weekly_seasonality': False,
        'daily_seasonality': False,
        'growth': 'flat',
    }
}

COD_EN_TO_MES = {
    '01': 'ALMATY',
    '02': 'VOSTOK',
    '03': 'ZAPAD',
    '04': 'AKTOBE',
    '05': 'CENTER',
    '06': 'KOSTANAY',
    '07': 'SEVER',
    '08': 'AKMOLA',
    '10': 'UZHNIY',
    '20': 'NDC',
}

KOD_OBLASTI_TO_PATH = {
    1: '/ALMATY/@regions/Almaty',
    2: '/VOSTOK/@regions/East Kazakhstan',
    3: '/ZAPAD/@regions/Atyrau',
    4: '/ZAPAD/@regions/Mangystau',
    5: '/AKTOBE/@regions/Aktobe',
    6: '/CENTER/@regions/Karaganda',
    7: '/KOSTANAY/@regions/Kostanay',
    8: '/SEVER/@regions/Pavlodar',
    9: '/AKMOLA/@regions/North Kazakhstan',
    10: '/AKMOLA/@regions/Akmola',
    11: '/UZHNIY/@regions/Jambyl',
    12: '/UZHNIY/@regions/KysylOrda',
    13: '/UZHNIY/@regions/Turkestan',
    14: '/AKTOBE/@regions/West Kazakhstan',
}

ALLOWED_LAT_LON_BOUNDS = {
    'lat_min': 40.66667,
    'lat_max': 54.91261,
    'lon_min': 46.84705,
    'lon_max': 84.87144,
}
DEFAULT_LAT = 43.256700
DEFAULT_LON = 76.928600

UTC_SHIFT_HOURS = 5  # Kazakhstan time is UTC+5