from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import RequestError, ConnectionError, AuthorizationException
from requests_aws4auth import AWS4Auth
import time
import json
import os
from crhelper import CfnResource
from boto3.session import Session

REGION = os.getenv("AWS_REGION")
COLLECTION_ENDPOINT = os.getenv("COLLECTION_ENDPOINT").replace("https://", "")
service = "aoss"

helper = CfnResource(json_logging=False, log_level="DEBUG", boto_level="CRITICAL")
credentials = Session().get_credentials()


def create_aws_auth(credentials, region: str, service: str) -> AWS4Auth:
    """
    Creates an AWS4Auth instance for authenticating requests to AWS services.

    This function generates authentication credentials required for AWS Signature Version 4
    signing process. It's commonly used for services like OpenSearch that require
    AWS authentication.

    Args:
        credentials: AWS credentials object containing access key, secret key, and session token
        region (str): AWS region where the service is located (e.g., 'us-east-1')
        service (str): AWS service identifier (e.g., 'aoss' for OpenSearch Serverless)

    Returns:
        AWS4Auth: Authentication object used for signing AWS requests

    Example:
        >>> session = Session()
        >>> credentials = session.get_credentials()
        >>> auth = create_aws_auth(credentials, 'us-east-1', 'aoss')
    """
    return AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        service,
        session_token=credentials.token
    )


awsauth = create_aws_auth(credentials, REGION, service)


def create_opensearch_client(endpoint: str, auth: AWS4Auth, timeout: int = 300) -> OpenSearch:
    """
    Creates an OpenSearch client for AWS OpenSearch Service/Serverless.

    Establishes a secure connection to an OpenSearch endpoint using AWS authentication
    and HTTPS. This client can be used to perform operations like creating indices,
    searching, and managing documents.

    Args:
        endpoint (str): OpenSearch endpoint without 'https://' prefix
        auth (AWS4Auth): AWS authentication object for request signing
        timeout (int, optional): Connection timeout in seconds. Defaults to 300.

    Returns:
        OpenSearch: Configured OpenSearch client instance

    Raises:
        ConnectionError: If unable to establish connection to OpenSearch
        AuthorizationException: If AWS credentials are invalid
        ValueError: If endpoint is malformed

    Example:
        >>> auth = create_aws_auth(credentials, REGION, 'aoss')
        >>> client = create_opensearch_client('my-domain.us-east-1.aoss.amazonaws.com', auth)

    Notes:
        - Always uses HTTPS (port 443) for secure communication
        - Verifies SSL certificates for enhanced security
        - Uses RequestsHttpConnection for AWS IAM authentication support
        - Implements AWS best practices for OpenSearch connection
    """
    try:
        return OpenSearch(
            hosts=[{'host': endpoint, 'port': 443}],
            http_auth=auth,
            use_ssl=True,  # Enforce HTTPS for security
            verify_certs=True,  # Verify SSL certificates
            connection_class=RequestsHttpConnection,  # Required for AWS auth
            timeout=timeout
        )
    except Exception as e:
        raise ConnectionError(f"Failed to create OpenSearch client: {str(e)}")


# Create OpenSearch client instance
oss_client = create_opensearch_client(
    endpoint=COLLECTION_ENDPOINT,
    auth=awsauth
)

# OpenSearch Index Configuration
body_json = {
    "settings": {
        "index.knn": "true",
        "number_of_shards": 1,
        "knn.algo_param.ef_search": 512,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "vector": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "engine": "faiss",
                    "space_type": "l2",
                    "parameters": {
                        "ef_construction": 512,
                        "m": 16
                    },
                },
            },
            "text": {
                "type": "text"
            },
            "text-metadata": {
                "type": "text"
            }
        }
    }
}


@helper.create
def create(event, context):
    """
    CloudFormation custom resource handler to create an OpenSearch index.

    Creates a new OpenSearch index with vector search capabilities for use with Amazon Bedrock
    Knowledge Base. Implements retry logic with exponential backoff to handle eventual 
    consistency of IAM permissions and transient failures.

    Args:
        event (dict): CloudFormation custom resource event containing:
            - RequestType: 'Create'
            - ResourceProperties: Custom properties passed from CloudFormation
            - StackId: ID of the CloudFormation stack
            - RequestId: Unique request identifier
            - LogicalResourceId: Logical ID of the custom resource
        context (Any): Lambda context object containing runtime information

    Returns:
        Optional[dict]: OpenSearch create index response if successful, None if index already exists

    Raises:
        RequestError: If index creation fails due to invalid configuration
        ConnectionError: If unable to connect to OpenSearch endpoint
        AuthorizationException: If permissions are insufficient
        Exception: If index creation fails after maximum retries

    Environment Variables Required:
        BEDROCK_KB_INDEX_NAME (str): Name of the OpenSearch index to create

    Example CloudFormation Resource:
        MySearchIndex:
          Type: Custom::OpenSearchIndex
          Properties:
            ServiceToken: !GetAtt IndexCreationFunction.Arn

    Notes:
        - Implements retry mechanism with exponential backoff
        - Maximum 3 retry attempts
        - Initial backoff of 3 seconds
        - Checks for existing index before creation
        - Waits for IAM permission propagation
        - Logs detailed operation status and errors
        - Uses crhelper for CloudFormation response handling

    AWS Best Practices:
        - Implements idempotency through index existence check
        - Handles eventual consistency of IAM permissions
        - Uses exponential backoff for retries
        - Provides detailed logging for troubleshooting
        - Properly handles CloudFormation stack events
    """
    index_name = os.getenv("BEDROCK_KB_INDEX_NAME")
    attempt = 0
    max_retries = 3
    initial_backoff = 3
    while attempt < max_retries:
        try:
            exists_response = oss_client.indices.exists(index_name)
            print(f"{index_name} exists status: {exists_response}")
            if exists_response:
                print(f"Index '{index_name}' already exists. Skipping creation.")
                return
            print(f"Attempting to create index '{index_name}' (attempt {attempt+1}/{max_retries})")
            response = oss_client.indices.create(index_name, body=json.dumps(body_json))
            print(f"Creating index response: {json.dumps(response, default=str)}")
            backoff_time = initial_backoff * 10
            time.sleep(backoff_time)
            return response
        except (RequestError, ConnectionError, AuthorizationException) as e:
            print(f"Exception occurred when trying to create index: {str(EOFError)}")
            if "User does not have permissions for the requested resource" in str(e):
                print("User permissions error detected. Need to wait for data access rules to be enforced")
            attempt += 1
            if attempt >= max_retries:
                print(f"Max retries ({max_retries}) exceeded. Failed to create index")
                raise  # Re-raise the last exception

            # Calculate backoff time with exponential increase
            backoff_time = initial_backoff * (2 ** attempt)
            print(f"Attempt {attempt + 1} failed. Retrying in {backoff_time} seconds...")
            time.sleep(backoff_time)
    else:
        print("Index creation could not be verified")
        raise


@helper.update
def update(event, context):
    return None


@helper.delete
def delete(event, context):
    return None


def handler(event, context):
    print(f"event received: {json.dumps(event, default=str)}")
    helper(event, context)
