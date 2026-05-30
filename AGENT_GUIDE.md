# Agent Guide (IMPORTANT)

You are working on an AI-powered finance system.

## Your Responsibilities

- Improve modularity
- Avoid breaking existing pipeline
- Keep logic separated (parser / rules / LLM)
- Prefer simple deterministic logic over complex AI

---

## DO NOT

- Modify database structure blindly
- Break API contracts
- Hardcode bank-specific logic in core pipeline
- Overuse LLM when rules can solve it

---

## ALWAYS FOLLOW

### 1. Code Separation

- parser logic → parsers/
- categorization → engine/
- API → api/

---

### 2. Categorization Priority

1. Transfer detection
2. Rule match
3. LLM fallback
4. Save new rule

---

### 3. When Adding Features

- Must be reusable
- Must support multi-bank input
- Must not break existing CSV flow

---

## Current Limitations

- No regex rules yet
- No PDF parser
- No approval UI integration

---

## Current Focus

- Preview system
- Unknown merchant detection
- Rule learning system

---

## Goal

Make system:
- self-learning
- low manual effort
- scalable across banks