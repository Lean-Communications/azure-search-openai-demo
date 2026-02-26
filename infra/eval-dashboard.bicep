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

resource evalWorkbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: workbookId
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'RAG Evaluation Dashboard'
    category: 'workbook'
    sourceId: applicationInsights.id
    serializedData: serializedWorkbook
  }
}

var serializedWorkbook = string({
  version: 'Notebook/1.0'
  items: [
    // ── Tab 1: Latest Run KPIs ──
    {
      type: 1
      content: {
        json: '## Latest Run KPIs\nKey metrics from the most recent evaluation run.'
      }
      name: 'header-kpis'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: '''
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
        size: 4
        title: 'Latest Run Summary'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'tiles'
        tileSettings: {
          titleContent: {
            columnMatch: 'groundedness_pass_rate'
            formatter: 12
            formatOptions: {
              palette: 'greenRed'
            }
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
        query: '''
customEvents
| where name == "EvalRunCompleted"
| extend run_id = tostring(customDimensions.run_id)
| extend groundedness_pass_rate = todouble(customDimensions.groundedness_pass_rate) * 100
| extend relevance_pass_rate = todouble(customDimensions.relevance_pass_rate) * 100
| extend citations_matched_rate = todouble(customDimensions.citations_matched_rate) * 100
| extend any_citation_rate = todouble(customDimensions.any_citation_rate) * 100
| extend latency_mean = todouble(customDimensions.latency_mean)
| extend latency_max = todouble(customDimensions.latency_max)
| extend answer_length_mean = todouble(customDimensions.answer_length_mean)
| extend num_questions = toint(customDimensions.num_questions)
| top 1 by timestamp desc
| project
    ['Run ID'] = run_id,
    ['Questions'] = num_questions,
    ['Groundedness %'] = groundedness_pass_rate,
    ['Relevance %'] = relevance_pass_rate,
    ['Citation Match %'] = citations_matched_rate,
    ['Any Citation %'] = any_citation_rate,
    ['Avg Latency (s)'] = latency_mean,
    ['Max Latency (s)'] = latency_max,
    ['Avg Answer Length'] = answer_length_mean,
    ['Timestamp'] = timestamp
'''
        size: 0
        title: 'Latest Run Details'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
      }
      name: 'kpi-table'
    }
    // ── Tab 2: Trends Over Time ──
    {
      type: 1
      content: {
        json: '## Trends Over Time\nPass rates and latency across evaluation runs.'
      }
      name: 'header-trends'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: '''
customEvents
| where name == "EvalRunCompleted"
| extend groundedness = todouble(customDimensions.groundedness_pass_rate) * 100
| extend relevance = todouble(customDimensions.relevance_pass_rate) * 100
| extend citations = todouble(customDimensions.citations_matched_rate) * 100
| project timestamp, groundedness, relevance, citations
| order by timestamp asc
'''
        size: 0
        title: 'Pass Rates Over Time (%)'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'linechart'
        chartSettings: {
          xAxis: 'timestamp'
          yAxis: ['groundedness', 'relevance', 'citations']
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
        query: '''
customEvents
| where name == "EvalRunCompleted"
| extend latency_mean = todouble(customDimensions.latency_mean)
| extend latency_max = todouble(customDimensions.latency_max)
| project timestamp, latency_mean, latency_max
| order by timestamp asc
'''
        size: 0
        title: 'Latency Over Time (seconds)'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'linechart'
        chartSettings: {
          xAxis: 'timestamp'
          yAxis: ['latency_mean', 'latency_max']
          seriesLabelSettings: [
            { series: 'latency_mean', label: 'Mean Latency' }
            { series: 'latency_max', label: 'Max Latency' }
          ]
        }
      }
      name: 'trend-latency'
    }
    // ── Tab 3: Per-Question Drill-down ──
    {
      type: 1
      content: {
        json: '## Per-Question Drill-down\nDetailed results for individual questions from the latest run.'
      }
      name: 'header-drilldown'
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        query: '''
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
    Question = tostring(customDimensions.question),
    Groundedness = todouble(customDimensions.groundedness),
    Relevance = todouble(customDimensions.relevance),
    ['Citations Matched'] = todouble(customDimensions.citations_matched),
    ['Any Citation'] = tobool(customDimensions.any_citation),
    ['Latency (s)'] = todouble(customDimensions.latency),
    ['Answer Length'] = toint(customDimensions.answer_length)
| project Question, Groundedness, Relevance, ['Citations Matched'], ['Any Citation'], ['Latency (s)'], ['Answer Length']
| order by Groundedness asc
'''
        size: 0
        title: 'Per-Question Results (Latest Run)'
        queryType: 0
        resourceType: 'microsoft.insights/components'
        visualization: 'table'
        gridSettings: {
          sortBy: [
            { itemKey: 'Groundedness', sortOrder: 1 }
          ]
        }
      }
      name: 'drilldown-table'
    }
  ]
  isLocked: false
  fallbackResourceIds: [
    applicationInsights.id
  ]
})

output workbookId string = evalWorkbook.id
output workbookName string = evalWorkbook.name
