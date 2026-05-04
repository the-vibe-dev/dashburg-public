from runner_app.config import load_config

cfg = load_config()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("runner_app.main:app", host=cfg.host, port=cfg.port, reload=False)
