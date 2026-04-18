from __future__ import annotations

import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any

try:
    from ..policy.politicaDecisao import CASE_ID_COLUMN
except ImportError:
    from src.policy.politicaDecisao import CASE_ID_COLUMN

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_PUBLIC_DIR = ROOT_DIR / "src" / "interface" / "interface-front" / "public"
FRONTEND_GENERATED_DIR = FRONTEND_PUBLIC_DIR / "generated"
FRONTEND_BASE_PATH = FRONTEND_GENERATED_DIR / "base_processos.json"
DECISION_METRICS_PATH = ROOT_DIR / "data" / "policy_artifacts" / "politica_decisao_metricas.json"

DOCUMENT_UI_KEYS = {
    "Contrato": "contrato",
    "Extrato": "extrato",
    "Comprovante de crédito": "comprovanteCredito",
    "Dossiê": "dossie",
    "Demonstrativo de evolução da dívida": "demonstrativoDivida",
    "Laudo referenciado": "laudoReferenciado",
}

UI_KEY_HINTS = {
    "contrato": ("contrato",),
    "extrato": ("extrato",),
    "comprovanteCredito": ("comprovante", "credito"),
    "dossie": ("dossie",),
    "demonstrativoDivida": ("demonstrativo", "evolucao", "divida"),
    "laudoReferenciado": ("laudo", "referenciado"),
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_text_key(text: str) -> str:
    lowered = _strip_accents(text).lower()
    return "".join(char if char.isalnum() else " " for char in lowered).strip()


def _format_brl(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Não informado"
    return f"R$ {number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _safe_probability_to_percent(value: Any) -> int:
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _build_model_monitor_payload() -> dict[str, Any]:
    if not DECISION_METRICS_PATH.exists():
        return {
            "origem": str(DECISION_METRICS_PATH),
            "disponivel": False,
            "metrics": {},
            "feature_importances": {},
        }

    payload = json.loads(DECISION_METRICS_PATH.read_text(encoding="utf-8"))
    return {
        "origem": str(DECISION_METRICS_PATH),
        "disponivel": True,
        "metrics": payload.get("metrics", {}),
        "feature_importances": payload.get("feature_importances", {}),
    }


def _build_subsidy_file_map(source_dir: Path, process_public_dir: Path) -> dict[str, list[dict[str, str]]]:
    subsidy_map = {ui_key: [] for ui_key in UI_KEY_HINTS}
    subsidy_target_dir = process_public_dir / "subsidios"

    if not source_dir.exists():
        return subsidy_map

    for source_file in sorted(path for path in source_dir.iterdir() if path.is_file()):
        target_file = subsidy_target_dir / source_file.name
        _copy_file(source_file, target_file)

        normalized_name = _normalize_text_key(source_file.stem)
        for ui_key, hints in UI_KEY_HINTS.items():
            if all(hint in normalized_name for hint in hints):
                subsidy_map[ui_key].append(
                    {
                        "nome": source_file.name,
                        "url": f"/generated/processos/{process_public_dir.name}/subsidios/{source_file.name}",
                    }
                )
                break

    return subsidy_map


def _copy_process_assets(process_dir: Path, process_id: str, generated_dir: Path) -> dict[str, Any]:
    process_public_dir = generated_dir / "processos" / process_id
    process_public_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "autosPdf": "",
        "contatoJson": "",
        "acordoJson": "",
        "defesaPdf": "",
        "subsidios": {ui_key: [] for ui_key in UI_KEY_HINTS},
    }

    autos_dir = process_dir / "autos"
    for source_file in sorted(path for path in autos_dir.glob("*.pdf")) if autos_dir.exists() else []:
        target_file = process_public_dir / "autos" / source_file.name
        _copy_file(source_file, target_file)
        if not manifest["autosPdf"]:
            manifest["autosPdf"] = f"/generated/processos/{process_id}/autos/{source_file.name}"

    manifest["subsidios"] = _build_subsidy_file_map(process_dir / "subsidios", process_public_dir)

    for filename, manifest_key in [
        ("Contato.json", "contatoJson"),
        ("Acordo.json", "acordoJson"),
        ("Defesa.pdf", "defesaPdf"),
    ]:
        source_file = process_dir / filename
        if source_file.exists():
            target_file = process_public_dir / filename
            _copy_file(source_file, target_file)
            manifest[manifest_key] = f"/generated/processos/{process_id}/{filename}"

    return manifest


def _build_justificativa(item: dict[str, Any]) -> str:
    decision = item["politica_decisao"]
    decision_label = str(decision["decisao"]).upper()
    prob_acordo = _safe_probability_to_percent(decision.get("probabilidade_acordo", 0))
    prob_defesa = _safe_probability_to_percent(decision.get("probabilidade_exito", 0))
    priorizados = decision.get("subsidios_prioritarios", [])
    faltantes = decision.get("subsidios_ausentes_criticos", [])

    if "politica_acordo" in item:
        acordo = item["politica_acordo"]
        parts = [
            (
                f"Recomendação de {decision_label} com {prob_acordo}% de probabilidade de acordo "
                f"e {prob_defesa}% de chance de êxito em defesa."
            ),
            (
                f"Faixa sugerida entre {_format_brl(acordo.get('faixa_negociacao_min'))} "
                f"e {_format_brl(acordo.get('faixa_negociacao_max'))}, com oferta alvo em "
                f"{_format_brl(acordo.get('valor_acordo_sugerido'))}."
            ),
        ]
        if faltantes:
            parts.append(f"Lacunas críticas para defesa: {', '.join(faltantes)}.")
        if priorizados:
            parts.append(f"Subsídios mais relevantes na leitura do caso: {', '.join(priorizados)}.")
        racional = str(acordo.get("racional") or "").strip()
        if racional:
            parts.append(racional)
        return " ".join(parts)

    defesa = item["politica_defesa"]
    parts = [
        f"Recomendação de {decision_label} com {prob_defesa}% de chance de êxito na defesa.",
        str(defesa.get("estrategia") or "").strip(),
    ]
    if priorizados:
        parts.append(f"Subsídios priorizados: {', '.join(priorizados)}.")
    if faltantes:
        parts.append(f"Pontos documentais em atenção: {', '.join(faltantes)}.")
    return " ".join(part for part in parts if part)


def _build_ui_subsidy_flags(case_payload: dict[str, Any]) -> dict[str, int]:
    flags: dict[str, int] = {}
    for policy_name, ui_key in DOCUMENT_UI_KEYS.items():
        try:
            flags[ui_key] = int(case_payload.get(policy_name, 0))
        except (TypeError, ValueError):
            flags[ui_key] = 0
    return flags


def _build_ui_process_payload(item: dict[str, Any], asset_manifest: dict[str, Any]) -> dict[str, Any]:
    case_payload = item["caso"]
    process_id = case_payload[CASE_ID_COLUMN]
    contacts = item["contatos_interface"]
    decision = item["politica_decisao"]
    recommendation = str(decision["decisao"]).upper()

    process_payload: dict[str, Any] = {
        "id": process_id,
        "autor": contacts.get("parte_autora_nome") or "Não informado",
        "valorCausa": _format_brl(case_payload.get("Valor da causa")),
        "chanceAcordo": _safe_probability_to_percent(decision.get("probabilidade_acordo", 0)),
        "chanceDefesa": _safe_probability_to_percent(decision.get("probabilidade_exito", 0)),
        "recomendacao": recommendation,
        "justificativa": _build_justificativa(item),
        "subsidios": _build_ui_subsidy_flags(case_payload),
        "subsidiosPrioritarios": decision.get("subsidios_prioritarios", []),
        "subsidiosAusentesCriticos": decision.get("subsidios_ausentes_criticos", []),
        "contatoOposicao": {
            "nome": contacts.get("advogado_nome") or "Não informado",
            "oab": contacts.get("advogado_oab") or "Não informada",
            "email": contacts.get("advogado_email") or "Sem e-mail",
        },
        "parteAutora": {
            "nome": contacts.get("parte_autora_nome") or "Não informado",
            "email": contacts.get("parte_autora_email") or "Sem e-mail",
        },
        "documentos": asset_manifest,
        "arquivos": {
            "autosPdf": asset_manifest.get("autosPdf", ""),
            "contatoJson": asset_manifest.get("contatoJson", ""),
            "acordoJson": asset_manifest.get("acordoJson", ""),
            "defesaPdf": asset_manifest.get("defesaPdf", ""),
        },
    }

    if "politica_acordo" in item:
        acordo = item["politica_acordo"]
        process_payload.update(
            {
                "valorSugeridoAcordo": _format_brl(acordo.get("valor_acordo_sugerido")),
                "valorCondenacaoPrevisto": _format_brl(acordo.get("valor_condenacao_previsto")),
                "faixaNegociacao": (
                    f"{_format_brl(acordo.get('faixa_negociacao_min'))} a "
                    f"{_format_brl(acordo.get('faixa_negociacao_max'))}"
                ),
                "economiaEstimada": _format_brl(acordo.get("economia_estimada")),
                "detalhesAcordo": acordo,
            }
        )
    else:
        defesa = item["politica_defesa"]
        process_payload.update(
            {
                "valorSugeridoAcordo": "Não recomendado",
                "estrategiaDefesa": defesa.get("estrategia") or "",
                "detalhesDefesa": defesa,
            }
        )

    return process_payload


def sync_interface_payload(
    results_payload: dict[str, Any],
    frontend_public_dir: Path | str = FRONTEND_PUBLIC_DIR,
) -> str:
    frontend_public_dir = Path(frontend_public_dir)
    generated_dir = frontend_public_dir / "generated"

    if generated_dir.exists():
        shutil.rmtree(generated_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)

    ui_base: dict[str, Any] = {}
    for item in results_payload.get("resultados", []):
        process_dir = Path(item["processo_dir"])
        process_id = item["caso"][CASE_ID_COLUMN]
        asset_manifest = _copy_process_assets(process_dir, process_id, generated_dir)
        ui_base[process_id] = _build_ui_process_payload(item, asset_manifest)

    base_path = generated_dir / "base_processos.json"
    base_path.write_text(json.dumps(ui_base, ensure_ascii=False, indent=2), encoding="utf-8")

    monitor_path = generated_dir / "modelo_decisao_metricas.json"
    monitor_path.write_text(
        json.dumps(_build_model_monitor_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(base_path)
