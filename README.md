# DevGenius - AWS Solution Builder

DevGenius turns a plain-language idea into a complete, ready-to-deploy AWS
solution: an architecture diagram, a cost estimate, infrastructure as code in
**CloudFormation, CDK, and Terraform**, and full technical documentation. It is
an AI application built on **Amazon Bedrock**, grounded in current information
through the **Amazon Bedrock AgentCore** managed **Web Search** tool.

> **v2 rewrite.** The UI is a professional **React + [Cloudscape](https://cloudscape.design/)**
> single-page app (replacing the original Streamlit app), the backend is fully
> **serverless**, and the old Bedrock Knowledge Base + OpenSearch retrieval has
> been replaced by the **AgentCore Gateway web-search connector**. The only
> external data dependency is web search - everything else runs in your account.

## What you can do

- **Build a solution** conversationally. DevGenius asks a few discovery
  questions, then designs a complete solution, searching the web for the latest
  AWS services, pricing, and best practices and citing its sources.
- **Analyze an existing architecture** by attaching a diagram image (or a
  hand-drawn sketch) in the chat; DevGenius explains it and helps you refine it.
- **Generate artifacts** for the finalized design, streamed live as they're written:
  - Monthly **cost estimate** with current pricing
  - **Architecture diagram** (draw.io / diagrams.net) rendered in-app, with an
    "Edit in draw.io" link to tweak it
  - **AWS CDK** (TypeScript), **CloudFormation** (YAML), and **Terraform** (HCL)
  - Comprehensive **technical documentation** (rendered as formatted HTML)
- **Keep your history.** Past conversations live in the left sidebar; open one to
  restore its full transcript and every generated artifact, or delete it (and all
  its artifacts) with one click.
- **Download** any artifact, or a zip bundle of everything.

## Architecture

```
                          ┌───────────────────────────────────────────────┐
   Browser (SPA)          │                    AWS account                 │
  React + Cloudscape      │                                                │
        │                 │   CloudFront (OAC) ─── S3 (static site)         │
        │  Cognito login  │                                                │
        ├────────────────▶│   Cognito User Pool                            │
        │  ID token        │                                               │
        │  (Bearer JWT)   │   API Gateway (HTTP API, JWT authorizer)        │
        └────────────────▶│         │                                      │
                          │         ▼                                      │
                          │   Lambda (Python)  ─── DynamoDB (conversations, │
                          │    async job worker      sessions, feedback,    │
                          │    Bedrock Converse       jobs)                 │
                          │    + streaming        ─── S3 (artifacts)        │
                          │         │ web_search tool                       │
                          │         ▼                                       │
                          │   AgentCore Gateway ─── managed web-search      │
                          │   (MCP, AWS_IAM)          connector             │
                          │         │                                       │
                          │         ▼                                       │
                          │   Amazon Bedrock (Claude)                       │
                          └───────────────────────────────────────────────┘
```

- **Frontend** - React + TypeScript + Vite + Cloudscape, hosted on S3 and served
  through CloudFront with Origin Access Control. A conversation-history sidebar,
  a bottom-pinned chat input with image attach/preview, live streaming output,
  and a side panel for the generated artifacts.
- **Auth** - Cognito **User Pool** for sign-in (via the Amplify Authenticator).
  The browser sends the Cognito **ID token** as a bearer credential.
- **API** - an **API Gateway HTTP API** with a **Cognito JWT authorizer**. Long
  generations (diagrams, docs, IaC with live web search) exceed API Gateway's
  ~30s limit, so `chat` and `generate` run as **async jobs**: the request returns
  a `jobId` immediately, a background Lambda does the work and streams partial
  output, and the client polls for the result.
- **Backend** - a Python **Lambda** running an Amazon Bedrock **Converse** loop
  with one tool, `web_search`. It continues past token limits so long artifacts
  finish completely.
- **Web search** - an **AgentCore Gateway** with the managed `web-search`
  connector target. The Lambda calls it over MCP (SigV4-signed) whenever the
  model requests a search. This fully replaces the Knowledge Base + OpenSearch.
- **State** - DynamoDB tables for conversations, sessions, feedback, and async
  jobs; S3 for generated artifacts and downloadable bundles. All timestamps are
  recorded in US Eastern Time.

## Prerequisites

- An AWS account and credentials configured (`aws configure` or SSO).
- **Node.js 18+** and **Python 3.13** (for the Lambda runtime).
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
│       ├── handler.py        # API router + async job worker
│       ├── bedrock.py        # streaming Converse loop with the web_search tool
│       ├── websearch.py      # AgentCore Gateway MCP client (SigV4)
│       ├── prompts.py        # system + artifact prompts
│       └── storage.py        # DynamoDB + S3 helpers (ET timestamps)
└── frontend/                 # React + Cloudscape SPA
    ├── src/
    │   ├── App.tsx           # auth shell + top navigation
    │   ├── Console.tsx       # layout: history sidebar, chat, artifacts panel
    │   ├── api.ts            # backend client (bearer ID token, job polling)
    │   ├── config.ts         # runtime config loader
    │   └── components/       # ChatArea, ConversationList, ArtifactsPanel,
    │                         #   DiagramViewer, Markdown
    └── public/config.example.json
```

## Security notes

This is a sample. Before production use:

- The API Gateway HTTP API is protected by a **Cognito JWT authorizer**; only
  signed-in users can call it. Consider adding **AWS WAF** to CloudFront and the
  API, and enabling CloudFront/S3 access logging.
- S3 buckets block all public access; the SPA is served only through CloudFront
  (Origin Access Control).
- Restrict the Lambda's Bedrock IAM actions to specific model ARNs, and review
  the Cognito password policy and advanced-security settings.

## License

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
