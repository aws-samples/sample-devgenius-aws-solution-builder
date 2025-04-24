import boto3
import os
import uuid
import datetime
from utils import retrieve_environment_variables


class DynanmoPersistance():
    def __init__(self):
        AWS_REGION = os.getenv("AWS_REGION")
        self.dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
        self.CONVERSATION_TABLE_NAME = retrieve_environment_variables("CONVERSATION_TABLE_NAME")
        self.FEEDBACK_TABLE_NAME = retrieve_environment_variables("FEEDBACK_TABLE_NAME")
        self.SESSION_TABLE_NAME = retrieve_environment_variables("SESSION_TABLE_NAME")
        self.S3_BUCKET_NAME = retrieve_environment_variables("S3_BUCKET_NAME")

    # Store conversation details in DynamoDB
    def save_session(self, conversation_id, name, email):
        item = {
            'conversation_id': conversation_id,
            'user_name': name,
            'user_email': email,
            'session_start_time': datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        self.dynamodb_resource.Table(self.SESSION_TABLE_NAME).put_item(Item=item)

    # Store conversation details in DynamoDB
    def save_conversation(self, conversation_id, prompt, response):
        item = {
            'conversation_id': conversation_id,
            'uuid': str(uuid.uuid4()),
            'user_response': prompt,
            'assistant_response': response,
            'conversation_time': datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        self.dynamodb_resource.Table(self.CONVERSATION_TABLE_NAME).put_item(Item=item)

    # Store conversation details in DynamoDB
    def update_session(self, conversation_id, presigned_url):
        # Update dynamodb table with new attribute pre-signed url for existing conversation id
        print(f"presigned_url: {presigned_url}")
        # Update the item with new attribute
        response = self.dynamodb_resource.Table(self.SESSION_TABLE_NAME).update_item(
            Key={
                'conversation_id': conversation_id
            },
            UpdateExpression='SET presigned_url = :url, session_update_time = :update_time',
            ExpressionAttributeValues={
                ':url': presigned_url,
                ':update_time': datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            },
            ReturnValues="UPDATED_NEW"
        )

        return response
