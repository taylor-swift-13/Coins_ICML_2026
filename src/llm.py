from abc import ABC, abstractmethod

import openai

from config import LLMConfig


class LLMError(RuntimeError):
    """An API failure; never a proof or specification rejection."""


class BaseChatModel(ABC):
    def __init__(self, config: LLMConfig):
        self.config = config
        self.messages = [{'role': 'system', 'content': 'You are a helpful assistant.'}]

    @abstractmethod
    def generate_response(self, user_input: str) -> str:
        raise NotImplementedError


class OpenAILLM(BaseChatModel):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.api_key:
            raise LLMError('COINS_API_KEY is not set')
        try:
            self.client = openai.OpenAI(base_url=config.base_url, api_key=config.api_key, timeout=300.0)
        except Exception as exc:
            raise LLMError('Cannot initialize the LLM client') from exc

    def generate_response(self, user_input: str) -> str:
        self.messages.append({'role': 'user', 'content': user_input})
        try:
            response = self.client.chat.completions.create(
                model=self.config.api_model, messages=self.messages,
                temperature=self.config.api_temperature)
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise LLMError('The API returned no text')
        except Exception as exc:
            self.messages.pop()
            # Avoid including endpoint credentials or arbitrary server bodies in logs.
            raise LLMError(f'LLM request failed ({type(exc).__name__})') from exc
        self.messages.append({'role': 'assistant', 'content': content})
        return content


class Chatbot:
    def __init__(self, config: LLMConfig):
        self.config = config
        if not config.use_api_model:
            raise LLMError('Local model inference is not implemented')
        self.llm_instance = OpenAILLM(config)

    def chat(self, user_input: str) -> str:
        return self.llm_instance.generate_response(user_input)

    def new_chat(self, user_input: str) -> str:
        self.llm_instance = OpenAILLM(self.config)
        return self.llm_instance.generate_response(user_input)
