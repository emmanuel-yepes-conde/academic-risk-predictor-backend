"""
Generador de Datos de Entrenamiento para el Modelo de Predicción de Riesgo Académico
=====================================================================================

Este script genera datos sintéticos realistas para entrenar el modelo de regresión logística.
Los datos generados simulan el comportamiento académico de estudiantes con correlaciones
realistas entre las variables.

Variables generadas:
- promedio_asistencia: Porcentaje de asistencia (0-100)
- promedio_seguimiento: Promedio de seguimiento académico (0-5)
- nota_parcial_1: Nota del primer parcial (0-5)
- inicios_sesion_plataforma: Número de inicios de sesión en la plataforma
- uso_tutorias: Uso de tutorías (0-10)
- riesgo_reprobacion: Etiqueta objetivo (0 = aprobado, 1 = riesgo de reprobación)

Autor: Sistema de Predicción de Riesgo Académico
Fecha: Noviembre 2025
"""

import pandas as pd
import numpy as np
from typing import Tuple
import os


class GeneradorDatosAcademicos:
    """
    Clase para generar datos sintéticos de estudiantes con comportamiento realista.
    """
    
    def __init__(self, seed: int = 42):
        """
        Inicializa el generador con una semilla para reproducibilidad.
        
        Args:
            seed: Semilla para el generador de números aleatorios
        """
        self.seed = seed
        np.random.seed(seed)
        
    def generar_estudiante_aprobado(self) -> dict:
        """
        Genera datos de un estudiante con buen rendimiento (riesgo bajo).
        
        Returns:
            Diccionario con los datos del estudiante
        """
        # Estudiantes aprobados tienden a tener buenos indicadores
        asistencia = np.random.normal(85, 10)  # Media 85%, desviación 10%
        asistencia = np.clip(asistencia, 60, 100)
        
        seguimiento = np.random.normal(3.5, 0.7)  # Media 3.5/5.0
        seguimiento = np.clip(seguimiento, 2.0, 5.0)
        
        nota_parcial = np.random.normal(3.5, 0.8)  # Media 3.5/5.0
        nota_parcial = np.clip(nota_parcial, 2.5, 5.0)
        
        # Mayor asistencia correlaciona con más logins
        logins = int(np.random.normal(40, 10))
        logins = np.clip(logins, 25, 60)
        
        # Uso variable de tutorías
        uso_tutorias = int(np.random.exponential(2))
        uso_tutorias = np.clip(uso_tutorias, 0, 10)
        
        return {
            'promedio_asistencia': round(asistencia, 1),
            'promedio_seguimiento': round(seguimiento, 1),
            'nota_parcial_1': round(nota_parcial, 1),
            'inicios_sesion_plataforma': logins,
            'uso_tutorias': uso_tutorias,
            'riesgo_reprobacion': 0
        }
    
    def generar_estudiante_riesgo(self) -> dict:
        """
        Genera datos de un estudiante en riesgo de reprobación.
        
        Returns:
            Diccionario con los datos del estudiante
        """
        # Estudiantes en riesgo tienden a tener indicadores más bajos
        asistencia = np.random.normal(65, 12)  # Media 65%, más variabilidad
        asistencia = np.clip(asistencia, 40, 90)
        
        seguimiento = np.random.normal(2.5, 0.8)  # Media 2.5/5.0
        seguimiento = np.clip(seguimiento, 1.0, 4.0)
        
        nota_parcial = np.random.normal(2.3, 0.7)  # Media 2.3/5.0
        nota_parcial = np.clip(nota_parcial, 1.0, 3.5)
        
        # Menos logins en promedio
        logins = int(np.random.normal(35, 12))
        logins = np.clip(logins, 15, 55)
        
        # Menor uso de tutorías (aunque algunos sí las usan)
        uso_tutorias = int(np.random.exponential(1.5))
        uso_tutorias = np.clip(uso_tutorias, 0, 8)
        
        return {
            'promedio_asistencia': round(asistencia, 1),
            'promedio_seguimiento': round(seguimiento, 1),
            'nota_parcial_1': round(nota_parcial, 1),
            'inicios_sesion_plataforma': logins,
            'uso_tutorias': uso_tutorias,
            'riesgo_reprobacion': 1
        }
    
    def generar_estudiante_borderline(self) -> dict:
        """
        Genera datos de un estudiante en zona intermedia (puede ir para cualquier lado).
        Usa un modelo probabilístico para determinar si aprueba o no.
        
        Returns:
            Diccionario con los datos del estudiante
        """
        # Zona intermedia - indicadores mixtos
        asistencia = np.random.normal(75, 8)
        asistencia = np.clip(asistencia, 60, 90)
        
        seguimiento = np.random.normal(3.0, 0.6)
        seguimiento = np.clip(seguimiento, 2.0, 4.0)
        
        nota_parcial = np.random.normal(2.8, 0.6)
        nota_parcial = np.clip(nota_parcial, 2.0, 3.8)
        
        logins = int(np.random.normal(37, 10))
        logins = np.clip(logins, 20, 50)
        
        uso_tutorias = int(np.random.exponential(1.8))
        uso_tutorias = np.clip(uso_tutorias, 0, 8)
        
        # Calcular riesgo basado en un score ponderado
        score = (
            (asistencia / 100) * 0.25 +  # 25% peso
            (seguimiento / 5.0) * 0.20 +  # 20% peso
            (nota_parcial / 5.0) * 0.35 +  # 35% peso (más importante)
            (min(logins, 50) / 50) * 0.10 +  # 10% peso
            (min(uso_tutorias, 5) / 5) * 0.10  # 10% peso
        )
        
        # Convertir score a probabilidad de aprobar
        # Score alto (cercano a 1) = baja probabilidad de riesgo
        probabilidad_riesgo = 1 - score
        
        # Añadir algo de aleatoriedad
        riesgo = 1 if np.random.random() < probabilidad_riesgo else 0
        
        return {
            'promedio_asistencia': round(asistencia, 1),
            'promedio_seguimiento': round(seguimiento, 1),
            'nota_parcial_1': round(nota_parcial, 1),
            'inicios_sesion_plataforma': logins,
            'uso_tutorias': uso_tutorias,
            'riesgo_reprobacion': riesgo
        }
    
    def generar_dataset(
        self, 
        n_total: int = 5000,
        proporcion_aprobados: float = 0.65,
        proporcion_borderline: float = 0.20
    ) -> pd.DataFrame:
        """
        Genera un dataset completo de estudiantes.
        
        Args:
            n_total: Número total de estudiantes a generar
            proporcion_aprobados: Proporción de estudiantes que aprueban (0.0-1.0)
            proporcion_borderline: Proporción de estudiantes en zona intermedia (0.0-1.0)
            
        Returns:
            DataFrame con los datos generados
        """
        print(f"\n{'='*70}")
        print(f"🎓 GENERADOR DE DATOS DE ENTRENAMIENTO")
        print(f"{'='*70}\n")
        
        # Calcular cantidades
        n_aprobados = int(n_total * proporcion_aprobados)
        n_borderline = int(n_total * proporcion_borderline)
        n_riesgo = n_total - n_aprobados - n_borderline
        
        print(f"📊 Configuración:")
        print(f"   Total de estudiantes: {n_total}")
        print(f"   Estudiantes aprobados (base): {n_aprobados} ({proporcion_aprobados*100:.1f}%)")
        print(f"   Estudiantes en zona intermedia: {n_borderline} ({proporcion_borderline*100:.1f}%)")
        print(f"   Estudiantes en riesgo (base): {n_riesgo} ({(1-proporcion_aprobados-proporcion_borderline)*100:.1f}%)")
        print(f"\n⏳ Generando datos...\n")
        
        estudiantes = []
        
        # Generar estudiantes aprobados
        print(f"✓ Generando {n_aprobados} estudiantes aprobados...")
        for _ in range(n_aprobados):
            estudiantes.append(self.generar_estudiante_aprobado())
        
        # Generar estudiantes en riesgo
        print(f"✓ Generando {n_riesgo} estudiantes en riesgo...")
        for _ in range(n_riesgo):
            estudiantes.append(self.generar_estudiante_riesgo())
        
        # Generar estudiantes borderline (pueden ser aprobados o en riesgo)
        print(f"✓ Generando {n_borderline} estudiantes en zona intermedia...")
        for _ in range(n_borderline):
            estudiantes.append(self.generar_estudiante_borderline())
        
        # Crear DataFrame
        df = pd.DataFrame(estudiantes)
        
        # Mezclar aleatoriamente
        df = df.sample(frac=1, random_state=self.seed).reset_index(drop=True)
        
        print(f"\n✅ Dataset generado exitosamente!\n")
        
        # Mostrar estadísticas finales
        self._mostrar_estadisticas(df)
        
        return df
    
    def _mostrar_estadisticas(self, df: pd.DataFrame):
        """
        Muestra estadísticas descriptivas del dataset generado.
        
        Args:
            df: DataFrame con los datos generados
        """
        print(f"{'='*70}")
        print(f"📈 ESTADÍSTICAS DEL DATASET GENERADO")
        print(f"{'='*70}\n")
        
        # Distribución de la variable objetivo
        total = len(df)
        n_riesgo = df['riesgo_reprobacion'].sum()
        n_aprobados = total - n_riesgo
        
        print(f"🎯 Distribución de Riesgo de Reprobación:")
        print(f"   Estudiantes aprobados (riesgo=0): {n_aprobados} ({n_aprobados/total*100:.1f}%)")
        print(f"   Estudiantes en riesgo (riesgo=1): {n_riesgo} ({n_riesgo/total*100:.1f}%)")
        print()
        
        # Estadísticas por grupo
        print(f"📊 Promedios por Grupo:")
        print(f"\n{'Métrica':<30} {'Aprobados':>12} {'En Riesgo':>12} {'Diferencia':>12}")
        print(f"{'-'*70}")
        
        aprobados = df[df['riesgo_reprobacion'] == 0]
        en_riesgo = df[df['riesgo_reprobacion'] == 1]
        
        metricas = [
            ('Asistencia (%)', 'promedio_asistencia'),
            ('Seguimiento (/5)', 'promedio_seguimiento'),
            ('Nota Parcial 1 (/5)', 'nota_parcial_1'),
            ('Inicios de Sesión', 'inicios_sesion_plataforma'),
            ('Uso de Tutorías', 'uso_tutorias')
        ]
        
        for nombre, columna in metricas:
            media_aprobados = aprobados[columna].mean()
            media_riesgo = en_riesgo[columna].mean()
            diferencia = media_aprobados - media_riesgo
            
            print(f"{nombre:<30} {media_aprobados:>12.2f} {media_riesgo:>12.2f} {diferencia:>12.2f}")
        
        print(f"\n{'='*70}\n")
    
    def guardar_dataset(self, df: pd.DataFrame, nombre_archivo: str = "dataset_generado.csv"):
        """
        Guarda el dataset en un archivo CSV.
        
        Args:
            df: DataFrame con los datos
            nombre_archivo: Nombre del archivo de salida
        """
        ruta_completa = os.path.join(os.path.dirname(__file__), nombre_archivo)
        df.to_csv(ruta_completa, index=False)
        
        print(f"💾 Dataset guardado en: {ruta_completa}")
        print(f"📁 Tamaño del archivo: {os.path.getsize(ruta_completa) / 1024:.2f} KB")
        print(f"📊 Total de registros: {len(df)}")
        print(f"📋 Total de columnas: {len(df.columns)}")
        print()


def main():
    """
    Función principal para ejecutar el generador de datos.
    """
    print("\n" + "="*70)
    print("🚀 INICIANDO GENERADOR DE DATOS DE ENTRENAMIENTO")
    print("="*70)
    
    # Parámetros de generación
    N_TOTAL = 99000  # Número total de estudiantes
    PROPORCION_APROBADOS = 0.70  # 70% aprueban
    PROPORCION_BORDERLINE = 0.30  # 30% en zona intermedia
    SEED = 42  # Para reproducibilidad
    
    # Crear generador
    generador = GeneradorDatosAcademicos(seed=SEED)
    
    # Generar dataset
    df = generador.generar_dataset(
        n_total=N_TOTAL,
        proporcion_aprobados=PROPORCION_APROBADOS,
        proporcion_borderline=PROPORCION_BORDERLINE
    )
    
    # Guardar dataset
    generador.guardar_dataset(df, "dataset_estudiantes_decimal.csv")
    
    print("\n" + "="*70)
    print("✅ PROCESO COMPLETADO EXITOSAMENTE")
    print("="*70)
    print("\n💡 Ahora puedes usar este dataset para:")
    print("   1. Entrenar un nuevo modelo desde cero")
    print("   2. Reemplazar el archivo 'dataset_estudiantes_decimal.csv'")
    print("   3. Aumentar los datos existentes (data augmentation)")
    print("   4. Validar el modelo actual con datos frescos")
    print("\n📝 Para entrenar con este nuevo dataset:")
    print("   1. Renombra 'dataset_nuevo_entrenamiento.csv' a 'dataset_estudiantes_decimal.csv'")
    print("   2. Elimina los archivos 'modelo_logistico.joblib' y 'scaler.joblib'")
    print("   3. Ejecuta 'python main.py' para entrenar con los nuevos datos")
    print()


if __name__ == "__main__":
    main()

