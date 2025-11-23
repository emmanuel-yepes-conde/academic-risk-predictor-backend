"""
Servicio de Machine Learning
Encapsula la lógica de predicción de riesgo académico
Patrón Singleton para cargar el modelo una sola vez
"""

import joblib
import numpy as np
import pandas as pd
import os
from typing import Dict, List
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


class AcademicRiskService:
    """
    Servicio singleton para predicción de riesgo académico
    Carga el modelo y scaler una sola vez al iniciar la aplicación
    """
    
    def __init__(self):
        self.model: LogisticRegression = None
        self.scaler: StandardScaler = None
        self.promedio_estudiantes_aprobados: Dict[str, float] = None
        self._load_model()
        self._load_reference_data()
    
    def _load_model(self):
        """
        Carga el modelo y scaler desde archivos .joblib
        Si no existen, entrena desde cero con el dataset
        """
        # Importar settings para obtener rutas configuradas
        from app.core.config import settings
        
        modelo_path = settings.get_full_model_path()
        scaler_path = settings.get_full_scaler_path()
        dataset_path = settings.get_full_dataset_path()
        
        # Si los archivos del modelo YA existen, solo cargarlos
        if os.path.exists(modelo_path) and os.path.exists(scaler_path):
            print("✅ Cargando modelo y scaler existentes...")
            self.model = joblib.load(modelo_path)
            self.scaler = joblib.load(scaler_path)
            print(f"✅ Modelo cargado desde: {modelo_path}")
            print(f"✅ Scaler cargado desde: {scaler_path}")
        else:
            # Si NO existen, entrenar desde cero
            print("🔄 Modelo no encontrado. Iniciando entrenamiento...")
            
            # Verificar que existe el dataset
            if not os.path.exists(dataset_path):
                raise FileNotFoundError(
                    f"❌ No se encontró el archivo de datos: {dataset_path}\n"
                    f"Asegúrate de que el archivo CSV esté en el directorio raíz del proyecto"
                )
            
            # 1. Cargar el dataset
            print(f"📊 Cargando dataset desde {dataset_path}...")
            df = pd.read_csv(dataset_path)
            print(f"✅ Dataset cargado: {len(df)} registros, {len(df.columns)} columnas")
            
            # 2. Preparar los datos (X, y)
            feature_columns = [
                'promedio_asistencia',
                'promedio_seguimiento',
                'nota_parcial_1',
                'inicios_sesion_plataforma',
                'uso_tutorias'
            ]
            
            X = df[feature_columns].values
            y = df['riesgo_reprobacion'].values
            
            print(f"📈 Datos preparados: X shape = {X.shape}, y shape = {y.shape}")
            
            # 3. Instanciar y ajustar el StandardScaler
            print("🔧 Escalando variables con StandardScaler...")
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)
            print("✅ Variables escaladas correctamente")
            
            # 4. Entrenar el modelo de Regresión Logística
            print("🤖 Entrenando modelo de Regresión Logística...")
            self.model = LogisticRegression(
                random_state=42,
                max_iter=1000,
                solver='lbfgs'
            )
            self.model.fit(X_scaled, y)
            print("✅ Modelo entrenado exitosamente")
            
            # 5. Guardar el modelo y el scaler para uso futuro
            print("💾 Guardando modelo y scaler...")
            joblib.dump(self.model, modelo_path)
            joblib.dump(self.scaler, scaler_path)
            print(f"✅ Modelo guardado en: {modelo_path}")
            print(f"✅ Scaler guardado en: {scaler_path}")
            
            # Mostrar información del modelo
            print("\n📊 Información del modelo entrenado:")
            print(f"   Intercepto (β₀): {self.model.intercept_[0]:.4f}")
            print(f"   Coeficientes (β₁...β₅):")
            for i, (col, coef) in enumerate(zip(feature_columns, self.model.coef_[0])):
                print(f"      {col}: {coef:.4f}")
    
    def _load_reference_data(self):
        """
        Carga datos de referencia (promedios de estudiantes aprobados)
        para comparación en el gráfico de radar
        """
        from app.core.config import settings
        dataset_path = settings.get_full_dataset_path()
        
        print("\n📊 Calculando promedios de estudiantes aprobados...")
        df = pd.read_csv(dataset_path)
        estudiantes_aprobados = df[df['riesgo_reprobacion'] == 0]
        
        self.promedio_estudiantes_aprobados = {
            "promedio_asistencia": float(estudiantes_aprobados['promedio_asistencia'].mean()),
            "promedio_seguimiento": float(estudiantes_aprobados['promedio_seguimiento'].mean()),
            "nota_parcial_1": float(estudiantes_aprobados['nota_parcial_1'].mean()),
            "inicios_sesion_plataforma": float(estudiantes_aprobados['inicios_sesion_plataforma'].mean()),
            "uso_tutorias": float(estudiantes_aprobados['uso_tutorias'].mean())
        }
        
        print("✅ Promedios calculados:")
        for key, value in self.promedio_estudiantes_aprobados.items():
            print(f"   {key}: {value:.2f}")
    
    def predict(self, features: List[float]) -> Dict:
        """
        Realiza una predicción de riesgo académico
        
        Args:
            features: Lista con [asistencia, seguimiento, parcial_1, logins, tutorias]
        
        Returns:
            Diccionario con probability, risk_level y scaled_features
        """
        if not self.model or not self.scaler:
            raise RuntimeError("El modelo ML no está disponible.")
        
        # Convertir a formato numpy (1 muestra, n features)
        data_array = np.array([features])
        
        # Escalar los datos usando el scaler entrenado
        data_scaled = self.scaler.transform(data_array)
        
        # Predicción de probabilidad (Clase 1 = Riesgo)
        probabilidad = float(self.model.predict_proba(data_scaled)[0][1])
        
        return {
            "probability": probabilidad,
            "risk_level": self._classify_risk(probabilidad),
            "scaled_features": data_scaled[0].tolist()
        }
    
    def _classify_risk(self, prob: float) -> str:
        """
        Clasifica el nivel de riesgo según la probabilidad
        Umbrales de negocio definidos en el proyecto
        """
        if prob >= 0.7:
            return "ALTO"
        if prob >= 0.4:
            return "MEDIO"
        return "BAJO"
    
    def generar_analisis_ia(self, datos_estudiante: Dict, probabilidad_riesgo: float) -> str:
        """
        Genera un análisis personalizado basado en patrones y reglas inteligentes.
        Sistema de consejería académica autónomo sin dependencias externas.
        
        Args:
            datos_estudiante: Diccionario con los datos del estudiante
            probabilidad_riesgo: Probabilidad de riesgo (0-1)
        
        Returns:
            Texto del análisis personalizado con consejos específicos
        """
        porcentaje_riesgo = probabilidad_riesgo * 100
        nivel_riesgo = "ALTO" if porcentaje_riesgo >= 70 else "MEDIO" if porcentaje_riesgo >= 40 else "BAJO"
        
        # Extraer datos del estudiante
        asistencia = datos_estudiante['promedio_asistencia']
        seguimiento = datos_estudiante['promedio_seguimiento']
        parcial = datos_estudiante['nota_parcial_1']
        logins = datos_estudiante['inicios_sesion_plataforma']
        usa_tutorias = datos_estudiante['uso_tutorias']
        
        # === ANÁLISIS INICIAL ===
        analisis = []
        
        # Determinar mensaje inicial según nivel de riesgo
        if nivel_riesgo == "ALTO":
            analisis.append("⚠️ **SITUACIÓN DE RIESGO ALTO**")
            analisis.append(f"Tu probabilidad de reprobación es del {porcentaje_riesgo:.1f}%. Esta situación requiere acciones inmediatas y concretas.")
        elif nivel_riesgo == "MEDIO":
            analisis.append("⚠️ **SITUACIÓN DE RIESGO MODERADO**")
            analisis.append(f"Tu probabilidad de reprobación es del {porcentaje_riesgo:.1f}%. Aún estás a tiempo de mejorar con cambios estratégicos.")
        else:
            analisis.append("✅ **SITUACIÓN FAVORABLE**")
            analisis.append(f"Tu probabilidad de reprobación es del {porcentaje_riesgo:.1f}%. Vas por buen camino, pero siempre hay espacio para mejorar.")
        
        analisis.append("")  # Línea en blanco
        
        # === IDENTIFICAR ÁREAS PROBLEMÁTICAS ===
        problemas = []
        fortalezas = []
        
        # Análisis de Asistencia
        if asistencia < 70:
            problemas.append(("asistencia", f"Tu asistencia ({asistencia:.1f}%) está muy por debajo del mínimo recomendado (85%)"))
        elif asistencia < 85:
            problemas.append(("asistencia", f"Tu asistencia ({asistencia:.1f}%) necesita mejorar para alcanzar el 85% recomendado"))
        else:
            fortalezas.append(f"Excelente asistencia ({asistencia:.1f}%)")
        
        # Análisis de Seguimiento
        if seguimiento < 2.5:
            problemas.append(("seguimiento", f"Tu seguimiento académico ({seguimiento:.1f}/5.0) es bajo, indica poca participación"))
        elif seguimiento < 3.5:
            problemas.append(("seguimiento", f"Tu seguimiento ({seguimiento:.1f}/5.0) puede mejorar con más participación activa"))
        else:
            fortalezas.append(f"Buen nivel de seguimiento ({seguimiento:.1f}/5.0)")
        
        # Análisis de Nota Parcial
        if parcial < 2.5:
            problemas.append(("parcial", f"Tu nota del parcial ({parcial:.1f}/5.0) está por debajo de 2.5, requiere refuerzo urgente"))
        elif parcial < 3.0:
            problemas.append(("parcial", f"Tu nota del parcial ({parcial:.1f}/5.0) necesita mejorar para aprobar con seguridad"))
        elif parcial < 3.5:
            problemas.append(("parcial", f"Tu nota del parcial ({parcial:.1f}/5.0) es aceptable pero mejorable"))
        else:
            fortalezas.append(f"Buen desempeño en el parcial ({parcial:.1f}/5.0)")
        
        # Análisis de Logins (Plataforma)
        if logins < 30:
            problemas.append(("logins", f"Tus inicios de sesión ({logins}) son muy bajos, indica poca interacción con el material"))
        elif logins < 40:
            problemas.append(("logins", f"Podrías aumentar tu uso de la plataforma (actualmente {logins} logins)"))
        else:
            fortalezas.append(f"Buen uso de la plataforma ({logins} logins)")
        
        # Análisis de Tutorías
        if usa_tutorias < 2:
            problemas.append(("tutorias", "No estás aprovechando suficientemente el servicio de tutorías disponible"))
        else:
            fortalezas.append("Aprovechas las tutorías disponibles")
        
        # === MOSTRAR DIAGNÓSTICO ===
        if fortalezas:
            analisis.append("**🌟 Tus Fortalezas:**")
            for f in fortalezas:
                analisis.append(f"• {f}")
            analisis.append("")
        
        if problemas:
            analisis.append("**⚠️ Áreas que Requieren Atención:**")
            for tipo, desc in problemas:
                analisis.append(f"• {desc}")
            analisis.append("")
        
        # === GENERAR CONSEJOS PERSONALIZADOS ===
        analisis.append("**💡 Plan de Acción Personalizado:**")
        analisis.append("")
        
        consejos = []
        problemas_dict = dict(problemas)
        
        # 1. Consejo sobre ASISTENCIA (máxima prioridad si hay problema)
        if "asistencia" in problemas_dict:
            if asistencia < 70:
                consejos.append({
                    "prioridad": 1,
                    "icono": "🎯",
                    "titulo": "URGENTE: Mejora tu Asistencia",
                    "descripcion": f"Actualmente tienes {asistencia:.1f}% de asistencia. Objetivo inmediato: llegar al 85%.",
                    "acciones": [
                        "Organiza tu horario para no perderte ninguna clase",
                        "Si tienes problemas de transporte u otros, habla con tu coordinador",
                        f"Necesitas asistir consistentemente para recuperar terreno"
                    ]
                })
            else:
                consejos.append({
                    "prioridad": 2,
                    "icono": "📅",
                    "titulo": "Aumenta tu Asistencia",
                    "descripcion": f"Con {asistencia:.1f}%, estás cerca del objetivo. ¡Un esfuerzo más!",
                    "acciones": [
                        "Asiste a todas las clases las próximas semanas",
                        "Llega puntual para aprovechar toda la sesión"
                    ]
                })
        
        # 2. Consejo sobre PARCIAL (crítico si está bajo)
        if "parcial" in problemas_dict:
            if parcial < 2.5:
                consejos.append({
                    "prioridad": 1,
                    "icono": "📚",
                    "titulo": "URGENTE: Refuerza tus Conocimientos",
                    "descripcion": f"Tu nota de {parcial:.1f}/5.0 indica dificultades con el contenido.",
                    "acciones": [
                        "Solicita retroalimentación detallada del parcial",
                        "Identifica los temas específicos donde fallaste",
                        "Dedica al menos 2 horas diarias de estudio estructurado",
                        "Forma grupos de estudio con compañeros que dominen el tema"
                    ]
                })
            elif parcial < 3.0:
                consejos.append({
                    "prioridad": 2,
                    "icono": "📝",
                    "titulo": "Mejora tu Desempeño Académico",
                    "descripcion": f"Tu {parcial:.1f}/5.0 es aprobatorio pero justo. Necesitas subir para el siguiente.",
                    "acciones": [
                        "Revisa los errores del primer parcial",
                        "Practica con ejercicios similares a los del examen",
                        "Consulta con el profesor tus dudas específicas"
                    ]
                })
            else:
                consejos.append({
                    "prioridad": 3,
                    "icono": "⭐",
                    "titulo": "Mantén tu Rendimiento",
                    "descripcion": f"Con {parcial:.1f}/5.0 vas bien. Mantén el nivel.",
                    "acciones": [
                        "Continúa estudiando regularmente",
                        "Profundiza en temas más complejos"
                    ]
                })
        
        # 3. Consejo sobre TUTORÍAS
        if "tutorias" in problemas_dict and porcentaje_riesgo >= 40:
            consejos.append({
                "prioridad": 2,
                "icono": "👨‍🏫",
                "titulo": "Aprovecha las Tutorías",
                "descripcion": "Las tutorías pueden marcar la diferencia en tu desempeño.",
                "acciones": [
                    "Agenda sesiones de tutoría esta misma semana",
                    "Prepara preguntas específicas antes de cada sesión",
                    "Los estudiantes que usan tutorías tienen 45% más probabilidad de aprobar"
                ]
            })
        
        # 4. Consejo sobre SEGUIMIENTO/PARTICIPACIÓN
        if "seguimiento" in problemas_dict:
            if seguimiento < 2.5:
                consejos.append({
                    "prioridad": 2,
                    "icono": "🙋",
                    "titulo": "Aumenta tu Participación",
                    "descripcion": f"Tu seguimiento de {seguimiento:.1f}/5.0 indica poca interacción en clase.",
                    "acciones": [
                        "Participa activamente haciendo preguntas",
                        "Completa todas las tareas y actividades a tiempo",
                        "Interactúa más con el profesor y compañeros"
                    ]
                })
            else:
                consejos.append({
                    "prioridad": 3,
                    "icono": "💬",
                    "titulo": "Mejora tu Participación",
                    "descripcion": f"Con {seguimiento:.1f}/5.0 de seguimiento, puedes involucrarte más.",
                    "acciones": [
                        "Participa al menos una vez por clase",
                        "Completa tareas extras si están disponibles"
                    ]
                })
        
        # 5. Consejo sobre PLATAFORMA
        if "logins" in problemas_dict and porcentaje_riesgo >= 40:
            consejos.append({
                "prioridad": 3,
                "icono": "💻",
                "titulo": "Usa Más la Plataforma Educativa",
                "descripcion": f"Con {logins} logins, no estás aprovechando todos los recursos.",
                "acciones": [
                    "Ingresa diariamente para revisar material nuevo",
                    "Revisa videos, lecturas y recursos adicionales",
                    "Haz los ejercicios de práctica disponibles"
                ]
            })
        
        # 6. Consejo GENERAL sobre organización
        if nivel_riesgo == "ALTO":
            consejos.append({
                "prioridad": 1,
                "icono": "🗓️",
                "titulo": "Crea un Plan de Recuperación",
                "descripcion": "Necesitas un cambio significativo en tu enfoque académico.",
                "acciones": [
                    "Establece un horario fijo de estudio (mínimo 10 horas semanales)",
                    "Elimina distracciones durante las horas de estudio",
                    "Comunícate con tu profesor para acordar un plan de mejora",
                    "Considera reducir horas de trabajo u otras actividades si es posible"
                ]
            })
        
        # Ordenar consejos por prioridad
        consejos.sort(key=lambda x: x["prioridad"])
        
        # Limitar a los 3-4 consejos más importantes
        consejos_mostrar = consejos[:4] if nivel_riesgo == "ALTO" else consejos[:3]
        
        # Formatear consejos
        for i, consejo in enumerate(consejos_mostrar, 1):
            analisis.append(f"**{consejo['icono']} {i}. {consejo['titulo']}**")
            analisis.append(consejo['descripcion'])
            for accion in consejo['acciones']:
                analisis.append(f"   • {accion}")
            analisis.append("")
        
        # === MENSAJE MOTIVACIONAL FINAL ===
        analisis.append("---")
        if nivel_riesgo == "ALTO":
            analisis.append("⚡ **Recuerda:** Aunque la situación es difícil, NO es imposible. Muchos estudiantes en tu situación han logrado recuperarse con esfuerzo consistente. ¡Tú también puedes!")
        elif nivel_riesgo == "MEDIO":
            analisis.append("💪 **Recuerda:** Estás a tiempo de cambiar el resultado. Con los ajustes correctos, puedes aprobar con buena nota.")
        else:
            analisis.append("🎉 **¡Excelente trabajo!** Mantén esta actitud y terminarás el curso exitosamente.")
        
        return "\n".join(analisis)
    
    def calcular_detalles_matematicos(
        self,
        features_scaled: np.ndarray,
        probabilidad_riesgo: float
    ) -> Dict:
        """
        Calcula todos los detalles matemáticos de la predicción para transparencia.
        Implementa las fórmulas de Regresión Logística.
        
        Args:
            features_scaled: Array con las características escaladas
            probabilidad_riesgo: Probabilidad calculada por el modelo
        
        Returns:
            Diccionario con todos los detalles matemáticos
        """
        # Obtener coeficientes e intercepto del modelo
        coeficientes = self.model.coef_[0].tolist()
        intercepto = float(self.model.intercept_[0])
        
        # Calcular z (logit) = β₀ + Σ(βᵢ × xᵢ_scaled)
        z = intercepto + np.dot(features_scaled, self.model.coef_[0])
        valor_z = float(z)
        
        # Construir el cálculo paso a paso
        terminos = [f"{intercepto:.4f}"]  # Intercepto
        
        feature_names = [
            "Asistencia",
            "Seguimiento",
            "Parcial 1",
            "Logins",
            "Tutorías"
        ]
        
        for coef, feat_scaled in zip(coeficientes, features_scaled):
            impacto = coef * feat_scaled
            terminos.append(f"({coef:.4f} × {feat_scaled:.4f})")
        
        calculo_logit_texto = f"z = {' + '.join(terminos)} = {valor_z:.4f}"
        
        # Calcular probabilidad usando la función sigmoide: P = 1 / (1 + e^(-z))
        calculo_probabilidad_texto = f"P(riesgo) = 1 / (1 + e^(-{valor_z:.4f})) = {probabilidad_riesgo:.4f}"
        
        return {
            "formula_logit": r"z = \beta_0 + \sum_{i=1}^{n} (\beta_i \cdot x_i^{\text{scaled}})",
            "formula_sigmoide": r"P(\text{riesgo}) = \frac{1}{1 + e^{-z}}",
            "features_scaled": features_scaled.tolist(),
            "coeficientes": coeficientes,
            "intercepto": intercepto,
            "calculo_logit_texto": calculo_logit_texto,
            "valor_z": valor_z,
            "calculo_probabilidad_texto": calculo_probabilidad_texto
        }
    
    def get_promedio_aprobados(self) -> Dict[str, float]:
        """Retorna los promedios de estudiantes aprobados"""
        return self.promedio_estudiantes_aprobados


# Instancia Global (Singleton)
# Se carga UNA SOLA VEZ al iniciar la aplicación
risk_service = AcademicRiskService()

