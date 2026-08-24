/**
 * DevGenius v2 - fully serverless CDK stack.
 *
 * Frontend : React + Cloudscape SPA on S3 + CloudFront (OAC).
 * Auth     : Cognito User Pool (login) + Identity Pool (SigV4 credentials).
 * Backend  : Python Lambda behind a Function URL (IAM auth), Bedrock Converse
 *            with a web_search tool.
 * Search   : Amazon Bedrock AgentCore Gateway with the managed web-search
 *            connector (replaces the old Knowledge Base + OpenSearch).
 * State    : DynamoDB (conversations/sessions/feedback) + S3 (artifacts).
 */
import * as path from "path"
import * as cdk from "aws-cdk-lib"
import { Construct } from "constructs"
import * as iam from "aws-cdk-lib/aws-iam"
import * as s3 from "aws-cdk-lib/aws-s3"
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment"
import * as lambda from "aws-cdk-lib/aws-lambda"
import * as logs from "aws-cdk-lib/aws-logs"
import * as dynamodb from "aws-cdk-lib/aws-dynamodb"
import * as cognito from "aws-cdk-lib/aws-cognito"
import * as cloudfront from "aws-cdk-lib/aws-cloudfront"
import * as origins from "aws-cdk-lib/aws-cloudfront-origins"
import * as apigw from "aws-cdk-lib/aws-apigatewayv2"
import { HttpLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations"
import { HttpJwtAuthorizer } from "aws-cdk-lib/aws-apigatewayv2-authorizers"

// The AgentCore web-search connector is only available in these Regions today.
const WEB_SEARCH_REGIONS = ["us-east-1", "eu-west-1", "ap-northeast-1"]

class DevGeniusStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props: cdk.StackProps) {
        super(scope, id, props)

        const stackName = cdk.Stack.of(this).stackName
        const region = cdk.Stack.of(this).region
        const account = cdk.Stack.of(this).account

        // Default model can be overridden with `-c modelId=...`.
        const modelId =
            this.node.tryGetContext("modelId") || "us.anthropic.claude-sonnet-4-6"

        // ----------------------------------------------------------------- //
        // Data stores
        // ----------------------------------------------------------------- //
        const conversationTable = new dynamodb.TableV2(this, "ConversationTable", {
            tableName: `${stackName}-conversation-table`,
            partitionKey: { name: "conversation_id", type: dynamodb.AttributeType.STRING },
            sortKey: { name: "uuid", type: dynamodb.AttributeType.STRING },
            billing: dynamodb.Billing.onDemand(),
            encryption: dynamodb.TableEncryptionV2.dynamoOwnedKey(),
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        const feedbackTable = new dynamodb.TableV2(this, "FeedbackTable", {
            tableName: `${stackName}-feedback-table`,
            partitionKey: { name: "conversation_id", type: dynamodb.AttributeType.STRING },
            sortKey: { name: "uuid", type: dynamodb.AttributeType.STRING },
            billing: dynamodb.Billing.onDemand(),
            encryption: dynamodb.TableEncryptionV2.dynamoOwnedKey(),
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        const sessionTable = new dynamodb.TableV2(this, "SessionTable", {
            tableName: `${stackName}-session-table`,
            partitionKey: { name: "conversation_id", type: dynamodb.AttributeType.STRING },
            // Lists a user's conversations for the sidebar, newest first.
            globalSecondaryIndexes: [
                {
                    indexName: "by-user",
                    partitionKey: { name: "user_email", type: dynamodb.AttributeType.STRING },
                    sortKey: { name: "updated", type: dynamodb.AttributeType.STRING },
                },
            ],
            billing: dynamodb.Billing.onDemand(),
            encryption: dynamodb.TableEncryptionV2.dynamoOwnedKey(),
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        // Tracks async chat/generate jobs (the client polls these). TTL cleans up.
        const jobsTable = new dynamodb.TableV2(this, "JobsTable", {
            tableName: `${stackName}-jobs-table`,
            partitionKey: { name: "job_id", type: dynamodb.AttributeType.STRING },
            timeToLiveAttribute: "ttl",
            billing: dynamodb.Billing.onDemand(),
            encryption: dynamodb.TableEncryptionV2.dynamoOwnedKey(),
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        // Bucket for generated artifacts (diagrams, IaC, docs, zip bundles).
        const artifactsBucket = new s3.Bucket(this, "ArtifactsBucket", {
            bucketName: `${stackName}-artifacts-${account}-${region}`,
            encryption: s3.BucketEncryption.S3_MANAGED,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            enforceSSL: true,
            autoDeleteObjects: true,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        // ----------------------------------------------------------------- //
        // AgentCore Gateway with the managed web-search connector
        // ----------------------------------------------------------------- //
        const gatewayServiceRole = new iam.Role(this, "GatewayServiceRole", {
            roleName: `${stackName}-${region}-gateway-role`,
            description: "Role assumed by the AgentCore Gateway to call web-search",
            assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com", {
                conditions: {
                    StringEquals: { "aws:SourceAccount": account },
                    ArnLike: {
                        "aws:SourceArn": `arn:aws:bedrock-agentcore:${region}:${account}:gateway/*`,
                    },
                },
            }),
        })
        gatewayServiceRole.addToPolicy(
            new iam.PolicyStatement({
                sid: "InvokeGateway",
                actions: ["bedrock-agentcore:InvokeGateway"],
                resources: [`arn:aws:bedrock-agentcore:${region}:${account}:gateway/*`],
            })
        )
        gatewayServiceRole.addToPolicy(
            new iam.PolicyStatement({
                sid: "InvokeWebSearch",
                actions: ["bedrock-agentcore:InvokeWebSearch"],
                resources: [`arn:aws:bedrock-agentcore:${region}:aws:tool/web-search.v1`],
            })
        )

        const gateway = new cdk.CfnResource(this, "WebSearchGateway", {
            type: "AWS::BedrockAgentCore::Gateway",
            properties: {
                Name: `${stackName}-websearch`.replace(/[^a-zA-Z0-9_-]/g, "-"),
                Description: "DevGenius managed web-search gateway",
                ProtocolType: "MCP",
                AuthorizerType: "AWS_IAM",
                RoleArn: gatewayServiceRole.roleArn,
            },
        })
        const gatewayUrl = gateway.getAtt("GatewayUrl").toString()

        const webSearchTarget = new cdk.CfnResource(this, "WebSearchTarget", {
            type: "AWS::BedrockAgentCore::GatewayTarget",
            properties: {
                GatewayIdentifier: gateway.getAtt("GatewayIdentifier").toString(),
                Name: "websearch",
                Description: "Built-in web-search connector",
                CredentialProviderConfigurations: [
                    { CredentialProviderType: "GATEWAY_IAM_ROLE" },
                ],
                TargetConfiguration: {
                    Mcp: {
                        Connector: {
                            Source: { ConnectorId: "web-search" },
                            Configurations: [{ Name: "WebSearch", ParameterValues: {} }],
                        },
                    },
                },
            },
        })
        webSearchTarget.addDependency(gateway)

        // ----------------------------------------------------------------- //
        // Backend Lambda (Function URL, IAM auth)
        // ----------------------------------------------------------------- //
        const apiFn = new lambda.Function(this, "ApiFunction", {
            functionName: `${stackName}-api`,
            runtime: lambda.Runtime.PYTHON_3_13,
            handler: "handler.handler",
            code: lambda.Code.fromAsset(path.join(__dirname, "lambda/api")),
            timeout: cdk.Duration.minutes(15),
            memorySize: 1024,
            description: "DevGenius API: Bedrock Converse + AgentCore web search",
            environment: {
                CONVERSATION_TABLE_NAME: conversationTable.tableName,
                SESSION_TABLE_NAME: sessionTable.tableName,
                FEEDBACK_TABLE_NAME: feedbackTable.tableName,
                JOBS_TABLE_NAME: jobsTable.tableName,
                ARTIFACTS_BUCKET_NAME: artifactsBucket.bucketName,
                GATEWAY_URL: gatewayUrl,
                BEDROCK_MODEL_ID: modelId,
            },
            logGroup: new logs.LogGroup(this, "ApiFunctionLogs", {
                logGroupName: `/aws/lambda/${stackName}-api`,
                retention: logs.RetentionDays.TWO_WEEKS,
                removalPolicy: cdk.RemovalPolicy.DESTROY,
            }),
        })

        conversationTable.grantReadWriteData(apiFn)
        sessionTable.grantReadWriteData(apiFn)
        feedbackTable.grantReadWriteData(apiFn)
        jobsTable.grantReadWriteData(apiFn)
        artifactsBucket.grantReadWrite(apiFn)
        // The function re-invokes itself (event mode) to run long jobs. Use a
        // constructed ARN (the function name is deterministic) instead of
        // grantInvoke, which would create a circular dependency.
        apiFn.addToRolePolicy(
            new iam.PolicyStatement({
                sid: "SelfInvoke",
                actions: ["lambda:InvokeFunction"],
                resources: [`arn:aws:lambda:${region}:${account}:function:${stackName}-api`],
            })
        )

        apiFn.addToRolePolicy(
            new iam.PolicyStatement({
                sid: "Bedrock",
                actions: [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                ],
                resources: ["*"],
            })
        )
        apiFn.addToRolePolicy(
            new iam.PolicyStatement({
                sid: "InvokeGateway",
                actions: ["bedrock-agentcore:InvokeGateway"],
                resources: [`arn:aws:bedrock-agentcore:${region}:${account}:gateway/*`],
            })
        )

        // ----------------------------------------------------------------- //
        // Cognito User Pool (login). The browser sends the ID token, which the
        // API Gateway JWT authorizer validates.
        // ----------------------------------------------------------------- //
        const userPool = new cognito.UserPool(this, "UserPool", {
            userPoolName: `${stackName}-users`,
            selfSignUpEnabled: true,
            autoVerify: { email: true },
            signInAliases: { email: true },
            standardAttributes: { email: { required: true, mutable: true } },
            passwordPolicy: {
                minLength: 8,
                requireLowercase: true,
                requireUppercase: true,
                requireDigits: true,
                requireSymbols: true,
            },
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        const userPoolClient = userPool.addClient("UserPoolClient", {
            generateSecret: false,
            authFlows: { userSrp: true, userPassword: true },
        })

        // ----------------------------------------------------------------- //
        // API Gateway HTTP API with a Cognito JWT authorizer. A Lambda Function
        // URL cannot be used here - an Organizations control blocks Function URL
        // invocation in this account.
        // ----------------------------------------------------------------- //
        const httpApi = new apigw.HttpApi(this, "HttpApi", {
            apiName: `${stackName}-api`,
            corsPreflight: {
                allowOrigins: ["*"],
                allowMethods: [apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.OPTIONS],
                allowHeaders: ["content-type", "authorization"],
                maxAge: cdk.Duration.hours(1),
            },
        })
        const authorizer = new HttpJwtAuthorizer(
            "JwtAuthorizer",
            `https://cognito-idp.${region}.amazonaws.com/${userPool.userPoolId}`,
            { jwtAudience: [userPoolClient.userPoolClientId] }
        )
        const integration = new HttpLambdaIntegration("ApiIntegration", apiFn)
        httpApi.addRoutes({
            path: "/invoke",
            methods: [apigw.HttpMethod.POST],
            integration,
            authorizer,
        })
        httpApi.addRoutes({
            path: "/job/{jobId}",
            methods: [apigw.HttpMethod.GET],
            integration,
            authorizer,
        })
        const apiUrl = httpApi.apiEndpoint

        // ----------------------------------------------------------------- //
        // Frontend hosting: S3 + CloudFront (OAC)
        // ----------------------------------------------------------------- //
        const siteBucket = new s3.Bucket(this, "SiteBucket", {
            bucketName: `${stackName}-site-${account}-${region}`,
            encryption: s3.BucketEncryption.S3_MANAGED,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            enforceSSL: true,
            autoDeleteObjects: true,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        })

        const distribution = new cloudfront.Distribution(this, "Distribution", {
            comment: `${stackName} DevGenius SPA`,
            defaultRootObject: "index.html",
            defaultBehavior: {
                origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
                viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
                allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
            },
            errorResponses: [
                { httpStatus: 403, responseHttpStatus: 200, responsePagePath: "/index.html" },
                { httpStatus: 404, responseHttpStatus: 200, responsePagePath: "/index.html" },
            ],
            minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
        })

        // Runtime configuration the SPA fetches at startup (/config.json).
        const runtimeConfig = {
            region,
            userPoolId: userPool.userPoolId,
            userPoolClientId: userPoolClient.userPoolClientId,
            apiUrl: apiUrl,
        }

        // Deploy the built SPA (frontend/dist) plus the resolved config.json.
        // `frontend/dist` must exist at synth time - run the frontend build first
        // (deploy.sh does this for you).
        new s3deploy.BucketDeployment(this, "DeploySite", {
            destinationBucket: siteBucket,
            distribution,
            distributionPaths: ["/*"],
            sources: [
                s3deploy.Source.asset(path.join(__dirname, "../frontend/dist")),
                s3deploy.Source.jsonData("config.json", runtimeConfig),
            ],
        })

        // ----------------------------------------------------------------- //
        // Outputs
        // ----------------------------------------------------------------- //
        this.addTags()
        new cdk.CfnOutput(this, "AppUrl", { value: `https://${distribution.distributionDomainName}` })
        new cdk.CfnOutput(this, "ApiUrl", { value: apiUrl })
        new cdk.CfnOutput(this, "GatewayUrl", { value: gatewayUrl })
        new cdk.CfnOutput(this, "UserPoolId", { value: userPool.userPoolId })
        new cdk.CfnOutput(this, "UserPoolClientId", { value: userPoolClient.userPoolClientId })
        new cdk.CfnOutput(this, "ArtifactsBucketName", { value: artifactsBucket.bucketName })
    }

    private addTags() {
        cdk.Tags.of(this).add("project", "DevGenius")
        cdk.Tags.of(this).add("repo", "https://github.com/aws-samples/sample-devgenius-aws-solution-builder")
    }
}

const app = new cdk.App()
const stackName = app.node.tryGetContext("stackName") || "dev-genius-stack"
// Region: honour CDK_DEPLOY_REGION / default, but the web-search connector only
// exists in a few Regions - fall back to us-east-1 and warn otherwise.
let region = process.env.CDK_DEPLOY_REGION || process.env.CDK_DEFAULT_REGION || "us-east-1"
if (!WEB_SEARCH_REGIONS.includes(region)) {
    console.warn(
        `[DevGenius] Region '${region}' does not offer the AgentCore web-search ` +
            `connector. Falling back to us-east-1. Supported: ${WEB_SEARCH_REGIONS.join(", ")}.`
    )
    region = "us-east-1"
}
new DevGeniusStack(app, stackName, { env: { region } })
