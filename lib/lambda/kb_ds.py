import json
import os
import boto3
from crhelper import CfnResource

REGION = os.getenv("AWS_REGION")
DATA_SOURCES = os.getenv("DATA_SOURCES")
service = "aoss"

boto3_session = boto3.session.Session()
bedrock_agent_client = boto3_session.client('bedrock-agent', region_name=REGION)
helper = CfnResource(json_logging=False, log_level="DEBUG", boto_level="CRITICAL")


@helper.create
def create(event, context):
    # Create datasource
    seedUrls = []
    for data_source in DATA_SOURCES.split(","):
        seedUrls.append({"url": data_source})
    create_ds_response = bedrock_agent_client.create_data_source(
        name=os.getenv("DATASOURCE_NAME"),
        dataDeletionPolicy='RETAIN',
        description="Data source for Bedrock Knowledge Base",
        knowledgeBaseId=os.getenv("KNOWLEDGE_BASE_ID"),
        dataSourceConfiguration={
            "type": "WEB",
            "webConfiguration": {
                "crawlerConfiguration": {
                    "crawlerLimits": {
                        "rateLimit": 300
                    }
                },
                "sourceConfiguration": {
                    "urlConfiguration": {
                        "seedUrls": seedUrls
                    }
                }
            }
        },
        vectorIngestionConfiguration={}
    )
    ds = create_ds_response["dataSource"]
    print(f"Datasource response: {ds}")

    # Start an ingestion job
    start_job_response = bedrock_agent_client.start_ingestion_job(
        knowledgeBaseId=os.getenv("KNOWLEDGE_BASE_ID"),
        dataSourceId=ds["dataSourceId"])
    job = start_job_response["ingestionJob"]
    print(f"Ingestion job: {job}")
    print("Started sync process. This would take a longer time than Lambda timeout. Ending CFN execution here.")  # noqa


@helper.update
def update(event, context):
    return None


@helper.delete
def delete(event, context):
    # Delete datasource
    response = bedrock_agent_client.list_data_sources(knowledgeBaseId=os.getenv("KNOWLEDGE_BASE_ID"))
    for ds in response["dataSourceSummaries"]:
        bedrock_agent_client.delete_data_source(
            knowledgeBaseId=os.getenv("KNOWLEDGE_BASE_ID"), dataSourceId=ds["dataSourceId"])
        print(f"Deleted data source name: {ds['name']} with id: {ds['dataSourceId']}")
    return None


def handler(event, context):
    print(f"event received: {json.dumps(event, default=str)}")
    helper(event, context)
