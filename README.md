# DevGenius - AWS Solution Builder

DevGenius turns a plain-language idea into a complete, ready-to-deploy AWS
solution: an architecture diagram, a cost estimate, infrastructure as code in
**CloudFormation, CDK, and Terraform**, and full technical documentation. It is
an AI application built on **Amazon Bedrock**, grounded in current information
through the **Amazon Bedrock AgentCore** managed **Web Search** tool.

![Demo](demo/DevGenius_Demo.gif)

> **v2 rewrite.** The UI is now a professional **React + [Cloudscape](https://cloudscape.design/)**
> single-page app (replacing Streamlit), the backend is fully **serverless**, and
> the old Bedrock Knowledge Base + OpenSearch retrieval has been replaced by the
> **AgentCore Gateway web-search connector**. The only external data dependency
> is web search - everything else runs in your account.

## What you can do

- **Build a solution** conversationally. DevGenius asks a few discovery
  questions, then designs a complete solution, searching the web for the latest
  AWS services, pricing, and best practices and citing its sources.
- **Analyze an existing architecture** by uploading a diagram image (or a
  hand-drawn sketch); DevGenius explains it and helps you refine it.
- **Generate artifacts** for the finalized design:
  - Monthly **cost estimate** with current pricing
  - **Architecture diagram** (draw.io / diagrams.net), rendered in-app
  - **AWS CDK** (TypeScript), **CloudFormation** (YAML), and **Terraform** (HCL)
  - Comprehensive **technical documentation**
- **Deploy in one click**: the generated CloudFormation template opens directly
  in the CloudFormation console via a Launch Stack link.
- **Download** any artifact, or a zip bundle of everything.

## Architecture

```
                          ┌──────────────────────────────────────────┐
   Browser (SPA)          │                  AWS account              │
  React + Cloudscape      │                                           │
        │                 │   CloudFront (OAC) ── S3 (static site)    │
        │  Cognito login  │                                           │
        ├────────────────▶│   Cognito User Pool                       │
        │  access token   │                                           │
        │  POST (Bearer)  │   Lambda Function URL  ── DynamoDB (x3)    │
        └────────────────▶│      (Python, Bedrock  ── S3 (artifacts)  │
                          │       Converse loop)                      │
                          │            │ web_search tool               │
                          │            ▼                               │
                          │   AgentCore Gateway ── managed web-search  │
                          │   (MCP, AWS_IAM)        connector          │
                          │            │                               │
                          │            ▼                               │
                          │   Amazon Bedrock (Claude)                  │
                          └──────────────────────────────────────────┘
```

- **Frontend** - React + TypeScript + Vite + Cloudscape, hosted on S3 and served
  through CloudFront with Origin Access Control. Auth is handled by the Amplify
  Authenticator against Cognito.
- **Auth** - Cognito **User Pool** for sign-in. The browser sends the Cognito
  access token as a bearer credential; the Lambda validates it (via GetUser) on
  every request.
- **Backend** - a single Python **Lambda** behind a **Function URL**.
  It runs an Amazon Bedrock **Converse** loop with one tool, `web_search`. There
  is no API Gateway 30-second limit, so long generations run to completion.
- **Web search** - an **AgentCore Gateway** with the managed `web-search`
  connector target. The Lambda calls it over MCP (SigV4-signed) whenever the
  model requests a search. This fully replaces the Knowledge Base + OpenSearch.
- **State** - DynamoDB tables for conversations, sessions, and feedback; S3 for
  generated artifacts and downloadable bundles.

## Prerequisites

- An AWS account and credentials configured (`aws configure` or SSO).
- **Node.js 18+** and **Python 3.13** (for the Lambda runtime bundling).
- The AWS CDK CLI is installed automatically as a dev dependency (`npx cdk`).
- **Amazon Bedrock model access** enabled for the model you use (default
  `us.anthropic.claude-sonnet-4-6`) in the deployment Region.
- Deploy in a Region that offers the AgentCore web-search connector:
  **us-east-1**, **eu-west-1**, or **ap-northeast-1** (default: `us-east-1`).

## Deploy (one click)

```bash
./deploy.sh
```

This installs dependencies, builds the SPA, bootstraps the environment, and
deploys the stack. When it finishes, open the **AppUrl** output, sign up with an
email, confirm the code, and start building.

Options:

```bash
STACK_NAME=my-devgenius ./deploy.sh          # custom stack name
CDK_DEPLOY_REGION=eu-west-1 ./deploy.sh       # supported Region
```

Override the model:

```bash
npx cdk deploy -c stackName=dev-genius-stack -c modelId=us.anthropic.claude-sonnet-4-6
```

## Local development

The SPA reads its configuration at runtime from `/config.json`. After a deploy,
copy the stack outputs into `frontend/public/config.json`:

```bash
cp frontend/public/config.example.json frontend/public/config.json
# edit region, userPoolId, userPoolClientId, apiUrl
cd frontend && npm install && npm run dev
```

## Clean up

```bash
npx cdk destroy -c stackName=dev-genius-stack
```

This removes all resources created by the stack, including the DynamoDB tables
and S3 buckets (auto-delete is enabled). This is irreversible.

## Project structure

```txt
├── deploy.sh                 # one-click build + deploy
├── cdk.json                  # CDK entry (lib/index.ts)
├── lib/
│   ├── index.ts              # the entire serverless stack
│   └── lambda/api/           # backend Lambda (Python)
│       ├── handler.py        # Function URL router (chat/generate/session/...)
│       ├── bedrock.py        # Converse loop with the web_search tool
│       ├── websearch.py      # AgentCore Gateway MCP client (SigV4)
│       ├── prompts.py        # system + artifact prompts
│       └── storage.py        # DynamoDB + S3 helpers
└── frontend/                 # React + Cloudscape SPA
    ├── src/
    │   ├── App.tsx           # shell: auth, top nav, layout, modes
    │   ├── api.ts            # backend client (bearer access token)
    │   ├── config.ts         # runtime config loader
    │   └── components/       # chat, artifacts, diagram viewer, markdown
    └── public/config.example.json
```

## Security notes

- The backend Function URL is public (authType NONE) but the Lambda validates a
  Cognito access token on every request, so only signed-in users can use it. (This
  avoids IAM-auth Function URLs, which this account's SCP blocks for federated
  roles. For production, consider fronting it with API Gateway + a JWT authorizer
  or WAF.)
- S3 buckets block all public access; the CloudFormation Launch Stack link uses a
  short-lived presigned URL for the template.
- This is a sample. Before production use, add a WAF to CloudFront, restrict
  Bedrock IAM actions to specific model ARNs, add CloudFront/S3 access logging,
  and review Cognito password and advanced-security settings.

## License

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
