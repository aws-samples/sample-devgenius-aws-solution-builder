export AWS_REGION="us-west-2"
export BEDROCK_AGENT_ID="XGNQZQXJKU"
export BEDROCK_AGENT_ALIAS_ID="OTOURNGVYA"
export S3_BUCKET_NAME="devgenius-re-data-source-037225164867-us-west-2"
export CONVERSATION_TABLE_NAME="devgenius-re-conversation-table"
export FEEDBACK_TABLE_NAME="devgenius-re-feedback-table"
export SESSION_TABLE_NAME="devgenius-re-session-table"

# Step 1: Get the presigned URL using AWS CLI
temp_url=$(aws sagemaker create-presigned-domain-url --domain-id d-anqncaklahai --user-profile-name default-20241106T140590 --space-name DevGenius --session-expiration-duration-in-seconds 1800 --query 'AuthorizedUrl' --output text)

# Step 2: Modify the URL to include the /proxy/absolute/8501 path
app_url=$(echo "$temp_url" | cut -d '/' -f 1-3)/jupyterlab/default/proxy/8501/

# Step 3: Print the modified app URL
echo "App URL to use after executing the next code block:"
echo "$app_url"

# Check if Streamlit is running
if ps aux | grep '[s]treamlit' > /dev/null; then
    echo "Streamlit is running, stopping it..."
    # Get the process ID and kill the Streamlit process
    pid=$(ps aux | grep '[s]treamlit' | awk '{print $2}')
    kill "$pid"
    sleep 2  # Wait for a few seconds before restarting
else
    echo "Streamlit is not running."
fi

# Restart Streamlit
echo "Restarting Streamlit... Use the URL presented above"
streamlit run agent.py