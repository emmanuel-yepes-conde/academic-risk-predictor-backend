# Product: Modelo Predictivo de Riesgo Académico (MPRA)

## 1. Definición del Producto
El **MPRA** es una solución de inteligencia de datos diseñada para la detección temprana de la deserción universitaria. Utiliza un modelo de **Regresión Logística** para transformar variables académicas en una probabilidad de riesgo (0 a 1), permitiendo intervenciones pedagógicas antes de que ocurra la pérdida de la asignatura.

## 2. Objetivos de Negocio
* **Proactividad:** Pasar de un modelo de bienestar reactivo a uno predictivo.
* **Retención:** Aumentar los índices de permanencia estudiantil mediante alertas tempranas.
* **Transparencia:** Democratizar el acceso a la información de riesgo para el estudiante.

## 3. Stakeholders (Interesados)
* **Docentes:** Responsables de la integridad de los datos.
* **Estudiantes:** Beneficiarios de las alertas y usuarios de tutorías.
* **Bienestar Universitario:** Coordinadores de las estrategias de retención.
* **Directores de programas:** Beneficiados con métricas para la mejora continua del programa (Porcentaje de perdida de asignaturas, profesores con más perdidas, etc)

## 4. Reglas de Negocio (Business Rules)
* **RB-01 (Variables Mínimas):** El sistema requiere obligatoriamente **Asistencia, Seguimiento y Nota del Primer Parcial** para generar una predicción válida.
* **RB-02 (Consentimiento):** Ningún dato será procesado por el motor de ML sin la aceptación explícita de términos y condiciones por parte del estudiante.
* **RB-03 (Umbrales de Riesgo):** 
    * Bajo: < 0.4
    * Medio: 0.4 - 0.7
    * Alto: > 0.7
* **RB-04 (Privacidad):** Los docentes solo pueden visualizar los datos de los estudiantes inscritos en sus asignaturas asignadas.