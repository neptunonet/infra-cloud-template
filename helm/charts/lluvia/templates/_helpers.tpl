{{/*
Nombre completo. Si el release ya contiene el nombre del chart («helm install lluvia ...»), se usa tal cual para
no tener «lluvia-lluvia».
*/}}
{{- define "lluvia.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
