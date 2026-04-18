from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = ROOT_DIR / "data" / "sentencas.csv"
DEFAULT_ARTIFACT_DIR = ROOT_DIR / "data" / "policy_artifacts"

CASE_ID_COLUMN = "Número do processo"
FEATURE_COLUMNS = [
    "UF",
    "Sub-assunto",
    "Valor da causa",
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
    "Dossiê",
    "Demonstrativo de evolução da dívida",
    "Laudo referenciado",
]
DOCUMENT_COLUMNS = [
    "Contrato",
    "Extrato",
    "Comprovante de crédito",
    "Dossiê",
    "Demonstrativo de evolução da dívida",
    "Laudo referenciado",
]
CATEGORICAL_COLUMNS = ["UF", "Sub-assunto"]
NUMERIC_COLUMNS = [column for column in FEATURE_COLUMNS if column not in CATEGORICAL_COLUMNS]
FRIENDLY_FEATURE_NAMES = {
    "cat__UF": "UF",
    "cat__Sub-assunto": "Sub-assunto",
    "num__Valor da causa": "Valor da causa",
    "num__Contrato": "Contrato",
    "num__Extrato": "Extrato",
    "num__Comprovante de crédito": "Comprovante de crédito",
    "num__Dossiê": "Dossiê",
    "num__Demonstrativo de evolução da dívida": "Demonstrativo de evolução da dívida",
    "num__Laudo referenciado": "Laudo referenciado",
}


@dataclass
class FeatureContribution:
    feature: str
    valor_no_caso: Any
    contribuicao: float


@dataclass
class DecisionResult:
    processo_id: str
    decisao: str
    probabilidade_exito: float
    probabilidade_acordo: float
    score_confianca: float
    limiar_defesa: float
    features_relevantes: list[FeatureContribution]
    subsidios_prioritarios: list[str]
    subsidios_ausentes_criticos: list[str]
    metricas_modelo: dict[str, float]
    dados_caso: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["features_relevantes"] = [asdict(item) for item in self.features_relevantes]
        return payload


def _build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "encoder",
                            OrdinalEncoder(
                                handle_unknown="use_encoded_value",
                                unknown_value=-1,
                            ),
                        ),
                    ]
                ),
                CATEGORICAL_COLUMNS,
            ),
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                NUMERIC_COLUMNS,
            ),
        ],
        verbose_feature_names_out=True,
    )


def _build_classifier() -> xgb.XGBClassifier:
    return xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        eval_metric="logloss",
        tree_method="hist",
    )


def _normalize_target(target: pd.Series) -> pd.Series:
    if target.dtype == object:
        mapped = target.astype(str).str.strip().map({"Êxito": 1, "Não Êxito": 0})
        return mapped.fillna(target).astype(int)
    return target.astype(int)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if pd.isna(value):
        return default
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_binary_flag(value: Any) -> int:
    if pd.isna(value) or value is None or value == "":
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "nao", "não", "n"}:
            return 0
        if normalized in {"1", "true", "sim", "s"}:
            return 1
    try:
        return 1 if int(float(value)) > 0 else 0
    except (TypeError, ValueError):
        return 1 if bool(value) else 0


def normalize_case(case_data: dict[str, Any]) -> dict[str, Any]:
    normalized = {CASE_ID_COLUMN: str(case_data.get(CASE_ID_COLUMN) or "processo_demo")}
    normalized["UF"] = str(case_data.get("UF") or "ND")
    normalized["Sub-assunto"] = str(case_data.get("Sub-assunto") or "Genérico")
    normalized["Valor da causa"] = _safe_float(case_data.get("Valor da causa"), 0.0)

    for column in DOCUMENT_COLUMNS:
        normalized[column] = _safe_binary_flag(case_data.get(column, 0))

    return normalized


class PoliticaDecisao:
    def __init__(
        self,
        data_path: Path | str = DEFAULT_DATA_PATH,
        artifact_dir: Path | str = DEFAULT_ARTIFACT_DIR,
        limiar_defesa: float = 0.60,
    ) -> None:
        self.data_path = Path(data_path)
        self.artifact_dir = Path(artifact_dir)
        self.artifact_path = self.artifact_dir / "politica_decisao.joblib"
        self.report_path = self.artifact_dir / "politica_decisao_metricas.json"
        self.limiar_defesa = limiar_defesa
        self.bundle: dict[str, Any] | None = None

    def ensure_trained(self, force_retrain: bool = False) -> dict[str, Any]:
        if force_retrain or not self.artifact_path.exists():
            return self.train()
        self.bundle = joblib.load(self.artifact_path)
        return self.bundle

    def train(self) -> dict[str, Any]:
        if not self.data_path.exists():
            raise FileNotFoundError(
                f"Base historica nao encontrada em {self.data_path}. "
                "Coloque o arquivo data/sentencas.csv para treinar a politica."
            )

        df = pd.read_csv(self.data_path, thousands=".", decimal=",")
        model_df = df[[CASE_ID_COLUMN, *FEATURE_COLUMNS, "Resultado macro"]].copy()
        model_df["Resultado macro"] = _normalize_target(model_df["Resultado macro"])

        X = model_df[FEATURE_COLUMNS]
        y = model_df["Resultado macro"]

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y,
        )

        validation_preprocessor = _build_preprocessor()
        X_train_encoded = validation_preprocessor.fit_transform(X_train)
        X_test_encoded = validation_preprocessor.transform(X_test)

        validation_model = _build_classifier()
        validation_model.fit(X_train_encoded, y_train)
        test_probabilities = validation_model.predict_proba(X_test_encoded)[:, 1]
        test_predictions = (test_probabilities >= self.limiar_defesa).astype(int)

        metrics = {
            "roc_auc": round(float(roc_auc_score(y_test, test_probabilities)), 4),
            "accuracy": round(float(accuracy_score(y_test, test_predictions)), 4),
            "precision_defesa": round(float(precision_score(y_test, test_predictions)), 4),
            "recall_defesa": round(float(recall_score(y_test, test_predictions)), 4),
            "base_historica": int(len(model_df)),
            "limiar_defesa": float(self.limiar_defesa),
        }

        production_preprocessor = _build_preprocessor()
        X_full_encoded = production_preprocessor.fit_transform(X)

        production_model = _build_classifier()
        production_model.fit(X_full_encoded, y)

        feature_names = production_preprocessor.get_feature_names_out().tolist()
        importances = {
            FRIENDLY_FEATURE_NAMES.get(name, name): round(float(score), 6)
            for name, score in sorted(
                zip(feature_names, production_model.feature_importances_, strict=False),
                key=lambda item: item[1],
                reverse=True,
            )
        }

        bundle = {
            "preprocessor": production_preprocessor,
            "model": production_model,
            "feature_names": feature_names,
            "feature_importances": importances,
            "metrics": metrics,
            "limiar_defesa": self.limiar_defesa,
        }

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, self.artifact_path)
        self.report_path.write_text(
            json.dumps(
                {
                    "metrics": metrics,
                    "feature_importances": importances,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.bundle = bundle
        return bundle

    def predict_case(self, case_data: dict[str, Any]) -> DecisionResult:
        bundle = self.ensure_trained()
        normalized_case = normalize_case(case_data)
        case_df = pd.DataFrame([normalized_case], columns=[CASE_ID_COLUMN, *FEATURE_COLUMNS]).drop(
            columns=[CASE_ID_COLUMN]
        )

        preprocessor: ColumnTransformer = bundle["preprocessor"]
        model: xgb.XGBClassifier = bundle["model"]
        encoded_case = preprocessor.transform(case_df)
        probability = float(model.predict_proba(encoded_case)[0][1])
        decision = "defesa" if probability >= bundle["limiar_defesa"] else "acordo"
        score_confianca = abs(probability - bundle["limiar_defesa"])

        contributions = model.get_booster().predict(
            xgb.DMatrix(encoded_case),
            pred_contribs=True,
        )[0]
        feature_names = bundle["feature_names"]

        ranked_features: list[FeatureContribution] = []
        for feature_name, contribution in zip(feature_names, contributions[:-1], strict=False):
            friendly_name = FRIENDLY_FEATURE_NAMES.get(feature_name, feature_name)
            ranked_features.append(
                FeatureContribution(
                    feature=friendly_name,
                    valor_no_caso=normalized_case.get(friendly_name),
                    contribuicao=round(float(contribution), 4),
                )
            )

        ranked_features.sort(key=lambda item: abs(item.contribuicao), reverse=True)

        local_document_scores = {
            item.feature: abs(item.contribuicao)
            for item in ranked_features
            if item.feature in DOCUMENT_COLUMNS
        }
        global_importances: dict[str, float] = bundle["feature_importances"]

        present_documents = [
            column
            for column in DOCUMENT_COLUMNS
            if normalized_case.get(column)
        ]
        missing_documents = [
            column
            for column in DOCUMENT_COLUMNS
            if not normalized_case.get(column)
        ]

        subsidios_prioritarios = sorted(
            present_documents,
            key=lambda column: (
                local_document_scores.get(column, 0.0),
                global_importances.get(column, 0.0),
            ),
            reverse=True,
        )[:3]
        subsidios_ausentes_criticos = sorted(
            missing_documents,
            key=lambda column: global_importances.get(column, 0.0),
            reverse=True,
        )[:3]

        return DecisionResult(
            processo_id=normalized_case[CASE_ID_COLUMN],
            decisao=decision,
            probabilidade_exito=round(probability, 4),
            probabilidade_acordo=round(1.0 - probability, 4),
            score_confianca=round(score_confianca, 4),
            limiar_defesa=float(bundle["limiar_defesa"]),
            features_relevantes=ranked_features[:5],
            subsidios_prioritarios=subsidios_prioritarios,
            subsidios_ausentes_criticos=subsidios_ausentes_criticos,
            metricas_modelo=bundle["metrics"],
            dados_caso=normalized_case,
        )
