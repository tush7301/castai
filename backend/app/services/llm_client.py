from __future__ import annotations

import anthropic

from app.config import settings


class LLMClient:
    def __init__(self) -> None:
        self.client = (
            anthropic.Anthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )

    def answer(self, system_prompt: str, user_prompt: str) -> str:
        if not self.client:
            return (
                "I cannot call Claude because ANTHROPIC_API_KEY is not configured. "
                "Set it in backend/.env and restart the server."
            )

        try:
            response = self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_blocks = [
                block.text
                for block in response.content
                if getattr(block, "type", "") == "text"
            ]
            return "\n".join(text_blocks).strip()

        except anthropic.RateLimitError:
            return (
                "I cannot answer right now because the Anthropic API rate limit has been reached. "
                "Please try again in a moment."
            )
        except anthropic.APIStatusError as exc:
            return (
                f"The Anthropic API returned an error ({exc.status_code}). "
                "Please try again or contact support."
            )
        except anthropic.APIConnectionError:
            return (
                "I cannot reach the Anthropic API. "
                "Check your internet connection and try again."
            )
