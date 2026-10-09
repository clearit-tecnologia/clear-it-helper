{{/* Base name used by every resource (fixed by the integration contract). */}}
{{- define "ch.fullname" -}}
{{- default "clear-helper" .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ch.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels. Usage: include "ch.labels" (dict "ctx" . "component" "api") */}}
{{- define "ch.labels" -}}
helm.sh/chart: {{ include "ch.chart" .ctx }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
app.kubernetes.io/part-of: clear-helper
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
{{ include "ch.selectorLabels" . }}
{{- end -}}

{{- define "ch.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ch.fullname" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "ch.imageTag" -}}
{{- default .Chart.AppVersion .Values.image.tag -}}
{{- end -}}

{{- define "ch.backendImage" -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.backendImage.repository (include "ch.imageTag" .) -}}
{{- end -}}

{{- define "ch.frontendImage" -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.frontendImage.repository (include "ch.imageTag" .) -}}
{{- end -}}

{{- define "ch.imagePullSecrets" -}}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
Backend environment (API, worker, migration and bootstrap Jobs).
Rendered inline (no ConfigMap) because the PreSync/pre-install hooks run before any
regular chart resource exists.
*/}}
{{- define "ch.backendEnv" -}}
- name: CH_ENV
  value: {{ .Values.config.env | quote }}
- name: CH_LOG_LEVEL
  value: {{ .Values.config.logLevel | quote }}
- name: CH_HEALTH_TIMEOUT_SECONDS
  value: {{ .Values.config.healthTimeoutSeconds | quote }}
- name: CH_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.postgres.name }}
      key: {{ .Values.secrets.postgres.uriKey }}
- name: CH_REDIS_URL
  value: {{ .Values.config.redisUrl | quote }}
- name: CH_QDRANT_URL
  value: {{ .Values.config.qdrantUrl | quote }}
- name: CH_QDRANT_COLLECTION
  value: {{ .Values.config.rag.qdrantCollection | quote }}
- name: CH_LLM_MODEL
  value: {{ .Values.config.rag.llmModel | quote }}
- name: CH_LLM_TIMEOUT_SECONDS
  value: {{ .Values.config.rag.llmTimeoutSeconds | quote }}
- name: CH_EMBEDDING_MODEL
  value: {{ .Values.config.rag.embeddingModel | quote }}
- name: CH_EMBEDDING_DIM
  value: {{ .Values.config.rag.embeddingDim | quote }}
- name: CH_CHUNK_SIZE
  value: {{ .Values.config.rag.chunkSize | quote }}
- name: CH_CHUNK_OVERLAP
  value: {{ .Values.config.rag.chunkOverlap | quote }}
- name: CH_RETRIEVAL_TOP_K
  value: {{ .Values.config.rag.retrievalTopK | quote }}
- name: CH_RETRIEVAL_MIN_SCORE
  value: {{ .Values.config.rag.retrievalMinScore | quote }}
- name: CH_UPLOAD_MAX_MB
  value: {{ .Values.config.rag.uploadMaxMb | quote }}
- name: CH_S3_ENDPOINT
  value: {{ .Values.config.s3.endpoint | quote }}
- name: CH_S3_BUCKET
  value: {{ .Values.config.s3.bucket | quote }}
- name: CH_S3_REGION
  value: {{ .Values.config.s3.region | quote }}
- name: CH_S3_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.garage.name }}
      key: {{ .Values.secrets.garage.accessKeyIdKey }}
- name: CH_S3_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.garage.name }}
      key: {{ .Values.secrets.garage.secretAccessKeyKey }}
- name: CH_LITELLM_URL
  value: {{ .Values.config.litellmUrl | quote }}
- name: CH_LITELLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.litellm.name }}
      key: {{ .Values.secrets.litellm.key }}
{{- if .Values.langfuse.enabled }}
- name: CH_LANGFUSE_HOST
  value: {{ .Values.langfuse.host | quote }}
- name: CH_LANGFUSE_PUBLIC_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.langfuse.secretName }}
      key: {{ .Values.langfuse.publicKeyKey }}
- name: CH_LANGFUSE_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.langfuse.secretName }}
      key: {{ .Values.langfuse.secretKeyKey }}
{{- end }}
- name: CH_JWT_EXPIRES_MINUTES
  value: {{ .Values.config.jwtExpiresMinutes | quote }}
- name: CH_CORS_ORIGINS
  value: {{ .Values.config.corsOrigins | quote }}
{{- with .Values.config.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/* JWT signing key: only the API needs it (contract). */}}
{{- define "ch.jwtEnv" -}}
- name: CH_JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.app.name }}
      key: {{ .Values.secrets.app.jwtSecretKey }}
{{- end -}}

{{- define "ch.bootstrapEnv" -}}
- name: CH_BOOTSTRAP_TENANT
  value: {{ .Values.config.bootstrap.tenant | quote }}
- name: CH_BOOTSTRAP_ADMIN_EMAIL
  value: {{ .Values.config.bootstrap.adminEmail | quote }}
- name: CH_BOOTSTRAP_ADMIN_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secrets.app.name }}
      key: {{ .Values.secrets.app.bootstrapAdminPasswordKey }}
{{- end -}}
