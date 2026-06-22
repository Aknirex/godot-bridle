from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import ValidationError

from bridle import __version__
from bridle.config.key_resolver import KeyResolver
from bridle.config.secrets import contains_forbidden_secret_field
from bridle.domain.assets import GodotImportResult
from bridle.domain.capabilities import ProviderCapability
from bridle.domain.errors import AuthError, ConfigError, ProviderCapabilityError
from bridle.domain.events import JsonValue
from bridle.domain.jobs import JobRef, JobStatus
from bridle.domain.projects import ProjectSummary
from bridle.domain.providers import (
    LlmChatRequest,
    LlmStreamEvent,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderKind,
)
from bridle.godot.project import detect_project
from bridle.harness.cache import ExactCache, SemanticCache
from bridle.harness.character_workflow import (
    CharacterGenerationRequest,
    CharacterGenerationWorkflow,
)
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator, JobContext
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.chroma_store import ChromaVectorStore
from bridle.knowledge.documents import KnowledgeAnswer, KnowledgeIndexStatus, RetrievalHit
from bridle.knowledge.service import ProjectKnowledgeService
from bridle.providers.asset_meshy import MeshyProvider, MockMeshyProvider
from bridle.providers.resolver import ProviderResolver


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
        self.providers = (
            providers
            if providers is not None
            else _merge_provider_configs(
                default_provider_configs(),
                store.list_provider_configs(),
            )
        )
        self.key_resolver = key_resolver or KeyResolver()
        self._llm_cache = ExactCache(
            store.db_path.parent / "response-cache.sqlite3",
            max_entries=1_000,
        )
        self._semantic_caches: dict[str, SemanticCache] = {}
        self._llm_providers: dict[str, object] = {}
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
        for provider in self._llm_providers.values():
            close = getattr(provider, "close", None)
            if close is not None:
                await close()
        self._llm_providers.clear()
        for knowledge in self._knowledge_services.values():
            knowledge.catalog.close()
        self._knowledge_services.clear()
        self._llm_cache.close()
        for cache in self._semantic_caches.values():
            cache.close()
        self._semantic_caches.clear()
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

    async def save_provider_config(self, params: dict) -> ProviderConfig:
        if contains_forbidden_secret_field(params):
            raise ConfigError(
                "Provider config must not contain plaintext secrets. Use api_key_env instead."
            )
        try:
            config = ProviderConfig.model_validate(params)
        except ValidationError as error:
            raise ConfigError("Invalid provider configuration.") from error
        self.store.save_provider_config(config)
        self.providers = _merge_provider_configs(self.providers, [config])
        stale = self._llm_providers.pop(config.provider_id, None)
        if stale is not None:
            close = getattr(stale, "close", None)
            if close is not None:
                await close()
        for knowledge in self._knowledge_services.values():
            knowledge.catalog.close()
        self._knowledge_services.clear()
        return config

    async def test_provider(self, provider_id: str) -> ProviderHealth:
        provider = self._provider_by_id(provider_id)
        if ProviderCapability.EMBEDDING_GENERATE in provider.capabilities:
            return await self._embedding_provider(provider).test_connection()
        if provider.kind == ProviderKind.LLM:
            return await self._llm_provider(provider).test_connection()
        if provider.kind == ProviderKind.ASSET and provider.backend == "mock_meshy":
            return await MockMeshyProvider(provider).test_connection()
        if provider.kind == ProviderKind.ASSET and provider.backend == "meshy":
            return await MeshyProvider(provider, self.key_resolver).test_connection()
        return ProviderHealth(
            provider_id=provider.provider_id,
            status=ProviderHealthStatus.UNKNOWN,
            safe_details=f"No health adapter for backend {provider.backend!r}.",
        )

    async def stream_llm_chat(
        self, provider_id: str, params: dict
    ):
        config = self._provider_by_id(provider_id)
        if ProviderCapability.LLM_STREAM not in config.capabilities:
            raise ProviderCapabilityError(
                f"Provider {provider_id!r} does not support llm.stream."
            )
        try:
            request = LlmChatRequest.model_validate(params)
        except ValidationError as error:
            raise ConfigError("Invalid LLM chat request.") from error
        provider = self._llm_provider(config)
        async for event in provider.stream_chat(request):
            yield LlmStreamEvent.model_validate(event)

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
                llm_config = self._provider_by_id("deepseek")
                llm_provider = self._llm_provider(llm_config)
            workflow = CharacterGenerationWorkflow(
                request,
                provider,
                llm_provider=llm_provider,
                import_diagnoser=self._diagnose_import_failure,
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

    async def get_project_knowledge_status(
        self,
        project_path: str,
    ) -> KnowledgeIndexStatus:
        root = Path(project_path).resolve()
        detect_project(root)
        catalog = SQLiteKnowledgeCatalog(
            self.store.db_path,
            connection=self.store.connection,
        )
        return catalog.status(root)

    async def ask_project_knowledge(
        self,
        project_path: str,
        question: str,
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
    ) -> KnowledgeAnswer:
        if not 1 <= top_k <= 20:
            raise ConfigError("Knowledge query top_k must be between 1 and 20.")
        root = Path(project_path).resolve()
        detect_project(root)
        knowledge = await self._knowledge_for(root)
        try:
            return await knowledge.ask_project(question, top_k=top_k, filters=filters)
        except ValueError as error:
            raise ConfigError(str(error)) from error

    async def _diagnose_import_failure(
        self,
        project_root: Path,
        import_result: GodotImportResult,
    ) -> KnowledgeAnswer:
        knowledge = await self._knowledge_for(project_root)
        await knowledge.index_project(project_root)
        log_excerpt = _import_log_excerpt(import_result)
        question = (
            "Diagnose this Godot import failure using only the indexed project and diagnostic "
            f"sources. Error: {import_result.safe_details} Exit code: {import_result.exit_code}."
        )
        if log_excerpt:
            question += f" Log excerpt:\n{log_excerpt}"
        return await knowledge.ask_project(question, top_k=5)

    async def _knowledge_for(self, project_root: Path) -> ProjectKnowledgeService:
        root = project_root.resolve()
        existing = self._knowledge_services.get(root)
        if existing is not None:
            return existing
        async with self._knowledge_lock:
            existing = self._knowledge_services.get(root)
            if existing is not None:
                return existing
            embedding_config = (
                ProviderResolver(self.providers)
                .resolve([ProviderCapability.EMBEDDING_GENERATE])
                .provider_for(ProviderCapability.EMBEDDING_GENERATE)
            )
            embeddings = self._embedding_provider(embedding_config)
            llm_config = (
                ProviderResolver(self.providers)
                .resolve([ProviderCapability.LLM_CHAT])
                .provider_for(ProviderCapability.LLM_CHAT)
            )
            answer_provider = self._llm_provider(llm_config)
            try:
                vector_store = await asyncio.to_thread(
                    ChromaVectorStore,
                    self.store.db_path.parent / "knowledge-vectors",
                    root,
                    embedding_identity=embeddings.index_identity,
                )
            except RuntimeError as error:
                raise ConfigError(str(error)) from error
            knowledge = ProjectKnowledgeService(
                SQLiteKnowledgeCatalog(
                    self.store.db_path,
                    connection=self.store.connection,
                ),
                embeddings,
                vector_store,
                index_identity=embeddings.index_identity,
                answer_provider=answer_provider,
            )
            self._knowledge_services[root] = knowledge
            return knowledge

    def _provider_by_id(self, provider_id: str) -> ProviderConfig:
        for provider in self.providers:
            if provider.provider_id == provider_id:
                return provider
        raise ProviderCapabilityError(f"Provider {provider_id!r} is not configured.")

    def _llm_provider(self, config: ProviderConfig):
        existing = self._llm_providers.get(config.provider_id)
        if existing is not None:
            return existing
        provider = None
        if config.backend == "anthropic":
            from bridle.providers.llm_http import AnthropicProvider

            provider = AnthropicProvider(config, self.key_resolver)
        elif config.backend == "litellm":
            from bridle.providers.llm_litellm import LiteLlmProvider

            provider = LiteLlmProvider(config, self.key_resolver)
        elif config.backend in {"openai", "openai_compatible"}:
            from bridle.providers.llm_http import OpenAICompatibleProvider

            provider = OpenAICompatibleProvider(config, self.key_resolver)
        if provider is None:
            raise ProviderCapabilityError(
                f"Provider {config.provider_id!r} uses unsupported LLM backend "
                f"{config.backend!r}."
            )
        from bridle.providers.cached import CachedLLMProvider

        semantic_cache = self._semantic_cache_for(config)
        cached = CachedLLMProvider(
            provider,
            self._llm_cache,
            semantic_cache=semantic_cache,
        )
        self._llm_providers[config.provider_id] = cached
        return cached

    def _semantic_cache_for(self, config: ProviderConfig) -> SemanticCache | None:
        existing = self._semantic_caches.get(config.provider_id)
        if existing is not None:
            return existing
        try:
            embedding_config = (
                ProviderResolver(self.providers)
                .resolve([ProviderCapability.EMBEDDING_GENERATE])
                .provider_for(ProviderCapability.EMBEDDING_GENERATE)
            )
            # Semantic lookup is optional. Do not add a failing network request
            # when the user configured only a chat provider.
            self.key_resolver.resolve_required(embedding_config)
        except (AuthError, ProviderCapabilityError):
            return None
        cache = SemanticCache(
            self.store.db_path.parent / "semantic-response-cache.sqlite3",
            self._embedding_provider(embedding_config),
            threshold=0.94,
            max_entries=500,
        )
        self._semantic_caches[config.provider_id] = cache
        return cache

    def _embedding_provider(self, config: ProviderConfig):
        if config.backend == "litellm":
            from bridle.providers.embedding_litellm import LiteLlmEmbeddingProvider

            return LiteLlmEmbeddingProvider(config, self.key_resolver)
        if config.backend in {"openai", "openai_compatible"}:
            from bridle.providers.llm_http import OpenAICompatibleEmbeddingProvider

            return OpenAICompatibleEmbeddingProvider(config, self.key_resolver)
        raise ProviderCapabilityError(
            f"Provider {config.provider_id!r} uses unsupported embedding backend "
            f"{config.backend!r}."
        )


def default_provider_configs() -> list[ProviderConfig]:
    return [
        ProviderConfig(
            provider_id="deepseek",
            kind=ProviderKind.LLM,
            backend="openai_compatible",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            capabilities=[ProviderCapability.LLM_CHAT, ProviderCapability.LLM_STREAM],
            default_for=[ProviderCapability.LLM_CHAT, ProviderCapability.LLM_STREAM],
        ),
        ProviderConfig(
            provider_id="openai_embedding",
            kind=ProviderKind.LLM,
            backend="openai_compatible",
            model="text-embedding-3-small",
            api_key_env="OPENAI_API_KEY",
            capabilities=[ProviderCapability.EMBEDDING_GENERATE],
            default_for=[ProviderCapability.EMBEDDING_GENERATE],
        ),
        ProviderConfig(
            provider_id="meshy_mock",
            kind=ProviderKind.ASSET,
            backend="mock_meshy",
            capabilities=[
                ProviderCapability.MODEL3D_TEXT_TO_3D,
                ProviderCapability.MODEL3D_IMAGE_TO_3D,
                ProviderCapability.TEXTURE_RETEXTURE,
                ProviderCapability.RIGGING_AUTO_RIG,
            ],
            default_for=[
                ProviderCapability.MODEL3D_TEXT_TO_3D,
                ProviderCapability.MODEL3D_IMAGE_TO_3D,
                ProviderCapability.TEXTURE_RETEXTURE,
                ProviderCapability.RIGGING_AUTO_RIG,
            ],
        ),
        ProviderConfig(
            provider_id="meshy",
            kind=ProviderKind.ASSET,
            backend="meshy",
            api_key_env="MESHY_API_KEY",
            capabilities=[
                ProviderCapability.MODEL3D_TEXT_TO_3D,
                ProviderCapability.MODEL3D_IMAGE_TO_3D,
                ProviderCapability.TEXTURE_RETEXTURE,
                ProviderCapability.RIGGING_AUTO_RIG,
            ],
        ),
    ]


def _import_log_excerpt(import_result: GodotImportResult, limit: int = 4_000) -> str:
    excerpts: list[str] = []
    for path in (import_result.stderr_path, import_result.stdout_path):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            excerpts.append(text)
    return "\n".join(excerpts)[:limit]


def _merge_provider_configs(
    defaults: list[ProviderConfig],
    overrides: list[ProviderConfig],
) -> list[ProviderConfig]:
    merged = {provider.provider_id: provider for provider in defaults}
    merged.update({provider.provider_id: provider for provider in overrides})
    return list(merged.values())
