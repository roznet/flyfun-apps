#!/usr/bin/env python3
"""
Convert one or more country Excel files (Q/A format) into a normalized rules.json
that your MCP server can load.

Usage examples:
  # Minimal: add three files with explicit country codes
  python tools/xls_to_rules.py --out rules.json \
      --add GB "EU Rules UK.xlsx" \
      --add FR "EU Rules France.xlsx" \
      --add CH "EU Rules Switzerland.xlsx"

  # Append to an existing rules.json (merge/overwrite per country+question)
  python tools/xls_to_rules.py --out rules.json --append \
      --add DE "EU Rules Germany.xlsx"

Notes:
  - Expected columns (case-insensitive): Question, Answer, (optional) Links
  - If 'Links' is missing, URLs inside the Answer are auto-extracted.
  - last_reviewed is preserved from existing rules unless the answer changes (then it is set to today)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
  import pandas as pd  # type: ignore
except Exception as e:
  print("This tool requires pandas. Try: pip install pandas openpyxl", file=sys.stderr)
  raise

# --- Topic inference (lightweight, editable) --------------------------------
TOPIC_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"(customs|poe|port of entry|schengen|immigration)", re.I), "Customs/Schengen"),
    (re.compile(r"(fis|listening\s+squawk|listening\s+code|ats|clearance)", re.I), "FIS/ATC"),
    (re.compile(r"(ifr|vfr|cloudbreak|let-?down|night)\b", re.I), "IFR/VFR"),
    (re.compile(r"(airspace|class\s+[cdegb])", re.I), "Airspace"),
    (re.compile(r"(flight\s*plan|autorouter|skydemon|foreflight)", re.I), "Paperwork"),
]

URL_RE = re.compile(r"https?://\S+", re.I)

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)

def qid_for(question_raw: str, question_prefix: str) -> str:
    return f"{question_prefix}-{question_raw}" if question_prefix else question_raw
    
    #base = slugify(question_text)[:80]
    #h = hashlib.blake2b(question_text.encode("utf-8"), digest_size=6).hexdigest()
    #return f"{base}-{h}"

def infer_topic(question_text: str) -> Optional[str]:
    for pat, topic in TOPIC_RULES:
        if pat.search(question_text or ""):
            return topic
    return None

def extract_links(answer: str, explicit_links: Optional[str]) -> List[str]:
    links: List[str] = []
    if explicit_links:
        # split on common separators; keep only urls
        parts = re.split(r"[\s,;]+", explicit_links)
        links.extend([p for p in parts if p and p.lower().startswith(("http://","https://"))])
    for m in URL_RE.findall(answer or ""):
        if m not in links:
            links.append(m)
    return links

def find_col(df, candidates: List[str]) -> Optional[str]:
    cols = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        key = cand.lower()
        if key in cols:
            return cols[key]
    # fuzzy contains
    for k, orig in cols.items():
        if any(k.startswith(c.lower()) for c in candidates):
            return orig
    return None

def parse_tags(tags_str: Optional[str]) -> List[str]:
    if not tags_str:
        return []
    parts = [t.strip() for t in str(tags_str).split(",")]
    return [t for t in parts if t]

def load_definitions(defs_xlsx: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load question definitions from an Excel with headers:
    Raw Question, Question, Category, Tags.
    Returns mapping question_id -> { question_id, question_text, question_prefix, category, tags }.
    """
    xl = pd.read_excel(defs_xlsx, sheet_name=None)
    defs: Dict[str, Dict[str, Any]] = {}
    q_prefix = ""
    valid_prefixes = set()
    for _, df in xl.items():
        if df is None or df.empty:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        raw_col = find_col(df, ["Raw Question", "Raw", "Source Question"])
        q_col = find_col(df, ["Question", "Normalized Question", "Final Question"])
        cat_col = find_col(df, ["Category", "Categories"])
        tags_col = find_col(df, ["Tags", "Tag"])
        if not raw_col or not q_col:
            continue
        for _, row in df.iterrows():
            q_raw = str(row[raw_col]).strip() if pd.notna(row[raw_col]) else ""
            q_text = str(row[q_col]).strip() if pd.notna(row[q_col]) else ""
            if not q_raw and not q_text:
                q_prefix = ""
                continue
            if q_raw and not q_text:
                q_prefix = q_raw
                valid_prefixes.add(q_prefix)
                continue
            category = str(row[cat_col]).strip() if cat_col and pd.notna(row[cat_col]) else ""
            tags = parse_tags(str(row[tags_col]).strip()) if tags_col and pd.notna(row[tags_col]) else []
            qid = qid_for(q_raw, q_prefix)
            defs[qid] = {
                "question_id": qid,
                "question_raw": q_raw,
                "question_text": q_text,
                "question_prefix": q_prefix,
                "category": category,
                "tags": tags,
            }
    return {"definitions": defs, "valid_prefixes": list(valid_prefixes)}

def load_rules_for_country(country_code: str, xlsx_path: Path, definitions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse a country's rule spreadsheet; returns list of { question_id, question_raw, question_prefix, answer_html, links }.
    Supports both header and headerless formats; handles prefix rows.
    """
    country_code = country_code.upper()
    xl = pd.read_excel(xlsx_path, sheet_name=None)
    out: List[Dict[str, Any]] = []
    defs = definitions["definitions"]
    valid_prefixes = definitions["valid_prefixes"]
    inconsistent_qids = set()

    for sheet_name, df in xl.items():
        if df is None or df.empty:
            continue

        qcol = None
        acol = None
        lcol = None

        # Header-based first
        df.columns = [str(c).strip() for c in df.columns]
        qcol = find_col(df, ["Question","Questions","Q"])  # raw question text in source
        acol = find_col(df, ["Answer","Answers","A","Response"])
        lcol = find_col(df, ["Links","Link","Sources","Source"])

        # Fallback to headerless
        if not qcol or not acol:
            xl_no_header = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None)
            if xl_no_header is not None and not xl_no_header.empty:
                df = xl_no_header
                qcol = 0
                acol = 1
                if df.shape[1] > 2:
                    lcol = 2

        if qcol is None or acol is None:
            continue

        q_prefix = ""
        for _, row in df.iterrows():
            q_raw = str(row[qcol]).strip() if pd.notna(row[qcol]) else ""
            a = str(row[acol]).strip() if pd.notna(row[acol]) else ""
            if not q_raw and not a:
                q_prefix = ""
                continue
            if q_raw and not a and q_raw in valid_prefixes:
                q_prefix = q_raw
                continue
            
            explicit_links = str(row[lcol]).strip() if lcol is not None and pd.notna(row[lcol]) else None
            links = extract_links(a, explicit_links)
            qid = qid_for(q_raw, q_prefix)
            if qid not in defs:
                if qid == "":
                    # Empty question ID might be a continuation of the previous answer
                    if out and a:
                        previous_q = out[-1]
                        # Append answer text (with separator if previous answer exists)
                        if previous_q.get("answer_html"):
                            previous_q["answer_html"] += "<br>" + a
                        else:
                            previous_q["answer_html"] = a
                        # Merge links, avoiding duplicates
                        if "links" not in previous_q:
                            previous_q["links"] = []
                        existing_links = set(previous_q["links"])
                        new_links = [link for link in links if link not in existing_links]
                        previous_q["links"].extend(new_links)
                    else:
                        print("Warning: Empty question but no previous answer found", file=sys.stderr)
                        continue
                else:
                    inconsistent_qids.add(qid)
                    continue
            out.append({
                "question_id": qid,
                "question_raw": q_raw if qid != "" else previous_q["question_raw"],
                "question_prefix": q_prefix if qid != "" else previous_q["question_prefix"],
                "answer_html": a if qid != "" else previous_q["answer_html"],
                "links": links if qid != "" else previous_q["links"],
                "country_code": country_code,
            })
    if len(inconsistent_qids) > 0:
        print(f"Warning: {len(inconsistent_qids)} inconsistent question IDs found in {xlsx_path.name}", file=sys.stderr)
        for qid in inconsistent_qids:
            print(f"  <{qid}>", file=sys.stderr)
    return out

def merge_rules_with_definitions(
    existing: Dict[str, Any],
    definitions: Dict[str, Dict[str, Any]],
    country_results: List[Dict[str, Any]],
    review_date: str,
    history: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge parsed country results into the combined structure using definitions.
    Output schema:
    {
      "questions": [
        {
          "question_id": str,
          "question_text": str,
          "category": str,
          "tags": [str,...],
          "answers_by_country": {
            "FR": { "answer_html": str, "links": [str], "last_reviewed": str, "confidence": str }
          }
        }
      ]
    }
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    for q in existing.get("questions", []):
        if not isinstance(q, dict) or "question_id" not in q:
            continue
        by_id[q["question_id"]] = q
    defs = definitions["definitions"]
    history_by_id: Dict[str, Dict[str, Any]] = {}
    if history:
        for q in history.get("questions", []):
            if isinstance(q, dict) and q.get("question_id"):
                history_by_id[q["question_id"]] = q

    # Ensure all definitions exist as base questions
    for qid, d in defs.items():
        if qid not in by_id:
            by_id[qid] = {
                "question_id": qid,
                "question_raw": d["question_raw"],
                "question_text": d["question_text"],
                "question_prefix": d["question_prefix"],
                "category": d.get("category", ""),
                "tags": list(d.get("tags", [])),
                "answers_by_country": {},
            }
        else:
            existing_q = by_id[qid]
            if not existing_q.get("question_raw"):
                existing_q["question_raw"] = d["question_raw"]
            if not existing_q.get("question_prefix"):
                existing_q["question_prefix"] = d["question_prefix"]
            if "category" not in existing_q:
                existing_q["category"] = d.get("category", "")
            if "tags" not in existing_q:
                existing_q["tags"] = list(d.get("tags", []))
            if "answers_by_country" not in existing_q:
                existing_q["answers_by_country"] = {}

    # Merge country results
    inconsistent_qids = set()
    for rec in country_results:
        qid = rec.get("question_id", "").strip()
        cc = rec.get("country_code")
        ans = {
            "answer_html": rec.get("answer_html", ""),
            "links": rec.get("links", []),
        }
        d = defs.get(qid)
        if d is None:
            inconsistent_qids.add(qid)
            continue

        existing_answer = by_id[qid]["answers_by_country"].get(cc)
        if not existing_answer and history_by_id:
            existing_answer = (
                history_by_id.get(qid, {})
                .get("answers_by_country", {})
                .get(cc)
            )
            if existing_answer:
                existing_answer = dict(existing_answer)

        if existing_answer:
            existing_links = existing_answer.get("links", [])
            content_changed = (
                ans["answer_html"] != existing_answer.get("answer_html", "")
                or ans["links"] != existing_links
            )
            if content_changed:
                if review_date:
                    ans["last_reviewed"] = review_date
                by_id[qid]["answers_by_country"][cc] = ans
            else:
                # keep the existing answer (including last_reviewed) untouched
                if cc not in by_id[qid]["answers_by_country"]:
                    by_id[qid]["answers_by_country"][cc] = existing_answer
                continue
        else:
            if review_date:
                ans["last_reviewed"] = review_date
            by_id[qid]["answers_by_country"][cc] = ans

    out = {
        "questions": sorted(by_id.values(), key=lambda x: x.get("question_text", "").lower())
    }
    if len(inconsistent_qids) > 0:
        out["inconsistent_qids"] = list(inconsistent_qids)
        print(f"Warning: {len(inconsistent_qids)} inconsistent question IDs found", file=sys.stderr)
    return out

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Convert definitions + country Excel Q/A files into rules.json")
    p.add_argument("--out", required=True, help="Output rules.json path")
    p.add_argument("--defs", required=False, help="Definitions Excel path (Raw Question, Question, Category, Tags). Required if --add is used.")
    p.add_argument("--append", action="store_true", help="Append into existing rules.json if present")
    p.add_argument("--add", action="append", nargs=2, metavar=("CC","XLSX"),
                   help="Add Excel file for country code CC (ISO-2), can be repeated. If omitted, only rebuilds RAG from existing rules.json")
    
    # RAG vector database options
    p.add_argument("--build-rag", action="store_true", default=True,
                   help="Build vector database for RAG retrieval (default: True)")
    p.add_argument("--no-rag", action="store_false", dest="build_rag",
                   help="Skip vector database build")
    p.add_argument("--vector-db-path", default=None,
                   help="Path for vector database (local mode). Defaults to cache/rules_vector_db or VECTOR_DB_PATH env var")
    p.add_argument("--vector-db-url", default=None,
                   help="URL for ChromaDB service (service mode, takes precedence over --vector-db-path). Can also use VECTOR_DB_URL env var")
    p.add_argument("--embedding-model", default="all-MiniLM-L6-v2",
                   help="Embedding model for RAG (default: all-MiniLM-L6-v2)")
    
    args = p.parse_args(argv)

    out_path = Path(args.out)
    
    # If --add is provided, --defs is required
    if args.add:
        if not args.defs:
            p.error("--defs is required when using --add")
        defs_path = Path(args.defs).expanduser()
        if not defs_path.exists():
            print(f"Error: definitions file not found {defs_path}", file=sys.stderr)
            return 2
    else:
        # No --add commands: just rebuild RAG from existing rules.json
        if not out_path.exists():
            p.error(f"Output file {out_path} does not exist. Use --add to create rules.json from Excel files.")
        defs_path = None

    # Load existing rules.json if it exists
    history_data: Dict[str, Any] = {"questions": []}
    combined: Dict[str, Any] = {"questions": []}
    if out_path.exists():
        try:
            history_data = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(history_data, dict) or "questions" not in history_data:
                history_data = {"questions": []}
            # Use existing data as base
            if args.append or not args.add:
                combined = history_data
        except Exception:
            print(f"Warning: failed to parse existing {out_path}, ignoring previous data", file=sys.stderr)
            history_data = {"questions": []}
            if not args.add:
                print(f"Error: cannot rebuild RAG from invalid {out_path}", file=sys.stderr)
                return 2

    # Process --add commands if provided
    total_answers = 0
    if args.add:
        # defs_path is guaranteed to be Path here (checked above)
        assert defs_path is not None, "--defs is required when using --add"
        definitions = load_definitions(defs_path)
        
        for cc, fpath in args.add:
            xlsx = Path(fpath).expanduser()
            if not xlsx.exists():
                print(f"Error: file not found {xlsx}", file=sys.stderr)
                return 2
            country_results = load_rules_for_country(cc, xlsx, definitions)
            total_answers += len(country_results)
            review_date = dt.date.today().isoformat()
            combined = merge_rules_with_definitions(
                combined,
                definitions,
                country_results,
                review_date=review_date,
                history=history_data,
            )
            print(f"Loaded {len(country_results)} entries from {cc}:{xlsx.name}")

        # optional: mirror links_json for potential downstream loaders
        for q in combined.get("questions", []):
            answers_by_country = q.get("answers_by_country", {})
            for cc, ans in answers_by_country.items():
                if "links_json" not in ans:
                    ans["links_json"] = ans.get("links", [])

        # Write updated rules.json
        out_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
        num_q = len(combined.get('questions', []))
        print(f"Wrote {out_path} with {num_q} questions and {total_answers} country-answers.")
    else:
        # No --add: just report what we're working with
        num_q = len(combined.get('questions', []))
        total_answers = sum(len(q.get("answers_by_country", {})) for q in combined.get("questions", []))
        print(f"Using existing {out_path} with {num_q} questions and {total_answers} country-answers.")
    
    # Build vector database for RAG
    if args.build_rag:
        print(f"\nBuilding vector database with {args.embedding_model}...")
        try:
            # Import here to avoid dependency if not needed
            import sys
            import os
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from shared.aviation_agent.rules_rag import build_vector_db
            
            # Determine vector DB configuration: URL takes precedence, then path
            vector_db_url = args.vector_db_url or os.environ.get("VECTOR_DB_URL")
            vector_db_path = None
            if not vector_db_url:
                # Use path from args, env var, or default
                vector_db_path_str = args.vector_db_path or os.environ.get("VECTOR_DB_PATH", "cache/rules_vector_db")
                vector_db_path = Path(vector_db_path_str)
            
            doc_count = build_vector_db(
                rules_json_path=out_path,
                vector_db_path=vector_db_path,
                vector_db_url=vector_db_url,
                embedding_model=args.embedding_model,
                force_rebuild=True
            )
            if vector_db_url:
                print(f"✓ Vector database built with {doc_count} documents at {vector_db_url}")
            else:
                print(f"✓ Vector database built with {doc_count} documents at {vector_db_path}")
        except ImportError as e:
            print(f"Warning: Could not build vector database: {e}", file=sys.stderr)
            print("Install dependencies: pip install chromadb sentence-transformers", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Vector database build failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())