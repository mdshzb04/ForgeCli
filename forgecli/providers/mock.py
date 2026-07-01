"""A deterministic provider used in tests and offline development."""

from __future__ import annotations

import hashlib
from typing import ClassVar

from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    Provider,
    Role,
    StreamChunk,
)


class MockProviderConfig:
    """Configuration for :class:`MockProvider`."""

    def __init__(self, default_model: str = "mock-model", max_tokens: int = 1024) -> None:
        self.default_model = default_model
        self.max_tokens = max_tokens


class MockProvider(Provider[MockProviderConfig]):
    """Echoes the last user message and returns deterministic embeddings."""

    name: ClassVar[str] = "mock"
    _MODELS: ClassVar[list[ModelInfo]] = [
        ModelInfo(id="mock-model", name="Mock Model", context_window=8192),
    ]

    def __init__(self, config: MockProviderConfig | None = None) -> None:
        super().__init__(config or MockProviderConfig())

    async def chat(self, request: ChatRequest) -> ChatResponse:
        last_user = next(
            (m for m in reversed(request.messages) if m.role is Role.USER),
            None,
        )
        text = last_user.content if last_user else ""

        has_diff_request = any(
            m.role is Role.SYSTEM and "diff" in m.content.lower()
            for m in request.messages
        )

        if has_diff_request:
            text_lower = text.lower()
            if "next.js" in text_lower or "next" in text_lower or "page.tsx" in text_lower or "tsx" in text_lower:
                filename = "page.tsx"
                file_content = (
                    "import React from 'react';\n"
                    "export default function Page() {\n"
                    "    return <div>Hello Next.js</div>;\n"
                    "}\n"
                )
            elif "react" in text_lower or "app.jsx" in text_lower or "jsx" in text_lower:
                filename = "App.jsx"
                file_content = (
                    "import React from 'react';\n"
                    "export default function App() {\n"
                    "    return <div>Hello React</div>;\n"
                    "}\n"
                )
            elif "css" in text_lower or "styles.css" in text_lower:
                filename = "styles.css"
                file_content = (
                    "body {\n"
                    "    background-color: #f0f0f0;\n"
                    "    color: #333;\n"
                    "}\n"
                )
            elif "html" in text_lower or "index.html" in text_lower or "page" in text_lower:
                filename = "index.html"
                file_content = (
                    "<!DOCTYPE html>\n"
                    "<html>\n"
                    "<head><title>Simple Page</title></head>\n"
                    "<body><h1>Hello, World!</h1></body>\n"
                    "</html>\n"
                )
            elif "typescript" in text_lower or "ts" in text_lower or "main.ts" in text_lower:
                filename = "main.ts"
                file_content = (
                    "async function hello(): Promise<void> {\n"
                    "    await Promise.resolve();\n"
                    "    console.log(\"Hello TS\");\n"
                    "}\n"
                    "hello();\n"
                )
            elif "javascript" in text_lower or "js" in text_lower or "main.js" in text_lower:
                filename = "main.js"
                file_content = (
                    "async function hello() {\n"
                    "    await Promise.resolve();\n"
                    "    console.log(\"Hello\");\n"
                    "}\n"
                    "hello();\n"
                )
            elif "go" in text_lower or "main.go" in text_lower:
                filename = "main.go"
                file_content = (
                    "package main\n"
                    "\n"
                    "import \"fmt\"\n"
                    "\n"
                    "func main() {\n"
                    "    fmt.Println(\"Hello Go\")\n"
                    "}\n"
                )
            elif "rust" in text_lower or "rs" in text_lower or "main.rs" in text_lower:
                filename = "main.rs"
                file_content = (
                    "fn main() {\n"
                    "    println!(\"Hello Rust\");\n"
                    "}\n"
                )
            elif "json" in text_lower or "data.json" in text_lower:
                filename = "data.json"
                file_content = (
                    "{\n"
                    "    \"message\": \"Hello JSON\"\n"
                    "}\n"
                )
            elif "yaml" in text_lower or "yml" in text_lower or "config.yaml" in text_lower:
                filename = "config.yaml"
                file_content = (
                    "message: Hello YAML\n"
                )
            elif "markdown" in text_lower or "md" in text_lower or "readme.md" in text_lower:
                filename = "README.md"
                file_content = (
                    "# Hello Markdown\n"
                )
            else:
                filename = "main.py"
                file_content = (
                    "def main():\n"
                    "    print(\"Hello from mock build!\")\n"
                    "\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                )

            diff_lines = [f"+{line}" for line in file_content.splitlines()]
            diff_content = "\n".join(diff_lines) + "\n"
            content = (
                f"diff --git a/{filename} b/{filename}\n"
                f"new file mode 100644\n"
                f"index 0000000..e69de29\n"
                f"--- /dev/null\n"
                f"+++ b/{filename}\n"
                f"@@ -0,0 +{len(diff_lines)} @@\n"
                f"{diff_content}"
            )
        else:
            content = f"[mock] {text}"

        return ChatResponse(
            model=request.model or self.config.default_model,
            message=ChatMessage(role=Role.ASSISTANT, content=content),
            finish_reason="stop",
            prompt_tokens=len(text),
            completion_tokens=len(content),
            total_tokens=len(text) + len(content),
        )

    async def stream(self, request: ChatRequest):
        response = await self.chat(request)
        for word in response.message.content.split(" "):
            yield StreamChunk(delta=word + " ", raw=response.raw)
        yield StreamChunk(delta="", finish_reason="stop")

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors: list[list[float]] = []
        for text in request.inputs:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [b / 255.0 for b in digest[:16]]
            vectors.append(vec)
        return EmbeddingResponse(
            model=request.model or self.config.default_model,
            vectors=vectors,
            prompt_tokens=sum(len(t) for t in request.inputs),
            total_tokens=sum(len(t) for t in request.inputs),
        )

    async def list_models(self) -> list[ModelInfo]:
        return list(self._MODELS)
