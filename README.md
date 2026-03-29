# RolePlay-LLM (Qwen 3.5 Fine-Tuning)

This project is a dedicated pipeline for fine-tuning **Qwen 3.5** specifically for **RolePlay** capabilities. The project covers the full lifecycle from data collection to final model evaluation.

## Project Structure

- `src/data_collection/`: Tools and scripts for gathering roleplay dialogue data.
- `src/data_cleaning/`: Pipelines for filtering, deduplication, and PII scrubbing.
- `src/dataset_generation/`: Conversion scripts to format data for Qwen's SFT (Supervised Fine-Tuning).
- `src/fine_tuning/`: Training scripts and configurations (LoRA/QLoRA etc.).
- `data/`: Local storage for dataset files (ignored by git).

## Getting Started

### 1. Requirements
Ensure you have Python 3.10+ installed. Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Project Rules
Refer to `.agent/instructions/rules.md` for coding standards and data handling guidelines.

## Development Roadmap
1. [ ] Dataset Cleaning Tool (Current Stage)
2. [ ] Data Collection Pipeline
3. [ ] Qwen Format Generator
4. [ ] Fine-Tuning Execution