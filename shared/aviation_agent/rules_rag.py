#!/usr/bin/env python3
"""
RAG (Retrieval-Augmented Generation) system for aviation rules.

This module provides semantic search capabilities for aviation regulations,
enabling efficient retrieval of relevant rules based on natural language queries.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """
    Provides text embeddings using OpenAI models.
    
    Uses OpenAI embeddings for semantic search. Requires OPENAI_API_KEY to be set.
    """
    
    def __init__(self, model_name: str = "text-embedding-3-small"):
        """
        Initialize embedding provider.
        
        Args:
            model_name: Name of the embedding model. Options:
                - "text-embedding-3-small" (OpenAI, 1536 dims, fast, excellent quality)
                - "text-embedding-3-large" (OpenAI, 3072 dims, best quality)
        """
        self.model_name = model_name
        
        if not model_name.startswith("text-embedding-"):
            raise ValueError(
                f"Unsupported embedding model: {model_name}. "
                "Only OpenAI models (text-embedding-3-small, text-embedding-3-large) are supported."
            )
        
        # OpenAI embeddings
        try:
            from langchain_openai import OpenAIEmbeddings
            self.model = OpenAIEmbeddings(model=model_name)
            self.provider = "openai"
            logger.info(f"Initialized OpenAI embeddings: {model_name}")
        except ImportError:
            raise ImportError(
                "OpenAI embeddings require langchain-openai. "
                "Install with: pip install langchain-openai"
            )
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # OpenAI embeddings
        return self.model.embed_documents(texts)
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.
        
        Args:
            query: Query text to embed
            
        Returns:
            Embedding vector
        """
        # OpenAI embeddings
        return self.model.embed_query(query)


class QueryReformulator:
    """
    Reformulates colloquial queries into formal aviation regulation questions.
    
    Improves retrieval quality by converting informal user queries like
    "Where do I clear customs?" into formal questions like
    "What are the customs clearance requirements?"
    """
    
    def __init__(self, llm: Optional[Any] = None):
        """
        Initialize query reformulator.
        
        Args:
            llm: Optional LLM instance for reformulation. If None, uses environment.
        """
        self.llm = llm
        self._initialized = False
    
    def _ensure_llm(self):
        """Lazy initialization of LLM."""
        if self._initialized:
            return
        
        if self.llm is None:
            try:
                from langchain_openai import ChatOpenAI
                model = os.getenv("ROUTER_MODEL", "gpt-4o-mini")
                self.llm = ChatOpenAI(model=model, temperature=0)
                logger.debug(f"Initialized reformulation LLM: {model}")
            except ImportError:
                logger.warning(
                    "Query reformulation requires langchain-openai. "
                    "Proceeding without reformulation."
                )
                self.llm = None
        
        self._initialized = True
    
    def reformulate(self, query: str, context: Optional[List[str]] = None) -> str:
        """
        Reformulate a colloquial query into a formal aviation question.
        
        Args:
            query: User's original query
            context: Optional conversation context
            
        Returns:
            Reformulated formal question, or original if reformulation fails
        """
        self._ensure_llm()
        
        if self.llm is None:
            logger.debug("No LLM available, using original query")
            return query
        
        try:
            prompt = f"""Reformulate this aviation query into a formal question that would appear in official aviation regulations or documentation.

User query: "{query}"

Guidelines:
- Keep it concise and specific
- Use aviation terminology where appropriate
- Focus on the core regulatory question
- Don't add information not in the original query

Formal question:"""
            
            response = self.llm.invoke(prompt)
            reformulated = response.content.strip().strip('"').strip()
            
            if reformulated and reformulated != query:
                logger.debug(f"Reformulated: '{query}' → '{reformulated}'")
                return reformulated
            else:
                return query
                
        except Exception as e:
            logger.warning(f"Query reformulation failed: {e}")
            return query


class OpenAIReranker:
    """
    OpenAI-based reranker using embeddings.
    
    Uses OpenAI embeddings to compute similarity between query and documents,
    then reranks based on cosine similarity.
    """
    
    def __init__(self, model_name: str, embedding_provider: "EmbeddingProvider"):
        """
        Initialize OpenAI reranker.
        
        Args:
            model_name: OpenAI embedding model name
            embedding_provider: EmbeddingProvider instance to reuse
        """
        self.model_name = model_name
        self.embedding_provider = embedding_provider
        self._initialized = True
        
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        text_key: str = "question_text",
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using OpenAI embeddings.
        
        Args:
            query: The search query
            documents: List of document dicts to rerank
            text_key: Key in document dict containing text to compare
            top_k: Number of top results to return (None = all)
            
        Returns:
            Reranked list of documents with added 'rerank_score' field
        """
        if not documents:
            return documents
        
        try:
            import numpy as np
            from numpy.linalg import norm
            
            # Embed query
            query_embedding = np.array(self.embedding_provider.embed_query(query))
            
            # Embed all documents
            texts = [doc.get(text_key, "") for doc in documents]
            doc_embeddings = [np.array(self.embedding_provider.embed_query(text)) for text in texts]
            
            # Compute cosine similarities
            similarities = []
            for doc_emb in doc_embeddings:
                # Cosine similarity
                dot_product = np.dot(query_embedding, doc_emb)
                norms = norm(query_embedding) * norm(doc_emb)
                similarity = dot_product / norms if norms > 0 else 0.0
                similarities.append(float(similarity))
            
            # Create list with scores
            scored_docs = []
            for doc, score in zip(documents, similarities):
                doc_copy = doc.copy()
                doc_copy["rerank_score"] = score
                scored_docs.append(doc_copy)
            
            # Sort by score (descending)
            scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
            
            # Return top_k if specified
            if top_k:
                scored_docs = scored_docs[:top_k]
            
            logger.info(f"OpenAI reranked {len(documents)} documents to {len(scored_docs)} results")
            return scored_docs
            
        except Exception as e:
            logger.warning(f"OpenAI reranking failed: {e}")
            return documents


class Reranker:
    """
    Cohere-based reranker for improved retrieval precision.
    
    Uses Cohere's rerank API to rerank results after initial retrieval,
    providing better accuracy than local cross-encoders.
    
    Uses direct HTTP API calls to avoid SDK dependency issues.
    """
    
    # Default model - Cohere's latest rerank model
    DEFAULT_MODEL = "rerank-v3.5"
    COHERE_API_URL = "https://api.cohere.com/v2/rerank"
    
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Cohere reranker.
        
        Args:
            model_name: Cohere rerank model name. Options:
                - "rerank-v3.5" (latest, best quality)
                - "rerank-english-v3.0" (English only)
                - "rerank-multilingual-v3.0" (multilingual)
            api_key: Cohere API key. If not provided, uses COHERE_API_KEY env var.
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("COHERE_API_KEY")
        self._initialized = False
        
    def _ensure_initialized(self) -> bool:
        """Check if reranker is properly configured."""
        if self._initialized:
            return True
        if not self._api_key:
            logger.warning(
                "Cohere API key not set. Set COHERE_API_KEY environment variable. "
                "Reranking disabled."
            )
            return False
        logger.info(f"✓ Cohere reranker ready: {self.model_name}")
        self._initialized = True
        return True
    
    def rerank(
        self, 
        query: str, 
        documents: List[Dict[str, Any]], 
        text_key: str = "question_text",
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using Cohere rerank API.
        
        Args:
            query: The search query
            documents: List of document dicts to rerank
            text_key: Key in document dict containing text to compare
            top_k: Number of top results to return (None = all)
            
        Returns:
            Reranked list of documents with added 'rerank_score' field
        """
        if not documents:
            return documents
            
        if not self._ensure_initialized():
            logger.debug("Cohere reranker not available, returning original order")
            return documents
        
        # Extract texts from documents
        texts = [doc.get(text_key, "") for doc in documents]
        
        try:
            import httpx
            
            # Call Cohere rerank API directly
            response = httpx.post(
                self.COHERE_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model_name,
                    "query": query,
                    "documents": texts,
                    "top_n": top_k or len(documents)
                },
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            
            # Build reranked list based on response
            reranked = []
            for result in data.get("results", []):
                idx = result.get("index", 0)
                doc = documents[idx].copy()
                doc["rerank_score"] = float(result.get("relevance_score", 0))
                reranked.append(doc)
            
            logger.info(f"Cohere reranked {len(documents)} documents")
            
            return reranked
            
        except Exception as e:
            logger.warning(f"Cohere reranking failed: {e}")
            return documents


class RulesRAG:
    """
    RAG system for aviation rules retrieval.
    
    Provides semantic search over aviation regulations with country filtering
    and query reformulation for improved accuracy.
    """
    
    def __init__(
        self,
        vector_db_path: Optional[Path | str] = None,
        vector_db_url: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        enable_reformulation: bool = True,
        enable_reranking: bool = False,
        reranking_provider: str = "cohere",
        reranking_config: Optional[Any] = None,
        retrieval_config: Optional[Any] = None,
        llm: Optional[Any] = None,
        rules_manager: Optional[Any] = None,
    ):
        """
        Initialize RAG system.
        
        Args:
            vector_db_path: Path to ChromaDB storage directory (for local mode)
            vector_db_url: URL to ChromaDB service (for service mode). If provided, takes precedence over vector_db_path.
            embedding_model: Name of embedding model to use (OpenAI models only)
            enable_reformulation: Whether to reformulate queries for better matching
            enable_reranking: Whether to use reranking
            reranking_provider: Reranking provider ("cohere", "openai", or "none")
            reranking_config: RerankingConfig object with provider-specific settings
            retrieval_config: RetrievalConfig object with retrieval parameters (top_k, similarity_threshold, rerank_candidates_multiplier)
            llm: Optional LLM instance for reformulation
            rules_manager: Optional RulesManager instance for multi-country lookups
        """
        self.vector_db_path = Path(vector_db_path) if vector_db_path else None
        self.vector_db_url = vector_db_url
        self.embedding_model = embedding_model
        
        # Initialize embedding provider
        self.embedding_provider = EmbeddingProvider(embedding_model)
        
        # Initialize query reformulator
        self.enable_reformulation = enable_reformulation
        if enable_reformulation:
            self.reformulator = QueryReformulator(llm)
        else:
            self.reformulator = None
        
        # Initialize reranker based on provider
        self.enable_reranking = enable_reranking
        self.reranking_provider = reranking_provider if enable_reranking else "none"
        self.reranking_config = reranking_config
        self.retrieval_config = retrieval_config
        
        if enable_reranking and reranking_provider == "cohere":
            from .behavior_config import RerankingConfig
            if reranking_config and hasattr(reranking_config, 'cohere') and reranking_config.cohere:
                model = reranking_config.cohere.model
            else:
                model = "rerank-v3.5"
            self.reranker = Reranker(model_name=model)
        elif enable_reranking and reranking_provider == "openai":
            # OpenAI reranker implementation
            from .behavior_config import RerankingConfig
            if reranking_config and hasattr(reranking_config, 'openai') and reranking_config.openai:
                model = reranking_config.openai.model
            else:
                model = "text-embedding-3-large"
            self.reranker = OpenAIReranker(model_name=model, embedding_provider=self.embedding_provider)
        else:
            self.reranker = None
        
        # Store rules manager for multi-country lookups
        self.rules_manager = rules_manager
        
        # Initialize ChromaDB - use service mode if URL is provided, otherwise local mode
        if self.vector_db_url:
            logger.info(f"Initializing ChromaDB service at {self.vector_db_url}")
            # Parse URL to extract host and port
            parsed_url = urlparse(self.vector_db_url)
            host = parsed_url.hostname or "localhost"
            port = parsed_url.port or (8000 if parsed_url.scheme == "http" else 443)
            
            # Initialize HttpClient with basic settings
            # Note: Auth token support can be added later if needed via headers or Settings
            self.client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=Settings(anonymized_telemetry=False)
            )
        elif self.vector_db_path:
            logger.info(f"Initializing ChromaDB at {self.vector_db_path}")
            self.client = chromadb.PersistentClient(
                path=str(self.vector_db_path),
                settings=Settings(
                    anonymized_telemetry=False,  # Disable telemetry for privacy
                )
            )
        else:
            raise ValueError("Either vector_db_path or vector_db_url must be provided")
        
        # Load collection
        try:
            self.collection = self.client.get_collection(
                name="aviation_rules",
                embedding_function=None  # We provide embeddings manually
            )
            doc_count = self.collection.count()
            logger.info(f"✓ Loaded collection with {doc_count} documents")
        except Exception as e:
            logger.error(f"Failed to load collection: {e}")
            logger.error("Run build_vector_db() to create the vector database")
            self.collection = None
    
    @staticmethod
    def _parse_json_field(value: Any, default: Any = []) -> Any:
        """Parse a JSON field from metadata, handling both string and list formats."""
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default
        if isinstance(value, list):
            return value
        return default
    
    def retrieve_rules(
        self,
        query: str,
        countries: Optional[List[str]] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        reformulate: Optional[bool] = None,
        rules_manager: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant rules using semantic search.
        
        For multiple countries: queries the first country to get top questions,
        then uses RulesManager to get answers for those questions across all countries.
        For single country: returns results directly from vector DB metadata.
        
        Args:
            query: User query text
            countries: List of ISO-2 country codes to filter by (e.g., ["FR", "GB"])
            top_k: Number of question IDs to retrieve (will return answers for all countries)
            similarity_threshold: Minimum similarity score (0-1)
            reformulate: Override default reformulation setting
            rules_manager: Optional RulesManager instance (uses self.rules_manager if not provided)
        
        Returns:
            List of matching rules with metadata, sorted by similarity score.
            For multiple countries, returns the same questions for all countries.
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return []
        
        # Use provided rules_manager or fall back to instance variable
        rules_mgr = rules_manager or self.rules_manager
        
        # Determine if we have multiple countries
        has_multiple_countries = countries and len(countries) > 1
        
        # Query reformulation
        original_query = query
        if reformulate is None:
            reformulate = self.enable_reformulation
        
        if reformulate and self.reformulator:
            query = self.reformulator.reformulate(query)
        
        # Generate query embedding
        try:
            query_embedding = self.embedding_provider.embed_query(query)
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return []
        
        # For multiple countries: query WITHOUT country filter to get globally best questions
        # Then use RulesManager to expand those questions to all requested countries
        # For single country: query that country directly and return results
        if has_multiple_countries:
            # Query without country filter to get globally best matching questions
            where_filter = None  # No country filter - find best questions across all
            n_results = top_k * 3  # Get more results since we'll dedupe by question_id
            logger.info(f"Multi-country query: searching globally for best questions, then expanding to {countries}")
        else:
            # Single country or no country filter
            where_filter = None
            if countries:
                countries_upper = [c.upper() for c in countries]
                where_filter = {"country_code": {"$in": countries_upper}}
            n_results = top_k
        
        # Search collection
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []
        
        # Extract top question IDs and their similarity scores
        question_matches = []
        if results and results['ids'] and results['ids'][0]:
            seen_question_ids = set()
            for i, doc_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][i] if results['distances'] else 1.0
                # ChromaDB cosine "distance" varies by model. For sentence-transformers,
                # distances around 1.0 are common for good matches. The formula below
                # maps distance to a usable similarity range.
                similarity = max(0, 1 - (distance / 2))
                
                if similarity < similarity_threshold:
                    continue
                
                metadata = results['metadatas'][0][i]
                question_id = metadata.get("question_id")
                
                if not question_id:
                    continue
                
                # Track unique question IDs with their best similarity score
                if question_id not in seen_question_ids:
                    seen_question_ids.add(question_id)
                    question_matches.append({
                        "question_id": question_id,
                        "question_text": results['documents'][0][i],
                        "similarity": similarity,
                        "category": metadata.get("category"),
                        "tags": self._parse_json_field(metadata.get("tags"), []),
                    })
        
        # Sort by similarity and take candidates for reranking
        question_matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        # If reranking enabled, get more candidates and rerank
        if self.enable_reranking and self.reranker:
            # Take top_k * multiplier candidates for reranking to give reranker more options
            from .behavior_config import RetrievalConfig
            multiplier = 2  # Default
            if self.retrieval_config and hasattr(self.retrieval_config, 'rerank_candidates_multiplier'):
                multiplier = self.retrieval_config.rerank_candidates_multiplier
            candidates = question_matches[:top_k * multiplier]
            if candidates:
                question_matches = self.reranker.rerank(
                    query=original_query,  # Use original query, not reformulated
                    documents=candidates,
                    text_key="question_text",
                    top_k=top_k
                )
                logger.info(f"Reranked {len(candidates)} candidates to {len(question_matches)} results using {self.reranking_provider}")
        else:
            question_matches = question_matches[:top_k]
        
        if not question_matches:
            logger.info(f"No matching rules found for query: '{query}'")
            return []
        
        # For multiple countries: use RulesManager to get answers for all countries
        if has_multiple_countries:
            if not rules_mgr:
                logger.warning(
                    "Multiple countries requested but RulesManager not available. "
                    "Falling back to single-country query behavior."
                )
                # Fall through to single-country logic below
            else:
                # Ensure rules manager is loaded
                if not rules_mgr.loaded:
                    rules_mgr.load_rules()
                
                matches = []
                countries_upper = [c.upper() for c in countries] if countries else []
                
                for q_match in question_matches:
                    question_id = q_match["question_id"]
                    question_info = rules_mgr.question_map.get(question_id)
                    
                    if not question_info:
                        logger.warning(f"Question ID {question_id} not found in RulesManager")
                        continue
                    
                    answers_by_country = question_info.get("answers_by_country", {})
                    
                    # Get answers for all requested countries
                    for country_code in countries_upper:
                        answer_data = answers_by_country.get(country_code)
                        
                        if not answer_data:
                            # Skip if no answer for this country
                            continue
                        
                        # Parse links
                        links = answer_data.get("links", [])
                        if isinstance(links, str):
                            try:
                                links = json.loads(links)
                            except (json.JSONDecodeError, TypeError):
                                links = []
                        elif not isinstance(links, list):
                            links = []
                        
                        matches.append({
                            "id": f"{question_id}_{country_code}",
                            "question_id": question_id,
                            "question_text": q_match["question_text"],
                            "similarity": round(q_match["similarity"], 3),
                            "country_code": country_code,
                            "category": q_match["category"],
                            "tags": q_match["tags"],
                            "answer_html": answer_data.get("answer_html", ""),
                            "links": links,
                            "last_reviewed": answer_data.get("last_reviewed"),
                        })
                
                log_msg = f"Retrieved {len(question_matches)} questions for {len(countries_upper)} countries"
                if query != original_query:
                    log_msg += f" (reformulated: '{original_query}' → '{query}')"
                logger.info(log_msg)
                
                return matches
        
        # For single country: return results directly from metadata
        matches = []
        if results and results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][i] if results['distances'] else 1.0
                similarity = max(0, 1 - (distance / 2))
                
                if similarity < similarity_threshold:
                    continue
                
                metadata = results['metadatas'][0][i]
                
                # Parse JSON fields
                links_raw = metadata.get("links", "[]")
                if isinstance(links_raw, str):
                    try:
                        links = json.loads(links_raw)
                    except (json.JSONDecodeError, TypeError):
                        links = []
                elif isinstance(links_raw, list):
                    links = links_raw
                else:
                    links = []
                
                tags_raw = metadata.get("tags", "[]")
                if isinstance(tags_raw, str):
                    try:
                        tags = json.loads(tags_raw)
                    except (json.JSONDecodeError, TypeError):
                        tags = []
                elif isinstance(tags_raw, list):
                    tags = tags_raw
                else:
                    tags = []
                
                matches.append({
                    "id": doc_id,
                    "question_id": metadata.get("question_id"),
                    "question_text": results['documents'][0][i],
                    "similarity": round(similarity, 3),
                    "country_code": metadata.get("country_code"),
                    "category": metadata.get("category"),
                    "tags": tags,
                    "answer_html": metadata.get("answer_html"),
                    "links": links,
                    "last_reviewed": metadata.get("last_reviewed"),
                })
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        log_msg = f"Retrieved {len(matches)} rules"
        if query != original_query:
            log_msg += f" (reformulated: '{original_query}' → '{query}')"
        if countries:
            log_msg += f" for {countries}"
        logger.info(log_msg)
        
        return matches[:top_k]


def build_vector_db(
    rules_json_path: Path | str,
    vector_db_path: Optional[Path | str] = None,
    vector_db_url: Optional[str] = None,
    embedding_model: str = "text-embedding-3-small",
    batch_size: int = 100,
    force_rebuild: bool = False,
) -> int:
    """
    Build vector database from rules.json.
    
    This function creates a ChromaDB collection with embeddings for all
    questions in the rules.json file, indexed by country.
    
    Args:
        rules_json_path: Path to rules.json file
        vector_db_path: Path to ChromaDB storage directory (for local mode)
        vector_db_url: URL to ChromaDB service (for service mode). If provided, takes precedence over vector_db_path.
        embedding_model: Name of embedding model to use
        batch_size: Number of documents to process per batch
        force_rebuild: If True, rebuild even if collection exists
        
    Returns:
        Number of documents added to the database
        
    Raises:
        FileNotFoundError: If rules.json doesn't exist
        ValueError: If rules.json format is invalid
    """
    rules_json_path = Path(rules_json_path)
    
    # Load rules.json
    if not rules_json_path.exists():
        raise FileNotFoundError(f"Rules file not found: {rules_json_path}")
    
    logger.info(f"Loading rules from {rules_json_path}")
    with open(rules_json_path, 'r', encoding='utf-8') as f:
        rules_data = json.load(f)

    # Handle both flat array format and nested format
    if isinstance(rules_data, list):
        # Flat format: [{"country_code": "GB", "question_id": "...", ...}, ...]
        rules_list = rules_data
        logger.info(f"Found {len(rules_list)} rule entries (flat format)")
    elif isinstance(rules_data, dict) and "questions" in rules_data:
        # Nested format: {"questions": [...]}
        questions = rules_data.get("questions", [])
        if not questions:
            raise ValueError(f"No questions found in {rules_json_path}")
        logger.info(f"Found {len(questions)} questions (nested format)")
        # Convert to flat format for processing
        rules_list = []
        for question in questions:
            question_id = question.get("question_id")
            question_text = question.get("question_text", "")
            answers_by_country = question.get("answers_by_country", {})
            for country_code, answer in answers_by_country.items():
                rules_list.append({
                    "country_code": country_code,
                    "question_id": question_id,
                    "question_text": question_text,
                    "answer": answer.get("answer_html", ""),
                    "category": question.get("category", ""),
                    "tags": question.get("tags", []),
                    "links": answer.get("links", []),
                    "last_reviewed": answer.get("last_reviewed", ""),
                })
    else:
        raise ValueError(f"Invalid rules.json format: expected list or dict with 'questions' key")

    if not rules_list:
        raise ValueError(f"No rules found in {rules_json_path}")

    # Initialize embedding provider
    embedding_provider = EmbeddingProvider(embedding_model)

    # Initialize ChromaDB - use service mode if URL is provided, otherwise local mode
    if vector_db_url:
        logger.info(f"Building vector database using ChromaDB service at {vector_db_url}")
        # Parse URL to extract host and port
        parsed_url = urlparse(vector_db_url)
        host = parsed_url.hostname or "localhost"
        port = parsed_url.port or (8000 if parsed_url.scheme == "http" else 443)
        
        # Initialize HttpClient with basic settings
        # Note: Auth token support can be added later if needed
        client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False)
        )
    elif vector_db_path:
        vector_db_path = Path(vector_db_path)
        logger.info(f"Building vector database at {vector_db_path}")
        vector_db_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(vector_db_path),
            settings=Settings(anonymized_telemetry=False)
        )
    else:
        raise ValueError("Either vector_db_path or vector_db_url must be provided")

    # Check if collection exists
    collection_name = "aviation_rules"
    try:
        existing = client.get_collection(collection_name)
        if not force_rebuild:
            doc_count = existing.count()
            logger.info(f"Collection already exists with {doc_count} documents")
            logger.info("Use force_rebuild=True to rebuild")
            return doc_count
        logger.info("Force rebuild: deleting existing collection")
        client.delete_collection(collection_name)
    except Exception:
        pass  # Collection doesn't exist, that's fine

    # Create new collection
    collection = client.create_collection(
        name=collection_name,
        metadata={"description": "Aviation rules and regulations by country"}
    )
    logger.info(f"Created collection: {collection_name}")

    # Process each rule entry
    documents = []
    metadatas = []
    ids = []

    for rule in rules_list:
        question_id = rule.get("question_id")
        question_text = rule.get("question_text", "")
        country_code = rule.get("country_code", "")

        if not question_id or not question_text or not country_code:
            logger.warning(f"Skipping rule with missing required fields: {rule}")
            continue

        # Create unique document ID
        doc_id = f"{question_id}_{country_code}".replace(" ", "_")

        documents.append(question_text)
        metadatas.append({
            "question_id": question_id,
            "country_code": country_code.upper(),
            "category": rule.get("category", ""),
            "tags": json.dumps(rule.get("tags", [])),
            "answer_html": rule.get("answer", ""),
            "links": json.dumps(rule.get("links", [])),
            "last_reviewed": rule.get("last_reviewed", ""),
        })
        ids.append(doc_id)
    
    if not documents:
        raise ValueError("No valid documents to add to vector database")
    
    logger.info(f"Processing {len(documents)} documents in batches of {batch_size}")
    
    # Add documents in batches with embeddings
    total_added = 0
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i + batch_size]
        batch_metas = metadatas[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        
        # Generate embeddings for batch
        try:
            embeddings = embedding_provider.embed(batch_docs)
        except Exception as e:
            logger.error(f"Failed to generate embeddings for batch {i // batch_size + 1}: {e}")
            continue
        
        # Add to collection
        try:
            collection.add(
                documents=batch_docs,
                embeddings=embeddings,
                metadatas=batch_metas,
                ids=batch_ids
            )
            total_added += len(batch_docs)
            batch_num = i // batch_size + 1
            logger.info(f"Added batch {batch_num}: {len(batch_docs)} documents")
        except Exception as e:
            logger.error(f"Failed to add batch {i // batch_size + 1}: {e}")
            continue
    
    logger.info(f"✓ Vector DB built with {total_added} documents")
    logger.info(f"✓ Saved to {vector_db_path}")
    
    return total_added


if __name__ == "__main__":
    # Simple test when run directly
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        # Build mode
        rules_json = Path("data/rules.json")
        vector_db = Path("cache/rules_vector_db")
        
        if not rules_json.exists():
            print(f"Error: {rules_json} not found")
            sys.exit(1)
        
        count = build_vector_db(rules_json, vector_db, force_rebuild=True)
        print(f"\n✓ Successfully built vector DB with {count} documents")
        print(f"  Location: {vector_db}")
        
    else:
        # Test mode
        vector_db = Path("cache/rules_vector_db")
        if not vector_db.exists():
            print("Error: Vector DB not found. Run with 'build' argument first.")
            sys.exit(1)
        
        rag = RulesRAG(vector_db, enable_reformulation=False)  # No LLM for simple test
        
        test_query = "Do I need to file a flight plan?"
        print(f"\nTest query: '{test_query}'")
        print(f"Country: FR\n")
        
        results = rag.retrieve_rules(test_query, countries=["FR"], top_k=3)
        
        for i, result in enumerate(results, 1):
            print(f"{i}. [{result['country_code']}] {result['question_text']}")
            print(f"   Similarity: {result['similarity']:.3f}")
            print(f"   Category: {result['category']}")
            print()

