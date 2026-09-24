#!/usr/bin/env bash
# Despliegue en Azure: Container Registry + PostgreSQL + Container Apps + API Management.
# Requisitos: Azure CLI (`az login` hecho) y ejecutar desde la raíz del repositorio.
# COSTOS: PostgreSQL Flexible (B1ms) y API Management (Consumption) generan cargos pequeños.
# Al terminar la demo borra todo con:  az group delete -n "$RG" --yes
set -euo pipefail

# ---------- Variables (cámbialas) ----------
RG="rg-ai-integration-hub"
LOCATION="eastus"
SUFFIX="$RANDOM"                      # nombres únicos a nivel global
ACR="acrhub${SUFFIX}"
PG="pg-hub-${SUFFIX}"
PG_USER="hubadmin"
PG_PASS="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 20)Aa1"
ENV_NAME="cae-hub"
APP="ai-integration-hub"
APIM="apim-hub-${SUFFIX}"
API_KEY="$(openssl rand -hex 24)"
WC_SECRET="$(openssl rand -hex 24)"
AI_PROVIDER="${AI_PROVIDER:-mock}"
AI_API_KEY="${AI_API_KEY:-}"

echo "==> 1. Grupo de recursos"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> 2. Azure Container Registry + build de la imagen en la nube (no necesitas Docker local)"
az acr create -n "$ACR" -g "$RG" --sku Basic --admin-enabled true -o none
az acr build -r "$ACR" -t "$APP:v1" .

echo "==> 3. Base de datos PostgreSQL administrada"
az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOCATION" \
  --admin-user "$PG_USER" --admin-password "$PG_PASS" \
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 \
  --public-access 0.0.0.0 -o none          # 0.0.0.0 = permite solo servicios de Azure
az postgres flexible-server db create -g "$RG" -s "$PG" -d hub -o none
DATABASE_URL="postgresql+psycopg://${PG_USER}:${PG_PASS}@${PG}.postgres.database.azure.com:5432/hub?sslmode=require"

echo "==> 4. Azure Container Apps (la API, con HTTPS y escalado automático)"
az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" -o none
ACR_PASS="$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)"
az containerapp create -n "$APP" -g "$RG" --environment "$ENV_NAME" \
  --image "${ACR}.azurecr.io/${APP}:v1" \
  --registry-server "${ACR}.azurecr.io" --registry-username "$ACR" --registry-password "$ACR_PASS" \
  --target-port 8000 --ingress external --min-replicas 1 --max-replicas 3 \
  --secrets "db-url=${DATABASE_URL}" "api-key=${API_KEY}" "wc-secret=${WC_SECRET}" "ai-key=${AI_API_KEY:-none}" \
  --env-vars ENVIRONMENT=azure "DATABASE_URL=secretref:db-url" "API_KEY=secretref:api-key" \
             "WOOCOMMERCE_WEBHOOK_SECRET=secretref:wc-secret" "AI_PROVIDER=${AI_PROVIDER}" "AI_API_KEY=secretref:ai-key" \
  -o none
FQDN="$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "    API desplegada en: https://${FQDN}/docs"

echo "==> 5. Azure API Management (puerta de entrada: suscripciones, límites de uso, analítica)"
az apim create -n "$APIM" -g "$RG" -l "$LOCATION" --sku-name Consumption \
  --publisher-email "you@example.com" --publisher-name "AI Integration Hub" -o none
az apim api import -g "$RG" --service-name "$APIM" --api-id hub --path hub \
  --specification-format OpenApi --specification-url "https://${FQDN}/openapi.json" \
  --service-url "https://${FQDN}" -o none

cat <<EOF

Listo.
  API directa:         https://${FQDN}/docs
  API vía APIM:        https://${APIM}.azure-api.net/hub
  API_KEY (guárdala):  ${API_KEY}
  Secreto WooCommerce: ${WC_SECRET}
  Webhook para WooCommerce: https://${FQDN}/webhooks/woocommerce
EOF
