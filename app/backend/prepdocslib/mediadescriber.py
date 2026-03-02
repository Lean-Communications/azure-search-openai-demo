import base64
import logging
from abc import ABC
from typing import Optional

import aiohttp
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import get_bearer_token_provider
from openai import AsyncOpenAI, RateLimitError
from rich.progress import Progress
from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
    wait_random_exponential,
)

logger = logging.getLogger("scripts")


class MediaDescriber(ABC):

    async def describe_image(self, image_bytes) -> str:
        raise NotImplementedError  # pragma: no cover


class ContentUnderstandingDescriber(MediaDescriber):
    CU_API_VERSION = "2024-12-01-preview"

    analyzer_schema = {
        "analyzerId": "image_analyzer",
        "name": "Image understanding",
        "description": "Trekk ut detaljert strukturert informasjon fra bilder hentet fra dokumenter.",
        "baseAnalyzerId": "prebuilt-image",
        "scenario": "image",
        "config": {"returnDetails": False},
        "fieldSchema": {
            "name": "ImageInformation",
            "descriptions": "Beskrivelse av bildet.",
            "fields": {
                "Description": {
                    "type": "string",
                    "description": "Beskrivelse av bildet på norsk. Hvis bildet har en tittel, start med tittelen. Inkluder et sammendrag på 2 setninger. Hvis bildet er et diagram, tabell eller graf, inkluder de underliggende dataene i en HTML-tabell med nøyaktige tall. Hvis bildet er en graf, beskriv akser og forklaringer. De eneste tillatte HTML-taggene er table/thead/tr/td/tbody.",
                },
            },
        },
    }

    def __init__(self, endpoint: str, credential: AsyncTokenCredential):
        self.endpoint = endpoint
        self.credential = credential

    async def poll_api(self, session, poll_url, headers):

        @retry(stop=stop_after_attempt(60), wait=wait_fixed(2), retry=retry_if_exception_type(ValueError))
        async def poll():
            async with session.get(poll_url, headers=headers) as response:
                response.raise_for_status()
                response_json = await response.json()
                if response_json["status"] == "Failed":
                    raise Exception("Failed")
                if response_json["status"] == "Running":
                    raise ValueError("Running")
                return response_json

        return await poll()

    async def create_analyzer(self):
        logger.info("Creating analyzer '%s'...", self.analyzer_schema["analyzerId"])

        token_provider = get_bearer_token_provider(self.credential, "https://cognitiveservices.azure.com/.default")
        token = await token_provider()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        params = {"api-version": self.CU_API_VERSION}
        analyzer_id = self.analyzer_schema["analyzerId"]
        cu_endpoint = f"{self.endpoint}/contentunderstanding/analyzers/{analyzer_id}"
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url=cu_endpoint, params=params, headers=headers, json=self.analyzer_schema
            ) as response:
                if response.status == 409:
                    logger.info("Analyzer '%s' already exists.", analyzer_id)
                    return
                elif response.status != 201:
                    data = await response.text()
                    raise Exception("Error creating analyzer", data)
                else:
                    poll_url = response.headers.get("Operation-Location")

            with Progress() as progress:
                progress.add_task("Creating analyzer...", total=None, start=False)
                await self.poll_api(session, poll_url, headers)

    async def describe_image(self, image_bytes: bytes) -> str:
        async with aiohttp.ClientSession() as session:
            token = await self.credential.get_token("https://cognitiveservices.azure.com/.default")
            headers = {"Authorization": "Bearer " + token.token}
            params = {"api-version": self.CU_API_VERSION}
            analyzer_name = self.analyzer_schema["analyzerId"]
            async with session.post(
                url=f"{self.endpoint}/contentunderstanding/analyzers/{analyzer_name}:analyze",
                params=params,
                headers=headers,
                data=image_bytes,
            ) as response:
                response.raise_for_status()
                poll_url = response.headers["Operation-Location"]

                with Progress() as progress:
                    progress.add_task("Processing...", total=None, start=False)
                    results = await self.poll_api(session, poll_url, headers)

                fields = results["result"]["contents"][0]["fields"]
                return fields["Description"]["valueString"]


class MultimodalModelDescriber(MediaDescriber):
    def __init__(self, openai_client: AsyncOpenAI, model: str, deployment: Optional[str] = None):
        self.openai_client = openai_client
        self.model = model
        self.deployment = deployment

    async def describe_image(self, image_bytes: bytes) -> str:
        def before_retry_sleep(retry_state):
            logger.info("Rate limited on the OpenAI chat completions API, sleeping before retrying...")

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_datauri = f"data:image/png;base64,{image_base64}"

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(RateLimitError),
            wait=wait_random_exponential(min=15, max=60),
            stop=stop_after_attempt(15),
            before_sleep=before_retry_sleep,
        ):
            with attempt:
                response = await self.openai_client.chat.completions.create(
                    model=self.model if self.deployment is None else self.deployment,
                    max_tokens=500,
                    seed=42,  # Keep responses more consistent across runs
                    messages=[
                        {
                            "role": "system",
                            "content": "Du er en hjelpsom assistent som beskriver bilder fra organisasjonsdokumenter. Svar alltid på norsk.",
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": "Beskriv bildet med maksimalt 5 setninger. Ikke spekluler om noe du ikke vet.",
                                    "type": "text",
                                },
                                {"image_url": {"url": image_datauri, "detail": "low"}, "type": "image_url"},
                            ],
                        },
                    ],
                )
        description = ""
        if response.choices and response.choices[0].message.content:
            description = response.choices[0].message.content.strip()
        return description
