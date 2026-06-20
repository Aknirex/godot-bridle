from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import ValidationError

from bridle import __version__
from bridle.config.key_resolver import KeyResolver
from bridle.domain.capabilities import ProviderCapability
from bridle.domain.errors import ConfigError, ProviderCapabilityError
from bridle.domain.events import JsonValue
from bridle.domain.jobs import JobRef, JobStatus
from bridle.domain.projects import ProjectSummary
from bridle.domain.providers import (
    ProviderConfig,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderKind,
)
from bridle.godot.project import detect_project
from bridle.harness.character_workflow import (
    CharacterGenerationRequest,
    CharacterGenerationWorkflow,
)
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator, JobContext
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.chroma_store import ChromaVectorStore
from bridle.knowledge.documents import RetrievalHit
from bridle.knowledge.embeddings import DeterministicEmbeddingProvider
from bridle.knowledge.service import ProjectKnowledgeService
from bridle.providers.asset_meshy import MeshyProvider, MockMeshyProvider


class BridleAppService:
    def __init__(
        self,
        store: SQLiteJobStore,
        events: JobEventBroker,
        orchestrator: AsyncTaskOrchestrator,
        providers: list[ProviderConfig] | None = None,
        key_resolver: KeyResolver | None = None,
    ) -> None:
        self.store = store
        self.events = events
        self.orchestrator = orchestrator
        self.providers = providers if providers is not None else default_provider_configs()
        self.key_resolver = key_resolver or KeyResolver()
        self._knowledge_services: dict[Path, ProjectKnowledgeService] = {}
        self._knowledge_lock = asyncio.Lock()

    @classmethod
    def create(cls, db_path: Path) -> BridleAppService:
        store = SQLiteJobStore(db_path)
        store.recover_interrupted_jobs()
        events = JobEventBroker(store)
        orchestrator = AsyncTaskOrchestrator(store, events)
        return cls(store=store, events=events, orchestrator=orchestrator)

    async def start(self) -> None:
        await self.orchestrator.start()

    async def stop(self) -> None:
        await self.orchestrator.stop()
        for knowledge in self._knowledge_services.values():
            knowledge.catalog.close()
        self._knowledge_services.clear()
        self.store.close()

    async def health(self) -> dict[str, str]:
        return {
            "name": "godot-bridle",
            "version": __version__,
            "status": "ok",
        }

    async def open_project(self, path: str) -> ProjectSummary:
        summary = detect_project(Path(path))
        self.store.save_project(summary)
        return summary

    async def list_providers(self) -> list[dict]:
        return [provider.model_dump(mode="json") for provider in self.providers]

    async def test_provider(self, provider_id: str) -> ProviderHealth:
        provider = self._provider_by_id(provider_id)
        if provider.kind == ProviderKind.LLM:
            from bridle.providers.llm_litellm import LiteLlmProvider

            return await LiteLlmProvider(provider, self.key_resolver).test_connection()
        if provider.kind == ProviderKind.ASSET and provider.backend == "mock_meshy":
            return await MockMeshyProvider(provider).test_connection()
        if provider.kind == ProviderKind.ASSET and provider.backend == "meshy":
            return await MeshyProvider(provider, self.key_resolver).test_connection()
        return ProviderHealth(
            provider_id=provider.provider_id,
            status=ProviderHealthStatus.UNKNOWN,
            safe_details=f"No health adapter for backend {provider.backend!r}.",
        )

    async def submit_workflow(self, params: dict) -> JobRef:
        workflow_id = str(params.get("workflow_id", "mock.sleep"))
        if workflow_id == "character_gen":
            try:
                request = CharacterGenerationRequest.model_validate(params)
            except ValidationError as error:
                raise ConfigError("Invalid character generation request.") from error
            provider_config = self._provider_by_id(request.provider_id)
            if provider_config.backend == "mock_meshy":
                provider = MockMeshyProvider(provider_config)
            elif provider_config.backend == "meshy":
                provider = MeshyProvider(provider_config, self.key_resolver)
            else:
                raise ProviderCapabilityError(
                    f"Provider {request.provider_id!r} is not a supported asset provider."
                )
            llm_provider = None
            if request.enhance_prompt:
                from bridle.providers.llm_litellm import LiteLlmProvider

                llm_config = self._provider_by_id("deepseek")
                llm_provider = LiteLlmProvider(llm_config, self.key_resolver)
            workflow = CharacterGenerationWorkflow(
                request,
                provider,
                llm_provider=llm_provider,
            )
            return await self.orchestrator.submit(workflow_id, workflow.run)

        duration_ms = int(params.get("duration_ms", 10))

        async def handler(context: JobContext) -> None:
            await context.emit("job.progress", "Workflow started", progress=0.1)
            await asyncio.sleep(max(duration_ms, 0) / 1000)
            await context.emit("job.progress", "Workflow finished", progress=0.9)

        return await self.orchestrator.submit(workflow_id, handler)

    async def get_job_status(self, job_id: str) -> JobStatus:
        return self.orchestrator.get_status(job_id)

    async def cancel_job(self, job_id: str) -> JobStatus:
        return self.orchestrator.cancel_job(job_id)

    async def index_project_knowledge(self, project_path: str) -> JobRef:
        root = Path(project_path).resolve()
        detect_project(root)

        async def handler(context: JobContext) -> None:
            await context.emit(
                "knowledge.index.started",
                "Project knowledge indexing started",
                progress=0.1,
            )
            knowledge = await self._knowledge_for(root)
            summary = await knowledge.index_project(root)
            await context.emit(
                "knowledge.index.completed",
                "Project knowledge indexing completed",
                progress=0.95,
                payload=summary.model_dump(mode="json"),
            )

        return await self.orchestrator.submit("knowledge.index_project", handler)

    async def query_project_knowledge(
        self,
        project_path: str,
        question: str,
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
    ) -> list[RetrievalHit]:
        if not 1 <= top_k <= 20:
            raise ConfigError("Knowledge query top_k must be between 1 and 20.")
        root = Path(project_path).resolve()
        detect_project(root)
        knowledge = await self._knowledge_for(root)
        try:
            return await knowledge.query_project(
                question,
                top_k=top_k,
                filters=filters,
            )
        except ValueError as error:
            raise ConfigError(str(error)) from error

    async def _knowledge_for(self, project_root: Path) -> ProjectKnowledgeService:
        root = project_root.resolve()
        existing = self._knowledge_services.get(root)
        if existing is not None:
            return existing
        async with self._knowledge_lock:
            existing = self._knowledge_services.get(root)
            if existing is not None:
                return existing
            try:
                vector_store = await asyncio.to_thread(
                    ChromaVectorStore,
                    self.store.db_path.parent / "knowledge-vectors",
                    root,
                )
            except RuntimeError as error:
                raise ConfigError(str(error)) from error
            knowledge = ProjectKnowledgeService(
                SQLiteKnowledgeCatalog(
                    self.store.db_path,
                    connection=self.store.connection,
                ),
                DeterministicEmbeddingProvider(),
                vector_store,
            )
            self._knowledge_services[root] = knowledge
            return knowledge

    def _provider_by_id(self, provider_id: str) -> ProviderConfig:
        for provider in self.providers:
            if provider.provider_id == provider_id:
                return provider
        raise ProviderCapabilityError(f"Provider {provider_id!r} is not configured.")


def default_provider_configs() -> list[ProviderConfig]:
    return [
        ProviderConfig(
            provider_id="deepseek",
            kind=ProviderKind.LLM,
            backend="litellm",
            model="deepseek/deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
            capabilities=[ProviderCapability.LLM_CHAT, ProviderCapability.LLM_STREAM],
            default_for=[ProviderCapability.LLM_CHAT, ProviderCapability.LLM_STREAM],
        ),
        ProviderConfig(
            provider_id="meshy_mock",
            kind=ProviderKind.ASSET,
            backend="mock_meshy",
            capabilities=[ProviderCapability.MODEL3D_TEXT_TO_3D],
            default_for=[ProviderCapability.MODEL3D_TEXT_TO_3D],
        ),
        ProviderConfig(
            provider_id="meshy",
            kind=ProviderKind.ASSET,
            backend="meshy",
            api_key_env="MESHY_API_KEY",
            capabilities=[ProviderCapability.MODEL3D_TEXT_TO_3D],
        ),
    ]
