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


class RulesRAG:
    """
    RAG system for aviation rules retrieval.
    
    Provides semantic search over aviation regulations with country filtering
    and query reformulation for improved accuracy.
    """
    
    def __init__(
        self,
        vector_db_path: Path | str,
        embedding_model: str = "all-MiniLM-L6-v2",
        enable_reformulation: bool = True,
        llm: Optional[Any] = None,
    ):
        """
        Initialize RAG system.
        
        Args:
            vector_db_path: Path to ChromaDB storage directory
            embedding_model: Name of embedding model to use
            enable_reformulation: Whether to reformulate queries for better matching
            llm: Optional LLM instance for reformulation
        """
        self.vector_db_path = Path(vector_db_path)
        self.embedding_model = embedding_model
        
        # Initialize embedding provider
        self.embedding_provider = EmbeddingProvider(embedding_model)
        
        # Initialize query reformulator
        self.enable_reformulation = enable_reformulation
        if enable_reformulation:
            self.reformulator = QueryReformulator(llm)
        else:
            self.reformulator = None
        
        # Initialize ChromaDB
        logger.info(f"Initializing ChromaDB at {self.vector_db_path}")
        self.client = chromadb.PersistentClient(
            path=str(self.vector_db_path),
            settings=Settings(
                anonymized_telemetry=False,  # Disable telemetry for privacy
            )
        )
        
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
    
    def retrieve_rules(
        self,
        query: str,
        countries: Optional[List[str]] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        reformulate: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant rules using semantic search.
        
        Args:
            query: User query text
            countries: List of ISO-2 country codes to filter by (e.g., ["FR", "GB"])
            top_k: Number of results to return per country
            similarity_threshold: Minimum similarity score (0-1)
            reformulate: Override default reformulation setting
        
        Returns:
            List of matching rules with metadata, sorted by similarity score
        """
        if self.collection is None:
            logger.error("Collection not initialized")
            return []
        
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
        
        # Build filters
        where_filter = None
        if countries:
            countries_upper = [c.upper() for c in countries]
            where_filter = {"country_code": {"$in": countries_upper}}
        
        # Calculate n_results
        n_results = top_k * len(countries) if countries else top_k
        
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
        
        # Format results
        matches = []
        if results and results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][i] if results['distances'] else 1.0
                # Convert distance to similarity score (cosine distance → similarity)
                # ChromaDB uses L2 distance, normalize to 0-1 range
                similarity = max(0, 1 - (distance / 2))
                
                if similarity < similarity_threshold:
                    continue
                
                metadata = results['metadatas'][0][i]
                
                # Parse JSON fields
                try:
                    links = json.loads(metadata.get("links", "[]"))
                except (json.JSONDecodeError, TypeError):
                    links = []
                
                try:
                    tags = json.loads(metadata.get("tags", "[]"))
                except (json.JSONDecodeError, TypeError):
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
    vector_db_path: Path | str,
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
        vector_db_path: Path to ChromaDB storage directory
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
    vector_db_path = Path(vector_db_path)
    
    # Load rules.json
    if not rules_json_path.exists():
        raise FileNotFoundError(f"Rules file not found: {rules_json_path}")
    
    logger.info(f"Loading rules from {rules_json_path}")
    with open(rules_json_path, 'r', encoding='utf-8') as f:
        rules_data = json.load(f)
    
    questions = rules_data.get("questions", [])
    if not questions:
        raise ValueError(f"No questions found in {rules_json_path}")
    
    logger.info(f"Found {len(questions)} questions")
    
    # Initialize embedding provider
    embedding_provider = EmbeddingProvider(embedding_model)
    
    # Initialize ChromaDB
    vector_db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(vector_db_path),
        settings=Settings(anonymized_telemetry=False)
    )
    
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
    
    # Process each question for each country
    documents = []
    metadatas = []
    ids = []
    
    for question in questions:
        question_id = question.get("question_id")
        question_text = question.get("question_text", "")
        
        if not question_id or not question_text:
            logger.warning(f"Skipping question with missing ID or text: {question}")
            continue
        
        answers_by_country = question.get("answers_by_country", {})
        
        for country_code, answer in answers_by_country.items():
            doc_id = f"{question_id}_{country_code}"
            
            documents.append(question_text)
            metadatas.append({
                "question_id": question_id,
                "country_code": country_code.upper(),
                "category": question.get("category", ""),
                "tags": json.dumps(question.get("tags", [])),
                "answer_html": answer.get("answer_html", ""),
                "links": json.dumps(answer.get("links", [])),
                "last_reviewed": answer.get("last_reviewed", ""),
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

