import os
import boto3

physical_id = 'TheOnlyCustomResource'
ec2_client = boto3.client("ec2")


def lambda_handler(event, context):
    print(event)
    request_type = event["RequestType"]
    if request_type == "Create":
        return on_create()
    else:
        return on_others()


def on_create():
    try:
        pl_name = os.getenv("PREFIX_LIST_NAME", default="com.amazonaws.global.cloudfront.origin-facing")
        response = ec2_client.describe_managed_prefix_lists(Filters=[{"Name": "prefix-list-name", "Values": [pl_name]}])
        attributes = {
            "PrefixListId": response['PrefixLists'][0]['PrefixListId']
        }
        return {"PhysicalResourceId": physical_id, 'Data': attributes}
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        raise e
    return {"PhysicalResourceId": physical_id}


def on_others():
    return {"PhysicalResourceId": physical_id}
