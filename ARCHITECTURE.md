# Architecture Overview

## Layers

### 1. Input Layer
- CSV (Revolut)
- Excel (HDFC)
- PDF (Advanzia - upcoming)

---

### 2. Parsing Layer (parsers/)
Converts raw bank formats → normalized dataframe

---

### 3. Processing Layer (pipeline/)

#### normalize.py
- cleans data
- standardizes columns

#### rule_engine.py
- applies merchant rules
- supports substring + regex (future)

#### llm_categorizer.py
- fallback when no rule found
- uses Ollama (local LLM)

---

### 4. API Layer (api/)
- /import → upload + process
- /preview → view transactions
- /unknown → detect uncategorized

---

### 5. UI Layer (frontend/)
- dashboard
- import screen
- merchant review

---

## Data Flow

File → Parser → Normalize → Categorize → Output → Preview → Approve → Learn

---

## Key Principle

Rules > LLM

LLM is fallback only.
System should become rule-driven over time.