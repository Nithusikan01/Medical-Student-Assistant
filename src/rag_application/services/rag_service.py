from rag_application.llm.generator import GeminiGenerator
from rag_application.llm.prompt_builder import PromptBuilder
from rag_application.retrieval.retriever import Retriever



class RAGService:

    def __init__(
        self,
        retriever: Retriever,
        generator: GeminiGenerator
    ):
        self.retriever = retriever
        self.generator = generator

    def answer(
        self,
        question: str,
        top_k: int = 5
    ) -> str:

        chunks = self.retriever.retrieve(
            query=question,
            top_k=top_k
        )

        if not chunks:
            return "I don't know based on the provided document."

        prompt = PromptBuilder.build_prompt(
            question=question,
            chunks=chunks
        )

        response = self.generator.generate(
            prompt
        )
        if not response.text:
            raise ValueError(
                "Gemini returned empty response"
            )
        return response.text