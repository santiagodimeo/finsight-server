#!/usr/bin/env bash
# Deploy finsight-server to AWS Lambda + API Gateway HTTP API.
# Prerequisites: AWS CLI configured, Docker running, jq installed.
# Usage: bash infra/deploy.sh

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REGION="${AWS_REGION:-us-east-1}"
REPO="finsight-server"
FUNCTION="finsight-api"
API_NAME="finsight-api"
ROLE_NAME="finsight-lambda-role"

# ── Load env vars from .env.local ─────────────────────────────────────────────
if [[ -f .env.local ]]; then
  set -o allexport
  source .env.local
  set +o allexport
fi

required_vars=(SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY VOYAGE_API_KEY ANTHROPIC_API_KEY)
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: $var is not set. Add it to .env.local before deploying." >&2
    exit 1
  fi
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"

echo "Account : $ACCOUNT_ID"
echo "Region  : $REGION"
echo "ECR     : $ECR_URI"
echo ""

# ── 1. IAM role ───────────────────────────────────────────────────────────────
echo "==> Ensuring IAM role '$ROLE_NAME'…"
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$TRUST" \
    --output text --query 'Role.RoleName'
  aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "    Created role. Waiting 10 s for IAM to propagate…"
  sleep 10
fi
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)

# ── 2. ECR repo ───────────────────────────────────────────────────────────────
echo "==> Ensuring ECR repo '$REPO'…"
if ! aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" &>/dev/null; then
  aws ecr create-repository --repository-name "$REPO" --region "$REGION" --output text --query 'repository.repositoryUri'
fi

# ── 3. Docker build + push ────────────────────────────────────────────────────
echo "==> Logging in to ECR…"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

echo "==> Building image (linux/amd64)…"
docker build --platform linux/amd64 --provenance=false -t "$REPO" .

echo "==> Pushing to ECR…"
docker tag "$REPO:latest" "$ECR_URI"
docker push "$ECR_URI"

# ── 4. Lambda function ────────────────────────────────────────────────────────
ENV_VARS="Variables={SUPABASE_URL=$SUPABASE_URL,SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY,VOYAGE_API_KEY=$VOYAGE_API_KEY,ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY}"

echo "==> Deploying Lambda function '$FUNCTION'…"
if aws lambda get-function --function-name "$FUNCTION" --region "$REGION" &>/dev/null; then
  aws lambda update-function-code \
    --function-name "$FUNCTION" \
    --image-uri "$ECR_URI" \
    --region "$REGION" \
    --output text --query 'FunctionName'
  aws lambda wait function-updated --function-name "$FUNCTION" --region "$REGION"
  aws lambda update-function-configuration \
    --function-name "$FUNCTION" \
    --environment "$ENV_VARS" \
    --region "$REGION" \
    --output text --query 'FunctionName'
else
  aws lambda create-function \
    --function-name "$FUNCTION" \
    --package-type Image \
    --code "ImageUri=$ECR_URI" \
    --role "$ROLE_ARN" \
    --timeout 120 \
    --memory-size 1024 \
    --environment "$ENV_VARS" \
    --region "$REGION" \
    --output text --query 'FunctionName'
  echo "    Waiting for Lambda to become active…"
  aws lambda wait function-active --function-name "$FUNCTION" --region "$REGION"
fi

LAMBDA_ARN=$(aws lambda get-function --function-name "$FUNCTION" --region "$REGION" --query 'Configuration.FunctionArn' --output text)

# ── 5. API Gateway HTTP API ───────────────────────────────────────────────────
echo "==> Checking for existing API Gateway '$API_NAME'…"
API_ID=$(aws apigatewayv2 get-apis --region "$REGION" \
  --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)

if [[ "$API_ID" == "None" || -z "$API_ID" ]]; then
  echo "==> Creating API Gateway HTTP API '$API_NAME'…"
  API_ID=$(aws apigatewayv2 create-api \
    --name "$API_NAME" \
    --protocol-type HTTP \
    --cors-configuration "AllowOrigins=*,AllowMethods=GET POST OPTIONS,AllowHeaders=content-type authorization" \
    --region "$REGION" \
    --query 'ApiId' --output text)
else
  aws apigatewayv2 update-api \
    --api-id "$API_ID" \
    --cors-configuration "AllowOrigins=*,AllowMethods=GET POST OPTIONS,AllowHeaders=content-type authorization" \
    --region "$REGION" --output text --query 'ApiId' &>/dev/null
fi
echo "    API ID: $API_ID"

# ── 6. Lambda integration ─────────────────────────────────────────────────────
echo "==> Creating Lambda integration…"
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
  --api-id "$API_ID" \
  --integration-type AWS_PROXY \
  --integration-uri "$LAMBDA_ARN" \
  --payload-format-version 2.0 \
  --region "$REGION" \
  --query 'IntegrationId' --output text)

# ── 7. Routes ─────────────────────────────────────────────────────────────────
echo "==> Creating routes…"
for ROUTE in "POST /upload" "POST /query" "GET /documents"; do
  aws apigatewayv2 create-route \
    --api-id "$API_ID" \
    --route-key "$ROUTE" \
    --target "integrations/$INTEGRATION_ID" \
    --region "$REGION" \
    --output text --query 'RouteId' &>/dev/null || true
done

# ── 8. Default stage ──────────────────────────────────────────────────────────
echo "==> Creating \$default stage…"
aws apigatewayv2 create-stage \
  --api-id "$API_ID" \
  --stage-name '$default' \
  --auto-deploy \
  --region "$REGION" \
  --output text --query 'StageName' &>/dev/null || true

# ── 9. Lambda invoke permission ───────────────────────────────────────────────
echo "==> Granting API Gateway permission to invoke Lambda…"
aws lambda add-permission \
  --function-name "$FUNCTION" \
  --statement-id "apigateway-invoke-$API_ID" \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*" \
  --region "$REGION" \
  --output text --query 'Statement' &>/dev/null || true

# ── Done ──────────────────────────────────────────────────────────────────────
API_URL="https://$API_ID.execute-api.$REGION.amazonaws.com"
echo ""
echo "✓ Deployed successfully."
echo ""
echo "  API URL: $API_URL"
echo ""
echo "  Test:"
echo "    curl \$API_URL/documents"
echo "    curl -X POST \$API_URL/upload -F 'file=@path/to/file.pdf'"
echo "    curl -X POST \$API_URL/query -H 'Content-Type: application/json' -d '{\"question\":\"What is the gross pay?\"}'"
