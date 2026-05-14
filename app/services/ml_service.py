"""
Servicio de Machine Learning para riesgo académico.
Entrena/carga un modelo de regresión logística basado solo en notas por cohorte.
"""

from __future__ import annotations

import asyncio
import os
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.infrastructure.database import AsyncSessionFactory
from app.infrastructure.models.enrollment import Enrollment


class AcademicRiskService:
    """Servicio singleton para predicción de riesgo académico."""

    FEATURE_COLUMNS = ["nota_corte_1", "nota_corte_2", "nota_corte_final", "nota_total"]
    COHORT_FACTORS = {
        "first_cohort": 0.85,
        "second_cohort": 1.00,
        "third_cohort": 1.15,
    }
    COHORT_NAMES = {
        "first_cohort": "Corte 1",
        "second_cohort": "Corte 2",
        "third_cohort": "Corte final",
    }

    def __init__(self):
        self.model: LogisticRegression | None = None
        self.scaler: StandardScaler | None = None
        self.promedio_estudiantes_aprobados: Dict[str, float] | None = None
        self._load_model()
        self._load_reference_data()

    def _load_model(self):
        """Carga modelo/scaler. Si no existen, entrena con BD (fallback: dataset CSV)."""
        from app.core.config import settings

        modelo_path = settings.get_full_model_path()
        scaler_path = settings.get_full_scaler_path()
        dataset_path = settings.get_full_dataset_path()

        if os.path.exists(modelo_path) and os.path.exists(scaler_path):
            self.model = joblib.load(modelo_path)
            self.scaler = joblib.load(scaler_path)
            return

        X: np.ndarray | None = None
        y: np.ndarray | None = None

        db_data = None
        try:
            db_data = self._run_async(self._load_training_data_from_db())
        except Exception:
            db_data = None
        if db_data is not None:
            X, y = db_data
        elif os.path.exists(dataset_path):
            df = pd.read_csv(dataset_path)
            missing = [c for c in self.FEATURE_COLUMNS + ["riesgo_reprobacion"] if c not in df.columns]
            if missing:
                raise ValueError(
                    "Dataset incompatible para el modelo actual. "
                    f"Faltan columnas: {', '.join(missing)}"
                )
            X = df[self.FEATURE_COLUMNS].values
            y = df["riesgo_reprobacion"].values
        else:
            return

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = LogisticRegression(random_state=42, max_iter=1000, solver="lbfgs")
        self.model.fit(X_scaled, y)

        joblib.dump(self.model, modelo_path)
        joblib.dump(self.scaler, scaler_path)

    def _load_reference_data(self):
        """Promedios de referencia para comparación visual (fuente principal: BD)."""
        from app.core.config import settings

        reference_from_db = None
        try:
            reference_from_db = self._run_async(self._load_reference_data_from_db())
        except Exception:
            reference_from_db = None
        if reference_from_db is not None:
            self.promedio_estudiantes_aprobados = reference_from_db
            return

        dataset_path = settings.get_full_dataset_path()
        if os.path.exists(dataset_path):
            df = pd.read_csv(dataset_path)
            missing = [c for c in self.FEATURE_COLUMNS + ["riesgo_reprobacion"] if c not in df.columns]
            if missing:
                raise ValueError(
                    "Dataset incompatible para referencia ML. "
                    f"Faltan columnas: {', '.join(missing)}"
                )
            aprobados = df[df["riesgo_reprobacion"] == 0]
            if not aprobados.empty:
                self.promedio_estudiantes_aprobados = {
                    col: float(aprobados[col].mean()) for col in self.FEATURE_COLUMNS
                }
                return

        # Fallback defensivo para no bloquear arranque.
        self.promedio_estudiantes_aprobados = {
            "nota_corte_1": 3.5,
            "nota_corte_2": 3.5,
            "nota_corte_final": 3.5,
            "nota_total": 3.5,
        }

    def _run_async(self, coro):
        """
        Ejecuta una corrutina desde contexto sync.
        Durante boot normal no existe loop; si existe, ejecuta en un loop aislado.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    async def _load_training_data_from_db(self) -> tuple[np.ndarray, np.ndarray] | None:
        """
        Extrae features y etiqueta desde enrollments:
        - y=1 si final_grade < 3.0 (riesgo de reprobar), y=0 si >= 3.0.
        Requiere suficientes registros y al menos 2 clases.
        """
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(
                    Enrollment.first_cohort_grade,
                    Enrollment.second_cohort_grade,
                    Enrollment.third_cohort_grade,
                    Enrollment.final_grade,
                ).where(
                    Enrollment.first_cohort_grade.is_not(None),
                    Enrollment.second_cohort_grade.is_not(None),
                    Enrollment.third_cohort_grade.is_not(None),
                    Enrollment.final_grade.is_not(None),
                )
            )
            rows = result.all()

        if len(rows) < 20:
            return None

        X = np.array(
            [[float(r[0]), float(r[1]), float(r[2]), float(r[3])] for r in rows],
            dtype=float,
        )
        y = np.array([1 if float(r[3]) < 3.0 else 0 for r in rows], dtype=int)

        if np.unique(y).size < 2:
            return None
        return X, y

    async def _load_reference_data_from_db(self) -> Dict[str, float] | None:
        """
        Calcula promedio de aprobados desde enrollments con notas completas.
        Si no hay aprobados, usa promedio general con notas completas.
        """
        async with AsyncSessionFactory() as session:
            base_stmt = select(
                Enrollment.first_cohort_grade,
                Enrollment.second_cohort_grade,
                Enrollment.third_cohort_grade,
                Enrollment.final_grade,
            ).where(
                Enrollment.first_cohort_grade.is_not(None),
                Enrollment.second_cohort_grade.is_not(None),
                Enrollment.third_cohort_grade.is_not(None),
                Enrollment.final_grade.is_not(None),
            )

            approved_result = await session.execute(
                base_stmt.where(Enrollment.final_grade >= 3.0)
            )
            approved_rows = approved_result.all()

            rows = approved_rows
            if not rows:
                all_result = await session.execute(base_stmt)
                rows = all_result.all()

        if not rows:
            return None

        values = np.array(
            [[float(r[0]), float(r[1]), float(r[2]), float(r[3])] for r in rows],
            dtype=float,
        )
        means = values.mean(axis=0)
        return {
            "nota_corte_1": float(means[0]),
            "nota_corte_2": float(means[1]),
            "nota_corte_final": float(means[2]),
            "nota_total": float(means[3]),
        }

    def predict(self, features: List[float]) -> Dict:
        """Predice riesgo desde [corte_1, corte_2, corte_final, total]."""
        if not self.model or not self.scaler:
            raise RuntimeError("El modelo ML no está disponible.")
        if len(features) != len(self.FEATURE_COLUMNS):
            raise ValueError(
                f"Se esperaban {len(self.FEATURE_COLUMNS)} features "
                f"({', '.join(self.FEATURE_COLUMNS)}), llegaron {len(features)}."
            )

        data_array = np.array([features], dtype=float)
        data_scaled = self.scaler.transform(data_array)
        probabilidad = float(self.model.predict_proba(data_scaled)[0][1])

        return {
            "probability": probabilidad,
            "risk_level": self._classify_risk(probabilidad),
            "scaled_features": data_scaled[0].tolist(),
        }

    def predict_cohort_risk(
        self,
        *,
        cohort_key: str,
        nota_parcial: float,
        promedio_seguimiento: float,
        porcentaje_asistencia: float,
    ) -> Dict:
        """
        Predicción de riesgo por cohorte.

        Usa un modelo analítico (sigmoide) sobre 3 variables del cohorte:
        parcial, seguimiento y asistencia.
        """
        if cohort_key not in self.COHORT_FACTORS:
            raise ValueError("cohort_key inválido")

        parcial = float(nota_parcial)
        seguimiento = float(promedio_seguimiento)
        asistencia = float(porcentaje_asistencia)

        parcial_deficit = max(0.0, 3.0 - parcial) / 3.0
        seguimiento_deficit = max(0.0, 3.0 - seguimiento) / 3.0
        asistencia_deficit = max(0.0, 80.0 - asistencia) / 80.0

        # Parcial pesa más (aprendizaje consolidado), luego seguimiento, luego asistencia.
        base_score = (
            (0.55 * parcial_deficit)
            + (0.30 * seguimiento_deficit)
            + (0.15 * asistencia_deficit)
        )

        cohort_factor = self.COHORT_FACTORS[cohort_key]
        adjusted_score = base_score * cohort_factor

        # Escalamiento logístico para obtener probabilidad [0, 1].
        z = (adjusted_score - 0.32) * 5.0
        probabilidad = 1.0 / (1.0 + np.exp(-z))
        probabilidad = float(np.clip(probabilidad, 0.0, 1.0))

        return {
            "cohort_key": cohort_key,
            "cohort_name": self.COHORT_NAMES[cohort_key],
            "probability": probabilidad,
            "risk_level": self._classify_risk(probabilidad),
            "component_scores": {
                "parcial_deficit": round(parcial_deficit, 4),
                "seguimiento_deficit": round(seguimiento_deficit, 4),
                "asistencia_deficit": round(asistencia_deficit, 4),
                "base_score": round(base_score, 4),
                "cohort_factor": cohort_factor,
                "adjusted_score": round(adjusted_score, 4),
                "z": round(float(z), 4),
            },
        }

    def _classify_risk(self, prob: float) -> str:
        if prob >= 0.7:
            return "ALTO"
        if prob >= 0.4:
            return "MEDIO"
        return "BAJO"

    def generar_analisis_ia(self, datos_estudiante: Dict, probabilidad_riesgo: float) -> str:
        """Análisis sencillo y entendible para el estudiante, basado en cohortes."""
        porcentaje = probabilidad_riesgo * 100
        nivel = self._classify_risk(probabilidad_riesgo)

        c1 = float(datos_estudiante["nota_corte_1"])
        c2 = float(datos_estudiante["nota_corte_2"])
        c3 = float(datos_estudiante["nota_corte_final"])
        total = float(datos_estudiante["nota_total"])

        lineas: list[str] = []
        if nivel == "ALTO":
            lineas.append(f"Riesgo alto ({porcentaje:.1f}%). Necesitas intervenir ya.")
        elif nivel == "MEDIO":
            lineas.append(f"Riesgo medio ({porcentaje:.1f}%). Estás a tiempo de mejorar.")
        else:
            lineas.append(f"Riesgo bajo ({porcentaje:.1f}%). Vas en buen camino.")

        lineas.append(
            f"Notas actuales — Corte 1: {c1:.1f}, Corte 2: {c2:.1f}, "
            f"Corte final: {c3:.1f}, Total: {total:.1f}."
        )

        debiles: list[str] = []
        if c1 < 3.0:
            debiles.append("Corte 1")
        if c2 < 3.0:
            debiles.append("Corte 2")
        if c3 < 3.0:
            debiles.append("Corte final")

        if debiles:
            lineas.append("Áreas a reforzar: " + ", ".join(debiles) + ".")
            lineas.append("Prioriza preparación para la actividad final y recuperación de temas base.")
        else:
            lineas.append("No hay cohortes críticas por debajo de 3.0. Mantén el ritmo.")

        return "\n".join(lineas)

    def calcular_detalles_matematicos(
        self,
        features_scaled: np.ndarray,
        probabilidad_riesgo: float,
    ) -> Dict:
        """Detalles de la regresión logística para transparencia."""
        coeficientes = self.model.coef_[0].tolist()
        intercepto = float(self.model.intercept_[0])
        z = intercepto + np.dot(features_scaled, self.model.coef_[0])
        valor_z = float(z)

        terminos = [f"{intercepto:.4f}"]
        for coef, feat_scaled in zip(coeficientes, features_scaled):
            terminos.append(f"({coef:.4f} × {feat_scaled:.4f})")

        return {
            "formula_logit": r"z = \beta_0 + \sum_{i=1}^{n} (\beta_i \cdot x_i^{\text{scaled}})",
            "formula_sigmoide": r"P(\text{riesgo}) = \frac{1}{1 + e^{-z}}",
            "feature_names": ["Corte 1", "Corte 2", "Corte Final", "Total"],
            "features_scaled": features_scaled.tolist(),
            "coeficientes": coeficientes,
            "intercepto": intercepto,
            "calculo_logit_texto": f"z = {' + '.join(terminos)} = {valor_z:.4f}",
            "valor_z": valor_z,
            "calculo_probabilidad_texto": (
                f"P(riesgo) = 1 / (1 + e^(-{valor_z:.4f})) = {probabilidad_riesgo:.4f}"
            ),
        }

    def get_promedio_aprobados(self) -> Dict[str, float]:
        return self.promedio_estudiantes_aprobados


_risk_service: AcademicRiskService | None = None


def get_risk_service() -> AcademicRiskService:
    global _risk_service
    if _risk_service is None:
        _risk_service = AcademicRiskService()
    return _risk_service
