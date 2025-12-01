print("importing libraries...")
import json
import tkinter as tk
from tkinter import filedialog

from dotenv import load_dotenv

from pid_extractor import PIDExtractor


def select_folder():
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    folder_path = filedialog.askdirectory(title="Select a Folder")
    return folder_path


def main(doc_dir: str, equip_lists_path: str):
    """Loop through PDFs in a directory and persist extracted tags."""
    extractor = PIDExtractor()
    equip_lists = extractor.process_directory(doc_dir)
    with open(equip_lists_path, "w", encoding="utf-8") as handle:
        json.dump(equip_lists, handle, indent=4)

if __name__ == "__main__":
    # Load environment variables from .env file
    print("loading environment variables...")
    load_dotenv() # Load environment variables from .env file

    # Define the paths for the input Excel file and output JSONL file

    # doc_dir = select_folder()
    doc_dir = "./docs/Newton"  # equipment_data.xlsx"
    equip_lists_path = "equipment_lists_pascha.json"
    # get the system prompt and examples from environment variables
    print("reading instructions and examples...")

    print("creating openai client...")
    main(doc_dir, equip_lists_path)
    print("Script completed successfully.")
