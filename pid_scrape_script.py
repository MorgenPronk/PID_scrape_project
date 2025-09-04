print("importing libraries...")
from openai import AzureOpenAI
import pandas as pd
import json
from dotenv import load_dotenv
import os
from log_error import log_error
import fitz  # PyMuPDF
import traceback
import re
import ast
from tqdm import tqdm
import tkinter as tk
from tkinter import filedialog

def select_folder():
    root = tk.Tk()
    root.withdraw() # Hide the main window
    folder_path = filedialog.askdirectory(title="Select a Folder")
    return folder_path

def clean_model_output(output):
    # Remove any leading/trailing whitespace
    output = output.strip()
    # Remove any triple backticks and language hints
    output = re.sub(r"```(?:python)?\s*", "", output)  # Remove ``` or ```python
    output = re.sub(r"\s*```$", "", output)  # Remove closing ```
    return output

def generate_with_retry(model_input, system_prompt, examples, max_retries=4):
    # First attempt to generate hierarchy
    tries = 0
    model_output = None

    while tries < max_retries:
        try:
            # Build the prompt
            if tries == 0:
                prompt = model_input
            else:
                prompt = (
                    f"The previous output, {model_output}, was not a valid python list of equipment tags. "
                    f"Please provide a valid python list of equipment tags only, in the format: ['TAG1', 'TAG2', ...]. "
                    f"Do not include any additional text or explanation. "
                    f"Here is the original input again:\n{model_input}\n"
                )

            # call the model
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": f"{system_prompt} \n\n{examples}"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
            model_output = response.choices[0].message.content
            cleaned_output = clean_model_output(model_output)
            # print(f"Model output try{tries + 1}:\n{model_output}")

            # Try to parse the output
            equip_list = ast.literal_eval(cleaned_output)
            if isinstance(equip_list, list):
                # print("is a valid list! Exiting retry loop.")
                return equip_list
            else:
                # print(f"Output is not a valid list, got type {type(equip_list)}")
                raise ValueError("Output is not a valid list")
            
        except (json.JSONDecodeError, ValueError) as e:
            tries += 1
            continue

        except Exception as e:
            error_message = f"Error generating and validating equipment list: {e}\n"
            # print(error_message)
            log_error(error_message)
            break

    # If we reach here, all retires failed
    error_message = (f"Failed to generate valid equipment list after {max_retries} tries. Last output:\n{model_output}\n"
    f"Last model ouptut:\n{model_output}\n")
    # print(error_message)
    log_error(error_message)
    return None

def pid_scrape(file_path):
    """
    Convert a PID file to a SC rate file.
    """
    # Get all of the text from the PID file. NO OCR is performed, so the file must be text-based currently.
    pid_content = fitz.open(file_path)
    full_text = ""
    for page in pid_content:
        full_text += page.get_text()
    return full_text
    
def loop_files(root_dir):
    """
    Recursively Loop through all of the files in the directory and it's subdirectories.
    """
    # Get the system prompt from a text file
    with open("system_prompt.txt", "r") as file:
        system_prompt = file.read()

    with open("examples.txt", "r") as file:
        examples = file.read()

    # collect all files first
    pdf_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for file in filenames:
            if file.endswith(".pdf"):
                pdf_files.append(os.path.join(dirpath, file))

    equip_lists = {}
    for pid_file_path in tqdm(pdf_files, desc="Processing PDF files", unit="file"):
                try:
                    base_name = os.path.splitext(os.path.basename(pid_file_path))[0]
                    # get the file content
                    doc_content = pid_scrape(pid_file_path)
                    # print(f"--DOC_CONTENT--\n{doc_content}\n--END-DOC-CONTENT--")
                    # generate the list of equipment tags
                    equip_list = generate_with_retry(doc_content, system_prompt, examples) #model_input, system_prompt, examples, max_retries=4
                    # Log if the equip_list is generated
                    log_error(f"Processed file {file}, generated {len(equip_list) if equip_list else 0} tags.\n")
                    # print(f"Generated equipment list for {base_name}: \n{equip_list}")
                    equip_lists[pid_file_path] = equip_list
                except Exception as e:
                    error_message = f"Error processing file {file}: \n{traceback.format_exc()}\n"
                    # print(error_message)
                    log_error(error_message)
    return equip_lists

def main():
    """
    Main function to run the script.
    """
    # Loop through the equipment records and generate hierarchy
    equip_lists = loop_files(doc_dir)
    with open(equip_lists_path, 'w') as f:
        json.dump(equip_lists, f, indent=4)

if __name__ == "__main__":
    # Load environment variables from .env file
    print("loading environment variables...")
    load_dotenv() # Load environment variables from .env file

    # Define the paths for the input Excel file and output JSONL file

    # doc_dir = select_folder()
    doc_dir = "./docs/Newton" #equipment_data.xlsx"
    error_log_path = "error_log.log"
    equip_lists_path = "equipment_lists_pascha.json"
    # get the system prompt and examples from environment variables
    print("reading instructions and examples...")

    # Get the model and endpoint from environment variables
    # The model, api_version, api key, and endpoint_url should be set in the .env file because they are all unique to the model used.
    API_key = os.getenv("API_key")
    endpoint_url = os.getenv("endpoint_url")
    deployment = os.getenv("deployment")
    api_version = os.getenv("api_version")

    print("creating openai client...")
    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint= endpoint_url,
        api_key=API_key,
    )

    main()
    print("Script completed successfully.")
