"""Mejorar nombres y descripciones de jobs en job_configs

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-20
"""
from alembic import op

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE job_configs SET
            name = 'Monitoreo del sistema',
            description = 'Verifica cada 5 minutos el estado de todos los componentes (Backend, Base de datos, WAHA, Frontend, RAG). Notifica al grupo de WhatsApp cuando detecta una falla o recuperación.'
        WHERE id = 'monitoring'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Recordatorio semanal: riesgo ALTO',
            description = 'Cada lunes a las 8:00 a.m. envía un mensaje personalizado a cada estudiante con nivel de riesgo ALTO, recordándole que debe tomar acciones de mejora. También crea una notificación in-app.'
        WHERE id = 'risk-alerts'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Alerta de crisis en el curso',
            description = 'Detecta cuando el 35 % o más de los estudiantes de un curso tienen riesgo ALTO y notifica de inmediato al docente con recomendaciones pedagógicas concretas.'
        WHERE id = 'class-crisis'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Confirmación de asistencia por QR',
            description = 'Cada vez que un estudiante escanea el código QR y registra su asistencia, se genera automáticamente una notificación in-app de confirmación.'
        WHERE id = 'attendance-registered'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Notificación de remisión al estudiante',
            description = 'Cuando el docente crea una remisión para un estudiante (por bajo rendimiento u otra causa), el sistema envía un correo electrónico al estudiante informándolo de la situación.'
        WHERE id = 'referral-created'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Alerta de riesgo detectado por IA',
            description = 'Al ejecutar el predictor ML para un estudiante y obtener resultado ALTO, se envía una alerta multicanal (WhatsApp, correo e in-app) al estudiante con el análisis completo.'
        WHERE id = 'risk-prediction'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE job_configs SET
            name = 'Monitoreo de servicios',
            description = 'Verifica el estado de todos los componentes del sistema (Backend, BD, WAHA, Frontend, RAG). Notifica al grupo de WhatsApp cuando detecta fallas o recuperaciones.'
        WHERE id = 'monitoring'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Alertas semanales de riesgo ALTO',
            description = 'Cada lunes envía un mensaje a cada estudiante con nivel de riesgo ALTO, recordándole que tome acción. También genera una notificación in-app.'
        WHERE id = 'risk-alerts'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Alerta de crisis de clase',
            description = 'Si el 35% o más de los estudiantes de un curso tienen riesgo ALTO, notifica inmediatamente al profesor con recomendaciones pedagógicas.'
        WHERE id = 'class-crisis'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Asistencia registrada por QR',
            description = 'Cuando un estudiante escanea el QR y registra su asistencia, se genera una notificación in-app para el profesor.'
        WHERE id = 'attendance-registered'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Referido creado',
            description = 'Cuando el profesor crea un referido para un estudiante (por bajo rendimiento u otra razón), el sistema envía un correo electrónico al estudiante notificándolo.'
        WHERE id = 'referral-created'
    """)

    op.execute("""
        UPDATE job_configs SET
            name = 'Predicción de riesgo individual',
            description = 'Al ejecutar el predictor ML para un estudiante, si el resultado es ALTO se envía una alerta multicanal al estudiante y una notificación in-app.'
        WHERE id = 'risk-prediction'
    """)
