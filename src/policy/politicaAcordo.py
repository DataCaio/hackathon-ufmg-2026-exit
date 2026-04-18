from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

try:
    from .politicaDecisao import (
        CASE_ID_COLUMN,
        CATEGORICAL_COLUMNS,
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_PATH,
        DOCUMENT_COLUMNS,
        FEATURE_COLUMNS,
        NUMERIC_COLUMNS,
        DecisionResult,
        normalize_case,
    )
except ImportError:
    from politicaDecisao import (
        CASE_ID_COLUMN,
        CATEGORICAL_COLUMNS,
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_PATH,
        DOCUMENT_COLUMNS,
        FEATURE_COLUMNS,
        NUMERIC_COLUMNS,
        DecisionResult,
        normalize_case,
    )


@dataclass
class AgreementRecommendation:
    processo_id: str
    valor_causa_original: float
    valor_condenacao_previsto: float
    valor_acordo_sugerido: float
    faixa_negociacao_min: float
    faixa_negociacao_max: float
    economia_estimada: float
    desconto_percentual: float
    racional: str
    metricas_modelo: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _build_regressor() -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        tree_method="hist",
    )


def _quantile(values: np.ndarray, q: float, default: float = 0.0) -> float:
    cleaned = values[np.isfinite(values)]
    if cleaned.size == 0:
        return default
    return float(np.quantile(cleaned, q))


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _safe_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    safe_denominator = np.maximum(np.abs(denominator), 1.0)
    return numerator / safe_denominator


class PoliticaAcordo:
    def __init__(
        self,
        data_path: Path | str = DEFAULT_DATA_PATH,
        artifact_dir: Path | str = DEFAULT_ARTIFACT_DIR,
    ) -> None:
        self.data_path = Path(data_path)
        self.artifact_dir = Path(artifact_dir)
        self.artifact_path = self.artifact_dir / "politica_acordo.joblib"
        self.report_path = self.artifact_dir / "politica_acordo_metricas.json"
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
        model_df = df[[CASE_ID_COLUMN, *FEATURE_COLUMNS, "Valor da condenação/indenização"]].copy()
        model_df["Valor da condenação/indenização"] = (
            pd.to_numeric(model_df["Valor da condenação/indenização"], errors="coerce")
            .fillna(0.0)
            .astype(float)
        )

        X = model_df[FEATURE_COLUMNS]
        y = model_df["Valor da condenação/indenização"]

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
        )

        validation_preprocessor = _build_preprocessor()
        X_train_encoded = validation_preprocessor.fit_transform(X_train)
        X_test_encoded = validation_preprocessor.transform(X_test)

        validation_model = _build_regressor()
        validation_model.fit(X_train_encoded, y_train)
        predictions = validation_model.predict(X_test_encoded)

        y_test_arr = y_test.to_numpy(dtype=float, copy=False)
        pred_arr = np.asarray(predictions, dtype=float)
        positive_mask = (y_test_arr > 0.0) & (pred_arr > 0.0)
        relative_residuals = _safe_ratio(
            y_test_arr[positive_mask] - pred_arr[positive_mask],
            pred_arr[positive_mask],
        )
        relative_residuals = np.clip(relative_residuals, -0.75, 1.5)

        valor_causa_arr = pd.to_numeric(model_df["Valor da causa"], errors="coerce").to_numpy(dtype=float)
        condenacao_arr = y.to_numpy(dtype=float, copy=False)
        ratio_mask = (valor_causa_arr > 0.0) & (condenacao_arr > 0.0)
        condemnation_to_cause_ratio = _safe_ratio(
            condenacao_arr[ratio_mask],
            valor_causa_arr[ratio_mask],
        )

        calibration = {
            "residual_q20": round(_quantile(relative_residuals, 0.20, default=-0.10), 6),
            "residual_q50": round(_quantile(relative_residuals, 0.50, default=0.15), 6),
            "residual_q80": round(_quantile(relative_residuals, 0.80, default=0.60), 6),
            "cause_ratio_q20": round(_quantile(condemnation_to_cause_ratio, 0.20, default=0.50), 6),
            "cause_ratio_q50": round(_quantile(condemnation_to_cause_ratio, 0.50, default=0.74), 6),
            "cause_ratio_q80": round(_quantile(condemnation_to_cause_ratio, 0.80, default=0.89), 6),
        }

        rmse = mean_squared_error(y_test, predictions) ** 0.5
        metrics = {
            "mae": round(float(mean_absolute_error(y_test, predictions)), 2),
            "rmse": round(float(rmse), 2),
            "r2": round(float(r2_score(y_test, predictions)), 4),
            "base_historica": int(len(model_df)),
        }

        production_preprocessor = _build_preprocessor()
        X_full_encoded = production_preprocessor.fit_transform(X)

        production_model = _build_regressor()
        production_model.fit(X_full_encoded, y)

        bundle = {
            "preprocessor": production_preprocessor,
            "model": production_model,
            "metrics": metrics,
            "calibration": calibration,
        }

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, self.artifact_path)
        self.report_path.write_text(
            json.dumps(
                {"metrics": metrics, "calibration": calibration},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.bundle = bundle
        return bundle

    def predict_condemnation(self, case_data: dict[str, Any]) -> float:
        bundle = self.ensure_trained()
        normalized_case = normalize_case(case_data)
        case_df = pd.DataFrame([normalized_case], columns=[CASE_ID_COLUMN, *FEATURE_COLUMNS]).drop(
            columns=[CASE_ID_COLUMN]
        )
        preprocessor: ColumnTransformer = bundle["preprocessor"]
        model: xgb.XGBRegressor = bundle["model"]
        encoded_case = preprocessor.transform(case_df)
        return max(0.0, float(model.predict(encoded_case)[0]))

    def recommend(
        self,
        case_data: dict[str, Any],
        decision_result: DecisionResult | None = None,
    ) -> AgreementRecommendation:
        bundle = self.ensure_trained()
        normalized_case = normalize_case(case_data)
        predicted_condemnation = self.predict_condemnation(normalized_case)

        probabilidade_exito = (
            decision_result.probabilidade_exito if decision_result is not None else 0.35
        )
        subsidios_ausentes = (
            len(decision_result.subsidios_ausentes_criticos)
            if decision_result is not None
            else 2
        )
        valor_causa = float(normalized_case["Valor da causa"])

        calibration = bundle.get("calibration", {})
        residual_q20 = float(calibration.get("residual_q20", -0.15))
        residual_q50 = float(calibration.get("residual_q50", 0.15))
        residual_q80 = float(calibration.get("residual_q80", 0.60))
        cause_ratio_q20 = float(calibration.get("cause_ratio_q20", 0.50))
        cause_ratio_q50 = float(calibration.get("cause_ratio_q50", 0.74))
        cause_ratio_q80 = float(calibration.get("cause_ratio_q80", 0.89))

        predicted_p20 = max(0.0, predicted_condemnation * (1.0 + residual_q20))
        predicted_p50 = max(0.0, predicted_condemnation * (1.0 + residual_q50))
        predicted_p80 = max(0.0, predicted_condemnation * (1.0 + residual_q80))

        total_docs = max(1, len(DOCUMENT_COLUMNS))
        docs_presentes = total_docs - max(0, subsidios_ausentes)
        cobertura_documental = docs_presentes / total_docs
        tolerancia_risco = _clip01(probabilidade_exito * cobertura_documental)
        aversao_risco = 1.0 - tolerancia_risco

        max_cause_ratio = cause_ratio_q50 + (aversao_risco * (cause_ratio_q80 - cause_ratio_q50))
        min_cause_ratio = cause_ratio_q20

        faixa_negociacao_max = min(
            predicted_p80,
            predicted_condemnation,
            valor_causa * max_cause_ratio if valor_causa > 0 else predicted_condemnation,
        )
        faixa_negociacao_min = max(
            predicted_p20,
            valor_causa * min_cause_ratio if valor_causa > 0 else 0.0,
        )
        faixa_negociacao_min = min(faixa_negociacao_min, faixa_negociacao_max)

        valor_sugerido = faixa_negociacao_min + aversao_risco * (
            faixa_negociacao_max - faixa_negociacao_min
        )
        valor_sugerido = min(valor_sugerido, faixa_negociacao_max)
        valor_sugerido = max(valor_sugerido, faixa_negociacao_min)
        valor_sugerido = min(valor_sugerido, predicted_p50)
        valor_sugerido = max(valor_sugerido, faixa_negociacao_min)

        if valor_causa > 0:
            valor_sugerido = min(valor_sugerido, valor_causa)
            faixa_negociacao_min = min(faixa_negociacao_min, valor_causa)
            faixa_negociacao_max = min(faixa_negociacao_max, valor_causa)

        economia_estimada = max(valor_causa - valor_sugerido, 0.0)
        desconto_percentual = (
            _clip01(1.0 - (valor_sugerido / predicted_condemnation))
            if predicted_condemnation > 0
            else 0.0
        )

        racional = (
            "Oferta ancorada em quantis robustos do erro historico do modelo de condenacao, "
            "com menor sensibilidade a outliers. O valor sugerido e posicionado em faixa de "
            "risco conforme chance de exito da defesa e cobertura documental do caso."
        )

        return AgreementRecommendation(
            processo_id=normalized_case[CASE_ID_COLUMN],
            valor_causa_original=round(valor_causa, 2),
            valor_condenacao_previsto=round(predicted_condemnation, 2),
            valor_acordo_sugerido=round(valor_sugerido, 2),
            faixa_negociacao_min=round(max(faixa_negociacao_min, 0.0), 2),
            faixa_negociacao_max=round(max(faixa_negociacao_max, 0.0), 2),
            economia_estimada=round(economia_estimada, 2),
            desconto_percentual=round(desconto_percentual * 100, 2),
            racional=racional,
            metricas_modelo=bundle["metrics"],
        )
