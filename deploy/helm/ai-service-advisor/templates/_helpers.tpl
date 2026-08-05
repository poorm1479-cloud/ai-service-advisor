{{- define "asa.name" -}}
ai-service-advisor
{{- end -}}

{{- define "asa.fullname" -}}
{{ .Release.Name }}
{{- end -}}
