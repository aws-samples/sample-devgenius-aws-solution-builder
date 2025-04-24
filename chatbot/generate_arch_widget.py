import uuid
import get_code_from_markdown
import streamlit as st
from utils import BEDROCK_MODEL_ID
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
from utils import continuation_prompt
from utils import convert_xml_to_html
from utils import invoke_bedrock_model_streaming


@st.fragment
def generate_arch(arch_messages):

    arch_messages = arch_messages[:]

    # Retain messages and previous insights in the chat section
    if 'arch_messages' not in st.session_state:
        st.session_state.arch_messages = []

    # Create the radio button for cost estimate selection
    if 'arch_user_select' not in st.session_state:
        st.session_state.arch_user_select = False  # Initialize the value if it doesn't exist

    left, middle, right = st.columns([3, 1, 0.5])

    with left:
        st.markdown(
            "<div style='font-size: 18px'><b>Use the checkbox below to generate a visual representation of the proposed solution</b></div>",  # noqa
            unsafe_allow_html=True)
        st.divider()
        st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
        select_arch = st.checkbox(
            "Check this box to generate architecture",
            key="arch"
        )
        # Only update the session state when the checkbox value changes
        if select_arch != st.session_state.arch_user_select:
            st.session_state.arch_user_select = select_arch
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        if st.session_state.arch_user_select:
            st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
            if st.button(label="⟳ Retry", key="retry", type="secondary"):
                st.session_state.arch_user_select = True  # Probably redundant
            st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.arch_user_select:
        architecture_prompt = """
            Generate an AWS architecture and data flow diagram for the given solution, applying AWS best practices. Follow these steps:
            1. Create an XML file suitable for draw.io that captures the architecture and data flow.
            2. Reference the latest AWS architecture icons here: https://aws.amazon.com/architecture/icons/
            3. Respond only with the XML in markdown format—no additional text.
            4. Ensure the XML is complete, with all elements having proper opening and closing tags.
            5. Confirm that all AWS services/icons are properly connected and enclosed within an AWS Cloud icon, deployed inside a VPC where applicable.
            6. Remove unnecessary whitespace to optimize size and minimize output tokens.
            7. Use valid AWS architecture icons to represent services, avoiding random images.
            8. The final XML should be syntactically correct and cover all components of the given solution.
        """  # noqa

        st.session_state.arch_messages.append({"role": "user", "content": architecture_prompt})
        arch_messages.append({"role": "user", "content": architecture_prompt})

        max_attempts = 4
        full_response_array = []
        full_response = ""

        for attempt in range(max_attempts):
            arch_gen_response, stop_reason = invoke_bedrock_model_streaming(arch_messages, enable_reasoning=True)
            # full_response += arch_gen_response
            full_response_array.append(arch_gen_response)

            if stop_reason != "max_tokens":
                break

            if attempt == 0:
                full_response = ''.join(str(x) for x in full_response_array)
                arch_messages = continuation_prompt(architecture_prompt, full_response)

        if attempt == max_attempts - 1:
            st.error("Reached maximum number of attempts. Final result is incomplete. Please try again.")

        try:
            full_response = ''.join(str(x) for x in full_response_array)
            arch_content_xml = get_code_from_markdown.get_code_from_markdown(full_response, language="xml")[0]
            arch_content_html = convert_xml_to_html(arch_content_xml)
            st.session_state.arch_messages.append({"role": "assistant", "content": "XML"})

            with st.container():
                st.components.v1.html(arch_content_html, scrolling=True, height=350)

            st.session_state.interaction.append({"type": "Solution Architecture", "details": full_response})
            store_in_s3(content=full_response, content_type='architecture')
            save_conversation(st.session_state['conversation_id'], architecture_prompt, full_response)
            collect_feedback(str(uuid.uuid4()), arch_content_xml, "generate_architecture", BEDROCK_MODEL_ID)

        except Exception as e:
            st.error("Internal error occurred. Please try again.")
            print(f"Error occurred when generating architecture: {str(e)}")
            # Removing last element from list so we can retry request by hitting "No" and "Yes"
            del st.session_state.arch_messages[-1]
            del arch_messages[-1]
