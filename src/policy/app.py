from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .politicaAcordo import PoliticaAcordo
    from .politicaDecisao import CASE_ID_COLUMN, DOCUMENT_COLUMNS, PoliticaDecisao, normalize_case
    from .politicaDefesa import PoliticaDefesa
    from ..utils.extrator_contatos import ExtratorContatoAutos
    from ..utils.sincronizador_interface import sync_interface_payload
except ImportError:
    CURRENT_FILE = Path(__file__).resolve()
    PROJECT_ROOT = CURRENT_FILE.parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from politicaAcordo import PoliticaAcordo
    from politicaDecisao import CASE_ID_COLUMN, DOCUMENT_COLUMNS, PoliticaDecisao, normalize_case
    from politicaDefesa import PoliticaDefesa
    from src.utils.extrator_contatos import ExtratorContatoAutos
    from src.utils.sincronizador_interface import sync_interface_payload

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = ROOT_DIR / "data" / "data.csv"
DEFAULT_PROCESSOS_DIR = ROOT_DIR / "data" / "processos_exemplo"
DEFAULT_FRONTEND_PUBLIC_DIR = ROOT_DIR / "src" / "interface" / "interface-front" / "public"


def _write_agreement_json(
    process_dir: Path,
    case_payload: dict[str, Any],
    decision_result: dict[str, Any],
    agreement_result: dict[str, Any],
) -> str:
    output_path = process_dir / "Acordo.json"
    payload = {
        "processo_id": case_payload[CASE_ID_COLUMN],
        "tipo_resultado": "acordo",
        "caso": case_payload,
        "politica_decisao": {
            "decisao": decision_result["decisao"],
            "probabilidade_exito": decision_result["probabilidade_exito"],
            "probabilidade_acordo": decision_result["probabilidade_acordo"],
            "subsidios_prioritarios": decision_result["subsidios_prioritarios"],
            "subsidios_ausentes_criticos": decision_result["subsidios_ausentes_criticos"],
        },
        "politica_acordo": agreement_result,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)

def _load_cases_from_csv(csv_path: Path) -> dict[str, dict[str, Any]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo de casos não encontrado em {csv_path}")

    df = pd.read_csv(csv_path, thousands=".", decimal=",")
    if CASE_ID_COLUMN not in df.columns:
        raise ValueError(f"O CSV precisa conter a coluna '{CASE_ID_COLUMN}'.")

    df[CASE_ID_COLUMN] = df[CASE_ID_COLUMN].astype(str)
    indexed_df = df.drop_duplicates(subset=[CASE_ID_COLUMN]).set_index(CASE_ID_COLUMN)

    cases: dict[str, dict[str, Any]] = {}
    for process_id, row in indexed_df.iterrows():
        row_dict = row.to_dict()
        row_dict[CASE_ID_COLUMN] = process_id
        cases[process_id] = row_dict

    return cases


def _list_process_dirs(processos_root: Path, processo_id: str | None = None) -> list[Path]:
    if not processos_root.exists():
        raise FileNotFoundError(f"Diretório de processos não encontrado em {processos_root}")

    process_dirs = [path for path in sorted(processos_root.iterdir()) if path.is_dir()]
    if processo_id is None:
        if not process_dirs:
            raise FileNotFoundError(f"Nenhum processo encontrado em {processos_root}")
        return process_dirs

    selected_process = processos_root / processo_id
    if not selected_process.exists():
        raise FileNotFoundError(f"Processo {processo_id} não encontrado em {processos_root}")
    return [selected_process]


def _build_case_payloads(
    csv_path: Path,
    processos_root: Path,
    processo_id: str | None = None,
) -> list[dict[str, Any]]:
    cases_by_id = _load_cases_from_csv(csv_path)
    process_dirs = _list_process_dirs(processos_root, processo_id)

    payloads: list[dict[str, Any]] = []
    for process_dir in process_dirs:
        current_process_id = process_dir.name
        case = cases_by_id.get(current_process_id)
        if case is None:
            raise KeyError(
                f"Processo {current_process_id} não encontrado em {csv_path}. "
                "O data.csv deve conter uma linha para cada diretório em data/processos_exemplo."
            )

        payloads.append(
            {
                "processo_id": current_process_id,
                "processo_dir": process_dir,
                "caso": normalize_case(case),
            }
        )

    return payloads


def run(args: argparse.Namespace) -> dict[str, Any]:
    csv_path = Path(args.csv_path)
    processos_root = Path(args.processos_dir)
    case_payloads = _build_case_payloads(
        csv_path=csv_path,
        processos_root=processos_root,
        processo_id=args.processo_id,
    )

    politica_decisao = PoliticaDecisao()
    politica_decisao.ensure_trained(force_retrain=args.force_retrain)

    politica_acordo = PoliticaAcordo()
    politica_acordo.ensure_trained(force_retrain=args.force_retrain)

    politica_defesa = PoliticaDefesa()
    extrator_contatos = ExtratorContatoAutos()
    results: list[dict[str, Any]] = []

    for item in case_payloads:
        case_payload = item["caso"]
        process_dir = item["processo_dir"]
        contact_result = extrator_contatos.extract_and_persist(process_dir, case_payload[CASE_ID_COLUMN])
        decision_result = politica_decisao.predict_case(case_payload)
        result: dict[str, Any] = {
            "caso": case_payload,
            "processo_dir": str(process_dir),
            "contatos_interface": contact_result.to_dict(),
            "politica_decisao": decision_result.to_dict(),
        }

        if decision_result.decisao == "acordo":
            acordo = politica_acordo.recommend(case_payload, decision_result)
            agreement_payload = acordo.to_dict()
            agreement_payload["arquivo_acordo_json"] = _write_agreement_json(
                process_dir=process_dir,
                case_payload=case_payload,
                decision_result=decision_result.to_dict(),
                agreement_result=agreement_payload,
            )
            result["politica_acordo"] = agreement_payload
        else:
            defesa = politica_defesa.build_defense(
                case_data=case_payload,
                decision_result=decision_result,
                processo_dir=process_dir,
            )
            result["politica_defesa"] = defesa.to_dict()

        results.append(result)

    payload = {
        "total_processos": len(results),
        "csv_path": str(csv_path),
        "processos_dir": str(processos_root),
        "resultados": results,
    }
    if not args.skip_interface_sync and Path(args.frontend_public_dir).exists():
        payload["interface_sync"] = {
            "base_processos_json": sync_interface_payload(
                payload,
                frontend_public_dir=args.frontend_public_dir,
            )
        }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orquestrador da politica de acordos do Banco UFMG."
    )
    parser.add_argument(
        "--csv-path",
        default=str(DEFAULT_CASES_PATH),
        help="Arquivo CSV com os dados estruturados de todos os processos exemplo.",
    )
    parser.add_argument(
        "--processos-dir",
        default=str(DEFAULT_PROCESSOS_DIR),
        help="Diretório raiz com os processos exemplo nomeados pelo número do processo.",
    )
    parser.add_argument(
        "--processo-id",
        default=None,
        help="Número de um processo específico para rodar isoladamente.",
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
    parser.add_argument(
        "--frontend-public-dir",
        default=str(DEFAULT_FRONTEND_PUBLIC_DIR),
        help="Diretório public do frontend para sincronizar os dados consumidos pela interface.",
    )
    parser.add_argument(
        "--skip-interface-sync",
        action="store_true",
        help="Não exporta a base consolidada para a interface.",
    )
    return parser


def _format_single_result(result: dict[str, Any]) -> str:
    decision = result["politica_decisao"]
    lines = [
        f"Processo: {decision['processo_id']}",
        f"Decisão recomendada: {decision['decisao']}",
        f"Probabilidade de êxito: {decision['probabilidade_exito']:.2%}",
        f"Subsídios prioritários: {', '.join(decision['subsidios_prioritarios']) or 'nenhum'}",
        f"Contato extraído: {result['contatos_interface']['arquivo_contato_json']}",
    ]

    if "politica_acordo" in result:
        acordo = result["politica_acordo"]
        lines.extend(
            [
                f"Valor da causa original: R$ {acordo['valor_causa_original']:.2f}",
                f"Valor previsto de condenação: R$ {acordo['valor_condenacao_previsto']:.2f}",
                f"Oferta sugerida: R$ {acordo['valor_acordo_sugerido']:.2f}",
                f"Faixa de negociação: R$ {acordo['faixa_negociacao_min']:.2f} a R$ {acordo['faixa_negociacao_max']:.2f}",
                f"Economia estimada: R$ {acordo['economia_estimada']:.2f}",
                f"JSON gerado: {acordo['arquivo_acordo_json']}",
            ]
        )
    else:
        defesa = result["politica_defesa"]
        lines.extend(
            [
                f"Origem da minuta: {defesa['origem']}",
                f"PDF gerado: {defesa['arquivo_defesa_pdf']}",
                "Minuta inicial:",
                defesa["minuta_defesa"],
            ]
        )

    return "\n".join(lines)


def _format_human_summary(result: dict[str, Any]) -> str:
    lines = [
        f"Total de processos avaliados: {result['total_processos']}",
        f"CSV utilizado: {result['csv_path']}",
        f"Diretório de processos: {result['processos_dir']}",
    ]
    if "interface_sync" in result:
        lines.append(f"Base sincronizada para a interface: {result['interface_sync']['base_processos_json']}")
    for item in result["resultados"]:
        lines.append("")
        lines.append(_format_single_result(item))
    return "\n".join(lines)


def main() -> None:
    parser = build_parser()
    try:
        args = parser.parse_args()
        result = run(args)
    except Exception as error:
        print(f"Erro ao executar a política: {error}", file=sys.stderr)
        raise

    if args.pretty:
        print(_format_human_summary(result))
        print("\nJSON:")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
