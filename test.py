import os

# Definição da estrutura de pastas e arquivos do microserviço
structure = {
    "app": {
        "__init__.py": "",
        "main.py": '''from fastapi import FastAPI
from app.routers import items

app = FastAPI(
    title="Microserviço FastAPI",
    description="Microserviço modular estruturado via script de automação",
    version="1.0.0",
)

app.include_router(items.router, prefix="/api/v1", tags=["items"])


@app.get("/health", tags=["Health Check"])
def health_check():
    return {"status": "healthy", "service": "active"}
''',
        "routers": {
            "__init__.py": "",
            "items.py": '''from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class Item(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


# Base de dados simulada em memória
fake_db = [
    Item(id=1, name="Item Alpha", description="Primeiro item de exemplo"),
    Item(id=2, name="Item Beta", description="Segundo item de exemplo"),
]


@router.get("/items", response_model=List[Item])
def list_items():
    return fake_db


@router.post("/items", response_model=Item, status_code=201)
def create_item(item: Item):
    for existing in fake_db:
        if existing.id == item.id:
            raise HTTPException(status_code=400, detail="Item com este ID já existe.")
    fake_db.append(item)
    return item
''',
        },
        "services": {
            "__init__.py": "",
        },
    },
    "tests": {
        "__init__.py": "",
        "test_main.py": '''from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "active"}


def test_list_items():
    response = client.get("/api/v1/items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2


def test_create_item():
    payload = {"id": 99, "name": "Item Teste", "description": "Criado via Pytest"}
    response = client.post("/api/v1/items", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 99
    assert data["name"] == "Item Teste"
''',
    },
    "requirements.txt": "fastapi\nuvicorn\npytest\n",
    "README.md": '''# Microserviço FastAPI
Este é um microserviço estruturado utilizando FastAPI, com endpoints para gerenciamento de itens e testes automatizados via Pytest.

## Estrutura do Projeto
- `app/`: Contém a aplicação FastAPI.
  - `main.py`: Ponto de entrada da aplicação.
  - `routers/`: Contém os roteadores da aplicação.
  - `services/`: Contém serviços auxiliares (atualmente vazio).
- `tests/`: Contém os testes automatizados.

## Como Executar
1. Instale as dependências:
```bash
pip install -r requirements.txt
```
2. Execute a aplicação:
```bash
uvicorn app.main:app --reload
```
3. Acesse a documentação interativa em `http://localhost:8000/docs`.
''',
}


def create_structure(base_dir: str, items: dict) -> None:
    for name, value in items.items():
        path = os.path.join(base_dir, name)

        if isinstance(value, dict):
            os.makedirs(path, exist_ok=True)
            create_structure(path, value)
            continue

        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:
            file.write(value)


if __name__ == "__main__":
    create_structure(os.getcwd(), structure)
    print(f"Estrutura do projeto criada em: {os.getcwd()}")
