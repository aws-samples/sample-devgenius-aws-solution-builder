import os
import boto3
import streamlit as st
import get_code_from_markdown
from botocore.config import Config
from utils import BEDROCK_MODEL_ID
from utils import invoke_bedrock_model_streaming
from utils import retrieve_environment_variables
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
import uuid

AWS_REGION = os.getenv("AWS_REGION")

config = Config(read_timeout=1000, retries=(dict(max_attempts=5)))
s3_client = boto3.client('s3', region_name=AWS_REGION)
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION, config=config)


# Generate CFN
@st.fragment
def generate_cfn(cfn_messages):
    cfn_messages = cfn_messages[:]

    # Retain messages and previous insights in the chat section
    if 'cfn_messages' not in st.session_state:
        st.session_state.cfn_messages = []

    # Create the radio button for cost estimate selection
    if 'cfn_user_select' not in st.session_state:
        st.session_state.cfn_user_select = None  # Initialize the value if it doesn't exist

    left, middle, right = st.columns([4, 0.5, 0.5])

    with left:
        st.markdown(
            "<div style='font-size: 18px'><b>Use the checkbox below to generate AWS CloudFormation Template code to deploy the proposed solution as Infrastructure as Code</b></div>",  # noqa
            unsafe_allow_html=True)
        st.divider()
        st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
        select_cfn = st.checkbox(
            "Check this box to generate AWS CloudFormation Template",
            key="cfn"
        )
        # Only update the session state when the checkbox value changes
        if select_cfn != st.session_state.cfn_user_select:
            st.session_state.cfn_user_select = select_cfn
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        if st.session_state.cfn_user_select:
            st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
            if st.button(label="⟳ Retry", key="retry-cfn", type="secondary"):
                st.session_state.cfn_user_select = True  # Probably redundant
            st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.cfn_user_select:
        cfn_prompt = """
            For the given solution, generate a CloudFormation template in YAML to automate the deployment of AWS resources.
            Provide the actual source code for all the jobs wherever applicable.
            The CloudFormation template should provision all the resources and the components.
            If Python code is needed, generate a "Hello, World!" code example.
            At the end generate sample commands to deploy the CloudFormation template.
        """  # noqa

        cfn_messages.append({"role": "user", "content": cfn_prompt})

        cfn_response, stop_reason = invoke_bedrock_model_streaming(cfn_messages)
        st.session_state.cfn_messages.append({"role": "assistant", "content": cfn_response})

        cfn_yaml = get_code_from_markdown.get_code_from_markdown(cfn_response, language="yaml")[0]

        with st.container(height=350):
            st.markdown(cfn_response)

        S3_BUCKET_NAME = retrieve_environment_variables("S3_BUCKET_NAME")

        st.session_state.interaction.append({"type": "CloudFormation Template", "details": cfn_response})
        store_in_s3(content=cfn_response, content_type='cfn')
        save_conversation(st.session_state['conversation_id'], cfn_prompt, cfn_response)
        collect_feedback(str(uuid.uuid4()), cfn_response, "generate_cfn", BEDROCK_MODEL_ID)

        # Write CFN template to S3 bucket and provide a button to launch the stack in the console
        object_name = f"{st.session_state['conversation_id']}/template.yaml"
        s3_client.put_object(Body=cfn_yaml, Bucket=S3_BUCKET_NAME, Key=object_name)
        template_object_url = f"https://s3.amazonaws.com/{S3_BUCKET_NAME}/{object_name}"

        st.write("Click the below button to deploy the generated solution in your AWS account")
        stack_url = f"https://console.aws.amazon.com/cloudformation/home?region={AWS_REGION}#/stacks/new?stackName=myteststack&templateURL={template_object_url}"  # noqa
        st.markdown("If you don't have an AWS account, you can create one by clicking [this link](https://signin.aws.amazon.com/signup?request_type=register).")  # noqa
        st.markdown(f"[![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)]({stack_url})")  # noqa