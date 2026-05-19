"""add job_configs table

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'job_configs',
        sa.Column('id',          sa.String(64),  primary_key=True),
        sa.Column('name',        sa.String(120),  nullable=False),
        sa.Column('description', sa.Text(),       nullable=False),
        sa.Column('job_type',    sa.String(20),   nullable=False),   # 'cron' | 'trigger'
        sa.Column('cron_expr',   sa.String(120),  nullable=True),    # solo para cron
        sa.Column('trigger_event', sa.String(120), nullable=True),   # solo para trigger
        sa.Column('channels',    JSONB,           nullable=False, server_default='[]'),
        sa.Column('enabled',     sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra',       JSONB,           nullable=True),
    )

    # Seed: jobs y triggers conocidos
    op.execute("""
        INSERT INTO job_configs (id, name, description, job_type, cron_expr, trigger_event, channels, enabled) VALUES
        (
          'monitoring',
          'Monitoreo de servicios',
          'Verifica el estado de todos los componentes del sistema (Backend, BD, WAHA, Frontend, RAG). Notifica al grupo de WhatsApp cuando detecta fallas o recuperaciones.',
          'cron',
          '*/5 * * * *',
          NULL,
          '["whatsapp"]',
          true
        ),
        (
          'risk-alerts',
          'Alertas semanales de riesgo ALTO',
          'Cada lunes envía un mensaje a cada estudiante con nivel de riesgo ALTO, recordándole que tome acción. También genera una notificación in-app.',
          'cron',
          '0 8 * * 1',
          NULL,
          '["whatsapp","email","inapp"]',
          true
        ),
        (
          'class-crisis',
          'Alerta de crisis de clase',
          'Si el 35% o más de los estudiantes de un curso tienen riesgo ALTO, notifica inmediatamente al profesor con recomendaciones pedagógicas.',
          'cron',
          '*/5 * * * *',
          NULL,
          '["whatsapp","inapp"]',
          true
        ),
        (
          'attendance-registered',
          'Asistencia registrada por QR',
          'Cuando un estudiante escanea el QR y registra su asistencia, se genera una notificación in-app para el profesor.',
          'trigger',
          NULL,
          'attendance.registered',
          '["inapp"]',
          true
        ),
        (
          'referral-created',
          'Referido creado',
          'Cuando el profesor crea un referido para un estudiante (por bajo rendimiento u otra razón), el sistema envía un correo electrónico al estudiante notificándolo.',
          'trigger',
          NULL,
          'referral.created',
          '["email"]',
          true
        ),
        (
          'risk-prediction',
          'Predicción de riesgo individual',
          'Al ejecutar el predictor ML para un estudiante, si el resultado es ALTO se envía una alerta multicanal al estudiante y una notificación in-app.',
          'trigger',
          NULL,
          'prediction.high_risk',
          '["whatsapp","email","inapp"]',
          true
        )
    """)


def downgrade() -> None:
    op.drop_table('job_configs')
