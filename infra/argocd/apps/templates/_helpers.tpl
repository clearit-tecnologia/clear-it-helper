{{- define "apps.repoURL" -}}
{{- required "repoURL is required (injected by infra/argocd/root.yaml)" .Values.repoURL -}}
{{- end -}}

{{- define "apps.targetRevision" -}}
{{- default "HEAD" .Values.targetRevision -}}
{{- end -}}

{{/* Common Application spec tail: destination + syncPolicy. Args: ctx, namespace */}}
{{- define "apps.syncPolicy" -}}
syncPolicy:
  {{- toYaml .ctx.Values.syncPolicy | nindent 2 }}
  syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
    - SkipDryRunOnMissingResource=true
    {{- range .extraOptions }}
    - {{ . }}
    {{- end }}
{{- end -}}

{{- define "apps.enabled" -}}
{{- $e := .component.enabled -}}
{{- if eq (toString $e) "langfuse" -}}
{{- .ctx.Values.langfuse.enabled -}}
{{- else -}}
{{- $e -}}
{{- end -}}
{{- end -}}
