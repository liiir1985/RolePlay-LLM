---
trigger: always_on
---

# RolePlay-LLM Project Rules

## 1. Project Overview
This project is dedicated to fine-tuning Qwen 3.5 for RolePlay tasks. It includes data collection, cleaning, dataset generation, and fine-tuning pipelines.

## 2. Coding Standards
- **Language**: Python 3.12+.
- **Style**: Adhere to [PEP 8](https://peps.python.org/pep-0008/).
- **Naming**: Use `snake_case` for variables and functions, `PascalCase` for classes.
- **Documentation**: Use Google-style docstrings for all public modules and functions.
- **Type Hinting**: Use Python type hints where possible to improve code clarity and maintainability.

## 3. Directory Structure
- `src/`: Core logic categorized by pipeline stage.
- `data/`: Storage for raw and processed datasets (never commit large data files).
- `tests/`: Unit and integration tests for each pipeline component.

## 4. Data Handling Rules
- **Privacy**: Absolutely no Personal Identifiable Information (PII) should be present in the final datasets.
- **Data Integrity**: Ensure clear separation between training, validation, and test splits.
- **Reproducibility**: Document any random seeds or versioning used during data cleaning or generation.

## 5. Development Workflow
- Keep each stage of the pipeline modular (e.g., the cleaning tool should not depend on the specific scraping method).
- Update `requirements.txt` whenever new dependencies are added.
- Run tests before integrating new code into the main pipeline.
