import vertexai
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig, HarmCategory, HarmBlockThreshold, FinishReason
import json
import os
import re


class MaxTokensError(Exception):
    """Raised when model response is truncated due to hitting the max token limit."""
    pass


class VertexAIService:
    """Service for interacting with Vertex AI (Gemini)"""
    
    def __init__(self, project_id: str, location: str, model_name: str = "gemini-1.5-pro"):
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    # ── shared safety settings for medical content ──────────────────────
    
    @staticmethod
    def _get_safety_settings() -> dict:
        """Return permissive safety settings suitable for medical content."""
        return {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }

    # ── JSON extraction helper ──────────────────────────────────────────
    
    @staticmethod
    def _extract_json_from_response(text: str) -> str:
        """
        Extract JSON content from response text, handling markdown code blocks.
        
        Args:
            text: Raw response text that may contain markdown.
            
        Returns:
            Clean JSON string.
        """
        text = text.strip()
        
        # Try to extract JSON from markdown code blocks
        # Pattern: ```json\n...\n``` or ```\n...\n```
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        # If no code block, return as-is
        return text

    # ── common generate-and-parse pipeline ──────────────────────────────
    
    def _generate_json_response(
        self,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        context: str,
    ):
        """
        Call the model, validate the response, extract JSON and return the
        parsed Python object.

        Args:
            prompt:            The full prompt to send.
            temperature:       Sampling temperature.
            max_output_tokens: Token budget for the response.
            context:           Human-readable label used in error messages
                               (e.g. "question generation", "SOAP processing").

        Returns:
            Parsed JSON (dict or list).

        Raises:
            MaxTokensError: If the response was truncated by the token limit.
            Exception:      For any other generation or parsing failure.
        """
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                safety_settings=self._get_safety_settings(),
            )

            # ── validate candidates ──────────────────────────────────
            if not response.candidates:
                raise Exception("Model response was blocked or had no candidates")

            candidate = response.candidates[0]

            # ── check finish reason ──────────────────────────────────
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason != FinishReason.STOP:
                finish_reason_name = (
                    candidate.finish_reason.name
                    if hasattr(candidate.finish_reason, 'name')
                    else str(candidate.finish_reason)
                )

                # Build optional safety info string
                safety_info = ""
                if hasattr(candidate, 'safety_ratings'):
                    safety_info = "\nSafety Ratings: " + str([
                        f"{rating.category.name}: {rating.probability.name}"
                        for rating in candidate.safety_ratings
                    ])

                if candidate.finish_reason == FinishReason.MAX_TOKENS:
                    raise MaxTokensError(
                        f"Hit max tokens during {context}. "
                        f"Finish reason: {finish_reason_name}{safety_info}"
                    )

                # For SAFETY, RECITATION, OTHER, etc.
                partial_preview = ""
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    partial_preview = f"\nPartial content: {candidate.content.parts[0].text[:200]}"

                raise Exception(
                    f"{context} incomplete. "
                    f"Finish reason: {finish_reason_name}{safety_info}{partial_preview}"
                )

            # ── extract text ─────────────────────────────────────────
            if not response or not hasattr(response, 'text') or not response.text:
                raise Exception("Model returned empty response")

            json_text = self._extract_json_from_response(response.text)
            if not json_text:
                raise Exception("No JSON content found in response")

            return json.loads(json_text)

        except (MaxTokensError, json.JSONDecodeError):
            raise  # let callers handle these specifically
        except Exception as e:
            raise Exception(f"Failed during {context}: {str(e)}")

    @staticmethod
    def _create_summary_prompt(input_text: str, schema_version: str) -> str:
        """
        Build the summary prompt by loading the prompt template and JSON schema
        for the given schema version, then substituting the ``{{input}}`` and
        ``{{schema}}`` placeholders.

        Args:
            input_text:     The raw input text (transcript / notes / combined).
            schema_version: Version string (e.g. "1.2", "1.3") that matches a
                            folder under ``summarySchema/``.

        Returns:
            Fully assembled prompt string ready to send to the model.

        Raises:
            FileNotFoundError: If the schema version folder or files don't exist.
        """
        # Resolve paths relative to *this* file  (utils/ → ../summarySchema/<ver>/)
        base_dir = os.path.join(
            os.path.dirname(__file__), '..', 'summarySchema', schema_version
        )
        prompt_path = os.path.join(base_dir, 'prompt.txt')
        schema_path = os.path.join(base_dir, 'schema.json')

        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(
                f"Prompt template not found for schema version {schema_version}: {prompt_path}"
            )
        if not os.path.isfile(schema_path):
            raise FileNotFoundError(
                f"Schema file not found for schema version {schema_version}: {schema_path}"
            )

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_content = f.read()

        # Substitute placeholders using .replace() so that literal { } in the
        # schema JSON and prompt text are preserved (no f-string escaping needed).
        prompt = (
            prompt_template
            .replace('{{input}}', input_text)
            .replace('{{schema}}', schema_content)
        )

        return prompt

    # ── public methods ──────────────────────────────────────────────────
    
    def generate_questions(self, transcript: str) -> list:
        """
        Generate 0-3 potential questions a patient could ask based on the transcript.
        
        Args:
            transcript: The current transcript of the medical conversation.
            
        Returns:
            List of question strings.
        """
        
        prompt = f"""You are a medical assistant helping patients understand their doctor's appointment.

You will be given a raw transcript of a medical appointment between a doctor and patient. Treat the doctor's words as the ground truth for all medical information.

Based on the transcript, generate 0-3 relevant questions that the patient might want to ask their doctor for clarification.

Rules:
- Each question MUST be directly traceable to a specific statement made in the transcript. If you cannot point to a specific sentence in the transcript that the question derives from, do not include it.
- DO NOT hallucinate, infer, or extrapolate beyond what was explicitly said.
- The objective is only to find points from the transcript that need further clarification.
- If there are no such clarifying questions, return an empty JSON array: []

Transcript:
{transcript}

Return ONLY a JSON array of question strings, nothing else. Format: ["question 1", "question 2", "question 3"] or [] if none.
"""
        
        try:
            questions = self._generate_json_response(
                prompt=prompt,
                temperature=0.2,
                max_output_tokens=2048,
                context="question generation",
            )

            # Ensure we have a list and limit to 3 questions
            if isinstance(questions, list):
                return questions[:3]
            return []

        except MaxTokensError:
            print("Warning: Hit max tokens during question generation. Returning empty list.")
            return []
        except json.JSONDecodeError as e:
            raise Exception(
                f"Failed to parse JSON response during question generation. Error: {str(e)}"
            )
        except Exception as e:
            raise Exception(f"Failed to generate questions: {str(e)}")
    
    def process_transcript_to_soap(self, input_text: str, schema_version: str = "1.3") -> dict:
        """
        Process raw input into a structured medical summary using the prompt
        template and JSON schema defined by *schema_version*.

        Args:
            input_text:      The raw, unprocessed input (transcript / notes / combined).
            schema_version:  Schema version folder to load (default ``"1.3"``).

        Returns:
            Dictionary with the structured summary.
        """

        prompt = self._create_summary_prompt(input_text, schema_version)

        try:
            soap_notes = self._generate_json_response(
                prompt=prompt,
                temperature=0.3,
                max_output_tokens=65000,
                context="SOAP processing",
            )
            return soap_notes

        except MaxTokensError:
            raise Exception(
                "Transcript too long for SOAP processing. "
                "Please try with a shorter conversation or increase token limits."
            )
        except json.JSONDecodeError as e:
            raise Exception(
                f"Failed to parse JSON response during SOAP processing. Error: {str(e)}"
            )
        except Exception as e:
            raise Exception(f"Failed to process transcript to SOAP: {str(e)}")
