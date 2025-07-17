What is a Reasoning Model?

Reasoning models are LLMs trained with reinforcement learning to perform reasoning. These models think before they answer, producing a long internal chain of thought before responding to the user.

When combined with tools to access the web, reasoning models are particularly good at research. Their chain‑of‑thought training and reward signals make them better at spotting gaps, cross‑checking sources, and iterating on hypotheses.
Some popular reasoning models include:

    DeepSeek R1,
    o3 and o1
    Phi-4-reasoning.

Getting started with DeepSeek R1

To access DeepSeek R1 we will be using langchain-azure-ai, the official Python package that contains most of Langchain's Azure integrations. This package leverages the Azure AI Inference SDK to give us access to all the models available in Azure AI Foundry using Langchain.
Lab Exercise

    Open the file lab1a_reasoning.py and examine the code in this file.

    In the VS Code terminal run the following command and enter a research topic. For example 'What's the best coffee in Seattle?'☕:

    python lab1a_reasoning.py

Note

🧠✨ Thinking... What do you notice about the answer DeepSeek R1 returns vs what a chat model would typically output?

Reasoning models 'think' and show you how they arrived at the final answer!

Type in exit to leave the program and continue with the next section.
Seperating Thinking from the Final Answer

The output from the model in the previous step contains the models thinking. This output might be helpful for developers but might not always be useful when building an application where users only expect the final output.

Tip

Many reasoning models put their thought process in thinking tags that look like this <think> </think>.

In order to seperate the models thinking from it's final answer we can create helper function in Python to seperate the thinking from the final output. The function would look like this:

def seperate_thinking_from_final_output(text: str):
    """
    Extract the content between <think> and </think> tags and remove them from the text.
    """
    thoughts = ""
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>")
        # Extract the content between tags (excluding the tags themselves)
        thoughts += text[start + len("<think>"):end].strip() + "\n\n"
        # Remove the tags and their content from the original text
        text = text[:start] + text[end + len("</think>"):]
    return thoughts.strip(), text.strip()

Lab Exercise

    Open the stream_llm_response.py file and examine the code in this file.

    It contains a slightly updated version of this helper function in the stream_thinking_and_answer function. This helper function will be imported in all our python files going forward. It also contains some code that uses the Python package rich for prettier display in the terminal.

    To test that this code works we can run the lab1b_reasoning.py script which imports the helper function. Run the following command in the terminal to do so:

    python lab1b_reasoning.py

Updating the System Prompt

The final output is returned as bullet points. This format can be specified in the models system prompt that tells the LLM how to behave. You do not need to add a system prompt but these can be useful for improving the format and contextual relevance of the models final response.

The current system prompt in lab1b_reasoning.py is:

SYSTEM_PROMPT = """
You are a research assistant that thinks carefully about questions before answering.

When you receive a research question, first think about the problem step-by-step.

After thinking, provide your final answer in bullet points.
Make sure to include all the important details in your answer.

Lab Exercise

    Update the system prompt in lab1b_reasoning.py to change the final output format. For example ask the model to return the answer as a table or in a Q&A format.

    Rerun the following command in the terminal to test your updates:

    python lab1b_reasoning.py


