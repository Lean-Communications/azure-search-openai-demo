// Parameters for both function apps
param location string = resourceGroup().location
param tags object = {}
param applicationInsightsName string
param storageResourceGroupName string
param searchServiceResourceGroupName string
param openAiResourceGroupName string
param documentIntelligenceResourceGroupName string
param visionServiceName string = ''
param visionResourceGroupName string = ''
param contentUnderstandingServiceName string = ''
param contentUnderstandingResourceGroupName string = ''

// App environment variables from main.bicep
param appEnvVariables object

// Function App Names
param documentExtractorName string
param figureProcessorName string
param textProcessorName string
param documentIngesterName string
param evalRunnerName string = ''

@description('Whether to deploy the eval runner function app')
param deployEvalRunner bool = false

@description('Target URL for the eval runner to call (backend /chat endpoint)')
param evalTargetUrl string = ''

@description('Entra App ID of the backend (for managed identity auth)')
param evalTargetAppId string = ''
// OpenID issuer provided by main template (e.g. https://login.microsoftonline.com/<tenantId>/v2.0)
param openIdIssuer string

@description('The principal ID of the Search service user-assigned managed identity')
param searchUserAssignedIdentityClientId string

@description('Client ID of the Logic App managed identity to allow calling the document ingester')
param logicAppIdentityClientId string = ''

var abbrs = loadJsonContent('../abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, resourceGroup().id, location))

var documentExtractorRuntimeStorageName = '${abbrs.storageStorageAccounts}doc${take(resourceToken, 18)}'
var figureProcessorRuntimeStorageName = '${abbrs.storageStorageAccounts}fig${take(resourceToken, 18)}'
var textProcessorRuntimeStorageName = '${abbrs.storageStorageAccounts}txt${take(resourceToken, 18)}'
var documentIngesterRuntimeStorageName = '${abbrs.storageStorageAccounts}ing${take(resourceToken, 18)}'
var evalRunnerRuntimeStorageName = '${abbrs.storageStorageAccounts}evl${take(resourceToken, 18)}'

var documentExtractorHostId = 'doc-skill-${take(resourceToken, 12)}'
var figureProcessorHostId = 'fig-skill-${take(resourceToken, 12)}'
var textProcessorHostId = 'txt-skill-${take(resourceToken, 12)}'
var documentIngesterHostId = 'ing-skill-${take(resourceToken, 12)}'
var evalRunnerHostId = 'evl-skill-${take(resourceToken, 12)}'

var runtimeStorageRoles = [
  {
    suffix: 'blob'
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  }
  {
    suffix: 'queue'
    roleDefinitionId: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  }
  {
    suffix: 'table'
    roleDefinitionId: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  }
]

// Deployment storage container name (same name used in each function's storage account)
var deploymentContainerName = 'app-package-deployment'

// Runtime storage accounts per function (Flex Consumption requirement)
module documentExtractorRuntimeStorageAccount '../core/storage/storage-account.bicep' = {
  name: 'doc-extractor-runtime-storage'
  params: {
    name: documentExtractorRuntimeStorageName
    location: location
    tags: tags
    allowBlobPublicAccess: false
    containers: [
      {
        name: deploymentContainerName
      }
    ]
  }
}

module figureProcessorRuntimeStorageAccount '../core/storage/storage-account.bicep' = {
  name: 'figure-processor-runtime-storage'
  params: {
    name: figureProcessorRuntimeStorageName
    location: location
    tags: tags
    allowBlobPublicAccess: false
    containers: [
      {
        name: deploymentContainerName
      }
    ]
  }
}

module textProcessorRuntimeStorageAccount '../core/storage/storage-account.bicep' = {
  name: 'text-processor-runtime-storage'
  params: {
    name: textProcessorRuntimeStorageName
    location: location
    tags: tags
    allowBlobPublicAccess: false
    containers: [
      {
        name: deploymentContainerName
      }
    ]
  }
}

module documentIngesterRuntimeStorageAccount '../core/storage/storage-account.bicep' = {
  name: 'document-ingester-runtime-storage'
  params: {
    name: documentIngesterRuntimeStorageName
    location: location
    tags: tags
    allowBlobPublicAccess: false
    containers: [
      {
        name: deploymentContainerName
      }
    ]
  }
}

module evalRunnerRuntimeStorageAccount '../core/storage/storage-account.bicep' = if (deployEvalRunner) {
  name: 'eval-runner-runtime-storage'
  params: {
    name: evalRunnerRuntimeStorageName
    location: location
    tags: tags
    allowBlobPublicAccess: false
    containers: [
      {
        name: deploymentContainerName
      }
    ]
  }
}

resource documentExtractorRuntimeStorage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: documentExtractorRuntimeStorageName
}

resource figureProcessorRuntimeStorage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: figureProcessorRuntimeStorageName
}

resource textProcessorRuntimeStorage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: textProcessorRuntimeStorageName
}

resource documentIngesterRuntimeStorage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: documentIngesterRuntimeStorageName
}

resource evalRunnerRuntimeStorage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = if (deployEvalRunner) {
  name: evalRunnerRuntimeStorageName
}

resource documentExtractorRuntimeStorageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in runtimeStorageRoles: {
  name: guid(documentExtractorRuntimeStorage.id, role.roleDefinitionId, 'doc-storage-roles')
  scope: documentExtractorRuntimeStorage
  properties: {
    principalId: functionsUserIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', role.roleDefinitionId)
  }
  dependsOn: [
    documentExtractorRuntimeStorageAccount
  ]
}]

resource figureProcessorRuntimeStorageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in runtimeStorageRoles: {
  name: guid(figureProcessorRuntimeStorage.id, role.roleDefinitionId, 'figure-storage-roles')
  scope: figureProcessorRuntimeStorage
  properties: {
    principalId: functionsUserIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', role.roleDefinitionId)
  }
  dependsOn: [
    figureProcessorRuntimeStorageAccount
  ]
}]

resource textProcessorRuntimeStorageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in runtimeStorageRoles: {
  name: guid(textProcessorRuntimeStorage.id, role.roleDefinitionId, 'text-storage-roles')
  scope: textProcessorRuntimeStorage
  properties: {
    principalId: functionsUserIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', role.roleDefinitionId)
  }
  dependsOn: [
    textProcessorRuntimeStorageAccount
  ]
}]

resource documentIngesterRuntimeStorageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in runtimeStorageRoles: {
  name: guid(documentIngesterRuntimeStorage.id, role.roleDefinitionId, 'ingester-storage-roles')
  scope: documentIngesterRuntimeStorage
  properties: {
    principalId: functionsUserIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', role.roleDefinitionId)
  }
  dependsOn: [
    documentIngesterRuntimeStorageAccount
  ]
}]

resource evalRunnerRuntimeStorageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in runtimeStorageRoles: if (deployEvalRunner) {
  name: guid(evalRunnerRuntimeStorage.id, role.roleDefinitionId, 'eval-storage-roles')
  scope: evalRunnerRuntimeStorage
  properties: {
    principalId: functionsUserIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', role.roleDefinitionId)
  }
  dependsOn: [
    evalRunnerRuntimeStorageAccount
  ]
}]

// Flex Consumption supports only one Function App per plan; create a dedicated plan per ingestion function
module documentExtractorPlan 'br/public:avm/res/web/serverfarm:0.1.1' = {
  name: 'doc-extractor-plan'
  params: {
    name: '${abbrs.webServerFarms}doc-extractor-${resourceToken}'
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
    reserved: true
    location: location
    tags: tags
  }
}

module figureProcessorPlan 'br/public:avm/res/web/serverfarm:0.1.1' = {
  name: 'figure-processor-plan'
  params: {
    name: '${abbrs.webServerFarms}figure-processor-${resourceToken}'
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
    reserved: true
    location: location
    tags: tags
  }
}

module textProcessorPlan 'br/public:avm/res/web/serverfarm:0.1.1' = {
  name: 'text-processor-plan'
  params: {
    name: '${abbrs.webServerFarms}text-processor-${resourceToken}'
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
    reserved: true
    location: location
    tags: tags
  }
}

module documentIngesterPlan 'br/public:avm/res/web/serverfarm:0.1.1' = {
  name: 'document-ingester-plan'
  params: {
    name: '${abbrs.webServerFarms}doc-ingester-${resourceToken}'
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
    reserved: true
    location: location
    tags: tags
  }
}


module evalRunnerPlan 'br/public:avm/res/web/serverfarm:0.1.1' = if (deployEvalRunner) {
  name: 'eval-runner-plan'
  params: {
    name: '${abbrs.webServerFarms}eval-runner-${resourceToken}'
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
    reserved: true
    location: location
    tags: tags
  }
}

module functionsUserIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.1' = {
  name: 'functions-user-identity'
  params: {
    location: location
    tags: tags
    name: 'functions-user-identity-${resourceToken}'
  }
}



// Document Extractor Function App
// App registration for document extractor (uses function identity principalId as FIC subject)
module documentExtractorAppReg '../core/auth/appregistration.bicep' = {
  name: 'doc-extractor-appreg'
  params: {
    appUniqueName: '${documentExtractorName}-appreg'
    cloudEnvironment: environment().name
    webAppIdentityId: functionsUserIdentity.outputs.principalId
    clientAppName: '${documentExtractorName}-app'
    clientAppDisplayName: '${documentExtractorName} Entra App'
    issuer: openIdIssuer
    webAppEndpoint: 'https://${documentExtractorName}.azurewebsites.net'
  }
}

module documentExtractor 'functions-app.bicep' = {
  name: 'document-extractor-func'
  params: {
    name: documentExtractorName
    location: location
    tags: union(tags, { 'azd-service-name': 'document-extractor' })
    applicationInsightsName: applicationInsightsName
    appServicePlanId: documentExtractorPlan.outputs.resourceId
    runtimeName: 'python'
    runtimeVersion: '3.11'
    identityId: functionsUserIdentity.outputs.resourceId
    identityClientId: functionsUserIdentity.outputs.clientId
    authClientId: documentExtractorAppReg.outputs.clientAppId
    authIdentifierUri: documentExtractorAppReg.outputs.identifierUri
    authTenantId: tenant().tenantId
    searchUserAssignedIdentityClientId: searchUserAssignedIdentityClientId
    storageAccountName: documentExtractorRuntimeStorageName
    deploymentStorageContainerName: deploymentContainerName
    appSettings: union(appEnvVariables, {
      AzureFunctionsWebHost__hostid: documentExtractorHostId
    })
    instanceMemoryMB: 4096 // High memory for document processing
    maximumInstanceCount: 100
  }
  dependsOn: [
    documentExtractorRuntimeStorageAccount
  ]
}

// Figure Processor Function App
module figureProcessorAppReg '../core/auth/appregistration.bicep' = {
  name: 'figure-processor-appreg'
  params: {
    appUniqueName: '${figureProcessorName}-app'
    cloudEnvironment: environment().name
    webAppIdentityId: functionsUserIdentity.outputs.principalId
    clientAppName: 'skill-${figureProcessorName}'
    clientAppDisplayName: 'skill-${figureProcessorName}'
    issuer: openIdIssuer
    webAppEndpoint: 'https://${figureProcessorName}.azurewebsites.net'
  }
}

module figureProcessor 'functions-app.bicep' = {
  name: 'figure-processor-func'
  params: {
    name: figureProcessorName
    location: location
    tags: union(tags, { 'azd-service-name': 'figure-processor' })
    applicationInsightsName: applicationInsightsName
    appServicePlanId: figureProcessorPlan.outputs.resourceId
    runtimeName: 'python'
    runtimeVersion: '3.11'
    storageAccountName: figureProcessorRuntimeStorageName
    deploymentStorageContainerName: deploymentContainerName
    identityId: functionsUserIdentity.outputs.resourceId
    identityClientId: functionsUserIdentity.outputs.clientId
    authClientId: figureProcessorAppReg.outputs.clientAppId
    authIdentifierUri: figureProcessorAppReg.outputs.identifierUri
    authTenantId: tenant().tenantId
    searchUserAssignedIdentityClientId: searchUserAssignedIdentityClientId
    appSettings: union(appEnvVariables, {
      AzureFunctionsWebHost__hostid: figureProcessorHostId
    })
    instanceMemoryMB: 2048
    maximumInstanceCount: 100
  }
  dependsOn: [
    figureProcessorRuntimeStorageAccount
  ]
}

// Text Processor Function App
module textProcessorAppReg '../core/auth/appregistration.bicep' = {
  name: 'text-processor-appreg'
  params: {
    appUniqueName: '${textProcessorName}-app'
    cloudEnvironment: environment().name
    webAppIdentityId: functionsUserIdentity.outputs.principalId
    clientAppName: 'skill-${textProcessorName}'
    clientAppDisplayName: 'skill-${textProcessorName}'
    issuer: openIdIssuer
    webAppEndpoint: 'https://${textProcessorName}.azurewebsites.net'
  }
}

module textProcessor 'functions-app.bicep' = {
  name: 'text-processor-func'
  params: {
    name: textProcessorName
    location: location
    tags: union(tags, { 'azd-service-name': 'text-processor' })
    applicationInsightsName: applicationInsightsName
    appServicePlanId: textProcessorPlan.outputs.resourceId
    runtimeName: 'python'
    runtimeVersion: '3.11'
    storageAccountName: textProcessorRuntimeStorageName
    deploymentStorageContainerName: deploymentContainerName
    identityId: functionsUserIdentity.outputs.resourceId
    identityClientId: functionsUserIdentity.outputs.clientId
    authClientId: textProcessorAppReg.outputs.clientAppId
    authIdentifierUri: textProcessorAppReg.outputs.identifierUri
    authTenantId: tenant().tenantId
    searchUserAssignedIdentityClientId: searchUserAssignedIdentityClientId
    appSettings: union(appEnvVariables, {
      AzureFunctionsWebHost__hostid: textProcessorHostId
    })
    instanceMemoryMB: 2048 // Standard memory for embedding
    maximumInstanceCount: 100
  }
  dependsOn: [
    textProcessorRuntimeStorageAccount
  ]
}

// Document Ingester Function App
module documentIngesterAppReg '../core/auth/appregistration.bicep' = {
  name: 'doc-ingester-appreg'
  params: {
    appUniqueName: '${documentIngesterName}-appreg'
    cloudEnvironment: environment().name
    webAppIdentityId: functionsUserIdentity.outputs.principalId
    clientAppName: '${documentIngesterName}-app'
    clientAppDisplayName: '${documentIngesterName} Entra App'
    issuer: openIdIssuer
    webAppEndpoint: 'https://${documentIngesterName}.azurewebsites.net'
  }
}

module documentIngester 'functions-app.bicep' = {
  name: 'document-ingester-func'
  params: {
    name: documentIngesterName
    location: location
    tags: union(tags, { 'azd-service-name': 'document-ingester' })
    applicationInsightsName: applicationInsightsName
    appServicePlanId: documentIngesterPlan.outputs.resourceId
    runtimeName: 'python'
    runtimeVersion: '3.11'
    identityId: functionsUserIdentity.outputs.resourceId
    identityClientId: functionsUserIdentity.outputs.clientId
    authClientId: documentIngesterAppReg.outputs.clientAppId
    authIdentifierUri: documentIngesterAppReg.outputs.identifierUri
    authTenantId: tenant().tenantId
    searchUserAssignedIdentityClientId: searchUserAssignedIdentityClientId
    additionalAllowedApplicationClientIds: !empty(logicAppIdentityClientId) ? [logicAppIdentityClientId] : []
    storageAccountName: documentIngesterRuntimeStorageName
    deploymentStorageContainerName: deploymentContainerName
    appSettings: union(appEnvVariables, {
      AzureFunctionsWebHost__hostid: documentIngesterHostId
    })
    instanceMemoryMB: 4096
    maximumInstanceCount: 100
  }
  dependsOn: [
    documentIngesterRuntimeStorageAccount
  ]
}

// Eval Runner Function App
module evalRunnerAppReg '../core/auth/appregistration.bicep' = if (deployEvalRunner) {
  name: 'eval-runner-appreg'
  params: {
    appUniqueName: '${evalRunnerName}-appreg'
    cloudEnvironment: environment().name
    webAppIdentityId: functionsUserIdentity.outputs.principalId
    clientAppName: '${evalRunnerName}-app'
    clientAppDisplayName: '${evalRunnerName} Entra App'
    issuer: openIdIssuer
    webAppEndpoint: 'https://${evalRunnerName}.azurewebsites.net'
  }
}

module evalRunner 'functions-app.bicep' = if (deployEvalRunner) {
  name: 'eval-runner-func'
  params: {
    name: evalRunnerName
    location: location
    tags: union(tags, { 'azd-service-name': 'eval-runner' })
    applicationInsightsName: applicationInsightsName
    appServicePlanId: deployEvalRunner ? evalRunnerPlan!.outputs.resourceId : ''
    runtimeName: 'python'
    runtimeVersion: '3.12'
    identityId: functionsUserIdentity.outputs.resourceId
    identityClientId: functionsUserIdentity.outputs.clientId
    authClientId: deployEvalRunner ? evalRunnerAppReg!.outputs.clientAppId : ''
    authIdentifierUri: deployEvalRunner ? evalRunnerAppReg!.outputs.identifierUri : ''
    authTenantId: tenant().tenantId
    searchUserAssignedIdentityClientId: searchUserAssignedIdentityClientId
    storageAccountName: evalRunnerRuntimeStorageName
    deploymentStorageContainerName: deploymentContainerName
    appSettings: union(appEnvVariables, {
      AzureFunctionsWebHost__hostid: evalRunnerHostId
      EVAL_TARGET_URL: evalTargetUrl
      EVAL_TARGET_APP_ID: evalTargetAppId
      EVAL_BLOB_CONTAINER: 'eval-data'
    })
    enableEasyAuth: false
    instanceMemoryMB: 2048
    maximumInstanceCount: 10
  }
  dependsOn: [
    evalRunnerRuntimeStorageAccount
  ]
}

// RBAC: Document Extractor Roles
module functionsIdentityRBAC 'functions-rbac.bicep' = {
  name: 'doc-extractor-rbac'
  params: {
    principalId: functionsUserIdentity.outputs.principalId
    storageResourceGroupName: storageResourceGroupName
    searchServiceResourceGroupName: searchServiceResourceGroupName
    openAiResourceGroupName: openAiResourceGroupName
    documentIntelligenceResourceGroupName: documentIntelligenceResourceGroupName
    visionServiceName: visionServiceName
    visionResourceGroupName: visionResourceGroupName
    contentUnderstandingServiceName: contentUnderstandingServiceName
    contentUnderstandingResourceGroupName: contentUnderstandingResourceGroupName
    useMultimodal: bool(appEnvVariables.USE_MULTIMODAL)
  }
}


// Outputs
output documentExtractorName string = documentExtractor.outputs.name
output documentExtractorUrl string = documentExtractor.outputs.defaultHostname
output figureProcessorName string = figureProcessor.outputs.name
output figureProcessorUrl string = figureProcessor.outputs.defaultHostname
output textProcessorName string = textProcessor.outputs.name
output textProcessorUrl string = textProcessor.outputs.defaultHostname
output documentIngesterName string = documentIngester.outputs.name
output documentIngesterUrl string = documentIngester.outputs.defaultHostname
// Resource IDs for each function app (used for auth_resource_id with managed identity secured skills)
output documentExtractorAuthIdentifierUri string = documentExtractorAppReg.outputs.identifierUri
output figureProcessorAuthIdentifierUri string = figureProcessorAppReg.outputs.identifierUri
output textProcessorAuthIdentifierUri string = textProcessorAppReg.outputs.identifierUri
output documentIngesterAuthIdentifierUri string = documentIngesterAppReg.outputs.identifierUri
output evalRunnerName string = deployEvalRunner ? evalRunner!.outputs.name : ''
output evalRunnerUrl string = deployEvalRunner ? evalRunner!.outputs.defaultHostname : ''
output evalRunnerAuthIdentifierUri string = deployEvalRunner ? evalRunnerAppReg!.outputs.identifierUri : ''
// Principal ID of the shared user-assigned identity (for additional role assignments in main.bicep)
output principalId string = functionsUserIdentity.outputs.principalId
output identityClientId string = functionsUserIdentity.outputs.clientId
