import streamlit as st
from utils import BEDROCK_MODEL_ID
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
from utils import invoke_bedrock_model_streaming
import uuid
from styles import apply_custom_styles


# Generate Cost Estimates
@st.fragment
def generate_cost_estimates(cost_messages):
    apply_custom_styles()
    cost_messages = cost_messages[:]

    # Retain messages and previous insights in the chat section
    if 'cost_messages' not in st.session_state:
        st.session_state.cost_messages = []

    # Create the radio button for cost estimate selection
    if 'cost_user_select' not in st.session_state:
        print("not in session_state")
        st.session_state.cost_user_select = False  # Initialize the value if it doesn't exist

    # Concatenate all 'content' from messages where 'role' is 'assistant'
    concatenated_message = ' '.join(
        message['content'] for message in cost_messages if message['role'] == 'assistant'
    )

    left, middle, right = st.columns([3, 1, 0.5])

    with left:
        # st.markdown("**Use the checkbox below to get cost estimates of AWS services in the proposed solution**")
        st.markdown(
            "<div style='font-size: 18px'><b>Use the checkbox below to get cost estimates of AWS services in the proposed solution</b></div>",  # noqa
            unsafe_allow_html=True)
        st.divider()
        st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
        select_cost = st.checkbox(
            "Check this box to get the cost estimates",
            key="cost",
        )
        print(select_cost)
        # Only update the session state when the checkbox value changes
        if select_cost != st.session_state.cost_user_select:
            print(select_cost)
            st.session_state.cost_user_select = select_cost
        print("st.session_state.cost_user_select", st.session_state.cost_user_select)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        if st.session_state.cost_user_select:
            st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
            if st.button(label="⟳ Retry", key="retry-cost", type="secondary"):
                st.session_state.cost_user_select = True  # Probably redundant
            st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.cost_user_select:
        cost_prompt = f"""
            Calculate approximate monthly cost for the generated architecture based on the following description:
            {concatenated_message}
            Use https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html for getting the latest pricing.
            Provide a short summary for easier consumption in a tabular format - service name, configuration size, price, and total cost.
            Order the services by the total cost in descending order while displaying the tabular format.
            The tabular format should look **very professional and readable**, with a clear structure that is easy to interpret. 
            Ensure that the services are ordered by **Total Cost** in descending order to highlight the most expensive services first.
            Use the below example as reference to generate the pricing details in tabular output format.
            <example>
            Based on the architecture described and using the latest AWS pricing information, here's an approximate monthly cost breakdown for the enterprise data lake solution. Please note that these are estimates and actual costs may vary based on usage, data transfer, and other factors.

    | Service Name | Configuration | Price (per unit) | Estimated Monthly Cost |
    |--------------|---------------|-------------------|------------------------|
    | Amazon ECS (Fargate) | 2 tasks, 0.25 vCPU, 0.5 GB RAM, running 24/7 | $0.04048 per hour | $59.50 |
    | Amazon OpenSearch | 1 t3.small.search instance, 10 GB EBS | $0.036 per hour + $0.10 per GB-month | $27.40 |
    | Amazon S3 | 100 GB storage, 100 GB data transfer | $0.023 per GB-month + $0.09 per GB transfer | $11.30 |
    | Amazon CloudFront | 100 GB data transfer, 1M requests | $0.085 per GB + $0.0075 per 10,000 requests | $9.25 |
    | Application Load Balancer | 1 ALB, running 24/7 | $0.0225 per hour + $0.008 per LCU-hour | $16.74 |
    | Amazon DynamoDB | 25 GB storage, 1M write requests, 1M read requests | $0.25 per GB-month + $1.25 per million write requests + $0.25 per million read requests | $7.75 |
    | AWS Lambda | 1M invocations, 128 MB memory, 100ms avg. duration | $0.20 per 1M requests + $0.0000166667 per GB-second | $0.41 |
    | Amazon CloudWatch | 5 GB logs ingested, 5 custom metrics | $0.50 per GB ingested + $0.30 per metric per month | $4.00 |
    | Amazon VPC | 1 NAT Gateway, running 24/7 | $0.045 per hour + $0.045 per GB processed | $33.48 |
    | Total Estimated Monthly Cost | | | $169.83 |

    Please note:
    1. These estimates assume moderate usage and may vary based on actual workload.
    2. Data transfer costs between services within the same region are not included, as they are typically free.
    3. Costs for AWS CDK, CloudFormation, and IAM are not included as they are generally free services.
    4. The Bedrock Agent and Claude Model costs are not included as pricing information for these services was not available at the time of this estimation.
    5. Actual costs may be lower with reserved instances, savings plans, or other discounts available to your AWS account.
            </example>
            """  # noqa

        cost_messages.append({"role": "user", "content": cost_prompt})

        cost_response, stop_reason = invoke_bedrock_model_streaming(cost_messages)
        cost_response = cost_response.replace("$", "USD ")
        st.session_state.cost_messages.append({"role": "assistant", "content": cost_response})

        with st.container(height=350):
            st.markdown(cost_response)

        st.session_state.interaction.append({"type": "Cost Analysis", "details": cost_response})
        store_in_s3(content=cost_response, content_type='cost')
        save_conversation(st.session_state['conversation_id'], cost_prompt, cost_response)
        collect_feedback(str(uuid.uuid4()), cost_response, "generate_cost", BEDROCK_MODEL_ID)
