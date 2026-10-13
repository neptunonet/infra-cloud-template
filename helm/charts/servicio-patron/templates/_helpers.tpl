{{/*
Fully qualified name. If the release name already contains the chart name
(e.g. "helm install servicio-patron ..."), use it as-is to avoid "servicio-patron-servicio-patron".
*/}}
{{- define "servicio-patron.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
