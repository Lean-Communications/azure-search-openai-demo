// Logic App module for SharePoint document ingestion
// Deploys a Consumption Logic App that monitors a SharePoint folder for new/modified files
// and calls the document ingester Azure Function for each file.
//
// After deployment, you must authorize the SharePoint API connection in the Azure portal:
// 1. Go to the resource group → find the API connection resource (named <logicAppName>-sharepoint)
// 2. Click "Edit API connection" → "Authorize" → sign in with your SharePoint credentials → Save
// 3. Go to the Logic App → Overview → click "Enable"

param name string
param location string = resourceGroup().location
param tags object = {}

@description('Full URL of the SharePoint site (e.g. https://contoso.sharepoint.com/sites/mysite)')
param sharepointSiteUrl string

@description('SharePoint document library GUID (find via portal Logic App designer or SharePoint site settings)')
param sharepointLibraryId string

@description('Folder path within the SharePoint document library to monitor for new files')
param sharepointFolderPath string

@description('Full URL of the document ingester function endpoint (e.g. https://func-name.azurewebsites.net/api/ingest)')
param documentIngesterEndpoint string

@description('Entra ID audience (identifier URI) of the document ingester function for managed identity auth')
param documentIngesterAudience string

@description('Polling interval in minutes for checking new SharePoint files')
param pollingIntervalMinutes int = 5

@description('Resource ID of the user-assigned managed identity')
param identityId string

// Logic App expression fragments (multi-line strings avoid single-quote escaping issues in Bicep)
var connectionNameExpr = trim('''
@parameters('$connections')['sharepointonline']['connectionId']
''')

var driveIdExpr = trim('''
@triggerOutputs()?['body/{DriveId}']
''')

var driveItemIdExpr = trim('''
@triggerOutputs()?['body/{DriveItemId}']
''')

var filenameExpr = trim('''
@{encodeURIComponent(triggerOutputs()?['body/{FilenameWithExtension}'])}
''')

var linkExpr = trim('''
@triggerOutputs()?['body/{Link}']
''')

var splitOnExpr = trim('''
@triggerBody()?['value']
''')

// Build path fragments using Logic App runtime encoding (matching portal-generated format)
var encodeExprOpen = trim('''
@{encodeURIComponent(encodeURIComponent('
''')
var encodeExprClose = trim('''
'))}
''')

var siteDatasetPath = '/datasets/${encodeExprOpen}${sharepointSiteUrl}${encodeExprClose}'
var libraryTablePath = '/tables/${encodeExprOpen}${sharepointLibraryId}${encodeExprClose}'

// SharePoint Online API connection
// This creates the connection resource in an unauthorized state.
// A user must authorize it manually in the portal (one-time OAuth consent).
resource sharepointConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: '${name}-sharepoint'
  location: location
  tags: tags
  properties: {
    displayName: 'SharePoint - Document Ingestion'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'sharepointonline')
    }
  }
}

// Logic App workflow
resource logicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    state: 'Disabled' // Starts disabled — enable after authorizing the SharePoint connection
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      triggers: {
        When_a_file_is_created_or_modified: {
          type: 'ApiConnection'
          recurrence: {
            frequency: 'Minute'
            interval: pollingIntervalMinutes
          }
          splitOn: splitOnExpr
          inputs: {
            host: {
              connection: {
                name: connectionNameExpr
              }
            }
            method: 'get'
            path: '${siteDatasetPath}${libraryTablePath}/onupdatedfileitems'
            queries: {
              folderPath: sharepointFolderPath
            }
          }
        }
      }
      actions: {
        Call_Document_Ingester: {
          type: 'Http'
          runAfter: {}
          inputs: {
            method: 'POST'
            uri: documentIngesterEndpoint
            headers: {
              'X-Filename': filenameExpr
              'X-Source-Url': linkExpr
              'X-Drive-Id': driveIdExpr
              'X-Drive-Item-Id': driveItemIdExpr
            }
            authentication: {
              type: 'ManagedServiceIdentity'
              identity: identityId
              audience: documentIngesterAudience
            }
          }
          limit: {
            timeout: 'PT30M'
          }
        }
      }
      parameters: {
        '$connections': {
          defaultValue: {}
          type: 'Object'
        }
      }
    }
    parameters: {
      '$connections': {
        value: {
          sharepointonline: {
            connectionId: sharepointConnection.id
            connectionName: sharepointConnection.name
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'sharepointonline')
          }
        }
      }
    }
  }
}

output name string = logicApp.name
output resourceId string = logicApp.id
output connectionName string = sharepointConnection.name
