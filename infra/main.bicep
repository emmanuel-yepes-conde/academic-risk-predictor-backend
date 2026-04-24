// ============================================================================
// MPRA — Infraestructura Azure (Bicep)
// Modelo Predictivo de Riesgo Académico
// ============================================================================

// ---------------------------------------------------------------------------
// Parámetros
// ---------------------------------------------------------------------------

@description('Nombre del entorno (dev, staging, prod)')
param environmentName string

@description('Región de Azure para los recursos')
param location string = resourceGroup().location

@secure()
@description('Contraseña del administrador de PostgreSQL')
param dbAdminPassword string

@secure()
@description('Clave secreta para firmar tokens JWT')
param jwtSecretKey string

@description('Nombre de la base de datos')
param dbName string = 'mpra_db'

@description('Usuario administrador de PostgreSQL')
param dbAdminUser string = 'mpraadmin'

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var acrName = 'acrmpra${environmentName}'
var containerAppEnvName = 'cae-mpra-${environmentName}'
var containerAppName = 'ca-mpra-${environmentName}'
var postgresServerName = 'pg-mpra-${environmentName}'
var logAnalyticsName = 'log-mpra-${environmentName}'

var databaseUrl = 'postgresql+asyncpg://${dbAdminUser}:${dbAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${dbName}?sslmode=require'

// AcrPull built-in role definition ID
var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

// ---------------------------------------------------------------------------
// Azure Container Registry
// ---------------------------------------------------------------------------

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

// ---------------------------------------------------------------------------
// Log Analytics Workspace (requerido por Container App Environment)
// ---------------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------------
// Container App Environment
// ---------------------------------------------------------------------------

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerAppEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ---------------------------------------------------------------------------
// PostgreSQL Flexible Server
// ---------------------------------------------------------------------------

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: postgresServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: dbAdminUser
    administratorLoginPassword: dbAdminPassword
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

// ---------------------------------------------------------------------------
// PostgreSQL Database
// ---------------------------------------------------------------------------

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  parent: postgresServer
  name: dbName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// ---------------------------------------------------------------------------
// PostgreSQL Firewall Rule — Permitir acceso desde servicios de Azure
// ---------------------------------------------------------------------------

resource postgresFirewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------------------------------------------------------------------------
// Container App
// ---------------------------------------------------------------------------

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'database-url'
          value: databaseUrl
        }
        {
          name: 'jwt-secret-key'
          value: jwtSecretKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mpra-backend'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'JWT_SECRET_KEY'
              secretRef: 'jwt-secret-key'
            }
            {
              name: 'HOST'
              value: '0.0.0.0'
            }
            {
              name: 'PORT'
              value: '8000'
            }
            {
              name: 'LOG_LEVEL'
              value: 'info'
            }
            {
              name: 'CORS_ORIGINS'
              value: '*'
            }
            {
              name: 'MODEL_PATH'
              value: 'ml_models/modelo_logistico.joblib'
            }
            {
              name: 'SCALER_PATH'
              value: 'ml_models/scaler.joblib'
            }
            {
              name: 'DATASET_PATH'
              value: 'datasets/dataset_estudiantes_decimal.csv'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Role Assignment — AcrPull para la identidad del Container App sobre el ACR
// ---------------------------------------------------------------------------

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, containerApp.id, acrPullRoleDefinitionId)
  scope: acr
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleDefinitionId
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output postgresHost string = postgresServer.properties.fullyQualifiedDomainName
output containerAppName string = containerApp.name
output containerAppEnvironmentName string = containerAppEnv.name
