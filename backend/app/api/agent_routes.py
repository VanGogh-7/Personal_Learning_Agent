from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.embeddings.providers import EmbeddingProviderError
from app.graphs.chat_rag_graph import (
    ChatRAGGraphError,
    ChatRAGValidationError,
    run_chat_rag_graph,
)
from app.graphs.schemas import AgentChatRequest, AgentChatResponse
from app.llm.providers import LLMConfigurationError, LLMProviderError
from app.rag.retrieval import LibraryItemRagError

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat_endpoint(request: AgentChatRequest) -> AgentChatResponse:
    try:
        db_session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            response = run_chat_rag_graph(request, db_session)
            db_session.commit()
            return response
        except ChatRAGValidationError as exc:
            db_session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LibraryItemRagError as exc:
            db_session.rollback()
            detail = str(exc)
            status_code = 404 if detail == "Library item not found" else 400
            raise HTTPException(status_code=status_code, detail=detail) from exc
        except ChatRAGGraphError as exc:
            db_session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            db_session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
        except (EmbeddingProviderError, LLMConfigurationError, LLMProviderError) as exc:
            db_session.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        db_session.close()
