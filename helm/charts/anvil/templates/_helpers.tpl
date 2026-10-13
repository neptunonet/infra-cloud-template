{{/*
Fully qualified name. If the release name already contains the chart name
(e.g. "helm install anvil ..."), use it as-is to avoid "anvil-anvil".
*/}}
{{- define "anvil.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
