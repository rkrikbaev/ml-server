import argparse
import shutil
from pathlib import Path


def parase_args():
    parser = argparse.ArgumentParser(
        description="Rebuild longterm losses structure"
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Input directory containing model.json files",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Output directory to save rebuilt structures",
    )
    return parser.parse_args()


def map_old_path_to_new_path(old_path: Path):
    # structured/Vostocnye_MES_220_kV_i_nije_Holostoj_hod_v_transformatorah/model.json
    # structured/Vostocnye_MES_220_kV_i_nije_Korona/model.json
    # structured/Vostocnye_MES_220_kV_i_nije_Nagruzocnye_v_liniah/model.json
    # structured/Vostocnye_MES_220_kV_i_nije_Nagruzocnye_v_transformatorah/model.json
    # structured/Vostocnye_MES_220_kV_i_nije_SN_PS/model.json
    # structured/Vostocnye_MES_220_kV_i_nije_VSEGO/model.json
    # structured/Vostocnye_MES_500_kV_Holostoj_hod_v_transformatorah/model.json
    # structured/Vostocnye_MES_500_kV_Korona/model.json
    # structured/Vostocnye_MES_500_kV_Nagruzocnye_v_liniah/model.json
    # structured/Vostocnye_MES_500_kV_Nagruzocnye_v_transformatorah/model.json
    # structured/Vostocnye_MES_500_kV_Reaktory/model.json
    # structured/Vostocnye_MES_500_kV_SN_PS/model.json
    # structured/Vostocnye_MES_500_kV_VSEGO/model.json

    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/total
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/lines_load
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/corona
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/transformers_load
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/transformers_idle
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/reactors
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/500kV/own
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/total
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/lines_load
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/corona
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/transformers_load
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/transformers_idle
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/reactors
    # prophet/elect/M/VOSTOK/@regions/VOSTOK/loss/le220kV/own

    MES_MAP = {
        'AO_KEGOC': 'KEGOC',
        'Akmolinskie_MES': 'AKMOLA',
        'Aktubinskie_MES': 'AKTOBE',
        'Almatinskie_MES': 'ALMATY',
        'Sarbajskie_MES': 'KOSTANAY',
        'Severnye_MES': 'SEVER',
        'Ujnye_MES': 'UZHNIY',
        'Vostocnye_MES': 'VOSTOK',
        'Zapadnye_MES': 'ZAPAD',
        'Zentral_nye_MES': 'CENTER',
    }

    VC_MAP = {
        '220_kV_i_nije': 'le220kV',
        '500_kV': '500kV',
    }

    TYPE_MAP = {
        'VSEGO': 'total',
        'Nagruzocnye_v_liniah': 'lines_load',
        'Korona': 'corona',
        'Nagruzocnye_v_transformatorah': 'transformers_load',
        'Holostoj_hod_v_transformatorah': 'transformers_idle',
        'Reaktory': 'reactors',
        'SN_PS': 'own',
    }

    old_path_str = str(old_path)

    mes, vc, loss_type = None, None, None

    for mes_key, mes_value in MES_MAP.items():
        if mes_key in old_path_str:
            mes = mes_value
            break

    if 'Poteri' in old_path_str:
        vc, loss_type = 'total', 'total'
    else:
        for vc_key, vc_value in VC_MAP.items():
            if vc_key in old_path_str:
                vc = vc_value
                break

        for type_key, type_value in TYPE_MAP.items():
            if type_key in old_path_str:
                loss_type = type_value
                break

    assert mes is not None, f"Unknown MES in path: {old_path_str}"
    assert vc is not None, f"Unknown VC in path: {old_path_str}"
    assert loss_type is not None, f"Unknown loss type in path: {old_path_str}"

    new_path = Path(
        'prophet',
        'elect',
        'M',
        mes,
        '@regions',
        mes,
        'loss',
        vc,
        loss_type,
    )

    return new_path


def main(args):
    filepaths = sorted(list(args.input_dir.glob('**/model.json')))
    for filepath in filepaths:
        old_rel_dirpath = filepath.relative_to(args.input_dir).parent
        new_dirpath = args.output_dir / map_old_path_to_new_path(old_rel_dirpath)

        new_dirpath.mkdir(parents=True, exist_ok=True)
        new_filepath = new_dirpath / 'model.json'

        shutil.copy2(filepath, new_filepath)
        print(f"Copied {filepath} to {new_filepath}")


if __name__ == "__main__":
    args = parase_args()
    main(args)
