from typing import List, Optional

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
