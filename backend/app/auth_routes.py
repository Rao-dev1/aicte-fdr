from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Actor, create_token, get_actor, hash_password, require, verify_password
from .db import get_db
from .models import Institution, User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    name: str
    role: str
    institution_id: Optional[int]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=200)
    role: Literal["INSTITUTION_USER", "REGULATOR_OFFICER", "APPROVING_AUTHORITY", "ADMIN"]
    institution_id: Optional[int] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: Optional[str]
    role: str
    institution_id: Optional[int]


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    token = create_token(user.username, user.full_name, user.role, user.institution_id)
    return LoginOut(
        access_token=token,
        username=user.username,
        name=user.full_name,
        role=user.role,
        institution_id=user.institution_id,
    )


@router.get("/me")
def me(actor: Actor = Depends(get_actor)):
    return {
        "username": actor.name,
        "name": actor.full_name,
        "role": actor.role,
        "institution_id": actor.institution_id,
    }


@router.post("/users", status_code=201, response_model=UserOut)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: Actor = Depends(require())):
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    if body.role == "INSTITUTION_USER":
        if body.institution_id is None or db.get(Institution, body.institution_id) is None:
            raise HTTPException(status_code=400, detail="Institution users need a valid institution_id")
    user = User(
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        role=body.role,
        institution_id=body.institution_id if body.role == "INSTITUTION_USER" else None,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
