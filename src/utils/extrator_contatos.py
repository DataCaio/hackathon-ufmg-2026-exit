from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.4")
DEFAULT_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")

CONTACT_KEYS = {
    "parte_autora_nome",
    "parte_autora_email",
    "advogado_nome",
    "advogado_email",
    "advogado_oab",
}
FOCUS_PATTERNS = [
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in [
        r"endere[cç]o eletr[oô]nico",
        r"\bOAB\b",
        r"outorgad[oa]",
        r"advogad[oa]",
        r"subscreve",
        r"procura[cç][aã]o",
        r"e-?mail",
    ]
]
EMAIL_REGEX = re.compile(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}")
OAB_REGEX = re.compile(r"OAB/\s*([A-Z]{2})\s*([\d.\-]+)", flags=re.IGNORECASE)


@dataclass
class ContactExtractionResult:
    processo_id: str
    autos_pdf: str
    parte_autora_nome: str
    parte_autora_email: str
    advogado_nome: str
    advogado_email: str
    advogado_oab: str
    origem: str
    arquivo_contato_json: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _deduplicate_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped in seen:
            continue
        deduped.append(stripped)
        seen.add(stripped)
    return deduped


def _build_focus_text(full_text: str) -> str:
    lines = full_text.splitlines()
    selected_lines = lines[:70]

    for index, line in enumerate(lines):
        if any(pattern.search(line) for pattern in FOCUS_PATTERNS):
            start = max(0, index - 2)
            end = min(len(lines), index + 3)
            selected_lines.extend(lines[start:end])

    selected_lines.extend(lines[-40:])
    compact_text = "\n".join(_deduplicate_lines(selected_lines))
    return compact_text[:14000]


def _heuristic_hints(full_text: str) -> dict[str, str]:
    emails = EMAIL_REGEX.findall(full_text)
    oab_matches = OAB_REGEX.findall(full_text)
    hints: dict[str, str] = {
        "parte_autora_email_hint": emails[0] if emails else "",
        "advogado_email_hint": emails[-1] if emails else "",
        "advogado_oab_hint": "",
    }

    if oab_matches:
        uf, number = oab_matches[-1]
        hints["advogado_oab_hint"] = f"OAB/{uf.upper()} {number}"

    return hints


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("A resposta da OpenAI para contatos não veio em JSON válido.")
        return json.loads(candidate[start:end + 1])


def _sanitize_contact_value(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s{2,}", " ", text)
    text = text.replace("\n", " ").strip(" .")
    return text


def _normalize_contact_payload(payload: dict[str, Any]) -> dict[str, str]:
    normalized = {key: _sanitize_contact_value(payload.get(key, "")) for key in CONTACT_KEYS}

    if normalized["parte_autora_email"]:
        email_match = EMAIL_REGEX.search(normalized["parte_autora_email"])
        normalized["parte_autora_email"] = email_match.group(0) if email_match else ""

    if normalized["advogado_email"]:
        email_match = EMAIL_REGEX.search(normalized["advogado_email"])
        normalized["advogado_email"] = email_match.group(0) if email_match else ""

    if normalized["advogado_oab"]:
        oab_match = OAB_REGEX.search(normalized["advogado_oab"])
        if oab_match:
            normalized["advogado_oab"] = f"OAB/{oab_match.group(1).upper()} {oab_match.group(2)}"
        else:
            normalized["advogado_oab"] = ""

    return normalized


class ExtratorContatoAutos:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        api_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def extract_and_persist(self, processo_dir: Path, processo_id: str) -> ContactExtractionResult:
        if not self.api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY não configurada. A extração de contatos dos autos exige a chave."
            )

        autos_pdf = _find_autos_pdf(processo_dir)
        full_text = _extract_pdf_text(autos_pdf)
        focus_text = _build_focus_text(full_text)
        hints = _heuristic_hints(full_text)
        contact_payload = self._call_openai(focus_text, hints)

        output_path = processo_dir / "Contato.json"
        persisted_payload = {
            "processo_id": processo_id,
            "autos_pdf": str(autos_pdf),
            "origem": f"openai:{self.model_name}",
            **contact_payload,
        }
        output_path.write_text(
            json.dumps(persisted_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return ContactExtractionResult(
            processo_id=processo_id,
            autos_pdf=str(autos_pdf),
            parte_autora_nome=contact_payload["parte_autora_nome"],
            parte_autora_email=contact_payload["parte_autora_email"],
            advogado_nome=contact_payload["advogado_nome"],
            advogado_email=contact_payload["advogado_email"],
            advogado_oab=contact_payload["advogado_oab"],
            origem=f"openai:{self.model_name}",
            arquivo_contato_json=str(output_path),
        )

    def _call_openai(self, focus_text: str, hints: dict[str, str]) -> dict[str, str]:
        prompt = f"""
Extraia do texto dos autos os dados de contato relevantes para a interface.

Você deve identificar:
- nome da parte autora
- e-mail da parte autora
- nome do advogado ou advogada que subscreve / outorgado(a)
- e-mail do advogado ou advogada
- OAB do advogado ou advogada

Regras:
- Responda SOMENTE em JSON válido.
- Use exatamente estas chaves:
{{
  "parte_autora_nome": "",
  "parte_autora_email": "",
  "advogado_nome": "",
  "advogado_email": "",
  "advogado_oab": ""
}}
- Não invente informações.
- Se algum campo não estiver disponível, retorne string vazia.
- Priorize o advogado da procuração ou o nome próximo à OAB.

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
                                "de dados documentais. Responda apenas no formato solicitado."
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
            raise RuntimeError("A OpenAI não retornou texto utilizável para extração de contatos.")

        raw_payload = _extract_json_payload(output_text)
        return _normalize_contact_payload(raw_payload)
