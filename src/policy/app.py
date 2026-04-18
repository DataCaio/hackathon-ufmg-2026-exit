from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .politicaAcordo import PoliticaAcordo
    from .politicaDecisao import CASE_ID_COLUMN, DOCUMENT_COLUMNS, PoliticaDecisao, normalize_case
    from .politicaDefesa import PoliticaDefesa
except ImportError:
    from politicaAcordo import PoliticaAcordo
    from politicaDecisao import CASE_ID_COLUMN, DOCUMENT_COLUMNS, PoliticaDecisao, normalize_case
    from politicaDefesa import PoliticaDefesa

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = ROOT_DIR / "data" / "data.csv"
DEFAULT_PROCESSOS_DIR = ROOT_DIR / "data" / "processos_exemplo"


def _load_case_from_csv(csv_path: Path, row_index: int) -> dict[str, Any]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo de casos não encontrado em {csv_path}")

    df = pd.read_csv(csv_path, thousands=".", decimal=",")
    if row_index >= len(df):
        raise IndexError(
            f"row_index={row_index} fora do intervalo. A base possui {len(df)} linhas."
        )

    row = df.iloc[row_index].to_dict()
    row[CASE_ID_COLUMN] = str(row.get(CASE_ID_COLUMN) or f"caso_csv_{row_index + 1}")
    return row


def _discover_process_dir(user_process_dir: str | None) -> Path | None:
    if user_process_dir:
        path = Path(user_process_dir)
        return path if path.exists() else None

    if not DEFAULT_PROCESSOS_DIR.exists():
        return None

    candidates = [path for path in sorted(DEFAULT_PROCESSOS_DIR.iterdir()) if path.is_dir()]
    return candidates[0] if candidates else None


def _infer_document_flags(process_dir: Path | None) -> dict[str, int]:
    if process_dir is None:
        return {column: 0 for column in DOCUMENT_COLUMNS}

    search_root = process_dir / "subsidios"
    if not search_root.exists():
        search_root = process_dir

    flags = {column: 0 for column in DOCUMENT_COLUMNS}
    for file_path in search_root.rglob("*"):
        if not file_path.is_file():
            continue
        normalized_name = file_path.name.lower()
        for column in DOCUMENT_COLUMNS:
            tokens = (
                column.lower()
                .replace("ê", "e")
                .replace("é", "e")
                .replace("í", "i")
                .replace("ç", "c")
                .split()
            )
            if any(token in normalized_name for token in tokens):
                flags[column] = 1
    return flags


def _load_metadata_from_process(process_dir: Path | None) -> dict[str, Any]:
    if process_dir is None:
        return {}

    metadata_candidates = [
        process_dir / "metadata.json",
        process_dir / "caso.json",
        process_dir / "dados_caso.json",
    ]
    for candidate in metadata_candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def _build_case_payload(
    csv_path: Path,
    row_index: int,
    process_dir: Path | None,
) -> dict[str, Any]:
    case: dict[str, Any] = {}
    if csv_path.exists():
        case.update(_load_case_from_csv(csv_path, row_index))

    case.update(_load_metadata_from_process(process_dir))

    if process_dir is not None:
        case[CASE_ID_COLUMN] = str(case.get(CASE_ID_COLUMN) or process_dir.name)
        case.update(_infer_document_flags(process_dir))
    elif CASE_ID_COLUMN not in case:
        case[CASE_ID_COLUMN] = f"caso_csv_{row_index + 1}"

    return normalize_case(case)


def run(args: argparse.Namespace) -> dict[str, Any]:
    csv_path = Path(args.csv_path)
    process_dir = _discover_process_dir(args.processo_dir)
    case_payload = _build_case_payload(
        csv_path=csv_path,
        row_index=args.row_index,
        process_dir=process_dir,
    )

    politica_decisao = PoliticaDecisao()
    politica_decisao.ensure_trained(force_retrain=args.force_retrain)

    politica_acordo = PoliticaAcordo()
    politica_acordo.ensure_trained(force_retrain=args.force_retrain)

    politica_defesa = PoliticaDefesa()

    decision_result = politica_decisao.predict_case(case_payload)
    result: dict[str, Any] = {
        "caso": case_payload,
        "processo_dir": str(process_dir) if process_dir else None,
        "politica_decisao": decision_result.to_dict(),
    }

    if decision_result.decisao == "acordo":
        acordo = politica_acordo.recommend(case_payload, decision_result)
        result["politica_acordo"] = acordo.to_dict()
    else:
        defesa = politica_defesa.build_defense(
            case_data=case_payload,
            decision_result=decision_result,
            processo_dir=process_dir,
        )
        result["politica_defesa"] = defesa.to_dict()

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orquestrador da politica de acordos do Banco UFMG."
    )
    parser.add_argument(
        "--csv-path",
        default=str(DEFAULT_CASES_PATH),
        help="Arquivo CSV com casos estruturados para inferência.",
    )
    parser.add_argument(
        "--row-index",
        type=int,
        default=0,
        help="Índice da linha do CSV a ser usada como caso de entrada.",
    )
    parser.add_argument(
        "--processo-dir",
        default=None,
        help=(
            "Diretório de um processo exemplo com subpastas autos/ e subsidios/. "
            "Se omitido, tenta usar o primeiro processo em data/processos_exemplo/."
        ),
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Imprime um resumo humanizado além do JSON.",
    )
    parser.add_argument(
        "--force-retrain",
        action="store_true",
        help="Reprocessa os modelos de decisão e acordo antes da inferência.",
    )
    return parser


def _format_human_summary(result: dict[str, Any]) -> str:
    decision = result["politica_decisao"]
    lines = [
        f"Processo: {decision['processo_id']}",
        f"Decisão recomendada: {decision['decisao']}",
        f"Probabilidade de êxito: {decision['probabilidade_exito']:.2%}",
        f"Subsídios prioritários: {', '.join(decision['subsidios_prioritarios']) or 'nenhum'}",
    ]

    if "politica_acordo" in result:
        acordo = result["politica_acordo"]
        lines.extend(
            [
                f"Valor previsto de condenação: R$ {acordo['valor_condenacao_previsto']:.2f}",
                f"Oferta sugerida: R$ {acordo['valor_acordo_sugerido']:.2f}",
                f"Faixa de negociação: R$ {acordo['faixa_negociacao_min']:.2f} a R$ {acordo['faixa_negociacao_max']:.2f}",
            ]
        )
    else:
        defesa = result["politica_defesa"]
        lines.extend(
            [
                f"Origem da minuta: {defesa['origem']}",
                "Minuta inicial:",
                defesa["minuta_defesa"],
            ]
        )

    return "\n".join(lines)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)

    if args.pretty:
        print(_format_human_summary(result))
        print("\nJSON:")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
