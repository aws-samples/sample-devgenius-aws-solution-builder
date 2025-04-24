import streamlit as st
import boto3
import os
from pypdf import PdfWriter, PdfReader
import io
import tempfile
from botocore.config import Config
# Import necessary modules
from langchain.document_loaders import UnstructuredPowerPointLoader

# NORTHSTAR_S3_BUCKET_NAME = os.environ.get('NORTHSTAR_S3_BUCKET_NAME')
NORTHSTAR_S3_BUCKET_NAME = "devgenius-reinvent-release-037225164867-us-west-2"
AWS_REGION = os.getenv("AWS_REGION")
config = Config(read_timeout=1000, retries=(dict(max_attempts=5)))

bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION, config=config)
s3_client = boto3.client('s3', region_name=AWS_REGION, config=config)
s3_resource = boto3.resource('s3', region_name=AWS_REGION)

import re

class PPTExtraction:
    def __init__(self, file_path):
        """
        Initialize PPTExtraction class with the provided file path.

        Args:
        - file_path (str): Path to the PowerPoint file.
        """
        self.file_path = file_path
        # Initialize the UnstructuredPowerPointLoader to load PowerPoint data.
        self.loader = UnstructuredPowerPointLoader(self.file_path, mode="elements")
        # Load the PowerPoint data.
        self.data = self.loader.load()

    def extract(self):
        """
        Extract text content from the PowerPoint slides and format them.

        Returns:
        - str: Formatted text containing the extracted content.
        """
        slides = []
        current_slide_number = None

        # Iterate through each document in the PowerPoint data.
        for document in self.data:
            # Check the category of the current document.
            if document.metadata["category"] == "Title":
                slide_number = document.metadata["page_number"]
                # If the slide number changes, format the slide accordingly.
                if slide_number != current_slide_number:
                    if slide_number == 1:
                        slide = f"Slide {slide_number}:\n\nTitle: {document.page_content}"
                    else:
                        slide = f"Slide {slide_number}:\n\nOutline: {document.page_content}"
                    current_slide_number = slide_number
                else:
                    slide = f"Outline: {document.page_content}"
            elif document.metadata["category"] in ["NarrativeText", "ListItem"]:
                slide = f"Content: {document.page_content}"
            elif document.metadata["category"] == "PageBreak":
                # If it's a page break, reset the current slide number.
                slide = ""
                current_slide_number = None
            else:
                continue

            slides.append(slide)

        # Join the formatted slides into a single string.
        formatted_slides = "\n\n".join(slides)
        return formatted_slides


def split_pdf(pdf_content):
    pdf_reader = PdfReader(io.BytesIO(pdf_content))
    total_pages = len(pdf_reader.pages)
    mid_point = total_pages // 2

    # Create two new PDF writers
    part1_writer = PdfWriter()
    part2_writer = PdfWriter()

    # Split pages between the two writers
    for page_num in range(total_pages):
        if page_num < mid_point:
            part1_writer.add_page(pdf_reader.pages[page_num])
        else:
            part2_writer.add_page(pdf_reader.pages[page_num])

    # Save both parts to bytes objects
    part1_bytes = io.BytesIO()
    part2_bytes = io.BytesIO()

    part1_writer.write(part1_bytes)
    part2_writer.write(part2_bytes)

    return part1_bytes.getvalue(), part2_bytes.getvalue()


def upload_to_s3(file_content, filename, bucket_name):
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=filename,
            Body=file_content
        )
        return True
    except Exception as e:
        st.error(f"Error uploading to S3: {str(e)}")
        return False


def upload_file():
    with st.sidebar:
        # File uploader
        uploaded_file = st.file_uploader(
            "Upload a file",
            type=['pdf', 'doc','docx','xls', 'xlsx','csv','txt']
        )

        if uploaded_file is not None:
            file_content = uploaded_file.read()
            file_size = len(file_content)
            file_extension = uploaded_file.name.split('.')[-1].lower()
            print("file_extension:",file_extension)
            print("uploaded_file.name:",uploaded_file.name)

            # Save the uploaded file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file.flush()  # Ensure all data is written to disk
                file_path = tmp_file.name

            # Handle large files (> 45MB)
            if file_extension == 'pdf':
                if file_size > 45 * 1024 * 1024:  # 45MB in bytes
                    st.info("File is larger than 45MB. Splitting into two parts...")
                    part1, part2 = split_pdf(file_content)
                    # Upload both parts
                    filename_base = uploaded_file.name.rsplit('.', 1)[0]
                    success1 = upload_to_s3(part1, f"{filename_base}_part1.pdf", NORTHSTAR_S3_BUCKET_NAME)
                    success2 = upload_to_s3(part2, f"{filename_base}_part2.pdf", NORTHSTAR_S3_BUCKET_NAME)

                    if success1 and success2:
                        st.success("Both parts uploaded successfully!")
                else:
                    # Upload normal file
                    if upload_to_s3(file_content, uploaded_file.name, NORTHSTAR_S3_BUCKET_NAME):
                        st.success("File uploaded successfully!")
            # Handle PPT/PPTX conversion
            elif file_extension in ['ppt', 'pptx']:
                st.info("Converting PowerPoint to txt...")
                ppt_extract = PPTExtraction(file_path)
                updated_file_content = ppt_extract.extract()
                # file_content = convert_ppt_to_pdf(file_content)
                uploaded_file.name = uploaded_file.name.rsplit('.', 1)[0] + '.txt'
                # Upload normal file
                if upload_to_s3(updated_file_content, uploaded_file.name, NORTHSTAR_S3_BUCKET_NAME):
                    st.success("File uploaded successfully!")
            else: # docx, txt, xlsx,csv
                if file_size > 45 * 1024 * 1024:  # 45MB in bytes
                    st.error("Files larger than 45MB that are not PDFs cannot be split automatically.")
                else:
                # Upload normal file
                    if upload_to_s3(file_content, uploaded_file.name, NORTHSTAR_S3_BUCKET_NAME):
                        st.success("File uploaded successfully!")

