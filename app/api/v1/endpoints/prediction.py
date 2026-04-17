"""
Endpoints de Predicción
Controladores que manejan las peticiones HTTP
Solo orquestación, sin lógica de negocio
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.student import StudentInput, PredictionOutput, ChatInput, ChatOutput
from app.services.ml_service import AcademicRiskService, risk_service
from app.application.services.consent_service import ConsentService
from app.application.services.ml_service import MLApplicationService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.consent_repository import ConsentRepository
from typing import Dict, Optional
import numpy as np

router = APIRouter()


# Helper para Inyección de Dependencias
def get_ml_service() -> AcademicRiskService:
    """Retorna la instancia singleton del servicio de ML"""
    return risk_service


def get_ml_application_service(
    session: AsyncSession = Depends(get_session),
    ml_service: AcademicRiskService = Depends(get_ml_service),
) -> MLApplicationService:
    """Construye MLApplicationService con ConsentService inyectado."""
    consent_repo = ConsentRepository(session)
    consent_service = ConsentService(consent_repo)
    return MLApplicationService(ml_service, consent_service)


@router.post("/predict", response_model=PredictionOutput)
async def predecir_riesgo(
    estudiante: StudentInput,
    student_id: Optional[UUID] = None,
    service: AcademicRiskService = Depends(get_ml_service),
    ml_app_service: MLApplicationService = Depends(get_ml_application_service),
):
    """
    Endpoint principal para predecir el riesgo de reprobación de un estudiante.
    
    Este endpoint realiza:
    1. Escalado de las características de entrada
    2. Predicción de probabilidad de riesgo
    3. Generación de análisis con IA
    4. Cálculo de detalles matemáticos completos
    5. Preparación de datos para gráfico de radar
    
    Args:
        estudiante: Datos del estudiante (asistencia, seguimiento, parcial, logins, tutorías)
        service: Servicio de ML (inyectado)
    
    Returns:
        Diccionario con predicción, análisis IA, datos para radar y detalles matemáticos
    """
    try:
        # 1. Preparar los datos de entrada
        datos_estudiante = {
            "promedio_asistencia": estudiante.promedio_asistencia,
            "promedio_seguimiento": estudiante.promedio_seguimiento,
            "nota_parcial_1": estudiante.nota_parcial_1,
            "inicios_sesion_plataforma": estudiante.inicios_sesion_plataforma,
            "uso_tutorias": estudiante.uso_tutorias
        }
        
        # Mapeo estricto para garantizar el orden de columnas del entrenamiento
        feature_vector = [
            estudiante.promedio_asistencia,
            estudiante.promedio_seguimiento,
            estudiante.nota_parcial_1,
            estudiante.inicios_sesion_plataforma,
            estudiante.uso_tutorias
        ]
        
        # 2. Verificar consentimiento ML si se proporciona student_id (Req 8.2, 8.3)
        if student_id is not None:
            result = await ml_app_service.predict_with_consent_check(student_id, feature_vector)
        else:
            result = service.predict(feature_vector)
        probabilidad_riesgo = result["probability"]
        nivel_riesgo = result["risk_level"]
        features_scaled = np.array(result["scaled_features"])
        
        # 3. Generar análisis personalizado basado en patrones
        print(f"\n🧠 Generando análisis personalizado para estudiante con {probabilidad_riesgo*100:.1f}% de riesgo...")
        analisis_ia = service.generar_analisis_ia(datos_estudiante, probabilidad_riesgo)
        
        # 4. Calcular detalles matemáticos completos
        detalles_matematicos = service.calcular_detalles_matematicos(
            features_scaled,
            probabilidad_riesgo
        )
        
        # 5. Preparar datos para el gráfico de radar
        promedio_aprobados = service.get_promedio_aprobados()
        datos_radar = {
            "labels": [
                "Asistencia (%)",
                "Seguimiento",
                "Parcial 1",
                "Logins",
                "Tutorías"
            ],
            "estudiante": [
                estudiante.promedio_asistencia,
                estudiante.promedio_seguimiento,
                estudiante.nota_parcial_1,
                estudiante.inicios_sesion_plataforma,
                estudiante.uso_tutorias
            ],
            "promedio_aprobado": [
                promedio_aprobados["promedio_asistencia"],
                promedio_aprobados["promedio_seguimiento"],
                promedio_aprobados["nota_parcial_1"],
                promedio_aprobados["inicios_sesion_plataforma"],
                promedio_aprobados["uso_tutorias"]
            ]
        }
        
        # 6. Construir y retornar la respuesta completa
        respuesta = PredictionOutput(
            probabilidad_riesgo=probabilidad_riesgo,
            porcentaje_riesgo=probabilidad_riesgo * 100,
            nivel_riesgo=nivel_riesgo,
            analisis_ia=analisis_ia,
            datos_radar=datos_radar,
            detalles_matematicos=detalles_matematicos
        )
        
        print(f"✅ Predicción completada: {probabilidad_riesgo*100:.2f}% de riesgo")
        
        return respuesta
        
    except Exception as e:
        print(f"❌ Error en predicción: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la predicción: {str(e)}"
        )


@router.post("/chat", response_model=ChatOutput)
async def chat_consejero(chat_input: ChatInput):
    """
    Endpoint para el chat inteligente con el consejero virtual.
    Responde preguntas personalizadas sobre el rendimiento académico del estudiante.
    
    Args:
        chat_input: Pregunta y datos del estudiante
    
    Returns:
        Respuesta del consejero virtual
    """
    try:
        pregunta = chat_input.pregunta.lower()
        datos = chat_input.datos_estudiante
        prediccion = chat_input.prediccion_actual
        
        # Analizar la pregunta y generar respuesta
        respuesta = ""
        
        # Preguntas sobre cómo mejorar
        if any(palabra in pregunta for palabra in ["mejorar", "mejor", "subir", "aumentar"]):
            respuesta = f"""**💡 Cómo Mejorar Tu Rendimiento:**

Con tus datos actuales:
• Asistencia: {datos.promedio_asistencia}%
• Seguimiento: {datos.promedio_seguimiento}/5.0
• Nota Parcial 1: {datos.nota_parcial_1}/5.0
• Logins: {datos.inicios_sesion_plataforma}
• Tutorías: {datos.uso_tutorias}

**🎯 Áreas de Mejora:**

"""
            # Analizar cada área
            if datos.promedio_asistencia < 80:
                respuesta += "• **Asistencia:** Intenta llegar al 90% o más. Cada clase perdida es conocimiento que no recuperas fácilmente.\n"
            
            if datos.promedio_seguimiento < 3.5:
                respuesta += "• **Participación:** Participa más en clase, haz preguntas, completa tareas a tiempo.\n"
            
            if datos.nota_parcial_1 < 3.5:
                respuesta += "• **Notas:** Dedica más tiempo al estudio. Forma grupos de estudio, usa recursos adicionales.\n"
            
            if datos.inicios_sesion_plataforma < 20:
                respuesta += "• **Plataforma:** Ingresa más seguido (ideal: 3-4 veces por semana). Revisa materiales, foros, anuncios.\n"
            
            if datos.uso_tutorias < 3:
                respuesta += "• **Tutorías:** ¡Úsalas! Son gratuitas y te ayudan mucho. Intenta al menos 3-5 sesiones.\n"
                
            respuesta += "\n**⭐ Recomendación Principal:** Enfócate primero en tu área más débil y luego avanza a las demás."
        
        # Preguntas sobre áreas débiles
        elif any(palabra in pregunta for palabra in ["débil", "debil", "peor", "malo", "bajo", "baja"]):
            areas_debiles = []
            
            if datos.promedio_asistencia < 75:
                areas_debiles.append(("Asistencia", datos.promedio_asistencia, "%"))
            if datos.promedio_seguimiento < 3.0:
                areas_debiles.append(("Seguimiento", datos.promedio_seguimiento, "/5.0"))
            if datos.nota_parcial_1 < 3.0:
                areas_debiles.append(("Nota Parcial 1", datos.nota_parcial_1, "/5.0"))
            if datos.inicios_sesion_plataforma < 15:
                areas_debiles.append(("Uso de Plataforma", datos.inicios_sesion_plataforma, " logins"))
            if datos.uso_tutorias < 2:
                areas_debiles.append(("Uso de Tutorías", datos.uso_tutorias, " sesiones"))
            
            if areas_debiles:
                respuesta = "**⚠️ Tus Áreas Más Débiles:**\n\n"
                for i, (area, valor, unidad) in enumerate(areas_debiles, 1):
                    respuesta += f"{i}. **{area}:** {valor}{unidad}\n"
                respuesta += "\n💪 **Consejo:** Prioriza estas áreas en ese orden."
            else:
                respuesta = "**✅ ¡Excelente!** No tienes áreas particularmente débiles. Mantén tu buen desempeño en todas las áreas."
        
        # Preguntas sobre qué necesita para aprobar
        elif any(palabra in pregunta for palabra in ["aprobar", "pasar", "necesito", "requiero"]):
            if prediccion and prediccion.get("porcentaje_riesgo"):
                riesgo = prediccion["porcentaje_riesgo"]
                respuesta = f"""**📊 Análisis para Aprobar:**

Tu riesgo actual de reprobación es: **{riesgo:.1f}%**

"""
                if riesgo < 30:
                    respuesta += "✅ **Vas muy bien!** Con tu desempeño actual, tienes alta probabilidad de aprobar.\n\n**Recomendación:** Mantén tu nivel actual en todas las áreas."
                elif riesgo < 50:
                    respuesta += "⚠️ **Estás en la zona de riesgo medio.** Necesitas mejorar algunas áreas.\n\n**Para reducir tu riesgo:**\n"
                    respuesta += "• Sube tu asistencia a 85%+\n"
                    respuesta += "• Mejora tu nota del próximo parcial (objetivo: 3.5+)\n"
                    respuesta += "• Aumenta tu participación y seguimiento\n"
                else:
                    respuesta += "🚨 **Riesgo alto.** Necesitas acción inmediata.\n\n**Plan de Acción Urgente:**\n"
                    respuesta += "1. Habla con tu profesor HOY\n"
                    respuesta += "2. Asiste a TODAS las clases restantes\n"
                    respuesta += "3. Usa todas las tutorías disponibles\n"
                    respuesta += "4. Forma un grupo de estudio\n"
                    respuesta += "5. Dedica mínimo 2 horas diarias de estudio\n"
            else:
                respuesta = """**📝 Para Aprobar la Materia:**

Generalmente necesitas:
• **Asistencia:** Mínimo 80% (ideal: 90%+)
• **Notas:** Promedio de 3.0 o superior
• **Participación:** Activa y constante
• **Uso de recursos:** Plataforma y tutorías

💡 **Tip:** Haz una predicción primero para ver tu riesgo actual y obtener recomendaciones personalizadas."""
        
        # Preguntas sobre consejos generales
        elif any(palabra in pregunta for palabra in ["consejo", "recomend", "ayuda", "sugerencia"]):
            respuesta = f"""**🎓 Consejos Personalizados para Ti:**

**📊 Tu Situación Actual:**
• Asistencia: {datos.promedio_asistencia}% {'✅' if datos.promedio_asistencia >= 80 else '⚠️'}
• Seguimiento: {datos.promedio_seguimiento}/5.0 {'✅' if datos.promedio_seguimiento >= 3.5 else '⚠️'}
• Nota Parcial: {datos.nota_parcial_1}/5.0 {'✅' if datos.nota_parcial_1 >= 3.0 else '⚠️'}

**💪 Consejos Específicos:**

1. **Organízate:**
   • Crea un horario semanal de estudio
   • Dedica 1-2 horas diarias a esta materia
   
2. **Sé Constante:**
   • Ingresa a la plataforma 3-4 veces por semana
   • Revisa materiales antes y después de clase
   
3. **Busca Apoyo:**
   • Forma grupos de estudio con compañeros
   • Usa las tutorías (son gratis y efectivas)
   
4. **Participa Activamente:**
   • Haz preguntas en clase
   • Participa en foros y discusiones
   
5. **Prepárate Bien:**
   • Estudia con anticipación para los exámenes
   • Practica con ejercicios adicionales

**🎯 Objetivo:** Mejorar un poco cada semana. ¡Los pequeños cambios generan grandes resultados!"""
        
        # Pregunta general o no reconocida
        else:
            respuesta = f"""**🤖 Consejero Académico Virtual**

¡Hola! Estoy aquí para ayudarte a mejorar tu rendimiento académico.

**Tus datos actuales:**
• Asistencia: {datos.promedio_asistencia}%
• Seguimiento: {datos.promedio_seguimiento}/5.0
• Nota Parcial 1: {datos.nota_parcial_1}/5.0
• Logins: {datos.inicios_sesion_plataforma}
• Tutorías: {datos.uso_tutorias}

**Puedes preguntarme:**
• "¿Cómo puedo mejorar mi nota?"
• "¿Cuál es mi área más débil?"
• "¿Qué necesito para aprobar?"
• "Dame consejos personalizados"
• "¿Cómo usar las tutorías?"

¿En qué más puedo ayudarte? 😊"""
        
        return ChatOutput(respuesta=respuesta)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando la pregunta: {str(e)}"
        )

