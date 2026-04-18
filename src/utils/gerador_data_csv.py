from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PROCESSOS_DIR = ROOT_DIR / "data" / "processos_exemplo"
DEFAULT_OUTPUT_CSV = ROOT_DIR / "data" / "data.csv"
DEFAULT_MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.4")
DEFAULT_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")

CSV_COLUMNS = [
    "Número do processo",
    "UF",
    "Assunto",
    "Sub-assunto",
    "Resultado macro",
    "Resultado micro",
    "Valor da causa",
    "Valor da condenação/indenização",
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
    "Dossiê",
    "Demonstrativo de evolução da dívida",
    "Laudo referenciado",
]

DOCUMENT_PATTERNS = {
    "Contrato": ("contrato",),
    "Extrato": ("extrato",),
    "Comprovante de crédito": ("comprovante", "credito"),
    "Dossiê": ("dossie",),
    "Demonstrativo de evolução da dívida": ("demonstrativo", "evolucao", "divida"),
    "Laudo referenciado": ("laudo", "referenciado"),
}

PROCESS_NUMBER_REGEX = re.compile(r"Processo\s*n[ºo]\s*([\d.\-]+)", flags=re.IGNORECASE)
UF_REGEX = re.compile(r"Comarca de .*?/([A-Z]{2})", flags=re.IGNORECASE)
CAUSE_VALUE_REGEX = re.compile(
    r"D[aá]-?se\s+[aà]\s+causa\s+o\s+valor\s+de\s+R\$\s*([\d.]+,\d{2})",
    flags=re.IGNORECASE,
)


@dataclass
class LinhaDataCsv:
    numero_processo: str
    uf: str
    assunto: str
    sub_assunto: str
    valor_causa: str
    contrato: int
    extrato: int
    comprovante_credito: int
    dossie: int
    demonstrativo_evolucao_divida: int
    laudo_referenciado: int

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "Número do processo": self.numero_processo,
            "UF": self.uf,
            "Assunto": self.assunto,
            "Sub-assunto": self.sub_assunto,
            "Resultado macro": pd.NA,
            "Resultado micro": pd.NA,
            "Valor da causa": self.valor_causa,
            "Valor da condenação/indenização": pd.NA,
            "Contrato": self.contrato,
            "Extrato": self.extrato,
            "Comprovante de crédito": self.comprovante_credito,
            "Dossiê": self.dossie,
            "Demonstrativo de evolução da dívida": self.demonstrativo_evolucao_divida,
            "Laudo referenciado": self.laudo_referenciado,
        }


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_text_key(text: str) -> str:
    lowered = _strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _find_autos_pdf(processo_dir: Path) -> Path:
    autos_dir = processo_dir / "autos"
    if not autos_dir.exists():
        raise FileNotFoundError(f"Pasta de autos não encontrada em {autos_dir}")

    pdfs = sorted(autos_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"Nenhum PDF de autos encontrado em {autos_dir}")
    return pdfs[0]


def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("O binário 'pdftotext' é necessário para extrair os autos.") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Falha ao extrair texto do PDF {pdf_path.name}.") from error

    return result.stdout.strip()


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("A resposta da OpenAI para o data.csv não veio em JSON válido.")
        return json.loads(candidate[start : end + 1])


def _format_brl_from_float(value: float) -> str:
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _coerce_brl_value(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip().replace("R$", "").strip()
    if not text:
        return ""

    text = text.replace(" ", "")
    if re.fullmatch(r"[\d.]+,\d{2}", text):
        return text
    if re.fullmatch(r"[\d,]+\.\d{2}", text):
        number = float(text.replace(",", ""))
        return _format_brl_from_float(number)

    digits = re.sub(r"[^\d,.-]", "", text)
    if not digits:
        return ""

    if "," in digits:
        normalized = digits.replace(".", "").replace(",", ".")
    else:
        normalized = digits

    try:
        return _format_brl_from_float(float(normalized))
    except ValueError:
        return ""


def _heuristic_hints(full_text: str, processo_dir: Path) -> dict[str, str]:
    process_match = PROCESS_NUMBER_REGEX.search(full_text)
    uf_match = UF_REGEX.search(full_text)
    value_match = CAUSE_VALUE_REGEX.search(full_text)
    assunto_hint = ""
    normalized_text = _normalize_text_key(full_text)
    if "nao reconhece" in normalized_text or "inexistencia de debito" in normalized_text:
        assunto_hint = "Não reconhece operação"

    return {
        "numero_processo_hint": process_match.group(1) if process_match else processo_dir.name,
        "uf_hint": uf_match.group(1).upper() if uf_match else "",
        "assunto_hint": assunto_hint,
        "sub_assunto_hint": "Golpe" if _looks_like_golpe(full_text) else "Genérico",
        "valor_causa_hint": value_match.group(1) if value_match else "",
    }


def _build_focus_text(full_text: str) -> str:
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    focus_lines: list[str] = []
    keywords = [
        "processo",
        "comarca",
        "acao",
        "inexistencia",
        "debito",
        "valor",
        "causa",
        "emprestimo",
        "consignado",
        "nao reconhece",
    ]

    for line in lines[:120]:
        focus_lines.append(line)

    for line in lines:
        normalized_line = _normalize_text_key(line)
        if any(keyword in normalized_line for keyword in keywords):
            focus_lines.append(line)

    compact = []
    seen: set[str] = set()
    for line in focus_lines:
        if line in seen:
            continue
        compact.append(line)
        seen.add(line)

    return "\n".join(compact)[:16000]


def _default_assunto(full_text: str) -> str:
    normalized_text = _normalize_text_key(full_text)
    if "nao reconhece" in normalized_text or "inexistencia de debito" in normalized_text:
        return "Não reconhece operação"
    return "Genérico"


def _looks_like_golpe(full_text: str) -> bool:
    normalized_text = _normalize_text_key(full_text)
    golpe_markers = [
        "golpe",
        "fraude",
        "fraudulenta",
        "fraudulento",
        "contratacao fraudulenta",
        "uso indevido de sua identidade",
        "terceiro em nome",
    ]
    return any(marker in normalized_text for marker in golpe_markers)


def _normalize_sub_assunto(raw_value: Any, full_text: str) -> str:
    normalized_value = _normalize_text_key(str(raw_value or ""))
    if "golpe" in normalized_value:
        return "Golpe"
    if _looks_like_golpe(full_text):
        return "Golpe"
    return "Genérico"


def _normalize_metadata(
    payload: dict[str, Any],
    full_text: str,
    processo_dir: Path,
) -> dict[str, str]:
    hints = _heuristic_hints(full_text, processo_dir)
    numero_processo = str(payload.get("Número do processo") or hints["numero_processo_hint"]).strip()
    uf = str(payload.get("UF") or hints["uf_hint"]).strip().upper()
    assunto = str(payload.get("Assunto") or hints["assunto_hint"]).strip()
    sub_assunto = _normalize_sub_assunto(
        payload.get("Sub-assunto") or hints["sub_assunto_hint"],
        full_text,
    )
    valor_causa = _coerce_brl_value(payload.get("Valor da causa") or hints["valor_causa_hint"])

    if not numero_processo:
        numero_processo = processo_dir.name
    if not uf:
        uf = "ND"
    if not assunto:
        assunto = _default_assunto(full_text)
    return {
        "Número do processo": numero_processo,
        "UF": uf,
        "Assunto": assunto,
        "Sub-assunto": sub_assunto,
        "Valor da causa": valor_causa,
    }


def _extract_subsidy_flags(processo_dir: Path) -> dict[str, int]:
    subsidios_dir = processo_dir / "subsidios"
    flags = {column: 0 for column in DOCUMENT_PATTERNS}
    if not subsidios_dir.exists():
        return flags

    normalized_files = [
        _normalize_text_key(file_path.stem)
        for file_path in subsidios_dir.iterdir()
        if file_path.is_file()
    ]

    for column, tokens in DOCUMENT_PATTERNS.items():
        flags[column] = int(
            any(all(token in normalized_name for token in tokens) for normalized_name in normalized_files)
        )

    return flags


class GeradorDataCsvProcessos:
    def __init__(
        self,
        processos_dir: Path | str = DEFAULT_PROCESSOS_DIR,
        output_csv: Path | str = DEFAULT_OUTPUT_CSV,
        model_name: str = DEFAULT_MODEL_NAME,
        api_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
    ) -> None:
        self.processos_dir = Path(processos_dir)
        self.output_csv = Path(output_csv)
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def build_rows(self) -> list[LinhaDataCsv]:
        if not self.api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY não configurada. A geração do data.csv exige a chave."
            )
        if not self.processos_dir.exists():
            raise FileNotFoundError(f"Diretório de processos não encontrado em {self.processos_dir}")

        rows: list[LinhaDataCsv] = []
        for processo_dir in sorted(path for path in self.processos_dir.iterdir() if path.is_dir()):
            rows.append(self._build_single_row(processo_dir))
        return rows

    def generate_and_persist(self) -> pd.DataFrame:
        rows = [row.to_csv_row() for row in self.build_rows()]
        dataframe = pd.DataFrame(rows, columns=CSV_COLUMNS)
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        dataframe.to_csv(self.output_csv, index=False, encoding="utf-8", na_rep="NaN")
        return dataframe

    def _build_single_row(self, processo_dir: Path) -> LinhaDataCsv:
        autos_pdf = _find_autos_pdf(processo_dir)
        full_text = _extract_pdf_text(autos_pdf)
        focus_text = _build_focus_text(full_text)
        metadata = self._call_openai(focus_text, _heuristic_hints(full_text, processo_dir))
        normalized_metadata = _normalize_metadata(metadata, full_text, processo_dir)
        subsidy_flags = _extract_subsidy_flags(processo_dir)

        return LinhaDataCsv(
            numero_processo=normalized_metadata["Número do processo"],
            uf=normalized_metadata["UF"],
            assunto=normalized_metadata["Assunto"],
            sub_assunto=normalized_metadata["Sub-assunto"],
            valor_causa=normalized_metadata["Valor da causa"],
            contrato=subsidy_flags["Contrato"],
            extrato=subsidy_flags["Extrato"],
            comprovante_credito=subsidy_flags["Comprovante de crédito"],
            dossie=subsidy_flags["Dossiê"],
            demonstrativo_evolucao_divida=subsidy_flags["Demonstrativo de evolução da dívida"],
            laudo_referenciado=subsidy_flags["Laudo referenciado"],
        )

    def _call_openai(self, focus_text: str, hints: dict[str, str]) -> dict[str, str]:
        prompt = f"""
Extraia do texto dos autos os dados estruturados para uma linha do data.csv.

Responda SOMENTE em JSON válido, usando exatamente estas chaves:
{{
  "Número do processo": "",
  "UF": "",
  "Assunto": "",
  "Sub-assunto": "",
  "Valor da causa": ""
}}

Regras:
- "Número do processo": devolva o número CNJ completo, se estiver no texto.
- "UF": devolva apenas a sigla da unidade federativa com 2 letras.
- "Assunto": normalize em uma etiqueta curta de negócio. Quando o caso tratar de operação bancária
  não reconhecida, fraude em empréstimo ou ação de inexistência de débito por contratação impugnada,
  use exatamente "Não reconhece operação".
- "Sub-assunto": use apenas uma destas duas saídas:
  - "Golpe": somente se o texto explicitamente indicar golpe, fraude, contratação fraudulenta
    ou uso indevido de identidade por terceiro.
  - "Genérico": em qualquer outro caso.
- "Valor da causa": devolva apenas o valor em formato brasileiro, por exemplo "25.000,00", sem "R$".
- Não invente dados ausentes.

Hints heurísticos extraídos localmente:
{json.dumps(hints, ensure_ascii=False, indent=2)}

Trecho consolidado dos autos:
{focus_text}
""".strip()

        payload = {
            "model": self.model_name,
            "input": [
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Você é um analista jurídico especializado em extração estruturada "
                                "de dados para bases tabulares. Responda apenas no formato solicitado."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                },
            ],
        }

        request = Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")

        response_payload = json.loads(body)
        output_text = response_payload.get("output_text")
        if not output_text:
            messages: list[str] = []
            for item in response_payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        messages.append(content.get("text", ""))
            output_text = "\n".join(part.strip() for part in messages if part.strip()).strip()

        if not output_text:
            raise RuntimeError("A OpenAI não retornou texto utilizável para a geração do data.csv.")

        return _extract_json_payload(output_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera o data.csv estruturado a partir de data/processos_exemplo."
    )
    parser.add_argument(
        "--processos-dir",
        default=str(DEFAULT_PROCESSOS_DIR),
        help="Diretório raiz com os processos exemplo.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_OUTPUT_CSV),
        help="Arquivo CSV de saída.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    gerador = GeradorDataCsvProcessos(
        processos_dir=args.processos_dir,
        output_csv=args.output_csv,
    )
    dataframe = gerador.generate_and_persist()
    print(
        json.dumps(
            {
                "output_csv": str(Path(args.output_csv).resolve()),
                "total_processos": int(len(dataframe)),
                "colunas": CSV_COLUMNS,
                "processos": dataframe["Número do processo"].tolist(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
