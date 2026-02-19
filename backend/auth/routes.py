from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from auth.security import create_access_token, hash_password, verify_password
from database import users_collection

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    try:
        users_collection.insert_one(
            {
                "username": body.username,
                "hashed_password": hash_password(body.password),
            }
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    return {"message": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = users_collection.find_one({"username": body.username})
    if user is None or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(data={"sub": user["username"]})
    return TokenResponse(access_token=token)
