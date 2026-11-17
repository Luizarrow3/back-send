import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.cpf import limpar_cpf, validar_cpf


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nome: str
    perfil: str


class UsuarioCreate(BaseModel):
    email: str
    nome: str = Field(..., min_length=2, max_length=150)
    password: str = Field(..., min_length=10)
    perfil: str = "OPERADOR"


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nome: str
    perfil: str
    ativo: bool


class AuditoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int | None = None
    entidade: str
    entidade_id: int | None = None
    acao: str
    detalhes: str | None = None
    criado_em: object


class PessoaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str = Field(..., min_length=2, max_length=150)
    cpf: str = Field(..., min_length=11, max_length=14)
    sexo: Literal["FEMININO", "MASCULINO", "OUTRO"]
    data_nascimento: date

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, value: str) -> str:
        nome = re.sub(r"\s+", " ", value).strip()
        if len(nome) < 2:
            raise ValueError("O nome deve conter ao menos 2 caracteres")
        return nome

    @field_validator("cpf")
    @classmethod
    def validar_cpf_cadastral(cls, value: str) -> str:
        if not re.fullmatch(r"[\d.\-\s]+", value):
            raise ValueError("CPF deve conter somente números e máscara")
        cpf = limpar_cpf(value)
        if not validar_cpf(cpf):
            raise ValueError("CPF inválido")
        return cpf

    @field_validator("data_nascimento")
    @classmethod
    def validar_data_nascimento(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("A data de nascimento não pode estar no futuro")
        return value


class PessoaUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str | None = None
    sexo: Literal["FEMININO", "MASCULINO", "OUTRO"] | None = None
    data_nascimento: date | None = None
    motivo_rejeicao: str | None = None

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, value: str | None) -> str | None:
        if value is None:
            return None
        nome = re.sub(r"\s+", " ", value).strip()
        if len(nome) < 2:
            raise ValueError("O nome deve conter ao menos 2 caracteres")
        return nome

    @field_validator("data_nascimento")
    @classmethod
    def validar_data_nascimento(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("A data de nascimento não pode estar no futuro")
        return value


class PessoaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    cpf: str
    cpf_mascarado: str
    sexo: str
    data_nascimento: date
    status: str
    usuario_id: int | None = None


class PessoaPageResponse(BaseModel):
    items: list[PessoaResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ValidacaoFacialRequest(BaseModel):
    correspondencia_simulada: bool


class ValidacaoFacialResponse(BaseModel):
    id: int
    pessoa_id: int
    resultado: str
    modo_simulacao: bool
    assertividade_simulada: float
    criado_em: datetime
