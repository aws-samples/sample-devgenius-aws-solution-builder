import uuid
import streamlit as st
from utils import BEDROCK_MODEL_ID
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
from utils import invoke_bedrock_model_streaming


# Generate documentation
@st.fragment
def generate_doc(doc_messages):

    doc_messages = doc_messages[:]

    # Retain messages and previous insights in the chat section
    if 'doc_messages' not in st.session_state:
        st.session_state.doc_messages = []

    # Create the radio button for cost estimate selection
    if 'doc_user_select' not in st.session_state:
        st.session_state.doc_user_select = False  # Initialize the value if it doesn't exist

    left, middle, right = st.columns([3, 1, 0.5])

    with left:
        st.markdown(
            "<div style='font-size: 18px'><b>Use the checkbox below to generate generate technical documentation for the proposed solution</b></div>",  # noqa
            unsafe_allow_html=True)
        st.divider()
        st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
        select_doc = st.checkbox(
            "Check this box to generate documentation",
            key="doc",
        )
        # Only update the session state when the checkbox value changes
        if select_doc != st.session_state.doc_user_select:
            st.session_state.doc_user_select = select_doc
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        if st.session_state.doc_user_select:
            st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
            if st.button(label="⟳ Retry", key="retry-doc", type="secondary"):
                st.session_state.doc_user_select = True  # Probably redundant
            st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.doc_user_select:
        doc_prompt = """
            For the given solution, generate a complete, professional technical documentation including a table of contents, 
            for the following architecture. Expand all the table of contents topics to create a comprehensive professional technical documentation
        """  # noqa

        st.session_state.doc_messages.append({"role": "user", "content": doc_prompt})
        doc_messages.append({"role": "user", "content": doc_prompt})

        doc_response, stop_reason = invoke_bedrock_model_streaming(doc_messages)
        st.session_state.doc_messages.append({"role": "assistant", "content": doc_response})

        with st.container(height=350):
            st.markdown(doc_response)

        st.session_state.interaction.append({"type": "Technical documentation", "details": doc_response})
        store_in_s3(content=doc_response, content_type='documentation')
        save_conversation(st.session_state['conversation_id'], doc_prompt, doc_response)
        collect_feedback(str(uuid.uuid4()), doc_response, "generate_documentation", BEDROCK_MODEL_ID)
