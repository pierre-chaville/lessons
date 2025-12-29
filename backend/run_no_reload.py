"""
Development server without auto-reload (faster startup, no multiprocessing issues).
Restart manually when you make changes.
"""
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,  # Disable reload to avoid multiprocessing
        log_level="info"
    )

