# Secrets do ambiente mvp

Este diretório guarda **somente** `SealedSecret`s, cifrados com a chave do controller
Sealed Secrets do cluster mvp. O Argo CD aplica tudo que estiver aqui (`*.yaml`) pela
Application `clear-helper-secrets` (sync-wave 1, antes da camada de dados).

Nunca faça commit de `Secret` em claro. Gere cada arquivo assim (exemplo):

```bash
kubectl create secret generic clear-helper-app -n clear-helper \
  --from-file=jwt-secret=./jwt-secret.txt \
  --from-file=bootstrap-admin-password=./admin-password.txt \
  --dry-run=client -o yaml \
| kubeseal --controller-namespace kube-system --controller-name sealed-secrets-controller \
    --format yaml > infra/secrets/mvp/clear-helper-app.sealed.yaml
```

Secrets esperados (nomes e chaves): veja `infra/README.md`, seção "Secrets".
