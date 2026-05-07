from enum import Enum


class RoleEnum(str, Enum):
    STUDENT = "STUDENT"
    PROFESSOR = "PROFESSOR"
    ADMIN = "ADMIN"


class OperationEnum(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class UserStatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CourseStatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class EnrollmentStatusEnum(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReferralTypeEnum(str, Enum):
    BAJO_RENDIMIENTO       = "Bajo rendimiento académico"
    INASISTENCIA           = "Inasistencia reiterada"
    INCUMPLIMIENTO         = "Incumplimiento de actividades"
    PROBLEMAS_PERSONALES   = "Problemas personales"
    DIFICULTADES_ECONOMICAS = "Dificultades económicas"
    PROBLEMAS_SALUD        = "Problemas de salud"
    OTROS                  = "Otros"


class AsistioEnum(str, Enum):
    SIN_CONFIRMAR = "Sin confirmar"
    SI            = "Sí"
    NO            = "No"


class ReferralStatusEnum(str, Enum):
    PENDIENTE = "PENDIENTE"
    ATENDIDA  = "ATENDIDA"
    CANCELADA = "CANCELADA"
