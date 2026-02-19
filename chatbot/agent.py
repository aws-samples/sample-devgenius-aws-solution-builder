import streamlit as st
import os
import boto3
from botocore.config import Config
from PIL import Image
from utils import invoke_bedrock_agent
from utils import read_agent_response
from utils import enable_artifacts_download
from utils import retrieve_environment_variables
from utils import save_conversation
from utils import save_session
from utils import invoke_bedrock_model_streaming
from layout import create_tabs, create_option_tabs, welcome_sidebar, login_page
from styles import apply_styles
from cost_estimate_widget import generate_cost_estimates
from generate_arch_widget import generate_arch
from generate_cdk_widget import generate_cdk
from generate_cfn_widget import generate_cfn
from generate_doc_widget import generate_doc
import io

# Streamlit configuration 
st.set_page_config(page_title="DevGenius", layout='wide')
apply_styles()

# Initialize AWS clients
AWS_REGION = os.getenv("AWS_REGION")
config = Config(read_timeout=1000, retries=dict(max_attempts=5))
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION, config=config)
s3_client = boto3.client('s3', region_name=AWS_REGION)
sts_client = boto3.client('sts', region_name=AWS_REGION)
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)

ACCOUNT_ID = sts_client.get_caller_identity()["Account"]
# Constants
BEDROCK_MODEL_ID = f"arn:aws:bedrock:{AWS_REGION}:{ACCOUNT_ID}:inference-profile/us.anthropic.claude-sonnet-4-6"  # noqa
CONVERSATION_TABLE_NAME = retrieve_environment_variables("CONVERSATION_TABLE_NAME")
FEEDBACK_TABLE_NAME = retrieve_environment_variables("FEEDBACK_TABLE_NAME")
SESSION_TABLE_NAME = retrieve_environment_variables("SESSION_TABLE_NAME")
S3_BUCKET_NAME = retrieve_environment_variables("S3_BUCKET_NAME")
BEDROCK_AGENT_ID = retrieve_environment_variables("BEDROCK_AGENT_ID")
BEDROCK_AGENT_ALIAS_ID = retrieve_environment_variables("BEDROCK_AGENT_ALIAS_ID")


def display_image(image, width=600, caption="Uploaded Image", use_center=True):
    if use_center:
        # Center the image using columns
        col1, col2, col3 = st.columns([1, 2, 1])
        display_container = col2
    else:
        # Use full width container
        display_container = st

    with display_container:
        st.image(
            image,
            caption=caption,
            width=width,
            use_column_width=False,
            clamp=True  # Prevents image from being larger than its original size
        )


# Function to interact with the Bedrock model using an image and query
def get_image_insights(image_data, query="Explain in detail the architecture flow"):
    query = ('''Explain in detail the architecture flow.
             If the given image is not related to technical architecture, then please request the user to upload an AWS architecture or hand drawn architecture.
             When generating the solution , highlight the AWS service names in bold
             ''')  # noqa
    messages = [{
        "role": "user",
        "content": [
            {"image": {"format": "png", "source": {"bytes": image_data}}},
            {"text": query}
        ]}
    ]
    try:
        streaming_response = bedrock_client.converse_stream(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            inferenceConfig={"maxTokens": 2000, "temperature": 0.1, "topP": 0.9}
        )

        full_response = ""
        output_placeholder = st.empty()
        for chunk in streaming_response["stream"]:
            if "contentBlockDelta" in chunk:
                text = chunk["contentBlockDelta"]["delta"]["text"]
                full_response += text
                output_placeholder.markdown(f"<div class='wrapped-text'>{full_response}</div>", unsafe_allow_html=True)
        output_placeholder.write("")

        if 'mod_messages' not in st.session_state:
            st.session_state.mod_messages = []
        st.session_state.mod_messages.append({"role": "assistant", "content": full_response})
        st.session_state.interaction.append({"type": "Architecture details", "details": full_response})
        save_conversation(st.session_state['conversation_id'], prompt, full_response)

    except Exception as e:
        st.error(f"ERROR: Can't invoke '{BEDROCK_MODEL_ID}'. Reason: {e}")


# Reset the chat history in session state
def reset_chat():
    # Clear specific message-related session states
    keys_to_keep = {'conversation_id', 'user_authenticated', 'user_name', 'user_email', 'cognito_authentication', 'token', 'midway_user'}  # noqa
    keys_to_remove = set(st.session_state.keys()) - keys_to_keep

    for key in keys_to_remove:
        del st.session_state[key]

    st.session_state.messages = []


# Reset the chat history in session state
def reset_messages():
    # st.session_state['conversation_id'] = str(uuid.uuid4())

    initial_question = get_initial_question(st.session_state.topic_selector)
    st.session_state.messages = [{"role": "assistant", "content": "Welcome to DevGenius — turning ideas into reality. Together, we’ll design your architecture and solution, with each conversation shaping your vision. Let’s get started on building!"}]

    if initial_question:
        st.session_state.messages.append({"role": "user", "content": initial_question})
        response = invoke_bedrock_agent(st.session_state.conversation_id, initial_question)
        event_stream = response['completion']
        ask_user, agent_answer = read_agent_response(event_stream)
        st.session_state.messages.append({"role": "assistant", "content": agent_answer})


# Function to format assistant's response for markdown
def format_for_markdown(response_text):
    return response_text.replace("\n", "\n\n")  # Ensure proper line breaks for markdown rendering


def get_initial_question(topic):
    return {
        "Data Lake": "How can I build an enterprise data lake on AWS?",
        "Log Analytics": "How can I build a log analytics solution on AWS?"
    }.get(topic, "")


# Function to compress or resize image if it exceeds 5MB
def resize_or_compress_image(uploaded_image):
    # Open the image using PIL
    image = Image.open(uploaded_image)

    # Check the size of the uploaded image
    image_bytes = uploaded_image.getvalue()
    if len(image_bytes) > 5 * 1024 * 1024:  # 5MB in bytes
        st.write("Image size exceeds 5MB. Resizing...")

        # Resize the image (you can adjust the dimensions as needed)
        image = image.resize((800, 600))  # Example resize, you can adjust this

        # Compress the image by saving it to a BytesIO object with reduced quality
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="JPEG", quality=85)  # Adjust quality if needed
        img_byte_arr.seek(0)

        # Return the compressed image
        return img_byte_arr
    else:
        # If the image is under 5MB, no resizing is needed, just return the original
        return uploaded_image


#########################################
# Streamlit Main Execution Starts Here
#########################################
if 'user_authenticated' not in st.session_state:
    st.session_state.user_authenticated = False
if 'interaction' not in st.session_state:
    st.session_state.interaction = []

if not st.session_state.user_authenticated:
    login_page()
else:
    # Save session on first load after login
    if 'session_saved' not in st.session_state:
        save_session(
            st.session_state['conversation_id'],
            st.session_state.get('user_name', ''),
            st.session_state.get('user_email', '')
        )
        st.session_state.session_saved = True

    tabs = create_tabs()
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = "Build a solution"
    with st.sidebar:
        # st.title("DevGenius")
        welcome_sidebar()

    # Tab for "Generate Architecture Diagram and Solution"
    with tabs[0]:
        st.header("Generate Architecture Diagram and Solution")

        if "topic_selector" not in st.session_state:
            st.session_state.topic_selector = ""
            reset_messages()

        if st.session_state.active_tab != "Build a solution":
            print("inside tab1 active_tab:", st.session_state.active_tab)
            st.session_state.active_tab = "Build a solution"

        # col1, col2, _, _, right = st.columns(5)
        # with col1:
        #     topic = st.selectbox("Select the feature to proceed", ["","Data Lake", "Log Analytics"], key="topic_selector", on_change=reset_messages)  # noqa
        # with right:
        #     st.button('Clear Chat History', on_click=reset_messages)

        if "messages" not in st.session_state:
            st.session_state["messages"] = [{"role": "assistant", "content": "Welcome"}]

        # Display the conversation messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        prompt = st.chat_input(key='Generate')

        if prompt:

            # when the user refines the solution , reset checkbox of all tabs
            # and force user to re-check to generate updated solution
            st.session_state.cost = False
            st.session_state.arch = False
            st.session_state.cdk = False
            st.session_state.cfn = False
            st.session_state.doc = False

            st.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = invoke_bedrock_agent(st.session_state.conversation_id, prompt)
                    event_stream = response['completion']
                    ask_user, agent_answer = read_agent_response(event_stream)
                    st.markdown(agent_answer)

            st.session_state.messages.append({"role": "assistant", "content": agent_answer})

            # Check if we have reached the number of questions
            if not ask_user:
                st.session_state.interaction.append(
                    {"type": "Details", "details": st.session_state.messages[-1]['content']})
                devgenius_option_tabs = create_option_tabs()
                with devgenius_option_tabs[0]:
                    generate_cost_estimates(st.session_state.messages)
                with devgenius_option_tabs[1]:
                    generate_arch(st.session_state.messages)
                with devgenius_option_tabs[2]:
                    generate_cdk(st.session_state.messages)
                with devgenius_option_tabs[3]:
                    generate_cfn(st.session_state.messages)
                with devgenius_option_tabs[4]:
                    generate_doc(st.session_state.messages)
                enable_artifacts_download()

            save_conversation(st.session_state['conversation_id'], prompt, agent_answer)

    # Tab for "Generate Solution from Existing Architecture"
    with tabs[1]:
        st.header("Generate Solution from Existing Architecture")

        # Custom CSS to style the file uploader button
        st.markdown("""
            <style>
            /* Target the file uploader button */
            .stFileUploader button {
                background-color: #4CAF50; /* Green background for the button */
                color: white !important; /* White text color */
                border: none !important; /* Remove default border */
                padding: 10px 20px; /* Add padding */
                border-radius: 5px; /* Rounded corners */
                font-size: 16px; /* Font size */
                cursor: pointer; /* Pointer cursor on hover */
            }

            /* Add hover effect to make the button look more interactive */
            .stFileUploader button:hover {
                background-color: #45a049; /* Darker green when hovered */
            }
            </style>
        """, unsafe_allow_html=True)

        # File uploader and image insights logic
        uploaded_file = st.file_uploader("Choose an image...", type=["png", "jpg", "jpeg"], on_change=reset_chat)
        if st.session_state.active_tab != "Modify your existing architecture":
            print("inside tab2 active_tab:", st.session_state.active_tab)
            # reset_chat()
            st.session_state.active_tab = "Modify your existing architecture"

        if uploaded_file:
            # write the upload file to S3 bucket
            s3_key = f"{st.session_state.conversation_id}/uploaded_file/{uploaded_file.name}"  # noqa
            # response = s3_client.put_object(Body=uploaded_file.getvalue(), Bucket=S3_BUCKET_NAME, Key=s3_key)
            # print(response)
            # st.session_state.uploaded_image = uploaded_file
            resized_image = resize_or_compress_image(uploaded_file)
            response = s3_client.put_object(Body=resized_image, Bucket=S3_BUCKET_NAME, Key=s3_key)
            st.session_state.uploaded_image = resized_image
            image = Image.open(st.session_state.uploaded_image)
            display_image(image)
            image_bytes = st.session_state.uploaded_image.getvalue()

            if 'image_insights' not in st.session_state:
                st.session_state.image_insights = get_image_insights(
                    image_data=image_bytes)

        if 'mod_messages' not in st.session_state:
            st.session_state.mod_messages = []

        if 'generate_arch_called' not in st.session_state:
            st.session_state.generate_arch_called = False

        if 'generate_cost_estimates_called' not in st.session_state:
            st.session_state.generate_cost_estimates_called = False

        if 'generate_cdk_called' not in st.session_state:
            st.session_state.generate_cdk_called = False

        if 'generate_cfn_called' not in st.session_state:
            st.session_state.generate_cfn_called = False

        if 'generate_doc_called' not in st.session_state:
            st.session_state.generate_doc_called = False

        # Display chat history
        for msg in st.session_state.mod_messages:
            if msg["role"] == "user":
                st.chat_message("user").markdown(msg["content"])
            elif msg["role"] == "assistant":
                # Format the assistant's response for markdown (ensure proper rendering)
                formatted_content = format_for_markdown(msg["content"])
                st.chat_message("assistant").markdown(formatted_content)

        # Trigger actions for generating solution
        if uploaded_file:
            devgenius_option_tabs = create_option_tabs()
            with devgenius_option_tabs[0]:
                if not st.session_state.generate_cost_estimates_called:
                    generate_cost_estimates(st.session_state.mod_messages)
                    st.session_state.generate_cost_estimates_called = True
            with devgenius_option_tabs[1]:
                if not st.session_state.generate_arch_called:
                    generate_arch(st.session_state.mod_messages)
                    st.session_state.generate_arch_called = True

            with devgenius_option_tabs[2]:
                if not st.session_state.generate_cdk_called:
                    generate_cdk(st.session_state.mod_messages)
                    st.session_state.generate_cdk_called = True

            with devgenius_option_tabs[3]:
                if not st.session_state.generate_cfn_called:
                    generate_cfn(st.session_state.mod_messages)
                    st.session_state.generate_cfn_called = True

            with devgenius_option_tabs[4]:
                if not st.session_state.generate_doc_called:
                    generate_doc(st.session_state.mod_messages)
                    st.session_state.generate_doc_called = True

            if st.session_state.interaction:
                enable_artifacts_download()

        # Handle new chat input
        if prompt := st.chat_input():
            st.session_state.generate_arch_called = False
            st.session_state.generate_cdk_called = False
            st.session_state.generate_cfn_called = False
            st.session_state.generate_cost_estimates_called = False
            st.session_state.generate_doc_called = False

            # when the user refines the solution , reset checkbox of all tabs
            # and force user to re-check to generate updated solution
            st.session_state.cost = False
            st.session_state.arch = False
            st.session_state.cdk = False
            st.session_state.cfn = False
            st.session_state.doc = False

            st.session_state.mod_messages.append({"role": "user", "content": prompt})
            st.chat_message("user").markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = invoke_bedrock_model_streaming(st.session_state.mod_messages)
                    st.session_state.interaction.append({"type": "Architecture details", "details": response})
                    st.markdown(f"<div class='wrapped-text'>{response}</div>", unsafe_allow_html=True)

            st.session_state.mod_messages.append({"role": "assistant", "content": response[0]})
            save_conversation(st.session_state['conversation_id'], prompt, response[0])
            st.rerun()
