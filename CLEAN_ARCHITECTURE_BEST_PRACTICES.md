# Clean Architecture - Boas Práticas e Próximos Passos

---

## 1. Checklist para Manutenção Contínua

Ao adicionar novos recursos, use este checklist:

### ✅ Quando Criar uma Nova Entidade

- [ ] Entidade criada em `domain/entities/`
- [ ] Sua classe é um Pydantic BaseModel puro (sem imports de framework)
- [ ] Sem dependências externas (ex: ORM, cache)
- [ ] Validações de negócio estão na entidade

**Exemplo:**
```python
# ✅ Correto
class User(BaseModel):
    id: uuid.UUID
    email: EmailStr
    @field_validator("email")
    def lowercase_email(cls, v): return v.lower()

# ❌ Incorreto
class User:
    def __init__(self, session):  # ← Acoplamento!
        self.session = session
```

---

### ✅ Quando Criar um Novo Repositório

1. **Criar interface abstrata em `domain/repositories/`**
   ```python
   class AbstractProductRepository(ABC):
       @abstractmethod
       async def get_by_id(...): ...
   ```

2. **Implementar em `infrastructure/database/`**
   ```python
   class SQLProductRepository(AbstractProductRepository):
       def __init__(self, session):
           self._session = session
   ```

3. **Adicionar factory em `core/factories.py`**
   ```python
   def get_product_repository(
       session: Annotated[AsyncSession, Depends(get_db)]
   ) -> AbstractProductRepository:
       return SQLProductRepository(session)
   ```

4. **Usar em endpoints via tipo abstrato**
   ```python
   async def list_products(
       repo: Annotated[AbstractProductRepository, Depends(get_product_repository)]
   ): ...
   ```

---

### ✅ Quando Criar um Novo Serviço

1. **Aceitar apenas abstrações no `__init__`**
   ```python
   class ProductService:
       def __init__(self, repo: AbstractProductRepository):
           self._repo = repo  # ✅ Interface, não concreto!
   ```

2. **Factory em `core/factories.py`**
   ```python
   def get_product_service(
       repo: Annotated[AbstractProductRepository, Depends(get_product_repository)]
   ) -> ProductService:
       return ProductService(repo=repo)
   ```

3. **Usar em endpoints via factory**
   ```python
   async def create_product(
       svc: Annotated[ProductService, Depends(get_product_service)]
   ): ...
   ```

---

### ✅ Quando Criar um Novo Endpoint

1. **Depender via tipo abstrato**
   ```python
   # ✅ Correto
   repo: Annotated[AbstractProductRepository, Depends(...)]
   
   # ❌ Incorreto
   repo: Annotated[SQLProductRepository, Depends(...)]
   ```

2. **Usar tipos claros e documentados**
   ```python
   @router.get("/{id}", response_model=ProductResponse)
   async def get_product(
       id: uuid.UUID,
       repo: Annotated[AbstractProductRepository, Depends(get_product_repository)],
   ) -> ProductResponse:
       """[Description] and why each dependency exists."""
       product = await repo.get_by_id(id)
       if not product:
           raise ProductNotFoundException(str(id))
       return ProductResponse.model_validate(product)
   ```

3. **Manter controllers finos**
   - Lógica de negócio → Services
   - Transformação de dados → Services
   - HTTP stuff → Controllers (status, headers, etc)

---

## 2. Padrões que Devem ser Seguidos

### ✅ Mapeamento ORM ↔ Domain

```python
# Infrastructure
@staticmethod
def _to_domain(orm: UserORM) -> User:
    return User.model_validate(orm)

@staticmethod
def _to_orm(user: User) -> UserORM:
    return UserORM(
        id=user.id,
        email=user.email,
        # ... rest of fields
    )
```

**Por quê?** Isolação do ORM. Se SQLAlchemy mudar, só muda aqui.

---

### ✅ Exceções Personalizadas em `core/exceptions.py`

```python
class ProductNotFoundException(HTTPException):
    def __init__(self, product_id: str):
        super().__init__(
            status_code=404,
            detail=f"Product {product_id} not found"
        )
```

**Por quê?** Centralizado, testável, sem repetição.

---

### ✅ Use Type Aliases para DI Complexa

```python
# Em guards.py ou dependencies.py
CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]

# Em endpoints
async def get_profile(user: CurrentUser): ...
async def admin_action(admin: AdminUser): ...
```

**Por quê?** Mais limpo, menos repetição, fácil de mudar.

---

## 3. Anti-Padrões a Evitar

### ❌ Não Importe Concretos em Controllers

```python
# ❌ NUNCA FAÇA
from app.infrastructure.database.user_repository import SQLUserRepository

async def get_user(repo: SQLUserRepository): ...

# ✅ SEMPRE FAÇA
from app.domain.repositories.user_repository import AbstractUserRepository

async def get_user(repo: Annotated[AbstractUserRepository, Depends(...)]): ...
```

---

### ❌ Não Crie Instâncias Diretas em Endpoints

```python
# ❌ NUNCA
async def login(email: str):
    session = AsyncSessionLocal()  # ← Direct instantiation!
    repo = SQLUserRepository(session)  # ← Tight coupling!

# ✅ SEMPRE
async def login(
    email: str,
    repo: Annotated[AbstractUserRepository, Depends(get_user_repository)]
): ...
```

---

### ❌ Não Misture Responsabilidades em Services

```python
# ❌ Serviço fazendo muitas coisas
class UserService:
    async def __init__(self):
        self.db = SQLAlchemy()
        self.cache = Redis()
        self.email = EmailClient()

# ✅ Serviço foco
class UserService:
    def __init__(
        self,
        repo: AbstractUserRepository,
        cache: AbstractTokenCache,
    ):
        self._repo = repo
        self._cache = cache
```

---

### ❌ Não Coloque Lógica de Negócio em Controllers

```python
# ❌ Controllers gordos
@router.post("/users")
async def create_user(email, password):
    # Validation ← Logic!
    if len(password) < 8:
        raise ValidationError()
    # Hashing ← Logic!
    hashed = bcrypt.hash(password)
    # Create ← DB stuff!
    user = User(email=email, hashed_password=hashed)

# ✅ Controllers finos
@router.post("/users", response_model=UserResponse)
async def create_user(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)]
) -> UserResponse:
    user = await service.register(
        email=body.email,
        password=body.password
    )
    return UserResponse.model_validate(user)
```

---

## 4. Testes Unitários com Abstrações

### ✅ Mock Repositories para Testes

```python
# tests/mocks.py
class MockUserRepository(AbstractUserRepository):
    def __init__(self):
        self._users = {}
    
    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._users.get(user_id)
    
    async def create(self, user: User) -> User:
        self._users[user.id] = user
        return user
```

### ✅ Testar Services com Mocks

```python
@pytest.mark.asyncio
async def test_user_profile_update():
    # Setup
    mock_repo = MockUserRepository()
    user = User(id=uuid.uuid4(), email="test@example.com", ...)
    await mock_repo.create(user)
    
    service = UserService(user_repo=mock_repo)
    
    # Execute
    updated = await service.update_profile(
        user_id=user.id,
        full_name="New Name"
    )
    
    # Assert
    assert updated.full_name == "New Name"
```

---

## 5. Dependência Cíclica (Circular Dependency)

### ✅ Como Evitar

**Problema:** `factories.py` importa de `guards.py` que importa de `factories.py`

**Solução:** Usar lazy imports ou reorganizar dependências

```python
# ✅ Em guards.py, importar dentro da função
def require_roles(*roles):
    async def _guard(current_user: User = Depends(get_current_active_user)):
        # ← get_current_active_user importado implicitamente
        ...
    return _guard
```

---

## 6. Estrutura Recomendada para Novos Módulos

```
app/
├── domain/
│   ├── entities/
│   │   └── product.py          ← Entity pura
│   └── repositories/
│       └── product_repository.py ← Interface abstrata
├── infrastructure/
│   ├── database/
│   │   ├── models.py           ← ORM product
│   │   └── product_repository.py ← Implementação SQL
│   └── ...
├── services/
│   └── product_service.py      ← Lógica de negócio
├── api/
│   └── v1/
│       ├── endpoints/
│       │   └── products.py     ← Controllers
│       └── schemas.py          ← DTOs
└── core/
    └── factories.py            ← Factories (adicionar aqui!)
```

---

## 7. Migration Checklist

Ao onboarding alguém no projeto:

- [ ] Ler [CLEAN_ARCHITECTURE_ANALYSIS.md](CLEAN_ARCHITECTURE_ANALYSIS.md)
- [ ] Ler [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)
- [ ] Entender estrutura em `app/core/`
- [ ] Entender diferença entre `domain/` (puro) vs `infrastructure/` (detalhes)
- [ ] Entender padrão de factories em `core/factories.py`
- [ ] Não fazer imports de `infrastructure` em `services`

---

## 8. Evoluindo a Arquitetura

### Quando Adicionar Novos Componentes

| Componente | Localização | Padrão |
|-----------|-------------|--------|
| **Entity** | `domain/entities/` | Pydantic BaseModel puro |
| **Repository (interface)** | `domain/repositories/` | ABC com @abstractmethod |
| **Repository (impl)** | `infrastructure/database/` | Implementação de interface |
| **Cache (interface)** | `domain/repositories/` | ABC com @abstractmethod |
| **Cache (impl)** | `infrastructure/cache/` | Implementação de interface |
| **Service** | `services/` | Depende de abstrações |
| **Endpoint** | `api/v1/endpoints/` | Depende de abstrações |
| **DTO** | `api/v1/schemas.py` | Pydantic BaseModel |
| **Factory** | `core/factories.py` | Função retorna abstrações |

---

## 9. Referências

- **Clean Architecture** - Robert C. Martin (Uncle Bob)
  - https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
  
- **Dependency Inversion Principle** - SOLID
  - https://en.wikipedia.org/wiki/Dependency_inversion_principle

- **Hexagonal Architecture** (Ports & Adapters)
  - https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)

- **FastAPI Dependency Injection**
  - https://fastapi.tiangolo.com/tutorial/dependencies/

---

## Conclusão

Seu projeto agora segue **Clean Architecture** com excelência. Mantenha este padrão adicionando:
- ✅ Abstrações antes de implementações
- ✅ Dependência de interfaces, não concretos
- ✅ Factories centralizadas
- ✅ Testes com mocks abstratos

**Placar Final: 8.5/10** 🎉
