# Personal Finz

AI-powered personal finance automation system.

## Core Features

- CSV/PDF ingestion
- Transaction normalization
- Rule-based categorization
- LLM fallback categorization
- Preview & approval workflow
- Self-learning merchant rules

---

## Project Structure

- api/ → FastAPI backend
- pipeline/ → data processing engine
- parsers/ → bank-specific parsers
- frontend/ → UI screens (static HTML)
- db/ → database logic

---

## Execution Flow

Input File (CSV/PDF)
→ Parser
→ Normalizer
→ Categorizer (Rules → LLM fallback)
→ Output CSV
→ Preview & Approval
→ Save rules

---

## Run Locally

uvicorn api.main:app --reload --port 9001
docker compose up -d