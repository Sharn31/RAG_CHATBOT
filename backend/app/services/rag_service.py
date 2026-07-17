
"""
RAG Service - Orchestrates the end-to-end RAG pipeline.
"""

import re
from datetime import date
from typing import List, Optional, Dict, Any
from enum import Enum

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from app.config import settings
from app.schemas.response import UploadResponse, ChatResponse, SourceChunk
from app.services import (
    pdf_service,
    chunk_service,
    embedding_service,
    vector_service,
    llm_service,
    memory_service,
)
from app.utils.helpers import (
    generate_session_id,
    truncate_snippet,
    dedupe_sources_by_page,
)
from app.utils.prompt import NOT_FOUND_TOKEN
from datetime import date, datetime


# ============================================================================
# Document Type Detection
# ============================================================================

class DocumentType(Enum):
    RESUME = "resume"
    RESEARCH = "research"
    LEGAL = "legal"
    GENERAL = "general"


def detect_document_type(first_chunks: List[Dict]) -> DocumentType:
    text = " ".join(c.get("text", "")[:500] for c in first_chunks[:2]).lower()

    resume_keywords = [
        "experience", "education", "skills", "employment",
        "qualification", "cv", "curriculum", "profile",
        "contact", "phone", "email", "linkedin"
    ]

    if sum(1 for kw in resume_keywords if kw in text) >= 3:
        return DocumentType.RESUME

    if "abstract" in text or "introduction" in text:
        return DocumentType.RESEARCH

    if "hereby" in text or "whereas" in text or "agreement" in text:
        return DocumentType.LEGAL

    return DocumentType.GENERAL


# ============================================================================
# Entity Extraction for Resumes
# ============================================================================

class ResumeEntityExtractor:
    @staticmethod
    def extract_name(text: str) -> Optional[str]:
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$', line):
                return line
            if re.match(r'^[A-Z]+(?:\s+[A-Z]+){1,3}$', line) and len(line.split()) <= 4:
                return line.title()
        return None

    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        return match.group(0) if match else None

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        match = re.search(r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b', text)
        return match.group(0) if match else None

    @staticmethod
    def extract_entities(chunks: List[Dict]) -> Dict[str, str]:
        combined_text = " ".join(c.get("text", "") for c in chunks[:5])
        return {
            "name": ResumeEntityExtractor.extract_name(combined_text),
            "email": ResumeEntityExtractor.extract_email(combined_text),
            "phone": ResumeEntityExtractor.extract_phone(combined_text),
        }


# ============================================================================
# Experience / Tenure Calculation
# ============================================================================

class ExperienceCalculator:
    """Computes total work experience deterministically from date ranges
    found anywhere in the document, instead of asking the LLM to do date
    arithmetic on raw text (which it does unreliably).

    Generalized (not resume-only): it's only invoked when the question asks
    about total experience/tenure, and if no date ranges are found - e.g. on
    a document that isn't a resume/CV at all - it simply returns None and
    the caller falls through to normal retrieval, so this is safe to run
    unconditionally regardless of document type.
    """

    # Both sides accept an optional month name before the year, so this
    # matches "Jan 2026 - Present", "Jun 2024 - Jan 2025", AND year-only
    # ranges like "2021 - 2024" (common for degree durations). Year is
    # restricted to 19xx/20xx to avoid false-matching arbitrary 4-digit
    # numbers (phone digits, percentages, etc.) elsewhere in the text.
    _DATE_TOKEN = (
        r'(?:[A-Za-z]{3,9}\.?\s+(?:19|20)\d{2}'      # "Jun 2024" / "June 2024"
        r'|(?:0?[1-9]|1[0-2])/(?:19|20)\d{2})'         # "06/2024"
    )

    DATE_RANGE_PATTERN = re.compile(
        rf'({_DATE_TOKEN})\s*[-–—]\s*(Present|present|{_DATE_TOKEN})'
    )

    TOTAL_EXPERIENCE_TRIGGERS = [
        "total experience", "years of experience", "how much experience",
        "how many years", "overall experience", "total work experience",
    ]

    @staticmethod
    def is_total_experience_question(question: str) -> bool:
        q = question.lower().strip()
        return any(t in q for t in ExperienceCalculator.TOTAL_EXPERIENCE_TRIGGERS)

    @staticmethod
    def _parse_match(match) -> Optional[tuple]:
        try:
            start = date_parser.parse(match.group(1), fuzzy=True, default=datetime(2000, 1, 1)).date()
        except (ValueError, OverflowError):
            return None

        end_str = match.group(2)
        if end_str.lower() == "present":
            end = date.today()
        else:
            try:
                end = date_parser.parse(end_str, fuzzy=True, default=datetime(2000, 1, 1)).date()
            except (ValueError, OverflowError):
                return None

        if end < start:
            return None
        return (start, end)
    

    EDUCATION_KEYWORDS = [
        "bachelor", "b.e.", "b.tech", "bca", "mca", "master",
        "university", "college", "school", "cgpa", "engineering",
        "secondary", "cbse", "degree", "10th", "12th",
    ]

    CONTEXT_WINDOW_BEFORE = 80  # chars to look back from the match for education keywords
    CONTEXT_WINDOW_AFTER = 20   # chars to look forward

    @staticmethod
    def compute_total(chunks: List[Dict]) -> Optional[str]:
        seen_matches = set()
        ranges = []

        for c in chunks:
            text = c.get("text", "")
            for match in ExperienceCalculator.DATE_RANGE_PATTERN.finditer(text):
                raw = match.group(0)
                if raw in seen_matches:
                    continue

                start_idx = max(0, match.start() - ExperienceCalculator.CONTEXT_WINDOW_BEFORE)
                end_idx = min(len(text), match.end() + ExperienceCalculator.CONTEXT_WINDOW_AFTER)
                context = text[start_idx:end_idx].lower()

                if any(kw in context for kw in ExperienceCalculator.EDUCATION_KEYWORDS):
                    continue  # this date range sits next to education-related text - skip it

                seen_matches.add(raw)
                r = ExperienceCalculator._parse_match(match)
                if r:
                    ranges.append(r)

        if not ranges:
            return None

        total_months = sum(
            relativedelta(end, start).years * 12 + relativedelta(end, start).months
            for start, end in ranges
        )
        years, months = divmod(total_months, 12)
        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        return " and ".join(parts) if parts else "less than a month"
    

# ============================================================================
# Query Optimization
# ============================================================================

class QueryOptimizer:
    """Transform user question into better search queries."""

    PRONOUNS = {"my", "me", "i", "his", "her", "their", "it", "its"}

    # Keyed by topic, matched by individual trigger WORDS present anywhere in
    # the question (checked before pronoun stripping - see optimize()).
    #
    # The "experience"/"work" expansions deliberately avoid generic words
    # like "career" or "background" - those also appear naturally in resume
    # summary/education sections ("strong foundation... background in..."),
    # so including them was pulling retrieval toward the wrong chunk (e.g.
    # education/CGPA) instead of the actual employment dates. The words
    # below are chosen to stay specific to job/employment content.
    TOPIC_EXPANSIONS = {
        "name":       (["name"],                        ["name", "full name", "called"]),
        "email":      (["email"],                       ["email", "email address", "contact"]),
        "phone":      (["phone", "number", "telephone"], ["phone", "telephone", "contact number"]),
        "skills":     (["skill", "skills"],              ["skills", "expertise", "proficiencies"]),
        "work":       (["work", "company", "employer"],  ["company", "employer", "job title", "role", "employment"]),
        "experience": (["experience", "years", "tenure"], ["work experience", "employment history", "job", "company", "duration"]),
    }

    @staticmethod
    def needs_expansion(question: str) -> bool:
        words = question.lower().split()
        return len(words) <= 5

    @staticmethod
    def expand_short_question(question: str) -> str:
        question_lower = question.lower().strip('?').strip()
        words = set(question_lower.split())

        for topic, (triggers, expansions) in QueryOptimizer.TOPIC_EXPANSIONS.items():
            if any(t in words for t in triggers):
                return f"{question} {' '.join(expansions)}"

        if words & QueryOptimizer.PRONOUNS:
            return f"{question} profile information personal details"

        return question

    @staticmethod
    def remove_pronouns_for_search(question: str) -> str:
        words = question.lower().split()
        filtered = [w for w in words if w.strip('?').strip() not in QueryOptimizer.PRONOUNS]
        return " ".join(filtered) if filtered else question

    @staticmethod
    @staticmethod
    def optimize(question: str, document_type: DocumentType) -> str:
        query = question

        if QueryOptimizer.needs_expansion(query):
            query = QueryOptimizer.expand_short_question(query)

        query = QueryOptimizer.remove_pronouns_for_search(query)

        return query


# ============================================================================
# Multi-Layer Retrieval
# ============================================================================

class MultiLayerRetrieval:
    @staticmethod
    def hybrid_search(
        session_id: str,
        question: str,
        entities: Dict[str, str],
        top_k: int = 5,
    ) -> List[Dict]:
        store = vector_service.get_vector_store()
        query_embedding = embedding_service.embed_query(question)
        results = store.query_session(session_id, query_embedding, top_k)
        return sorted(results, key=lambda x: x["distance"])


# ============================================================================
# Identity Question Shortcut
# ============================================================================

IDENTITY_QUESTION_PATTERNS = {
    "name": ["what is my name", "whats my name", "who am i", "my name"],
    "email": ["what is my email", "whats my email", "my email"],
    "phone": ["what is my phone", "whats my phone", "my phone number", "my number"],
}


def match_identity_question(question: str) -> Optional[str]:
    q = question.lower().strip().strip('?').strip()
    for entity_key, patterns in IDENTITY_QUESTION_PATTERNS.items():
        if any(p in q for p in patterns):
            return entity_key
    return None


# ============================================================================
# Main RAG Functions
# ============================================================================

def ingest_pdf(pdf_path: str, filename: str) -> UploadResponse:
    pages = pdf_service.extract_pages(pdf_path)
    if not pages:
        raise ValueError("No extractable text found in PDF.")

    chunks = chunk_service.build_chunks(pages)
    if not chunks:
        raise ValueError("PDF text could not be split into chunks.")

    doc_type = detect_document_type(chunks)

    entities = {}
    if doc_type == DocumentType.RESUME:
        entities = ResumeEntityExtractor.extract_entities(chunks)

    session_id = generate_session_id()

    chunk_service.cache_chunks(session_id, filename, chunks)

    texts = [c["text"] for c in chunks]
    embeddings = embedding_service.embed_texts(texts)
    embedding_service.cache_embeddings(session_id, embeddings)

    store = vector_service.get_vector_store()
    store.create_session_collection(session_id, chunks, embeddings)

    memory = memory_service.get_memory_service()
    memory.create_session(session_id, filename, len(pages))

    memory.set_metadata(session_id, {
        "document_type": doc_type.value,
        "entities": entities,
    })

    return UploadResponse(
        session_id=session_id,
        filename=filename,
        num_pages=len(pages),
        num_chunks=len(chunks),
    )


def answer_question(session_id: str, question: str) -> ChatResponse:
    memory = memory_service.get_memory_service()

    if not memory.exists(session_id):
        raise LookupError("Session not found. Upload a PDF first.")

    metadata = memory.get_metadata(session_id) or {}
    doc_type = DocumentType(metadata.get("document_type", "general"))
    entities = metadata.get("entities", {})

    # Fast path 1: identity questions, answered from pre-extracted entities.
    # Naturally a no-op on non-resume documents, since `entities` is empty
    # for those - falls straight through to normal retrieval below.
    entity_key = match_identity_question(question)
    if entity_key and entities.get(entity_key):
        answer_text = f"Your {entity_key} is {entities[entity_key]}."
        print(f"\nIdentity shortcut matched: {entity_key} = {entities[entity_key]}")
        memory.append_turn(session_id, "user", question)
        memory.append_turn(session_id, "assistant", answer_text)
        return ChatResponse(answer=answer_text, sources=[], in_scope=True)

    # Fast path 2: total-experience questions, answered via deterministic
    # date math over ALL cached chunks. Not gated on doc_type == RESUME -
    # if a document has no parseable date ranges (e.g. it isn't a resume/CV
    # at all), compute_total simply returns None and this falls through to
    # normal retrieval, so it's safe on any document type.
    if ExperienceCalculator.is_total_experience_question(question):
        all_chunks = chunk_service.get_cached_chunks(session_id)
        total = ExperienceCalculator.compute_total(all_chunks)
        if total:
            answer_text = (
                f"Based on the roles listed in the document, the total experience "
                f"is approximately {total}."
            )
            print(f"\nExperience shortcut matched: {total}")
            memory.append_turn(session_id, "user", question)
            memory.append_turn(session_id, "assistant", answer_text)
            return ChatResponse(answer=answer_text, sources=[], in_scope=True)
        print("\nExperience shortcut found no parseable date ranges - falling through to retrieval")

    optimized_question = QueryOptimizer.optimize(question, doc_type)

    print("\n" + "=" * 60)
    print("QUERY OPTIMIZATION")
    print("=" * 60)
    print(f"Original:   {question}")
    print(f"Optimized:  {optimized_question}")
    print(f"Doc Type:   {doc_type.value}")
    if entities.get("name"):
        print(f"Found Name: {entities.get('name')}")

    retrieved = MultiLayerRetrieval.hybrid_search(
        session_id,
        optimized_question,
        entities,
        top_k=settings.TOP_K,
    )

    print("\n" + "=" * 60)
    print("RETRIEVED CONTEXT")
    print("=" * 60)

    if not retrieved:
        print("No chunks retrieved.")
    else:
        for i, chunk in enumerate(retrieved, start=1):
            print(
                f"\nChunk {i}"
                f"\n  Page:     {chunk['page']}"
                f"\n  Distance: {chunk['distance']:.4f}"
                f"\n  Text:     {chunk['text'][:200]}..."
            )

    top_distance = retrieved[0]["distance"] if retrieved else None
    top_distance_str = f"{top_distance:.4f}" if top_distance is not None else "N/A"

    if not retrieved or top_distance > settings.SIMILARITY_THRESHOLD:
        print(f"\nSimilarity gate failed: {top_distance_str} > {settings.SIMILARITY_THRESHOLD}")
        return ChatResponse(
            answer=settings.OUT_OF_SCOPE_MESSAGE,
            sources=[],
            in_scope=False,
        )

    print(f"\nSimilarity gate passed: {top_distance_str} <= {settings.SIMILARITY_THRESHOLD}")

    raw_history = memory.get_history(session_id)
    history = [{"role": h["role"], "content": h["content"]} for h in raw_history]

    raw_answer = llm_service.generate_answer(question, retrieved, history)

    if NOT_FOUND_TOKEN in raw_answer:
        print("LLM gate failed: NOT_FOUND_TOKEN detected")
        return ChatResponse(
            answer=settings.OUT_OF_SCOPE_MESSAGE,
            sources=[],
            in_scope=False,
        )

    print("LLM gate passed")

    memory.append_turn(session_id, "user", question)
    memory.append_turn(session_id, "assistant", raw_answer)

    sources: List[SourceChunk] = [
        SourceChunk(page=c["page"], snippet=truncate_snippet(c["text"]))
        for c in retrieved
    ]
    sources = dedupe_sources_by_page(sources)

    print(f"Answer generated with {len(sources)} source(s)")

    return ChatResponse(answer=raw_answer, sources=sources, in_scope=True)


def delete_session(session_id: str) -> None:
    vector_service.get_vector_store().delete_session(session_id)
    memory_service.get_memory_service().delete(session_id)