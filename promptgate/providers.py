from __future__ import annotations
import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from promptgate.config import Config


class LLMResponse:
    def __init__(
        self,
        text: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        model: str = "",
        raw_response: Optional[Any] = None
    ):
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.latency_ms = latency_ms
        self.cost_usd = cost_usd
        self.model = model
        self.raw_response = raw_response


class BaseProvider(ABC):
    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        pass


class MockProvider(BaseProvider):
    """
    High-fidelity offline provider for local evaluation, unit testing, and CI runs
    without requiring API keys. Simulates outputs realistically based on prompt directives.
    """

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "mock-test-model",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        start_time = time.time()
        sys_lower = system_prompt.lower()
        usr_lower = user_prompt.lower()

        # Judge evaluation prompt detection
        if "you are an expert impartial llm judge" in sys_lower or "evaluation rubric" in usr_lower or "pairwise" in sys_lower:
            output_text = self._mock_judge(user_prompt)
        elif "financial document" in sys_lower or ("invoice" in sys_lower and "extract" in sys_lower):
            output_text = self._mock_invoice(user_prompt, system_prompt)
        elif "triage agent" in sys_lower or "summarize" in sys_lower:
            output_text = self._mock_summarize(user_prompt)
        elif "customer support" in sys_lower or "support reply" in sys_lower or "busy tier-1" in sys_lower:
            output_text = self._mock_reply(user_prompt, system_prompt)
        else:
            output_text = "Standard response generated for testing."

        latency_ms = (time.time() - start_time) * 1000 + 45.0  # realistic simulated latency
        prompt_tokens = len(system_prompt + user_prompt) // 4
        completion_tokens = len(output_text) // 4
        cost = (prompt_tokens / 1000.0) * 0.000075 + (completion_tokens / 1000.0) * 0.0003

        return LLMResponse(
            text=output_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            model=model
        )

    def _mock_invoice(self, user_prompt: str, system_prompt: str) -> str:
        # Check if this is the deliberate regression prompt that breaks schema
        if "v2_broke_schema" in system_prompt or "format it nicely inside a markdown code block" in system_prompt:
            return (
                "Here is the extracted invoice data:\n\n```json\n"
                "{\n  \"inv_num\": \"INV-BROKEN\",\n  \"total\": \"$1,420.00\"\n}\n```\nHope that helps!"
            )
        
        # Parse fields from prompt if possible
        inv_match = re.search(r"INV-\d+", user_prompt, re.IGNORECASE)
        inv_num = inv_match.group(0) if inv_match else "INV-2024-001"
        
        total_match = re.search(r"\$([0-9,]+\.[0-9]{2})", user_prompt)
        total = float(total_match.group(1).replace(",", "")) if total_match else 249.99
        
        vendor_match = re.search(r"(Acme [A-Za-z]+|TechCorp|CloudHost Inc|Stripe|Amazon AWS|OfficeSupplies Co)", user_prompt, re.IGNORECASE)
        vendor = vendor_match.group(0) if vendor_match else "Acme Global Solutions"
        
        data = {
            "invoice_number": inv_num,
            "date": "2024-10-15",
            "vendor": vendor,
            "line_items": [
                {"description": "Platform Subscription (Pro)", "quantity": 1, "amount": total}
            ],
            "total_amount": total,
            "currency": "USD"
        }
        return json.dumps(data, indent=2)

    def _mock_summarize(self, user_prompt: str) -> str:
        sentiment = "frustrated" if any(w in user_prompt.lower() for w in ["terrible", "outrageous", "broken", "angry", "failed"]) else "neutral"
        urgency = "high" if any(w in user_prompt.lower() for w in ["asap", "emergency", "immediately", "down", "critical"]) else "medium"
        data = {
            "ticket_summary": "Customer is reporting an issue with recent billing and product access.",
            "core_issue": "Billing / access interruption",
            "sentiment": sentiment,
            "urgency": urgency,
            "recommended_action": "Verify subscription state in Stripe and send reassurance email."
        }
        return json.dumps(data, indent=2)

    def _mock_reply(self, user_prompt: str, system_prompt: str) -> str:
        # Check if this is the deliberate regression: broke policy (promises refund)
        if "v2_broke_policy" in system_prompt or "unconditional refund" in system_prompt:
            return (
                "Hi there, I am so sorry for the inconvenience! I have gone ahead and promised you a full "
                "cash refund of $250.00 right away, and I guarantee our engineering team will personally fix "
                "this within an hour. Let me know if you need anything else!"
            )
        
        # Check if this is deliberate regression: rude tone
        if "v2_rude_tone" in system_prompt or "terse" in system_prompt:
            return "Read our docs. Your ticket does not qualify. Nothing we can do."

        # Production baseline or safe refinement
        customer_name_match = re.search(r"Customer Name:\s*([A-Za-z]+)", user_prompt)
        customer_name = customer_name_match.group(1) if customer_name_match else "there"
        
        return (
            f"Hello {customer_name},\n\n"
            "Thank you for contacting our support team. I understand how frustrating it is when a service "
            "interruption impacts your workflow. Our technical team is actively investigating the incident, "
            "and we expect full resolution shortly.\n\n"
            "Regarding your billing inquiry, our policy requires account verification before processing credits. "
            "I have forwarded your request to our billing specialist who will follow up within one business day.\n\n"
            "Best regards,\nCustomer Support Team"
        )

    def _mock_judge(self, user_prompt: str) -> str:
        lower_prompt = user_prompt.lower()
        
        # Level 1: Rude, aggressive, dismissive, or severe policy breach
        if "read our docs" in lower_prompt or "stop spamming" in lower_prompt or "don't care" in lower_prompt:
            return json.dumps({
                "score": 1,
                "justification": "The response is rude, dismissive, lacks empathy, and fails to support the user."
            })
        
        if "promised you a full cash refund" in lower_prompt or "unconditional refund" in lower_prompt or "i will personally guarantee" in lower_prompt:
            return json.dumps({
                "score": 1,
                "justification": "Severe policy violation: promised an unauthorized refund and gave unapproved SLA guarantees."
            })
        
        # Level 2: Cold, terse, minimal, robotic
        if "the export button has a bug" in lower_prompt or "wait for an update" in lower_prompt:
            return json.dumps({
                "score": 2,
                "justification": "Robotic and terse response; provides no workaround, timeline, or acknowledgment."
            })
        
        if "```json" in lower_prompt and "inv_num" in lower_prompt:
            return json.dumps({
                "score": 2,
                "justification": "Failed strict formatting instructions: wrapped output in markdown code fence instead of pure raw JSON."
            })

        # Level 3: Standard, neutral business, factual
        if "to invite team members go to settings" in lower_prompt:
            return json.dumps({
                "score": 3,
                "justification": "Accurate response that answers the core question, but lacks extra helpful details or links."
            })

        # Level 5: Outstanding de-escalation, high emotional intelligence
        if "i completely understand how critical this server access is" in lower_prompt or "personally escalated your server recovery" in lower_prompt:
            return json.dumps({
                "score": 5,
                "justification": "Exceptional empathy, proactive de-escalation, clear next steps, and polished professionalism."
            })

        # Level 4: Standard high quality empathetic response
        if "i am very sorry for the disruption" in lower_prompt or "thank you for contacting" in lower_prompt:
            return json.dumps({
                "score": 4,
                "justification": "Empathetic, reassuring, polite, and fully policy-compliant without making false guarantees."
            })

        # Default high quality
        return json.dumps({
            "score": 5,
            "justification": "Response is polite, highly faithful to instructions, respects policy boundaries, and addresses customer needs clearly."
        })


class GeminiProvider(BaseProvider):
    """Google Gemini provider via official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or set in environment.")
        from google import genai
        self.client = genai.Client(api_key=self.api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        from google.genai import types
        start = time.time()
        
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if response_schema:
            config.response_mime_type = "application/json"
            config.response_schema = response_schema

        response = self.client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config
        )
        
        latency = (time.time() - start) * 1000
        text = response.text or ""
        
        prompt_tokens = 0
        completion_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0

        rates = Config.MODEL_COSTS.get(model, Config.MODEL_COSTS["gemini-2.5-flash"])
        cost = (prompt_tokens / 1000.0) * rates["prompt"] + (completion_tokens / 1000.0) * rates["completion"]

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
            cost_usd=cost,
            model=model,
            raw_response=response
        )


class OpenAIProvider(BaseProvider):
    """OpenAI provider via openai SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be provided or set in environment.")
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_schema: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        start = time.time()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_schema:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        latency = (time.time() - start) * 1000
        choice = response.choices[0]
        text = choice.message.content or ""
        
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        rates = Config.MODEL_COSTS.get(model, Config.MODEL_COSTS["gpt-4o-mini"])
        cost = (prompt_tokens / 1000.0) * rates["prompt"] + (completion_tokens / 1000.0) * rates["completion"]

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
            cost_usd=cost,
            model=model,
            raw_response=response
        )


def get_provider(model_name: str, force_mock: bool = False) -> BaseProvider:
    """Returns the appropriate provider based on model name and environment."""
    if force_mock or os.getenv("PROMPTGATE_MOCK_MODE", "0") == "1":
        return MockProvider()

    if "gemini" in model_name.lower():
        if Config.GEMINI_API_KEY:
            try:
                return GeminiProvider()
            except Exception:
                pass
        return MockProvider()

    if "gpt" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower():
        if Config.OPENAI_API_KEY:
            try:
                return OpenAIProvider()
            except Exception:
                pass
        return MockProvider()

    return MockProvider()
