from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from html import escape
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
    conteudo_defesa_pdf: str
    arquivo_defesa_pdf: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_DEFENSE_KEYS = {
    "resumo_executivo",
    "tese_central",
    "pontos_probatorios",
    "fragilidades_cautelas",
    "argumentos_prioritarios",
    "minuta_base",
    "proximas_diligencias",
}

UNWANTED_LINE_PATTERNS = [
    r"^\s*Se quiser\b.*$",
    r"^\s*Termos em que[,]?\s*.*$",
    r"^\s*Pede deferimento[.]?\s*$",
    r"^\s*Excelent[íi]ssimo\b.*$",
    r"^\s*\[.*\]\s*$",
    r"^\s*CONTESTA[CÇ][AÃ]O\s*$",
]


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


def _normalize_pdf_text(text: str) -> str:
    sanitized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "    ")
    )
    return sanitized


def _apply_inline_formatting(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def _markdownish_to_html(text: str) -> str:
    normalized = _normalize_pdf_text(text)
    lines = normalized.split("\n")
    html_parts: list[str] = []
    paragraph_buffer: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            content = " ".join(item.strip() for item in paragraph_buffer if item.strip())
            if content:
                html_parts.append(f"<p>{_apply_inline_formatting(content)}</p>")
            paragraph_buffer = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue

        if line.startswith("### "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h3>{_apply_inline_formatting(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h2>{_apply_inline_formatting(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h1>{_apply_inline_formatting(line[2:])}</h1>")
            continue
        if re.match(r"^\d+\.\s+", line):
            flush_paragraph()
            close_list()
            html_parts.append(f"<h3>{_apply_inline_formatting(re.sub(r'^\\d+\\.\\s+', '', line))}</h3>")
            continue
        if line.startswith(("- ", "* ")):
            flush_paragraph()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_apply_inline_formatting(line[2:])}</li>")
            continue
        if line == "---":
            flush_paragraph()
            close_list()
            html_parts.append("<hr />")
            continue

        paragraph_buffer.append(line)

    flush_paragraph()
    close_list()
    return "\n".join(html_parts)


def _build_defense_html(title: str, process_id: str, body_text: str) -> str:
    body_html = _markdownish_to_html(body_text)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
  <style>
    @page {{
      size: A4;
      margin: 22mm 18mm 22mm 20mm;
    }}
    :root {{
      --ink: #1f2937;
      --muted: #5b6472;
      --line: #d7dce3;
      --accent: #0f3d75;
      --panel: #f6f8fb;
    }}
    body {{
      font-family: "Georgia", "Times New Roman", serif;
      color: var(--ink);
      line-height: 1.55;
      font-size: 12pt;
      margin: 0;
    }}
    .header {{
      border-bottom: 2px solid var(--accent);
      padding-bottom: 14px;
      margin-bottom: 20px;
    }}
    .eyebrow {{
      font-family: "Arial", sans-serif;
      font-size: 10pt;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
      margin: 0 0 8px;
      font-weight: 700;
    }}
    .title {{
      font-size: 22pt;
      line-height: 1.2;
      margin: 0 0 6px;
      color: #10233f;
    }}
    .subtitle {{
      font-family: "Arial", sans-serif;
      font-size: 10.5pt;
      color: var(--muted);
      margin: 0;
    }}
    .meta {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px 16px;
      margin: 0 0 22px;
      font-family: "Arial", sans-serif;
      font-size: 10.5pt;
    }}
    .meta strong {{
      color: #0f172a;
    }}
    h1, h2, h3 {{
      font-family: "Arial", sans-serif;
      color: #10233f;
      page-break-after: avoid;
    }}
    h1 {{
      font-size: 18pt;
      margin: 24px 0 10px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 4px;
    }}
    h2 {{
      font-size: 15pt;
      margin: 20px 0 8px;
    }}
    h3 {{
      font-size: 12.5pt;
      margin: 16px 0 6px;
    }}
    p {{
      margin: 0 0 12px;
      text-align: justify;
    }}
    ul {{
      margin: 0 0 12px 22px;
      padding: 0;
    }}
    li {{
      margin: 0 0 6px;
    }}
    hr {{
      border: none;
      border-top: 1px solid var(--line);
      margin: 18px 0;
    }}
    .footer {{
      margin-top: 28px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      font-family: "Arial", sans-serif;
      font-size: 9.5pt;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <header class="header">
    <p class="eyebrow">Documento de apoio ao advogado</p>
    <h1 class="title">Defesa</h1>
    <p class="subtitle">Processo {escape(process_id)} | Conteúdo estruturado para aproveitamento em peça jurídica.</p>
  </header>
  <section class="meta">
    <strong>Observação:</strong> este material consolida os argumentos mais fortes do caso com base nos subsídios disponíveis e na estratégia sugerida pelo sistema.
  </section>
  <main>
    {body_html}
  </main>
  <footer class="footer">
    Documento gerado automaticamente para apoio interno na elaboração da defesa.
  </footer>
</body>
</html>
"""


def _write_defense_pdf(output_path: Path, processo_id: str, body_text: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = _build_defense_html(
        title=f"Defesa - Processo {processo_id}",
        process_id=processo_id,
        body_text=body_text,
    )

    with tempfile.TemporaryDirectory(prefix="defesa_pdf_") as tmp_dir:
        html_path = Path(tmp_dir) / "defesa.html"
        html_path.write_text(html, encoding="utf-8")

        chrome_cmd = [
            "google-chrome",
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={output_path}",
            html_path.as_uri(),
        ]
        try:
            subprocess.run(
                chrome_cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as chrome_error:
            libreoffice_cmd = [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf:writer_web_pdf_Export",
                "--outdir",
                str(output_path.parent),
                str(html_path),
            ]
            try:
                subprocess.run(
                    libreoffice_cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                generated_pdf = output_path.parent / f"{html_path.stem}.pdf"
                if generated_pdf.exists():
                    generated_pdf.replace(output_path)
                else:
                    raise RuntimeError("LibreOffice não gerou o PDF esperado.")
            except Exception as libreoffice_error:
                raise RuntimeError(
                    "Falha ao gerar Defesa.pdf com Chrome e LibreOffice."
                ) from libreoffice_error


def _format_list_for_report(items: list[str], empty_message: str) -> str:
    if not items:
        return empty_message
    return "\n".join(f"- {item}" for item in items)


def _sanitize_generated_text(text: str) -> str:
    sanitized = _normalize_pdf_text(text)
    sanitized = re.sub(r"```(?:json)?", "", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\[[^\]]+\]", "", sanitized)
    sanitized = re.sub(r"_{3,}", "", sanitized)

    kept_lines: list[str] = []
    for raw_line in sanitized.split("\n"):
        line = raw_line.strip()
        if not line:
            kept_lines.append("")
            continue
        if any(re.match(pattern, line, flags=re.IGNORECASE) for pattern in UNWANTED_LINE_PATTERNS):
            continue
        if "oab/" in line.lower():
            continue
        kept_lines.append(line)

    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _sanitize_generated_list(items: Any) -> list[str]:
    if items is None:
        return []
    if isinstance(items, str):
        items = [items]

    sanitized_items: list[str] = []
    for item in items:
        text = _sanitize_generated_text(str(item))
        if text:
            sanitized_items.append(text)
    return sanitized_items


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("A OpenAI não retornou JSON estruturado para a defesa.")
        return json.loads(candidate[start:end + 1])


def _normalize_structured_defense(raw_payload: dict[str, Any]) -> dict[str, Any]:
    missing_keys = REQUIRED_DEFENSE_KEYS - set(raw_payload.keys())
    if missing_keys:
        raise RuntimeError(
            "A resposta estruturada da defesa veio incompleta. "
            f"Chaves ausentes: {', '.join(sorted(missing_keys))}."
        )

    argumentos: list[dict[str, str]] = []
    for item in raw_payload.get("argumentos_prioritarios", []):
        if isinstance(item, dict):
            titulo = _sanitize_generated_text(str(item.get("titulo", "")))
            texto = _sanitize_generated_text(str(item.get("texto", "")))
            if titulo or texto:
                argumentos.append({"titulo": titulo, "texto": texto})
        elif item:
            texto = _sanitize_generated_text(str(item))
            if texto:
                argumentos.append({"titulo": "", "texto": texto})

    return {
        "resumo_executivo": _sanitize_generated_text(str(raw_payload.get("resumo_executivo", ""))),
        "tese_central": _sanitize_generated_text(str(raw_payload.get("tese_central", ""))),
        "pontos_probatorios": _sanitize_generated_list(raw_payload.get("pontos_probatorios", [])),
        "fragilidades_cautelas": _sanitize_generated_list(raw_payload.get("fragilidades_cautelas", [])),
        "argumentos_prioritarios": argumentos,
        "minuta_base": _sanitize_generated_text(str(raw_payload.get("minuta_base", ""))),
        "proximas_diligencias": _sanitize_generated_list(raw_payload.get("proximas_diligencias", [])),
    }


def _format_argument_blocks(argumentos: list[dict[str, str]]) -> str:
    if not argumentos:
        return "Não foram gerados blocos argumentativos específicos."

    blocks: list[str] = []
    for index, item in enumerate(argumentos, start=1):
        titulo = item.get("titulo", "").strip()
        texto = item.get("texto", "").strip()
        if titulo:
            blocks.append(f"{index}. {titulo}\n{texto}".strip())
        elif texto:
            blocks.append(f"{index}. {texto}")
    return "\n\n".join(blocks)


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
        if not self.api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY não configurada. A política de defesa exige a chave para gerar a minuta."
            )

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
        structured_content = self._call_openai(prompt)
        origem = f"openai:{self.model_name}"
        subsidios_nao_localizados = [
            document.tipo for document in collected_documents if not document.encontrado
        ]
        subsidios_utilizados = [
            document.tipo for document in collected_documents if document.encontrado
        ]
        subsidios_faltantes = sorted(
            set(decision_result.subsidios_ausentes_criticos + subsidios_nao_localizados)
        )
        estrategia = (
            "Defesa orientada pelos subsídios com maior peso no modelo de decisão, "
            "priorizando regularidade da contratação, liberação do crédito e trilha documental."
        )
        conteudo_pdf = self._build_defense_report(
            case_data=case_data,
            decision_result=decision_result,
            subsidios_utilizados=subsidios_utilizados,
            subsidios_faltantes=subsidios_faltantes,
            structured_content=structured_content,
        )
        pdf_path = self._resolve_output_pdf_path(processo_path, case_data)
        _write_defense_pdf(
            pdf_path,
            str(case_data.get(CASE_ID_COLUMN) or "processo_demo"),
            conteudo_pdf,
        )

        return DefenseResult(
            processo_id=str(case_data.get(CASE_ID_COLUMN) or "processo_demo"),
            origem=origem,
            subsidios_utilizados=subsidios_utilizados,
            subsidios_faltantes=subsidios_faltantes,
            estrategia=estrategia,
            minuta_defesa=structured_content["minuta_base"],
            conteudo_defesa_pdf=conteudo_pdf,
            arquivo_defesa_pdf=str(pdf_path),
        )

    def _resolve_output_pdf_path(
        self,
        processo_path: Path | None,
        case_data: dict[str, Any],
    ) -> Path:
        if processo_path is not None:
            return processo_path / "Defesa.pdf"
        return ROOT_DIR / f"Defesa_{case_data.get(CASE_ID_COLUMN, 'processo_demo')}.pdf"

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
Elabore o conteúdo estruturado de uma defesa que será entregue ao advogado em um arquivo PDF
chamado "Defesa.pdf", para um processo cível bancário de não reconhecimento de contratação
de empréstimo.

Use apenas os fatos fornecidos abaixo. Se algum elemento estiver ausente, trate como lacuna
probatória e não invente.
O texto final será entregue a um advogado como apoio prático ao final da análise, então escreva
de forma útil, objetiva e pronta para aproveitamento em peça jurídica.
Isto é um documento interno de apoio, não uma petição protocolizável.

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

Use os sinais do modelo e a hierarquia implícita dos subsídios prioritários para dar mais
ênfase aos argumentos mais fortes, mas não cite "importância de feature", "métrica" ou
"modelo" na redação final.

REGRAS OBRIGATÓRIAS:
- Responda SOMENTE em JSON válido.
- Não use markdown, não use crases e não escreva texto fora do JSON.
- Não inclua "Se quiser...", ofertas de continuação, comentários meta ou observações ao usuário.
- Não inclua endereçamento ao juízo, qualificação das partes, assinatura, OAB, pedidos finais,
  "termos em que", "pede deferimento", campos em branco, placeholders ou trechos como
  [Local], [data], [Advogado], [parte autora], [vara], [comarca].
- Não produza contestação pronta para protocolo. Produza apenas fundamentos defensivos
  aproveitáveis pelo advogado.

Use exatamente este formato de chaves:
{{
  "resumo_executivo": "texto",
  "tese_central": "texto",
  "pontos_probatorios": ["item 1", "item 2"],
  "fragilidades_cautelas": ["item 1", "item 2"],
  "argumentos_prioritarios": [
    {{"titulo": "titulo curto", "texto": "parágrafo objetivo"}}
  ],
  "minuta_base": "texto corrido com fundamentos defensivos aproveitáveis, sem endereçamento nem assinatura",
  "proximas_diligencias": ["item 1", "item 2"]
}}
""".strip()

    def _build_defense_report(
        self,
        case_data: dict[str, Any],
        decision_result: DecisionResult,
        subsidios_utilizados: list[str],
        subsidios_faltantes: list[str],
        structured_content: dict[str, Any],
    ) -> str:
        process_id = str(case_data.get(CASE_ID_COLUMN) or "processo_demo")
        resumo = [
            "# Documento de apoio ao advogado",
            "",
            "## Identificação do caso",
            f"Processo: {process_id}",
            f"Estratégia sugerida: {decision_result.decisao}",
            f"Probabilidade estimada de êxito na defesa: {decision_result.probabilidade_exito:.2%}",
            f"Valor da causa: R$ {float(case_data.get('Valor da causa', 0.0)):.2f}",
            "",
            "## Subsídios priorizados para sustentar a defesa",
            _format_list_for_report(
                decision_result.subsidios_prioritarios,
                "Nenhum subsídio prioritário foi identificado.",
            ),
            "",
            "## Subsídios localizados no processo",
            _format_list_for_report(
                subsidios_utilizados,
                "Nenhum subsídio foi localizado no processo.",
            ),
            "",
            "## Pontos de atenção documental",
            _format_list_for_report(
                subsidios_faltantes,
                "Não foram identificadas lacunas documentais críticas.",
            ),
            "",
            "## Resumo executivo do caso",
            structured_content["resumo_executivo"],
            "",
            "## Tese central de defesa",
            structured_content["tese_central"],
            "",
            "## Pontos probatórios que fortalecem o banco",
            _format_list_for_report(
                structured_content["pontos_probatorios"],
                "Nenhum ponto probatório foi consolidado.",
            ),
            "",
            "## Fragilidades e cautelas",
            _format_list_for_report(
                structured_content["fragilidades_cautelas"],
                "Nenhuma fragilidade adicional foi destacada.",
            ),
            "",
            "## Argumentos jurídicos e fáticos prioritários",
            _format_argument_blocks(structured_content["argumentos_prioritarios"]),
            "",
            "## Minuta-base para aproveitamento pelo advogado",
            structured_content["minuta_base"],
            "",
            "## Próximas diligências recomendadas",
            _format_list_for_report(
                structured_content["proximas_diligencias"],
                "Nenhuma diligência adicional foi indicada.",
            ),
        ]
        return "\n".join(resumo).strip()

    def _call_openai(self, prompt: str) -> dict[str, Any]:
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
                                "Seja objetivo, técnico e não invente fatos. "
                                "Quando solicitado, responda apenas no formato exato pedido."
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
        raw_payload = _extract_json_payload(text)
        return _normalize_structured_defense(raw_payload)
