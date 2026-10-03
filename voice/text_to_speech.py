"""Gemini text-to-speech with a provider-friendly function boundary."""

import base64
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

from voice.speech_to_text import SUPPORTED_LANGUAGES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TTS_MODEL = "gemini-3.8-flash-tts"
DEFAULT_TEXT_MODEL = "gemini-3.8-flash"


class TextToSpeechError(RuntimeError):
	"""Raised when recommendation audio cannot be generated."""


def _get_client() -> Any:
	load_dotenv(PROJECT_ROOT / ".env")
	api_key = os.getenv("GEMINI_API_KEY")
	if not api_key:
		raise TextToSpeechError(
			"GEMINI_API_KEY is not set. Add it to Government-Scheme-Agent/.env."
		)
	return genai.Client(api_key=api_key)


def _translate_for_speech(text: str, language: str, client: Any) -> str:
	if language == "English":
		return text

	response = client.models.generate_content(
		model=os.getenv("GEMINI_TEXT_MODEL", DEFAULT_TEXT_MODEL),
		contents=(
			f"Translate the following recommendation faithfully into {language}. "
			"Return only the translation. Do not add, omit, or change facts, "
			"amounts, scheme names, or telephone numbers.\n\n"
			f"{text}"
		),
	)
	translated_text = (response.text or "").strip()
	if not translated_text:
		raise TextToSpeechError("The recommendation could not be translated for audio.")
	return translated_text


def synthesize_speech(
	text: str,
	language: str = "English",
	client: Any | None = None,
	model_name: str | None = None,
) -> bytes:
	"""Return recommendation speech as WAV bytes in the requested language."""
	if not text.strip():
		raise TextToSpeechError("There is no recommendation text to read aloud.")
	if language not in SUPPORTED_LANGUAGES:
		raise ValueError(f"Choose one of the supported languages: {SUPPORTED_LANGUAGES}.")

	try:
		if client is None:
			client = _get_client()
		spoken_text = _translate_for_speech(text, language, client)
		interaction = client.interactions.create(
			model=model_name or os.getenv("GEMINI_TTS_MODEL", DEFAULT_TTS_MODEL),
			input=[
				{
					"type": "user_input",
					"content": [{"type": "text", "text": spoken_text}],
				}
			],
			response_format={"type": "audio", "mime_type": "audio/wav"},
			generation_config={"speech_config": [{"voice": "Kore"}]},
		)
		audio_data = interaction.output_audio.data
		if not audio_data:
			raise TextToSpeechError("Gemini returned no audio data.")
		if isinstance(audio_data, str):
			return base64.b64decode(audio_data)
		return base64.b64decode(audio_data)
	except TextToSpeechError:
		raise
	except Exception as exc:
		raise TextToSpeechError(
			"Speech generation failed. Check the API key, SDK version, connection, and try again."
		) from exc