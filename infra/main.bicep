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

@description('Nombre de la base de datos')
param dbName string = 'mpra_db'

@description('Usuario administrador de PostgreSQL')
param dbAdminUser string = 'mpraadmin'

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var acrName = 'acrmpra${environmentName}'
var containerAppEnvName = 'cae-mpra-${environmentName}'
var postgresServerName = 'pg-mpra-${environmentName}'
var logAnalyticsName = 'log-mpra-${environmentName}'


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
// Outputs
// El Container App se crea y configura desde deploy.sh para evitar timeouts
// de aprovisionamiento en el ARM deployment.
// ---------------------------------------------------------------------------

output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output postgresHost string = postgresServer.properties.fullyQualifiedDomainName
output containerAppEnvironmentName string = containerAppEnv.name
