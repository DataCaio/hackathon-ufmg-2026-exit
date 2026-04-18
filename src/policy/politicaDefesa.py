from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .politicaDecisao import CASE_ID_COLUMN, DOCUMENT_COLUMNS, DecisionResult
except ImportError:
    from politicaDecisao import CASE_ID_COLUMN, DOCUMENT_COLUMNS, DecisionResult

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.4")
DEFAULT_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".html"}

DOCUMENT_FILE_HINTS = {
    "Contrato": ["contrato"],
    "Extrato": ["extrato"],
    "Comprovante de crédito": ["comprovante", "credito", "crédito"],
    "Dossiê": ["dossie", "dossiê"],
    "Demonstrativo de evolução da dívida": ["demonstrativo", "divida", "dívida"],
    "Laudo referenciado": ["laudo", "referenciado"],
}


@dataclass
class DefenseDocument:
    tipo: str
    caminho: str
    trecho: str
    encontrado: bool


@dataclass
class DefenseResult:
    processo_id: str
    origem: str
    subsidios_utilizados: list[str]
    subsidios_faltantes: list[str]
    estrategia: str
    minuta_defesa: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_text(file_path: Path, max_chars: int = 2500) -> str:
    suffix = file_path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars].strip()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return "[PDF localizado, mas a extração textual local requer o pacote pypdf.]"

        reader = PdfReader(str(file_path))
        chunks: list[str] = []
        for page in reader.pages[:5]:
            text = (page.extract_text() or "").strip()
            if text:
                chunks.append(text)
        return "\n".join(chunks)[:max_chars].strip() or "[PDF sem texto extraível.]"

    return f"[Arquivo localizado: {file_path.name}]"


def _find_best_document(base_dir: Path | None, document_type: str) -> Path | None:
    if base_dir is None or not base_dir.exists():
        return None

    hints = DOCUMENT_FILE_HINTS[document_type]
    for file_path in sorted(base_dir.rglob("*")):
        if not file_path.is_file():
            continue
        normalized_name = file_path.name.lower()
        if all(hint in normalized_name for hint in hints[:1]) or any(
            hint in normalized_name for hint in hints
        ):
            return file_path
    return None


class PoliticaDefesa:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        api_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def build_defense(
        self,
        case_data: dict[str, Any],
        decision_result: DecisionResult,
        processo_dir: Path | str | None = None,
    ) -> DefenseResult:
        processo_path = Path(processo_dir) if processo_dir else None
        subsidios_dir = None
        autos_dir = None
        if processo_path and processo_path.exists():
            subsidios_dir = processo_path / "subsidios"
            autos_dir = processo_path / "autos"

        collected_documents = self._collect_documents(
            subsidios_dir=subsidios_dir,
            autos_dir=autos_dir,
            prioritized_documents=decision_result.subsidios_prioritarios,
        )

        prompt = self._build_prompt(
            case_data=case_data,
            decision_result=decision_result,
            documents=collected_documents,
        )

        if self.api_key:
            try:
                minuta = self._call_openai(prompt)
                origem = f"openai:{self.model_name}"
            except (HTTPError, URLError, RuntimeError) as error:
                origem = f"fallback:{type(error).__name__}"
                minuta = self._build_fallback_defense(
                    decision_result=decision_result,
                    documents=collected_documents,
                )
        else:
            origem = "fallback:sem_api_key"
            minuta = self._build_fallback_defense(
                decision_result=decision_result,
                documents=collected_documents,
            )

        estrategia = (
            "Defesa orientada pelos subsídios com maior peso no modelo de decisão, "
            "priorizando regularidade da contratação, liberação do crédito e trilha documental."
        )
        subsidios_nao_localizados = [
            document.tipo for document in collected_documents if not document.encontrado
        ]

        return DefenseResult(
            processo_id=str(case_data.get(CASE_ID_COLUMN) or "processo_demo"),
            origem=origem,
            subsidios_utilizados=[
                document.tipo for document in collected_documents if document.encontrado
            ],
            subsidios_faltantes=sorted(
                set(decision_result.subsidios_ausentes_criticos + subsidios_nao_localizados)
            ),
            estrategia=estrategia,
            minuta_defesa=minuta,
        )

    def _collect_documents(
        self,
        subsidios_dir: Path | None,
        autos_dir: Path | None,
        prioritized_documents: list[str],
    ) -> list[DefenseDocument]:
        ordered_documents = []
        seen: set[str] = set()

        for document_type in prioritized_documents + DOCUMENT_COLUMNS:
            if document_type in seen:
                continue
            ordered_documents.append(document_type)
            seen.add(document_type)

        documents: list[DefenseDocument] = []
        for document_type in ordered_documents:
            best_path = _find_best_document(subsidios_dir, document_type)
            if best_path is None:
                best_path = _find_best_document(autos_dir, document_type)

            if best_path is None:
                documents.append(
                    DefenseDocument(
                        tipo=document_type,
                        caminho="",
                        trecho="[Documento não localizado no processo de exemplo.]",
                        encontrado=False,
                    )
                )
                continue

            documents.append(
                DefenseDocument(
                    tipo=document_type,
                    caminho=str(best_path),
                    trecho=_extract_text(best_path),
                    encontrado=True,
                )
            )

        return documents

    def _build_prompt(
        self,
        case_data: dict[str, Any],
        decision_result: DecisionResult,
        documents: list[DefenseDocument],
    ) -> str:
        top_features = "\n".join(
            f"- {item.feature}: contribuição {item.contribuicao}"
            for item in decision_result.features_relevantes[:5]
        )
        document_context = "\n\n".join(
            (
                f"## {document.tipo}\n"
                f"Encontrado: {'sim' if document.encontrado else 'não'}\n"
                f"Caminho: {document.caminho or 'não localizado'}\n"
                f"Trecho:\n{document.trecho or '[sem texto extraído]'}"
            )
            for document in documents[:4]
        )

        return f"""
Elabore uma minuta inicial de defesa em português do Brasil para um processo cível bancário
de não reconhecimento de contratação de empréstimo.

Use apenas os fatos fornecidos abaixo. Se algum elemento estiver ausente, trate como lacuna
probatória e não invente.

Dados estruturados do caso:
{json.dumps(case_data, ensure_ascii=False, indent=2)}

Leitura do modelo de decisão:
- Probabilidade de êxito na defesa: {decision_result.probabilidade_exito}
- Decisão sugerida pelo fluxo: {decision_result.decisao}
- Subsídios prioritários: {', '.join(decision_result.subsidios_prioritarios) or 'nenhum'}
- Subsídios ausentes críticos: {', '.join(decision_result.subsidios_ausentes_criticos) or 'nenhum'}

Principais sinais do modelo:
{top_features}

Contexto documental:
{document_context}

Estruture a resposta com:
1. Resumo executivo do caso
2. Tese central de defesa
3. Pontos probatórios que fortalecem o banco
4. Fragilidades e cautelas
5. Minuta objetiva de defesa com linguagem jurídica
6. Próximas diligências recomendadas
""".strip()

    def _call_openai(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "input": [
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Você é um advogado cível sênior especializado em defesa bancária. "
                                "Seja objetivo, técnico e não invente fatos."
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
        if output_text:
            return str(output_text).strip()

        messages: list[str] = []
        for item in response_payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    messages.append(content.get("text", ""))

        text = "\n".join(part.strip() for part in messages if part.strip()).strip()
        if not text:
            raise RuntimeError("Resposta da OpenAI veio sem texto utilizável.")
        return text

    def _build_fallback_defense(
        self,
        decision_result: DecisionResult,
        documents: list[DefenseDocument],
    ) -> str:
        found_documents = [document.tipo for document in documents if document.encontrado]
        missing_documents = [document.tipo for document in documents if not document.encontrado]
        prominent_signals = ", ".join(
            feature.feature for feature in decision_result.features_relevantes[:3]
        )

        return (
            "Resumo executivo:\n"
            f"- O caso apresenta probabilidade estimada de êxito em defesa de "
            f"{decision_result.probabilidade_exito:.2%}.\n"
            f"- Os principais sinais favoráveis no modelo foram: {prominent_signals or 'não identificado'}.\n\n"
            "Tese central:\n"
            "- Sustentar a regularidade da operação bancária a partir da trilha documental disponível, "
            "destacando contratação, disponibilização de crédito e evolução da relação contratual.\n\n"
            "Pontos probatórios:\n"
            f"- Subsídios localizados: {', '.join(found_documents) or 'nenhum'}.\n"
            f"- Subsídios ausentes ou não localizados: {', '.join(missing_documents) or 'nenhum'}.\n\n"
            "Minuta objetiva:\n"
            "A instituição ré requer o reconhecimento da regularidade da contratação, com base na "
            "documentação bancária apresentada, especialmente os subsídios prioritários apontados acima. "
            "Caso persista alguma lacuna documental, recomenda-se complementar a instrução antes da "
            "protocolização final da peça.\n\n"
            "Próximas diligências:\n"
            "- Validar se todos os documentos prioritários estão anexados em formato legível.\n"
            "- Conferir correspondência entre contrato, liberação do crédito e evolução da dívida.\n"
            "- Ajustar a defesa final aos fatos concretos dos autos."
        )
