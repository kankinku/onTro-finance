import requests
import subprocess
import time
from src.core.config import settings
from src.core.logger import logger

def check_and_pull_ollama_model():
    """
    Check if the required Ollama model exists.
    If not, attempt to pull it via command line.
    """
    model_name = settings.OLLAMA_MODEL
    base_url = settings.OLLAMA_BASE_URL
    
    logger.info(f"[Init] Checking Ollama model: {model_name}...")

    # 1. Check if Ollama is running
    try:
        # List local models
        # API: GET /api/tags
        res = requests.get(f"{base_url}/api/tags", timeout=5)
        if res.status_code != 200:
            logger.warning("[Init] Could not talk to Ollama API. Is 'ollama serve' running?")
            return
        
        models = res.json().get('models', [])
        # Normalizing model names can be tricky (e.g. "llama3:latest" vs "llama3")
        # We'll do a simple substring check
        found = any(model_name in m.get('name', '') for m in models)
        
        if found:
            logger.info(f"[Init] Model '{model_name}' found locally. Ready.")
            return
        
    except Exception as e:
        logger.warning(f"[Init] Connection to Ollama failed: {e}")
        return

    # 2. Pull model if not found
    logger.info(f"[Init] Model '{model_name}' NOT found. Attempting to pull (this may take time)...")
    try:
        # We use subprocess to stream the pull output to console
        # 'ollama pull <model>'
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Simple wait loop (or stream output)
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                logger.info(f"[Ollama Pull] {output.strip()}")
                
        if process.returncode == 0:
            logger.info(f"[Init] Successfully pulled '{model_name}'.")
        else:
            logger.error(f"[Init] Failed to pull model. Return code: {process.returncode}")
            
    except FileNotFoundError:
        logger.error("[Init] 'ollama' command not found in PATH. Please install Ollama.")
    except Exception as e:
        logger.error(f"[Init] Error during model pull: {e}")
