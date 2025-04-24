# DevGenius - AWS Solution Generator

DevGenius is an AI-powered application that transforms project ideas into complete, ready-to-deploy AWS solutions. It leverages Amazon Bedrock and Claude AI models to provide architecture diagrams, cost estimates, infrastructure as code, and comprehensive technical documentation.

**Conversational Solution Architecture Building:** DevGenius enables customers to design solution architectures in a conversational manner. Users can create architecture diagrams (in draw.io format) and refine them interactively. Once the design is finalized, they can generate end-to-end code automation using CDK or CloudFormation templates, and deploy it in their AWS account with a single click. Additionally, customers can receive cost estimates for running the architecture in production, along with detailed documentation for the solution.

**Build Solution Architecture from Whiteboard Drawings:** For customers who already have their architecture in image form (e.g., whiteboard drawings), DevGenius allows them to upload the image. Once uploaded, DevGenius analyzes the architecture and provides a detailed explanation. Customer can then refine the design conversationally and, once finalized, generate end-to-end code automation using CDK or CloudFormation. Cost estimates and comprehensive documentation are also available.

## Features

- **Solution Architecture Generation**: Create AWS architectures based on your project requirements
- **Architecture Diagram Creation**: Generate visual representations of your AWS solutions
- **Infrastructure as Code**: Generate both AWS CDK and CloudFormation templates
- **Cost Estimation**: Get detailed cost breakdowns for all proposed AWS services
- **Technical Documentation**: Generate comprehensive documentation for your solutions
- **Existing Architecture Analysis**: Upload and analyze existing architecture diagrams

## Architecture Overview

DevGenius is built using a modern cloud-native architecture:

- **Frontend**: Streamlit-based UI for intuitive interaction
- **AI Engine**: Amazon Bedrock with Claude AI models for solution generation
- **Knowledge Base**: Amazon Bedrock Knowledge Base with AWS documentation sources
- **Vector Storage**: Amazon OpenSearch Serverless for vector embeddings
- **Data Storage**: 
  - Amazon S3 for storing generated assets
  - DynamoDB for conversation and session tracking
- **Deployment**: 
  - AWS ECS Fargate for containerized application hosting
  - CloudFront for content distribution
  - Application Load Balancer for traffic management
- **Authentication**: Amazon Cognito for user authentication

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI configured with credentials
- Python 3.12 or later
- Docker (for container builds and local development)
- Access to Amazon Bedrock models (Claude-3-Sonnet/Claude-3-5-Sonnet)

## Installation and Setup

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/ devgenius
   cd devgenius
   ```

2. Install the required dependencies:
   ```bash
   npm install
   ```

3. Set up the required environment variables. Replace all the values that follow the pattern <REPLACE_ME_XXX>:
   ```bash
   export AWS_REGION="us-west-2"
   export BEDROCK_AGENT_ID="<REPLACE_ME_BEDROCK_AGENT_ID>"
   export BEDROCK_AGENT_ALIAS_ID="<REPLACE_ME_BEDROCK_AGENT_ALIAS_ID>"
   export S3_BUCKET_NAME="<REPLACE_ME_S3_BUCKET_NAME>"
   export CONVERSATION_TABLE_NAME="<REPLACE_ME_CONVERSATION_TABLE_NAME>"
   export FEEDBACK_TABLE_NAME="<REPLACE_ME_FEEDBACK_TABLE_NAME>"
   export SESSION_TABLE_NAME="<REPLACE_ME_SESSION_TABLE_NAME>"
   ```

4. Run the application:
   ```bash
   streamlit run chatbot/agent.py
   ```

### Docker Deployment

Build and run using Docker after replacing all the values that follow the pattern <REPLACE_ME_XXX>:

```bash
cd chatbot
docker build -t devgenius .
docker run -p 8501:8501 \
  -e AWS_REGION="us-west-2" \
  -e BEDROCK_AGENT_ID="<REPLACE_ME_BEDROCK_AGENT_ID>" \
  -e BEDROCK_AGENT_ALIAS_ID="<REPLACE_ME_BEDROCK_AGENT_ALIAS_ID>" \
  -e S3_BUCKET_NAME="<REPLACE_ME_S3_BUCKET_NAME>" \
  -e CONVERSATION_TABLE_NAME="<REPLACE_ME_CONVERSATION_TABLE_NAME>" \
  -e FEEDBACK_TABLE_NAME="<REPLACE_ME_FEEDBACK_TABLE_NAME>" \
  -e SESSION_TABLE_NAME="<REPLACE_ME_SESSION_TABLE_NAME>" \
  devgenius
```

## AWS Infrastructure Deployment

DevGenius includes a CDK stack that deploys all required infrastructure:

1. Install the CDK toolkit:
   ```bash
   npm install -g aws-cdk
   ```

2. From the root of the repository, install dependencies:
   ```bash
   npm install
   ```

3. Deploy the stack:
   ```bash
   cdk deploy --all --context stackName=devgenius
   ```

4. To destroy the infrastructure when no longer needed:
   ```bash
   cdk destroy --all --context stackName=devgenius
   ```
   This command will remove all AWS resources created by the stack. You'll be prompted to confirm before the deletion proceeds. Note that this action is irreversible and will delete all application data stored in the deployed resources.

The CDK stack deploys:
- VPC with public/private subnets
- ECS Fargate service with Streamlit container
- Application Load Balancer
- CloudFront distribution with Lambda@Edge for authentication
- Cognito user pool and identity pool
- DynamoDB tables for conversation tracking
- S3 bucket for storing generated assets
- Bedrock Agent with Knowledge Base
- OpenSearch Serverless collection for vector embeddings

## Usage Guide

### Authentication

1. Access the application URL provided in the CDK output (named StreamlitUrl)
2. Create (Sign up) for a new user account in Cognito in the landing page or sign in with existing credentials
3. Accept the terms and conditions

### Building a New Solution

1. Navigate to the "Build a solution" tab
2. Select a topic (Data Lake, Log Analytics)
3. Answer the discovery questions about your requirements
4. Review the generated solution
5. Use the option tabs to generate additional assets:
   - Cost Estimates: Get detailed pricing breakdown
   - Architecture Diagram: Visual representation of the solution
   - CDK Code: infrastructure as code
   - CloudFormation Code: YAML templates
   - Technical Documentation: Comprehensive solution documentation

### Analyzing Existing Architecture

1. Navigate to the "Modify your existing architecture" tab
2. Upload an architecture diagram image (PNG/JPG format)
3. The application will analyze the diagram and provide insights
4. Use the option tabs to generate modifications and improvements

## Key Components

### Bedrock Agent and Knowledge Base

DevGenius uses Amazon Bedrock Agents with a custom Knowledge Base containing AWS documentation, whitepapers, and blogs. The agent is configured with specialized prompts to generate AWS solutions following best practices.

Knowledge base sources include:
- AWS Well-Architected Analytics Lens
- AWS Whitepapers on data streaming and analytics architectures
- AWS documentation on data lakes
- AWS architecture blog posts
- AWS service announcements

### Vector Search with OpenSearch Serverless

Architecture information is stored as vector embeddings in Amazon OpenSearch Serverless, enabling semantic search and retrieval of relevant architectural patterns.

### Infrastructure as Code Generation

The application can generate both AWS CDK (TypeScript) and CloudFormation (YAML) templates for deploying the proposed solutions.

## Project Structure

```
├── chatbot/                      # Code for chatbot
   ├── agent.py                   # Main application entry point
   ├── cost_estimate_widget.py    # Cost estimation functionality
   ├── generate_arch_widget.py    # Architecture diagram generation
   ├── generate_cdk_widget.py     # CDK code generation
   ├── generate_cfn_widget.py     # CloudFormation template generation
   ├── generate_doc_widget.py     # Documentation generation
   ├── layout.py                  # UI layout components
   ├── styles.py                  # UI styling
   ├── utils.py                   # Utility functions
   ├── Dockerfile                 # Container definition
   ├── requirements.txt           # Python dependencies
├── lib/                          # CDK stack definition
   ├── layer/                     # Lambda layer containing dependencies
   ├── lambda/                    # Lambda function code
   └── edge-lambda/               # CloudFront Lambda@Edge function
```

## Security

DevGenius includes several security features:

- Cognito authentication for user management
- CloudFront with Lambda@Edge for request validation
- IAM roles with least privilege permissions
- VPC with security groups for network isolation
- S3 bucket with encryption for asset storage
- DynamoDB tables with encryption for data storage

## License

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.