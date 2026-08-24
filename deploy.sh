#!/usr/bin/env bash
#
# One-click deployment for DevGenius v2.
#
# Builds the React/Cloudscape frontend, then deploys the serverless stack
# (Cognito, Lambda Function URL, DynamoDB, S3, CloudFront, and the AgentCore
# web-search Gateway) with the AWS CDK. The stack publishes the built SPA plus a
# resolved config.json to the site bucket.
#
# Usage:
#   ./deploy.sh                 # deploy to us-east-1, stack "dev-genius-stack"
#   STACK_NAME=my-stack ./deploy.sh
#   CDK_DEPLOY_REGION=eu-west-1 ./deploy.sh
#
set -euo pipefail

# The AgentCore web-search connector is only available in these Regions.
export CDK_DEPLOY_REGION="${CDK_DEPLOY_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-dev-genius-stack}"

case "$CDK_DEPLOY_REGION" in
  us-east-1|eu-west-1|ap-northeast-1) ;;
  *)
    echo "WARNING: '$CDK_DEPLOY_REGION' does not offer the AgentCore web-search"
    echo "         connector. Falling back to us-east-1."
    export CDK_DEPLOY_REGION="us-east-1"
    ;;
esac

echo "==> Region: $CDK_DEPLOY_REGION   Stack: $STACK_NAME"

echo "==> Installing CDK dependencies"
npm install

echo "==> Building frontend (React + Cloudscape)"
pushd frontend >/dev/null
npm install
npm run build
popd >/dev/null

echo "==> Bootstrapping the environment (idempotent)"
npx cdk bootstrap -c stackName="$STACK_NAME"

echo "==> Deploying"
npx cdk deploy -c stackName="$STACK_NAME" --require-approval never

echo ""
echo "==> Done. Open the 'AppUrl' output above, sign up, and start building."
echo "    Remember to enable the model in Amazon Bedrock (model access) in $CDK_DEPLOY_REGION."
