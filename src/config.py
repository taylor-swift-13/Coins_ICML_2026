from dataclasses import dataclass, field
from pathlib import Path
import os

# Global proof/spec settings
# TYPE only determines the input directory path, no other logic differences
TYPE = "human"
MODEL_NAME = "deepseek-v4-pro"

# Paths based on TYPE (TYPE only affects input directory)
# Use relative paths based on project root (parent of src/)
BASE_DIR = Path(__file__).parent.parent.resolve()
DATASET_PATH = str(BASE_DIR / "HumanEvalPlus.jsonl")
SPEC_INPUT_DIR = str(BASE_DIR / "spec" / TYPE / "input")
SPEC_OUTPUT_DIR = str(BASE_DIR / "spec" / TYPE / "output")
ROOT_DIR = str(BASE_DIR / "spec" / TYPE)

# Proof generation settings
MAX_ITERATIONS = 3  # Maximum iterations for proof generation (test case 0)
SKIP_ON_FIRST_FAIL = True  # For batch_test: stop at first failed test case


@dataclass
class LLMConfig:
    """LLM API configuration"""
    use_api_model: bool = True  # Control whether to use API model or local Transformers model
    api_model: str = "deepseek-v4-pro"  # Default API model
    api_key: str = field(default_factory=lambda: os.getenv("COINS_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("COINS_BASE_URL", "https://api.openai.com/v1"))
    api_temperature: float = 0.7  # Temperature parameter for API calls
