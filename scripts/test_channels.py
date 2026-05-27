"""
Diagnóstico de canales de notificación — corre LOCALMENTE sin deployar.

Uso:
    cd academic-risk-predictor-backend
    venv/bin/python -m scripts.test_channels [--phone 3126226684] [--email tu@email.com]
    venv/bin/python -m scripts.test_channels --only waha
    venv/bin/python -m scripts.test_channels --only smtp
    venv/bin/python -m scripts.test_channels --only acs
    venv/bin/python -m scripts.test_channels --fullflow  # simula exactamente lo que hace la app

Flags:
    --phone     Número colombiano (10 dígitos, sin +57). Default: lee de DB (David)
    --email     Correo destino. Default: lee de DB (David)
    --skip-acs  No prueba ACS (para no gastar tokens Azure)
    --only      Solo prueba un canal: waha | smtp | acs
    --fullflow  Simula el flujo completo (DB + background task real)
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.core.config import settings  # noqa: E402

OK   = "\033[92m✅"
FAIL = "\033[91m❌"
WARN = "\033[93m⚠️ "
INFO = "\033[94mℹ️ "
RST  = "\033[0m"


def _section(title: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ─── 1. WAHA ──────────────────────────────────────────────────────────────────

async def test_waha(phone: str) -> bool:
    _section("CANAL: WhatsApp (WAHA)")

    if not settings.WAHA_URL:
        print(f"{FAIL} WAHA_URL no configurado en .env{RST}")
        return False
    if not settings.WAHA_API_KEY:
        print(f"{FAIL} WAHA_API_KEY no configurado en .env{RST}")
        return False

    print(f"{INFO}WAHA_URL = {settings.WAHA_URL}{RST}")
    print(f"{INFO}Destino  = +57{phone}{RST}")

    import httpx

    print("\n[1/3] Verificando sesiones WAHA...")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{settings.WAHA_URL.rstrip('/')}/api/sessions",
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
        if r.status_code == 200:
            sessions = r.json()
            print(f"{OK} Sesiones: {[s.get('name') + '→' + s.get('status','?') for s in sessions]}{RST}")
        else:
            print(f"{FAIL} GET /api/sessions → HTTP {r.status_code}: {r.text[:200]}{RST}")
            return False
    except Exception as exc:
        print(f"{FAIL} No se pudo conectar a WAHA: {exc}{RST}")
        return False

    print("\n[2/3] Estado de sesión 'default'...")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{settings.WAHA_URL.rstrip('/')}/api/sessions/default",
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
        data = r.json()
        status = data.get("status", "UNKNOWN")
        icon = OK if status == "WORKING" else FAIL
        print(f"{icon} Sesión default → {status}{RST}")
        if status != "WORKING":
            print(f"  Respuesta: {data}")
            return False
    except Exception as exc:
        print(f"{FAIL} Error verificando sesión: {exc}{RST}")
        return False

    print(f"\n[3/3] Enviando mensaje de prueba a {phone}...")
    numero = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not numero.startswith("57"):
        numero = f"57{numero}"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{settings.WAHA_URL.rstrip('/')}/api/sendText",
                json={"chatId": f"{numero}@c.us",
                      "text": "🧪 *Prueba Academic Risk*\n\nMensaje de diagnóstico local. Si lo ves, WhatsApp funciona ✅",
                      "session": "default"},
                headers={"X-Api-Key": settings.WAHA_API_KEY},
            )
        if r.status_code < 400:
            print(f"{OK} Mensaje enviado → HTTP {r.status_code}{RST}")
            return True
        else:
            print(f"{FAIL} sendText falló → HTTP {r.status_code}: {r.text[:300]}{RST}")
            return False
    except Exception as exc:
        print(f"{FAIL} Excepción: {exc}{RST}")
        return False


# ─── 2. SMTP ──────────────────────────────────────────────────────────────────

async def test_smtp(email: str) -> bool:
    _section("CANAL: Email SMTP (Gmail)")

    missing = [v for v in ["SMTP_SERVER","SMTP_USERNAME","SMTP_PASSWORD","FROM_EMAIL"]
               if not getattr(settings, v, None)]
    if missing:
        print(f"{FAIL} Faltan vars: {', '.join(missing)}{RST}")
        return False

    print(f"{INFO}Server  = {settings.SMTP_SERVER}:{settings.SMTP_PORT}{RST}")
    print(f"{INFO}Usuario = {settings.SMTP_USERNAME}{RST}")
    print(f"{INFO}Destino = {email}{RST}")

    print("\n[1/2] Conectividad STARTTLS...")
    import smtplib
    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=10) as s:
            s.ehlo(); s.starttls(); s.ehlo()
        print(f"{OK} Conexión OK{RST}")
    except Exception as exc:
        print(f"{FAIL} Sin conectividad: {exc}{RST}")
        return False

    print("\n[2/2] Login + envío...")
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🧪 Prueba SMTP — Academic Risk"
    msg["From"]    = f"Academic Risk <{settings.FROM_EMAIL}>"
    msg["To"]      = email
    msg.attach(MIMEText(
        "<html><body style='font-family:Arial;padding:24px'>"
        "<h2 style='color:#1E3932'>✅ SMTP funciona</h2>"
        "<p>Diagnóstico local de Academic Risk.</p></body></html>",
        "html", "utf-8",
    ))
    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=15) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            s.sendmail(settings.FROM_EMAIL, email, msg.as_string())
        print(f"{OK} Correo enviado a {email}{RST}")
        return True
    except smtplib.SMTPAuthenticationError as exc:
        print(f"{FAIL} Error de autenticación: {exc}{RST}")
        print(f"""{WARN}Gmail requiere App Password (no contraseña normal):
  1. https://myaccount.google.com/apppasswords
  2. Crea una para "Correo" → "Otro"
  3. Pon los 16 caracteres en SMTP_PASSWORD del .env{RST}""")
        return False
    except Exception as exc:
        print(f"{FAIL} Error: {exc}{RST}")
        return False


# ─── 3. ACS ───────────────────────────────────────────────────────────────────

async def test_acs(email: str) -> bool:
    _section("CANAL: Azure Communication Services (ACS)")

    if not settings.ACS_CONNECTION_STRING:
        print(f"{FAIL} ACS_CONNECTION_STRING no configurado{RST}")
        return False

    print(f"{INFO}Sender  = {settings.ACS_SENDER_EMAIL}{RST}")
    print(f"{INFO}Destino = {email}{RST}")

    try:
        from azure.communication.email import EmailClient  # noqa: F401
        print(f"{OK} Paquete azure-communication-email instalado{RST}")
    except ImportError:
        print(f"{FAIL} Paquete NO instalado → pip install azure-communication-email{RST}")
        return False

    print("\n[1/1] Enviando via ACS...")
    try:
        from app.services.acs_email_service import _send_acs
        ok = await _send_acs(
            email,
            "🧪 Prueba ACS — Academic Risk",
            "<html><body style='font-family:Arial;padding:24px'>"
            "<h2 style='color:#1E3932'>✅ ACS funciona</h2>"
            "<p>Diagnóstico local de Academic Risk.</p></body></html>",
        )
        if ok:
            print(f"{OK} Correo ACS enviado a {email}{RST}")
        else:
            print(f"{FAIL} ACS falló (ver logs arriba){RST}")
        return ok
    except Exception as exc:
        print(f"{FAIL} Excepción ACS: {exc}{RST}")
        return False


# ─── 4. FULLFLOW — simula exactamente el código de producción ─────────────────

async def test_fullflow(name_filter: str = "david") -> bool:
    """
    Simula el flujo completo que ejecuta la app:
    1. Busca el enrollment del estudiante en la BD real
    2. Llama a _notify_student_prediction_result directamente
    3. Reporta qué pasó en cada subpaso

    Esto reproduce EXACTAMENTE lo que hace FastAPI en producción.
    """
    _section(f"FLUJO COMPLETO — simulando producción (estudiante: {name_filter})")

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.infrastructure.database import engine
    from app.infrastructure.models.enrollment import Enrollment
    from app.infrastructure.models.user import User
    from app.infrastructure.models.course import Course

    # Paso 1: encontrar enrollment del estudiante
    print(f"\n[1/4] Buscando enrollment de '{name_filter}' en BD...")
    try:
        async with AsyncSession(engine) as db:
            user_q = await db.execute(
                select(User).where(User.full_name.ilike(f"%{name_filter}%"))
            )
            user = user_q.scalar_one_or_none()
            if not user:
                print(f"{FAIL} No se encontró estudiante con nombre '{name_filter}'{RST}")
                return False

            print(f"{OK} Estudiante: {user.full_name} (id={user.id}){RST}")
            print(f"{INFO}  phone={user.phone}  whatsapp_enabled={user.whatsapp_enabled}{RST}")
            print(f"{INFO}  email={user.email}  email_enabled={user.email_enabled}{RST}")
            print(f"{INFO}  institutional_email={getattr(user, 'institutional_email', None)}{RST}")

            if not user.phone:
                print(f"{WARN}  ⚠️  Sin número de teléfono — WhatsApp NO se enviará{RST}")
            if not user.whatsapp_enabled:
                print(f"{WARN}  ⚠️  whatsapp_enabled=False — WhatsApp NO se enviará{RST}")
            if not user.email_enabled:
                print(f"{WARN}  ⚠️  email_enabled=False — Email NO se enviará{RST}")

            # Buscar enrollment activo
            enroll_q = await db.execute(
                select(Enrollment).where(Enrollment.student_id == user.id).limit(1)
            )
            enrollment = enroll_q.scalar_one_or_none()
            if not enrollment:
                print(f"{FAIL} Sin enrollments para este estudiante{RST}")
                return False

            course_q = await db.execute(
                select(Course).where(Course.id == enrollment.course_id)
            )
            course = course_q.scalar_one_or_none()
            print(f"{OK} Enrollment: {enrollment.id} → {course.name if course else '?'}{RST}")

    except Exception as exc:
        print(f"{FAIL} Error accediendo BD: {exc}{RST}")
        import traceback; traceback.print_exc()
        return False

    # Paso 2: verificar que el número tenga el formato correcto
    print(f"\n[2/4] Validando formato del número de teléfono...")
    if user.phone:
        numero = user.phone.strip().replace(" ", "").replace("-", "").replace("+", "")
        if not numero.startswith("57") and len(numero) == 10:
            numero = f"57{numero}"
        print(f"{OK} Número normalizado: {numero}@c.us{RST}")
    else:
        print(f"{WARN}  Sin teléfono — saltando prueba WhatsApp{RST}")

    # Paso 3: llamar _notify_student_prediction_result directamente
    print(f"\n[3/4] Ejecutando _notify_student_prediction_result (flujo real)...")
    try:
        from app.api.v1.endpoints.enrollments import _notify_student_prediction_result
        await _notify_student_prediction_result(
            enrollment_id=enrollment.id,
            nivel_riesgo="MEDIO",
            probability=0.62,
            analisis_ia=(
                "Basado en tus notas actuales, tienes un desempeño moderado.\n"
                "Te recomendamos reforzar los temas donde tuviste menor puntaje."
            ),
        )
        print(f"{OK} _notify_student_prediction_result completó sin excepción{RST}")
    except Exception as exc:
        print(f"{FAIL} _notify_student_prediction_result lanzó excepción: {exc}{RST}")
        import traceback; traceback.print_exc()
        return False

    # Paso 4: verificar notificación en BD
    print(f"\n[4/4] Verificando notificación guardada en BD...")
    try:
        async with AsyncSession(engine) as db:
            from app.infrastructure.models.notification import Notification
            notif_q = await db.execute(
                select(Notification)
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc())
                .limit(1)
            )
            notif = notif_q.scalar_one_or_none()
            if notif:
                print(f"{OK} Notificación in-app creada: type={notif.type} title={notif.title!r}{RST}")
            else:
                print(f"{WARN}  No se encontró notificación in-app en BD{RST}")
    except Exception as exc:
        print(f"{WARN}  No se pudo verificar notificación: {exc}{RST}")

    print(f"\n{OK} Flujo completo ejecutado. Revisa los mensajes en el teléfono/correo.{RST}")
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone",    default="3126226684")
    parser.add_argument("--email",    default="deividlujan200@gmail.com")
    parser.add_argument("--skip-acs", action="store_true")
    parser.add_argument("--only",     choices=["waha","smtp","acs","fullflow"])
    parser.add_argument("--fullflow", action="store_true", help="Simula flujo completo con DB real")
    parser.add_argument("--student",  default="david", help="Nombre del estudiante para --fullflow")
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   Academic Risk — Diagnóstico de Notificaciones      ║")
    print("╚══════════════════════════════════════════════════════╝")

    results: dict[str, bool | None] = {"waha": None, "smtp": None, "acs": None, "fullflow": None}

    if args.fullflow or args.only == "fullflow":
        results["fullflow"] = await test_fullflow(args.student)
    elif args.only:
        if args.only == "waha":  results["waha"]  = await test_waha(args.phone)
        elif args.only == "smtp": results["smtp"] = await test_smtp(args.email)
        elif args.only == "acs":  results["acs"]  = await test_acs(args.email)
    else:
        results["waha"] = await test_waha(args.phone)
        results["smtp"] = await test_smtp(args.email)
        if not args.skip_acs:
            results["acs"] = await test_acs(args.email)

    _section("RESUMEN")
    all_tested = {k: v for k, v in results.items() if v is not None}
    for canal, ok in results.items():
        if ok is None:   print(f"  ⏭️  {canal.upper():<10} — omitido")
        elif ok:         print(f"  {OK} {canal.upper():<10} — funciona{RST}")
        else:            print(f"  {FAIL} {canal.upper():<10} — FALLÓ{RST}")
    print()
    if all(v for v in all_tested.values()):
        print(f"{OK} Todo OK — los canales probados funcionan.{RST}\n")
    else:
        print(f"{FAIL} Uno o más canales fallaron. Ver detalles arriba.{RST}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
