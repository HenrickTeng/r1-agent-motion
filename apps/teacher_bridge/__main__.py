import uvicorn


if __name__ == "__main__":
    uvicorn.run("apps.teacher_bridge.api:app", host="127.0.0.1", port=8765)
