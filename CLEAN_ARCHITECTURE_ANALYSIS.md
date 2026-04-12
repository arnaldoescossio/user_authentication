# Análise de Aderência ao Clean Architecture

**Data:** Abril 2026  
**Projeto:** user_authent  
**Escala:** 6.5/10 - Bom começo com alguns problema de vazamento de dependências

---

## 1. Estrutura de Camadas

### ✅ Pontos Fortes

#### 1.1 Domain Layer (Núcleo) - Bem Isolado
```
domain/
├── entities/
│   └── user.py          ← Pydantic BaseModel puro, sem dependências externas
└── repositories/
    └── *_repository.py  ← Interfaces abstratas (Ports)
```

- **User entity** é completamente agnóstico de framework
- Sem ORM imports, sem dependências do FastAPI, sem Redis
- Responsabilidade única: representar conceitos de domínio
- **Repositories abstratos** definem contratos (Dependency Inversion Principle)

#### 1.2 Infrastructure Layer - Bem Separado
```
infrastructure/
├── database/
│   ├── models.py        ← ORM layer (SQLAlchemy)
│   └── user_repository.py ← Implementação concreta
├── cache/
│   ├── token_cache.py
│   └── redis_token_repository.py
└── security/
    ├── jwt.py
    └── password.py
```

✅ ORM models estão isolados, não vazam para o domínio
✅ Implementações concretas conversam com abstrações (mapping: `_to_domain()`, `_to_orm()`)

#### 1.3 API Layer - Adequado
```
api/v1/
├── endpoints/           ← Controllers
├── schemas.py           ← DTOs
└── router.py
```

Controladores são finos e delegam para serviços.

---

## 2. Fluxo de Dependências

### ⚠️ PROBLEMA #1: Violação de Boundary - Dependencies.py

**Arquivo:** `app/core/dependencies.py`

Este arquivo centraliza TODO o setup de dependências, mas está MISTURANDO responsabilidades:

```python
# ❌ Importações que violam a camada
from app.infrastructure.cache.token_cache import TokenCache  
from app.infrastructure.database.user_repository import SQLUserRepository
from app.infrastructure.database.audit_repository import SQLAuditRepository

# ❌ Acoplamento concreto
def get_user_repository(session) -> SQLUserRepository:  # Deveria ser AbstractUserRepository!
def get_audit_repository(session) -> SQLAuditRepository
```

**Problema:**
- Controllers e outros componentes importam de `dependencies.py`, que traz acoplamento à infraestrutura
- A injeção de dependência está trazendo tipos concretos (SQLUserRepository) para a superfície
- Viola o princípio de Dependency Inversion

**Impacto:**
- Camadas de apresentação têm visibilidade sobre infraestrutura
- Difícil trocar implementações (ex: SQL → NoSQL)

---

### ⚠️ PROBLEMA #2: Controllers Dependendo de Implementações Concretas

**Arquivo:** `app/api/v1/endpoints/users.py`

```python
from app.infrastructure.database.user_repository import SQLUserRepository  # ❌ Concreto!

@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    body: UserUpdateRequest,
    current_user: CurrentUser,
    repo: Annotated[SQLUserRepository, Depends(get_user_repository)],  # ❌ Tipo concreto aqui
) -> UserResponse:
```

**Problema:**
- Controller conhece `SQLUserRepository` (implementação)
- Deveria apenas conhecer `AbstractUserRepository` (interface)
- Viola o Dependency Inversion Principle

**Esperado:**
```python
repo: Annotated[AbstractUserRepository, Depends(get_user_repository)]
```

---

### ⚠️ PROBLEMA #3: Services com Dependências Concretas de Infrastructure

**Arquivo:** `app/services/user_service.py`

```python
from app.infrastructure.cache.token_cache import TokenCache  # ❌ Concreto!
from app.infrastructure.security.password import hash_password, verify_password  # ❌ Concreto!

class UserService:
    def __init__(
        self,
        user_repo: AbstractUserRepository,  # ✅ Interface (bom)
        token_cache: TokenCache,  # ❌ Concretismo!
    ) -> None:
```

**Problema:**
- `UserService` (Application Layer) depende de `TokenCache` (Infrastructure)
- Deveria depender de uma abstração
- Torna o serviço acoplado à implementação Redis
- Dificulta testes unitários (mock mais complexo)

**Esperado:**
```python
# Criar interface
class AbstractTokenCache(ABC):
    @abstractmethod
    async def set(...): ...
    
# Service usa interface
class UserService:
    def __init__(self, token_cache: AbstractTokenCache): ...
```

---

## 3. Camadas Bem Definidas ✅

| Camada | Localização | Cumprimento |
|--------|------------|------------|
| **Entities** | `domain/entities/` | ✅ Perfeito - puro, sem frameworks |
| **Use Cases** | `services/` | ⚠️ Bom, mas com vazamento a infraestrutura |
| **Interface Adapters** | `api/`, `core/` | ⚠️ Controllers dependem de concretos |
| **Frameworks** | `infrastructure/` | ✅ Bem isolado, bom mapeamento ORM |

---

## 4. Questões Específicas

### Schemas/DTOs - Localização Correta? ✅
```
app/api/v1/schemas.py  ← Localização correta
```
DTOs (Data Transfer Objects) estão no nível correto (Interface Adapters).

### Core Package - Responsabilidades
```
core/
├── config.py           ← ✅ OK (configurações)
├── dependencies.py     ← ❌ PROBLEMÁTICO (DI + factories)
├── exceptions.py       ← ✅ OK (shared exceptions)
├── logging.py          ← ✅ OK (cross-cutting)
├── pagination.py       ← ✅ OK (utilidade)
└── rate_limit.py       ← ✅ OK (cross-cutting)
```

**Problema:** `dependencies.py` centraliza toda a orquestração e importa concretos.

---

## 5. Princípios de Clean Architecture

| Princípio | Status | Detalhes |
|-----------|--------|----------|
| **Independência de Frameworks** | ⚠️ Parcial | Domain é independente ✅, mas presentation/application vazam |
| **Testabilidade** | ⚠️ Comprometida | Services com dependências concretas dificultam testes |
| **Independência de UI** | ✅ Sim | Endpoints poderiam ser substituídos por gRPC sem mudança em services |
| **Independência de BD** | ❌ Não | Controllers sabem de SQLUserRepository |
| **Independência de Qualquer Agência Externa** | ⚠️ Parcial | Infrastructure apenas, mas vazam para cima |

---

## 6. Recomendações de Refatoração

### 🔴 CRÍTICO: Extrair Abstrações de Token Cache

**Arquivo:** Criar `domain/repositories/token_repository.py`

```python
from abc import ABC, abstractmethod

class AbstractTokenCache(ABC):
    """Interface para armazenamento de tokens."""
    
    @abstractmethod
    async def store_refresh_token(self, jti: str, user_id: str, ttl_seconds: int) -> None: ...
    
    @abstractmethod
    async def get_refresh_token_owner(self, jti: str) -> str | None: ...
```

**Impacto:** Services não dependem mais de infraestrutura concreta.

---

### 🔴 CRÍTICO: Corrigir Types em dependencies.py

**Arquivo:** `app/core/dependencies.py`

Mudar:
```python
def get_user_repository(...) -> SQLUserRepository:
```

Para:
```python
def get_user_repository(...) -> AbstractUserRepository:
```

**Impacto:** Esconder implementações da camada de apresentação.

---

### 🟠 IMPORTANTE: Tipos em Controllers

**Arquivo:** `app/api/v1/endpoints/users.py`

Mudar:
```python
repo: Annotated[SQLUserRepository, Depends(get_user_repository)]
```

Para:
```python
repo: Annotated[AbstractUserRepository, Depends(get_user_repository)]
```

**Impacto:** Reduzir acoplamento no nível de apresentação.

---

### 🟠 IMPORTANTE: Reorganizar core/dependencies.py

Considerar dividir em:
- `core/factories.py` - Manufacturing de serviços
- `core/security.py` - Definições de auth (oauth2_scheme)
- `core/guards.py` - Auth guards (get_current_user, etc)

**Impacto:** Melhor organização, responsabilidades claras.

---

## 7. Diagrama Atual vs Ideal

### Atual (com problemas):
```
┌──────────────────────────┐
│  API (endpoints)         │
│  ├─ imports SQLUserRepository ❌
│  └─ imports dependencies.py ❌
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  core/dependencies.py    │
│  ├─ imports TokenCache ❌
│  ├─ imports SQLUserRepository ❌
│  └─ factories & guards
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  Services                │
│  ├─ depends on AbstractUserRepository ✅
│  └─ depends on TokenCache (concreto) ❌
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  Infrastructure          │
│  ├─ SQLUserRepository    │
│  └─ TokenCache (Redis)   │
└──────────────────────────┘
```

### Ideal (Clean Architecture):
```
┌──────────────────────────┐
│  API (endpoints)         │
│  └─ depends on Abstract* ✅
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  Services                │
│  └─ depends on Abstract* ✅
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  Domain (Abstracts)      │
│  ├─ AbstractUserRepository
│  ├─ AbstractTokenCache
│  └─ Entities
└─────────┬────────────────┘
          │
┌─────────▼────────────────┐
│  Infrastructure          │
│  ├─ SQLUserRepository    │
│  └─ RedisTokenCache      │
└──────────────────────────┘
```

---

## 8. Conclusão

### Placar: 6.5/10

**Acertos:**
- ✅ Domain layer bem isolado e pure
- ✅ ORM models não vazam
- ✅ Repositórios abstratos implementados
- ✅ Services com lógica clara
- ✅ DTOs na camada correta

**Problemas:**
- ❌ Dependencies.py centraliza e importa concretos
- ❌ Controllers sabem de implementações (SQLUserRepository)
- ❌ Services dependem de TokenCache concreto
- ⚠️ Falta abstração para TokenCache

### Próximos Passos (Prioridade)

1. **P1** - Criar `AbstractTokenCache` em domain/repositories/
2. **P1** - Mudar retorno de `get_user_repository()` para `AbstractUserRepository`
3. **P2** - Refatorar endpoints para usar tipos abstratos
4. **P2** - Reorganizar `dependencies.py` em múltiplos arquivos
5. **P3** - Review de circular dependencies
6. **P3** - Adicionar testes de isomorfismo de dependências

---

## Referências

- **Clean Architecture** - Robert C. Martin (Uncle Bob)
- **Dependency Inversion Principle** - SOLID
- **Hexagonal Architecture** (Ports & Adapters)
