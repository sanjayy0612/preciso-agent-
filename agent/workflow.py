from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from config import Settings
from extraction import build_extractions
from groq_client import GroqAgentClient
from models import (
    AgentState,
    ParsedIntent,
    PrecisoIngestResult,
    ProviderRequest,
    SourceType,
)
from preciso_client import build_preciso_client
from providers import LocalFolderProvider, OpenBBProvider
from storage.files import write_source_documents


class PrecisoAgentWorkflow:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.groq_client = GroqAgentClient(settings)
        self.openbb_provider = OpenBBProvider(settings)
        self.local_provider = LocalFolderProvider(settings)
        self.preciso_client = build_preciso_client(settings)
        self.graph = self._build_graph()

    def run(self, prompt: str) -> AgentState:
        initial_state: AgentState = {
            "user_prompt": prompt,
            "messages": [{"role": "user", "content": prompt}],
            "errors": [],
        }
        return self.graph.invoke(initial_state)

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("parse_intent", self._parse_intent)
        workflow.add_node("prepare_provider_request", self._prepare_provider_request)
        workflow.add_node("fetch_documents", self._fetch_documents)
        workflow.add_node("write_documents", self._write_documents)
        workflow.add_node("extract_documents", self._extract_documents)
        workflow.add_node("check_preciso_status", self._check_preciso_status)
        workflow.add_node("ingest_documents", self._ingest_documents)
        workflow.add_node("query_graph", self._query_graph)
        workflow.add_node("summarize_run", self._summarize_run)

        workflow.add_edge(START, "parse_intent")
        workflow.add_conditional_edges(
            "parse_intent",
            self._route_after_intent,
            {
                "query_existing": "query_graph",
                "fetch": "prepare_provider_request",
            },
        )
        workflow.add_edge("prepare_provider_request", "fetch_documents")
        workflow.add_edge("fetch_documents", "write_documents")
        workflow.add_edge("write_documents", "extract_documents")
        workflow.add_edge("extract_documents", "check_preciso_status")
        workflow.add_edge("check_preciso_status", "ingest_documents")
        workflow.add_conditional_edges(
            "ingest_documents",
            self._route_after_ingest,
            {
                "query": "query_graph",
                "summarize": "summarize_run",
            },
        )
        workflow.add_edge("query_graph", "summarize_run")
        workflow.add_edge("summarize_run", END)
        return workflow.compile()

    def _parse_intent(self, state: AgentState) -> AgentState:
        intent = self.groq_client.parse_intent(state["user_prompt"])
        return {"parsed_intent": intent}

    def _route_after_intent(self, state: AgentState) -> str:
        intent: ParsedIntent = state["parsed_intent"]
        return "query_existing" if intent.run_mode == "query_existing" else "fetch"

    def _prepare_provider_request(self, state: AgentState) -> AgentState:
        intent = state["parsed_intent"]
        default_source_types: list[SourceType] = (
            ["local_document"]
            if intent.data_source == "local"
            else ["sec_filing", "management_discussion"]
        )
        provider_request = ProviderRequest(
            company=intent.company,
            ticker=(intent.ticker or intent.company).upper(),
            data_source=intent.data_source,
            source_types=intent.source_types or default_source_types,
            form_types=list(self.settings.default_form_types),
            max_documents=intent.max_documents,
            run_mode=intent.run_mode,
            query=intent.query_after_ingest,
        )
        return {"provider_request": provider_request}

    def _fetch_documents(self, state: AgentState) -> AgentState:
        request = state["provider_request"]
        errors = list(state.get("errors", []))
        if request.data_source == "local":
            provider, label = self.local_provider, "Local inbox"
        else:
            provider, label = self.openbb_provider, "OpenBB"
        try:
            documents = provider.fetch_documents(request)
        except Exception as exc:
            errors.append(f"{label} fetch failed: {exc}")
            documents = []
        return {"normalized_documents": documents, "errors": errors}

    def _write_documents(self, state: AgentState) -> AgentState:
        documents = write_source_documents(self.settings, state.get("normalized_documents", []))
        return {
            "normalized_documents": documents,
            "source_paths": [doc.output_path for doc in documents if doc.output_path],
        }

    def _extract_documents(self, state: AgentState) -> AgentState:
        if not state.get("normalized_documents"):
            return {"extraction_artifacts": []}
        artifacts = build_extractions(
            self.settings,
            self.groq_client,
            state.get("normalized_documents", []),
        )
        return {"extraction_artifacts": artifacts}

    def _check_preciso_status(self, state: AgentState) -> AgentState:
        status = self.preciso_client.get_status()
        errors = list(state.get("errors", []))
        if status.get("overall") == "degraded":
            errors.append(f"Preciso status degraded: {status.get('warnings', [])}")
        return {"preciso_status": status, "errors": errors}

    def _ingest_documents(self, state: AgentState) -> AgentState:
        results: list[PrecisoIngestResult] = []
        errors = list(state.get("errors", []))
        for artifact in state.get("extraction_artifacts", []):
            if artifact.status != "success":
                errors.append(f"Skipping failed extraction for {artifact.document_id}: {artifact.message}")
                continue
            ingest_result = self.preciso_client.ingest_file(artifact.extraction_path)
            results.append(
                PrecisoIngestResult(
                    extraction_path=artifact.extraction_path,
                    ingest_status=str(ingest_result.get("status", "error")),
                    entities_added=int(ingest_result.get("entities_added", 0) or 0),
                    relationships_added=int(ingest_result.get("relationships_added", 0) or 0),
                    chunks_stored=int(ingest_result.get("chunks_stored", 0) or 0),
                    message=ingest_result.get("message"),
                )
            )
            if ingest_result.get("status") not in {"success", "validation_failed"}:
                errors.append(
                    f"Ingestion failed for {artifact.extraction_path}: {ingest_result.get('message', 'unknown error')}"
                )
        return {"ingest_results": results, "errors": errors}

    def _route_after_ingest(self, state: AgentState) -> str:
        intent = state["parsed_intent"]
        return "query" if intent.run_mode == "fetch_ingest_query" else "summarize"

    def _query_graph(self, state: AgentState) -> AgentState:
        intent = state["parsed_intent"]
        query = intent.existing_graph_query or intent.query_after_ingest or state["user_prompt"]
        result = self.preciso_client.query_graph(query, self.settings.default_query_mode)
        return {"query_result": result}

    def _summarize_run(self, state: AgentState) -> AgentState:
        run_context: dict[str, Any] = {
            "intent": state.get("parsed_intent").model_dump() if state.get("parsed_intent") else {},
            "documents": [doc.model_dump() for doc in state.get("normalized_documents", [])],
            "extractions": [artifact.model_dump() for artifact in state.get("extraction_artifacts", [])],
            "preciso_status": state.get("preciso_status", {}),
            "ingest_results": [result.model_dump() for result in state.get("ingest_results", [])],
            "query_result": state.get("query_result"),
            "errors": state.get("errors", []),
        }
        summary = self.groq_client.summarize_run(state["user_prompt"], run_context)
        return {"final_response": summary}
