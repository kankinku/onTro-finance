import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    APP_NAME: str = "OntoFin System"
    ENV: str = "dev"
    
    # LLM (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2" # Default model, can be overridden env var
    
    # Database
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    
    # Persistence
    PERSISTENCE_FILE: str = "ontofin_graph.json"

    # External APIs
    FRED_API_KEY: str = "" # User must provide this in .env
    
    class Config:
        env_file = ".env"

settings = Settings()
