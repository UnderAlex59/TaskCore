{{- define "task-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else if contains (include "task-platform.name" .) .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "task-platform.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "task-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.labels" -}}
helm.sh/chart: {{ include "task-platform.chart" . }}
app.kubernetes.io/name: {{ include "task-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "task-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "task-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "task-platform.backend.fullname" -}}
{{- printf "%s-backend" (include "task-platform.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.frontend.fullname" -}}
{{- printf "%s-frontend" (include "task-platform.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.backend.configmap" -}}
{{- printf "%s-config" (include "task-platform.backend.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.backend.secret" -}}
{{- printf "%s-secret" (include "task-platform.backend.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.uploads.pvc" -}}
{{- printf "%s-uploads" (include "task-platform.backend.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "task-platform.frontend.backendUpstream" -}}
{{- if .Values.frontend.proxy.backendUpstream -}}
{{- .Values.frontend.proxy.backendUpstream -}}
{{- else -}}
{{- printf "%s:%v" (include "task-platform.backend.fullname" .) .Values.backend.service.port -}}
{{- end -}}
{{- end -}}
