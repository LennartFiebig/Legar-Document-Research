import streamlit as st
from openai import OpenAI
import os
import glob

# Set page title and configuration
st.set_page_config(page_title="Legal Research Assistant", layout="wide")
st.title("Legal Research Assistant")

# Initialize API key and validation state in session state if not present
if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = ""
if "api_key_valid" not in st.session_state:
    st.session_state.api_key_valid = False
if "success_message" not in st.session_state:
    st.session_state.success_message = None

# API Key input and validation
with st.sidebar:
    api_key = st.text_input("Enter your OpenAI API Key", type="password", value=st.session_state.openai_api_key)
    
    def validate_api_key():
        try:
            # Try to create a client with the provided key
            test_client = OpenAI(api_key=api_key)
            # Make a simple API call to validate the key
            test_client.models.list()
            st.session_state.openai_api_key = api_key
            st.session_state.api_key_valid = True
            st.session_state.error_message = None
            st.session_state.success_message = "✅ API key validated successfully! You can now use the chat."
        except Exception as e:
            st.session_state.api_key_valid = False
            st.session_state.error_message = "Invalid API key. Please check your key and try again."
            st.session_state.success_message = None

    # Add validate button
    if st.button("Validate API Key"):
        validate_api_key()

    # Show error message if validation failed
    if hasattr(st.session_state, 'error_message') and st.session_state.error_message:
        st.error(st.session_state.error_message)
    
    # Show success message if validation was successful
    if st.session_state.success_message:
        st.success(st.session_state.success_message)

if st.session_state.api_key_valid:
    # Initialize OpenAI client
    @st.cache_resource
    def get_client():
        return OpenAI(api_key=st.session_state.openai_api_key)

    client = get_client()

    # Initialize session state for chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        # Create a new thread
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id

    # Setup assistant if not already in session state
    if "assistant" not in st.session_state:
        # Create or retrieve the assistant
        assistant = client.beta.assistants.create(
            name="Research Assistant in Law",
            instructions="You are an expert research assistant in law. Use your knowledge base to answer questions about law.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
        )
        
        # Create a vector store called "uploaded_files" if it doesn't already exist
        try:
            # Try to retrieve the vector store first
            vector_stores = client.vector_stores.list()
            vector_store = next((vs for vs in vector_stores.data if vs.name == "Schriftsätze"), None)
            if vector_store is None:
                raise Exception("Vector store not found")
        except:
            # If retrieval fails, create a new one
            raise Exception("Vector store not found")
        
        # Update assistant with vector store
        assistant = client.beta.assistants.update(
            assistant_id=assistant.id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
        )
        
        st.session_state.assistant = assistant
        st.session_state.vector_store_id = vector_store.id

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Get user input
    user_input = st.chat_input("Ask a question...")

    if user_input:
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # Display user message
        with st.chat_message("user"):
            st.write(user_input)
        
        # Add the user message to the thread
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=user_input
        )
        
        # Show assistant is thinking
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.write("Thinking...")
            
            # Run the assistant
            run = client.beta.threads.runs.create_and_poll(
                thread_id=st.session_state.thread_id,
                assistant_id=st.session_state.assistant.id
            )
            
            # Get the latest message
            messages = list(client.beta.threads.messages.list(
                thread_id=st.session_state.thread_id
            ))
            
            # Process the response
            message_content = messages[0].content[0].text
            annotations = message_content.annotations
            citations = []
            
            # Process citations if any
            for index, annotation in enumerate(annotations):
                message_content.value = message_content.value.replace(annotation.text, f"[{index}]")
                if file_citation := getattr(annotation, "file_citation", None):
                    cited_file = client.files.retrieve(file_citation.file_id)
                    citations.append(f"[{index}] {cited_file.filename}")
            
            # Display the response
            response_text = message_content.value
            if citations:
                response_text += "\n\n" + "\n".join(citations)
            
            message_placeholder.write(response_text)
            
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": response_text})
else:
    st.info("Please enter your OpenAI API key in the sidebar and click 'Validate API Key' to begin.")
