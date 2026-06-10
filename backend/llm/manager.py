"""
backend/llm/manager.py

Enterprise LLM Manager — Full fallback chain.
Tries providers in order until one succeeds.

Priority chain:
  1. Groq          → FREE, 14,400 req/day, llama-3.1-8b-instant
  2. OpenRouter    → FREE tier, 50 req/day backup
  3. OpenAI        → Paid, highest quality
  4. Ollama        → Self-hosted, unlimited (local/on-prem only)
  5. Template      → Always works, no API needed

Render Deploy: Add GROQ_API_KEY env var → cost = ₹0

Usage:
    from backend.llm import llm_manager
    text = await llm_manager.generate(prompt, context="incident_report")
"""
from __future__ import annotations

import os
import time
from typing import Optional
from loguru import logger

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


# ── Template responses (zero-dependency fallback) ─────────────

_TEMPLATES = {
    "incident_report": (
        "SAFETY INCIDENT REPORT — Auto Generated\n\n"
        "INCIDENT SUMMARY:\n"
        "A PPE violation was detected by the AI vision system. The worker was "
        "observed without required personal protective equipment in a designated "
        "safety zone. Immediate corrective action is required.\n\n"
        "ROOT CAUSE ANALYSIS:\n"
        "Non-compliance with site safety protocols. Worker may not have been "
        "aware of PPE requirements for this zone, or equipment was unavailable.\n\n"
        "CORRECTIVE ACTIONS:\n"
        "1. Immediate verbal warning and provision of required PPE\n"
        "2. Safety briefing for the concerned worker and team\n"
        "3. Review PPE availability at zone entry points\n"
        "4. Update safety induction records\n\n"
        "COMPLIANCE REFERENCE:\n"
        "Factories Act 1948 Section 7A | IS 4770 | OSHA 1910.132\n\n"
        "[Note: Full AI narrative requires GROQ_API_KEY — get free at console.groq.com]"
    ),
    "severity_score": "7",
    "safety_advice": (
        "Ensure all workers in this zone wear required PPE at all times. "
        "PPE compliance is mandatory under the Factories Act 1948. "
        "Non-compliance may result in serious injury or regulatory penalties."
    ),
    "chat": (
        "I'm your safety assistant. Based on standard safety protocols: "
        "Always wear required PPE in designated zones. For site-specific guidance, "
        "please configure the LLM service (add GROQ_API_KEY to environment)."
    ),
}


class LLMManager:
    """
    Enterprise LLM Manager with full provider fallback chain.
    Thread-safe, async-first, zero mandatory dependencies.
    """

    def __init__(self):
        self._groq_key = os.getenv("GROQ_API_KEY", "")
        self._groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self._openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        self._openrouter_model = os.getenv(
            "OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct:free"
        )
        self._openai_key = os.getenv("OPENAI_API_KEY", "")
        self._openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = os.getenv("OLLAMA_MODEL", "llama3")

        # Log which providers are available
        available = []
        if self._groq_key:       available.append("groq ✅")
        if self._openrouter_key: available.append("openrouter ✅")
        if self._openai_key:     available.append("openai ✅")
        available.append("ollama (local)")
        available.append("template (always)")
        logger.info("LLM Manager initialized | providers: {}", " → ".join(available))

    # ── Public API ────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        context: str = "general",
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        """
        Generate text using the best available LLM provider.
        Falls back automatically if a provider fails.

        Args:
            prompt: The user/system prompt
            context: Used for template selection if all LLMs fail
            max_tokens: Max output tokens
            temperature: 0.0=deterministic, 1.0=creative

        Returns:
            Generated text string (never raises)
        """
        if not _HTTPX_OK:
            logger.warning("httpx not installed — using template fallback")
            return self._template(context)

        start = time.time()

        # Try each provider in order
        providers = [
            ("groq",        self._call_groq),
            ("openrouter",  self._call_openrouter),
            ("openai",      self._call_openai),
            ("ollama",      self._call_ollama),
        ]

        for name, fn in providers:
            try:
                result = await fn(prompt, max_tokens, temperature)
                if result and len(result.strip()) > 10:
                    elapsed = time.time() - start
                    logger.info(
                        "LLM response | provider={} | tokens≈{} | time={:.2f}s",
                        name, len(result.split()), elapsed
                    )
                    return result.strip()
            except Exception as exc:
                logger.warning("LLM provider {} failed: {}", name, str(exc)[:100])
                continue

        # All providers failed — use template
        logger.warning("All LLM providers failed — using template for context={}", context)
        return self._template(context)

    async def score_severity(self, violation_class: str, context: str = "") -> int:
        """
        Score severity 1-10 for a violation.
        Returns integer, guaranteed.
        """
        prompt = (
            f"Rate the safety severity of this PPE violation on a scale of 1-10 "
            f"(1=minor, 10=life-threatening).\n"
            f"Violation: {violation_class}\n"
            f"Context: {context}\n"
            f"Reply with ONLY a single integer between 1 and 10. No explanation."
        )
        result = await self.generate(prompt, context="severity_score", max_tokens=5)
        # Extract first integer from response
        import re
        nums = re.findall(r'\b([1-9]|10)\b', result)
        return int(nums[0]) if nums else 5

    async def generate_incident_narrative(
        self,
        violation_class: str,
        zone_id: str,
        worker_id: str,
        confidence: float,
        industry_type: str = "manufacturing",
        compliance_standard: str = "OSHA 1910.132",
    ) -> dict:
        """
        Generate a complete incident report narrative.
        Returns dict with summary, root_cause, corrective_actions, osha_reference.
        """
        prompt = f"""You are a safety officer writing an official incident report.

Incident Details:
- Violation: {violation_class}
- Zone: {zone_id}
- Worker ID: {worker_id}
- Detection Confidence: {confidence:.0%}
- Industry: {industry_type}
- Applicable Standard: {compliance_standard}

Write a professional incident report with these EXACT sections:
SUMMARY: (2 sentences — what happened)
ROOT CAUSE: (1-2 sentences — why it happened)
CORRECTIVE ACTIONS: (3 bullet points starting with numbers)
OSHA REFERENCE: (cite the specific regulation)

Be concise and professional."""

        raw = await self.generate(prompt, context="incident_report", max_tokens=400)

        # Parse sections from response
        import re
        sections = {
            "incident_summary": self._extract_section(raw, "SUMMARY", "ROOT CAUSE"),
            "root_cause_analysis": self._extract_section(raw, "ROOT CAUSE", "CORRECTIVE"),
            "corrective_actions": self._extract_section(raw, "CORRECTIVE ACTIONS", "OSHA"),
            "osha_reference": self._extract_section(raw, "OSHA REFERENCE", None),
            "narrative": raw,
        }

        # Fallback for any empty section
        if not sections["incident_summary"]:
            sections["incident_summary"] = (
                f"Worker {worker_id} detected without {violation_class} in {zone_id}. "
                f"Immediate corrective action required."
            )
        if not sections["osha_reference"]:
            sections["osha_reference"] = compliance_standard

        return sections

    async def answer_safety_question(self, question: str, context_docs: str = "") -> str:
        """Answer a safety Q&A question using RAG context."""
        prompt = (
            f"You are a safety expert. Answer this safety question concisely.\n\n"
            f"Context documents:\n{context_docs[:2000]}\n\n"
            f"Question: {question}\n\n"
            f"Answer in 2-3 sentences, citing relevant safety standards if applicable."
        )
        return await self.generate(prompt, context="chat", max_tokens=300)

    # ── Provider implementations ──────────────────────────────

    async def _call_groq(self, prompt: str, max_tokens: int, temperature: float) -> str:
        if not self._groq_key:
            raise ValueError("GROQ_API_KEY not configured")

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_openrouter(self, prompt: str, max_tokens: int, temperature: float) -> str:
        if not self._openrouter_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._openrouter_key}",
                    "HTTP-Referer": "https://safety-monitor.app",
                    "X-Title": "Industrial Safety Monitor",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._openrouter_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_openai(self, prompt: str, max_tokens: int, temperature: float) -> str:
        if not self._openai_key:
            raise ValueError("OPENAI_API_KEY not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._openai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_ollama(self, prompt: str, max_tokens: int, temperature: float) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": self._ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]

    # ── Template fallback ─────────────────────────────────────

    def _template(self, context: str) -> str:
        return _TEMPLATES.get(context, _TEMPLATES["safety_advice"])

    @staticmethod
    def _extract_section(text: str, start_marker: str, end_marker: Optional[str]) -> str:
        """Extract a section from LLM response between markers."""
        import re
        if end_marker:
            pattern = rf"{re.escape(start_marker)}[:\s]*(.*?)(?={re.escape(end_marker)})"
        else:
            pattern = rf"{re.escape(start_marker)}[:\s]*(.*?)$"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    # ── Status / health ───────────────────────────────────────

    def get_status(self) -> dict:
        """Return which providers are configured (for health endpoint)."""
        return {
            "groq":       bool(self._groq_key),
            "openrouter": bool(self._openrouter_key),
            "openai":     bool(self._openai_key),
            "ollama":     True,  # always try
            "template":   True,  # always available
            "active_model": (
                self._groq_model if self._groq_key
                else self._openrouter_model if self._openrouter_key
                else self._openai_model if self._openai_key
                else self._ollama_model
            ),
        }


# Module-level singleton
llm_manager = LLMManager()
