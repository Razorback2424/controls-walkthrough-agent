# Reusable Controls Walkthrough Agent
#
# INSTRUCTIONS:
# 1. Install the required library: pip install openai
# 2. Set your OpenAI API Key as an environment variable.
#    - Mac/Linux: export OPENAI_API_KEY='your-secret-key'
#    - Windows: setx OPENAI_API_KEY "your-secret-key"
# 3. Upload your PDF/text documents (client processes, professional standards) to OpenAI's
#    platform to get their unique File IDs.
# 4. Update the SCENARIO_CONFIG section below with your File IDs and scenario details.
# 5. Run the script from your terminal: python this_script_name.py

import openai
import json
import os
import time

# --- Part 1: Scenario Configuration ---
#
# IMPORTANT: Before running, you must replace the placeholder 'file-...' IDs
# with your actual File IDs from OpenAI.
# To add a new scenario, simply copy one of the dictionary blocks and
# update its contents with the new information.
#
SCENARIO_CONFIG = {
  "scenarios": [
    {
      "id": "gw_p2p",
      "name": "Global Widgets - Procure to Pay Walkthrough",
      "process_document_id": "file-REPLACE_WITH_YOUR_GLOBAL_WIDGETS_FILE_ID",
      "persona_name": "Sarah",
      "persona_role": "Accounts Payable Clerk",
      "standards_ids": ["file-REPLACE_WITH_YOUR_PCAOB_FILE_ID", "file-REPLACE_WITH_YOUR_COSO_FILE_ID"]
    },
    {
      "id": "ic_o2c",
      "name": "Innovate Corp - Order to Cash Walkthrough",
      "process_document_id": "file-REPLACE_WITH_YOUR_INNOVATE_CORP_FILE_ID",
      "persona_name": "David",
      "persona_role": "Accounts Receivable Manager",
      "standards_ids": ["file-REPLACE_WITH_YOUR_PCAOB_FILE_ID", "file-REPLACE_WITH_YOUR_COSO_FILE_ID"]
    },
    # Add more scenarios here...
    # {
    #   "id": "another_client",
    #   "name": "Another Client - Payroll Process",
    #   "process_document_id": "file-REPLACE_WITH_PAYROLL_DOC_ID",
    #   "persona_name": "Charles",
    #   "persona_role": "HR Specialist",
    #   "standards_ids": ["file-REPLACE_WITH_YOUR_PCAOB_FILE_ID", "file-REPLACE_WITH_YOUR_COSO_FILE_ID"]
    # }
  ]
}

# --- Part 2: Agent Logic ---

# Initialize the OpenAI client
# The client automatically uses the OPENAI_API_KEY environment variable.
try:
    client = openai.OpenAI()
except openai.OpenAIError:
    print("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
    exit()


def choose_scenario():
    """Presents a menu for the user to choose a scenario from the config."""
    scenarios = SCENARIO_CONFIG['scenarios']
    print("Welcome to the Audit Practice Simulator.")
    print("Please choose a scenario to practice:")
    for i, scenario in enumerate(scenarios):
        print(f"{i + 1}: {scenario['name']}")

    while True:
        try:
            choice = int(input("Enter the number of your choice: ")) - 1
            if 0 <= choice < len(scenarios):
                return scenarios[choice]
            else:
                print("Invalid choice. Please select a number from the list.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def create_dynamic_system_prompt(scenario):
    """Dynamically creates the system prompt based on the chosen scenario."""
    persona_name = scenario['persona_name']
    persona_role = scenario['persona_role']
    process_doc_id = scenario['process_document_id']

    return f"""
You are an 'Audit Practice Simulator.' You will play two distinct roles based on a keyword.

**ROLE 1: '{persona_name}, the {persona_role}'**
- When the user begins the walkthrough, you will act as {persona_name}.
- Your knowledge is strictly limited to the information within the process document for this session (ID: {process_doc_id}). You must not invent facts or use external knowledge.
- If the user asks a question not covered in the document, you must respond with "I'm not sure, that's not part of my daily process." or a similar phrase.
- Stay in this character until the user types the exact phrase 'end walkthrough'.

**ROLE 2: 'Audit Practice Partner'**
- As soon as the user types 'end walkthrough', you will immediately switch to this role.
- Your purpose is to provide a complete debrief of the user's performance.
- To create this debrief, you will analyze the entire conversation and evaluate the user's questions against the professional standards documents attached to this session.
- Your feedback must be structured and cover:
    1.  **Strengths:** What questions were effective and why.
    2.  **Critical Findings:** Did the user successfully identify the control gaps or weaknesses present in the process narrative? Explain the weakness they found.
    3.  **Missed Opportunities:** What key questions did they fail to ask? What risks might have been missed?
    4.  **Constructive Advice:** Provide specific advice for improvement, citing principles from the professional standards.
"""


def run_conversation():
    """Main function to set up and run the agent conversation."""
    selected_scenario = choose_scenario()
    system_prompt = create_dynamic_system_prompt(selected_scenario)

    # Combine all file IDs needed for this session's knowledge base
    all_file_ids = [selected_scenario['process_document_id']] + selected_scenario['standards_ids']

    print("\nSetting up your practice session... This may take a moment.")

    try:
        # Create a Vector Store containing all the documents for this session
        vector_store = client.beta.vector_stores.create(
            name=f"Vector Store - {selected_scenario['name']}",
            file_ids=all_file_ids
        )

        # Create the Assistant with the dynamic prompt and tools
        assistant = client.beta.assistants.create(
            name=f"Audit Simulator - {selected_scenario['name']}",
            instructions=system_prompt,
            model="gpt-4o",
            tools=[{"type": "file_search"}]
        )

        # Create a Thread (the conversation) and link the Vector Store to it
        thread = client.beta.threads.create(
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}}
        )

    except openai.APIError as e:
        print(f"An error occurred with the OpenAI API: {e}")
        print("Please check your File IDs in the configuration and ensure they are correct.")
        return

    print("\n--- Session Started ---")
    print(f"You are now speaking with {selected_scenario['persona_name']}. Type 'quit' at any time to exit.")

    while True:
        user_message = input("\nYour question: ")
        if user_message.lower() == 'quit':
            print("Exiting session.")
            # Clean up created resources
            client.beta.assistants.delete(assistant.id)
            client.beta.vector_stores.delete(vector_store.id)
            client.beta.threads.delete(thread.id)
            print("Cleanup complete.")
            break

        # Add the user's message to the thread
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        # Run the Assistant and poll for completion
        try:
            run = client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=assistant.id,
            )

            # Retrieve and display the Assistant's response
            if run.status == 'completed':
                messages = client.beta.threads.messages.list(thread_id=thread.id)
                # The latest message is from the assistant at index 0
                response = messages.data[0].content[0].text.value
                print(f"\nResponse: {response}")
            else:
                print(f"Run ended with status: {run.status}")
                print(f"Details: {run.last_error}")

            if 'end walkthrough' in user_message.lower():
                print("\n--- Debrief Mode Activated ---")
                print("You are now speaking with the Audit Practice Partner. Ask for your debrief.")

        except openai.APIError as e:
            print(f"An error occurred during the run: {e}")
            break


if __name__ == "__main__":
    run_conversation()
