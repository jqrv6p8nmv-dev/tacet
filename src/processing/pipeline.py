"""
Text post-processing pipeline.

Orchestrates: rule-based cleanup → LLM polish → custom dictionary.
"""
import logging
from typing import Optional

from .cleanup import quick_clean
from .context import get_active_app_bundle_id, get_active_app_name, get_llm_context_hint
from .dictionary import CustomDictionary
from .llm_polish import is_ollama_available, polish_text

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """
    Runs the full post-processing pipeline on raw transcription text.

    Steps:
      1. Rule-based cleanup (filler removal, self-correction, basic punctuation)
      2. LLM polish via Ollama (if enabled and available)
      3. Custom dictionary substitutions
    """

    def __init__(
        self,
        remove_fillers: bool = True,
        handle_corrections: bool = True,
        llm_cleanup: bool = True,
        ollama_model: str = "llama3.2:3b",
        ollama_url: str = "http://localhost:11434",
        custom_dictionary: Optional[CustomDictionary] = None,
    ):
        self.remove_fillers = remove_fillers
        self.handle_corrections = handle_corrections
        self.llm_cleanup = llm_cleanup
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self.dictionary = custom_dictionary or CustomDictionary()

    def process(self, raw_text: str) -> str:
        """
        Run the full pipeline on `raw_text`.

        Returns the cleaned, formatted text ready for insertion.
        """
        if not raw_text or not raw_text.strip():
            return raw_text

        logger.info(f"Processing: {raw_text!r}")

        # Step 1: Rule-based cleanup (always runs — fast and reliable)
        text = quick_clean(
            raw_text,
            remove_fillers_=self.remove_fillers,
            handle_corrections=self.handle_corrections,
        )

        # Step 2: LLM polish (if enabled and Ollama is reachable)
        if self.llm_cleanup and is_ollama_available(self.ollama_url):
            bundle_id = get_active_app_bundle_id()
            app_name = get_active_app_name()
            context_hint = get_llm_context_hint(bundle_id, app_name)

            polished = polish_text(
                text,
                ollama_model=self.ollama_model,
                ollama_url=self.ollama_url,
                context_app=context_hint,
                timeout=5.0,
            )
            if polished:
                text = polished
            else:
                logger.info("LLM polish failed — using rule-based output only")
        elif self.llm_cleanup:
            logger.info("Ollama not available — using rule-based output only")

        # Step 3: Custom dictionary substitutions
        text = self.dictionary.apply(text)

        logger.info(f"Result: {text!r}")
        return text

    def reload_dictionary(self) -> None:
        """Reload the custom dictionary from disk."""
        self.dictionary.load()
