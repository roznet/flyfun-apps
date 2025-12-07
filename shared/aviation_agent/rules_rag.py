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
    Provides text embeddings using configurable models.
    
    Supports both local models (sentence-transformers) and cloud-based models (OpenAI).
    Defaults to local model for development, can be configured for production.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding provider.
        
        Args:
            model_name: Name of the embedding model. Options:
                - "all-MiniLM-L6-v2" (local, 384 dims, fast)
                - "all-mpnet-base-v2" (local, 768 dims, better quality)
                - "text-embedding-3-small" (OpenAI, 1536 dims, excellent quality)
        """
        self.model_name = model_name
        
        if model_name.startswith("text-embedding-"):
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
        else:
            # Local sentence-transformers
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading local embedding model: {model_name}")
                self.model = SentenceTransformer(model_name)
                self.provider = "local"
                logger.info(f"✓ Loaded local model: {model_name}")
            except ImportError:
                raise ImportError(
                    "Local embeddings require sentence-transformers. "
                    "Install with: pip install sentence-transformers"
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
        
        if self.provider == "local":
            embeddings = self.model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            return embeddings.tolist()
        else:  # openai
            return self.model.embed_documents(texts)
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.
        
        Args:
            query: Query text to embed
            
        Returns:
            Embedding vector
        """
        if self.provider == "local":
            return self.embed([query])[0]
        else:  # openai
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


class Reranker:
    """
    Cross-encoder reranker for improved retrieval precision.
    
    Uses a cross-encoder model to rerank results after initial retrieval,
    providing better accuracy on top results.
    """
    
    # Default model - good balance of speed and quality
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    def __init__(self, model_name: str = None):
        """
        Initialize reranker.
        
        Args:
            model_name: Cross-encoder model name. Options:
                - "cross-encoder/ms-marco-MiniLM-L-6-v2" (fast, good quality)
                - "cross-encoder/ms-marco-TinyBERT-L-2-v2" (fastest, lower quality)
                - "cross-encoder/stsb-roberta-base" (slower, better for semantic similarity)
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None  # Lazy load
        
    @property
    def model(self):
        """Lazy load the cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading cross-encoder model: {self.model_name}")
                self._model = CrossEncoder(self.model_name)
                logger.info(f"✓ Loaded cross-encoder: {self.model_name}")
            except ImportError:
                logger.warning(
                    "Cross-encoder requires sentence-transformers. "
                    "Reranking disabled."
                )
                return None
            except Exception as e:
                logger.warning(f"Failed to load cross-encoder: {e}")
                return None
        return self._model
    
    def rerank(
        self, 
        query: str, 
        documents: List[Dict[str, Any]], 
        text_key: str = "question_text",
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using cross-encoder.
        
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
            
        if self.model is None:
            logger.debug("Reranker not available, returning original order")
            return documents
        
        # Prepare query-document pairs
        pairs = [(query, doc.get(text_key, "")) for doc in documents]
        
        try:
            # Get reranking scores
            scores = self.model.predict(pairs)
            
            # Add scores to documents and sort
            for doc, score in zip(documents, scores):
                doc["rerank_score"] = float(score)
            
            # Sort by rerank score (descending)
            reranked = sorted(documents, key=lambda x: x.get("rerank_score", 0), reverse=True)
            
            logger.debug(f"Reranked {len(documents)} documents")
            
            if top_k:
                return reranked[:top_k]
            return reranked
            
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
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
        embedding_model: str = "all-MiniLM-L6-v2",
        enable_reformulation: bool = True,
        enable_reranking: bool = True,
        llm: Optional[Any] = None,
        rules_manager: Optional[Any] = None,
    ):
        """
        Initialize RAG system.
        
        Args:
            vector_db_path: Path to ChromaDB storage directory (for local mode)
            vector_db_url: URL to ChromaDB service (for service mode). If provided, takes precedence over vector_db_path.
            embedding_model: Name of embedding model to use
            enable_reformulation: Whether to reformulate queries for better matching
            enable_reranking: Whether to use cross-encoder reranking
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
        
        # Initialize reranker (lazy loaded on first use)
        self.enable_reranking = enable_reranking
        if enable_reranking:
            self.reranker = Reranker()
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
            # Take top_k * 2 candidates for reranking to give reranker more options
            candidates = question_matches[:top_k * 2]
            if candidates:
                question_matches = self.reranker.rerank(
                    query=original_query,  # Use original query, not reformulated
                    documents=candidates,
                    text_key="question_text",
                    top_k=top_k
                )
                logger.debug(f"Reranked {len(candidates)} candidates to {len(question_matches)} results")
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
    embedding_model: str = "all-MiniLM-L6-v2",
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

