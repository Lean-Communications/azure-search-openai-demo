@description('Name of the Application Insights resource to query')
param applicationInsightsName string

@description('Location for the workbook resource')
param location string = resourceGroup().location

@description('Tags for the workbook resource')
param tags object = {}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

var workbookId = guid(resourceGroup().id, 'eval-dashboard-workbook')
var appInsightsId = applicationInsights.id

// ── KQL Queries ──

var kpiTilesQuery = '''
customEvents
| where name == "EvalRunCompleted"
| extend run_id = tostring(customDimensions.run_id)
| extend groundedness_pass_rate = todouble(customDimensions.groundedness_pass_rate)
| extend relevance_pass_rate = todouble(customDimensions.relevance_pass_rate)
| extend citations_matched_rate = todouble(customDimensions.citations_matched_rate)
| extend latency_mean = todouble(customDimensions.latency_mean)
| extend num_questions = toint(customDimensions.num_questions)
| top 1 by timestamp desc
| project groundedness_pass_rate, relevance_pass_rate, citations_matched_rate, latency_mean, num_questions
'''

var kpiTableQuery = '''
customEvents
| where name == "EvalRunCompleted"
| extend run_id = tostring(customDimensions.run_id)
| extend groundedness_pct = round(todouble(customDimensions.groundedness_pass_rate) * 100, 1)
| extend relevance_pct = round(todouble(customDimensions.relevance_pass_rate) * 100, 1)
| extend citations_pct = round(todouble(customDimensions.citations_matched_rate) * 100, 1)
| extend any_citation_pct = round(todouble(customDimensions.any_citation_rate) * 100, 1)
| extend latency_mean = round(todouble(customDimensions.latency_mean), 1)
| extend latency_max = round(todouble(customDimensions.latency_max), 1)
| extend answer_length_mean = round(todouble(customDimensions.answer_length_mean), 0)
| extend num_questions = toint(customDimensions.num_questions)
| top 1 by timestamp desc
| project run_id, num_questions, groundedness_pct, relevance_pct, citations_pct, any_citation_pct, latency_mean, latency_max, answer_length_mean, timestamp
'''

var trendPassRatesQuery = '''
customEvents
| where name == "EvalRunCompleted"
| extend groundedness = round(todouble(customDimensions.groundedness_pass_rate) * 100, 1)
| extend relevance = round(todouble(customDimensions.relevance_pass_rate) * 100, 1)
| extend citations = round(todouble(customDimensions.citations_matched_rate) * 100, 1)
| project timestamp, groundedness, relevance, citations
| order by timestamp asc
'''

var trendLatencyQuery = '''
customEvents
| where name == "EvalRunCompleted"
| extend latency_mean = round(todouble(customDimensions.latency_mean), 1)
| extend latency_max = round(todouble(customDimensions.latency_max), 1)
| project timestamp, latency_mean, latency_max
| order by timestamp asc
'''

var drilldownQuery = '''
let latest_run = toscalar(
  customEvents
  | where name == "EvalRunCompleted"
  | top 1 by timestamp desc
  | project tostring(customDimensions.run_id)
);
customEvents
| where name == "EvalQuestionResult"
| where tostring(customDimensions.run_id) == latest_run
| extend
    Source = tostring(customDimensions.source),
    Question = tostring(customDimensions.question),
    Groundedness = todouble(customDimensions.groundedness),
    Relevance = todouble(customDimensions.relevance),
    CitationsMatched = todouble(customDimensions.citations_matched),
    AnyCitation = tobool(customDimensions.any_citation),
    LatencySec = round(todouble(customDimensions.latency), 1),
    AnswerLength = toint(customDimensions.answer_length)
| project Source, Question, Groundedness, Relevance, CitationsMatched, AnyCitation, LatencySec, AnswerLength
| order by Groundedness asc
'''

var detailQuery = '''
let latest_run = toscalar(
  customEvents
  | where name == "EvalRunCompleted"
  | top 1 by timestamp desc
  | project tostring(customDimensions.run_id)
);
customEvents
| where name == "EvalQuestionResult"
| where tostring(customDimensions.run_id) == latest_run
| extend
    Source = tostring(customDimensions.source),
    Question = tostring(customDimensions.question),
    Groundedness = todouble(customDimensions.groundedness),
    Relevance = todouble(customDimensions.relevance),
    Answer = tostring(customDimensions.answer),
    ExpectedAnswer = tostring(customDimensions.truth),
    RetrievedContext = tostring(customDimensions.context)
| project Source, Question, Groundedness, Relevance, Answer, ExpectedAnswer, RetrievedContext
| order by Groundedness asc
'''

var sourceComparisonQuery = '''
let latest_run = toscalar(
  customEvents
  | where name == "EvalRunCompleted"
  | top 1 by timestamp desc
  | project tostring(customDimensions.run_id)
);
customEvents
| where name == "EvalQuestionResult"
| where tostring(customDimensions.run_id) == latest_run
| extend
    source = tostring(customDimensions.source),
    groundedness = todouble(customDimensions.groundedness),
    relevance = todouble(customDimensions.relevance),
    citations_matched = todouble(customDimensions.citations_matched),
    any_citation = tobool(customDimensions.any_citation),
    latency = todouble(customDimensions.latency)
| summarize
    Questions = count(),
    Groundedness_Avg = round(avg(groundedness), 2),
    Groundedness_Pass = round(countif(groundedness >= 4) * 100.0 / count(), 1),
    Relevance_Avg = round(avg(relevance), 2),
    Relevance_Pass = round(countif(relevance >= 4) * 100.0 / count(), 1),
    Citations_Matched_Avg = round(avg(citations_matched) * 100, 1),
    Any_Citation_Pct = round(countif(any_citation) * 100.0 / count(), 1),
    Latency_Avg = round(avg(latency), 2)
  by Source = source
| order by Source asc
'''

var operationHistoryQuery = '''
customEvents
| where name == "OperationStarted" or name == "OperationCompleted"
| extend
    operation = tostring(customDimensions.operation),
    status = tostring(customDimensions.status),
    duration = todouble(customDimensions.duration_seconds),
    details = tostring(customDimensions.details),
    error = tostring(customDimensions.error)
| project timestamp, name, operation, status, duration, details, error
| order by timestamp desc
'''

// ── Workbook Resource ──

resource evalWorkbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: workbookId
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'RAG Evaluation Dashboard'
    category: 'workbook'
    sourceId: applicationInsights.id
    serializedData: string({
      version: 'Notebook/1.0'
      items: [
        {
          type: 1
          content: { json: '## Operation History\\nRecent generate and evaluate runs.' }
          name: 'header-ops'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: operationHistoryQuery
            size: 0
            title: 'Recent Operations'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'table'
          }
          name: 'ops-table'
        }
        {
          type: 1
          content: { json: '## Latest Run KPIs\\nKey metrics from the most recent evaluation run.' }
          name: 'header-kpis'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: kpiTilesQuery
            size: 4
            title: 'Latest Run Summary'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'tiles'
            tileSettings: {
              titleContent: {
                columnMatch: 'groundedness_pass_rate'
                formatter: 12
                formatOptions: { palette: 'greenRed' }
              }
              showBorder: true
            }
          }
          name: 'kpi-tiles'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: kpiTableQuery
            size: 0
            title: 'Latest Run Details'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'table'
          }
          name: 'kpi-table'
        }
        {
          type: 1
          content: { json: '## Trends Over Time\\nPass rates and latency across evaluation runs.' }
          name: 'header-trends'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: trendPassRatesQuery
            size: 0
            title: 'Pass Rates Over Time (%)'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'linechart'
            chartSettings: {
              xAxis: 'timestamp'
              yAxis: [ 'groundedness', 'relevance', 'citations' ]
              seriesLabelSettings: [
                { series: 'groundedness', label: 'Groundedness' }
                { series: 'relevance', label: 'Relevance' }
                { series: 'citations', label: 'Citations Matched' }
              ]
            }
          }
          name: 'trend-pass-rates'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: trendLatencyQuery
            size: 0
            title: 'Latency Over Time (seconds)'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'linechart'
            chartSettings: {
              xAxis: 'timestamp'
              yAxis: [ 'latency_mean', 'latency_max' ]
              seriesLabelSettings: [
                { series: 'latency_mean', label: 'Mean Latency' }
                { series: 'latency_max', label: 'Max Latency' }
              ]
            }
          }
          name: 'trend-latency'
        }
        {
          type: 1
          content: { json: '## Manual vs Generated Questions\\nCompare metrics between manually curated and auto-generated questions.' }
          name: 'header-source-comparison'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: sourceComparisonQuery
            size: 0
            title: 'Metrics by Question Source (Latest Run)'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'table'
          }
          name: 'source-comparison-table'
        }
        {
          type: 1
          content: { json: '## Per-Question Drill-down\\nDetailed results for individual questions from the latest run.' }
          name: 'header-drilldown'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: drilldownQuery
            size: 0
            title: 'Per-Question Scores (Latest Run)'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'table'
            gridSettings: {
              sortBy: [ { itemKey: 'Groundedness', sortOrder: 1 } ]
            }
          }
          name: 'drilldown-table'
        }
        {
          type: 1
          content: { json: '## Question Detail\\nFull answer, expected answer, and retrieved context for each question. Scroll right to see all columns.' }
          name: 'header-detail'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: detailQuery
            size: 0
            title: 'Full Question Details (Latest Run)'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            crossComponentResources: [ appInsightsId ]
            visualization: 'table'
            gridSettings: {
              formatters: [
                {
                  columnMatch: 'Answer'
                  formatter: 1
                  formatOptions: {
                    linkTarget: 'CellDetails'
                    linkIsContextBlade: true
                  }
                }
                {
                  columnMatch: 'ExpectedAnswer'
                  formatter: 1
                  formatOptions: {
                    linkTarget: 'CellDetails'
                    linkIsContextBlade: true
                  }
                }
                {
                  columnMatch: 'RetrievedContext'
                  formatter: 1
                  formatOptions: {
                    linkTarget: 'CellDetails'
                    linkIsContextBlade: true
                  }
                }
              ]
              sortBy: [ { itemKey: 'Groundedness', sortOrder: 1 } ]
            }
          }
          name: 'detail-table'
        }
      ]
      isLocked: false
      fallbackResourceIds: [ appInsightsId ]
    })
  }
}

output workbookId string = evalWorkbook.id
output workbookName string = evalWorkbook.name
