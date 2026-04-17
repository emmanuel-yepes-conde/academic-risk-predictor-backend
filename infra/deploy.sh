#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# MPRA — Script de Despliegue en Azure
# Modelo Predictivo de Riesgo Académico
#
# Uso:
#   ./infra/deploy.sh -e <env> -r <region> -p <db-password> -j <jwt-secret>
#   ./infra/deploy.sh -e <env> --destroy
#   ./infra/deploy.sh --help
# ============================================================================

# ---------------------------------------------------------------------------
# Colores para output
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Variables globales
# ---------------------------------------------------------------------------
ENV_NAME=""
REGION=""
DB_PASSWORD=""
JWT_SECRET=""
DESTROY_MODE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Funciones de utilidad
# ---------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# ---------------------------------------------------------------------------
# usage() — Muestra instrucciones de uso
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
MPRA — Script de Despliegue en Azure
Modelo Predictivo de Riesgo Académico

Uso:
  $(basename "$0") -e <env> -r <region> -p <db-password> -j <jwt-secret>
  $(basename "$0") -e <env> --destroy
  $(basename "$0") --help

Parámetros:
  -e, --env           Nombre del entorno (dev, staging, prod)          [requerido]
  -r, --region        Región de Azure (ej: eastus, westeurope)         [requerido para deploy]
  -p, --db-password   Contraseña del administrador de PostgreSQL       [requerido para deploy]
  -j, --jwt-secret    Clave secreta para firmar tokens JWT             [requerido para deploy]
      --destroy       Eliminar todos los recursos del entorno
      --help          Mostrar esta ayuda

Ejemplos:
  # Despliegue completo en entorno dev
  $(basename "$0") -e dev -r eastus -p 'MiPassword123!' -j 'mi-jwt-secret-key'

  # Destrucción de recursos del entorno dev
  $(basename "$0") -e dev --destroy

Recursos creados:
  - Resource Group:       rg-mpra-{env}
  - Container Registry:   acrmpra{env}
  - Container App Env:    cae-mpra-{env}
  - Container App:        ca-mpra-{env}
  - PostgreSQL Server:    pg-mpra-{env}
  - Base de Datos:        mpra_db
EOF
}

# ---------------------------------------------------------------------------
# check_prerequisites() — Valida que Azure CLI está instalado y hay sesión
# ---------------------------------------------------------------------------
check_prerequisites() {
    log_info "Validando prerrequisitos..."

    # Verificar que Azure CLI está instalado
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI no está instalado."
        log_error "Instálalo desde: https://docs.microsoft.com/cli/azure/install-azure-cli"
        exit 1
    fi
    log_success "Azure CLI encontrado: $(az version --query '\"azure-cli\"' -o tsv 2>/dev/null || echo 'versión desconocida')"

    # Verificar que hay una sesión activa
    if ! az account show &> /dev/null; then
        log_error "No hay una sesión activa de Azure."
        log_error "Ejecuta 'az login' para iniciar sesión."
        exit 1
    fi

    local account_name
    account_name=$(az account show --query 'name' -o tsv 2>/dev/null || echo 'desconocida')
    log_success "Sesión activa en suscripción: ${account_name}"
}

# ---------------------------------------------------------------------------
# parse_args() — Parsea argumentos de línea de comandos
# ---------------------------------------------------------------------------
parse_args() {
    # Mostrar uso si no hay argumentos
    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -e|--env)
                ENV_NAME="$2"
                shift 2
                ;;
            -r|--region)
                REGION="$2"
                shift 2
                ;;
            -p|--db-password)
                DB_PASSWORD="$2"
                shift 2
                ;;
            -j|--jwt-secret)
                JWT_SECRET="$2"
                shift 2
                ;;
            --destroy)
                DESTROY_MODE=true
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                log_error "Argumento desconocido: $1"
                echo ""
                usage
                exit 1
                ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# validate_args() — Valida que los parámetros requeridos están presentes
# ---------------------------------------------------------------------------
validate_args() {
    local missing=false

    # El nombre del entorno siempre es requerido
    if [[ -z "${ENV_NAME}" ]]; then
        log_error "El parámetro --env (-e) es requerido."
        missing=true
    fi

    # En modo deploy, se requieren región, contraseña y JWT secret
    if [[ "${DESTROY_MODE}" == false ]]; then
        if [[ -z "${REGION}" ]]; then
            log_error "El parámetro --region (-r) es requerido para el despliegue."
            missing=true
        fi
        if [[ -z "${DB_PASSWORD}" ]]; then
            log_error "El parámetro --db-password (-p) es requerido para el despliegue."
            missing=true
        fi
        if [[ -z "${JWT_SECRET}" ]]; then
            log_error "El parámetro --jwt-secret (-j) es requerido para el despliegue."
            missing=true
        fi
    fi

    if [[ "${missing}" == true ]]; then
        echo ""
        usage
        exit 1
    fi

    log_success "Parámetros validados correctamente."
}

# ---------------------------------------------------------------------------
# deploy() — Flujo de despliegue completo
# ---------------------------------------------------------------------------
deploy() {
    local rg_name="rg-mpra-${ENV_NAME}"
    local bicep_file="${SCRIPT_DIR}/main.bicep"

    log_info "Iniciando despliegue del entorno '${ENV_NAME}' en región '${REGION}'..."
    log_info "Resource Group: ${rg_name}"

    # Verificar que el archivo Bicep existe
    if [[ ! -f "${bicep_file}" ]]; then
        log_error "No se encontró la plantilla Bicep en: ${bicep_file}"
        exit 1
    fi

    # -----------------------------------------------------------------------
    # Paso 1: Crear Resource Group
    # -----------------------------------------------------------------------
    log_info "Paso 1/6: Creando Resource Group '${rg_name}' en '${REGION}'..."
    if ! az group create --name "${rg_name}" --location "${REGION}" --output none; then
        log_error "No se pudo crear el Resource Group '${rg_name}'."
        log_error "Verifica que la región '${REGION}' es válida y que tienes permisos suficientes."
        exit 1
    fi
    log_success "Resource Group '${rg_name}' creado correctamente."

    # -----------------------------------------------------------------------
    # Paso 2: Desplegar plantilla Bicep
    # -----------------------------------------------------------------------
    log_info "Paso 2/6: Desplegando plantilla Bicep..."
    local deployment_output
    if ! deployment_output=$(az deployment group create \
        --resource-group "${rg_name}" \
        --template-file "${bicep_file}" \
        --parameters \
            environmentName="${ENV_NAME}" \
            dbAdminPassword="${DB_PASSWORD}" \
            jwtSecretKey="${JWT_SECRET}" \
        --output json 2>&1); then
        log_error "Falló el despliegue de la plantilla Bicep."
        log_error "Detalle: ${deployment_output}"
        exit 1
    fi
    log_success "Plantilla Bicep desplegada correctamente."

    # -----------------------------------------------------------------------
    # Paso 3: Capturar outputs del despliegue
    # -----------------------------------------------------------------------
    log_info "Paso 3/6: Capturando outputs del despliegue..."

    local acr_name acr_login_server fqdn postgres_host ca_name

    acr_name=$(echo "${deployment_output}" | jq -r '.properties.outputs.acrName.value')
    acr_login_server=$(echo "${deployment_output}" | jq -r '.properties.outputs.acrLoginServer.value')
    fqdn=$(echo "${deployment_output}" | jq -r '.properties.outputs.containerAppFqdn.value')
    postgres_host=$(echo "${deployment_output}" | jq -r '.properties.outputs.postgresHost.value')
    ca_name=$(echo "${deployment_output}" | jq -r '.properties.outputs.containerAppName.value')

    # Validar que los outputs se capturaron correctamente
    if [[ -z "${acr_name}" || "${acr_name}" == "null" ]]; then
        log_error "No se pudo obtener el nombre del ACR desde los outputs del despliegue."
        exit 1
    fi
    if [[ -z "${fqdn}" || "${fqdn}" == "null" ]]; then
        log_error "No se pudo obtener el FQDN del Container App desde los outputs del despliegue."
        exit 1
    fi
    if [[ -z "${ca_name}" || "${ca_name}" == "null" ]]; then
        log_error "No se pudo obtener el nombre del Container App desde los outputs del despliegue."
        exit 1
    fi

    log_success "Outputs capturados:"
    log_info "  ACR Name:         ${acr_name}"
    log_info "  ACR Login Server: ${acr_login_server}"
    log_info "  Container App:    ${ca_name}"
    log_info "  FQDN:             ${fqdn}"
    log_info "  PostgreSQL Host:  ${postgres_host}"

    # -----------------------------------------------------------------------
    # Paso 4: Construir imagen Docker en ACR
    # -----------------------------------------------------------------------
    log_info "Paso 4/6: Construyendo imagen Docker en ACR '${acr_name}'..."
    if ! az acr build \
        --registry "${acr_name}" \
        --image mpra-backend:latest \
        --file "${SCRIPT_DIR}/../Dockerfile" \
        "${SCRIPT_DIR}/.." 2>&1; then
        log_error "Falló la construcción de la imagen Docker en ACR."
        log_error "Verifica que el Dockerfile es válido y que el ACR '${acr_name}' está accesible."
        exit 1
    fi
    log_success "Imagen Docker 'mpra-backend:latest' construida y publicada en ACR."

    # -----------------------------------------------------------------------
    # Paso 5: Actualizar Container App con la imagen nueva
    # -----------------------------------------------------------------------
    log_info "Paso 5/6: Actualizando Container App '${ca_name}' con la imagen nueva..."
    if ! az containerapp update \
        --name "${ca_name}" \
        --resource-group "${rg_name}" \
        --image "${acr_login_server}/mpra-backend:latest" \
        --output none 2>&1; then
        log_error "Falló la actualización del Container App '${ca_name}'."
        log_error "Verifica que la imagen '${acr_login_server}/mpra-backend:latest' existe en el ACR."
        exit 1
    fi
    log_success "Container App '${ca_name}' actualizado con la imagen nueva."

    # -----------------------------------------------------------------------
    # Paso 6: Ejecutar migraciones Alembic
    # -----------------------------------------------------------------------
    log_info "Paso 6/6: Ejecutando migraciones Alembic..."
    set +e
    local migration_output
    migration_output=$(az containerapp exec \
        --name "${ca_name}" \
        --resource-group "${rg_name}" \
        --command "alembic upgrade head" 2>&1)
    local migration_exit_code=$?
    set -e

    if [[ ${migration_exit_code} -ne 0 ]]; then
        log_warn "Las migraciones de Alembic fallaron (exit code: ${migration_exit_code})."
        log_warn "Detalle: ${migration_output}"
        log_warn "La aplicación puede no funcionar correctamente hasta que las migraciones se ejecuten manualmente."
    else
        log_success "Migraciones de Alembic ejecutadas correctamente."
    fi

    # -----------------------------------------------------------------------
    # Resumen final
    # -----------------------------------------------------------------------
    echo ""
    echo -e "${GREEN}============================================================================${NC}"
    echo -e "${GREEN} Despliegue completado exitosamente${NC}"
    echo -e "${GREEN}============================================================================${NC}"
    echo ""
    echo -e "  ${BLUE}Entorno:${NC}            ${ENV_NAME}"
    echo -e "  ${BLUE}Región:${NC}             ${REGION}"
    echo -e "  ${BLUE}Resource Group:${NC}     ${rg_name}"
    echo ""
    echo -e "  ${BLUE}URL pública:${NC}        https://${fqdn}"
    echo -e "  ${BLUE}Health check:${NC}       https://${fqdn}/health"
    echo ""
    echo -e "  ${BLUE}PostgreSQL Host:${NC}    ${postgres_host}"
    echo -e "  ${BLUE}Cadena de conexión:${NC} postgresql+asyncpg://mpraadmin:****@${postgres_host}:5432/mpra_db?sslmode=require"
    echo ""
    echo -e "  ${BLUE}ACR:${NC}                ${acr_login_server}"
    echo -e "  ${BLUE}Container App:${NC}      ${ca_name}"
    echo ""
    echo -e "${GREEN}============================================================================${NC}"
}

# ---------------------------------------------------------------------------
# destroy() — Flujo de destrucción de recursos
# ---------------------------------------------------------------------------
destroy() {
    local rg_name="rg-mpra-${ENV_NAME}"

    log_info "Modo destrucción para el entorno '${ENV_NAME}'..."
    log_info "Resource Group a eliminar: ${rg_name}"

    # -----------------------------------------------------------------------
    # Paso 1: Verificar que el Resource Group existe
    # -----------------------------------------------------------------------
    log_info "Verificando si el Resource Group '${rg_name}' existe..."

    local rg_exists
    rg_exists=$(az group exists --name "${rg_name}" 2>/dev/null || echo "false")

    if [[ "${rg_exists}" != "true" ]]; then
        log_warn "El Resource Group '${rg_name}' no existe. No hay recursos que eliminar."
        exit 0
    fi

    log_info "Resource Group '${rg_name}' encontrado."

    # -----------------------------------------------------------------------
    # Paso 2: Solicitar confirmación interactiva
    # -----------------------------------------------------------------------
    echo ""
    log_warn "Esta operación eliminará TODOS los recursos del entorno '${ENV_NAME}':"
    echo -e "  - Resource Group:       ${rg_name}"
    echo -e "  - Container Registry:   acrmpra${ENV_NAME}"
    echo -e "  - Container App Env:    cae-mpra-${ENV_NAME}"
    echo -e "  - Container App:        ca-mpra-${ENV_NAME}"
    echo -e "  - PostgreSQL Server:    pg-mpra-${ENV_NAME}"
    echo -e "  - Base de Datos:        mpra_db"
    echo ""
    log_warn "Esta acción es IRREVERSIBLE."
    echo ""

    local confirm
    read -p "¿Estás seguro de que deseas eliminar todos los recursos? (sí/no): " confirm

    if [[ "${confirm}" != "sí" && "${confirm}" != "si" && "${confirm}" != "yes" ]]; then
        log_info "Operación cancelada por el usuario."
        exit 0
    fi

    # -----------------------------------------------------------------------
    # Paso 3: Eliminar Resource Group completo
    # -----------------------------------------------------------------------
    log_info "Eliminando Resource Group '${rg_name}' y todos sus recursos..."

    if ! az group delete --name "${rg_name}" --yes --no-wait 2>&1; then
        log_error "No se pudo iniciar la eliminación del Resource Group '${rg_name}'."
        log_error "Verifica que tienes permisos suficientes para eliminar recursos."
        exit 1
    fi

    # -----------------------------------------------------------------------
    # Paso 4: Confirmar eliminación exitosa
    # -----------------------------------------------------------------------
    echo ""
    log_success "Eliminación del Resource Group '${rg_name}' iniciada correctamente."
    log_info "La eliminación se ejecuta en segundo plano (--no-wait)."
    log_info "Puedes verificar el estado con: az group show --name ${rg_name} --query 'properties.provisioningState' -o tsv"
    log_info "Cuando el Resource Group ya no exista, todos los recursos habrán sido eliminados."
}

# ---------------------------------------------------------------------------
# main() — Punto de entrada principal
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"
    check_prerequisites
    validate_args

    if [[ "${DESTROY_MODE}" == true ]]; then
        destroy
    else
        deploy
    fi
}

main "$@"
