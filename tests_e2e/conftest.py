import pytest
import subprocess
import time
import urllib.request

@pytest.fixture(scope="session", autouse=True)
def start_frontend_server():
    proc = subprocess.Popen(
        [
            "python",
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "3000",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if proc.poll() is not None:
                raise RuntimeError("Servidor FastAPI encerrou antes de ficar disponível.")
            try:
                urllib.request.urlopen("http://127.0.0.1:3000/health", timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Servidor FastAPI não ficou disponível para os testes E2E.")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)
