{{/*
Expand the name of the chart.
*/}}
{{- define "draft.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncate at 63 chars because some Kubernetes name fields are limited to this.
*/}}
{{- define "draft.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label.
*/}}
{{- define "draft.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "draft.labels" -}}
helm.sh/chart: {{ include "draft.chart" . }}
{{ include "draft.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels used by Deployment and Service.
*/}}
{{- define "draft.selectorLabels" -}}
app.kubernetes.io/name: {{ include "draft.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret that holds DRAFT_MCP_TOKEN and API keys.
When mcp.existingSecret is set, use that; otherwise use the chart-managed Secret.
*/}}
{{- define "draft.secretName" -}}
{{- if .Values.mcp.existingSecret }}
{{- .Values.mcp.existingSecret }}
{{- else }}
{{- include "draft.fullname" . }}
{{- end }}
{{- end }}

{{/*
Name of the PVC.
*/}}
{{- define "draft.pvcName" -}}
{{- printf "%s-data" (include "draft.fullname" .) }}
{{- end }}
