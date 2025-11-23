#!/usr/bin/env python3
"""
Wrapper script to run LangSmith evaluations from project root.
This ensures PYTHONPATH is set correctly.
"""
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import and run the evaluation script
from tests.langsmith_tests.runners.run_evaluation import main

if __name__ == "__main__":
    main()
