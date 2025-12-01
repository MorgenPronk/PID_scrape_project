import ast
import os
import re
import traceback
from typing import Dict, Iterable, List, Optional

import fitz  # PyMuPDF
from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

from config_store import load_settings
from log_error import log_error


def clean_model_output(output: str) -> str:
    """Normalize model output before parsing as python literal."""
    normalized = output.strip()
    normalized = re.sub(r"```(?:python)?\s*", "", normalized)  # remove ``` or ```python
    normalized = re.sub(r"\s*```$", "", normalized)  # remove closing ```
    return normalized


def _read_text_file(path: str) -> str:
    if not os.path.exists(path):
        log_error(f"Missing prompt file at {path}")
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class PIDExtractor:
    def __init__(
        self,
        *,
        system_prompt_path: str = "system_prompt.txt",
        examples_path: str = "examples.txt",
        client: Optional[object] = None,
        max_retries: int = 4,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        deployment: Optional[str] = None,
        model: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> None:
        load_dotenv()
        settings = load_settings()

        self.provider = (provider or settings.get("provider") or "azure").lower()
        self.api_key = api_key or settings.get("api_key") or os.getenv("API_key") or os.getenv("OPENAI_API_KEY")
        self.endpoint_url = endpoint_url or settings.get("endpoint_url") or os.getenv("endpoint_url")
        self.deployment = deployment or settings.get("deployment") or os.getenv("deployment")
        self.model = model or settings.get("model") or os.getenv("openai_model") or "gpt-4.1"
        self.api_version = api_version or settings.get("api_version") or os.getenv("api_version")

        self.system_prompt = _read_text_file(system_prompt_path)
        self.examples = _read_text_file(examples_path)
        self.max_retries = max_retries

        self.client = client or self._build_client()

    def _build_client(self):
        if self.provider == "azure":
            missing = [
                name
                for name, value in {
                    "API_key": self.api_key,
                    "endpoint_url": self.endpoint_url,
                    "api_version": self.api_version,
                    "deployment": self.deployment,
                }.items()
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "Missing required Azure OpenAI settings: " + ", ".join(sorted(missing))
                )

            return AzureOpenAI(
                api_version=self.api_version,
                azure_endpoint=self.endpoint_url,
                api_key=self.api_key,
            )

        # Default to OpenAI
        if not self.api_key:
            raise RuntimeError("Missing OpenAI API key")
        return OpenAI(api_key=self.api_key, base_url=self.endpoint_url or None)

    def _generate_with_retry(self, model_input: str) -> Optional[List[str]]:
        tries = 0
        model_output: Optional[str] = None

        while tries < self.max_retries:
            try:
                prompt = model_input if tries == 0 else (
                    f"The previous output, {model_output}, was not a valid python list of equipment tags. "
                    f"Please provide a valid python list of equipment tags only, in the format: ['TAG1', 'TAG2', ...]. "
                    f"Do not include any additional text or explanation. "
                    f"Here is the original input again:\n{model_input}\n"
                )

                response = self.client.chat.completions.create(
                    model=self.deployment if self.provider == "azure" else self.model,
                    messages=[
                        {"role": "system", "content": f"{self.system_prompt} \n\n{self.examples}"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                )

                model_output = response.choices[0].message.content
                cleaned_output = clean_model_output(model_output)
                equip_list = ast.literal_eval(cleaned_output)
                if isinstance(equip_list, list):
                    return equip_list
                raise ValueError("Output is not a valid list")

            except (ValueError, SyntaxError):
                tries += 1
                continue
            except Exception as exc:  # unexpected errors get logged and break
                log_error(f"Error generating and validating equipment list: {exc}\n{traceback.format_exc()}")
                break

        log_error(
            "Failed to generate valid equipment list after "
            f"{self.max_retries} tries. Last output: {model_output}"
        )
        return None

    @staticmethod
    def _pdf_text_from_bytes(file_bytes: bytes) -> str:
        pid_content = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = "".join(page.get_text() for page in pid_content)
        return full_text

    @staticmethod
    def _pdf_text_from_path(file_path: str) -> str:
        pid_content = fitz.open(file_path)
        full_text = "".join(page.get_text() for page in pid_content)
        return full_text

    def extract_from_pdf_bytes(self, file_bytes: bytes, file_name: str = "") -> Optional[List[str]]:
        try:
            doc_content = self._pdf_text_from_bytes(file_bytes)
            return self._generate_with_retry(doc_content)
        except Exception as exc:
            log_error(f"Error processing in-memory file {file_name}: {exc}\n{traceback.format_exc()}")
            return None

    def extract_from_pdf_path(self, file_path: str) -> Optional[List[str]]:
        try:
            doc_content = self._pdf_text_from_path(file_path)
            return self._generate_with_retry(doc_content)
        except Exception as exc:
            log_error(f"Error processing file {file_path}: {exc}\n{traceback.format_exc()}")
            return None

    def process_directory(self, root_dir: str, *, extensions: Iterable[str] = (".pdf",)) -> Dict[str, Optional[List[str]]]:
        results: Dict[str, Optional[List[str]]] = {}
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if not filename.lower().endswith(tuple(ext.lower() for ext in extensions)):
                    continue
                file_path = os.path.join(dirpath, filename)
                tags = self.extract_from_pdf_path(file_path)
                tag_count = len(tags) if tags else 0
                log_error(f"Processed file {file_path}, generated {tag_count} tags.")
                results[file_path] = tags
        return results
